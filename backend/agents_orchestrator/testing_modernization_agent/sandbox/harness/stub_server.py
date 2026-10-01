"""Stub server — stands in for an external service INSIDE the sandbox network (no internet there).

    python stub_server.py <responses.json> <port>

responses.json: {"responses": [{"method", "path", "query"?, "status", "body"}, ...]}. The first entry
whose method, path and (when given) exact query match answers; nothing matching is a 404, so a call
the recording did not foresee shows up as a difference instead of being invented.
"""
import http.server
import json
import sys
import urllib.parse


def main(path, port):
    with open(path, encoding="utf-8") as f:
        responses = json.load(f)["responses"]

    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self):
            url = urllib.parse.urlsplit(self.path)
            for r in responses:
                if r["method"].upper() == self.command and r["path"] == url.path \
                        and ("query" not in r or r["query"] == url.query):
                    return self._send(int(r.get("status", 200)), r.get("body", {}))
            return self._send(404, {"error": "no stub for %s %s" % (self.command, self.path)})

        def _send(self, status, body):
            data = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _answer

        def log_message(self, *args):
            pass

    http.server.ThreadingHTTPServer(("0.0.0.0", int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
