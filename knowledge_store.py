# knowledge_store.py  —  Samuel's autonomous learning DB (isolated from samuel.db)
import os, sqlite3, time
from typing import Optional, List, Dict

KNOWLEDGE_DB_PATH = os.environ.get("SAMUEL_KNOWLEDGE_DB") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "samuel_knowledge.db")

def _connect():
    conn = sqlite3.connect(KNOWLEDGE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def init_knowledge_db():
    conn = _connect()
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS fetched_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, title TEXT, raw_text TEXT, fetched_ts INTEGER NOT NULL, query_used TEXT, status TEXT DEFAULT 'pending' CHECK(status IN ('pending','processed','failed','skipped')));")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_fp_url ON fetched_pages(url);")
            conn.execute("CREATE TABLE IF NOT EXISTS knowledge_nuggets (id INTEGER PRIMARY KEY AUTOINCREMENT, source_url TEXT NOT NULL, source_title TEXT, topic TEXT NOT NULL, summary TEXT NOT NULL, relevance_score REAL NOT NULL DEFAULT 1.0, approved INTEGER NOT NULL DEFAULT 0, created_ts INTEGER NOT NULL, query_origin TEXT);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kn_topic ON knowledge_nuggets(topic,approved);")
            conn.execute("CREATE TABLE IF NOT EXISTS autonomous_queries (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, ran_ts INTEGER NOT NULL, result_count INTEGER DEFAULT 0, triggered_by TEXT);")
            conn.execute("CREATE TABLE IF NOT EXISTS learning_digests (id INTEGER PRIMARY KEY AUTOINCREMENT, date_label TEXT NOT NULL, summary TEXT NOT NULL, nugget_ids TEXT, created_ts INTEGER NOT NULL);")
    finally: conn.close()

    

def save_fetched_page(url, title, raw_text, query_used=""):
    init_knowledge_db(); ts = int(time.time()); conn = _connect()
    try:
        with conn:
            conn.execute("INSERT INTO fetched_pages(url,title,raw_text,fetched_ts,query_used,status) VALUES(?,?,?,?,?,'pending') ON CONFLICT(url) DO UPDATE SET raw_text=excluded.raw_text,fetched_ts=excluded.fetched_ts,query_used=excluded.query_used,status='pending';", (url, title or "", (raw_text or "")[:40000], ts, query_used or ""))
            row = conn.execute("SELECT id FROM fetched_pages WHERE url=?;", (url,)).fetchone()
            return int(row["id"]) if row else -1
    finally: conn.close()

def mark_page_processed(page_id, status="processed"):
    conn = _connect()
    try:
        with conn: conn.execute("UPDATE fetched_pages SET status=? WHERE id=?;", (status, int(page_id)))
    finally: conn.close()

def save_nugget(source_url, source_title, topic, summary, relevance=1.0, query_origin=""):
    init_knowledge_db(); ts = int(time.time()); conn = _connect()
    try:
        with conn:
            conn.execute("INSERT INTO knowledge_nuggets (source_url,source_title,topic,summary,relevance_score,approved,created_ts,query_origin) VALUES(?,?,?,?,?,0,?,?);", (source_url, source_title or "", topic, summary, float(relevance), ts, query_origin or ""))
            return int(conn.execute("SELECT last_insert_rowid() AS id;").fetchone()["id"])
    finally: conn.close()

def list_nuggets(approved=None, limit=500):
    init_knowledge_db(); conn = _connect()
    try:
        if approved is not None:
            rows = conn.execute("SELECT * FROM knowledge_nuggets WHERE approved=? ORDER BY created_ts DESC LIMIT ?;", (int(approved), limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge_nuggets ORDER BY created_ts DESC LIMIT ?;", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally: conn.close()

def search_nuggets(query, approved_only=True, limit=20):
    init_knowledge_db(); like = "%" + (query or "").strip() + "%"; conn = _connect()
    try:
        cond = "(topic LIKE ? OR summary LIKE ? OR source_title LIKE ?)"; args = [like,like,like]
        if approved_only:
            rows = conn.execute("SELECT * FROM knowledge_nuggets WHERE approved=1 AND " + cond + " ORDER BY relevance_score DESC, created_ts DESC LIMIT ?;", args+[limit]).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge_nuggets WHERE " + cond + " ORDER BY relevance_score DESC, created_ts DESC LIMIT ?;", args+[limit]).fetchall()
        return [dict(r) for r in rows]
    finally: conn.close()

def approve_nugget(nid):
    conn=_connect()
    try:
        with conn: conn.execute("UPDATE knowledge_nuggets SET approved=1 WHERE id=?;",(int(nid),))
    finally: conn.close()

def reject_nugget(nid):
    conn=_connect()
    try:
        with conn: conn.execute("UPDATE knowledge_nuggets SET approved=-1 WHERE id=?;",(int(nid),))
    finally: conn.close()

def delete_nugget(nid):
    conn=_connect()
    try:
        with conn: conn.execute("DELETE FROM knowledge_nuggets WHERE id=?;",(int(nid),))
    finally: conn.close()

def delete_all_rejected():
    conn=_connect()
    try:
        with conn:
            ids=[r["id"] for r in conn.execute("SELECT id FROM knowledge_nuggets WHERE approved=-1;").fetchall()]
            if ids: conn.executemany("DELETE FROM knowledge_nuggets WHERE id=?;",[(i,) for i in ids])
            return len(ids)
    finally: conn.close()

def log_query(query, result_count=0, triggered_by="schedule"):
    init_knowledge_db(); conn=_connect()
    try:
        with conn: conn.execute("INSERT INTO autonomous_queries(query,ran_ts,result_count,triggered_by) VALUES(?,?,?,?);",(query,int(time.time()),int(result_count),triggered_by))
    finally: conn.close()

def recent_queries(limit=50):
    init_knowledge_db(); conn=_connect()
    try:
        return [r["query"] for r in conn.execute("SELECT query FROM autonomous_queries ORDER BY ran_ts DESC LIMIT ?;",(limit,)).fetchall()]
    finally: conn.close()

def get_knowledge_stats():
    init_knowledge_db(); conn=_connect()
    try:
        c = lambda sql: int(conn.execute(sql).fetchone()["c"])
        return {"pages_fetched":c("SELECT COUNT(*) AS c FROM fetched_pages;"),"nuggets_pending":c("SELECT COUNT(*) AS c FROM knowledge_nuggets WHERE approved=0;"),"nuggets_approved":c("SELECT COUNT(*) AS c FROM knowledge_nuggets WHERE approved=1;"),"nuggets_rejected":c("SELECT COUNT(*) AS c FROM knowledge_nuggets WHERE approved=-1;"),"queries_run":c("SELECT COUNT(*) AS c FROM autonomous_queries;")}
    finally: conn.close()

def build_knowledge_context(query, max_nuggets=6):
    hits = search_nuggets(query, approved_only=True, limit=max_nuggets)
    if not hits: return ""
    lines = ["SAMUEL'S LEARNED KNOWLEDGE (autonomous research):"]
    for h in hits: lines.append("- [" + h["topic"] + "] " + h["summary"][:220])
    return "\n".join(lines)