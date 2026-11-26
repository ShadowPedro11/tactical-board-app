"""Build match responses for the web server and desktop importer."""

import match_board
import match_import


def match_response(url):
    """Return an HTTP status and JSON-compatible response for a match link."""
    try:
        canonical, match_id = match_import.validate_match_url(url)
    except match_import.MatchImportError as exc:
        return 400, {"error": str(exc)}

    try:
        match = match_import.load_match(canonical)
        if not isinstance(match, dict) or match.get("match_id") != match_id:
            raise ValueError("The match did not contain two complete teams.")
        lineups = match.get("teams")
        if (not isinstance(lineups, list) or len(lineups) != 2
                or any(not isinstance(team, dict) for team in lineups)
                or [team.get("side") for team in lineups] != ["home", "away"]):
            raise ValueError("The match did not contain two complete teams.")
        teams = [match_board.build_imported_team(team, match_id) for team in lineups]
    except match_import.MatchImportError as exc:
        return 502, {"error": str(exc)}
    except (KeyError, TypeError, ValueError) as exc:
        return 422, {"error": f"Could not use the match lineup: {exc}"}
    return 200, {"match_id": match_id, "teams": teams}
