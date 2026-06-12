"""Ollama backend for the chat GUI.

Thin, dependency-light wrapper around the `ollama` Python client. Everything
here is plain functions that the GUI calls from a worker thread, so nothing in
this module touches Tkinter or blocks the UI directly.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Iterator, List, Optional

import ollama


class OllamaError(Exception):
    """Raised for any failure talking to Ollama, with a user-readable message."""


def _client() -> ollama.Client:
    """Build a client, honouring the OLLAMA_HOST env var if set."""
    host = os.environ.get("OLLAMA_HOST")
    return ollama.Client(host=host) if host else ollama.Client()


def _get(obj: Any, key: str, default=None):
    """Read `key` from an object attribute or a dict, whichever applies."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _model_name(entry: Any) -> Optional[str]:
    """Pull a model name out of one `ollama.list()` entry.

    The client has changed shape across versions: older releases returned
    dicts keyed by ``name``; current releases return pydantic objects exposing
    ``.model``. Handle both so we don't break on an upgrade.
    """
    for attr in ("model", "name"):
        value = _get(entry, attr)
        if value:
            return str(value)
    return None


def is_running() -> bool:
    """Return True if the Ollama server responds."""
    try:
        _client().list()
        return True
    except Exception:
        return False


def _raw_models() -> List[Any]:
    response = _client().list()
    raw = _get(response, "models")
    if raw is None and isinstance(response, dict):
        raw = response.get("models", [])
    return raw or []


def list_models() -> List[str]:
    """Return installed model names, sorted. Empty list if the server is down."""
    try:
        names = [n for n in (_model_name(m) for m in _raw_models()) if n]
        return sorted(set(names))
    except Exception:
        return []


def list_models_detailed() -> List[Dict[str, Any]]:
    """Return [{'name', 'size'}] for installed models, sorted by name."""
    try:
        out = []
        for m in _raw_models():
            name = _model_name(m)
            if name:
                out.append({"name": name, "size": _get(m, "size", 0) or 0})
        return sorted(out, key=lambda d: d["name"])
    except Exception:
        return []


def chat_stream(
    model: str,
    messages: List[Dict[str, str]],
    should_stop: Optional[Callable[[], bool]] = None,
    *,
    options: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Iterator[str]:
    """Stream a chat completion, yielding content chunks as they arrive.

    `messages` is the full conversation so far (a list of
    ``{"role": ..., "content": ...}`` dicts) so the model keeps context.
    `should_stop`, if given, is polled between chunks; when it returns True the
    stream is cut short cleanly. `options` is passed through to Ollama (e.g.
    ``{"temperature": 0.7}``). If `meta` is given, generation stats from the
    final chunk (token counts, durations) are written into it.
    """
    try:
        stream = _client().chat(
            model=model, messages=messages, stream=True, options=options or {}
        )
        for chunk in stream:
            if should_stop is not None and should_stop():
                break
            message = _get(chunk, "message")
            content = _get(message, "content") if message is not None else None
            if content:
                yield content
            if _get(chunk, "done") and meta is not None:
                for key in ("eval_count", "eval_duration",
                            "prompt_eval_count", "total_duration", "load_duration"):
                    meta[key] = _get(chunk, key)
    except ollama.ResponseError as exc:
        message = getattr(exc, "error", None) or str(exc)
        status = getattr(exc, "status_code", None)
        # Only treat this as a missing model when Ollama actually says so (404 /
        # "try pulling"). Other 5xx errors — e.g. a broken install — must surface
        # their real message rather than a misleading "pull it first".
        if status == 404 or "try pulling" in message.lower():
            raise OllamaError(
                f"Model '{model}' isn't installed. Pull it first with:  ollama pull {model}"
            ) from exc
        raise OllamaError(f"Ollama error: {message}") from exc
    except ConnectionError as exc:
        raise OllamaError(
            "Can't reach Ollama. Is the server running?  Start it with:  ollama serve"
        ) from exc
    except Exception as exc:  # network errors, timeouts, etc.
        raise OllamaError(f"Unexpected error talking to Ollama: {exc}") from exc


def pull_model(name: str, on_progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
    """Download a model, reporting progress dicts ({status, completed, total})."""
    try:
        for update in _client().pull(name, stream=True):
            if on_progress is not None:
                on_progress({
                    "status": _get(update, "status", ""),
                    "completed": _get(update, "completed", 0) or 0,
                    "total": _get(update, "total", 0) or 0,
                })
    except ollama.ResponseError as exc:
        raise OllamaError(f"Couldn't pull '{name}': {getattr(exc, 'error', None) or exc}") from exc
    except Exception as exc:
        raise OllamaError(f"Couldn't pull '{name}': {exc}") from exc


def delete_model(name: str) -> None:
    """Remove an installed model."""
    try:
        _client().delete(name)
    except ollama.ResponseError as exc:
        raise OllamaError(f"Couldn't delete '{name}': {getattr(exc, 'error', None) or exc}") from exc
    except Exception as exc:
        raise OllamaError(f"Couldn't delete '{name}': {exc}") from exc


if __name__ == "__main__":
    # Quick smoke test from the command line.
    if not is_running():
        raise SystemExit("Ollama server is not running. Start it with: ollama serve")
    available = list_models()
    print("Installed models:", available or "(none)")
    if not available:
        raise SystemExit("No models installed. Pull one with, e.g.: ollama pull llama3.1:8b")
    target = available[0]
    print(f"\nAsking {target}: 'What is a cow in one sentence?'\n")
    for piece in chat_stream(target, [{"role": "user", "content": "What is a cow in one sentence?"}]):
        print(piece, end="", flush=True)
    print()
