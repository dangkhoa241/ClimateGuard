"""Local dev server: serves the API Lambda handler on http://localhost:8787.

Uses local storage and NOTIFY_MODE=dryrun (sign-ups/alerts go to backend/.local/outbox.jsonl).
Usage: python scripts/local_api.py
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import _path  # noqa: F401

from climateguard.handlers.api import handler

PORT = 8787
ROUTES = [  # (method, regex, routeKey)
    ("GET", r"^/cities$", "GET /cities"),
    ("GET", r"^/cities/(?P<city>[a-z]+)$", "GET /cities/{city}"),
    ("GET", r"^/cities/(?P<city>[a-z]+)/alerts$", "GET /cities/{city}/alerts"),
    ("POST", r"^/subscribe$", "POST /subscribe"),
]
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, headers, body):
        self.send_response(status)
        for k, v in {**CORS, **headers}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self):
        self._send(204, {}, "")

    def _dispatch(self, method):
        path = self.path.split("?")[0]
        for m, pattern, route in ROUTES:
            match = re.match(pattern, path)
            if m == method and match:
                length = int(self.headers.get("Content-Length") or 0)
                event = {"routeKey": route, "pathParameters": match.groupdict(),
                         "body": self.rfile.read(length).decode("utf-8") if length else None,
                         "requestContext": {"http": {"sourceIp": self.client_address[0]}}}
                r = handler(event, None)
                return self._send(r["statusCode"], r["headers"], r["body"])
        self._send(404, {"Content-Type": "application/json"}, json.dumps({"error": "not found"}))

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


if __name__ == "__main__":
    print(f"ClimateGuard local API on http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
