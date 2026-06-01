"""Upstream HTTP client — connection management and request helpers."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import urllib.error
import http.client
from typing import Any

from .config import Settings
from .errors import UpstreamError


def _log(msg: str) -> None:
    """Print a debug log message (flushed immediately for Docker)."""
    print(f"[proxy] {msg}", flush=True)


def _parse_url(url: str) -> tuple[str, int, str]:
    """Parse an upstream URL into (host, port, base_path)."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    base = parsed.path.rstrip("/")
    return host, port, base


def open_upstream_connection(settings: Settings) -> http.client.HTTPConnection:
    """Open a connection to the upstream API."""
    host, port, _ = _parse_url(settings.upstream_url)
    parsed = urllib.parse.urlparse(settings.upstream_url)
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=settings.upstream_timeout)
    return http.client.HTTPConnection(host, port, timeout=settings.upstream_timeout)


def build_upstream_headers(request_headers: dict | None, settings: Settings) -> dict[str, str]:
    """Construct headers for an upstream request."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if settings.upstream_auth:
        headers["Authorization"] = settings.upstream_auth
    return headers


def fetch_upstream(
    method: str,
    path: str,
    body: bytes | None,
    settings: Settings,
) -> tuple[int, bytes, dict[str, str]]:
    """Make a non-streaming request to the upstream API.

    Returns (status_code, response_body, response_headers).
    """
    url = settings.upstream_url.rstrip("/") + path
    _log(f"{method} {url} (timeout={settings.upstream_timeout}s, body={len(body) if body else 0} bytes)")
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in build_upstream_headers(None, settings).items():
        req.add_header(k, v)

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=settings.upstream_timeout) as resp:
            resp_body = resp.read()
            elapsed = time.time() - start
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            _log(f"  <- {resp.status} ({len(resp_body)} bytes, {elapsed:.2f}s)")
            return resp.status, resp_body, hdrs
    except urllib.error.HTTPError as exc:
        elapsed = time.time() - start
        err_body = exc.read() if exc.fp else b""
        _log(f"  <- HTTP {exc.code} error ({len(err_body)} bytes, {elapsed:.2f}s)")
        raise UpstreamError(exc.code, err_body) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        elapsed = time.time() - start
        _log(f"  <- FAILED: {exc} ({elapsed:.2f}s)")
        raise UpstreamError(502, json.dumps({"error": f"upstream connection failed: {exc}"}).encode()) from exc


def fetch_upstream_chat(payload: dict, settings: Settings) -> dict:
    """Send a Chat Completions request and return the parsed JSON response."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, resp_body, _ = fetch_upstream("POST", "/v1/chat/completions", body, settings)
    try:
        return json.loads(resp_body)
    except (json.JSONDecodeError, ValueError):
        return {"error": f"upstream returned invalid JSON (status {status})"}


def stream_upstream_chat(payload: dict, settings: Settings) -> http.client.HTTPResponse:
    """Open a streaming connection to the upstream and return the raw response
    for the caller to read SSE chunks from."""
    conn = open_upstream_connection(settings)
    _, _, base = _parse_url(settings.upstream_url)
    path = base + "/v1/chat/completions"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = build_upstream_headers(None, settings)
    _log(f"STREAM POST {settings.upstream_url.rstrip('/')}{path} (timeout={settings.upstream_timeout}s)")
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        # Set read timeout on the socket to prevent infinite blocking on readline()
        sock = resp.fp.raw._sock if hasattr(resp, 'fp') and hasattr(resp.fp, 'raw') and hasattr(resp.fp.raw, '_sock') else None
        if sock:
            sock.settimeout(settings.upstream_timeout)
        _log(f"  <- stream opened, status={resp.status}")
        return resp
    except (OSError, TimeoutError) as exc:
        _log(f"  <- STREAM FAILED: {exc}")
        raise UpstreamError(502, json.dumps({"error": f"upstream connection failed: {exc}"}).encode()) from exc
