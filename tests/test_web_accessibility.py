"""Desktop fallback and browser bridge contract for native controls."""

import json
import platform
import unittest
from unittest.mock import patch

import web_accessibility


class FakeWindow:
    def __init__(self):
        self.scripts = []
        self.queue_result = "[]"

    def eval(self, script):
        self.scripts.append(script)
        if script == "JSON.stringify(window.boardCommands.splice(0))":
            return self.queue_result
        return True


class WebAccessibilityTests(unittest.TestCase):
    def test_desktop_does_not_create_browser_controls(self):
        with patch.object(web_accessibility.sys, "platform", "win32"):
            self.assertIsNone(web_accessibility.create_panel())

    def test_browser_panel_sends_serialized_state_only_when_it_changes(self):
        window = FakeWindow()
        with patch.object(web_accessibility.sys, "platform", "emscripten"):
            with patch.object(platform, "window", window, create=True):
                panel = web_accessibility.create_panel()

        self.assertIsInstance(panel, web_accessibility.WebAccessibilityPanel)
        self.assertIn("window.boardCommands", window.scripts[0])
        state = {"teams": [{"id": "porto", "name": "FC Porto"}], "mode": "move"}
        panel.update(state)
        panel.update(state)
        self.assertEqual(len(window.scripts), 2)
        prefix = "window.__tacticalBoardAccessibility.update("
        self.assertTrue(window.scripts[1].startswith(prefix))
        self.assertEqual(json.loads(window.scripts[1][len(prefix) : -1]), state)

        state["mode"] = "ball"
        panel.update(state)
        self.assertEqual(len(window.scripts), 3)

    def test_browser_commands_are_drained_in_order_and_invalid_data_is_rejected(self):
        window = FakeWindow()
        panel = web_accessibility.WebAccessibilityPanel(window)
        expected = [
            {"type": "set_mode", "mode": "arrow"},
            {"type": "move_player", "side": "A", "slot": 3, "x_m": 42.5, "y_m": 28},
            {"type": "add_arrow", "start": [20, 34], "end": [40, 34]},
            {"type": "place_ball", "point": [52.5, 34]},
        ]
        window.queue_result = json.dumps(expected)
        self.assertEqual(panel.drain_commands(), expected)
        window.queue_result = '[{"type":"set_mode"},null]'
        with self.assertRaises(ValueError):
            panel.drain_commands()


if __name__ == "__main__":
    unittest.main()
