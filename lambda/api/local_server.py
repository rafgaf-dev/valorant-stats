import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


SUMMARY = {
    "player": {"id": "neon-main", "displayName": "The Neon Menace", "agent": "Neon"},
    "metrics": {
        "kda": {
            "recent": 1.42,
            "lifetime": 1.18,
            "recentKills": 156,
            "recentDeaths": 110,
            "recentAssists": 74,
            "lifetimeKills": 1842,
            "lifetimeDeaths": 1561,
            "lifetimeAssists": 903,
            "recentSampleSize": 15,
            "lifetimeSampleSize": 312,
        },
        "winRate": {"recent": 0.6, "lifetime": 0.51, "recentSampleSize": 15, "lifetimeSampleSize": 312},
        "headshotPercentage": {"recent": 0.23, "lifetime": 0.19, "recentSampleSize": 15, "lifetimeSampleSize": 312},
    },
    "lastUpdatedAt": "2026-09-15T12:00:00Z",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, {"status": "ok"})
        elif path == "/v1/players/neon-main/summary":
            self._send(200, SUMMARY)
        else:
            self._send(404, {"error": "not_found"})

    def log_message(self, format, *args):
        print("[local-api] " + format % args)


if __name__ == "__main__":
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Local API running at http://{host}:{port}")
    server.serve_forever()