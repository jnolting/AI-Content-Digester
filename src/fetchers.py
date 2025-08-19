# src/fetchers.py
from __future__ import annotations
import os
import re
import io
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse

# -------------------------
# Your original constants/utilities
# -------------------------
GITHUB_API = "https://api.github.com"

def _extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = re.findall(r'https?://\S+', text, flags=re.IGNORECASE)
    return [u.rstrip(').,;\'"') for u in urls]

def _infer_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if url.lower().endswith(".pdf"):
        return "pdf"
    return "web"

def _since_midnight_utc() -> str:
    now = datetime.now(timezone.utc)
    midnight = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    return midnight.isoformat()

def fetch_items() -> list[dict]:
    """
    Pull links from GitHub Issues updated today (UTC) and return
    a list of items like:
      { 'source': <url>, 'type': 'youtube|web|pdf', 'context': <issue title|id> }
    """
    repo = os.environ.get("GITHUB_REPOSITORY")  # e.g. jnolting/AI-Content-Digester
    token = os.environ.get("GITHUB_TOKEN")

    if not repo:
        print("GITHUB_REPOSITORY not set; returning no items.")
        return []
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {
        "state": "all",
        "sort": "updated",
        "direction": "desc",
        "since": _since_midnight_utc(),
        "per_page": 100,
    }
    url = f"{GITHUB_API}/repos/{repo}/issues"
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    issues = resp.json()

    seen = set()
    items = []
    for issue in issues:
        if "pull_request" in issue:  # skip PRs
            continue
        title = issue.get("title") or ""
        body = issue.get("body") or ""
        urls = _extract_urls(title) + _extract_urls(body)
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            items.append({
                "source": u,
                "type": _infer_type(u),
                "context": f"Issue #{issue.get('number')}: {title}",
            })

    print(f"Fetched {len(items)} link(s) from issues updated since midnight UTC.")
    return items

# -------------------------
# Helpers used by main.py
# -------------------------

def fetch_webpage(url: str) -> tuple[str, dict]:
    """
    Returns (content_text, meta) where:
      meta = {'type': 'web', 'title': str, 'url': url}
    Uses trafilatura for readable text; falls back to raw HTML on error.
    """
    title = url
    content = ""
    html = None
    try:
        # Friendly UA to avoid basic bot blocks
        r = requests.get(
            url,
            timeout=45,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            },
        )
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return ("", {"type": "web", "title": title, "url": url, "error": f"http_error: {e}"})

    # extract text
    try:
        import trafilatura
        content = trafilatura.extract(html) or ""
    except Exception:
        content = html  # fallback: raw HTML

    # extract title from HTML if possible
    if html:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip() or title

    meta = {"type": "web", "title": title, "url": url}
    return content.strip(), meta

def fetch_pdf(url: str) -> tuple[str, dict]:
    """
    Returns (content_text, meta) where:
      meta = {'type': 'pdf', 'title': str, 'url': url, 'pages': int}
    """
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        return ("", {"type": "pdf", "title": url.split('/')[-1] or 'PDF', "url": url, "error": f"http_error: {e}"})

    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(resp.content))
        texts = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                pass
        content = "\n\n".join(t for t in texts if t).strip()
        title = (getattr(reader, "metadata", None) or {}).get("/Title") or url.split("/")[-1] or "PDF"
        meta = {"type": "pdf", "title": title, "url": url, "pages": len(reader.pages)}
        return content, meta
    except Exception as e:
        return ("", {"type": "pdf", "title": url.split('/')[-1] or 'PDF', "url": url, "error": f"pdf_parse_error: {e}"})

def fetch_youtube(url: str) -> tuple[str, dict]:
    """
    Returns (transcript_text_or_empty, meta) where:
      meta = {'type': 'youtube', 'title': str, 'url': url, 'duration': seconds}
    Tries transcript first; uses yt-dlp for title/duration.
    """
    video_id = _youtube_id(url)
    transcript_text = ""
    title = None
    duration = 0

    # transcript
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        parts = None
        for langs in (['en', 'en-US'], ['en-GB'], None):
            try:
                parts = YouTubeTranscriptApi.get_transcript(video_id, languages=langs) if langs else YouTubeTranscriptApi.get_transcript(video_id)
                if parts:
                    break
            except Exception:
                continue
        if parts:
            transcript_text = " ".join(p.get("text", "") for p in parts if p.get("text"))
    except Exception:
        pass

    # metadata (no download)
    try:
        import yt_dlp
        class _SilentLogger:
            def debug(self, msg):
                pass
            def warning(self, msg):
                pass
            def error(self, msg):
                pass
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "logger": _SilentLogger(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if isinstance(info, dict):
                title = info.get("title") or title
                try:
                    duration = int(info.get("duration") or 0)
                except Exception:
                    duration = 0
    except Exception:
        pass

    if not title:
        title = f"YouTube: {video_id}"

    meta = {"type": "youtube", "title": title, "url": url, "duration": duration}
    return transcript_text.strip(), meta

def _youtube_id(url: str) -> str:
    u = urlparse(url)
    if u.netloc.endswith("youtu.be"):
        return u.path.lstrip("/")
    if "youtube.com" in u.netloc:
        m = re.search(r"[?&]v=([^&]+)", url)
        if m:
            return m.group(1)
        m = re.search(r"/shorts/([^?&/]+)", url)
        if m:
            return m.group(1)
    return u.path.strip("/").split("/")[-1]


