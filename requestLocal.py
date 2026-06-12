"""Ollama backend for the chat GUI.

Thin, dependency-light wrapper around the `ollama` Python client. Everything
here is plain functions that the GUI calls from a worker thread, so nothing in
this module touches Tkinter or blocks the UI directly.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional

import ollama

# A small set of common models to fall back on when we can't reach the server
# to ask what's actually installed.
DEFAULT_MODELS: List[str] = ["llama3.1:8b", "llama3:8b", "llama2", "qwen2.5-coder:7b"]


class OllamaError(Exception):
    """Raised for any failure talking to Ollama, with a user-readable message."""


def _client() -> ollama.Client:
    """Build a client, honouring the OLLAMA_HOST env var if set."""
    host = os.environ.get("OLLAMA_HOST")
    return ollama.Client(host=host) if host else ollama.Client()


def _model_name(entry: Any) -> Optional[str]:
    """Pull a model name out of one `ollama.list()` entry.

    The client has changed shape across versions: older releases returned
    dicts keyed by ``name``; current releases return pydantic objects exposing
    ``.model``. Handle both so we don't break on an upgrade.
    """
    for attr in ("model", "name"):
        value = getattr(entry, attr, None)
        if value:
            return str(value)
    if isinstance(entry, dict):
        return entry.get("model") or entry.get("name")
    return None


def is_running() -> bool:
    """Return True if the Ollama server responds."""
    try:
        _client().list()
        return True
    except Exception:
        return False


def list_models() -> List[str]:
    """Return installed model names, sorted. Empty list if the server is down."""
    try:
        response = _client().list()
    except Exception:
        return []

    raw = getattr(response, "models", None)
    if raw is None and isinstance(response, dict):
        raw = response.get("models", [])
    names = [name for name in (_model_name(m) for m in (raw or [])) if name]
    return sorted(set(names))


def chat_stream(
    model: str,
    messages: List[Dict[str, str]],
    should_stop=None,
) -> Iterator[str]:
    """Stream a chat completion, yielding content chunks as they arrive.

    `messages` is the full conversation so far (a list of
    ``{"role": ..., "content": ...}`` dicts) so the model keeps context.
    `should_stop`, if given, is a zero-arg callable polled between chunks;
    when it returns True the stream is cut short cleanly.
    """
    try:
        stream = _client().chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            if should_stop is not None and should_stop():
                break
            content = chunk.get("message", {}).get("content") if isinstance(chunk, dict) else chunk.message.content
            if content:
                yield content
    except ollama.ResponseError as exc:
        message = getattr(exc, "error", None) or str(exc)
        if "not found" in message.lower() or "try pulling" in message.lower():
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


if __name__ == "__main__":
    # Quick smoke test from the command line.
    if not is_running():
        raise SystemExit("Ollama server is not running. Start it with: ollama serve")
    available = list_models()
    print("Installed models:", available or "(none)")
    target = available[0] if available else DEFAULT_MODELS[0]
    print(f"\nAsking {target}: 'What is a cow in one sentence?'\n")
    for piece in chat_stream(target, [{"role": "user", "content": "What is a cow in one sentence?"}]):
        print(piece, end="", flush=True)
    print()
