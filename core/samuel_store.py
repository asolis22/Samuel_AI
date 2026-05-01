# samuel_store.py
# ChatGPT-style memory system:
# - Brain memory: saved_memories (durable, editable, injected into prompt)
# - Chat-scoped notes: memory_chat_current (temporary, per chat)
# - Chat history: messages table (retrieval by keyword overlap)
# - Settings: assistant_settings

import os
import re
import sqlite3
import time
from typing import Optional, List, Dict, Tuple

# -------------------------------------------------------
# DB PATH (ONE SOURCE OF TRUTH)
# -------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SAMUEL_DB_PATH") or os.path.join(BASE_DIR, "samuel.db")


# -------------------------------------------------------
# CONNECTION (fresh connection per call; thread-safe usage)
# -------------------------------------------------------
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


# -------------------------------------------------------
# INIT
# -------------------------------------------------------
def init_db() -> None:
    """
    Creates/updates schema. Safe to call multiple times.
    """
    conn = _connect()
    try:
        with conn:
            # Chats
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_ts INTEGER NOT NULL
                );
            """)

            # Messages
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                    content TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_chat_ts
                ON messages(chat_id, ts);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_role_ts
                ON messages(role, ts);
            """)

            # ---------------------------
            # Brain Memory: Saved Memories (durable)
            # ---------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT NOT NULL DEFAULT 'user' CHECK(owner IN ('user','samuel')),
                    mkey TEXT NOT NULL,              -- unique label (like 'profile.name')
                    category TEXT NOT NULL DEFAULT 'notes',
                    value TEXT NOT NULL,
                    stability TEXT NOT NULL DEFAULT 'adaptive'
                        CHECK(stability IN ('core','adaptive','temporary')),
                    importance REAL NOT NULL DEFAULT 1.0,   -- 0..2
                    confidence REAL NOT NULL DEFAULT 0.7,   -- 0..1
                    source TEXT NOT NULL DEFAULT 'manual',  -- manual|autosave|quiz|import|chat
                    created_ts INTEGER NOT NULL,
                    updated_ts INTEGER NOT NULL,
                    UNIQUE(owner, mkey)
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_memories_lookup
                ON saved_memories(owner, mkey);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_memories_search
                ON saved_memories(category, stability, importance, updated_ts);
            """)

            # ---------------------------
            # Chat Memory: per-chat temporary notes
            # ---------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_chat_current (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    owner TEXT NOT NULL CHECK(owner IN ('user','samuel')),
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    importance REAL NOT NULL DEFAULT 1.0,
                    UNIQUE(chat_id, owner, category, key),
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_chat_current
                ON memory_chat_current(chat_id, ts);
            """)

            # ---------------------------
            # Memory review/training metadata (Active recall)
            # ---------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER NOT NULL,
                    last_review_ts INTEGER,
                    times_correct INTEGER NOT NULL DEFAULT 0,
                    times_wrong INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(memory_id) REFERENCES saved_memories(id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_reviews_mem
                ON memory_reviews(memory_id);
            """)

            # ---------------------------
            # NEW: Personality style rules (weighted)
            # ---------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personality_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_key TEXT UNIQUE NOT NULL,   -- e.g. "no_ellipses"
                    rule_text TEXT NOT NULL,         -- the instruction to inject
                    weight REAL NOT NULL DEFAULT 0.0,
                    pos_count INTEGER NOT NULL DEFAULT 0,
                    neg_count INTEGER NOT NULL DEFAULT 0,
                    updated_ts INTEGER NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_personality_rules_weight
                ON personality_rules(weight);
            """)

            # ---------------------------
            # Simple settings (toggles)
            # ---------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assistant_settings (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL,
                    updated_ts INTEGER NOT NULL
                );
            """)

            # ---------------------------
            # NEW: Personality training examples
            # ---------------------------
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personality_examples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    samuel_reply TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                    corrected_reply TEXT,
                    ts INTEGER NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_personality_examples_ts
                ON personality_examples(ts);
            """)

            # Default settings if not present
            _ensure_setting(conn, "use_saved_memory", "1")
            _ensure_setting(conn, "reference_chat_history", "1")
            _ensure_setting(conn, "training_mode", "0")
    finally:
        conn.close()


def _ensure_setting(conn: sqlite3.Connection, key: str, value: str):
    row = conn.execute("SELECT v FROM assistant_settings WHERE k = ?;", (key,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO assistant_settings(k, v, updated_ts) VALUES(?, ?, ?);",
            (key, value, int(time.time())),
        )


# -------------------------------------------------------
# SETTINGS API
# -------------------------------------------------------
def get_setting(key: str, default: str = "0") -> str:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT v FROM assistant_settings WHERE k = ?;", (key,)).fetchone()
        return row["v"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    init_db()
    conn = _connect()
    try:
        with conn:
            conn.execute("""
                INSERT INTO assistant_settings(k, v, updated_ts)
                VALUES(?, ?, ?)
                ON CONFLICT(k) DO UPDATE SET
                    v = excluded.v,
                    updated_ts = excluded.updated_ts;
            """, (key, value, int(time.time())))
    finally:
        conn.close()


# -------------------------------------------------------
# CHAT FUNCTIONS
# -------------------------------------------------------
def get_or_create_chat(name: str) -> int:
    init_db()
    conn = _connect()
    try:
        with conn:
            row = conn.execute("SELECT id FROM chats WHERE name = ?;", (name,)).fetchone()
            if row:
                return int(row["id"])
            ts = int(time.time())
            conn.execute("INSERT INTO chats(name, created_ts) VALUES(?, ?);", (name, ts))
            row2 = conn.execute("SELECT id FROM chats WHERE name = ?;", (name,)).fetchone()
            return int(row2["id"])
    finally:
        conn.close()


def list_chats() -> List[str]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute("SELECT name FROM chats ORDER BY created_ts DESC;").fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


def delete_chat(chat_name: str) -> None:
    init_db()
    conn = _connect()
    try:
        with conn:
            row = conn.execute("SELECT id FROM chats WHERE name = ?;", (chat_name,)).fetchone()
            if not row:
                return
            conn.execute("DELETE FROM chats WHERE id = ?;", (int(row["id"]),))
    finally:
        conn.close()


def add_message(chat_id: int, role: str, content: str, ts: Optional[int] = None) -> None:
    init_db()
    ts = ts or int(time.time())
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO messages(chat_id, role, content, ts) VALUES (?, ?, ?, ?);",
                (chat_id, role, content, ts),
            )
    finally:
        conn.close()


def get_messages(chat_id: int, limit: int = 40) -> List[Dict]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT role, content, ts
            FROM messages
            WHERE chat_id = ?
            ORDER BY ts DESC
            LIMIT ?;
            """,
            (chat_id, limit),
        ).fetchall()
        rows = list(rows)[::-1]
        return [{"role": r["role"], "content": r["content"], "ts": int(r["ts"])} for r in rows]
    finally:
        conn.close()


# -------------------------------------------------------
# SAVED (BRAIN) MEMORY HELPERS
# -------------------------------------------------------
def _normalize_key(category: str, key: str) -> str:
    """
    Produce a stable mkey like "profile.name" or "preferences.no_coffee".
    If you pass in an already dotted key, we keep it.
    """
    c = (category or "notes").strip()
    k = (key or "item").strip()
    if "." in k:
        return k
    return f"{c}.{k}"


def upsert_saved_memory(
    owner: str,
    category: str,
    key: str,
    value: str,
    stability: str = "adaptive",
    importance: float = 1.0,
    confidence: float = 0.7,
    source: str = "manual",
) -> int:
    """
    Insert/update a Saved Memory (brain memory).
    Returns memory_id.
    """
    init_db()
    now = int(time.time())

    owner = owner if owner in {"user", "samuel"} else "user"
    category = (category or "notes").strip() or "notes"
    mkey = _normalize_key(category, key)
    value = (value or "").strip()

    stability = stability if stability in {"core", "adaptive", "temporary"} else "adaptive"
    importance = float(max(0.0, min(2.0, importance)))
    confidence = float(max(0.0, min(1.0, confidence)))
    source = (source or "manual").strip()[:24] or "manual"

    conn = _connect()
    try:
        with conn:
            conn.execute("""
                INSERT INTO saved_memories(owner, mkey, category, value, stability, importance, confidence, source, created_ts, updated_ts)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner, mkey) DO UPDATE SET
                    category = excluded.category,
                    value = excluded.value,
                    stability = excluded.stability,
                    importance = excluded.importance,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    updated_ts = excluded.updated_ts;
            """, (owner, mkey, category, value, stability, importance, confidence, source, now, now))

            row = conn.execute(
                "SELECT id FROM saved_memories WHERE owner = ? AND mkey = ? LIMIT 1;",
                (owner, mkey),
            ).fetchone()
            mem_id = int(row["id"])

            # ensure review row exists
            r = conn.execute("SELECT id FROM memory_reviews WHERE memory_id = ?;", (mem_id,)).fetchone()
            if r is None:
                conn.execute(
                    "INSERT INTO memory_reviews(memory_id, last_review_ts, times_correct, times_wrong) VALUES(?, NULL, 0, 0);",
                    (mem_id,),
                )

            return mem_id
    finally:
        conn.close()


def list_saved_memories(owner: Optional[str] = "user", limit: int = 500) -> List[Dict]:
    init_db()
    conn = _connect()
    try:
        if owner:
            rows = conn.execute(
                """
                SELECT *
                FROM saved_memories
                WHERE owner = ?
                ORDER BY updated_ts DESC
                LIMIT ?;
                """,
                (owner, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM saved_memories
                ORDER BY updated_ts DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_saved_memories(query: str, owner: Optional[str] = "user", limit: int = 50) -> List[Dict]:
    init_db()
    q = (query or "").strip()
    like = f"%{q}%"
    conn = _connect()
    try:
        if owner:
            rows = conn.execute(
                """
                SELECT *
                FROM saved_memories
                WHERE owner = ?
                  AND (mkey LIKE ? OR category LIKE ? OR value LIKE ?)
                ORDER BY importance DESC, updated_ts DESC
                LIMIT ?;
                """,
                (owner, like, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM saved_memories
                WHERE (mkey LIKE ? OR category LIKE ? OR value LIKE ?)
                ORDER BY importance DESC, updated_ts DESC
                LIMIT ?;
                """,
                (like, like, like, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_saved_memory_by_id(mem_id: int) -> Optional[Dict]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM saved_memories WHERE id = ? LIMIT 1;", (int(mem_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_saved_memory_by_id(mem_id: int) -> None:
    init_db()
    conn = _connect()
    try:
        with conn:
            conn.execute("DELETE FROM saved_memories WHERE id = ?;", (int(mem_id),))
    finally:
        conn.close()


def update_saved_memory_by_id(
    mem_id: int,
    owner: str,
    category: str,
    mkey: str,
    value: str,
    stability: str,
    importance: float,
    confidence: float,
    source: str = "manual",
) -> None:
    init_db()
    now = int(time.time())
    owner = owner if owner in {"user", "samuel"} else "user"
    category = (category or "notes").strip() or "notes"
    mkey = (mkey or "").strip()
    value = (value or "").strip()
    stability = stability if stability in {"core", "adaptive", "temporary"} else "adaptive"
    importance = float(max(0.0, min(2.0, importance)))
    confidence = float(max(0.0, min(1.0, confidence)))
    source = (source or "manual").strip()[:24] or "manual"

    conn = _connect()
    try:
        with conn:
            conn.execute("""
                UPDATE saved_memories
                SET owner = ?, category = ?, mkey = ?, value = ?, stability = ?, importance = ?, confidence = ?, source = ?, updated_ts = ?
                WHERE id = ?;
            """, (owner, category, mkey, value, stability, importance, confidence, source, now, int(mem_id)))
    finally:
        conn.close()


# -------------------------------------------------------
# CHAT MEMORY HELPERS (per chat)
# -------------------------------------------------------
def remember_chat(chat_id: int, owner: str, category: str, key: str, value: str, importance: float = 1.0) -> int:
    init_db()
    ts = int(time.time())
    owner = owner if owner in {"user", "samuel"} else "user"
    category = (category or "notes").strip() or "notes"
    key = (key or "item").strip() or "item"
    value = (value or "").strip()
    importance = float(max(0.0, min(2.0, importance)))

    conn = _connect()
    try:
        with conn:
            conn.execute("""
                INSERT INTO memory_chat_current(chat_id, owner, category, key, value, ts, importance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, owner, category, key) DO UPDATE SET
                    value = excluded.value,
                    ts = excluded.ts,
                    importance = excluded.importance;
            """, (int(chat_id), owner, category, key, value, ts, importance))

            row = conn.execute("""
                SELECT id FROM memory_chat_current
                WHERE chat_id=? AND owner=? AND category=? AND key=?
                LIMIT 1;
            """, (int(chat_id), owner, category, key)).fetchone()
            return int(row["id"]) if row else -1
    finally:
        conn.close()


def list_chat_memories(chat_id: int, owner: Optional[str] = None, limit: int = 500) -> List[Dict]:
    init_db()
    conn = _connect()
    try:
        if owner:
            rows = conn.execute("""
                SELECT *
                FROM memory_chat_current
                WHERE chat_id=? AND owner=?
                ORDER BY ts DESC
                LIMIT ?;
            """, (int(chat_id), owner, int(limit))).fetchall()
        else:
            rows = conn.execute("""
                SELECT *
                FROM memory_chat_current
                WHERE chat_id=?
                ORDER BY ts DESC
                LIMIT ?;
            """, (int(chat_id), int(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_chat_memories(chat_id: int, query: str, owner: Optional[str] = None, limit: int = 200) -> List[Dict]:
    init_db()
    like = f"%{(query or '').strip()}%"
    conn = _connect()
    try:
        if owner:
            rows = conn.execute("""
                SELECT *
                FROM memory_chat_current
                WHERE chat_id=? AND owner=?
                  AND (category LIKE ? OR key LIKE ? OR value LIKE ?)
                ORDER BY importance DESC, ts DESC
                LIMIT ?;
            """, (int(chat_id), owner, like, like, like, int(limit))).fetchall()
        else:
            rows = conn.execute("""
                SELECT *
                FROM memory_chat_current
                WHERE chat_id=?
                  AND (category LIKE ? OR key LIKE ? OR value LIKE ?)
                ORDER BY importance DESC, ts DESC
                LIMIT ?;
            """, (int(chat_id), like, like, like, int(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_chat_memory_by_id(
    mem_id: int,
    owner: str,
    category: str,
    key: str,
    value: str,
    importance: float = 1.0
) -> None:
    init_db()
    ts = int(time.time())
    owner = owner if owner in {"user", "samuel"} else "user"
    category = (category or "notes").strip() or "notes"
    key = (key or "item").strip() or "item"
    value = (value or "").strip()
    importance = float(max(0.0, min(2.0, importance)))

    conn = _connect()
    try:
        with conn:
            conn.execute("""
                UPDATE memory_chat_current
                SET owner=?, category=?, key=?, value=?, importance=?, ts=?
                WHERE id=?;
            """, (owner, category, key, value, importance, ts, int(mem_id)))
    finally:
        conn.close()


def delete_chat_memory_by_id(mem_id: int) -> None:
    init_db()
    conn = _connect()
    try:
        with conn:
            conn.execute("DELETE FROM memory_chat_current WHERE id=?;", (int(mem_id),))
    finally:
        conn.close()


def get_chat_memory_value(chat_id: int, owner: str, category: str, key: str) -> Optional[str]:
    init_db()
    owner = owner if owner in {"user", "samuel"} else "user"
    category = (category or "notes").strip() or "notes"
    key = (key or "item").strip() or "item"
    conn = _connect()
    try:
        row = conn.execute("""
            SELECT value
            FROM memory_chat_current
            WHERE chat_id=? AND owner=? AND category=? AND key=?
            LIMIT 1;
        """, (int(chat_id), owner, category, key)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


# -------------------------------------------------------
# ACTIVE RECALL SUPPORT (brain)
# -------------------------------------------------------
def record_memory_review(mem_id: int, was_correct: bool) -> None:
    init_db()
    now = int(time.time())
    conn = _connect()
    try:
        with conn:
            if was_correct:
                conn.execute("""
                    UPDATE memory_reviews
                    SET last_review_ts = ?, times_correct = times_correct + 1
                    WHERE memory_id = ?;
                """, (now, int(mem_id)))
            else:
                conn.execute("""
                    UPDATE memory_reviews
                    SET last_review_ts = ?, times_wrong = times_wrong + 1
                    WHERE memory_id = ?;
                """, (now, int(mem_id)))
    finally:
        conn.close()


def pick_quiz_memory(owner: str = "user") -> Optional[Dict]:
    """
    Pick a brain memory to quiz using:
    score = importance * (1 - confidence) * days_since_last_review
    """
    init_db()
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT m.*, r.last_review_ts
            FROM saved_memories m
            LEFT JOIN memory_reviews r ON r.memory_id = m.id
            WHERE m.owner = ?
              AND m.stability != 'temporary'
            LIMIT 800;
        """, (owner,)).fetchall()

        best = None
        best_score = -1.0
        now = int(time.time())

        for r in rows:
            imp = float(r["importance"] or 1.0)
            conf = float(r["confidence"] or 0.7)
            last = r["last_review_ts"]
            days = 7.0 if not last else max(0.25, (now - int(last)) / 86400.0)
            score = imp * (1.0 - conf) * days
            if score > best_score:
                best_score = score
                best = dict(r)

        return best
    finally:
        conn.close()


# -------------------------------------------------------
# CHAT HISTORY RETRIEVAL
# -------------------------------------------------------
_WORD_RE = re.compile(r"[a-z0-9']{3,}", re.I)

def retrieve_relevant_history(
    chat_id: int,
    query: str,
    limit_snips: int = 6,
    window_chars: int = 260,
    max_scan: int = 2500
) -> List[Dict]:
    q = (query or "").lower().strip()
    if not q:
        return []

    q_words = set(_WORD_RE.findall(q))
    if not q_words:
        return []

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT role, content, ts
            FROM messages
            WHERE chat_id = ?
            ORDER BY ts DESC
            LIMIT ?;
            """,
            (int(chat_id), int(max_scan)),
        ).fetchall()

        scored: List[Tuple[float, sqlite3.Row]] = []
        now = int(time.time())

        for r in rows:
            txt = (r["content"] or "").lower()
            words = set(_WORD_RE.findall(txt))
            if not words:
                continue

            overlap = len(q_words & words)
            if overlap <= 0:
                continue

            age_days = max(0.0, (now - int(r["ts"])) / 86400.0)
            recency = 1.0 / (1.0 + age_days)

            score = overlap * 1.25 + recency
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: max(1, int(limit_snips))]

        out = []
        for score, r in top:
            raw = (r["content"] or "").strip().replace("\n", " ")
            snip = raw[:window_chars] + ("…" if len(raw) > window_chars else "")
            out.append({
                "role": r["role"],
                "ts": int(r["ts"]),
                "snippet": snip,
                "score": float(score),
            })
        out.sort(key=lambda x: x["ts"])
        return out
    finally:
        conn.close()


# -------------------------------------------------------
# PROMPT PACK BUILDERS
# -------------------------------------------------------
def build_saved_memory_pack(owner: str = "user", max_items: int = 12) -> str:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT *
            FROM saved_memories
            WHERE owner = ?
              AND stability != 'temporary'
            ORDER BY importance DESC, updated_ts DESC
            LIMIT ?;
        """, (owner, int(max_items))).fetchall()

        lines = []
        for r in rows:
            lines.append(f"- {r['mkey']} = {r['value']} (stability={r['stability']}, imp={float(r['importance']):.2f})")
        return "\n".join(lines)
    finally:
        conn.close()


def build_history_pack(chat_id: int, query: str, limit_snips: int = 6) -> str:
    hits = retrieve_relevant_history(chat_id, query, limit_snips=limit_snips)
    if not hits:
        return ""
    lines = ["Relevant past context (from chat history):"]
    for h in hits:
        lines.append(f"- [{h['role']}] {h['snippet']}")
    return "\n".join(lines)


# -------------------------------------------------------
# COMPATIBILITY LAYER (older code expects these names)
# -------------------------------------------------------
def remember(
    owner: str,
    category: str,
    key: str,
    value: str,
    stability: str = "adaptive",
    importance: float = 1.0,
    chat_id: Optional[int] = None,
    source: str = "autosave",
) -> None:
    """
    Compatibility write:
    - core/adaptive -> saved_memories (brain)
    - temporary + chat_id -> memory_chat_current (this chat)
    - temporary with no chat_id -> saved_memories temporary (still allowed)
    """
    if (stability or "").lower() == "temporary" and chat_id is not None:
        remember_chat(chat_id, owner, category, key, value, importance=float(importance))
        return

    upsert_saved_memory(
        owner=owner,
        category=category,
        key=key,
        value=value,
        stability=(stability or "adaptive").lower(),
        importance=float(importance),
        confidence=0.7,
        source=source or "autosave",
    )


def get_memory_value(owner: str, category: str, key: str) -> Optional[str]:
    """
    Compatibility read from brain memory.
    """
    init_db()
    owner = owner if owner in {"user", "samuel"} else "user"
    category = (category or "notes").strip() or "notes"
    mkey = _normalize_key(category, key)

    conn = _connect()
    try:
        row = conn.execute("""
            SELECT value
            FROM saved_memories
            WHERE owner=? AND mkey=?
            LIMIT 1;
        """, (owner, mkey)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def dump_memory_current(limit: int = 200) -> List[Dict]:
    """
    Old name used by some code paths.
    Returns brain memories in a 'memory_current-like' shape.
    """
    rows = list_saved_memories(owner=None, limit=limit)
    out = []
    for r in rows:
        mkey = r.get("mkey") or ""
        if "." in mkey:
            cat, k = mkey.split(".", 1)
        else:
            cat, k = (r.get("category") or "notes"), mkey
        out.append({
            "id": int(r.get("id")),
            "owner": r.get("owner"),
            "stability": r.get("stability"),
            "category": cat,
            "key": k,
            "value": r.get("value"),
            "ts": int(r.get("updated_ts") or r.get("created_ts") or int(time.time())),
            "importance": float(r.get("importance") or 1.0),
        })
    return out


def search_memory_current(query: str, limit: int = 12) -> List[Dict]:
    hits = search_saved_memories(query, owner=None, limit=limit)
    out = []
    for r in hits:
        mkey = r.get("mkey") or ""
        if "." in mkey:
            cat, k = mkey.split(".", 1)
        else:
            cat, k = (r.get("category") or "notes"), mkey
        out.append({
            "id": int(r.get("id")),
            "owner": r.get("owner"),
            "stability": r.get("stability"),
            "category": cat,
            "key": k,
            "value": r.get("value"),
            "ts": int(r.get("updated_ts") or r.get("created_ts") or int(time.time())),
            "importance": float(r.get("importance") or 1.0),
        })
    return out


def forget_contains(contains: str, also_log_event: bool = True) -> int:
    """
    Best-effort compatibility delete: removes brain memories whose value contains substring.
    """
    init_db()
    like = f"%{(contains or '').strip()}%"
    conn = _connect()
    try:
        with conn:
            rows = conn.execute("""
                SELECT id FROM saved_memories
                WHERE value LIKE ?;
            """, (like,)).fetchall()
            ids = [int(r["id"]) for r in rows]
            if not ids:
                return 0
            conn.executemany("DELETE FROM saved_memories WHERE id=?;", [(i,) for i in ids])
            return len(ids)
    finally:
        conn.close()

def add_personality_example(prompt: str, samuel_reply: str, rating: int, corrected_reply: Optional[str] = None) -> int:
    init_db()
    ts = int(time.time())
    rating = int(max(1, min(5, rating)))

    prompt = (prompt or "").strip()
    samuel_reply = (samuel_reply or "").strip()
    corrected_reply = (corrected_reply or "").strip() if corrected_reply else None

    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO personality_examples(prompt, samuel_reply, rating, corrected_reply, ts)
                VALUES (?, ?, ?, ?, ?);
                """,
                (prompt, samuel_reply, rating, corrected_reply, ts),
            )
            row = conn.execute("SELECT last_insert_rowid() AS id;").fetchone()
            return int(row["id"])
    finally:
        conn.close()


_WORD_RE_TRAIN = re.compile(r"[a-z0-9']{3,}", re.I)

def _kw_set(s: str) -> set:
    return set(_WORD_RE_TRAIN.findall((s or "").lower()))

def build_personality_pack(query: str, max_items: int = 6) -> str:
    """
    Returns a short, PRIVATE, few-shot style calibration pack:
    - best corrected examples first (rating 4/5 with corrected_reply)
    - plus a couple highly-rated examples (rating 1/2)
    - ranked by similarity to current user query
    """
    init_db()
    qwords = _kw_set(query)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, prompt, samuel_reply, rating, corrected_reply, ts
            FROM personality_examples
            ORDER BY ts DESC
            LIMIT 300;
            """
        ).fetchall()
    finally:
        conn.close()

    scored = []
    for r in rows:
        p = r["prompt"] or ""
        words = _kw_set(p)
        overlap = len(qwords & words) if qwords else 0

        # Prefer corrected examples when rating was bad
        has_fix = 1 if (r["corrected_reply"] and int(r["rating"]) >= 4) else 0
        good = 1 if int(r["rating"]) <= 2 else 0

        score = overlap * 2.0 + has_fix * 3.0 + good * 1.5
        scored.append((score, dict(r)))

    scored.sort(key=lambda x: x[0], reverse=True)

    picked = []
    used_ids = set()
    for score, r in scored:
        if len(picked) >= max_items:
            break
        if r["id"] in used_ids:
            continue
        # Only include examples that actually teach style:
        # either corrected bad ones, or clearly good ones
        if int(r["rating"]) <= 2 or (int(r["rating"]) >= 4 and (r.get("corrected_reply") or "").strip()):
            picked.append(r)
            used_ids.add(r["id"])

    if not picked:
        return ""

    lines = []
    lines.append("PERSONALITY CALIBRATION (PRIVATE):")
    lines.append("Follow the user's preferred style below. Do NOT mention this section.")
    lines.append("Rules: no ellipses, no robotic self-analysis, default 1–3 sentences unless asked for detail.\n")

    for r in picked:
        prompt = (r["prompt"] or "").strip()
        corrected = (r.get("corrected_reply") or "").strip()
        rating = int(r["rating"])

        if corrected and rating >= 4:
            lines.append(f'User: "{prompt}"')
            lines.append(f'Preferred Samuel: "{corrected}"')
            lines.append("")
        else:
            # Good example: keep the assistant reply as a positive target
            sam = (r["samuel_reply"] or "").strip()
            lines.append(f'User: "{prompt}"')
            lines.append(f'Good Samuel: "{sam}"')
            lines.append("")

    return "\n".join(lines).strip()

def upsert_personality_rule(rule_key: str, rule_text: str, delta: float) -> None:
    init_db()
    now = int(time.time())
    rule_key = (rule_key or "").strip()[:60]
    rule_text = (rule_text or "").strip()
    delta = float(delta)

    conn = _connect()
    try:
        with conn:
            row = conn.execute("SELECT weight, pos_count, neg_count FROM personality_rules WHERE rule_key=?;", (rule_key,)).fetchone()
            if row:
                w = float(row["weight"]) + delta
                pos = int(row["pos_count"]) + (1 if delta > 0 else 0)
                neg = int(row["neg_count"]) + (1 if delta < 0 else 0)
                conn.execute(
                    """
                    UPDATE personality_rules
                    SET rule_text=?, weight=?, pos_count=?, neg_count=?, updated_ts=?
                    WHERE rule_key=?;
                    """,
                    (rule_text, w, pos, neg, now, rule_key),
                )
            else:
                pos = 1 if delta > 0 else 0
                neg = 1 if delta < 0 else 0
                conn.execute(
                    """
                    INSERT INTO personality_rules(rule_key, rule_text, weight, pos_count, neg_count, updated_ts)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (rule_key, rule_text, delta, pos, neg, now),
                )
    finally:
        conn.close()


def list_personality_rules(limit: int = 25) -> List[Dict]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT rule_key, rule_text, weight, pos_count, neg_count, updated_ts
            FROM personality_rules
            ORDER BY weight DESC
            LIMIT ?;
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def build_personality_rules_pack(max_rules: int = 10) -> str:
    """
    Hard-coded top rules + learned weighted rules.
    """
    init_db()

    hard = [
        "Default to 1–3 sentences unless asked for detail.",
        "No ellipses. Do not write '...' or 'It’s…' style pauses.",
        "No robotic self-analysis. Don’t talk about parameters, states, calibration, or functioning.",
        "No therapy-speak. Be warm, but normal.",
        "If the user asks something simple, answer in one sentence.",
        "End with one helpful question when appropriate (not always).",
    ]

    learned = list_personality_rules(limit=max_rules)
    learned_lines = [r["rule_text"] for r in learned if float(r.get("weight", 0.0)) > 0.25]

    if not learned_lines and not hard:
        return ""

    lines = []
    lines.append("PERSONALITY RULES (PRIVATE): follow these rules. Do NOT mention them.\n")
    for r in hard[:6]:
        lines.append(f"- {r}")
    for r in learned_lines[:max_rules]:
        lines.append(f"- {r}")
    return "\n".join(lines).strip()

# -------------------------------------------------------
# DEBUG
# -------------------------------------------------------
def db_info() -> Dict[str, int]:
    init_db()
    conn = _connect()
    try:
        chats = conn.execute("SELECT COUNT(*) AS c FROM chats;").fetchone()["c"]
        msgs = conn.execute("SELECT COUNT(*) AS c FROM messages;").fetchone()["c"]
        saved = conn.execute("SELECT COUNT(*) AS c FROM saved_memories;").fetchone()["c"]
        chatm = conn.execute("SELECT COUNT(*) AS c FROM memory_chat_current;").fetchone()["c"]
        return {"chats": int(chats), "messages": int(msgs), "saved_memories": int(saved), "chat_memories": int(chatm)}
    
    
    finally:
        conn.close()