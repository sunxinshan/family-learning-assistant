"""Minimal production static server with SPA fallback."""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


class SpaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        requested = unquote(urlparse(self.path).path)
        target = Path(self.directory) / requested.lstrip("/")
        if requested != "/" and not target.exists() and "." not in Path(requested).name:
            self.path = "/index.html"
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / "index.html").is_file():
        raise SystemExit(f"missing frontend build: {root / 'index.html'}")
    handler = lambda *a, **kw: SpaHandler(*a, directory=str(root), **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"serving {root} on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
