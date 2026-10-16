"""Serve the browser board and import Zerozero matches from Python.

Run ``python tools/serve.py`` and open http://127.0.0.1:8000/.  The browser
uses this same-origin server for match links because Zerozero does not permit
its HTML to be read by a page hosted on another origin.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import parse_qs, unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import match_board  # noqa: E402 - script entry point also needs the project root
import match_import  # noqa: E402


def create_handler(web_root=WEB_ROOT):
    """Build a request handler for a specific static directory.

    Passing a directory also lets tests exercise the HTTP boundary without
    depending on the project's current web build files.
    """
    root = Path(web_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Web directory does not exist: {root}")

    class BoardHandler(BaseHTTPRequestHandler):
        server_version = "TacticalBoard/1.0"

        def do_GET(self):
            self._route(head_only=False)

        def do_HEAD(self):
            self._route(head_only=True)

        def _route(self, *, head_only):
            try:
                target = urlsplit(self.path)
            except ValueError:
                self._json(400, {"error": "Invalid request URL."}, head_only=head_only)
                return
            if target.path == "/api/match":
                if head_only:
                    self._json(405, {"error": "Use GET for match imports."}, head_only=True)
                    return
                self._match(target.query)
            elif target.path.startswith("/api/"):
                self._json(404, {"error": "Unknown API route."}, head_only=head_only)
            else:
                self._static(target.path, head_only=head_only)

        def _json(self, status, payload, *, head_only=False):
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head_only:
                self.wfile.write(encoded)

        def _match(self, query):
            if len(query) > 4096:
                self._json(414, {"error": "Match link is too long."})
                return
            try:
                fields = parse_qs(query, keep_blank_values=True, strict_parsing=True,
                                  max_num_fields=4)
            except ValueError:
                fields = {}
            if set(fields) != {"url"} or len(fields["url"]) != 1:
                self._json(400, {"error": "Provide exactly one Zerozero match URL."})
                return
            try:
                canonical, match_id = match_import.validate_match_url(fields["url"][0])
            except match_import.MatchImportError as exc:
                self._json(400, {"error": str(exc)})
                return

            try:
                match = match_import.load_match(canonical)
                if (not isinstance(match, dict) or match.get("match_id") != match_id
                        or not isinstance(match.get("teams"), list)
                        or [team.get("side") for team in match["teams"]] != ["home", "away"]):
                    raise ValueError("The match did not contain two complete teams.")
                teams = [match_board.build_imported_team(team, match_id)
                         for team in match["teams"]]
            except match_import.MatchImportError as exc:
                self._json(502, {"error": str(exc)})
                return
            except (KeyError, TypeError, ValueError) as exc:
                self._json(422, {"error": f"Could not use the match lineup: {exc}"})
                return
            self._json(200, {"match_id": match_id, "teams": teams})

        def _static(self, url_path, *, head_only):
            try:
                decoded = unquote(url_path, errors="strict")
            except UnicodeDecodeError:
                self._json(400, {"error": "Invalid file path."}, head_only=head_only)
                return
            if decoded == "/":
                decoded = "/index.html"
            parts = decoded.removeprefix("/").split("/")
            if (not decoded.startswith("/") or any(
                    not part or part in {".", ".."} or ":" in part or "\\" in part
                    or "\x00" in part for part in parts)):
                self._json(404, {"error": "File not found."}, head_only=head_only)
                return
            file_path = root.joinpath(*parts).resolve()
            if not file_path.is_relative_to(root) or not file_path.is_file():
                self._json(404, {"error": "File not found."}, head_only=head_only)
                return
            try:
                with file_path.open("rb") as source:
                    length = file_path.stat().st_size
                    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                    if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
                        mime += "; charset=utf-8"
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(length))
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    if not head_only:
                        shutil.copyfileobj(source, self.wfile)
            except OSError:
                # A file can disappear between the path check and the open.
                self._json(404, {"error": "File not found."}, head_only=head_only)

    return BoardHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve the tactical board")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "8000"),
                        help="listen port (default: PORT environment variable or 8000)")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    server = ThreadingHTTPServer((args.host, args.port), create_handler())
    print(f"Tactical board: http://{args.host}:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
