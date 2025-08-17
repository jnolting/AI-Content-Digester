# src/scoring.py
"""
Scoring rubric:
- Topic match (0–40)
- Info density (0–25)
- Time efficiency (0–20)
- Credibility (0–15)
Recommendation:
  >=70: Read/Watch
  50–69: Skim
  <50:  Skip
"""

from urllib.parse import urlparse
import json
import math
import os

# Optional: host weights from config/source_weights.json
def _load_host_weights(path="config/source_weights.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {k.lower(): int(v) for k, v in json.load(f).items()}
    except Exception:
        return {}

HOST_WEIGHTS = _load_host_weights()

DEFAULT_WEIGHTS = {
    "topic_match": 40,
    "info_density": 25,
    "time_efficiency": 20,
    "credibility": 15,
}

def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def _bounded(x, lo, hi):
    return max(lo, min(hi, x))

def _topic_match_score(title: str, notes_keywords: list[str] | None) -> int:
    # v1: simple keyword bumps; later you can swap in embeddings
    if not notes_keywords:
        return 20  # neutral middle if no interests specified
    title_l = (title or "").lower()
    hits = sum(1 for kw in notes_keywords if kw.lower() in title_l)
    # 0 hits -> 5, 1 -> 20, 2 -> 30, >=3 -> 40
    return _bounded(5 + hits * 15, 0, 40)

def _info_density_score(word_count: int, has_code_signals: bool) -> int:
    # Reward concise, technical content a bit
    # Heuristic: 600–1500 words good; >3000 likely meandering
    if not word_count:
        base = 15
    elif word_count < 400:
        base = 12
    elif word_count <= 1500:
        base = 22
    elif word_count <= 3000:
        base = 18
    else:
        base = 12
    if has_code_signals:
        base += 3
    return _bounded(base, 0, 25)

def _time_efficiency_score(kind: str, word_count: int, duration_sec: int) -> int:
    # Penalize very long items; prefer value-per-minute
    if kind == "youtube" and duration_sec:
        minutes = max(1, duration_sec // 60)
        # 5–15 min best; >30 decays
        if minutes <= 7:
            return 18
        elif minutes <= 15:
            return 20
        elif minutes <= 30:
            return 14
        else:
            return 8
    # text
    if word_count == 0:
        return 12
    minutes = max(1, word_count // 200)  # ~200 wpm
    if minutes <= 5:
        return 18
    elif minutes <= 12:
        return 20
    elif minutes <= 20:
        return 14
    else:
        return 8

def _credibility_score(url: str) -> int:
    host = _host(url)
    bonus = HOST_WEIGHTS.get(host, 0)  # 0..15 suggested
    return _bounded(bonus, 0, 15)

def recommend_score(kind: str,
                    word_count: int,
                    duration_sec: int,
                    url: str,
                    title: str,
                    interests: list[str] | None = None) -> tuple[int, str, dict]:
    """Return (score, label, breakdown)."""
    has_code = any(tok in (title or "").lower() for tok in ["c#", "dotnet", ".net", "kubernetes", "jwt", "oidc", "rocm", "pytorch", "bambu"])
    s_topic = _topic_match_score(title, interests)
    s_info  = _info_density_score(word_count, has_code)
    s_time  = _time_efficiency_score(kind, word_count, duration_sec)
    s_cred  = _credibility_score(url)

    score = s_topic + s_info + s_time + s_cred
    label = "Read/Watch" if score >= 70 else ("Skim" if score >= 50 else "Skip")

    breakdown = {
        "topic_match": s_topic,
        "info_density": s_info,
        "time_efficiency": s_time,
        "credibility": s_cred,
        "host": _host(url),
    }
    return score, label, breakdown
