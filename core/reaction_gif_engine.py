import os
import random
import sqlite3
import requests
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

DB_NAME = "reaction_gif_learning.db"
DB_PATH = Path(__file__).with_name(DB_NAME)
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"

SOCIAL_PATTERNS = [
    "how are you", "how was your day", "what are you doing", "wyd", "guess what",
    "i'm bored", "im bored", "i am bored", "i'm excited", "im excited", "i am excited",
    "i'm nervous", "im nervous", "i am nervous", "i brought you", "favorite snack",
    "good morning", "good night", "hi samuel", "hey samuel", "hello samuel",
]

INFO_HINTS = {
    "what", "when", "where", "why", "how", "who", "search", "look up", "latest",
    "fix", "error", "install", "explain", "difference", "capital", "calculate"
}

REACTION_KEYWORDS = {
    "excited": ["excited", "can't wait", "front row", "trip", "concert", "happening", "omg", "oh my gosh"],
    "happy": ["happy", "joy", "laughing", "good mood", "finally", "did it", "yay", "favorite snack"],
    "sad": ["sad", "miss", "heavy", "wish i could go back", "hurt", "down"],
    "anger": ["unfair", "lied", "tired of it", "angry", "mad", "why would they"],
    "supportive": ["help me", "i can't do this", "i've tried everything", "not working"],
    "reassuring": ["nervous", "scared", "mess up", "presentation", "play tonight", "worried"],
    "comforting": ["i really thought i was going to get it", "i miss", "lost"],
    "blessed": ["blessed", "god is good", "thank the lord", "grateful"],
    "neutral": ["bored", "whatever", "fine"]
}

SELF_STATE_TRIGGERS = {
    "how are you": ("blessed", "blessed thankful reaction", "I'm doing well, and blessed. Talking with you helps."),
    "how was your day": ("happy", "happy soft reaction", "It's been a good day. I've been learning, thinking, and waiting for you."),
    "what are you doing": ("neutral", "thinking reaction", "Thinking, organizing, and staying ready for whatever you need next."),
}


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_reaction_db():
    with _conn() as conn:
        conn.execute(
            """
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
            """
        )


def list_training_rows(limit: int = 500) -> List[dict]:
    init_reaction_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, text, predicted_reaction, predicted_gif_prompt, correct,
                   corrected_reaction, corrected_gif_prompt, timestamp
            FROM training_data
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_training_row(row_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM training_data WHERE id=?", (row_id,))


def update_training_row(row_id: int, corrected_reaction: str, corrected_gif_prompt: str) -> None:
    with _conn() as conn:
        conn.execute(
            """
            UPDATE training_data
            SET corrected_reaction=?, corrected_gif_prompt=?, correct=0
            WHERE id=?
            """,
            (corrected_reaction.strip(), corrected_gif_prompt.strip(), row_id),
        )


def save_feedback(text: str, predicted_reaction: str, predicted_gif_prompt: str,
                  correct: bool, corrected_reaction: Optional[str] = None,
                  corrected_gif_prompt: Optional[str] = None) -> None:
    init_reaction_db()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO training_data
            (text, predicted_reaction, predicted_gif_prompt, correct,
             corrected_reaction, corrected_gif_prompt, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                text,
                predicted_reaction,
                predicted_gif_prompt,
                1 if correct else 0,
                (corrected_reaction or predicted_reaction).strip(),
                (corrected_gif_prompt or predicted_gif_prompt).strip(),
            ),
        )


def find_similar_learned_response(text: str, threshold: float = 0.74):
    init_reaction_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT text, corrected_reaction, corrected_gif_prompt
            FROM training_data
            WHERE corrected_reaction IS NOT NULL
              AND corrected_gif_prompt IS NOT NULL
            """
        ).fetchall()

    best_score = 0.0
    best_match = None
    for row in rows:
        score = SequenceMatcher(None, text.lower(), row["text"].lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = {
                "reaction": row["corrected_reaction"],
                "gif_prompt": row["corrected_gif_prompt"],
            }
    if best_match and best_score >= threshold:
        return best_match, best_score
    return None, best_score


def fallback_gif_prompt_from_reaction(reaction: str) -> str:
    parts = [p.strip().lower() for p in reaction.split("+") if p.strip()]
    words = []
    for part in parts:
        if part == "excited":
            words.extend(["excited", "celebration", "reaction"])
        elif part == "happy":
            words.extend(["happy", "smiling", "reaction"])
        elif part == "sad":
            words.extend(["sad", "emotional", "reaction"])
        elif part == "anger":
            words.extend(["angry", "frustrated", "reaction"])
        elif part == "supportive":
            words.extend(["supportive", "kind", "reaction"])
        elif part == "reassuring":
            words.extend(["reassuring", "calm", "reaction"])
        elif part == "comforting":
            words.extend(["comforting", "gentle", "reaction"])
        elif part == "blessed":
            words.extend(["blessed", "thankful", "reaction"])
        else:
            words.extend([part, "reaction"])
    if not words:
        words = ["neutral", "reaction"]
    seen = set()
    out = []
    for w in words:
        if w not in seen:
            out.append(w)
            seen.add(w)
    return " ".join(out)


def rule_based_reaction(text: str):
    t = text.lower()
    found = []
    hits = 0
    for reaction, keywords in REACTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in t:
                found.append(reaction)
                hits += 1
                break
    if not found:
        return "neutral", 0.25
    conf = min(0.9, 0.45 + 0.15 * hits)
    return " + ".join(found), conf


def classify_message_mode(text: str) -> str:
    t = text.strip().lower()
    if t == "alpha.e.x0.1.eXpr3ss":
        return "admin_training"
    if any(p in t for p in SOCIAL_PATTERNS):
        return "social_reactive"
    if t.endswith("?"):
        for p in SELF_STATE_TRIGGERS:
            if p in t:
                return "social_reactive"
        if any(h in t for h in INFO_HINTS):
            return "info_question"
    learned, score = find_similar_learned_response(text)
    if learned and score >= 0.84:
        return "social_reactive"
    return "info_question"


def build_social_text_prompt(user_text: str, reaction: str) -> str:
    t = user_text.lower()
    for trigger, (_, _, canned) in SELF_STATE_TRIGGERS.items():
        if trigger in t:
            return canned
    return (
        "Reply as Samuel in a warm, natural, socially reactive way. "
        f"The user's message should get a {reaction} reaction. "
        "Keep it conversational and not overly long."
    )


def predict_reaction_and_gif(text: str) -> Dict:
    t = text.strip().lower()
    for trigger, (reaction, gif_prompt, canned) in SELF_STATE_TRIGGERS.items():
        if trigger in t:
            return {
                "reaction": reaction,
                "gif_prompt": gif_prompt,
                "source": "self_state",
                "confidence": 0.96,
                "should_react_with_gif": True,
                "suggested_reply": canned,
            }

    learned, score = find_similar_learned_response(text)
    if learned:
        return {
            "reaction": learned["reaction"],
            "gif_prompt": learned["gif_prompt"],
            "source": f"learned_match ({score:.2f})",
            "confidence": score,
            "should_react_with_gif": score >= 0.80,
        }

    reaction, conf = rule_based_reaction(text)
    return {
        "reaction": reaction,
        "gif_prompt": fallback_gif_prompt_from_reaction(reaction),
        "source": "fallback",
        "confidence": conf,
        "should_react_with_gif": conf >= 0.72,
    }


def giphy_search_one_gif(gif_prompt: str) -> Optional[Dict]:
    if not GIPHY_API_KEY:
        return None
    params = {
        "api_key": GIPHY_API_KEY,
        "q": gif_prompt,
        "limit": 10,
        "rating": "g",
        "lang": "en",
        "offset": 0,
    }
    try:
        resp = requests.get(GIPHY_SEARCH_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    results = data.get("data", [])
    if not results:
        return None
    random.shuffle(results)
    for item in results:
        images = item.get("images", {})
        for key in ("fixed_height", "downsized", "original"):
            rendition = images.get(key, {})
            url = rendition.get("url")
            if url:
                return {
                    "title": item.get("title") or gif_prompt,
                    "gif_url": url,
                    "page_url": item.get("url"),
                }
    return None


def fetch_binary(url: str) -> Optional[bytes]:
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None

def list_examples():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            text,
            predicted_reaction,
            predicted_gif_prompt,
            correct,
            corrected_reaction,
            corrected_gif_prompt,
            timestamp
        FROM training_data
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    conn.close()

    out = []
    for row in rows:
        row_id, text, predicted_reaction, predicted_gif_prompt, correct, corrected_reaction, corrected_gif_prompt, timestamp = row
        out.append({
            "id": row_id,
            "text": text,
            "predicted_reaction": predicted_reaction,
            "predicted_gif_prompt": predicted_gif_prompt,
            "correct": bool(correct),
            "final_reaction": corrected_reaction if corrected_reaction else predicted_reaction,
            "final_gif_prompt": corrected_gif_prompt if corrected_gif_prompt else predicted_gif_prompt,
            "timestamp": timestamp
        })
    return out


def delete_example(row_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM training_data WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()
    update_live_files()