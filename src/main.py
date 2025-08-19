import os, re, math, datetime, pathlib, json
from src.fetchers import fetch_webpage, fetch_pdf, fetch_youtube, _extract_urls
from src.summarize import chat_complete
from src.scoring import recommend_score

def load_prompt(path): return pathlib.Path(path).read_text(encoding="utf-8")

def get_inbox_issues():
    # GitHub provides GITHUB_REPOSITORY + token; list open issues with label 'inbox'
    import httpx
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{repo}/issues?state=open&labels=inbox"
    r = httpx.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return [i for i in r.json() if "pull_request" not in i]

def close_issue(number, comment):
    import httpx
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    httpx.post(f"https://api.github.com/repos/{repo}/issues/{number}/comments",
               headers=headers, json={"body": comment})
    httpx.patch(f"https://api.github.com/repos/{repo}/issues/{number}",
                headers=headers, json={"state":"closed"})

def extract_url(issue):
    # Prefer shared URL parsing across title + body
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    urls = _extract_urls(f"{title}\n{body}")
    return urls[0] if urls else None

def fetch(url):
    if url.lower().endswith(".pdf"):
        return fetch_pdf(url)
    if "youtube.com" in url or "youtu.be" in url:
        return fetch_youtube(url)
    return fetch_webpage(url)

def trim_for_context(text, max_chars=12000):
    if len(text) <= max_chars: return text
    # keep intro + most dense middle chunk
    head, tail = text[:4000], text[-3000:]
    mid = text[4000:-3000]
    return head + "\n[...snip...]\n" + mid[:4000] + "\n[...snip...]\n" + tail

def main():
    system = load_prompt("prompts/summarize_system.txt")
    today = datetime.date.today().isoformat()
    out_path = pathlib.Path(f"reports/{today}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    issues = get_inbox_issues()
    sections = []
    for issue in issues:
        url = extract_url(issue)
        if not url: continue
        content, meta = fetch(url)
        wc = len(content.split())
        dur = int(meta.get("duration") or 0)
        user_prompt = load_prompt("prompts/summarize_user.txt").format(
            title=meta.get("title") or url,
            kind=meta.get("type"),
            url=url,
            duration_human=(f"{dur//60}m{dur%60:02d}s" if dur else "n/a"),
            word_count=wc if wc else "n/a",
            content=trim_for_context(content),
        )
        try:
            summary = chat_complete(system, user_prompt, max_tokens=1100)
        except Exception as e:
            summary = f"_Summary failed: {e}_"

        # BEFORE:
        # score, label = recommend_score(meta.get("type"), wc, dur, meta.get("title"))

        # AFTER:
        score, label, breakdown = recommend_score(
            meta.get("type"),
            wc,
            dur,
            url,
            meta.get("title") or url,
            interests=[".net", "duende", "oidc", "kubernetes", "rocm", "pytorch", "bambu"]  # tweak to your interests
        )
        sections.append(
            f"## {meta.get('title')}\n**URL:** {url}\n**Recommendation:** {label} (score {score})\n"
            f"<sub>Scoring: {breakdown}</sub>\n\n{summary}\n"
        )
        close_issue(issue["number"], f"Processed in {today} daily report. Recommendation: **{label}** (score {score}).")

    if not sections:
        sections.append("_No new links today._")

    report = f"# Daily Content Report — {today}\n\n" + "\n---\n\n".join(sections)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")

if __name__ == "__main__":
    main()
