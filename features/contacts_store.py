# contacts_store.py
# Samuel's contacts database — lives in samuel_contacts.db
# Completely isolated from samuel.db
# Auto-populated from conversation + manually editable via panel
import os
import sqlite3
import time
from typing import Optional, List, Dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTACTS_DB_PATH = (
    os.environ.get("SAMUEL_CONTACTS_DB")
    or os.path.join(BASE_DIR, "samuel_contacts.db")
)


def _connect():
    conn = sqlite3.connect(CONTACTS_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_contacts_db():
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS contacts ("
                "  id          INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  name        TEXT NOT NULL,"
                "  nickname    TEXT,"
                "  phone       TEXT,"
                "  email       TEXT,"
                "  relationship TEXT,"
                "  notes       TEXT,"
                "  source      TEXT DEFAULT 'manual',"
                "  created_ts  INTEGER NOT NULL,"
                "  updated_ts  INTEGER NOT NULL"
                ");"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ct_name ON contacts(name);"
            )
            # Tags table for flexible labeling (classmate, professor, family, etc.)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS contact_tags ("
                "  contact_id INTEGER NOT NULL,"
                "  tag        TEXT NOT NULL,"
                "  UNIQUE(contact_id, tag)"
                ");"
            )
            # Mentions log — every time Samuel hears about a contact in chat
            conn.execute(
                "CREATE TABLE IF NOT EXISTS contact_mentions ("
                "  id         INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  contact_id INTEGER NOT NULL,"
                "  context    TEXT,"
                "  ts         INTEGER NOT NULL"
                ");"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def add_contact(
    name: str,
    nickname: str = "",
    phone: str = "",
    email: str = "",
    relationship: str = "",
    notes: str = "",
    tags: List[str] = None,
    source: str = "manual",
) -> int:
    init_contacts_db()
    ts = int(time.time())
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO contacts"
                " (name,nickname,phone,email,relationship,notes,source,created_ts,updated_ts)"
                " VALUES(?,?,?,?,?,?,?,?,?);",
                (name.strip(), nickname or "", phone or "", email or "",
                 relationship or "", notes or "", source, ts, ts),
            )
            row = conn.execute("SELECT last_insert_rowid() AS id;").fetchone()
            cid = int(row["id"])
            for tag in (tags or []):
                tag = tag.strip().lower()
                if tag:
                    conn.execute(
                        "INSERT OR IGNORE INTO contact_tags(contact_id,tag) VALUES(?,?);",
                        (cid, tag),
                    )
            return cid
    finally:
        conn.close()


def update_contact(
    contact_id: int,
    name: str = None,
    nickname: str = None,
    phone: str = None,
    email: str = None,
    relationship: str = None,
    notes: str = None,
) -> None:
    init_contacts_db()
    ts = int(time.time())
    conn = _connect()
    try:
        with conn:
            fields, vals = [], []
            for col, val in [
                ("name", name), ("nickname", nickname), ("phone", phone),
                ("email", email), ("relationship", relationship), ("notes", notes),
            ]:
                if val is not None:
                    fields.append(col + "=?")
                    vals.append(val)
            if not fields:
                return
            fields.append("updated_ts=?")
            vals.append(ts)
            vals.append(int(contact_id))
            conn.execute(
                "UPDATE contacts SET " + ", ".join(fields) + " WHERE id=?;", vals
            )
    finally:
        conn.close()


def delete_contact(contact_id: int) -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute("DELETE FROM contacts WHERE id=?;", (int(contact_id),))
            conn.execute("DELETE FROM contact_tags WHERE contact_id=?;", (int(contact_id),))
            conn.execute("DELETE FROM contact_mentions WHERE contact_id=?;", (int(contact_id),))
    finally:
        conn.close()


def get_contact(contact_id: int) -> Optional[Dict]:
    init_contacts_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM contacts WHERE id=?;", (int(contact_id),)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = _get_tags(conn, contact_id)
        return d
    finally:
        conn.close()


def list_contacts(search: str = "", limit: int = 500) -> List[Dict]:
    init_contacts_db()
    conn = _connect()
    try:
        if search:
            like = "%" + search.strip() + "%"
            rows = conn.execute(
                "SELECT * FROM contacts WHERE name LIKE ? OR nickname LIKE ?"
                " OR relationship LIKE ? OR notes LIKE ?"
                " ORDER BY name ASC LIMIT ?;",
                (like, like, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY name ASC LIMIT ?;", (limit,)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = _get_tags(conn, int(r["id"]))
            result.append(d)
        return result
    finally:
        conn.close()


def find_contact_by_name(name: str) -> Optional[Dict]:
    init_contacts_db()
    conn = _connect()
    try:
        like = "%" + name.strip() + "%"
        row = conn.execute(
            "SELECT * FROM contacts WHERE name LIKE ? OR nickname LIKE ?"
            " ORDER BY updated_ts DESC LIMIT 1;",
            (like, like),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = _get_tags(conn, int(row["id"]))
        return d
    finally:
        conn.close()


def _get_tags(conn, contact_id: int) -> List[str]:
    rows = conn.execute(
        "SELECT tag FROM contact_tags WHERE contact_id=?;", (int(contact_id),)
    ).fetchall()
    return [r["tag"] for r in rows]


def add_tag(contact_id: int, tag: str) -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO contact_tags(contact_id,tag) VALUES(?,?);",
                (int(contact_id), tag.strip().lower()),
            )
    finally:
        conn.close()


def remove_tag(contact_id: int, tag: str) -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "DELETE FROM contact_tags WHERE contact_id=? AND tag=?;",
                (int(contact_id), tag.strip().lower()),
            )
    finally:
        conn.close()


def log_mention(contact_id: int, context: str = "") -> None:
    init_contacts_db()
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO contact_mentions(contact_id,context,ts) VALUES(?,?,?);",
                (int(contact_id), (context or "")[:300], int(time.time())),
            )
    finally:
        conn.close()


def get_contact_stats() -> Dict:
    init_contacts_db()
    conn = _connect()
    try:
        total = int(conn.execute("SELECT COUNT(*) AS c FROM contacts;").fetchone()["c"])
        auto  = int(conn.execute(
            "SELECT COUNT(*) AS c FROM contacts WHERE source='auto';"
        ).fetchone()["c"])
        return {"total": total, "auto_detected": auto, "manual": total - auto}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CONTEXT BUILDER  (injected into Samuel's system prompt)
# ---------------------------------------------------------------------------

def build_contacts_context(user_text: str, max_contacts: int = 8) -> str:
    """
    Search contacts relevant to what the user is saying and inject into prompt.
    e.g. if user says 'Eric messaged me', Samuel already knows who Eric is.
    """
    init_contacts_db()
    words = [w for w in user_text.lower().split() if len(w) > 2]
    if not words:
        return ""

    conn = _connect()
    hits = []
    seen = set()
    try:
        for w in words:
            like = "%" + w + "%"
            rows = conn.execute(
                "SELECT * FROM contacts WHERE name LIKE ? OR nickname LIKE ?"
                " ORDER BY updated_ts DESC LIMIT 3;",
                (like, like),
            ).fetchall()
            for r in rows:
                cid = int(r["id"])
                if cid not in seen:
                    seen.add(cid)
                    d = dict(r)
                    d["tags"] = _get_tags(conn, cid)
                    hits.append(d)
    finally:
        conn.close()

    if not hits:
        return ""

    lines = ["KNOWN CONTACTS:"]
    for c in hits[:max_contacts]:
        parts = [c["name"]]
        if c.get("nickname"):
            parts.append("aka " + c["nickname"])
        if c.get("relationship"):
            parts.append(c["relationship"])
        if c.get("tags"):
            parts.append("tags: " + ", ".join(c["tags"]))
        if c.get("phone"):
            parts.append("📞 " + c["phone"])
        if c.get("email"):
            parts.append("✉ " + c["email"])
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)
