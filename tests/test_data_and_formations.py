"""Checks for the static data and formation geometry used by the board."""

import unittest

from formations import (
    FORMATIONS,
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    gk_slot,
    mirror_x,
    outfield_slots,
)
from teams_data import TEAMS, get_team


class FormationTests(unittest.TestCase):
    def test_every_formation_has_ten_distinct_outfield_slots(self):
        self.assertTrue(FORMATIONS)
        for name, lines in FORMATIONS.items():
            with self.subTest(formation=name):
                self.assertTrue(all(isinstance(count, int) and count > 0 for count in lines))
                self.assertEqual(sum(lines), 10)
                slots = outfield_slots(name)
                self.assertEqual(len(slots), 10)
                self.assertEqual(len(set(slots)), 10)
                self.assertTrue(all(0 < x < PITCH_LENGTH_M / 2 for x, _ in slots))
                self.assertTrue(all(0 < y < PITCH_WIDTH_M for _, y in slots))

                offset = 0
                previous_x = 0
                for count in lines:
                    row = slots[offset : offset + count]
                    self.assertEqual(len({x for x, _ in row}), 1)
                    self.assertGreater(row[0][0], previous_x)
                    self.assertEqual([y for _, y in row], sorted(y for _, y in row))
                    previous_x = row[0][0]
                    offset += count

    def test_goalkeeper_and_mirrored_slots_remain_on_pitch(self):
        gk_x, gk_y = gk_slot()
        self.assertTrue(0 < gk_x < PITCH_LENGTH_M / 2)
        self.assertEqual(gk_y, PITCH_WIDTH_M / 2)
        for name in FORMATIONS:
            for x, y in [gk_slot(), *outfield_slots(name)]:
                with self.subTest(formation=name, slot=(x, y)):
                    self.assertAlmostEqual(mirror_x(mirror_x(x)), x)
                    self.assertTrue(PITCH_LENGTH_M / 2 < mirror_x(x) < PITCH_LENGTH_M)
                    self.assertTrue(0 < y < PITCH_WIDTH_M)


class TeamDataTests(unittest.TestCase):
    def test_teams_have_valid_squads_and_kits(self):
        self.assertTrue(TEAMS)
        ids = [team["id"] for team in TEAMS]
        self.assertEqual(len(ids), len(set(ids)))

        for team in TEAMS:
            with self.subTest(team=team["id"]):
                self.assertTrue(team["id"])
                self.assertTrue(team["name"].strip())
                self.assertIs(get_team(team["id"]), team)
                self.assertTrue(team["kits"])
                for kit in [*team["kits"], team["gk_kit"]]:
                    self.assertTrue(kit["name"].strip())
                    self.assertTrue(kit["pattern"].strip())
                    self.assertTrue(kit["colors"])
                    for color in kit["colors"]:
                        self.assertEqual(len(color), 3)
                        self.assertTrue(
                            all(
                                isinstance(channel, int) and 0 <= channel <= 255
                                for channel in color
                            )
                        )

                for player in team["squad"]:
                    self.assertTrue(player["name"].strip())
                    self.assertIsInstance(player["number"], int)
                    self.assertGreater(player["number"], 0)
                    self.assertIn(player["position"], {"GK", "DF", "MF", "FW"})

    def test_every_team_can_fill_every_formation_by_position(self):
        for team in TEAMS:
            available = {
                position: sum(p["position"] == position for p in team["squad"])
                for position in ("GK", "DF", "MF", "FW")
            }
            for formation, lines in FORMATIONS.items():
                with self.subTest(team=team["id"], formation=formation):
                    self.assertGreaterEqual(available["GK"], 1)
                    self.assertGreaterEqual(available["DF"], lines[0])
                    self.assertGreaterEqual(available["MF"], sum(lines[1:-1]))
                    self.assertGreaterEqual(available["FW"], lines[-1])


if __name__ == "__main__":
    unittest.main()
