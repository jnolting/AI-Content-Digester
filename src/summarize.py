import os, math
import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # or local model name for Ollama
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-05-01-preview")

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
        "model": OPENAI_MODEL,
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }

    # Endpoint path rules:
    # - OpenAI-compatible: ensure we call .../v1/chat/completions
    # - Azure OpenAI:   .../openai/deployments/{model}/chat/completions?api-version=...
    if is_azure:
        endpoint = f"openai/deployments/{OPENAI_MODEL}/chat/completions?api-version={OPENAI_API_VERSION}"
    else:
        if base.endswith("/v1"):
            endpoint = "chat/completions"
        else:
            endpoint = "v1/chat/completions"

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
