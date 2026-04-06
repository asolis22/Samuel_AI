# reaction_gif_engine.py
# Decides WHEN to show a reaction GIF and what to search for.
# Flow: user message → classify → pick GIF search query → fetch from Tenor/Giphy
# GIF plays first (5s), then Samuel's eye expression shows after.

import os
import random
import sqlite3
import requests
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

DB_NAME = "reaction_gif_learning.db"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / DB_NAME

GIPHY_API_KEY    = os.getenv("GIPHY_API_KEY")
GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"
TENOR_KEY        = "AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCDY"  # free demo key

# ── Trigger patterns → (reaction_label, gif_search_query, confidence) ──
# These are the situations where a GIF is definitely appropriate.
# Organized by category so it's easy to add more.

GIF_TRIGGERS = [
    # ── Greetings ──────────────────────────────────────────────────────
    ("greeting",   "good morning gif",              0.95, [
        "good morning", "gm!", "morning!", "buenos días", "buenas mañanas"]),
    ("greeting",   "good night sweet dreams gif",   0.95, [
        "good night", "goodnight", "gn!", "buenas noches", "going to sleep"]),
    ("greeting",   "hello hi wave gif",             0.90, [
        "hi samuel", "hey samuel", "hello samuel", "hola samuel",
        "hi!", "hey!", "hello!", "hola!"]),
    ("greeting",   "welcome back gif",              0.88, [
        "i'm back", "im back", "i'm home", "im home"]),

    # ── Excitement / Celebration ───────────────────────────────────────
    ("excited",    "excited jumping celebration gif", 0.92, [
        "i'm so excited", "im so excited", "i am so excited",
        "so excited!!", "omg so excited", "i can't wait", "i cant wait",
        "finally!!", "it's happening", "let's go!", "lets go!"]),
    ("excited",    "celebration confetti gif",      0.90, [
        "i got the job", "i got in", "i passed", "i got accepted",
        "we won", "i finished", "i did it", "i graduated"]),
    ("happy",      "happy dance gif",               0.88, [
        "i'm so happy", "im so happy", "best day ever",
        "this made my day", "i love this"]),

    # ── Tiredness / Low energy ─────────────────────────────────────────
    ("tired",      "so tired exhausted gif",        0.93, [
        "i'm so tired", "im so tired", "i am so tired",
        "so tired", "exhausted", "i'm exhausted", "im exhausted",
        "i need sleep", "i can't sleep", "i haven't slept"]),
    ("tired",      "monday morning tired coffee gif", 0.88, [
        "it's monday", "hate mondays", "ugh monday"]),
    ("tired",      "sleepy yawning gif",            0.85, [
        "i'm sleepy", "im sleepy", "so sleepy", "yawning",
        "can't keep my eyes open"]),

    # ── Stress / Overwhelmed ───────────────────────────────────────────
    ("stressed",   "stressed overwhelmed gif",      0.90, [
        "i'm so stressed", "im so stressed", "so much to do",
        "overwhelmed", "i'm overwhelmed", "too much", "i can't do this",
        "breaking down", "i'm losing it"]),
    ("nervous",    "nervous anxious gif",           0.88, [
        "i'm so nervous", "im so nervous", "nervous wreck",
        "i have a presentation", "i have an interview", "wish me luck",
        "i'm scared", "im scared"]),

    # ── Sad / Emotional ────────────────────────────────────────────────
    ("sad",        "sad crying gif",                0.88, [
        "i'm so sad", "im so sad", "i want to cry", "i'm crying",
        "im crying", "i miss", "this is sad", "i feel sad",
        "feeling down", "having a bad day"]),
    ("sad",        "it will be okay comfort gif",   0.85, [
        "i failed", "i messed up", "everything went wrong",
        "nothing is working", "i give up"]),

    # ── Hungry / Food ──────────────────────────────────────────────────
    ("hungry",     "hungry food craving gif",       0.90, [
        "i'm so hungry", "im so hungry", "i'm starving", "im starving",
        "what should i eat", "i need food", "food please"]),
    ("food",       "eating delicious gif",          0.85, [
        "i'm eating", "just ate", "this food is so good",
        "favorite snack", "i got food"]),

    # ── Boredom ────────────────────────────────────────────────────────
    ("bored",      "bored doing nothing gif",       0.88, [
        "i'm so bored", "im so bored", "nothing to do",
        "so bored", "bored out of my mind", "i'm bored", "im bored"]),

    # ── Confusion ──────────────────────────────────────────────────────
    ("confused",   "confused what gif",             0.85, [
        "i'm so confused", "im so confused", "what is going on",
        "i don't understand", "this makes no sense", "what??"]),

    # ── Anger / Frustration ────────────────────────────────────────────
    ("angry",      "frustrated annoyed gif",        0.85, [
        "i'm so mad", "im so mad", "so annoying", "this is unfair",
        "i'm so frustrated", "im so frustrated", "why would they do that"]),

    # ── Surprise ───────────────────────────────────────────────────────
    ("surprised",  "shocked surprised reaction gif", 0.88, [
        "no way", "you're kidding", "are you serious", "omg",
        "oh my god", "what?!", "i can't believe it", "wow"]),

    # ── Love / Affection ───────────────────────────────────────────────
    ("love",       "sending love hearts gif",       0.88, [
        "i love you", "i love this", "aww", "that's so sweet",
        "you're the best", "this is so cute"]),

    # ── Blessing / Faith ───────────────────────────────────────────────
    ("blessed",    "blessed thankful grateful gif", 0.90, [
        "i'm so blessed", "im so blessed", "god is good",
        "thank the lord", "i'm grateful", "so thankful"]),

    # ── Victory / Success ──────────────────────────────────────────────
    ("triumph",    "victory winner celebration gif", 0.90, [
        "i won", "we won", "first place", "i'm the best",
        "nailed it", "killed it", "aced it"]),

    # ── Weekend / Vibes ────────────────────────────────────────────────
    ("happy",      "friday weekend gif",            0.88, [
        "it's friday", "finally friday", "weekend is here",
        "it's the weekend"]),
    ("relaxed",    "relaxing chill vibes gif",      0.82, [
        "just chilling", "relaxing", "no plans today", "day off"]),

    # ── Self-state questions (how are you etc.) ────────────────────────
    ("blessed",    "doing great blessed gif",       0.92, [
        "how are you", "how are you doing", "how are you samuel",
        "you okay", "are you okay samuel"]),
    ("happy",      "having a good day gif",         0.90, [
        "how was your day", "how was your day samuel",
        "what are you doing", "wyd samuel"]),
]

# ── Info/tool patterns that should NOT get GIFs ───────────────────────
_NO_GIF_HINTS = {
    "what", "when", "where", "why", "how", "who",
    "explain", "search", "look up", "latest", "calculate",
    "difference", "capital", "define", "translate",
    "fix", "error", "install", "help me code", "debug"
}


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_reaction_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                predicted_reaction TEXT,
                predicted_gif_prompt TEXT,
                correct INTEGER,
                corrected_reaction TEXT,
                corrected_gif_prompt TEXT,
                timestamp TEXT
            )
        """)


def list_training_rows(limit: int = 500) -> List[dict]:
    init_reaction_db()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id, text, predicted_reaction, predicted_gif_prompt, correct,
                   corrected_reaction, corrected_gif_prompt, timestamp
            FROM training_data ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def save_feedback(text: str, predicted_reaction: str, predicted_gif_prompt: str,
                  correct: bool, corrected_reaction: str = None,
                  corrected_gif_prompt: str = None) -> None:
    init_reaction_db()
    with _conn() as conn:
        conn.execute("""
            INSERT INTO training_data
            (text, predicted_reaction, predicted_gif_prompt, correct,
             corrected_reaction, corrected_gif_prompt, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (text, predicted_reaction, predicted_gif_prompt, 1 if correct else 0,
              corrected_reaction or predicted_reaction,
              corrected_gif_prompt or predicted_gif_prompt))


def find_similar_learned_response(text: str, threshold: float = 0.74):
    """Check learned corrections for similar past messages."""
    init_reaction_db()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT text, corrected_reaction, corrected_gif_prompt
            FROM training_data
            WHERE corrected_reaction IS NOT NULL AND corrected_gif_prompt IS NOT NULL
        """).fetchall()

    best_score = 0.0
    best_match = None
    for row in rows:
        score = SequenceMatcher(None, text.lower(), row["text"].lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = {"reaction": row["corrected_reaction"],
                          "gif_prompt": row["corrected_gif_prompt"]}
    if best_match and best_score >= threshold:
        return best_match, best_score
    return None, best_score


# Patterns that mean the user is ASKING for a specific GIF
_GIF_REQUEST_PATTERNS = [
    r"send\s+(?:me\s+)?(?:a\s+)?(.+?)\s+gif",
    r"show\s+(?:me\s+)?(?:a\s+)?(.+?)\s+gif",
    r"give\s+(?:me\s+)?(?:a\s+)?(.+?)\s+gif",
    r"find\s+(?:me\s+)?(?:a\s+)?(.+?)\s+gif",
    r"(.+?)\s+gif\s+please",
    r"(.+?)\s+gif[!?]*$",
    r"send\s+(?:a\s+)?gif\s+(?:of\s+)?(.+)",
    r"gif\s+of\s+(.+)",
]


def _extract_gif_request(text: str):
    """
    If the user is explicitly asking for a GIF, extract what they want.
    Returns (search_query, True) or (None, False)
    """
    import re
    t = text.strip().lower()
    for pattern in _GIF_REQUEST_PATTERNS:
        m = re.search(pattern, t)
        if m:
            query = m.group(1).strip().rstrip(".,!?")
            if len(query) > 1:
                return query + " gif", True
    return None, False


def predict_reaction_and_gif(text: str) -> Dict:
    """
    Main entry point. Returns dict with:
      reaction, gif_prompt, confidence, should_react_with_gif
    """
    t = text.strip().lower()

    # ── Check if user is ASKING for a specific GIF ──────────────────
    query, is_request = _extract_gif_request(text)
    if is_request:
        return {"reaction": "happy", "gif_prompt": query,
                "confidence": 0.99, "should_react_with_gif": True,
                "source": "user_request"}

    # Skip obvious info/tool questions
    if any(h in t for h in _NO_GIF_HINTS) and "?" in t:
        return {"reaction": "neutral", "gif_prompt": "", "confidence": 0.0,
                "should_react_with_gif": False}

    # Check learned corrections first
    learned, score = find_similar_learned_response(text)
    if learned and score >= 0.80:
        return {"reaction": learned["reaction"], "gif_prompt": learned["gif_prompt"],
                "confidence": score, "should_react_with_gif": True, "source": "learned"}

    # Check trigger patterns
    best_reaction = None
    best_prompt   = None
    best_conf     = 0.0

    for reaction, gif_prompt, base_conf, triggers in GIF_TRIGGERS:
        for trigger in triggers:
            if trigger in t:
                # Boost confidence if multiple triggers match
                conf = base_conf
                matches = sum(1 for tr in triggers if tr in t)
                if matches > 1:
                    conf = min(0.99, conf + 0.05 * (matches - 1))
                if conf > best_conf:
                    best_conf     = conf
                    best_reaction = reaction
                    best_prompt   = gif_prompt
                break

    if best_reaction:
        return {"reaction": best_reaction, "gif_prompt": best_prompt,
                "confidence": best_conf, "should_react_with_gif": True,
                "source": "trigger"}

    return {"reaction": "neutral", "gif_prompt": "", "confidence": 0.0,
            "should_react_with_gif": False, "source": "none"}


# ── GIF fetchers ───────────────────────────────────────────────────────

def giphy_search_one_gif(gif_prompt: str) -> Optional[Dict]:
    if not GIPHY_API_KEY:
        return None
    try:
        resp = requests.get(GIPHY_SEARCH_URL, params={
            "api_key": GIPHY_API_KEY, "q": gif_prompt,
            "limit": 10, "rating": "g", "lang": "en",
        }, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("data", [])
        if not results:
            return None
        random.shuffle(results)
        for item in results:
            for key in ("fixed_height", "downsized", "original"):
                url = item.get("images", {}).get(key, {}).get("url")
                if url:
                    return {"title": item.get("title", gif_prompt),
                            "gif_url": url, "page_url": item.get("url")}
    except Exception as e:
        print(f"[GIF] Giphy error: {e}")
    return None


def tenor_search_one_gif(gif_prompt: str) -> Optional[str]:
    """Fetch one GIF URL from Tenor. No API key required (uses demo key)."""
    try:
        resp = requests.get(
            "https://tenor.googleapis.com/v2/search",
            params={"q": gif_prompt, "key": TENOR_KEY,
                    "limit": 8, "contentfilter": "medium", "media_filter": "gif"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            print(f"[GIF] Tenor: 0 results for '{gif_prompt}'")
            return None
        item = random.choice(results[:5])
        for fmt in ("tinygif", "mediumgif", "gif"):
            url = item.get("media_formats", {}).get(fmt, {}).get("url")
            if url:
                return url
    except Exception as e:
        print(f"[GIF] Tenor error: {e}")
    return None


def fetch_reaction_gif(gif_prompt: str) -> Optional[str]:
    """Try Giphy first, fall back to Tenor. Returns URL or None."""
    if GIPHY_API_KEY:
        result = giphy_search_one_gif(gif_prompt)
        if result and result.get("gif_url"):
            return result["gif_url"]
    return tenor_search_one_gif(gif_prompt)


# ── DB helpers for trainer panel ──────────────────────────────────────

def delete_training_row(row_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM training_data WHERE id=?", (row_id,))

def update_training_row(row_id: int, corrected_reaction: str,
                        corrected_gif_prompt: str) -> None:
    with _conn() as conn:
        conn.execute("""UPDATE training_data
            SET corrected_reaction=?, corrected_gif_prompt=?, correct=0 WHERE id=?
        """, (corrected_reaction.strip(), corrected_gif_prompt.strip(), row_id))

def list_examples():
    rows = list_training_rows()
    for r in rows:
        r["final_reaction"]   = r["corrected_reaction"]   or r["predicted_reaction"]
        r["final_gif_prompt"] = r["corrected_gif_prompt"] or r["predicted_gif_prompt"]
    return rows

def delete_example(row_id: int):
    delete_training_row(row_id)