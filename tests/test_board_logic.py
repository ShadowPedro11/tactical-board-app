"""Regression checks for the board's layout and editable tactic state."""

import copy
import json
import os
import unittest
from collections import Counter
from itertools import combinations

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import main
from formations import FORMATIONS
from teams_data import TEAMS


def identity(player):
    return player.name, player.number, player.position


class BoardLayoutTests(unittest.TestCase):
    def test_phone_buttons_do_not_overlap_or_leave_the_control_panel(self):
        previous_layout = main.LAYOUT
        try:
            main.LAYOUT = main.Layout(360, 480)
            left = main.TeamSide("A", TEAMS[0], 1)
            right = main.TeamSide("B", TEAMS[1], -1)
            buttons = main.build_buttons(left, right)

            self.assertEqual(len(buttons), 8)
            for button in buttons:
                with self.subTest(action=button.action["kind"]):
                    self.assertGreaterEqual(button.rect.left, 0)
                    self.assertGreaterEqual(button.rect.top, 0)
                    self.assertLessEqual(button.rect.right, main.LAYOUT.window_w)
                    self.assertLessEqual(button.rect.bottom, main.LAYOUT.top_panel_h)
            for first, second in combinations(buttons, 2):
                with self.subTest(first=first.base_text, second=second.base_text):
                    self.assertFalse(first.rect.colliderect(second.rect))
        finally:
            main.LAYOUT = previous_layout


class LineupTests(unittest.TestCase):
    def test_every_club_starts_with_eleven_distinct_players_in_every_formation(self):
        self.assertEqual(len(TEAMS), 18)
        self.assertTrue(FORMATIONS)
        for team in TEAMS:
            valid = {(p["name"], p["number"], p["position"]) for p in team["squad"]}
            for formation in FORMATIONS:
                for label, direction in (("A", 1), ("B", -1)):
                    with self.subTest(team=team["id"], formation=formation, side=label):
                        side = main.TeamSide(label, team, direction)
                        side.formation_name = formation
                        side.build_players_from_squad()

                        self.assertEqual(len(side.players), 11)
                        self.assertEqual(len({p.number for p in side.players}), 11)
                        self.assertTrue(all(identity(p) in valid for p in side.players))
                        self.assertTrue(side.players[0].is_gk)
                        self.assertTrue(all(not p.is_gk for p in side.players[1:]))
                        self.assertEqual(
                            Counter(p.position for p in side.players[1:]),
                            Counter(side.formation_position_counts()),
                        )

    def test_formation_change_preserves_people_and_their_position_adjustments(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                side = main.TeamSide("A" if direction == 1 else "B", TEAMS[0], direction)
                # Replace a starter so retaining the original default eleven
                # would not be enough to pass this check.
                starter = side.players[2]
                used_numbers = {p.number for p in side.players}
                replacement = next(
                    p for p in side.team["squad"]
                    if p["position"] == starter.position and p["number"] not in used_numbers
                )
                starter.name = replacement["name"]
                starter.number = replacement["number"]
                starter.position = replacement["position"]

                for player in side.players:
                    player.x_m += -0.75 if direction == -1 else 0.75
                    player.y_m += 0.5
                before = {
                    id(player): (identity(player), player.x_m - player.home_m[0], player.y_m - player.home_m[1])
                    for player in side.players
                }

                side.apply_formation("4-2-3-1")

                self.assertEqual({id(p) for p in side.players}, set(before))
                self.assertEqual(side.formation_name, "4-2-3-1")
                for player in side.players:
                    with self.subTest(direction=direction, player=player.name):
                        person, dx, dy = before[id(player)]
                        self.assertEqual(identity(player), person)
                        self.assertAlmostEqual(player.x_m - player.home_m[0], dx)
                        self.assertAlmostEqual(player.y_m - player.home_m[1], dy)

    def test_player_picker_excludes_players_already_on_the_pitch(self):
        side = main.TeamSide("A", TEAMS[0], 1)
        selected = side.players[1]
        options = main.build_player_modal(side, selected).options
        available_numbers = {person["number"] for _, person in options}
        occupied_numbers = {p.number for p in side.players if p is not selected}
        self.assertTrue(options)
        self.assertFalse(available_numbers & occupied_numbers)
        self.assertTrue(all(person["position"] != "GK" for _, person in options))


class TacticStateTests(unittest.TestCase):
    def setUp(self):
        self.left = main.TeamSide("A", TEAMS[0], 1)
        self.right = main.TeamSide("B", TEAMS[1], -1)

    def test_json_roundtrip_preserves_teams_lineups_positions_and_annotations(self):
        self.left.kit_index = 1
        self.right.apply_formation("4-3-3")
        selected = self.left.players[1]
        used_numbers = {p.number for p in self.left.players}
        substitute = next(
            p for p in self.left.team["squad"]
            if p["position"] == selected.position and p["number"] not in used_numbers
        )
        selected.name, selected.number, selected.position = (
            substitute["name"], substitute["number"], substitute["position"]
        )
        self.left.players[1].x_m += 2.5
        self.right.players[4].y_m -= 1.25
        arrows = [((12.5, 20.0), (29.0, 32.0)), ((90.0, 44.0), (77.5, 20.0))]
        ball = (52.5, 34.0)
        state = main.tactic_state(self.left, self.right, arrows, ball)

        decoded = json.loads(json.dumps(state, ensure_ascii=False))
        left, right, restored_arrows, restored_ball = main.restore_tactic(decoded)

        self.assertEqual(main.tactic_state(left, right, restored_arrows, restored_ball), state)
        self.assertIsNot(left, self.left)
        self.assertIsNot(right, self.right)
        self.assertEqual(left.team["id"], self.left.team["id"])
        self.assertEqual(right.formation_name, "4-3-3")
        self.assertEqual(left.kit_index, 1)

    def test_restore_rejects_duplicate_player_in_a_team(self):
        state = main.tactic_state(self.left, self.right, [], None)
        duplicate = copy.deepcopy(state)
        duplicate["sides"][0]["players"][2] = copy.deepcopy(duplicate["sides"][0]["players"][1])

        with self.assertRaisesRegex(ValueError, "duplicate"):
            main.restore_tactic(duplicate)

    def test_restore_rejects_distinct_players_with_the_same_shirt_number(self):
        state = main.tactic_state(self.left, self.right, [], None)
        duplicate_number = copy.deepcopy(state)
        selected = duplicate_number["sides"][0]["players"]
        occupied_numbers = {player["number"] for player in selected}
        repeated = next(
            person for person in self.left.team["squad"]
            if person["number"] in occupied_numbers
            and (person["name"], person["number"], person["position"])
            not in {identity(p) for p in self.left.players}
            and person["position"] == "DF"
        )
        selected[2].update(
            name=repeated["name"], number=repeated["number"], position=repeated["position"]
        )

        with self.assertRaisesRegex(ValueError, "duplicate"):
            main.restore_tactic(duplicate_number)


if __name__ == "__main__":
    unittest.main()
