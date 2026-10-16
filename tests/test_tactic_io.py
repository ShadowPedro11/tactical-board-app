"""Contract tests for desktop files and pygbag's browser storage bridge."""

import json
import tempfile
import unittest
import webbrowser
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame

import tactic_io

TEST_DIR = Path(__file__).parent


class FakeStorage:
    def __init__(self):
        self.values = {}

    def setItem(self, key, value):
        self.values[key] = value

    def getItem(self, key):
        return self.values.get(key)


class TacticIOTests(unittest.TestCase):
    def setUp(self):
        self.state = {"version": 1, "team": "Benfica", "label": "Tática ágil"}

    def test_desktop_save_load_and_exports(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            with patch.object(tactic_io, "_is_web", return_value=False):
                with patch.object(tactic_io, "_desktop_path", side_effect=lambda name: Path(directory) / name):
                    save_path = tactic_io.save_state(self.state)
                    self.assertEqual(tactic_io.load_state(), self.state)
                    self.assertIn("Tática ágil", Path(save_path).read_text(encoding="utf-8"))

                    json_path = tactic_io.export_json(self.state)
                    self.assertEqual(Path(json_path).name, "tactic-export.json")
                    self.assertTrue(Path(json_path).is_file())

                    png_path = tactic_io.export_png(pygame.Surface((8, 8)))
                    self.assertEqual(Path(png_path).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_load_rejects_invalid_json_version_and_oversize_file(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / tactic_io.SAVE_FILENAME
            with patch.object(tactic_io, "_is_web", return_value=False):
                with patch.object(tactic_io, "_desktop_path", return_value=path):
                    for text in ("{", "[]", '{"version": 2}', '{"version": 1, "x": NaN}'):
                        with self.subTest(text=text):
                            path.write_text(text, encoding="utf-8")
                            with self.assertRaises(ValueError):
                                tactic_io.load_state()
                    path.write_text("x" * (tactic_io.MAX_JSON_BYTES + 1), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "1 MB"):
                        tactic_io.load_state()

    def test_browser_storage_and_downloads(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            storage = FakeStorage()
            downloads = []
            window = SimpleNamespace(
                localStorage=storage,
                MM=SimpleNamespace(download=downloads.append),
            )
            with patch.object(tactic_io, "_is_web", return_value=True):
                with patch.object(tactic_io, "_web_window", return_value=window):
                    with patch.object(tactic_io, "WEB_EXPORT_DIR", Path(directory)):
                        self.assertEqual(tactic_io.save_state(self.state), "armazenamento local do navegador")
                        self.assertEqual(tactic_io.load_state(), self.state)
                        self.assertTrue(storage.values[tactic_io.STORAGE_KEY].isascii())
                        self.assertEqual(tactic_io.export_json(self.state), "tactic-export.json")
                        self.assertEqual(tactic_io.export_png(pygame.Surface((8, 8))), "tactic.png")

            self.assertEqual([Path(path).name for path in downloads], ["tactic-export.json", "tactic.png"])
            self.assertTrue(all(Path(path).is_file() for path in downloads))

    def test_browser_bridge_keeps_accented_benfica_player_names(self):
        class MojibakeBridge(FakeStorage):
            def setItem(self, key, value):
                # Mimic a bridge that mishandles raw UTF-8 as Latin-1.
                self.values[key] = value.encode("utf-8").decode("latin-1")

        state = {
            "version": 1,
            "sides": [{"team_id": "benfica", "players": [
                {"name": "Amar Dedić", "number": 17},
                {"name": "António Silva", "number": 4},
                {"name": "João Veloso", "number": 68},
            ]}],
        }
        storage = MojibakeBridge()
        window = SimpleNamespace(localStorage=storage)
        with patch.object(tactic_io, "_is_web", return_value=True):
            with patch.object(tactic_io, "_web_window", return_value=window):
                tactic_io.save_state(state)
                self.assertEqual(tactic_io.load_state(), state)
        self.assertTrue(storage.values[tactic_io.STORAGE_KEY].isascii())

    def test_browser_download_uses_data_url_when_runtime_download_fails(self):
        class Anchor:
            def __init__(self):
                self.clicked = False
                self.removed = False

            def click(self):
                self.clicked = True

            def remove(self):
                self.removed = True

        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / "tactic-export.json"
            path.write_text('{"version":1}', encoding="utf-8")
            anchor = Anchor()
            body = SimpleNamespace(appendChild=lambda element: None)
            document = SimpleNamespace(createElement=lambda tag: anchor, body=body)
            window = SimpleNamespace(
                MM=SimpleNamespace(download=lambda path: (_ for _ in ()).throw(RuntimeError("unavailable"))),
                document=document,
            )
            with patch.object(tactic_io, "_web_window", return_value=window):
                tactic_io._download(path, "application/json;charset=utf-8")

        self.assertTrue(anchor.clicked)
        self.assertTrue(anchor.removed)
        self.assertEqual(anchor.download, "tactic-export.json")
        self.assertEqual(base64.b64decode(anchor.href.split(",", 1)[1]), b'{"version":1}')

    def test_missing_browser_save_has_clear_error(self):
        window = SimpleNamespace(localStorage=FakeStorage())
        with patch.object(tactic_io, "_is_web", return_value=True):
            with patch.object(tactic_io, "_web_window", return_value=window):
                with self.assertRaisesRegex(FileNotFoundError, "Ainda não existe"):
                    tactic_io.load_state()

    def test_import_json_file_uses_desktop_file_picker_and_validation(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / "shared-tactic.json"
            path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
            results = []
            with patch.object(tactic_io, "_is_web", return_value=False):
                with patch("tkinter.filedialog.askopenfilename", return_value=str(path)):
                    tactic_io.import_json_file(lambda state, error: results.append((state, error)))
            self.assertEqual(results, [(self.state, None)])

            path.write_text('{"version": 2}', encoding="utf-8")
            with patch.object(tactic_io, "_is_web", return_value=False):
                with patch.object(tactic_io, "_desktop_import_path", return_value=path):
                    tactic_io.import_json_file(lambda state, error: results.append((state, error)))
            self.assertIsNone(results[-1][0])
            self.assertIsInstance(results[-1][1], ValueError)

    def test_import_json_file_uses_browser_upload_event_once(self):
        results = []
        picker_callbacks = []
        setup_scripts = []
        window = SimpleNamespace(eval=setup_scripts.append)
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            upload = Path(directory) / "upload-1"
            upload.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
            with patch.object(tactic_io, "_is_web", return_value=True):
                with patch.object(tactic_io, "_web_window", return_value=window):
                    with patch.object(tactic_io, "_upload_handler_registered", False):
                        with patch.object(tactic_io, "_pending_import_callback", None):
                            with patch.object(webbrowser, "open_file", side_effect=lambda handler=None: picker_callbacks.append(handler), create=True):
                                tactic_io.import_json_file(lambda state, error: results.append((state, error)))
                                picker_callbacks[0](SimpleNamespace(text=str(upload), size=upload.stat().st_size))
                                upload.write_text('{"version": 2}', encoding="utf-8")
                                tactic_io.import_json_file(lambda state, error: results.append((state, error)))
                                picker_callbacks[0](SimpleNamespace(text=str(upload), size=upload.stat().st_size))

        self.assertEqual(results[0], (self.state, None))
        self.assertIsNone(results[1][0])
        self.assertIsInstance(results[1][1], ValueError)
        self.assertEqual(len(picker_callbacks), 2)
        self.assertIsNone(picker_callbacks[1])
        self.assertTrue(all("transfer_uploads" in script for script in setup_scripts))
        self.assertTrue(all(".json,application/json" in script for script in setup_scripts))


if __name__ == "__main__":
    unittest.main()
