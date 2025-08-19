import os, math
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

    with httpx.Client(base_url=base, headers=headers, timeout=120) as c:
        r = c.post(endpoint, json=payload)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # include response body to aid troubleshooting
            detail = None
            try:
                detail = r.text
            except Exception:
                pass
            raise httpx.HTTPStatusError(f"{e} — body: {detail}", request=e.request, response=e.response)
        return r.json()["choices"][0]["message"]["content"]
