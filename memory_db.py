# memory_db.py
# Compatibility layer: maps older calls onto samuel_store's "brain memory" (saved_memories)

from typing import List, Dict, Optional
import time

import samuel_store as store


def init_db():
    store.init_db()


def remember_user_passive(category: str, key: str, value: str, confidence: float = 0.7):
    if confidence < 0.6:
        return
    store.upsert_saved_memory(
        owner="user",
        category=category.strip(),
        key=key.strip(),
        value=value.strip(),
        stability="adaptive",
        importance=float(confidence),
        confidence=float(confidence),
        source="autosave",
    )


def remember_user_explicit(category: str, key: str, value: str):
    store.upsert_saved_memory(
        owner="user",
        category=category.strip(),
        key=key.strip(),
        value=value.strip(),
        stability="core",
        importance=1.0,
        confidence=0.9,
        source="manual",
    )


def remember_samuel_core(category: str, key: str, value: str):
    existing = get_latest_memory("samuel", category, key)
    if existing and existing.get("stability") == "core":
        return
    store.upsert_saved_memory(
        owner="samuel",
        category=category.strip(),
        key=key.strip(),
        value=value.strip(),
        stability="core",
        importance=1.0,
        confidence=0.85,
        source="manual",
    )


def remember_samuel_adaptive(category: str, key: str, value: str, allow_change: bool = False):
    if not allow_change:
        return
    store.upsert_saved_memory(
        owner="samuel",
        category=category.strip(),
        key=key.strip(),
        value=value.strip(),
        stability="adaptive",
        importance=0.9,
        confidence=0.7,
        source="manual",
    )


def get_latest_memory(owner: str, category: str, key: str) -> Optional[Dict]:
    val = store.get_memory_value(owner, category.strip(), key.strip())
    if val is None:
        return None

    hits = store.search_saved_memories(f"{category.strip()}.{key.strip()}", owner=None, limit=50)
    best = None
    for h in hits:
        if h.get("owner") == owner and (h.get("mkey") or "").endswith(f"{category.strip()}.{key.strip()}"):
            best = h
            break

    if best:
        return {
            "id": int(best.get("id")),
            "created_at": int(best.get("created_ts") or time.time()),
            "owner": best.get("owner"),
            "stability": best.get("stability"),
            "category": best.get("category"),
            "key": best.get("mkey"),
            "value": best.get("value"),
            "importance": float(best.get("importance") or 1.0),
        }

    return {
        "id": None,
        "created_at": int(time.time()),
        "owner": owner,
        "stability": "adaptive",
        "category": category.strip(),
        "key": key.strip(),
        "value": val,
        "importance": 1.0,
    }


def list_memories(owner: Optional[str] = None, limit: int = 200) -> List[Dict]:
    rows = store.list_saved_memories(owner=owner, limit=limit)
    out = []
    for r in rows:
        out.append({
            "owner": r["owner"],
            "stability": r["stability"],
            "category": r["category"],
            "key": r["mkey"],
            "value": r["value"],
            "created_at": int(r["updated_ts"]),
            "importance": float(r["importance"]),
        })
    return out[:limit]


def search_memories(query: str, owner: Optional[str] = None, limit: int = 12) -> List[Dict]:
    hits = store.search_saved_memories(query, owner=owner, limit=limit)
    out = []
    for h in hits:
        out.append({
            "owner": h["owner"],
            "stability": h["stability"],
            "category": h["category"],
            "key": h["mkey"],
            "value": h["value"],
            "created_at": int(h["updated_ts"]),
            "importance": float(h["importance"]),
        })
    return out[:limit]


def delete_memories(contains: str, owner: Optional[str] = None) -> int:
    # best-effort: store.forget_contains doesn't filter by owner, so do manual here
    store.init_db()
    like = f"%{(contains or '').strip()}%"
    import sqlite3

    conn = store._connect()
    try:
        with conn:
            if owner:
                rows = conn.execute(
                    "SELECT id FROM saved_memories WHERE owner=? AND value LIKE ?;",
                    (owner, like),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM saved_memories WHERE value LIKE ?;",
                    (like,),
                ).fetchall()

            ids = [int(r["id"]) for r in rows]
            if not ids:
                return 0
            conn.executemany("DELETE FROM saved_memories WHERE id=?;", [(i,) for i in ids])
            return len(ids)
    finally:
        conn.close()