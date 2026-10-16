"""Zerozero match parser contracts, using a small representative HTML report."""

import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import match_import


URL = "https://www.zerozero.pt/jogo/2026-10-10-maritimo-fc-porto/12278041"


def _player(player_id, number, name, event=""):
    return (
        '<div class="player fl-r-cen">'
        f'<div class="number match_player_stats" data-player-id="{player_id}">{number}</div>'
        f'<div class="name"><a href="/jogador/example/{player_id}">{name}</a></div>'
        f'<div class="events">{event}</div></div>'
    )


def _shirt(player_id, colors, pattern):
    second = f'<path id="color2" fill="{colors[1]}"></path>' if len(colors) > 1 else ""
    return (
        '<div class="campo_onze_bloco_jogador" '
        f'data-player-id="{player_id}"><svg><g id="{pattern}">'
        f'<path id="color1" fill="{colors[0]}"></path>{second}'
        '</g></svg></div>'
    )


def _pitch(ids, colors):
    # Five real Zerozero pitch columns: GK, 4 defenders, 1 + 2 midfielders,
    # and 3 forwards. The away side is displayed in reverse order.
    groups = [ids[:1], ids[1:5], ids[5:6], ids[6:8], ids[8:]]
    if ids[0] >= 200:
        groups.reverse()
    columns = []
    for group in groups:
        shirts = "".join(_shirt(player_id, ["#383838"] if player_id == ids[0] else colors,
                                "basic_plain_1-color" if player_id == ids[0]
                                else "vertical-2-stripes_1_col-2") for player_id in group)
        columns.append(f"<td>{shirts}</td>")
    return '<table class="team"><tr>' + "".join(columns) + '</tr></table>'


def _report():
    outgoing = '<span title="Assistência">B</span><div>15\'</div><span class="icn_zerozero grey">8</span><div>66\'</div>'
    simple_out = '<span class="icn_zerozero grey">8</span><div>66\'</div>'
    simple_in = '<span title="Entrou" class="icn_zerozero grey">7</span><div>66\'</div>'
    home = "".join(_player(i, i - 100, "Fran Vieites" if i == 101 else f"Home {i}",
                           outgoing if i == 106 else simple_out if i == 111 else "")
                   for i in range(101, 112))
    away = "".join(_player(i, i - 200, "Diogo Costa (C)" if i == 201 else f"Away {i}")
                   for i in range(201, 212))
    bench_home = (_player(112, 12, "Sub 112", simple_in) +
                  _player(113, 13, "Sub 113", simple_in))
    bench_away = _player(212, 12, "Sub 212") + _player(213, 13, "Sub 213")
    return (
        '<div id="game_report"><div class="zz-tpl-row game_report">'
        '<div class="zz-tpl-col is-6 fl-c"><div class="subtitle">Marítimo</div>'
        f'{home}</div><div class="zz-tpl-col is-6 fl-c">'
        f'<div class="subtitle">FC Porto</div>{away}</div></div>'
        '<div class="zz-tpl-row game_report mt">'
        f'<div class="zz-tpl-col is-6 fl-c">{bench_home}</div>'
        f'<div class="zz-tpl-col is-6 fl-c">{bench_away}</div></div></div>'
        + _pitch(list(range(101, 112)), ["#990012", "#00703c"])
        + _pitch(list(range(201, 212)), ["#ffffff", "#00276c"])
    )


class MatchImportTests(unittest.TestCase):
    def test_fetch_reports_upstream_status_and_network_failure(self):
        failures = (
            (HTTPError(URL, 403, "Forbidden", None, None), "HTTP 403"),
            (HTTPError(URL, 503, "Unavailable", None, None), "HTTP 503"),
            (URLError("network unavailable"), "could not reach Zerozero"),
        )
        for failure, expected in failures:
            with self.subTest(failure=failure), patch.object(match_import, "build_opener") as opener:
                opener.return_value.open.side_effect = failure
                with self.assertRaises(match_import.MatchImportError) as caught:
                    match_import.fetch_match(URL)
                self.assertIn(expected, str(caught.exception))

    def test_url_validation_blocks_other_hosts_and_malformed_links(self):
        self.assertEqual(match_import.validate_match_url(URL + "?utm_source=x"),
                         (URL, 12278041))
        for url in (
            "http://www.zerozero.pt/jogo/example/123",
            "https://zerozero.pt.evil.example/jogo/example/123",
            "https://user@zerozero.pt/jogo/example/123",
            "https://zerozero.pt:abc/jogo/example/123",
            "https://[zerozero.pt/jogo/example/123",
            "https://zerozero.pt/equipa/maritimo",
        ):
            with self.subTest(url=url), self.assertRaises(match_import.MatchImportError):
                match_import.validate_match_url(url)

    def test_redirect_target_is_checked_before_following(self):
        handler = match_import._SameMatchRedirects(URL)
        with self.assertRaises(match_import.MatchImportError):
            handler.redirect_request(None, None, 302, "Found", {},
                                     "https://evil.example/jogo/example/12278041")

    def test_parse_lineups_kits_positions_and_same_minute_substitutions(self):
        match = match_import.parse_match_html(_report(), URL)
        self.assertEqual(match["match_id"], 12278041)
        home, away = match["teams"]
        self.assertEqual((home["side"], away["side"]), ("home", "away"))
        self.assertEqual((home["name"], away["name"]), ("Marítimo", "FC Porto"))
        self.assertEqual((len(home["players"]), len(away["players"])), (11, 11))
        self.assertEqual(home["formation"], "4-1-2-3")
        self.assertEqual(away["formation"], "4-1-2-3")
        self.assertEqual([p["position"] for p in home["players"]],
                         ["GK"] + ["DF"] * 4 + ["MF"] * 3 + ["FW"] * 3)
        self.assertEqual(away["players"][0]["name"], "Diogo Costa")
        self.assertEqual(home["kit"], {"pattern": "vertical_stripes",
                                       "colors": ["#990012", "#00703c"]})
        self.assertEqual(away["kit"], {"pattern": "vertical_stripes",
                                       "colors": ["#ffffff", "#00276c"]})
        self.assertEqual(home["gk_kit"], {"pattern": "solid", "colors": ["#383838"]})
        self.assertEqual(home["substitutions"], [
            {"out_id": 106, "in_id": 112, "minute": 66},
            {"out_id": 111, "in_id": 113, "minute": 66},
        ])
        self.assertEqual(home["bench"][0]["position"], "MF")
        self.assertNotIn("_out_minute", home["players"][5])

    def test_incomplete_report_is_rejected(self):
        with self.assertRaisesRegex(match_import.MatchImportError, "no published lineups"):
            match_import.parse_match_html("<html><body>Match postponed</body></html>", URL)
        with self.assertRaisesRegex(match_import.MatchImportError, "complete starting lineup"):
            match_import.parse_match_html(_report().replace(
                _player(111, 11, "Home 111", '<span class="icn_zerozero grey">8</span><div>66\'</div>'),
                ""), URL)


if __name__ == "__main__":
    unittest.main()
