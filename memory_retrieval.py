# memory_retrieval.py
# Improved memory retrieval: semantic scoring + cross-chat search.
import re
import time
from typing import List, Dict, Optional

import Samuel_AI.core.samuel_store as store

try:
    from sentence_transformers import SentenceTransformer, util as st_util
    _ST_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    _SEMANTIC_AVAILABLE = True
except Exception:
    _SEMANTIC_AVAILABLE = False
    _ST_MODEL = None

_WORD_RE = re.compile(r"[a-z0-9]{3,}", re.I)


def _words(text: str) -> set:
    return set(_WORD_RE.findall((text or "").lower()))


def _keyword_score(q_words: set, candidate: str) -> float:
    cw = _words(candidate)
    if not cw or not q_words:
        return 0.0
    return len(q_words & cw) / max(1, len(q_words))


def _semantic_score(query: str, candidate: str) -> float:
    if not _SEMANTIC_AVAILABLE or not _ST_MODEL:
        return 0.0
    try:
        vecs  = _ST_MODEL.encode([query, candidate], convert_to_tensor=True)
        score = float(st_util.cos_sim(vecs[0], vecs[1]))
        return max(0.0, score)
    except Exception:
        return 0.0


def search_saved_memories_smart(
    query: str,
    owner: Optional[str] = "user",
    limit: int = 12,
    semantic_weight: float = 0.5,
) -> List[Dict]:
    store.init_db()
    q_words = _words(query)
    rows    = store.list_saved_memories(owner=owner, limit=500)
    now     = int(time.time())
    scored  = []

    for r in rows:
        text = (
            (r.get("mkey") or "") + " " +
            (r.get("value") or "") + " " +
            (r.get("category") or "")
        )
        kw      = _keyword_score(q_words, text)
        sem     = _semantic_score(query, text) if _SEMANTIC_AVAILABLE and query else 0.0
        imp     = float(r.get("importance") or 1.0)
        age_d   = max(0.0, (now - int(r.get("updated_ts") or now)) / 86400.0)
        recency = 1.0 / (1.0 + age_d / 30.0)

        if _SEMANTIC_AVAILABLE:
            text_s = (1.0 - semantic_weight) * kw + semantic_weight * sem
        else:
            text_s = kw

        final = text_s * 0.6 + imp * 0.25 + recency * 0.15

        if final > 0.05 or r.get("stability") == "core":
            scored.append((final, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def search_all_chats_history(
    query: str,
    current_chat_id: Optional[int] = None,
    limit_snips: int = 8,
    window_chars: int = 280,
    max_scan_per_chat: int = 300,
    semantic_weight: float = 0.4,
) -> List[Dict]:
    store.init_db()
    q_words = _words(query)
    if not q_words and not _SEMANTIC_AVAILABLE:
        return []

    conn = store._connect()
    try:
        chats = conn.execute(
            "SELECT id, name FROM chats ORDER BY created_ts DESC;"
        ).fetchall()
    finally:
        conn.close()

    now    = int(time.time())
    scored = []

    for chat in chats:
        cid   = int(chat["id"])
        cname = chat["name"]
        if current_chat_id is not None and cid == current_chat_id:
            continue

        conn2 = store._connect()
        try:
            rows = conn2.execute(
                "SELECT role, content, ts FROM messages"
                " WHERE chat_id=? ORDER BY ts DESC LIMIT ?;",
                (cid, max_scan_per_chat),
            ).fetchall()
        finally:
            conn2.close()

        for r in rows:
            txt = (r["content"] or "").strip()
            if not txt:
                continue
            kw      = _keyword_score(q_words, txt)
            sem     = _semantic_score(query, txt) if _SEMANTIC_AVAILABLE and query else 0.0
            age_d   = max(0.0, (now - int(r["ts"])) / 86400.0)
            recency = 1.0 / (1.0 + age_d)

            if _SEMANTIC_AVAILABLE:
                text_s = (1.0 - semantic_weight) * kw + semantic_weight * sem
            else:
                text_s = kw

            score = text_s * 1.5 + recency * 0.3
            if score < 0.1:
                continue

            snip = txt[:window_chars] + ("..." if len(txt) > window_chars else "")
            scored.append({
                "chat_name": cname,
                "role":      r["role"],
                "ts":        int(r["ts"]),
                "snippet":   snip,
                "score":     float(score),
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit_snips]


def build_smart_memory_pack(
    user_text: str,
    owner: str = "user",
    max_items: int = 12,
    semantic_weight: float = 0.5,
) -> str:
    hits = search_saved_memories_smart(
        user_text, owner=owner, limit=max_items, semantic_weight=semantic_weight
    )
    if not hits:
        return ""
    lines = ["SAVED MEMORY:"]
    for r in hits:
        mk   = r.get("mkey", "notes.item")
        val  = (r.get("value") or "").strip()
        stab = r.get("stability", "adaptive")
        imp  = float(r.get("importance") or 1.0)
        lines.append(
            "- " + mk + " = " + val +
            " (stability=" + stab + ", imp=" + str(round(imp, 2)) + ")"
        )
    return "\n".join(lines)


def build_cross_chat_pack(
    user_text: str,
    current_chat_id: Optional[int] = None,
    limit: int = 5,
    semantic_weight: float = 0.4,
) -> str:
    hits = search_all_chats_history(
        user_text,
        current_chat_id=current_chat_id,
        limit_snips=limit,
        semantic_weight=semantic_weight,
    )
    if not hits:
        return ""
    lines = ["RELEVANT PAST CHATS:"]
    for h in hits:
        lines.append(
            "- [" + h["chat_name"] + "/" + h["role"] + "] " + h["snippet"]
        )
    return "\n".join(lines)
