import os, math, time, random, json
import httpx

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    return v

OPENAI_API_KEY = _env("OPENAI_API_KEY", "")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")  # OpenAI default; for Azure see below
OPENAI_API_VERSION = _env("OPENAI_API_VERSION", "2024-05-01-preview")

def _is_azure(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "azure" in u or "openai.azure.com" in u

def chat_complete(system, user, max_tokens=1200):
    base = (OPENAI_BASE_URL or "").rstrip("/")
    is_azure = _is_azure(base)

    # Headers differ between providers
    if is_azure:
        headers = {"api-key": OPENAI_API_KEY, "Content-Type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    payload = {
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }

    # Endpoint path rules:
    # - OpenAI-compatible: ensure we call .../v1/chat/completions
    # - Azure OpenAI:   .../openai/deployments/{model}/chat/completions?api-version=...
    if is_azure:
        deployment = _env("AZURE_OPENAI_DEPLOYMENT", OPENAI_MODEL)
        if not deployment:
            raise ValueError("Azure OpenAI base URL configured but no AZURE_OPENAI_DEPLOYMENT/OPENAI_MODEL provided")
        endpoint = f"openai/deployments/{deployment}/chat/completions?api-version={OPENAI_API_VERSION}"
    else:
        if base.endswith("/v1"):
            endpoint = "chat/completions"
        else:
            endpoint = "v1/chat/completions"
        # For OpenAI-compatible APIs, ensure model is present; coalesce fallback
        model = OPENAI_MODEL or "gpt-4o-mini"
        payload["model"] = model

    max_retries = 4
    base_delay = 1.5
    with httpx.Client(base_url=base, headers=headers, timeout=120) as c:
        for attempt in range(max_retries + 1):
            r = None
            try:
                r = c.post(endpoint, json=payload)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as e:
                if attempt >= max_retries:
                    raise
                sleep_s = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(sleep_s)
                continue
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else None
                body_text = None
                try:
                    body_text = e.response.text if e.response is not None else None
                except Exception:
                    body_text = None

                # Try to parse error JSON for quota hint
                err_code = None
                try:
                    j = e.response.json()
                    err_code = ((j or {}).get("error") or {}).get("code")
                except Exception:
                    pass

                # If insufficient_quota, don't retry
                if err_code == "insufficient_quota":
                    raise httpx.HTTPStatusError(f"{e} — body: {body_text}", request=e.request, response=e.response)

                # Retry 429/5xx with backoff and Retry-After if present
                if status in (429,) or (status is not None and 500 <= status <= 599):
                    if attempt >= max_retries:
                        raise httpx.HTTPStatusError(f"{e} — body: {body_text}", request=e.request, response=e.response)
                    retry_after = None
                    try:
                        ra = e.response.headers.get("Retry-After") if e.response else None
                        retry_after = float(ra) if ra else None
                    except Exception:
                        retry_after = None
                    sleep_s = retry_after if retry_after is not None else (base_delay * (2 ** attempt) + random.uniform(0, 0.5))
                    time.sleep(sleep_s)
                    continue

                # Other status: raise with body for context
                raise httpx.HTTPStatusError(f"{e} — body: {body_text}", request=e.request, response=e.response)
