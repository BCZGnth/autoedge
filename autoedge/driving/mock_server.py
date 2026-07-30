"""A tiny local HTTP server that stands in for a real search engine so the
default run mode never makes a live network call. Runs in a daemon thread
inside the same process as the driver.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import mock_content


class _QuietHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # A browser dropping a keep-alive connection mid-request is normal
        # and constant; only surface genuinely unexpected server errors.
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the daemon's console output human-log only

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parts = urlsplit(self.path)
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}

        if parts.path == "/":
            self._send_html(mock_content.render_home())
        elif parts.path == "/search":
            query = params.get("q", "").strip()
            if not query:
                self._send_html("missing query", status=400)
                return
            page = max(1, int(params.get("page", "1") or 1))
            self._send_html(mock_content.render_results(query, page))
        elif parts.path == "/page":
            query = params.get("q", "")
            rid = params.get("rid", "1-0")
            self._send_html(mock_content.render_article(query, rid))
        else:
            self._send_html("not found", status=404)


class MockSearchServer:
    """Binds to an ephemeral local port and serves until `stop()`."""

    def __init__(self, host: str = "127.0.0.1"):
        self._host = host
        self._httpd = _QuietHTTPServer((host, 0), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                         daemon=True)
        self._started = False

    def start(self) -> "MockSearchServer":
        if not self._started:
            self._thread.start()
            self._started = True
        return self

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def url(self, path: str = "/") -> str:
        return f"http://{self._host}:{self.port}{path}"

    def stop(self) -> None:
        if self._started:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._started = False
