# memory_autosave.py
import re
import json
from dataclasses import dataclass
from typing import List, Optional

import Samuel_AI.core.samuel_store as store
from Samuel_AI.core.llm_ollama import ollama_chat
from ui.theme import TEXT_MODEL


@dataclass
class MemoryItem:
    owner: str = "user"
    category: str = "notes"
    key: str = "note"
    value: str = ""
    stability: str = "adaptive"  # core/adaptive/temporary
    importance: float = 0.7      # 0.0-2.0


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _safe_key(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:60] if s else "item"

def _cap_value(s: str, n: int = 300) -> str:
    s = _clean(s)
    return s if len(s) <= n else (s[: n - 3] + "...")

def _is_too_sensitive(category: str, key: str) -> bool:
    cat = (category or "").lower()
    k = (key or "").lower()
    blocked = {"medical", "health", "diagnosis", "mental_health", "sex", "politics"}
    if cat in blocked:
        return True
    if any(x in k for x in ["ssn", "social", "passport", "credit", "card_number"]):
        return True
    return False


def extract_rule_memories(text: str) -> List[MemoryItem]:
    t = text.strip()
    out: List[MemoryItem] = []

    # Location: "I live in X" / "I’m in X" / "I am in X"
    m = re.search(r"(?i)\b(i live in|i'm in|i am in)\b\s+(.+)$", t)
    if m:
        loc = _clean(m.group(2)).rstrip(".!")
        if 2 <= len(loc) <= 80:
            out.append(MemoryItem(category="profile", key="location", value=loc, stability="adaptive", importance=1.2))

    m = re.search(r"(?i)\bmy name is\b\s+(.+)$", t)
    if m:
        name = _clean(m.group(1)).rstrip(".!")
        if 2 <= len(name) <= 60:
            out.append(MemoryItem(category="profile", key="name", value=name, stability="core", importance=2.0))

    m = re.search(r"(?i)\b(i prefer|i like|i love|i hate|i don'?t like)\b\s+(.+)$", t)
    if m:
        verb = m.group(1).lower()
        thing = _clean(m.group(2)).rstrip(".!")
        if 2 <= len(thing) <= 120:
            key = _safe_key(thing)[:40]
            val = f"{verb}: {thing}"
            out.append(MemoryItem(category="preferences", key=key, value=val, stability="adaptive", importance=1.0))

    m = re.search(r"(?i)\bi work at\b\s+(.+)$", t)
    if m:
        out.append(MemoryItem(category="profile", key="workplace", value=_cap_value(m.group(1)), stability="adaptive", importance=1.1))

    m = re.search(r"(?i)\bi go to\b\s+(.+)$", t)
    if m:
        out.append(MemoryItem(category="profile", key="school", value=_cap_value(m.group(1)), stability="adaptive", importance=1.0))

    m = re.search(r"(?i)\bi(?:'m| am)\s+(?:a|an)\s+(.+?)\s+major\b", t)
    if m:
        out.append(MemoryItem(category="profile", key="major", value=_cap_value(m.group(1)), stability="adaptive", importance=1.2))

    return out


_MONTHS = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

def extract_event_memories(text: str) -> List[MemoryItem]:
    t = text.strip()
    out: List[MemoryItem] = []

    event_words = r"(interview|appointment|meeting|deadline|due|exam|test|quiz|presentation|flight|trip|birthday|wedding|church|service|shift)"
    date_pat = rf"(?i)\b{_MONTHS}\s+\d{{1,2}}(?:,\s*\d{{4}})?\b"
    time_pat = r"(?i)\b\d{1,2}:\d{2}\s*(am|pm)\b"

    if re.search(event_words, t, re.I) and (re.search(date_pat, t) or re.search(time_pat, t)):
        summary = _cap_value(t, 180)
        ew = re.search(event_words, t, re.I)
        ev = ew.group(1).lower() if ew else "event"
        date = re.search(date_pat, t)
        dt = _safe_key(date.group(0)) if date else "unknown_date"

        # events are usually chat-scoped unless you explicitly mark them important later
        out.append(MemoryItem(category="events", key=f"{ev}_{dt}", value=summary, stability="temporary", importance=1.3))

    return out


def llm_suggest_memories(user_text: str, recent_context: str = "", max_items: int = 4) -> List[MemoryItem]:
    system = (
        "You are a memory extractor for a personal assistant named Samuel.\n"
        "Return ONLY valid JSON (no markdown) with this shape:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "category": "profile|preferences|relationships|events|projects|habits|goals|work|school|notes",\n'
        '      "key": "short_snake_case_key",\n'
        '      "value": "short factual memory (no quotes, no long text)",\n'
        '      "stability": "core|adaptive|temporary",\n'
        '      "importance": 0.0\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only extract stable, useful facts or upcoming events.\n"
        "- Do NOT store sensitive info.\n"
        "- importance range: 0.0 to 2.0.\n"
        "- Keep value under 140 chars.\n"
        f"- Return at most {max_items} items.\n"
    )

    prompt = (
        "Recent context (optional):\n"
        f"{recent_context}\n\n"
        "User message:\n"
        f"{user_text}\n\n"
        "Extract memory items."
    )

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": prompt}]

    try:
        raw = ollama_chat(TEXT_MODEL, messages, temperature=0.1)
    except Exception:
        return []

    raw = (raw or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return []

    try:
        data = json.loads(raw[start:end+1])
    except Exception:
        return []

    items: List[MemoryItem] = []
    for it in (data.get("items") or []):
        try:
            category = _clean(it.get("category", "notes"))
            key = _safe_key(it.get("key", "item"))
            value = _cap_value(it.get("value", ""), 140)
            stability = _clean(it.get("stability", "adaptive")).lower()
            importance = float(it.get("importance", 0.7))
        except Exception:
            continue

        if not value:
            continue
        if stability not in {"core", "adaptive", "temporary"}:
            stability = "adaptive"

        items.append(MemoryItem(
            owner="user",
            category=category or "notes",
            key=key or "item",
            value=value,
            stability=stability,
            importance=max(0.0, min(2.0, importance))
        ))

    return items


def filter_memories(cands, source_text=""):
    from memory_filter import filter_memory_items
    return filter_memory_items(cands, source_text=source_text)

def save_memories(cands: List[MemoryItem], chat_id: Optional[int] = None) -> int:
    n = 0
    for m in cands:
        try:
            store.remember(
                m.owner,
                m.category,
                m.key,
                m.value,
                stability=m.stability,
                importance=float(m.importance),
                chat_id=chat_id,
                source="autosave",
            )
            n += 1
        except Exception:
            pass
    return n


def auto_memory_capture(user_text: str, recent_context: str = "", chat_id: Optional[int] = None) -> int:
    rule = extract_rule_memories(user_text)
    events = extract_event_memories(user_text)
    llm = llm_suggest_memories(user_text, recent_context=recent_context, max_items=4)

    merged = filter_memories(rule + events + llm, source_text=user_text)
    return save_memories(merged, chat_id=chat_id)