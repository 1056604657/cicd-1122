"""Minimal Python HTTP service used by the demo pipeline."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def greet(name: str) -> str:
    """Return a greeting message."""
    if not name.strip():
        return "Hello, world"
    return f"Hello, {name}"


class Handler(BaseHTTPRequestHandler):
    """Serves /healthz and /greet for readiness and smoke checks."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._respond(200, "ok")
            return
        if parsed.path == "/greet":
            name = parse_qs(parsed.query).get("name", ["world"])[0]
            self._respond(200, greet(name))
            return
        self._respond(404, "not found")

    def _respond(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main() -> None:
    """Entry point."""
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"python-api listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
