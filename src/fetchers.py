import os
import re
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

GITHUB_API = "https://api.github.com"

def _extract_urls(text: str) -> list[str]:
    if not text:
        return []
    # basic URL grabber
    urls = re.findall(r'https?://\S+', text, flags=re.IGNORECASE)
    # strip trailing punctuation
    clean = [u.rstrip(').,;\'"') for u in urls]
    return clean

def _infer_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if host.endswith(".pdf") or url.lower().endswith(".pdf"):
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

    # Issues updated since midnight UTC
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
        # Skip pull requests (issues API returns PRs too)
        if "pull_request" in issue:
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
