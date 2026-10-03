"""Claude client shared by Ask (Layer 2) and text signals (Layer 3 text) (owner: P2).

* Model from $ONTRACK_LLM_MODEL (default claude-opus-5); key from config.ANTHROPIC_API_KEY or the SDK's
  usual credential chain.
* Disk cache: every final result is stored under $ONTRACK_WORK_DIR/llm_cache keyed by a hash of the request, so
  re-running the benchmark is repeatable and free. Bump PROMPT_VERSION in the caller to invalidate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import anthropic

from ontrack import config

MODEL = os.environ.get("ONTRACK_LLM_MODEL", "claude-opus-5")
CACHE_DIR = config.WORK_DIR / "llm_cache"


def client() -> anthropic.Anthropic:
    if config.ANTHROPIC_API_KEY:
        return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=4)
    return anthropic.Anthropic(max_retries=4)


def available() -> bool:
    """True when some credential is configured (key in .env / env, or an auth token)."""
    return bool(config.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def cache_key(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def cache_get(namespace: str, key: str):
    path = CACHE_DIR / namespace / f"{key}.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def cache_put(namespace: str, key: str, value) -> None:
    path: Path = CACHE_DIR / namespace / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1, default=str)
    tmp.replace(path)


def text_of(message) -> str:
    return "".join(b.text for b in message.content if b.type == "text")
