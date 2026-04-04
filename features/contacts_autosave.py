# contacts_autosave.py
# Auto-detects people mentioned in conversation and suggests saving them.
# Samuel listens for names, relationships, phone numbers, emails in chat.
import re
from typing import List, Dict, Optional, Tuple
import Samuel_AI.features.contacts_store as cs

# -------------------------------------------------------
# DETECTION PATTERNS
# -------------------------------------------------------

# Name patterns — "my friend Eric", "my professor Dr. Smith", "my mom", etc.
_NAME_PATTERNS = [
    # "my [relationship] [Name]" or "my [relationship] is [Name]"
    (r"my (friend|classmate|roommate|boyfriend|girlfriend|partner|brother|sister|"
     r"mom|dad|mother|father|professor|teacher|boss|coworker|colleague|tutor|advisor)"
     r"[\s,]+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
     "relationship"),

    # "[Name] is my [relationship]"
    (r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+is\s+my\s+"
     r"(friend|classmate|roommate|boyfriend|girlfriend|partner|"
     r"brother|sister|mom|dad|professor|teacher|boss|coworker)",
     "name_first"),

    # "talked to [Name]" / "texted [Name]" / "messaged [Name]"
    (r"(?:talked to|texted|messaged|called|emailed|met with|saw|told)\s+"
     r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
     "mentioned"),

    # "Dr. / Prof. / Mr. / Ms. [Name]"
    (r"\b(Dr\.|Prof\.|Professor|Mr\.|Ms\.|Mrs\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
     "title"),
]

# Phone number pattern
_PHONE_RE = re.compile(
    r"\b(\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})\b"
)

# Email pattern
_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"
)

# Relationship keywords
_RELATIONSHIPS = {
    "friend", "classmate", "roommate", "boyfriend", "girlfriend", "partner",
    "brother", "sister", "mom", "dad", "mother", "father", "professor",
    "teacher", "boss", "coworker", "colleague", "tutor", "advisor",
    "dr", "prof", "mr", "ms", "mrs",
}

# Names to always ignore
_IGNORE_NAMES = {
    "Samuel", "I", "The", "This", "That", "He", "She", "They",
    "We", "You", "It", "My", "His", "Her", "Our", "Your",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "January", "February", "March", "April",
    "May", "June", "July", "August", "September", "October",
    "November", "December", "Google", "Apple", "Amazon",
}


# -------------------------------------------------------
# DETECTION
# -------------------------------------------------------

def detect_contacts(text: str) -> List[Dict]:
    """
    Scan a message for people worth adding to contacts.
    Returns list of candidate dicts: {name, relationship, source_text, confidence}
    """
    candidates = []
    seen_names = set()

    for pattern, mode in _NAME_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            if mode == "relationship":
                rel  = m.group(1).lower()
                name = m.group(2).strip()
            elif mode == "name_first":
                name = m.group(1).strip()
                rel  = m.group(2).lower()
            elif mode == "mentioned":
                name = m.group(1).strip()
                rel  = ""
            elif mode == "title":
                title = m.group(1).rstrip(".")
                name  = m.group(2).strip()
                rel   = title.lower()
            else:
                continue

            if name in _IGNORE_NAMES or len(name) < 2:
                continue
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            # Check if already in contacts
            existing = cs.find_contact_by_name(name)
            if existing:
                # Log the mention and update relationship if we learned something new
                cs.log_mention(existing["id"], context=text[:200])
                if rel and not existing.get("relationship"):
                    cs.update_contact(existing["id"], relationship=rel)
                continue

            candidates.append({
                "name":         name,
                "relationship": rel,
                "source_text":  text[:200],
                "confidence":   0.9 if rel else 0.6,
            })

    return candidates


def detect_phone_in_text(text: str) -> Optional[str]:
    m = _PHONE_RE.search(text)
    return m.group(1).strip() if m else None


def detect_email_in_text(text: str) -> Optional[str]:
    m = _EMAIL_RE.search(text)
    return m.group(1).strip() if m else None


# -------------------------------------------------------
# AUTO-SAVE (called from gui_app after each user message)
# -------------------------------------------------------

def auto_detect_and_queue(user_text: str) -> List[Dict]:
    """
    Scan the user's message and return candidates that should be
    proposed to the user for saving. The GUI confirms before saving.
    Returns list of candidate dicts.
    """
    cs.init_contacts_db()
    return detect_contacts(user_text)


def save_contact_from_candidate(candidate: Dict,
                                 phone: str = "",
                                 email: str = "") -> int:
    """Save a detected candidate to the contacts DB."""
    tags = []
    rel = (candidate.get("relationship") or "").lower()
    if rel in ("classmate", "professor", "teacher", "tutor", "advisor"):
        tags.append("school")
    if rel in ("boss", "coworker", "colleague"):
        tags.append("work")
    if rel in ("mom", "dad", "mother", "father", "brother", "sister"):
        tags.append("family")
    if rel in ("friend", "roommate", "boyfriend", "girlfriend", "partner"):
        tags.append("personal")

    return cs.add_contact(
        name=candidate["name"],
        relationship=candidate.get("relationship", ""),
        phone=phone or "",
        email=email or "",
        tags=tags,
        source="auto",
    )


# -------------------------------------------------------
# CONTEXT SUMMARY  (for Samuel's system prompt)
# -------------------------------------------------------

def build_contacts_summary(limit: int = 10) -> str:
    """Short contact list for Samuel's system prompt."""
    contacts = cs.list_contacts(limit=limit)
    if not contacts:
        return ""
    lines = ["CONTACTS:"]
    for c in contacts:
        line = "- " + c["name"]
        if c.get("relationship"):
            line += " (" + c["relationship"] + ")"
        if c.get("phone"):
            line += "  📞 " + c["phone"]
        if c.get("email"):
            line += "  ✉ " + c["email"]
        lines.append(line)
    return "\n".join(lines)
