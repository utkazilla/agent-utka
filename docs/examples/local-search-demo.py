"""Minimal local retrieval adapter for the fictional Orbit tutorial."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class SearchHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/search":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64 * 1024:
                raise ValueError
            request = json.loads(self.rfile.read(length))
            query = request["query"].casefold()
        except (ValueError, TypeError, KeyError, AttributeError):
            self.send_error(400, "Expected a JSON search request")
            return
        hits = [{"path": ".copilot-knowledge/imports/orbit-knowledge.md", "line": 7}] if "retry" in query else []
        body = json.dumps({"hits": hits}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8090), SearchHandler) as server:
        print("Orbit demo search API: http://127.0.0.1:8090/search", flush=True)
        server.serve_forever()
