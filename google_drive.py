# google_drive.py
# Google Drive integration — search files, read docs, list recent files.
import io
from typing import List, Dict, Optional
from google_auth import get_credentials


def _service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=get_credentials())


READABLE_MIME_TYPES = {
    "application/vnd.google-apps.document":     "text/plain",
    "application/vnd.google-apps.spreadsheet":  "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


# ---------------------------------------------------------------------------
# SEARCH + LIST
# ---------------------------------------------------------------------------

def list_recent_files(max_results: int = 20) -> List[Dict]:
    """List most recently modified files."""
    svc = _service()
    res = svc.files().list(
        pageSize=max_results,
        orderBy="modifiedTime desc",
        fields="files(id,name,mimeType,modifiedTime,size,webViewLink)",
    ).execute()
    return [_parse_file(f) for f in res.get("files", [])]


def search_files(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search Drive files by name or content.
    Uses Drive query syntax: name contains 'x' or fullText contains 'x'
    """
    svc = _service()
    q   = f"(name contains '{query}' or fullText contains '{query}') and trashed=false"
    res = svc.files().list(
        q=q,
        pageSize=max_results,
        orderBy="modifiedTime desc",
        fields="files(id,name,mimeType,modifiedTime,size,webViewLink)",
    ).execute()
    return [_parse_file(f) for f in res.get("files", [])]


def list_folder(folder_id: str = "root", max_results: int = 30) -> List[Dict]:
    """List files in a specific folder."""
    svc = _service()
    q   = f"'{folder_id}' in parents and trashed=false"
    res = svc.files().list(
        q=q,
        pageSize=max_results,
        orderBy="name",
        fields="files(id,name,mimeType,modifiedTime,size,webViewLink)",
    ).execute()
    return [_parse_file(f) for f in res.get("files", [])]


def _parse_file(f: dict) -> Dict:
    return {
        "id":           f.get("id", ""),
        "name":         f.get("name", ""),
        "mime_type":    f.get("mimeType", ""),
        "modified":     f.get("modifiedTime", ""),
        "size":         f.get("size", ""),
        "link":         f.get("webViewLink", ""),
        "is_google_doc": f.get("mimeType", "").startswith("application/vnd.google-apps"),
    }


# ---------------------------------------------------------------------------
# READ FILE CONTENT
# ---------------------------------------------------------------------------

def read_file_text(file_id: str, max_chars: int = 8000) -> str:
    """
    Read the text content of a Drive file.
    Works on Google Docs, Sheets, Slides, and plain text files.
    """
    svc = _service()

    # Get file metadata first
    meta = svc.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "")

    if mime in READABLE_MIME_TYPES:
        # Export Google Workspace files as plain text
        export_mime = READABLE_MIME_TYPES[mime]
        content = svc.files().export(
            fileId=file_id, mimeType=export_mime
        ).execute()
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="ignore")[:max_chars]
        return str(content)[:max_chars]

    elif mime == "text/plain" or mime.startswith("text/"):
        # Download plain text files directly
        content = svc.files().get_media(fileId=file_id).execute()
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="ignore")[:max_chars]
        return str(content)[:max_chars]

    return f"[Cannot read file type: {mime}]"


# ---------------------------------------------------------------------------
# CONTEXT BUILDER
# ---------------------------------------------------------------------------

def build_drive_context(query: str = "", max_files: int = 5) -> str:
    """
    Search Drive for files relevant to the conversation
    and inject into Samuel's prompt.
    """
    try:
        if query:
            files = search_files(query, max_results=max_files)
        else:
            files = list_recent_files(max_results=max_files)

        if not files:
            return ""

        lines = ["GOOGLE DRIVE FILES:"]
        for f in files:
            size = f"  ({f['size']} bytes)" if f.get("size") else ""
            lines.append(f"- {f['name']}{size}  [{f['modified'][:10]}]")
        return "\n".join(lines)
    except Exception:
        return ""
