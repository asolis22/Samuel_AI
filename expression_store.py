# expression_store.py
# SQLite backend for custom expressions + emotion training data.
# Samuel learns which expressions match which emotional contexts over time.

import sqlite3
import json
import os
import time
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "samuel_expressions.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_expression_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS expressions (
            name        TEXT PRIMARY KEY,
            params      TEXT NOT NULL,
            description TEXT DEFAULT '',
            keywords    TEXT DEFAULT '',
            builtin     INTEGER DEFAULT 0,
            created_at  REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS training_samples (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT NOT NULL,
            predicted   TEXT NOT NULL,
            correct     TEXT NOT NULL,
            was_right   INTEGER NOT NULL,
            created_at  REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS keyword_weights (
            keyword     TEXT NOT NULL,
            expression  TEXT NOT NULL,
            weight      REAL DEFAULT 1.0,
            PRIMARY KEY (keyword, expression)
        );
        """)


# -------------------------------------------------------
# EXPRESSIONS
# -------------------------------------------------------

def save_expression(name: str, params: Dict, description: str = "",
                    keywords: str = "", builtin: bool = False):
    with _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO expressions
            (name, params, description, keywords, builtin, created_at)
            VALUES (?,?,?,?,?,?)
        """, (name.lower().strip(), json.dumps(params),
              description, keywords, int(builtin), time.time()))


def get_expression(name: str) -> Optional[Dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM expressions WHERE name=?",
                        (name.lower().strip(),)).fetchone()
        if not row:
            return None
        return {
            "name":        row["name"],
            "params":      json.loads(row["params"]),
            "description": row["description"],
            "keywords":    row["keywords"],
            "builtin":     bool(row["builtin"]),
        }


def list_expressions() -> List[Dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM expressions ORDER BY builtin DESC, name ASC"
        ).fetchall()
        return [{"name": r["name"], "params": json.loads(r["params"]),
                 "description": r["description"], "keywords": r["keywords"],
                 "builtin": bool(r["builtin"])} for r in rows]


def delete_expression(name: str):
    with _conn() as c:
        c.execute("DELETE FROM expressions WHERE name=? AND builtin=0",
                  (name.lower().strip(),))


# -------------------------------------------------------
# TRAINING
# -------------------------------------------------------

def save_training_sample(text: str, predicted: str,
                          correct: str, was_right: bool):
    with _conn() as c:
        c.execute("""
            INSERT INTO training_samples
            (text, predicted, correct, was_right, created_at)
            VALUES (?,?,?,?,?)
        """, (text, predicted, correct, int(was_right), time.time()))
    # Update keyword weights
    _update_keyword_weights(text, correct, boost=1.0 if was_right else 0.3)
    if not was_right:
        _update_keyword_weights(text, predicted, boost=-0.4)


def _update_keyword_weights(text: str, expression: str, boost: float):
    words = [w.strip(".,!?").lower() for w in text.split() if len(w) > 2]
    with _conn() as c:
        for word in words:
            existing = c.execute(
                "SELECT weight FROM keyword_weights WHERE keyword=? AND expression=?",
                (word, expression)
            ).fetchone()
            if existing:
                new_w = max(0.0, existing["weight"] + boost)
                c.execute(
                    "UPDATE keyword_weights SET weight=? WHERE keyword=? AND expression=?",
                    (new_w, word, expression)
                )
            else:
                c.execute(
                    "INSERT INTO keyword_weights (keyword, expression, weight) VALUES (?,?,?)",
                    (word, expression, max(0.0, 1.0 + boost))
                )


def predict_from_training(text: str) -> Optional[str]:
    """Use learned keyword weights to predict expression."""
    words = [w.strip(".,!?").lower() for w in text.split() if len(w) > 2]
    if not words:
        return None
    with _conn() as c:
        scores = {}
        for word in words:
            rows = c.execute(
                "SELECT expression, weight FROM keyword_weights WHERE keyword=?",
                (word,)
            ).fetchall()
            for r in rows:
                scores[r["expression"]] = scores.get(r["expression"], 0) + r["weight"]
        if not scores:
            return None
        return max(scores, key=scores.get)


def get_training_stats() -> Dict:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM training_samples").fetchone()[0]
        right = c.execute(
            "SELECT COUNT(*) FROM training_samples WHERE was_right=1"
        ).fetchone()[0]
        recent = c.execute(
            "SELECT * FROM training_samples ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        return {
            "total":    total,
            "correct":  right,
            "accuracy": round(right / total * 100, 1) if total else 0,
            "recent":   [dict(r) for r in recent],
        }
