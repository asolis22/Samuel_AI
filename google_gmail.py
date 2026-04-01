# google_gmail.py
# Gmail integration — read inbox, draft, send, search emails.
import base64
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from google_auth import get_credentials


def _service():
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=get_credentials())


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def get_inbox(max_results: int = 20, label: str = "INBOX") -> List[Dict]:
    """Fetch recent emails from inbox."""
    svc = _service()
    res = svc.users().messages().list(
        userId="me", labelIds=[label], maxResults=max_results
    ).execute()

    messages = res.get("messages", [])
    emails   = []
    for m in messages:
        try:
            emails.append(_parse_message(svc, m["id"]))
        except Exception:
            continue
    return emails


def get_unread(max_results: int = 10) -> List[Dict]:
    """Fetch unread emails."""
    svc = _service()
    res = svc.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=max_results
    ).execute()
    emails = []
    for m in res.get("messages", []):
        try:
            emails.append(_parse_message(svc, m["id"]))
        except Exception:
            continue
    return emails


def search_emails(query: str, max_results: int = 10) -> List[Dict]:
    """Search Gmail — same syntax as Gmail search box."""
    svc = _service()
    res = svc.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    emails = []
    for m in res.get("messages", []):
        try:
            emails.append(_parse_message(svc, m["id"]))
        except Exception:
            continue
    return emails


def get_email_by_id(message_id: str) -> Optional[Dict]:
    svc = _service()
    try:
        return _parse_message(svc, message_id)
    except Exception:
        return None


def _parse_message(svc, message_id: str) -> Dict:
    msg     = svc.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    body    = _extract_body(msg["payload"])
    snippet = msg.get("snippet", "")
    labels  = msg.get("labelIds", [])

    return {
        "id":       message_id,
        "subject":  headers.get("Subject", "(no subject)"),
        "from":     headers.get("From", ""),
        "to":       headers.get("To", ""),
        "date":     headers.get("Date", ""),
        "snippet":  snippet,
        "body":     body[:3000],
        "unread":   "UNREAD" in labels,
        "labels":   labels,
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from email payload."""
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")

    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


# ---------------------------------------------------------------------------
# SEND / DRAFT
# ---------------------------------------------------------------------------

def send_email(to: str, subject: str, body: str,
               reply_to_id: str = "") -> Dict:
    """Send an email. Returns sent message info."""
    svc = _service()
    msg = MIMEMultipart()
    msg["to"]      = to
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_data = {"raw": raw}

    if reply_to_id:
        body_data["threadId"] = reply_to_id

    sent = svc.users().messages().send(
        userId="me", body=body_data
    ).execute()
    return sent


def create_draft(to: str, subject: str, body: str) -> Dict:
    """Save a draft without sending."""
    svc = _service()
    msg = MIMEMultipart()
    msg["to"]      = to
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    raw   = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = svc.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return draft


def mark_as_read(message_id: str) -> None:
    svc = _service()
    svc.users().messages().modify(
        userId="me", id=message_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()


# ---------------------------------------------------------------------------
# CONTEXT BUILDER
# ---------------------------------------------------------------------------

def build_gmail_context(max_unread: int = 5) -> str:
    """Inject unread email summary into Samuel's prompt."""
    try:
        emails = get_unread(max_results=max_unread)
        if not emails:
            return ""
        lines = [f"UNREAD EMAILS ({len(emails)}):"]
        for e in emails:
            lines.append(
                f"- From: {e['from'][:40]}  |  {e['subject'][:60]}"
            )
        return "\n".join(lines)
    except Exception:
        return ""
