"""Claude access shared by Ask (Layer 2) and text signals (Layer 3 text) (owner: P2).

Two backends, same call (`complete_json`):
  * api -> Anthropic Messages API when ANTHROPIC_API_KEY is set (.env or environment);
  * cli -> the logged-in Claude Code CLI (`claude -p`, headless, no tools, JSON-schema output) otherwise.
  Force one with ONTRACK_LLM_BACKEND=api|cli. Model: ONTRACK_LLM_MODEL (api default claude-opus-5-5; cli default
  the 'opus' alias).
* Disk cache: final results are stored under $ONTRACK_WORK_DIR/llm_cache keyed by a hash of the request, so
  re-running the benchmark is repeatable and free. Bump the caller's PROMPT_VERSION to invalidate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ontrack import config

CACHE_DIR = config.WORK_DIR / "llm_cache"


def _api_key() -> str:
    return config.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")


def _cli_path() -> str | None:
    return shutil.which("claude") or next(
        (str(p) for p in [Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"]
         if p.exists()), None)


def backend() -> str | None:
    forced = os.environ.get("ONTRACK_LLM_BACKEND", "").lower()
    if forced in ("api", "cli"):
        return forced
    if _api_key():
        return "api"
    return "cli" if _cli_path() else None


def available() -> bool:
    return backend() is not None


MODEL = os.environ.get("ONTRACK_LLM_MODEL") or ("claude-opus-5-5" if backend() == "api" else "opus")


def client():
    import anthropic
    return anthropic.Anthropic(api_key=_api_key() or None, max_retries=4)


def complete_json(system: str, prompt: str, schema: dict, model: str | None = None, effort: str = "medium",
                  timeout: int = 600) -> dict:
    """One call that must return a JSON object matching `schema`."""
    model = model or MODEL
    if backend() == "api":
        resp = client().messages.create(
            model=model, max_tokens=16000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("model refused the request")
        return json.loads(text_of(resp))
    exe = _cli_path()
    if not exe:
        raise RuntimeError("no LLM backend: set ANTHROPIC_API_KEY or install and log in to Claude Code")
    tmp = config.WORK_DIR / "tmp"
    tmp.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", dir=tmp, delete=False, encoding="utf-8") as f:
        f.write(system)          # Windows caps command lines at ~32k chars: the system prompt goes in a file
        sys_file = f.name
    try:
        p = subprocess.run(
            [exe, "-p", "--output-format", "json", "--model", model, "--tools", "", "--no-session-persistence",
             "--system-prompt-file", sys_file, "--json-schema", json.dumps(schema)],
            input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
    finally:
        os.unlink(sys_file)
    if p.returncode != 0 and not p.stdout.strip():
        raise RuntimeError(f"claude CLI failed ({p.returncode}): {p.stderr.strip()[:300]}")
    out = json.loads(p.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude CLI error: {str(out.get('result'))[:300]}")
    if isinstance(out.get("structured_output"), dict):
        return out["structured_output"]
    return json.loads(out.get("result") or "{}")


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
