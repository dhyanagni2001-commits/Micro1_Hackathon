"""Provider clients over plain HTTP. Retries on 429/5xx and network errors only."""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import tempfile
import time

import httpx

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_ATTEMPTS = 8
TIMEOUT = httpx.Timeout(900.0, connect=30.0)
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}


class ProviderError(RuntimeError):
    pass


def key_env(cfg: dict):
    """The env var holding this model's key, or None when it needs no key."""
    if cfg["provider"] in CLI_PROVIDERS or cfg.get("api_key_env") == "none":
        return None
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
    env = key_env(cfg)
    headers = {"Authorization": f"Bearer {os.environ[env]}"} if env else {}
    data = _post(f"{base}/chat/completions", headers, body)
    usage = data.get("usage", {})
    text = data["choices"][0]["message"].get("content") or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # local reasoning models
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


CLI_RETRY = re.compile(r"rate.?limit|overloaded|429|5\d\d|timed? ?out|temporar|try again", re.I)
CLI_TIMEOUT_S = 1200
CODEX_TOOL_ITEMS = {"command_execution", "file_change", "mcp_tool_call", "web_search"}


def _run_cli(argv, prompt) -> str:
    """Runs a CLI in an empty directory so the model cannot see this repo."""
    for attempt in range(4):
        with tempfile.TemporaryDirectory() as empty:
            try:
                proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                                      cwd=empty, timeout=CLI_TIMEOUT_S)
                detail = proc.stderr[-500:] + proc.stdout[-500:]
                if proc.returncode == 0:
                    return proc.stdout
            except subprocess.TimeoutExpired:
                detail = "timed out"
        if attempt == 3 or not CLI_RETRY.search(detail):
            raise ProviderError(f"{argv[0]} failed: {detail}")
        time.sleep(30 * (attempt + 1))
    raise AssertionError("unreachable")


def _claude_cli(cfg, prompt, temperature):
    """Claude Code headless on the subscription login: no tools, MCP, settings or session."""
    out = _run_cli(["claude", "-p", "--model", cfg["model"], "--output-format", "json",
                    "--tools", "", "--strict-mcp-config", "--setting-sources", "",
                    "--disable-slash-commands", "--no-session-persistence",
                    *cfg.get("cli_args", [])], prompt)
    data = json.loads(out)
    if data.get("is_error") or data.get("num_turns", 1) != 1:
        raise ProviderError(f"claude returned an error or used tools: {out[-500:]}")
    usage = data.get("usage", {})
    tokens_in = sum(usage.get(k) or 0 for k in
                    ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    model_id = ";".join(data.get("modelUsage", {})) or None
    return data.get("result") or "", model_id, tokens_in, usage.get("output_tokens")


def _codex_cli(cfg, prompt, temperature):
    """Codex headless on the ChatGPT login. A trial where Codex used any tool is rejected."""
    out = _run_cli(["codex", "exec", "--ephemeral", "--skip-git-repo-check",
                    "--sandbox", "read-only", "--json", "-m", cfg["model"],
                    *cfg.get("cli_args", []), "-"], prompt)
    text, usage = "", {}
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item", {})
        if item.get("type") in CODEX_TOOL_ITEMS:
            raise ProviderError(f"codex used a tool ({item['type']}); trial rejected")
        if item.get("type") == "agent_message":
            text = item.get("text", "")
        if event.get("type") == "turn.completed":
            usage = event.get("usage", {})
        if event.get("type") == "turn.failed":
            raise ProviderError(f"codex turn failed: {line[:500]}")
    output = (usage.get("output_tokens") or 0) + (usage.get("reasoning_output_tokens") or 0)
    return text, None, usage.get("input_tokens"), output


CLI_PROVIDERS = {"claude_cli": _claude_cli, "codex_cli": _codex_cli}
PROVIDERS = {"anthropic": _anthropic, "openai": _openai, "google": _google, **CLI_PROVIDERS}


def complete(cfg: dict, prompt: str) -> dict:
    """Calls the model once. Falls back to the default temperature when the API rejects 0."""
    call = PROVIDERS[cfg["provider"]]
    temperature = cfg.get("temperature")
    note = None
    if cfg["provider"] in CLI_PROVIDERS:
        temperature, note = None, "CLI run on a subscription login; temperature cannot be set"
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
