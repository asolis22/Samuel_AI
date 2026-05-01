# web_search.py  (improved — fixes broken links + better ranking)
import re, time, html as html_lib, requests
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

try:    import trafilatura
except: trafilatura = None
try:    from bs4 import BeautifulSoup
except: BeautifulSoup = None

HEADERS = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
DDG_BASE = "https://duckduckgo.com"

BLOCK_DOMAINS = {"wikipedia.org","wikidata.org","wikimedia.org","m.wikipedia.org","en.wikipedia.org","fandom.com","wikia.com","quora.com","pinterest.com"}
DOMAIN_BOOSTS = {".gov":2.0,".edu":1.7,"docs.python.org":1.8,"developer.mozilla.org":1.8,"reuters.com":1.5,"apnews.com":1.4,"bbc.com":1.4,"bbc.co.uk":1.4,"nytimes.com":1.3,"wsj.com":1.3,"theguardian.com":1.2,"nature.com":1.5,"healthline.com":1.3,"mayoclinic.org":1.5,"khanacademy.org":1.4}

def _clean_html(s):
    return re.sub("<.*?>","",html_lib.unescape(s or ""),flags=re.S).strip()

def _normalize_ddg_href(href):
    if not href: return ""
    href = html_lib.unescape(href)
    if href.startswith("//"): href = "https:" + href
    elif href.startswith("/") and not href.startswith("//"): href = urljoin(DDG_BASE, href)
    try:
        u = urlparse(href)
        if "duckduckgo.com" in (u.netloc or "") and u.path.startswith("/l/"):
            qs = parse_qs(u.query)
            if "uddg" in qs and qs["uddg"]: return unquote(qs["uddg"][0])
    except Exception: pass
    return href

def _domain(url):
    try: return (urlparse(url).netloc or "").lower()
    except: return ""

def _is_blocked(url):
    d = _domain(url)
    if not d: return True
    return any(d == b or d.endswith("." + b) for b in BLOCK_DOMAINS)

def _domain_boost(url):
    d = _domain(url); best = 0.0
    for host, b in DOMAIN_BOOSTS.items():
        if host.startswith(".") and d.endswith(host): best = max(best, b)
        elif not host.startswith(".") and (d == host or d.endswith("." + host)): best = max(best, b)
    return best

def duckduckgo_html_search(query, max_results=10):
    url = DDG_BASE + "/html/?q=" + quote_plus(query)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception: return []

    html = r.text; results = []
    links   = re.findall(r'<a[^>]*class="result__a"[^>]*href="(.*?)"[^>]*>(.*?)</a>', html, re.S|re.I)
    snips   = re.findall(r'class="result__snippet[^"]*"[^>]*>(.*?)</(?:a|span|div)>', html, re.S|re.I)

    for i,(href,title_html) in enumerate(links[:max_results*3]):
        title    = _clean_html(title_html)
        real_url = _normalize_ddg_href(href)
        snip     = _clean_html(snips[i]) if i < len(snips) else ""
        if not real_url or _is_blocked(real_url) or not real_url.startswith("http"): continue
        results.append({"title":title,"url":real_url,"snippet":snip})
        if len(results) >= max_results: break

    time.sleep(0.3)
    return results

def _score_result(query, item):
    q = (query or "").lower(); words = re.findall(r"[a-zA-Z0-9]{3,}", q)
    title = (item.get("title") or "").lower(); snip = (item.get("snippet") or "").lower()
    base = sum(1 for w in words if w in title or w in snip) / max(3, len(words)) if words else 0.0
    return base + _domain_boost(item.get("url","")) + (0.05 if (item.get("url","")).startswith("https") else 0.0)

def rank_results(query, results):
    return sorted(results, key=lambda r: _score_result(query, r), reverse=True)

def fetch_page_text(url, max_chars=14000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
        r.raise_for_status()
    except Exception: return ""
    html = r.text
    if trafilatura:
        try:
            x = trafilatura.extract(html, include_comments=False, include_tables=False)
            if x: return re.sub(r"\s+"," ",x).strip()[:max_chars]
        except: pass
    if BeautifulSoup:
        try:
            soup = BeautifulSoup(html,"lxml")
            for tag in soup(["script","style","noscript","header","footer","nav","aside"]): tag.decompose()
            return re.sub(r"\s+"," ",soup.get_text(" ")).strip()[:max_chars]
        except: pass
    html = re.sub(r"<script.*?>.*?</script>"," ",html,flags=re.S|re.I)
    html = re.sub(r"<style.*?>.*?</style>"," ",html,flags=re.S|re.I)
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html)).strip()[:max_chars]

def research(query, max_results=10, fetch_top_k=5):
    raw    = duckduckgo_html_search(query, max_results=max_results)
    raw    = [r for r in raw if r.get("url") and not _is_blocked(r["url"])]
    chosen = rank_results(query, raw)[:max(1, fetch_top_k)]
    out = []
    with ThreadPoolExecutor(max_workers=min(6,len(chosen))) as ex:
        futs = {ex.submit(fetch_page_text, it["url"]): it for it in chosen}
        for fut in as_completed(futs):
            it = futs[fut]; it2 = dict(it)
            try: it2["text"] = fut.result()
            except: it2["text"] = ""
            out.append(it2)
    url_to = {x["url"]:x for x in out}
    return [url_to[it["url"]] for it in chosen if it["url"] in url_to]