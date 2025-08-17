import re, subprocess, json, io
import httpx, trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader

def fetch_webpage(url: str) -> tuple[str, dict]:
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    downloaded = trafilatura.extract(r.text, include_comments=False, url=url) or ""
    title = BeautifulSoup(r.text, "html.parser").title.string if "<title" in r.text.lower() else ""
    meta = {"title": title.strip() if title else url, "type": "article"}
    return downloaded, meta

def fetch_pdf(url: str) -> tuple[str, dict]:
    r = httpx.get(url, timeout=60, follow_redirects=True)
    r.raise_for_status()
    buf = io.BytesIO(r.content)
    reader = PdfReader(buf)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text, {"title": url.rsplit("/",1)[-1], "type": "pdf"}

def fetch_youtube(url: str) -> tuple[str, dict]:
    # 1) transcript
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
        video_id = extract_video_id(url)
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        text = " ".join([x["text"] for x in transcript])
    except Exception:
        text = ""
    # 2) metadata via yt-dlp
    meta_raw = subprocess.check_output(["yt-dlp", "-J", "--", url], text=True)
    meta = json.loads(meta_raw)
    duration = int(meta.get("duration") or 0)
    title = meta.get("title") or url
    return text, {"title": title, "type": "youtube", "duration": duration}

def extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return m.group(1) if m else ""
