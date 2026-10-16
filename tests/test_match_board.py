"""Validation of match lineups before they enter or leave the board."""

import copy
import json
import unittest

from match_board import build_imported_team, validate_imported_team_document


def sample_match_team():
    starters = [
        {"id": 100 + number, "number": number, "name": f"Player {number}",
         "position": "GK" if number == 1 else "DF" if number <= 5 else "MF" if number <= 9 else "FW"}
        for number in range(1, 12)
    ]
    bench = [
        {"id": 112, "number": 12, "name": "Substitute 12", "position": "MF"},
        {"id": 113, "number": 13, "name": "Substitute 13", "position": "GK"},
    ]
    return {
        "side": "home",
        "name": "Example FC",
        "players": starters,
        "bench": bench,
        "kit": {"pattern": "vertical_stripes", "colors": ["#123", "#abcdef"]},
        "gk_kit": {"pattern": "solid", "colors": ["#f0c419"]},
        "formation": "4-4-2",
        "substitutions": [{"out_id": 106, "in_id": 112, "minute": 63}],
    }


class MatchBoardTests(unittest.TestCase):
    def test_converts_lineup_kits_and_substitution(self):
        team = build_imported_team(sample_match_team(), 12345)
        self.assertEqual(team["id"], "zerozero-12345-home")
        self.assertEqual(team["source"], {"provider": "zerozero", "match_id": 12345, "side": "home"})
        self.assertEqual(team["starting_ids"], list(range(101, 112)))
        self.assertEqual(team["kits"][0]["pattern"], "vertical_stripes")
        self.assertEqual(team["kits"][0]["colors"], [(17, 34, 51), (171, 205, 239)])
        self.assertEqual(team["gk_kit"]["colors"], [(240, 196, 25)])
        self.assertEqual(team["substitutions"], [{"out_id": 106, "in_id": 112, "minute": 63}])
        self.assertEqual(team["formation"], "4-4-2")

    def test_goalkeeper_is_first_even_if_source_order_differs(self):
        match = sample_match_team()
        match["players"] = match["players"][1:] + match["players"][:1]
        team = build_imported_team(match, 12345)
        self.assertEqual(team["starting_ids"][0], 101)

    def test_missing_uniforms_use_distinguishable_fallback(self):
        match = sample_match_team()
        match["side"] = "away"
        del match["kit"]
        del match["gk_kit"]
        team = build_imported_team(match, 12345)
        self.assertEqual(team["id"], "zerozero-12345-away")
        self.assertEqual(team["kits"][0]["name"], "Unknown")
        self.assertEqual(team["kits"][0]["colors"], [(210, 210, 210)])
        self.assertEqual(team["gk_kit"]["colors"], [(240, 196, 25)])

    def test_rejects_duplicate_players_and_numbers(self):
        for field in ("id", "number"):
            match = sample_match_team()
            match["bench"][0][field] = match["players"][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Duplicate"):
                build_imported_team(match, 12345)

    def test_rejects_invalid_colors_patterns_and_substitution(self):
        for mutation in (
            lambda match: match["kit"].update(colors=["#12x"]),
            lambda match: match["kit"].update(pattern="polka_dots"),
            lambda match: match["substitutions"][0].update(in_id=99999),
            lambda match: match["substitutions"][0].update(out_id=101),
        ):
            match = sample_match_team()
            mutation(match)
            with self.subTest(match=match), self.assertRaises(ValueError):
                build_imported_team(match, 12345)

    def test_json_saved_document_round_trips_and_detects_tampering(self):
        team = build_imported_team(sample_match_team(), 12345)
        decoded = json.loads(json.dumps(team))
        self.assertEqual(validate_imported_team_document(decoded), team)
        for field, value in (("starting_ids", [101] * 11), ("id", "other-team")):
            invalid = copy.deepcopy(decoded)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_imported_team_document(invalid)
        invalid = copy.deepcopy(decoded)
        invalid["source"]["match_id"] = 999
        with self.assertRaises(ValueError):
            validate_imported_team_document(invalid)


if __name__ == "__main__":
    unittest.main()
