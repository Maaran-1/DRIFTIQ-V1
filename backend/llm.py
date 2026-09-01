"""DRIFTIQ MVP — LLM abstraction.
Swappable LLM providers behind a single call_llm() function that returns JSON.
Supports automatic fallback: if the primary provider fails, the next one in
LLM_FALLBACK_PROVIDERS is tried until one succeeds.
"""
from __future__ import annotations
import json
import logging
import re
import requests
from google import genai
from google.genai import types

import config

log = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from a model response, tolerant of surrounding prose."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Look for a ```json ... ``` block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Look for the first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"Could not extract JSON from response:\n{text[:500]}")


# ---------- Provider implementations ----------

def _ollama(system_prompt: str, user_prompt: str) -> dict:
    """Local Ollama running on your machine. Free, private, no rate limits."""
    url = f"{config.OLLAMA_HOST}/api/chat"
    body = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    r = requests.post(url, json=body, timeout=600)
    r.raise_for_status()
    content = r.json()["message"]["content"]
    return _extract_json(content)


def _gemini(system_prompt: str, user_prompt: str) -> dict:
    """Google Gemini API via official google-genai SDK."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set.")
    # Reject the un-replaced placeholder value only
    if config.GEMINI_API_KEY.startswith("REPLACE_WITH"):
        raise RuntimeError(
            "GEMINI_API_KEY is still the placeholder. "
            "Set a real key (AIzaSy... from AI Studio or AQ... from Cloud Console) in your .env"
        )
    
    # Initialize the client. This correctly handles both AI Studio (AIzaSy) and Cloud (AQ) keys
    # provided they have access to the specified model.
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    
    return _extract_json(response.text)


def _openai(system_prompt: str, user_prompt: str) -> dict:
    """OpenAI (GPT-4o-mini by default). Paid, but cheap for MVP volumes."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set.")
    url = "https://api.openai.com/v1/chat/completions"
    body = {
        "model": config.OPENAI_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    r = requests.post(url, headers=headers, json=body, timeout=300)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return _extract_json(content)


def _claude(system_prompt: str, user_prompt: str) -> dict:
    """Anthropic Claude. High quality, small free credit on new signup."""
    if not config.CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY not set.")
    url = "https://api.anthropic.com/v1/messages"
    body = {
        "model": config.CLAUDE_MODEL,
        "system": system_prompt + "\n\nAlways respond with a single JSON object, no prose.",
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": 4096,
        "temperature": 0.2,
    }
    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    r = requests.post(url, headers=headers, json=body, timeout=300)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason}")
    content = r.json()["content"][0]["text"]
    return _extract_json(content)


def _groq_llm(system_prompt: str, user_prompt: str) -> dict:
    """Groq LLM via OpenAI-compatible API (free tier, very fast).
    Uses the same GROQ_API_KEY as the ASR provider.
    Default model: llama-3.1-8b-instant (fast + free).
    """
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set — cannot use Groq LLM.")
    url = "https://api.groq.com/openai/v1/chat/completions"
    body = {
        "model": config.GROQ_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    r = requests.post(url, headers=headers, json=body, timeout=300)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return _extract_json(content)


_ROUTES = {
    "ollama": _ollama,
    "gemini": _gemini,
    "openai": _openai,
    "claude": _claude,
    "groq":   _groq_llm,
}


# ---------- Public API ----------

def _build_provider_chain() -> list[str]:
    """Build the ordered list of providers to try: primary first, then fallbacks."""
    primary = config.LLM_PROVIDER
    fallbacks_raw = getattr(config, "LLM_FALLBACK_PROVIDERS", "")
    fallbacks = [
        p.strip() for p in fallbacks_raw.split(",") if p.strip() and p.strip() != primary
    ]
    return [primary] + fallbacks


def call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Call the configured LLM with automatic fallback.

    Tries the primary provider (LLM_PROVIDER) first. On any exception,
    falls back through LLM_FALLBACK_PROVIDERS (comma-separated) in order.
    Raises the last exception if all providers fail.
    """
    chain = _build_provider_chain()
    last_error: Exception | None = None

    for provider in chain:
        if provider not in _ROUTES:
            log.warning("Skipping unknown LLM provider %r — not in %s", provider, list(_ROUTES))
            continue
        try:
            if provider != chain[0]:
                log.info("LLM fallback: trying provider %r after previous failure.", provider)
            result = _ROUTES[provider](system_prompt, user_prompt)
            if provider != chain[0]:
                log.info("LLM fallback succeeded with provider %r.", provider)
            return result
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "LLM provider %r failed: %s — %s",
                provider,
                type(exc).__name__,
                exc,
            )
            last_error = exc

    raise RuntimeError(
        f"All LLM providers failed. Chain tried: {chain}. "
        f"Last error: {last_error}"
    ) from last_error
