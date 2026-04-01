# memory_filter.py
import re
from typing import Optional

_EPHEMERAL_PATTERNS = [
    r"\bwhat(?:'s| is) the (?:time|date|day)\b",
    r"\bwhat time is it\b",
    r"\bwhat(?:'s| is) the weather\b",
    r"\bweather (?:today|right now|currently|forecast)\b",
    r"\btemperature (?:is|outside|today)\b",
    r"\bit(?:'s| is) (?:sunny|cloudy|raining|snowing|hot|cold|warm)\b",
    r"\bfeels like \d+\b",
    r"\bprice of \w+ (?:is|was)\b",
    r"\bstock (?:price|market)\b",
    r"\bscore (?:is|was)\b",
    r"^(?:hi|hello|hey|sup|yo)[!?.\s]*$",
    r"^(?:ok|okay|sure|alright|got it|cool|thanks)[!?.\s]*$",
    r"^(?:yes|no|yeah|nope|yep|nah)[!?.\s]*$",
]
_EPHEMERAL_MKEYS = {
    "notes.item","notes.note","notes.misc","notes.temp","notes.stuff",
    "events.weather","events.time","events.date","preferences.weather",
    "notes.weather","notes.time","notes.date","notes.temperature",
}
_EPHEMERAL_CATEGORIES = {
    "weather","time","date","scores","prices","greeting","filler","acknowledgement",
}
_EPHEMERAL_VALUE_PATTERNS = [
    r"^\d{1,2}[:.]\d{2}\s*(?:am|pm)?$",
    r"\b(?:sunny|partly cloudy|overcast|raining|thunderstorm|snow|fog)\b",
    r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
]

def _is_ephemeral_text(text):
    t = (text or "").strip().lower()
    if len(t) < 3: return True
    for pat in _EPHEMERAL_PATTERNS:
        if re.search(pat, t, re.I): return True
    return False

def _is_ephemeral_value(value):
    v = (value or "").strip().lower()
    for pat in _EPHEMERAL_VALUE_PATTERNS:
        if re.search(pat, v, re.I): return True
    if re.match(r"^\d+(\.\d+)?$", v): return True
    return False

def should_remember(category, key, value, source_text=None, importance=1.0, stability="adaptive"):
    cat  = (category or "notes").strip().lower()
    key_ = (key or "item").strip().lower()
    mkey = cat + "." + key_
    val  = (value or "").strip()
    if mkey in _EPHEMERAL_MKEYS:             return False, "blocked mkey"
    if cat in _EPHEMERAL_CATEGORIES:         return False, "ephemeral category"
    if _is_ephemeral_value(val):             return False, "ephemeral value"
    if source_text and _is_ephemeral_text(source_text): return False, "ephemeral source"
    if importance < 0.65:                    return False, "low importance"
    if len(val) < 3:                         return False, "too short"
    return True, "ok"

def filter_memory_items(items, source_text=""):
    out = []
    for item in items:
        cat  = item.category if hasattr(item,"category") else item.get("category","notes")
        key_ = item.key      if hasattr(item,"key")      else item.get("key","item")
        val  = item.value    if hasattr(item,"value")    else item.get("value","")
        imp  = float(getattr(item,"importance",1.0) if hasattr(item,"importance") else item.get("importance",1.0))
        ok, _ = should_remember(cat, key_, val, source_text=source_text, importance=imp)
        if ok: out.append(item)
    return out