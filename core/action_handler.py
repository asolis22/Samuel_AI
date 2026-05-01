# action_handler.py
# Detects actionable intents in chat and executes them.
# Handles: send email, draft email, add calendar event, check schedule.
# Samuel confirms before sending anything — nothing fires without your OK.

import re
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple


# -------------------------------------------------------
# INTENT DETECTION
# -------------------------------------------------------

_EMAIL_SEND_TRIGGERS = [
    "send that email", "send the email", "send it", "go ahead and send",
    "yes send it", "send this email", "send that", "go ahead send",
    "please send it", "send now", "send the draft", "send this",
]

_EMAIL_DRAFT_TRIGGERS = [
    "draft an email", "write an email", "compose an email",
    "help me write an email", "write an email to", "draft a message to",
    "send an email to", "email to", "write to", "message to",
    "draft email", "compose email",
]

_CALENDAR_ADD_TRIGGERS = [
    "add to my calendar", "add to calendar", "put on my calendar",
    "schedule that", "schedule a", "put it on my calendar",
    "create an event", "add an event", "block off", "set a reminder",
    "remind me", "add this to my schedule", "put on my schedule",
    "schedule me", "create a meeting",
]

_CALENDAR_CHECK_TRIGGERS = [
    "what's on my calendar", "what's my schedule", "what do i have today",
    "what's today", "check my calendar", "show my schedule",
    "what's happening", "do i have anything", "my schedule today",
    "what's on my schedule", "what do i have", "any events today",
    "check my schedule", "show my calendar",
]

_CONFIRM_TRIGGERS = [
    "yes", "yeah", "yep", "sure", "go ahead", "do it",
    "confirmed", "correct", "that's right", "send it",
    "yes please", "please do", "ok", "okay", "perfect",
    "looks good", "that's perfect", "go for it",
]

_CANCEL_TRIGGERS = [
    "no", "cancel", "don't send", "never mind", "stop",
    "don't do it", "abort", "nope", "not yet", "wait",
]


def detect_intent(text: str) -> Optional[str]:
    t = text.strip().lower()
    if any(trigger in t for trigger in _EMAIL_SEND_TRIGGERS):
        return "email_send"
    if any(trigger in t for trigger in _EMAIL_DRAFT_TRIGGERS):
        return "email_draft"
    if any(trigger in t for trigger in _CALENDAR_ADD_TRIGGERS):
        return "calendar_add"
    if any(trigger in t for trigger in _CALENDAR_CHECK_TRIGGERS):
        return "calendar_check"
    return None


def is_confirmation(text: str) -> bool:
    t = text.strip().lower()
    return any(t == c or t.startswith(c + " ") or t.startswith(c + ",")
               for c in _CONFIRM_TRIGGERS)


def is_cancellation(text: str) -> bool:
    t = text.strip().lower()
    return any(t == c or t.startswith(c + " ")
               for c in _CANCEL_TRIGGERS)


# -------------------------------------------------------
# EMAIL EXTRACTION
# -------------------------------------------------------

def extract_email_details(text: str, llm_fn) -> Dict:
    """
    Use the LLM to extract: to, subject, body from a user message.
    Returns dict with keys: to, subject, body
    """
    prompt = (
        "Extract email details from this message. "
        "Return ONLY raw JSON, no markdown, no explanation.\n"
        'Format: {"to": "email or name", "subject": "subject line", "body": "email body"}\n'
        "If any field is missing use empty string.\n\n"
        "Message: " + text
    )
    try:
        import json
        raw = llm_fn([{"role": "user", "content": prompt}], temperature=0.1)
        raw = re.sub(r"```(?:json)?", "", (raw or "")).strip()
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            return json.loads(raw[s:e+1])
    except Exception:
        pass
    return {"to": "", "subject": "", "body": ""}


# -------------------------------------------------------
# CALENDAR EXTRACTION
# -------------------------------------------------------

def extract_event_details(text: str, llm_fn) -> Dict:
    """
    Use the LLM to extract event details.
    Returns dict with: title, date, start_time, end_time, location
    """
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"Today is {today}. Extract calendar event details from this message.\n"
        "Return ONLY raw JSON, no markdown, no explanation.\n"
        '{"title":"event name","date":"YYYY-MM-DD","start_time":"HH:MM","end_time":"HH:MM","location":""}\n'
        "Rules:\n"
        "- date must be YYYY-MM-DD format\n"
        "- times must be 24h HH:MM format\n"
        "- if no end time, add 1 hour to start\n"
        "- if no date mentioned, use today\n\n"
        "Message: " + text
    )
    try:
        import json
        raw = llm_fn([{"role": "user", "content": prompt}], temperature=0.1)
        raw = re.sub(r"```(?:json)?", "", (raw or "")).strip()
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            return json.loads(raw[s:e+1])
    except Exception:
        pass
    return {"title": "", "date": today, "start_time": "09:00",
            "end_time": "10:00", "location": ""}


# -------------------------------------------------------
# ACTION STATE  (tracks pending confirmations)
# -------------------------------------------------------

class ActionState:
    """
    Holds the pending action waiting for user confirmation.
    One instance lives on SamuelGUI.
    """
    def __init__(self):
        self.pending_action: Optional[str] = None   # "email_send" | "calendar_add"
        self.pending_data:   Optional[Dict] = None   # extracted details
        self.draft_body:     Optional[str]  = None   # last drafted email body

    def set(self, action: str, data: Dict):
        self.pending_action = action
        self.pending_data   = data

    def clear(self):
        self.pending_action = None
        self.pending_data   = None

    def has_pending(self) -> bool:
        return self.pending_action is not None


# -------------------------------------------------------
# HANDLERS  (called from gui_app.send_message)
# -------------------------------------------------------

def handle_calendar_check(say_fn, system_say_fn):
    """Fetch and display today's schedule."""
    def _fetch():
        try:
            from Samuel_AI.features.google_calendar import build_today_context, build_calendar_context
            today  = build_today_context()
            week   = build_calendar_context(days=7)
            result = (today or "No events today.") + "\n\n" + (week or "")
            say_fn(result.strip())
        except Exception as e:
            say_fn("I couldn't reach your calendar: " + str(e))
    threading.Thread(target=_fetch, daemon=True).start()


def handle_email_draft(user_text: str, state: ActionState,
                        say_fn, system_say_fn, llm_fn):
    """Extract email details and show a draft for confirmation."""
    def _draft():
        details = extract_email_details(user_text, llm_fn)
        to      = details.get("to", "").strip()
        subject = details.get("subject", "").strip()
        body    = details.get("body", "").strip()

        if not body:
            # Ask LLM to write the email
            write_prompt = (
                "Write a professional but friendly email based on this request.\n"
                "Request: " + user_text + "\n\n"
                "Return ONLY the email body text, no subject line, no headers."
            )
            body = llm_fn([{"role": "user", "content": write_prompt}],
                           temperature=0.6) or ""

        state.set("email_send", {"to": to, "subject": subject, "body": body})

        preview = (
            f"📧 Here's your draft:\n\n"
            f"To: {to or '(not specified)'}\n"
            f"Subject: {subject or '(not specified)'}\n\n"
            f"{body}\n\n"
            f"——\n"
            f"Say 'send it' to send, or tell me what to change."
        )
        system_say_fn(preview)

    threading.Thread(target=_draft, daemon=True).start()


def handle_email_send(state: ActionState, say_fn, system_say_fn):
    """Send the pending email draft."""
    data    = state.pending_data or {}
    to      = data.get("to", "").strip()
    subject = data.get("subject", "").strip()
    body    = data.get("body", "").strip()

    if not to:
        system_say_fn("Who should I send this to? Give me an email address.")
        return
    if not body:
        system_say_fn("There's nothing to send yet. Let's draft the email first.")
        return

    def _send():
        try:
            from Samuel_AI.features.google_gmail import send_email
            send_email(to, subject or "(no subject)", body)
            state.clear()
            system_say_fn(f"✅ Email sent to {to}!")
        except Exception as e:
            system_say_fn(f"❌ Failed to send: {str(e)[:80]}")

    threading.Thread(target=_send, daemon=True).start()


def handle_calendar_add(user_text: str, state: ActionState,
                         say_fn, system_say_fn, llm_fn):
    """Extract event details and confirm before adding."""
    def _extract():
        details    = extract_event_details(user_text, llm_fn)
        title      = details.get("title", "").strip()
        date_str   = details.get("date", "").strip()
        start_str  = details.get("start_time", "09:00").strip()
        end_str    = details.get("end_time", "10:00").strip()
        location   = details.get("location", "").strip()

        if not title:
            system_say_fn("What should I call this event?")
            return

        state.set("calendar_add", {
            "title": title, "date": date_str,
            "start_time": start_str, "end_time": end_str,
            "location": location,
        })

        preview = (
            f"📅 Add this to your calendar?\n\n"
            f"  {title}\n"
            f"  {date_str}  {start_str} — {end_str}"
            + (f"\n  📍 {location}" if location else "") +
            f"\n\nSay 'yes' to confirm or tell me what to change."
        )
        system_say_fn(preview)

    threading.Thread(target=_extract, daemon=True).start()


def handle_calendar_confirm(state: ActionState, system_say_fn):
    """Add the confirmed event to Google Calendar."""
    data      = state.pending_data or {}
    title     = data.get("title", "Event")
    date_str  = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    start_str = data.get("start_time", "09:00")
    end_str   = data.get("end_time", "10:00")
    location  = data.get("location", "")

    def _add():
        try:
            from Samuel_AI.features.google_calendar import create_event
            start_dt = datetime.fromisoformat(f"{date_str}T{start_str}:00")
            end_dt   = datetime.fromisoformat(f"{date_str}T{end_str}:00")
            create_event(title=title, start_dt=start_dt, end_dt=end_dt,
                          location=location)
            state.clear()
            system_say_fn(
                f"✅ Added '{title}' to your calendar on {date_str} at {start_str}!"
            )
        except Exception as e:
            system_say_fn(f"❌ Couldn't add event: {str(e)[:80]}")

    threading.Thread(target=_add, daemon=True).start()
