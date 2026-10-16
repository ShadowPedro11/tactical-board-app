"""Exercise the actual Pygame event loop without opening a visible window."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import main
from teams_data import TEAMS


class BoardEventTests(unittest.TestCase):
    def setUp(self):
        self.accessibility = patch.object(main, "setup_accessibility", return_value=None)
        self.accessibility.start()
        self.board = main.main()
        self.board.send(None)
        pygame.event.clear()
        self.player_pos = tuple(round(p) for p in main.TeamSide("A", TEAMS[0], 1).players[0].pos_px)

    def tearDown(self):
        try:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            self.board.send(None)
            with self.assertRaises(StopIteration):
                self.board.send(None)
        finally:
            self.board.close()
            self.accessibility.stop()

    def post_mouse(self, kind, pos):
        data = {"pos": pos}
        if kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            data["button"] = 1
        pygame.event.post(pygame.event.Event(kind, data))

    def test_plain_left_click_opens_player_picker(self):
        with patch.object(main, "build_player_modal", wraps=main.build_player_modal) as picker:
            self.post_mouse(pygame.MOUSEBUTTONDOWN, self.player_pos)
            self.post_mouse(pygame.MOUSEBUTTONUP, self.player_pos)
            self.board.send(None)

        picker.assert_called_once()
        self.assertEqual(picker.call_args.args[1].name, TEAMS[0]["squad"][0]["name"])

    def test_motion_below_drag_threshold_does_not_move_player(self):
        slightly_moved = (self.player_pos[0] + 1, self.player_pos[1] + 1)
        with patch.object(main.Player, "set_pos_from_px", autospec=True) as move:
            with patch.object(main, "build_player_modal", wraps=main.build_player_modal) as picker:
                self.post_mouse(pygame.MOUSEBUTTONDOWN, self.player_pos)
                self.post_mouse(pygame.MOUSEMOTION, slightly_moved)
                self.post_mouse(pygame.MOUSEBUTTONUP, slightly_moved)
                self.board.send(None)

        move.assert_not_called()
        picker.assert_called_once()

    def test_undo_restores_ball_after_dragging_from_its_current_position(self):
        sides = (main.TeamSide("A", TEAMS[0], 1), main.TeamSide("B", TEAMS[1], -1))
        tools_button = next(button for button in main.build_buttons(*sides)
                            if button.action["kind"] == "open_tools_modal")
        self.post_mouse(pygame.MOUSEBUTTONDOWN, tools_button.rect.center)
        self.post_mouse(pygame.MOUSEBUTTONUP, tools_button.rect.center)
        for key in (pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0}))
        self.board.send(None)

        start = tuple(round(v) for v in main.LAYOUT.m_to_px(50, 34))
        end = tuple(round(v) for v in main.LAYOUT.m_to_px(60, 34))
        self.post_mouse(pygame.MOUSEBUTTONDOWN, start)
        self.post_mouse(pygame.MOUSEBUTTONUP, start)
        self.board.send(None)
        self.post_mouse(pygame.MOUSEBUTTONDOWN, start)
        self.post_mouse(pygame.MOUSEMOTION, end)
        self.post_mouse(pygame.MOUSEBUTTONUP, end)
        self.board.send(None)

        pygame.event.post(pygame.event.Event(
            pygame.KEYDOWN, {"key": pygame.K_z, "mod": pygame.KMOD_CTRL}))
        with patch.object(main, "draw_annotations", wraps=main.draw_annotations) as draw:
            self.board.send(None)

        ball = draw.call_args.args[2]
        self.assertIsNotNone(ball)
        self.assertEqual(ball, main.px_to_m(start))


if __name__ == "__main__":
    unittest.main()
