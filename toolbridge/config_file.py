"""Persistent JSON configuration file.

Config file location (in priority order):
1. DATA_DIR environment variable (e.g. /app/data)
2. ~/.toolbridge/

Excluded from persistence (always from env/startup):
- ADMIN_PASSWORD
- PORT
- HOST
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# Allow overriding config directory via environment variable
# Docker: DATA_DIR=/app/data  ->  /app/data/config.json
_DATA_DIR_ENV = os.environ.get("DATA_DIR", "").strip()
if _DATA_DIR_ENV:
    CONFIG_DIR = Path(_DATA_DIR_ENV)
else:
    CONFIG_DIR = Path.home() / ".toolbridge"

CONFIG_PATH = CONFIG_DIR / "config.json"

# Fields that should NOT be persisted (always come from env/startup)
_EXCLUDE_FROM_PERSIST = {"ADMIN_PASSWORD", "PORT", "HOST"}


def load_config() -> dict | None:
    """Load configuration from disk. Returns None if file doesn't exist."""
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def save_config(data: dict) -> None:
    """Atomically write configuration to disk.

    Excluded fields (ADMIN_PASSWORD, PORT, HOST) are stripped before saving.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Strip excluded fields before persisting
    persist_data = {k: v for k, v in data.items() if k not in _EXCLUDE_FROM_PERSIST}

    payload = json.dumps(persist_data, indent=2, ensure_ascii=False)
    # Atomic write: write to temp file, then rename
    fd, tmp = tempfile.mkstemp(dir=str(CONFIG_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(CONFIG_PATH))
        print(f"[config] saved to {CONFIG_PATH}", flush=True)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
