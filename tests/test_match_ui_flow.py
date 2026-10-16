"""Headless, event-driven match import through the real board controls."""

import asyncio
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import main
from tests.test_match_board import sample_match_team


MATCH_URL = "https://www.zerozero.pt/jogo/2026-10-10-maritimo-fc-porto/12278041"


def parsed_match():
    home = sample_match_team()
    away = copy.deepcopy(home)
    home["name"] = "Home FC"
    away["side"] = "away"
    away["name"] = "Away FC"
    for player in [*away["players"], *away["bench"]]:
        player["id"] += 100
    for change in away["substitutions"]:
        change["out_id"] += 100
        change["in_id"] += 100
    return {"source_url": MATCH_URL, "match_id": 12278041, "teams": [home, away]}


class MatchUIFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_url_import_then_badge_click_switches_player(self):
        original_layout = main.LAYOUT
        main.LAYOUT = main.Layout(1300, 780)
        created_sides = []
        tools_modals = []
        url_modals = []
        real_team_side = main.TeamSide
        real_tools_modal = main.build_tools_modal
        real_url_modal = main.MatchURLModal

        def track_side(*args, **kwargs):
            side = real_team_side(*args, **kwargs)
            created_sides.append(side)
            return side

        def track_tools():
            modal = real_tools_modal()
            tools_modals.append(modal)
            return modal

        def track_url(*args, **kwargs):
            modal = real_url_modal(*args, **kwargs)
            url_modals.append(modal)
            return modal

        deadline = asyncio.get_running_loop().time() + 5

        async def until(predicate):
            while asyncio.get_running_loop().time() < deadline:
                if predicate():
                    return
                if board_task.done():
                    await board_task
                    self.fail("Board closed before completing the import flow")
                await asyncio.sleep(0.01)
            self.fail("Timed out waiting for the board UI")

        def click(pos):
            for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                pygame.event.post(pygame.event.Event(kind, {"button": 1, "pos": pos}))

        board_task = None
        try:
            with (
                patch.object(main, "setup_accessibility", return_value=None),
                patch.object(main.web_accessibility, "create_panel", return_value=None),
                patch.object(main.match_import, "load_match", return_value=parsed_match()) as fetch,
                patch.object(main, "TeamSide", side_effect=track_side),
                patch.object(main, "build_tools_modal", side_effect=track_tools),
                patch.object(main, "MatchURLModal", side_effect=track_url),
            ):
                board_task = asyncio.create_task(main.main())
                await until(lambda: len(created_sides) == 2)
                pygame.event.clear()

                tools_button = next(
                    button for button in main.build_buttons(*created_sides)
                    if button.action["kind"] == "open_tools_modal"
                )
                click(tools_button.rect.center)
                await until(lambda: bool(tools_modals))

                tools_modal = tools_modals[-1]
                match_row = next(index for index, (_, value) in enumerate(tools_modal.options)
                                 if value == "load_match")
                click(tools_modal._row_rect_for_index(match_row).center)
                await until(lambda: bool(url_modals))

                url_modal = url_modals[-1]
                for index in range(0, len(MATCH_URL), 20):
                    pygame.event.post(pygame.event.Event(
                        pygame.TEXTINPUT, {"text": MATCH_URL[index:index + 20]}))
                await until(lambda: url_modal.text == MATCH_URL)
                click(url_modal.submit_rect.center)
                await until(lambda: len(created_sides) == 4)
                fetch.assert_called_once_with(MATCH_URL)

                home, away = created_sides[-2:]
                self.assertEqual(home.team["name"], "Home FC")
                self.assertEqual(away.team["name"], "Away FC")
                self.assertEqual(len(home.players), 11)
                self.assertEqual(len(away.players), 11)

                outgoing = next(player for player in home.players
                                if player.switch_pair is not None)
                self.assertEqual(outgoing.player_id, 106)
                badge = outgoing.switch_badge_rect()
                self.assertIsNotNone(badge)
                click(badge.center)
                await until(lambda: outgoing.switch_active)
                self.assertEqual(outgoing.player_id, 112)
                self.assertEqual(outgoing.name, "Substitute 12")
                self.assertEqual(outgoing.number, 12)
        finally:
            if board_task is not None and not board_task.done():
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                await asyncio.wait_for(board_task, timeout=3)
            main.LAYOUT = original_layout


if __name__ == "__main__":
    unittest.main()
