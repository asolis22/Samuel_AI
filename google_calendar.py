# google_calendar.py
# Google Calendar integration — reads ALL calendars, not just primary.
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from google_auth import get_credentials


def _service():
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=get_credentials())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_iso(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def get_all_calendar_ids() -> List[str]:
    """Return IDs of every calendar in the user's account."""
    svc = _service()
    res = svc.calendarList().list().execute()
    return [c["id"] for c in res.get("items", [])]


def get_upcoming_events(days: int = 7, max_results: int = 50,
                         calendar_id: str = None) -> List[Dict]:
    svc     = _service()
    cal_ids = [calendar_id] if calendar_id else get_all_calendar_ids()
    all_events = []
    for cid in cal_ids:
        try:
            res = svc.events().list(
                calendarId=cid,
                timeMin=_now_iso(),
                timeMax=_future_iso(days),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            all_events.extend([_parse_event(e) for e in res.get("items", [])])
        except Exception:
            continue
    all_events.sort(key=lambda e: e.get("start", ""))
    return all_events


def get_todays_events(calendar_id: str = None) -> List[Dict]:
    now     = datetime.now(timezone.utc)
    start   = now.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    end     = now.replace(hour=23, minute=59, second=59, microsecond=0)
    svc     = _service()
    cal_ids = [calendar_id] if calendar_id else get_all_calendar_ids()
    all_events = []
    for cid in cal_ids:
        try:
            res = svc.events().list(
                calendarId=cid,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            all_events.extend([_parse_event(e) for e in res.get("items", [])])
        except Exception:
            continue
    all_events.sort(key=lambda e: e.get("start", ""))
    return all_events


def search_events(query: str, days_back: int = 30, days_forward: int = 30) -> List[Dict]:
    svc     = _service()
    start   = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
    end     = (datetime.now(timezone.utc) + timedelta(days=days_forward)).isoformat()
    cal_ids = get_all_calendar_ids()
    all_events = []
    for cid in cal_ids:
        try:
            res = svc.events().list(
                calendarId=cid, q=query,
                timeMin=start, timeMax=end,
                singleEvents=True, orderBy="startTime",
            ).execute()
            all_events.extend([_parse_event(e) for e in res.get("items", [])])
        except Exception:
            continue
    all_events.sort(key=lambda e: e.get("start", ""))
    return all_events


def _parse_event(e: dict) -> Dict:
    start = e.get("start", {})
    end   = e.get("end", {})
    return {
        "id":          e.get("id", ""),
        "title":       e.get("summary", "(no title)"),
        "description": e.get("description", ""),
        "location":    e.get("location", ""),
        "start":       start.get("dateTime") or start.get("date", ""),
        "end":         end.get("dateTime")   or end.get("date", ""),
        "all_day":     "date" in start and "dateTime" not in start,
        "html_link":   e.get("htmlLink", ""),
        "status":      e.get("status", "confirmed"),
    }


def _fmt_event_time(event: Dict) -> str:
    try:
        if event["all_day"]:
            return event["start"]
        dt = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
        dt = dt.astimezone()
        return dt.strftime("%a %b %d  %I:%M %p")
    except Exception:
        return event.get("start", "")


def create_event(title, start_dt, end_dt, description="", location="",
                  calendar_id="primary"):
    svc  = _service()
    body = {
        "summary": title, "description": description, "location": location,
        "start": {"dateTime": start_dt.isoformat(),
                  "timeZone": str(datetime.now().astimezone().tzinfo)},
        "end":   {"dateTime": end_dt.isoformat(),
                  "timeZone": str(datetime.now().astimezone().tzinfo)},
    }
    return _parse_event(svc.events().insert(calendarId=calendar_id, body=body).execute())


def delete_event(event_id, calendar_id="primary"):
    _service().events().delete(calendarId=calendar_id, eventId=event_id).execute()


def list_calendars():
    res = _service().calendarList().list().execute()
    return [{"id": c["id"], "name": c.get("summary",""), "primary": c.get("primary",False)}
            for c in res.get("items", [])]


def build_calendar_context(days: int = 3) -> str:
    try:
        events = get_upcoming_events(days=days, max_results=20)
        if not events:
            return ""
        lines = [f"UPCOMING CALENDAR ({days} days):"]
        for e in events:
            t = _fmt_event_time(e)
            lines.append("- " + t + "  |  " + e["title"] +
                         ("  @ " + e["location"] if e.get("location") else ""))
        return "\n".join(lines)
    except Exception:
        return ""


def build_today_context() -> str:
    try:
        events = get_todays_events()
        if not events:
            return "TODAY: No calendar events."
        lines = ["TODAY'S SCHEDULE:"]
        for e in events:
            t = _fmt_event_time(e)
            lines.append("- " + t + "  |  " + e["title"])
        return "\n".join(lines)
    except Exception:
        return ""
