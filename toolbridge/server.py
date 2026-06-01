"""HTTP server and request handler."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Settings
from .router import dispatch
from .web_admin import (
    handle_admin_page,
    handle_admin_get_config,
    handle_admin_save_config,
    handle_admin_fetch_models,
    handle_admin_status,
    handle_admin_login,
    handle_admin_check_auth,
    handle_admin_change_password,
)


class BridgeServer(ThreadingHTTPServer):
    """Threading HTTP server that holds application settings."""

    def __init__(self, address: tuple[str, int], handler_cls: type, settings: Settings):
        self.settings = settings
        self._settings_lock = threading.Lock()
        super().__init__(address, handler_cls)

    def hot_reload(self, new_settings: Settings) -> None:
        """Hot-reload configuration without restarting the server."""
        with self._settings_lock:
            self.settings = new_settings
        print(f"[bridge] configuration hot-reloaded (upstream: {new_settings.upstream_url})", flush=True)

    @property
    def current_settings(self) -> Settings:
        with self._settings_lock:
            return self.settings


class BridgeHandler(BaseHTTPRequestHandler):
    """Thin request handler that delegates to the router."""

    server: BridgeServer

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]  # strip query string
        # Admin routes
        if path == "/admin" or path == "/admin/":
            handle_admin_page(self)
        elif path == "/admin/api/config":
            handle_admin_get_config(self, self.server.current_settings)
        elif path == "/admin/api/status":
            handle_admin_status(self, self.server.current_settings)
        elif path == "/admin/api/auth_check":
            handle_admin_check_auth(self, self.server.current_settings)
        else:
            dispatch(self, self.server.current_settings, "GET", self.path, None)

    def do_HEAD(self) -> None:
        dispatch(self, self.server.current_settings, "HEAD", self.path, None)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        # Admin API routes
        if path == "/admin/api/login":
            handle_admin_login(self, self.server.current_settings)
            return
        elif path == "/admin/api/config":
            new_settings = handle_admin_save_config(self, self.server.current_settings)
            if new_settings is not self.server.current_settings:
                self.server.hot_reload(new_settings)
            return
        elif path == "/admin/api/fetch_models":
            handle_admin_fetch_models(self, self.server.current_settings)
            return
        elif path == "/admin/api/change_password":
            new_settings = handle_admin_change_password(self, self.server.current_settings)
            if new_settings is not self.server.current_settings:
                self.server.hot_reload(new_settings)
            return

        # For routed handlers (handle_chat, handle_anthropic), they read body themselves.
        # For passthrough, we read body here and pass it through dispatch.
        clean_path = path.rstrip("/") if path != "/" else path
        from .router import _ROUTE_TABLE
        if (self.command, clean_path) in _ROUTE_TABLE:
            dispatch(self, self.server.current_settings, "POST", self.path, None)
        else:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else None
            dispatch(self, self.server.current_settings, "POST", self.path, body)

    def log_message(self, format: str, *args: Any) -> None:
        # Minimal logging to stdout (flushed for Docker)
        print(f"[bridge] {format % args}", flush=True)


def create_server(settings: Settings) -> BridgeServer:
    """Create and return a BridgeServer instance."""
    return BridgeServer(
        (settings.listen_host, settings.listen_port),
        BridgeHandler,
        settings,
    )


def run_server(settings: Settings) -> None:
    """Create and start the server. Blocks until interrupted."""
    srv = create_server(settings)
    print(f"toolbridge listening on {settings.listen_host}:{settings.listen_port}", flush=True)
    print(f"  upstream: {settings.upstream_url}", flush=True)
    print(f"  admin UI: http://{settings.listen_host}:{settings.listen_port}/admin", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down", flush=True)
        srv.shutdown()


# ---------------------------------------------------------------------------
# Threaded server management (for GUI mode)
# ---------------------------------------------------------------------------

_server_instance: BridgeServer | None = None
_server_thread: threading.Thread | None = None


def start_server_threaded(settings: Settings) -> None:
    """Start the server in a daemon thread. Safe to call from any thread."""
    global _server_instance, _server_thread
    stop_server()
    _server_instance = create_server(settings)
    _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
    _server_thread.start()


def stop_server() -> None:
    """Stop the running server if any."""
    global _server_instance, _server_thread
    if _server_instance is not None:
        _server_instance.shutdown()
        _server_instance.server_close()
        _server_instance = None
    _server_thread = None


def is_server_running() -> bool:
    return _server_instance is not None


def get_server_port() -> int | None:
    if _server_instance is not None:
        return _server_instance.current_settings.listen_port
    return None


def hot_reload_settings(new_settings: Settings) -> None:
    """Hot-reload settings on the running server instance."""
    if _server_instance is not None:
        _server_instance.hot_reload(new_settings)
