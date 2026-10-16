"""HTTP checks for the local, same-origin browser server."""

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tools import serve
from tests.test_match_board import sample_match_team


MATCH_URL = "https://www.zerozero.pt/jogo/2026-10-10-maritimo-fc-porto/12278041"


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        (root / "index.html").write_text("<h1>Board</h1>", encoding="utf-8")
        (root / "app.js").write_text("window.board = true;", encoding="utf-8")
        handler = serve.create_handler(root)
        handler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _get(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return response.status, response.headers, response.read()

    def _error(self, path):
        with self.assertRaises(HTTPError) as caught:
            self._get(path)
        error = caught.exception
        return error.code, json.loads(error.read())

    def test_serves_web_files_and_rejects_traversal(self):
        status, headers, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"<h1>Board</h1>")
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))
        status, headers, body = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"window.board = true;")
        self.assertIn("javascript", headers["Content-Type"])

        status, payload = self._error("/%2e%2e/secret.txt")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "File not found.")

    def test_match_api_returns_validated_teams(self):
        home = sample_match_team()
        away = sample_match_team()
        away["side"] = "away"
        away["name"] = "Away FC"
        match = {"match_id": 12278041, "teams": [home, away]}
        path = "/api/match?" + urlencode({"url": MATCH_URL})
        with patch.object(serve.match_import, "load_match", return_value=match) as load:
            status, headers, body = self._get(path)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))
        load.assert_called_once_with(MATCH_URL)
        payload = json.loads(body)
        self.assertEqual(set(payload), {"match_id", "teams"})
        self.assertEqual(payload["match_id"], 12278041)
        self.assertEqual([team["id"] for team in payload["teams"]],
                         ["zerozero-12278041-home", "zerozero-12278041-away"])
        self.assertEqual(payload["teams"][0]["starting_ids"], list(range(101, 112)))
        self.assertEqual(payload["teams"][0]["substitutions"],
                         [{"out_id": 106, "in_id": 112, "minute": 63}])
        self.assertEqual(payload["teams"][0]["kits"][0]["colors"][0], [17, 34, 51])

    def test_match_api_rejects_invalid_requests_before_fetch(self):
        invalid = [
            "/api/match",
            "/api/match?" + urlencode({"url": "https://example.com/jogo/x/1"}),
            "/api/match?" + urlencode({"url": MATCH_URL}) + "&url=" + MATCH_URL,
        ]
        with patch.object(serve.match_import, "load_match") as load:
            for path in invalid:
                with self.subTest(path=path):
                    status, payload = self._error(path)
                    self.assertEqual(status, 400)
                    self.assertIn("error", payload)
        load.assert_not_called()

    def test_match_api_reports_fetch_and_lineup_errors(self):
        path = "/api/match?" + urlencode({"url": MATCH_URL})
        with patch.object(serve.match_import, "load_match",
                          side_effect=serve.match_import.MatchImportError("No published lineup.")):
            status, payload = self._error(path)
        self.assertEqual(status, 502)
        self.assertEqual(payload, {"error": "No published lineup."})

        with patch.object(serve.match_import, "load_match",
                          return_value={"match_id": 12278041, "teams": []}):
            status, payload = self._error(path)
        self.assertEqual(status, 422)
        self.assertIn("two complete teams", payload["error"])

    def test_head_does_not_download_match(self):
        request = Request(self.base + "/api/match?" + urlencode({"url": MATCH_URL}),
                          method="HEAD")
        with patch.object(serve.match_import, "load_match") as load:
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 405)
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
