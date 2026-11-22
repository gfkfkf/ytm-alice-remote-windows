#!/usr/bin/env python3
"""Mock ytm-alice web panel for testing the Android remote without a Station.

Serves the real web assets from a ytm-alice checkout and answers the small
JSON API the panel needs (/api/info, /api/state, /api/command).

    python tools/mock-panel.py --web path/to/ytm-alice/source/web

The panel is then available at http://127.0.0.1:24721. From an Android
emulator use http://10.0.2.2:24721.
"""

import argparse
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TRACKS = [
    {
        "id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "artists": "Rick Astley",
        "duration_ms": 213000,
        "thumbnail_url": "",
    },
    {
        "id": "5NV6Rdv1a3I",
        "title": "Get Lucky",
        "artists": "Daft Punk",
        "duration_ms": 369000,
        "thumbnail_url": "",
    },
]

STATE = {
    "version": "0.7.6",
    "status": "paused",
    "queue": list(TRACKS),
    "index": 0,
    "position_ms": 42000,
    "announce": True,
    "shuffle": False,
    "logged_in": False,
    "auth": {
        "configured": False,
        "checked": False,
        "valid": False,
        "expired": False,
        "method": "cookies",
        "account": None,
        "cookies": False,
    },
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ytm-alice-mock/1.0"
    web_dir = "."

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        path = urllib.parse.unquote(path)
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(self.web_dir, path.lstrip("/")))
        if not full.startswith(os.path.normpath(self.web_dir)) or not os.path.isfile(full):
            self.send_error(404)
            return
        ctype, _ = mimetypes.guess_type(full)
        if full.endswith(".js") or full.endswith(".mjs"):
            ctype = "text/javascript"
        elif full.endswith(".svg"):
            ctype = "image/svg+xml"
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", (ctype or "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/info":
            self._json({"version": STATE["version"]})
        elif path == "/api/state":
            self._json({"state": STATE})
        else:
            self._static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/command":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json({"error": "bad json"}, 400)
            return
        action = body.get("action")
        if action == "search":
            self._json({"tracks": TRACKS, "state": STATE})
        elif action == "liked":
            self._json({"tracks": TRACKS})
        elif action == "playlists":
            self._json({"playlists": []})
        elif action in ("jump", "select"):
            index = max(0, int(body.get("index", 1)) - 1)
            if index < len(STATE["queue"]):
                STATE["index"] = index
                STATE["position_ms"] = 0
                STATE["status"] = "playing"
            self._json({"state": STATE})
        elif action in ("pause", "stop"):
            STATE["status"] = "paused" if action == "pause" else "stopped"
            self._json({"state": STATE})
        elif action == "resume":
            STATE["status"] = "playing"
            self._json({"state": STATE})
        elif action in ("next", "previous"):
            if action == "next":
                STATE["index"] = min(len(STATE["queue"]) - 1, STATE["index"] + 1)
            else:
                STATE["index"] = max(0, STATE["index"] - 1)
            STATE["position_ms"] = 0
            self._json({"state": STATE})
        else:
            self._json({"state": STATE, "ok": True})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default=os.environ.get("YTM_WEB_DIR", "."),
                        help="path to ytm-alice/source/web")
    parser.add_argument("--port", type=int, default=24721)
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()
    Handler.web_dir = os.path.abspath(args.web)
    if not os.path.isfile(os.path.join(Handler.web_dir, "index.html")):
        raise SystemExit("index.html not found in %s" % Handler.web_dir)
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print("Mock panel: http://127.0.0.1:%d (assets: %s)" % (args.port, Handler.web_dir))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
