"""Imported match teams on the actual board and in saved tactics."""

import copy
import json
import unittest

import main
from match_board import build_imported_team
from tests.test_match_board import sample_match_team


def imported_sides():
    home = sample_match_team()
    away = copy.deepcopy(home)
    away["side"] = "away"
    away["name"] = "Away FC"
    return (
        main.TeamSide("A", build_imported_team(home, 12345), 1),
        main.TeamSide("B", build_imported_team(away, 12345), -1),
    )


class ImportedMatchBoardTests(unittest.TestCase):
    def test_uses_exact_starting_eleven_and_switch_badge(self):
        home, away = imported_sides()
        for side in (home, away):
            with self.subTest(team=side.team["id"]):
                self.assertEqual(len(side.players), 11)
                self.assertEqual([p.player_id for p in side.players], side.team["starting_ids"])
                self.assertEqual([p.number for p in side.players], list(range(1, 12)))
                self.assertEqual(len({p.number for p in side.players}), 11)
                self.assertIsNotNone(side.players[5].switch_badge_rect())
                self.assertIsNone(side.players[6].switch_badge_rect())

                outgoing = side.players[5]
                before = (outgoing.player_id, outgoing.number, outgoing.name, outgoing.position)
                self.assertEqual(outgoing.switch_pair["before"]["id"], 106)
                self.assertEqual(outgoing.switch_pair["after"]["id"], 112)
                self.assertTrue(outgoing.switch_player())
                self.assertTrue(outgoing.switch_active)
                self.assertEqual(outgoing.player_id, 112)
                self.assertEqual(outgoing.number, 12)
                self.assertEqual(outgoing.name, "Substitute 12")
                self.assertTrue(outgoing.switch_player())
                self.assertFalse(outgoing.switch_active)
                self.assertEqual((outgoing.player_id, outgoing.number, outgoing.name, outgoing.position), before)

    def test_save_restore_retains_dynamic_teams_and_active_switch(self):
        home, away = imported_sides()
        home.players[5].switch_player()
        home.players[5].x_m = 41.5
        state = main.tactic_state(home, away, [((10, 11), (20, 21))], (30, 31))
        encoded = json.loads(json.dumps(state))
        restored_home, restored_away, arrows, ball = main.restore_tactic(encoded)
        self.assertEqual(restored_home.team["id"], "zerozero-12345-home")
        self.assertEqual(restored_away.team["id"], "zerozero-12345-away")
        self.assertEqual([p.player_id for p in restored_home.players[:5]], home.team["starting_ids"][:5])
        self.assertEqual(restored_home.players[5].player_id, 112)
        self.assertTrue(restored_home.players[5].switch_active)
        self.assertIsNotNone(restored_home.players[5].switch_badge_rect())
        self.assertEqual(restored_home.players[5].x_m, 41.5)
        self.assertEqual(arrows, [((10, 11), (20, 21))])
        self.assertEqual(ball, (30, 31))

    def test_restore_rejects_corrupt_embedded_team_or_switch_pair(self):
        home, away = imported_sides()
        base = json.loads(json.dumps(main.tactic_state(home, away, [], None)))
        cases = []
        duplicate_number = copy.deepcopy(base)
        duplicate_number["sides"][0]["team_data"]["squad"][11]["number"] = 1
        cases.append(duplicate_number)
        invalid_color = copy.deepcopy(base)
        invalid_color["sides"][0]["team_data"]["kits"][0]["colors"][0] = [500, 0, 0]
        cases.append(invalid_color)
        invalid_pair = copy.deepcopy(base)
        invalid_pair["sides"][0]["players"][5]["switch_pair"]["after"]["name"] = "Unknown"
        cases.append(invalid_pair)
        invalid_pair_id = copy.deepcopy(base)
        invalid_pair_id["sides"][0]["players"][5]["switch_pair"]["after"]["id"] = 113
        cases.append(invalid_pair_id)
        for document in cases:
            with self.subTest(document=document["sides"][0]["team_data"]["id"]), self.assertRaises(ValueError):
                main.restore_tactic(document)


if __name__ == "__main__":
    unittest.main()
