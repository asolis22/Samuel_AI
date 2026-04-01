import re, io, base64, requests
from urllib.parse import quote_plus
from typing import List, Dict, Tuple
from pypdf import PdfReader
from docx import Document
from PIL import Image
from urllib.parse import urlparse, parse_qs, unquote

HEADERS = {"User-Agent": "Mozilla/5.0 (SamuelAI/1.0)"}

def web_search_ddg(query: str, max_results: int = 5) -> List[Dict]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text

    # Grab result blocks
    results = []

    pattern = re.findall(
        r'<a rel="nofollow" class="result__a" href="(.*?)".*?>(.*?)</a>',
        html,
        re.S
    )

    for href, title in pattern[:max_results]:
        clean_title = re.sub("<.*?>", "", title).strip()
        real_url = _normalize_ddg_url(href)

        results.append({
            "title": clean_title,
            "url": real_url
        })

    return results

def sniff_and_read_file(path: str, max_chars: int = 22000) -> Tuple[str, str]:
    lower = path.lower()

    if lower.endswith(".pdf"):
        reader = PdfReader(path)
        parts = []
        for page in reader.pages[:25]:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) > max_chars:
                break
        return ("pdf", "\n".join(parts)[:max_chars])

    if lower.endswith(".docx"):
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        return ("docx", text[:max_chars])

    if lower.endswith((".txt", ".md", ".csv", ".log")):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return ("text", f.read(max_chars))

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return ("text", f.read(max_chars))

def image_to_base64_png(path: str, max_side: int = 1024) -> str:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(max_side / max(w, h), 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
def _normalize_ddg_url(href: str) -> str:
    """
    DuckDuckGo HTML often returns redirect links like:
    https://duckduckgo.com/l/?uddg=<encoded>
    Decode to the real destination URL.
    """
    if not href:
        return href

    # Some results can be protocol-relative
    if href.startswith("//"):
        href = "https:" + href

    try:
        u = urlparse(href)
        if "duckduckgo.com" in u.netloc and u.path.startswith("/l/"):
            qs = parse_qs(u.query)
            if "uddg" in qs and qs["uddg"]:
                return unquote(qs["uddg"][0])
    except Exception:
        pass

    return href