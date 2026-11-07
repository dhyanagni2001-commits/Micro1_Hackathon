"""Provider clients over plain HTTP. Retries on 429/5xx and network errors only."""
from __future__ import annotations

import os
import random
import time

import httpx

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_ATTEMPTS = 8
TIMEOUT = httpx.Timeout(900.0, connect=30.0)
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}


class ProviderError(RuntimeError):
    pass


def key_env(cfg: dict) -> str:
    return cfg.get("api_key_env") or KEY_ENV[cfg["provider"]]


def _post(url, headers, body) -> dict:
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
        except httpx.TransportError as exc:
            detail = repr(exc)
        else:
            if response.status_code == 200:
                return response.json()
            detail = f"HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code not in RETRY_STATUS:
                raise ProviderError(detail)
        if attempt == MAX_ATTEMPTS - 1:
            raise ProviderError(detail)
        time.sleep(min(60, 2 ** attempt) + random.random())
    raise AssertionError("unreachable")


def _anthropic(cfg, prompt, temperature):
    body = {"model": cfg["model"], "max_tokens": cfg["max_tokens"],
            "messages": [{"role": "user", "content": prompt}], **cfg.get("params", {})}
    if temperature is not None:
        body["temperature"] = temperature
    headers = {"x-api-key": os.environ[key_env(cfg)], "anthropic-version": "2023-06-01"}
    data = _post("https://api.anthropic.com/v1/messages", headers, body)
    text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
    usage = data.get("usage", {})
    return text, data.get("model"), usage.get("input_tokens"), usage.get("output_tokens")


def _openai(cfg, prompt, temperature):
    base = cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
    body = {"model": cfg["model"], "max_completion_tokens": cfg["max_tokens"],
            "messages": [{"role": "user", "content": prompt}], **cfg.get("params", {})}
    if temperature is not None:
        body["temperature"] = temperature
    headers = {"Authorization": f"Bearer {os.environ[key_env(cfg)]}"}
    data = _post(f"{base}/chat/completions", headers, body)
    usage = data.get("usage", {})
    text = data["choices"][0]["message"].get("content") or ""
    return text, data.get("model"), usage.get("prompt_tokens"), usage.get("completion_tokens")


def _google(cfg, prompt, temperature):
    config = {"maxOutputTokens": cfg["max_tokens"], **cfg.get("params", {})}
    if temperature is not None:
        config["temperature"] = temperature
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config}
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg['model']}:generateContent")
    data = _post(url, {"x-goog-api-key": os.environ[key_env(cfg)]}, body)
    usage = data.get("usageMetadata", {})
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    output = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    return text, data.get("modelVersion"), usage.get("promptTokenCount"), output


PROVIDERS = {"anthropic": _anthropic, "openai": _openai, "google": _google}


def complete(cfg: dict, prompt: str) -> dict:
    """Calls the model once. Falls back to the default temperature when the API rejects 0."""
    call = PROVIDERS[cfg["provider"]]
    temperature = cfg.get("temperature")
    note = None
    started = time.monotonic()
    try:
        result = call(cfg, prompt, temperature)
    except ProviderError as exc:
        if temperature is None or "temperature" not in str(exc).lower():
            raise
        temperature, note = None, "API rejected temperature; used the model default"
        started = time.monotonic()
        result = call(cfg, prompt, None)
    text, model_id, input_tokens, output_tokens = result
    return {"text": text, "model_id_returned": model_id, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "temperature_used": temperature,
            "temperature_note": note, "latency_s": round(time.monotonic() - started, 2)}
