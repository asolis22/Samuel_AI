# background_learner.py
# Samuel's autonomous background learning — detective mode.
# Continuously works through topic seeds + memory-derived queries.
# Cycles every 5 minutes while Samuel is running.
# All nuggets land in Pending Review for your approval — nothing auto-approved.

import re
import time
import threading
import json
from typing import List, Optional

import samuel_store as store
import knowledge_store as ks
from web_search import research as web_research

# ---- CONFIG ----
LEARN_INTERVAL_SECONDS = 300    # cycle every 5 minutes
MAX_QUERIES_PER_CYCLE  = 3      # searches per cycle
MAX_PAGES_PER_QUERY    = 4      # pages per search
MIN_TEXT_LENGTH        = 300    # skip very short pages

# Full topic seed list — Samuel works through ALL of these
# like a detective, never repeating until all are exhausted
TOPIC_SEEDS = [
    # Study & Academic
    "study tips for college students",
    "note taking strategies college",
    "how to memorize information faster",
    "active recall studying technique",
    "spaced repetition learning method",
    "pomodoro technique productivity",
    "how to focus while studying",
    "best ways to prepare for exams",
    "how to write better essays",
    "understanding difficult concepts faster",

    # Engineering / Technical
    "embedded systems beginner guide",
    "PCB design tips for beginners",
    "how to read circuit diagrams",
    "microcontroller programming basics",
    "electronics components guide",
    "Arduino vs Raspberry Pi projects",
    "how to debug embedded code",
    "signal processing basics",
    "how to use oscilloscope",
    "soldering tips for beginners",

    # Health & Wellness
    "health and wellness tips for students",
    "sleep hygiene for college students",
    "how to reduce stress and anxiety",
    "exercise routines for busy students",
    "nutrition tips for brain health",
    "mental health self care habits",
    "how to build healthy habits",
    "dealing with burnout tips",

    # Finance & Life Skills
    "personal finance basics for students",
    "budgeting for beginners",
    "how to save money in college",
    "building credit score young adults",
    "investing basics for beginners",
    "how to manage time effectively",
    "goal setting techniques that work",
    "how to be more productive daily",

    # Career & Growth
    "career advice for young professionals",
    "how to build a resume",
    "internship tips for college students",
    "networking tips for introverts",
    "how to prepare for job interviews",
    "soft skills that matter most",
    "how to learn new skills faster",
    "building a portfolio as a student",

    # Interests - Superheroes
    "Superhero Universe",
    "Spider-Man",
    "Iron Man",
    "Batman and Bruce Wayne Robin and Dick Grayson Jason Todd Tim Drake and Damian Wayne",
    "The Batfamily",
    "Danny Phantom and its fandom",
    "superhero team dynamics and found family tropes",
    "superhero origin stories themes and symbolism",
    "spoiler free recommendations for superhero movies and shows",
    "compare and contrast heroes villains moral philosophies",
    "power scaling explained without being toxic",

    # Interests
    "Anime",
    "cartoon recommendations similar to Danny Phantom Teen Titans Ben 10",
    "how animated storytelling differs from live action",
    "episode by episode breakdowns themes and character growth",
    "villain writing in cartoons how to make them compelling",
    "found family and team dynamics in animated series",
    "animation trivia and behind the scenes facts with fact checking",

    # Books
    "books with strong hero vs villain dynamics and high emotional stakes",
    "books with male main characters underdog to powerful growth arcs",
    "books with super smart tactical genius protagonists and strategy battles",
    "books with overpowered protagonists but deep character development",
    "books with morally gray heroes and complicated villains",
    "antihero protagonists with redemption arcs and happy endings",
    "angst heavy books with happy endings and emotional payoff",
    "trauma recovery stories with healing found family and hope",
    "hurt comfort stories with action suspense and character growth",
    "rivals to allies to family dynamics in dark stories",
    "villains who are charismatic strategic and psychologically scary",
    "cat and mouse plots mastermind vs mastermind",
    "revenge arcs that turn into redemption and healing",
    "high stakes missions heists and infiltration with tactical planning",
    "training arcs and skill progression in darker stories",
    "protective main character themes loyalty sacrifice and devotion",

    # Genres
    "dark fantasy with hope and satisfying endings",
    "urban fantasy with powerful main characters and deep angst",
    "dystopian fiction with underdog heroes and villain regimes",
    "psychological thrillers with twisty plots but not gory",
    "mystery thrillers with strong villains and clever protagonists",
    "superhero novels and comic style storytelling in prose",

    # Reading support
    "how to recommend books based on tropes and mood not just genre",
    "content warnings and trigger summaries spoiler free",
    "spoiler free book summaries and chapter recaps",
    "how to find books similar to a specific character archetype",
    "how to build a reading list and keep continuity across series",
]

BLOCKED_TOPICS = {
    "politics", "religion", "celebrities", "gossip",
    "violence", "drugs", "weapons", "gambling", "nsfw",
}

_BAD_QUERY_PATTERNS = [
    r"^i can",
    r"^i will",
    r"^i don",
    r"^sure",
    r"^of course",
    r"^let me",
    r"^please",
    r"^here ",
    r"^okay",
    r"^ok ",
    r"\?$",
    r"\bsamuel\b",
    r"\bsorry\b",
    r"\bhelp you\b",
    r"\bprovide\b",
    r"\blocation\b",
]

# Internal queue — tracks which seeds haven't been searched yet this session
_seed_queue: List[str] = []
_queue_lock = threading.Lock()

# -------------------------------------------------------
# FOREGROUND PRIORITY CONTROL
# -------------------------------------------------------

_pause_event = threading.Event()   # set = learner paused
_stop_event = threading.Event()
_learn_thread: Optional[threading.Thread] = None

_active_foreground = 0
_fg_lock = threading.Lock()


def pause_learning():
    _pause_event.set()


def resume_learning():
    global _active_foreground
    with _fg_lock:
        if _active_foreground <= 0:
            _pause_event.clear()


def begin_foreground_task():
    global _active_foreground
    with _fg_lock:
        _active_foreground += 1
        _pause_event.set()


def end_foreground_task():
    global _active_foreground
    with _fg_lock:
        _active_foreground = max(0, _active_foreground - 1)
        if _active_foreground == 0:
            _pause_event.clear()


def learner_paused() -> bool:
    return _pause_event.is_set()


def _wait_if_paused(verbose: bool = False) -> bool:
    """
    Returns True if should stop entirely.
    Returns False when it's okay to continue.
    """
    while _pause_event.is_set() and not _stop_event.is_set():
        if verbose:
            print("[LEARN] Waiting... foreground task active.")
        _stop_event.wait(timeout=0.25)
    return _stop_event.is_set()


def _reset_seed_queue():
    global _seed_queue
    import random
    with _queue_lock:
        _seed_queue = TOPIC_SEEDS[:]
        random.shuffle(_seed_queue)


def _pop_seed_queries(n: int) -> List[str]:
    global _seed_queue
    with _queue_lock:
        if len(_seed_queue) < n:
            import random
            _seed_queue = TOPIC_SEEDS[:]
            random.shuffle(_seed_queue)
        out = _seed_queue[:n]
        _seed_queue = _seed_queue[n:]
        return out


def _is_bad_query(q: str) -> bool:
    q = q.strip().lower()
    if len(q) < 6 or len(q) > 120:
        return True
    for pat in _BAD_QUERY_PATTERNS:
        if re.search(pat, q, re.I):
            return True
    if any(b in q for b in BLOCKED_TOPICS):
        return True
    return False


# -------------------------------------------------------
# QUERY GENERATION
# -------------------------------------------------------

def _queries_from_memory(limit: int = 2) -> List[str]:
    queries = []
    try:
        # fallback if your store has list_memory_current instead
        if hasattr(store, "list_saved_memories"):
            rows = store.list_saved_memories(owner="user", limit=200)
        else:
            rows = store.dump_memory_current(limit=200)

        for r in rows:
            if r.get("owner") != "user":
                continue

            val = (r.get("value") or "").strip()
            cat = (r.get("category") or "").lower()
            stab = r.get("stability", "adaptive")

            if not val or stab == "temporary":
                continue
            if len(val) < 4 or len(val) > 80:
                continue

            q = None
            if any(x in cat for x in ("major", "school", "class", "course")):
                q = val.lower() + " study tips"
            elif any(x in cat for x in ("goal", "project", "skill", "learn")):
                q = "how to " + val.lower()
            elif any(x in cat for x in ("work", "job", "career")):
                q = val.lower() + " career tips"
            elif any(x in cat for x in ("hobby", "interest")):
                q = val.lower() + " beginner guide"

            if q and not _is_bad_query(q):
                queries.append(q)
            if len(queries) >= limit:
                break
    except Exception:
        pass
    return queries


def _get_cycle_queries() -> List[str]:
    recent = set()
    try:
        recent = set(ks.recent_queries(limit=60))
    except Exception:
        pass

    mem_qs = _queries_from_memory(limit=1)
    seed_qs = _pop_seed_queries(MAX_QUERIES_PER_CYCLE)

    out = []
    for q in mem_qs + seed_qs:
        q = q.strip()
        if not q or _is_bad_query(q):
            continue
        if q in recent:
            continue
        out.append(q)
        if len(out) >= MAX_QUERIES_PER_CYCLE:
            break

    if not out:
        out = _pop_seed_queries(2)

    return out


# -------------------------------------------------------
# NUGGET EXTRACTION
# -------------------------------------------------------

def _extract_nuggets(url: str, title: str, text: str, query: str) -> List[dict]:
    try:
        from llm_ollama import ollama_chat
        from ui.theme import TEXT_MODEL
    except Exception:
        return []

    system = (
        "You are a knowledge extractor for a personal AI assistant. "
        "Read the page text and pull out 1-5 genuinely useful facts. "
        "Return ONLY raw JSON, no markdown, no backticks, no explanation. "
        'Exact format: {"nuggets":[{"topic":"short label","summary":"one useful sentence","relevance":0.8}]} '
        "Rules: "
        "- topic: 2-5 word label e.g. 'active recall', 'PCB soldering tips' "
        "- summary: one specific, actionable sentence "
        "- relevance: 0.0-1.0 based on how useful for a student/young professional "
        "- skip ads, cookie notices, navigation, legal text "
        '- if nothing useful: {"nuggets":[]}'
    )

    prompt = (
        "Search query: " + query + "\n"
        "Page title: " + (title or "?") + "\n\n"
        "Text:\n" + text[:4000]
    )

    try:
        raw = ollama_chat(
            TEXT_MODEL,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw = re.sub(r"```(?:json)?", "", (raw or "")).strip()
        s, e = raw.find("{"), raw.rfind("}")
        if s == -1 or e == -1:
            return []

        data = json.loads(raw[s:e + 1])
        clean = []

        for n in (data.get("nuggets") or []):
            topic = (n.get("topic") or "").strip()[:80]
            summary = (n.get("summary") or "").strip()
            rel = float(n.get("relevance") or 0.5)

            if topic and summary and len(summary) > 10 and rel >= 0.3:
                clean.append({
                    "topic": topic,
                    "summary": summary,
                    "relevance": rel,
                })

        return clean
    except Exception:
        return []


# -------------------------------------------------------
# MAIN LEARNING CYCLE
# -------------------------------------------------------

def run_learning_cycle(verbose: bool = False) -> dict:
    if _pause_event.is_set():
        if verbose:
            print("[LEARN] Paused before cycle start.")
        return {"queries": 0, "pages": 0, "nuggets": 0}

    queries = _get_cycle_queries()
    if not queries:
        if verbose:
            print("[LEARN] No queries this cycle.")
        return {"queries": 0, "pages": 0, "nuggets": 0}

    total_pages = 0
    total_nuggets = 0

    for query in queries:
        if _wait_if_paused(verbose=verbose):
            break

        if verbose:
            print("[LEARN] Searching:", query)

        try:
            results = web_research(query, max_results=8, fetch_top_k=MAX_PAGES_PER_QUERY)
        except Exception as e:
            if verbose:
                print("[LEARN] Search error:", e)
            try:
                ks.log_query(query, result_count=0, triggered_by="schedule")
            except Exception:
                pass
            continue

        try:
            ks.log_query(query, result_count=len(results), triggered_by="schedule")
        except Exception:
            pass

        for item in results:
            if _wait_if_paused(verbose=verbose):
                break

            url = item.get("url", "")
            title = item.get("title", "")
            text = item.get("text", "")

            if not url or len(text) < MIN_TEXT_LENGTH:
                continue

            page_id = None
            try:
                page_id = ks.save_fetched_page(url, title, text, query_used=query)
            except Exception:
                page_id = None

            total_pages += 1

            nuggets = _extract_nuggets(url, title, text, query)

            if verbose:
                print(f"[LEARN]   {url[:55]} -> {len(nuggets)} nuggets")

            for nug in nuggets:
                if _wait_if_paused(verbose=verbose):
                    break

                try:
                    ks.save_nugget(
                        source_url=url,
                        source_title=title,
                        topic=nug["topic"],
                        summary=nug["summary"],
                        relevance=nug["relevance"],
                        query_origin=query,
                    )
                    total_nuggets += 1
                except Exception:
                    pass

            if page_id is not None:
                try:
                    ks.mark_page_processed(page_id, "processed")
                except Exception:
                    pass

            if _stop_event.wait(timeout=0.2):
                break

        if _stop_event.is_set():
            break

        if _stop_event.wait(timeout=0.5):
            break

    if verbose:
        print(
            f"[LEARN] Cycle done — queries={len(queries)} "
            f"pages={total_pages} nuggets={total_nuggets}"
        )

    return {
        "queries": len(queries),
        "pages": total_pages,
        "nuggets": total_nuggets,
    }


# -------------------------------------------------------
# BACKGROUND THREAD
# -------------------------------------------------------

def start_learning_thread(interval: int = LEARN_INTERVAL_SECONDS, verbose: bool = False):
    global _learn_thread, _stop_event

    _stop_event.clear()
    _pause_event.clear()

    try:
        ks.init_knowledge_db()
    except Exception:
        pass

    _reset_seed_queue()

    def _loop():
        time.sleep(20)  # let Samuel finish booting first

        while not _stop_event.is_set():
            if _wait_if_paused(verbose=verbose):
                break

            try:
                run_learning_cycle(verbose=verbose)
            except Exception as e:
                if verbose:
                    print("[LEARN] Cycle error:", e)

            slept = 0.0
            while slept < interval and not _stop_event.is_set():
                if _pause_event.is_set():
                    break
                chunk = min(0.5, interval - slept)
                _stop_event.wait(timeout=chunk)
                slept += chunk

    _learn_thread = threading.Thread(
        target=_loop,
        name="samuel-learner",
        daemon=True
    )
    _learn_thread.start()

    if verbose:
        print(f"[LEARN] Detective mode ON — {len(TOPIC_SEEDS)} topics queued, cycling every {interval}s")


def stop_learning_thread():
    _stop_event.set()
    _pause_event.set()