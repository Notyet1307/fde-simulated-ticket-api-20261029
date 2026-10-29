"""Read-only synthetic ticket list; no external data or services."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

TICKETS = json.loads(Path(__file__).with_name("tickets.json").read_text())

def list_tickets(*, owner=None, status=None, page=1, page_size=2):
    if status not in (None, "open", "closed"):
        raise ValueError("status must be open or closed")
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("invalid page or page_size")
    def matches(ticket):
        return (owner is None or ticket["owner"] == owner) and (status is None or ticket["status"] == status)
    ordered = sorted(TICKETS, key=lambda ticket: ticket["id"])
    start = (page - 1) * page_size
    rows = [ticket for ticket in ordered if matches(ticket)]
    return {"items": rows[start:start + page_size], "total": len(rows), "page": page, "page_size": page_size}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/tickets":
            self.reply(404, {"error": "not found"})
            return
        try:
            query = parse_qs(url.query, keep_blank_values=True)
            if set(query) - {"owner", "status", "page", "page_size"} or any(len(v) != 1 for v in query.values()):
                raise ValueError("unknown or repeated parameter")
            args = {key: value[0] for key, value in query.items()}
            for key in ("page", "page_size"):
                if key in args:
                    if not args[key].isascii() or not args[key].isdecimal():
                        raise ValueError("invalid page or page_size")
                    args[key] = int(args[key])
            self.reply(200, list_tickets(**args))
        except ValueError as error:
            self.reply(400, {"error": str(error)})

    def reply(self, code, value):
        data = json.dumps(value, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
