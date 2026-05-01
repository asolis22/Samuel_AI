# ui/text_utils.py
import re
import time
from .theme import IMG_EXT, DOC_EXT

URL_RE = re.compile(r"(https?://[^\s\)]+)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")

def sanitize_markdown_links(text: str) -> str:
    def repl(m):
        label = m.group(1).strip()
        url = m.group(2).strip()
        return f"{label}\n{url}"
    return MD_LINK_RE.sub(repl, text)

def now_ts() -> int:
    return int(time.time())

def now_stamp(ts: int | None = None) -> str:
    ts = ts or now_ts()
    return time.strftime("%I:%M %p", time.localtime(ts)).lstrip("0")

def day_label(ts: int) -> str:
    return time.strftime("%b %d, %Y", time.localtime(ts)).replace(" 0", " ")

def is_image(path: str) -> bool:
    return path.lower().endswith(IMG_EXT)

def is_doc(path: str) -> bool:
    return path.lower().endswith(DOC_EXT)

def clean_chat_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w \-\(\)\[\]\&\.\']+", "", name)
    return name[:40].strip() or "Untitled"