"""Web administration API for managing toolbridge configuration."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

from .config import Settings
from .config_file import load_config, save_config


# ---------------------------------------------------------------------------
# Session / Token management
# ---------------------------------------------------------------------------

# Active tokens: token_str -> expiry_timestamp
_active_tokens: dict[str, float] = {}
_TOKEN_TTL = 86400  # 24 hours


def _generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_hex(32)


def _verify_password(provided: str, expected: str) -> bool:
    """Constant-time password comparison."""
    if not expected:
        return True  # No password set = open access
    return hmac.compare_digest(provided.encode(), expected.encode())


def _create_session_token(password: str, settings: Settings) -> str | None:
    """Verify password and create a session token."""
    if not _verify_password(password, settings.admin_password):
        return None
    token = _generate_token()
    _active_tokens[token] = time.time() + _TOKEN_TTL
    # Clean expired tokens
    _cleanup_tokens()
    return token


def _cleanup_tokens() -> None:
    """Remove expired tokens."""
    now = time.time()
    expired = [t for t, exp in _active_tokens.items() if exp < now]
    for t in expired:
        del _active_tokens[t]


def _verify_token(token: str) -> bool:
    """Verify a session token is valid and not expired."""
    if token not in _active_tokens:
        return False
    if time.time() > _active_tokens[token]:
        del _active_tokens[token]
        return False
    return True


def check_admin_auth(handler: Any, settings: Settings) -> bool:
    """Check if the request is authenticated for admin access.

    Returns True if auth passes. If auth fails, sends 401 and returns False.
    If no password is set, always returns True (open access).
    """
    # No password configured = open access
    if not settings.admin_password:
        return True

    # Check Authorization header: "Bearer <token>"
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if _verify_token(token):
            return True

    # Not authenticated
    _send_json(handler, 401, {"error": "unauthorized", "need_login": True})
    return False


def normalize_auth_header(value: str) -> str:
    """Normalize auth header: if only a key is provided, prepend 'Bearer '."""
    value = value.strip()
    if not value:
        return ""
    # If it already has a scheme prefix like "Bearer ", "Basic ", etc. keep it
    if " " in value:
        return value
    # Only a key — auto-prepend Bearer
    return f"Bearer {value}"


def fetch_upstream_models(base_url: str, auth_header: str, timeout: int = 30) -> list[dict]:
    """Fetch model list from upstream /v1/models endpoint."""
    url = base_url.rstrip("/") + "/v1/models"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Content-Type", "application/json")
    if auth_header:
        req.add_header("Authorization", auth_header)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return []


def get_current_config(settings: Settings) -> dict:
    """Export current settings as a JSON-serializable dict."""
    return settings.to_dict()


def apply_config(data: dict, settings: Settings) -> Settings:
    """Apply new configuration, normalize auth, save to disk, return new Settings."""
    # Normalize auth header
    if "UPSTREAM_AUTH_HEADER" in data:
        data["UPSTREAM_AUTH_HEADER"] = normalize_auth_header(data["UPSTREAM_AUTH_HEADER"])

    # Ensure types
    if "PORT" in data:
        data["PORT"] = int(data["PORT"])
    if "UPSTREAM_TIMEOUT_SECONDS" in data:
        data["UPSTREAM_TIMEOUT_SECONDS"] = int(data["UPSTREAM_TIMEOUT_SECONDS"])
    if "FC_ERROR_RETRY_MAX_ATTEMPTS" in data:
        data["FC_ERROR_RETRY_MAX_ATTEMPTS"] = int(data["FC_ERROR_RETRY_MAX_ATTEMPTS"])
    if "RETRY_DELAY_SECONDS" in data:
        data["RETRY_DELAY_SECONDS"] = float(data["RETRY_DELAY_SECONDS"])

    # Boolean fields
    for key in ("ALLOW_UNMAPPED_MODEL_PASSTHROUGH", "FC_ERROR_RETRY"):
        if key in data:
            if isinstance(data[key], str):
                data[key] = data[key].lower() in ("true", "1", "yes", "on")

    # Save to disk (automatically excludes ADMIN_PASSWORD, PORT, HOST)
    save_config(data)

    # Preserve non-persisted fields from current settings for hot-reload
    data.setdefault("HOST", settings.listen_host)
    data.setdefault("PORT", settings.listen_port)
    data.setdefault("ADMIN_PASSWORD", settings.admin_password)

    # Return new Settings instance
    return Settings.from_dict(data)
    return Settings.from_dict(data)


# ---------------------------------------------------------------------------
# Admin route handlers
# ---------------------------------------------------------------------------

def handle_admin_page(handler: Any) -> None:
    """Serve the admin HTML page (always serve — auth is checked by JS)."""
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    html_path = os.path.join(static_dir, "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        body = content.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except FileNotFoundError:
        body = b"Admin page not found"
        handler.send_response(404)
        handler.send_header("Content-Type", "text/plain")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


def handle_admin_login(handler: Any, settings: Settings) -> None:
    """POST /admin/api/login — authenticate and return a session token."""
    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        _send_json(handler, 400, {"error": "empty body"})
        return

    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _send_json(handler, 400, {"error": "invalid JSON"})
        return

    password = data.get("password", "")
    token = _create_session_token(password, settings)
    if token:
        _send_json(handler, 200, {"ok": True, "token": token})
    else:
        _send_json(handler, 403, {"ok": False, "error": "密码错误"})


def handle_admin_check_auth(handler: Any, settings: Settings) -> None:
    """GET /admin/api/auth_check — check if password is required and token validity."""
    # No password = no auth needed
    if not settings.admin_password:
        _send_json(handler, 200, {"need_login": False, "authenticated": True})
        return

    # Check token
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if _verify_token(token):
            _send_json(handler, 200, {"need_login": True, "authenticated": True})
            return

    _send_json(handler, 200, {"need_login": True, "authenticated": False})


def handle_admin_change_password(handler: Any, settings: Settings) -> Settings:
    """POST /admin/api/change_password — change admin password."""
    if not check_admin_auth(handler, settings):
        return settings

    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        _send_json(handler, 400, {"error": "empty body"})
        return settings

    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _send_json(handler, 400, {"error": "invalid JSON"})
        return settings

    new_password = data.get("new_password", "").strip()
    # Update config
    cfg = get_current_config(settings)
    cfg["ADMIN_PASSWORD"] = new_password
    save_config(cfg)
    new_settings = Settings.from_dict(cfg)

    # Invalidate all existing tokens if password changed
    _active_tokens.clear()

    _send_json(handler, 200, {"ok": True, "message": "密码已更新，请重新登录"})
    return new_settings


def handle_admin_get_config(handler: Any, settings: Settings) -> None:
    """GET /admin/api/config — return current config."""
    if not check_admin_auth(handler, settings):
        return
    data = get_current_config(settings)
    # Don't expose the password in the config response
    data.pop("ADMIN_PASSWORD", None)
    _send_json(handler, 200, data)


def handle_admin_save_config(handler: Any, settings: Settings) -> Settings:
    """POST /admin/api/config — save config and return new Settings for hot-reload."""
    if not check_admin_auth(handler, settings):
        return settings

    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        _send_json(handler, 400, {"error": "empty body"})
        return settings

    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _send_json(handler, 400, {"error": "invalid JSON"})
        return settings

    if not isinstance(data, dict):
        _send_json(handler, 400, {"error": "expected JSON object"})
        return settings

    # Preserve existing password if not explicitly changed
    if "ADMIN_PASSWORD" not in data:
        data["ADMIN_PASSWORD"] = settings.admin_password

    new_settings = apply_config(data, settings)
    _send_json(handler, 200, {"ok": True, "message": "Configuration saved and applied"})
    return new_settings


def handle_admin_fetch_models(handler: Any, settings: Settings) -> None:
    """POST /admin/api/fetch_models — fetch models from upstream (or custom URL)."""
    if not check_admin_auth(handler, settings):
        return

    length = int(handler.headers.get("Content-Length", 0))
    data = {}
    if length:
        raw = handler.rfile.read(length)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

    base_url = data.get("base_url", settings.upstream_url)
    auth = data.get("auth_header", settings.upstream_auth)
    # Normalize auth for the fetch
    auth = normalize_auth_header(auth)
    timeout = data.get("timeout", 30)

    models = fetch_upstream_models(base_url, auth, timeout)
    if models:
        model_ids = [m.get("id", "") for m in models if m.get("id")]
        _send_json(handler, 200, {"ok": True, "models": model_ids, "raw": models})
    else:
        _send_json(handler, 200, {"ok": False, "models": [], "error": "Failed to fetch models from upstream"})


def handle_admin_status(handler: Any, settings: Settings) -> None:
    """GET /admin/api/status — return server status (no auth required for basic status)."""
    _send_json(handler, 200, {
        "running": True,
        "port": settings.listen_port,
        "upstream": settings.upstream_url,
        "model_count": len(settings.get_exposed_models()),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_json(handler: Any, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
