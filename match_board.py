"""Convert a Zerozero match lineup into the tactical board's team format.

This module has no network, browser, or pygame dependency.  Imported teams are
validated here both when a match is fetched and when a saved tactic is loaded.
"""

import re

from formations import FORMATIONS


_TEAM_ID = re.compile(r"^zerozero-([1-9][0-9]*)-(home|away)$")
_HEX_COLOR = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_PATTERNS = {"solid", "stripes", "vertical_stripes", "hoops", "halves"}
_POSITIONS = {"GK", "DF", "MF", "FW"}
_MAX_SAFE_INTEGER = 2**53 - 1  # IDs also travel through JavaScript in the web build.

_UNKNOWN_HOME_KIT = {"name": "Unknown", "pattern": "solid", "colors": [(80, 90, 110)]}
_UNKNOWN_AWAY_KIT = {"name": "Unknown", "pattern": "solid", "colors": [(210, 210, 210)]}
_UNKNOWN_GK_KIT = {"name": "GK", "pattern": "solid", "colors": [(240, 196, 25)]}


def _positive_id(value, label):
    if type(value) is not int or not 0 < value <= _MAX_SAFE_INTEGER:
        raise ValueError(f"Invalid {label}")
    return value


def _name(value, label):
    if not isinstance(value, str):
        raise ValueError(f"Invalid {label}")
    clean = value.strip()
    if not clean or len(clean) > 120 or any(ord(char) < 32 for char in clean):
        raise ValueError(f"Invalid {label}")
    return clean


def _color(value):
    if isinstance(value, str):
        match = _HEX_COLOR.fullmatch(value)
        if not match:
            raise ValueError("Invalid kit color")
        digits = match.group(1)
        if len(digits) == 3:
            return tuple(int(digit * 2, 16) for digit in digits)
        return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(channel) is not int or not 0 <= channel <= 255 for channel in value)):
        raise ValueError("Invalid kit color")
    return tuple(value)


def _pattern(value):
    if not isinstance(value, str):
        raise ValueError("Invalid kit pattern")
    pattern = value.strip().lower()
    if pattern in _PATTERNS:
        return pattern
    if pattern == "basic_plain_1-color":
        return "solid"
    if "vertical" in pattern and "stripe" in pattern:
        return "vertical_stripes"
    if "horizontal" in pattern and "stripe" in pattern:
        return "hoops"
    raise ValueError("Unsupported kit pattern")


def _kit(value, fallback, default_name):
    if value is None or value == {}:
        value = fallback
    if not isinstance(value, dict):
        raise ValueError("Invalid kit")
    name = _name(value.get("name", default_name), "kit name")
    pattern = _pattern(value.get("pattern"))
    colors = value.get("colors")
    if not isinstance(colors, (list, tuple)) or not 1 <= len(colors) <= 2:
        raise ValueError("Invalid kit colors")
    colors = [_color(color) for color in colors]
    if len(colors) == 1:
        pattern = "solid"
    return {"name": name, "pattern": pattern, "colors": colors}


def _player(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid player")
    player_id = _positive_id(value.get("id"), "player ID")
    number = value.get("number")
    if type(number) is not int or not 0 < number <= 999:
        raise ValueError("Invalid shirt number")
    position = value.get("position")
    if not isinstance(position, str) or position not in _POSITIONS:
        raise ValueError("Invalid player position")
    return {
        "id": player_id,
        "number": number,
        "name": _name(value.get("name"), "player name"),
        "position": position,
    }


def _substitutions(value, squad_by_id, starting_ids):
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("Invalid substitutions")
    changes = []
    for change in value:
        if not isinstance(change, dict):
            raise ValueError("Invalid substitution")
        out_id = _positive_id(change.get("out_id"), "substituted player ID")
        in_id = _positive_id(change.get("in_id"), "substitute player ID")
        minute = change.get("minute")
        if (out_id not in squad_by_id or in_id not in squad_by_id
                or out_id == in_id or type(minute) is not int or not 0 <= minute <= 180):
            raise ValueError("Invalid substitution")
        changes.append({"out_id": out_id, "in_id": in_id, "minute": minute})

    # A player must leave the pitch before their replacement can enter.  Keep
    # source order for simultaneous changes and reject impossible duplicates.
    changes.sort(key=lambda item: item["minute"])
    active = set(starting_ids)
    entered = set(starting_ids)
    for change in changes:
        if (change["out_id"] not in active or change["in_id"] in entered
                or ((squad_by_id[change["out_id"]]["position"] == "GK")
                    != (squad_by_id[change["in_id"]]["position"] == "GK"))):
            raise ValueError("Inconsistent substitution sequence")
        active.remove(change["out_id"])
        active.add(change["in_id"])
        entered.add(change["in_id"])
    return changes


def validate_imported_team_document(team):
    """Return a normalized copy of an imported team or raise ``ValueError``.

    This accepts JSON-decoded RGB lists as well as the RGB tuples used in the
    running application.  It never trusts embedded metadata or player links.
    """
    if not isinstance(team, dict):
        raise ValueError("Invalid imported team")
    team_id = team.get("id")
    match = _TEAM_ID.fullmatch(team_id) if isinstance(team_id, str) else None
    if not match:
        raise ValueError("Invalid imported team ID")
    match_id = _positive_id(int(match.group(1)), "match ID")
    side = match.group(2)
    source = team.get("source")
    if source is not None:
        if (not isinstance(source, dict) or source.get("provider") != "zerozero"
                or type(source.get("match_id")) is not int
                or source.get("match_id") != match_id or source.get("side") != side):
            raise ValueError("Invalid imported team source")

    name = _name(team.get("name"), "team name")
    fallback = _UNKNOWN_HOME_KIT if side == "home" else _UNKNOWN_AWAY_KIT
    kits = team.get("kits")
    if not isinstance(kits, list) or not 1 <= len(kits) <= 5:
        raise ValueError("Invalid team kits")
    normalized_kits = [_kit(kit, fallback, "Match") for kit in kits]
    gk_kit = _kit(team.get("gk_kit"), _UNKNOWN_GK_KIT, "GK")

    squad = team.get("squad")
    if not isinstance(squad, list) or not 11 <= len(squad) <= 40:
        raise ValueError("Invalid team squad")
    normalized_squad = [_player(player) for player in squad]
    ids = [player["id"] for player in normalized_squad]
    numbers = [player["number"] for player in normalized_squad]
    if len(set(ids)) != len(ids) or len(set(numbers)) != len(numbers):
        raise ValueError("Duplicate player or shirt number")
    by_id = {player["id"]: player for player in normalized_squad}

    starting_ids = team.get("starting_ids")
    if (not isinstance(starting_ids, list) or len(starting_ids) != 11
            or any(type(player_id) is not int or player_id not in by_id for player_id in starting_ids)
            or len(set(starting_ids)) != 11):
        raise ValueError("Invalid starting eleven")
    goalkeepers = [player_id for player_id in starting_ids if by_id[player_id]["position"] == "GK"]
    if len(goalkeepers) != 1:
        raise ValueError("The starting eleven needs exactly one goalkeeper")
    starting_ids = [goalkeepers[0], *(player_id for player_id in starting_ids if player_id != goalkeepers[0])]

    formation = team.get("formation")
    if formation is not None and (not isinstance(formation, str) or formation not in FORMATIONS):
        raise ValueError("Invalid imported formation")

    substitutions = _substitutions(team.get("substitutions", []), by_id, starting_ids)
    return {
        "id": team_id,
        "name": name,
        "kits": normalized_kits,
        "gk_kit": gk_kit,
        "squad": normalized_squad,
        "starting_ids": starting_ids,
        "substitutions": substitutions,
        "formation": formation,
        "source": {"provider": "zerozero", "match_id": match_id, "side": side},
    }


def build_imported_team(match_team, match_id):
    """Convert one parsed home/away match team to the board's team format."""
    match_id = _positive_id(match_id, "match ID")
    if not isinstance(match_team, dict):
        raise ValueError("Invalid match team")
    side = match_team.get("side")
    if side not in ("home", "away"):
        raise ValueError("Match team side must be home or away")
    starters = match_team.get("players")
    bench = match_team.get("bench", [])
    if not isinstance(starters, list) or len(starters) != 11 or not isinstance(bench, list):
        raise ValueError("A match team needs eleven starters and a bench list")
    squad = [_player(player) for player in [*starters, *bench]]
    goalkeeper = [player for player in squad[:11] if player["position"] == "GK"]
    if len(goalkeeper) != 1:
        raise ValueError("The starting eleven needs exactly one goalkeeper")
    starting_ids = [goalkeeper[0]["id"], *(player["id"] for player in squad[:11] if player["id"] != goalkeeper[0]["id"])]
    fallback = _UNKNOWN_HOME_KIT if side == "home" else _UNKNOWN_AWAY_KIT
    formation = match_team.get("formation")
    if not isinstance(formation, str) or formation not in FORMATIONS:
        formation = None
    document = {
        "id": f"zerozero-{match_id}-{side}",
        "name": match_team.get("name"),
        "kits": [_kit(match_team.get("kit"), fallback, "Match")],
        "gk_kit": _kit(match_team.get("gk_kit"), _UNKNOWN_GK_KIT, "GK"),
        "squad": squad,
        "starting_ids": starting_ids,
        "substitutions": match_team.get("substitutions", []),
        "formation": formation,
        "source": {"provider": "zerozero", "match_id": match_id, "side": side},
    }
    return validate_imported_team_document(document)
