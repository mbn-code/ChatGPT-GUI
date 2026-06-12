"""Persistence for the chat GUI: conversations and settings on disk.

State lives in a per-user data directory so chats and preferences survive
restarts. Everything is plain JSON; writes are atomic (write-temp-then-rename)
so a crash mid-save can't corrupt the store.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

APP_DIR_NAME = "local-llm-chat"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_model": "",
    "system_prompt": "",
    "temperature": 0.7,
    "geometry": "1040x720",
}


def data_dir() -> Path:
    """Return (creating if needed) the directory where state is stored."""
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        root = Path(base)
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path.home() / ".local" / "share"
    path = root / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _conversations_path() -> Path:
    return data_dir() / "conversations.json"


def _settings_path() -> Path:
    return data_dir() / "settings.json"


def _atomic_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_settings() -> Dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    try:
        with open(_settings_path(), encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            merged.update({k: stored[k] for k in stored if k in DEFAULT_SETTINGS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return merged


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        _atomic_write(_settings_path(), settings)
    except OSError:
        pass  # persistence is best-effort; never crash the app over it


def load_conversations() -> List[Dict[str, Any]]:
    """Return the stored conversations, or [] if none / unreadable."""
    try:
        with open(_conversations_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return [c for c in data if isinstance(c, dict) and "messages" in c]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def save_conversations(conversations: List[Dict[str, Any]]) -> None:
    try:
        _atomic_write(_conversations_path(), conversations)
    except OSError:
        pass
