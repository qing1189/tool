"""Entry point for ``python -m toolbridge``."""

from __future__ import annotations

import os
import sys

# Force unbuffered stdout/stderr for Docker logging
os.environ.setdefault("PYTHONUNBUFFERED", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

from .config import Settings
from .server import run_server


def main() -> None:
    if "--desktop" in sys.argv or _should_launch_gui():
        sys.argv = [a for a in sys.argv if a != "--desktop"]
        from .desktop import TrayApp
        settings = _load_settings_for_desktop()
        TrayApp(settings).run()
    else:
        settings = _load_settings()
        run_server(settings)


def _should_launch_gui() -> bool:
    """Detect no-console launch (pythonw.exe or macOS .app bundle)."""
    if sys.platform == "win32":
        return sys.executable.lower().endswith("pythonw.exe")
    return False


def _load_settings() -> Settings:
    """Load from config file first, fall back to environment.

    This allows the web admin to persist config changes that survive restarts.
    """
    from .config_file import load_config

    file_cfg = load_config()
    if file_cfg:
        print("[bridge] loaded configuration from config file")
        return Settings.from_dict(file_cfg)
    print("[bridge] using environment variables for configuration")
    return Settings.from_environment()


def _load_settings_for_desktop() -> Settings:
    """Load from config file first, fall back to environment."""
    from .config_file import load_config

    file_cfg = load_config()
    if file_cfg:
        return Settings.from_dict(file_cfg)
    return Settings.from_environment()


if __name__ == "__main__":
    main()
