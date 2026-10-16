"""Import a completed Zerozero match from its public match report.

The HTML parser deliberately uses only Python's standard library so it also
works in the desktop app without the optional scraper dependencies. Zerozero
can change its markup; missing lineups are reported as an error rather than
silently replacing a board with an incomplete team.
"""

from collections import defaultdict
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


_MATCH_PATH = re.compile(r"^/jogo/[^/]+/(\d+)/?$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SPACE = re.compile(r"\s+")
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
_MAX_HTML_BYTES = 2_000_000


class MatchImportError(ValueError):
    """The URL or match report cannot provide a complete starting lineup."""


def validate_match_url(url):
    """Return (canonical_url, numeric_match_id) for a Zerozero match URL."""
    if not isinstance(url, str) or len(url) > 2048:
        raise MatchImportError("Enter a valid zerozero.pt match link.")
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise MatchImportError("Enter a valid zerozero.pt match link.") from exc
    try:
        allowed_host = (parts.hostname in {"zerozero.pt", "www.zerozero.pt"}
                        and parts.port in {None, 443})
    except ValueError:
        allowed_host = False
    if (parts.scheme != "https" or not allowed_host or
            parts.username or parts.password):
        raise MatchImportError("Only HTTPS zerozero.pt match links are supported.")
    found = _MATCH_PATH.fullmatch(parts.path)
    if not found:
        raise MatchImportError("The link must point to a Zerozero match page.")
    return "https://www.zerozero.pt" + parts.path.rstrip("/"), int(found.group(1))


def fetch_match(url, *, timeout=15):
    """Download and parse a public Zerozero match report on desktop Python."""
    canonical, _ = validate_match_url(url)
    request = Request(canonical, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    })
    try:
        with build_opener(_SameMatchRedirects(canonical)).open(request, timeout=timeout) as response:
            final_url, _ = validate_match_url(response.geturl())
            if final_url != canonical:
                raise MatchImportError("The match link redirected to another match.")
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise MatchImportError("The match link did not return an HTML page.")
            raw = response.read(_MAX_HTML_BYTES + 1)
            if len(raw) > _MAX_HTML_BYTES:
                raise MatchImportError("The match page is too large to import.")
            declared = response.headers.get_content_charset()
    except MatchImportError:
        raise
    except Exception as exc:
        raise MatchImportError("Could not download the Zerozero match page.") from exc
    markup = raw.decode(declared or "utf-8", errors="replace")
    return parse_match_html(markup, canonical)


def load_match(url):
    """Load a match by link; convenient for calling from an async UI thread."""
    return fetch_match(url)


class _SameMatchRedirects(HTTPRedirectHandler):
    def __init__(self, canonical):
        self.canonical = canonical

    def redirect_request(self, request, fp, code, message, headers, new_url):
        target, _ = validate_match_url(new_url)
        if target != self.canonical:
            raise MatchImportError("The match link redirected to another match.")
        return super().redirect_request(request, fp, code, message, headers, new_url)


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.parent = parent

    def has_classes(self, *names):
        classes = set(self.attrs.get("class", "").split())
        return all(name in classes for name in names)

    def descendants(self, predicate):
        for child in self.children:
            if isinstance(child, _Node):
                if predicate(child):
                    yield child
                yield from child.descendants(predicate)

    def first(self, predicate):
        return next(self.descendants(predicate), None)

    def text(self):
        return "".join(
            child.text() if isinstance(child, _Node) else child
            for child in self.children
        )


class _TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _clean_text(text):
    return _SPACE.sub(" ", text.replace("\xa0", " ")).strip()


def _direct_columns(row):
    return [node for node in row.children
            if isinstance(node, _Node) and node.has_classes("zz-tpl-col", "is-6")]


def _parse_player(node):
    number_node = node.first(
        lambda item: item.tag == "div" and item.has_classes("number", "match_player_stats")
    )
    name_node = node.first(
        lambda item: item.tag == "a" and item.attrs.get("href", "").startswith("/jogador/")
    )
    if number_node is None or name_node is None:
        raise MatchImportError("A player entry is missing a number or name.")
    try:
        player_id = int(number_node.attrs["data-player-id"])
        number = int(_clean_text(number_node.text()))
    except (KeyError, ValueError) as exc:
        raise MatchImportError("A player entry has invalid identifiers.") from exc
    name = re.sub(r"\s*\(C\)$", "", _clean_text(name_node.text()))
    if not name or not 0 <= number <= 99:
        raise MatchImportError("A player entry has an invalid name or number.")
    player = {"id": player_id, "number": number, "name": name}
    events = node.first(lambda item: item.tag == "div" and item.has_classes("events"))
    if events is not None:
        event_children = [item for item in events.children if isinstance(item, _Node)]
        for index, icon in enumerate(event_children):
            if (icon.tag != "span" or not icon.has_classes("icn_zerozero", "grey")
                    or (_clean_text(icon.text()) not in {"7", "8"} and
                        icon.attrs.get("title") != "Entrou")):
                continue
            minute_node = next((item for item in event_children[index + 1:]
                                if item.tag == "div"), None)
            minute_text = _clean_text(minute_node.text()) if minute_node else ""
            minute = re.search(r"\d+", minute_text)
            if minute:
                if icon.attrs.get("title") == "Entrou" or _clean_text(icon.text()) == "7":
                    player["_in_minute"] = int(minute.group())
                elif _clean_text(icon.text()) == "8":
                    player["_out_minute"] = int(minute.group())
    return player


def _parse_players(column):
    return [_parse_player(node) for node in column.children
            if isinstance(node, _Node) and node.tag == "div" and
            node.has_classes("player", "fl-r-cen")]


def _kit_from_svg(player_node):
    svg = player_node.first(lambda item: item.tag == "svg")
    if svg is None:
        return None
    group = svg.first(lambda item: item.tag == "g" and item.attrs.get("id"))
    original_pattern = group.attrs["id"] if group is not None else ""
    if "vertical" in original_pattern and "stripe" in original_pattern:
        pattern = "vertical_stripes"
    elif "horizontal" in original_pattern or "hoop" in original_pattern:
        pattern = "hoops"
    elif "half" in original_pattern:
        pattern = "halves"
    else:
        pattern = "solid"
    colors = []
    for color_id in ("color1", "color2"):
        shape = svg.first(lambda item: item.tag in {"path", "rect", "polygon"} and
                          item.attrs.get("id") == color_id and
                          _HEX_COLOR.fullmatch(item.attrs.get("fill", "")))
        if shape is not None:
            colors.append(shape.attrs["fill"].lower())
    if not colors:
        return None
    return {"pattern": pattern, "colors": colors}


def _pitch_kits(root, team_players):
    cards = {}
    for node in root.descendants(
            lambda item: item.tag == "div" and item.has_classes("campo_onze_bloco_jogador")):
        try:
            cards[int(node.attrs["data-player-id"])] = node
        except (KeyError, ValueError):
            continue
    gk = cards.get(team_players[0]["id"])
    outfield = next((cards[player["id"]] for player in team_players[1:]
                     if player["id"] in cards), None)
    return (_kit_from_svg(outfield) if outfield else None,
            _kit_from_svg(gk) if gk else None)


def _pitch_layout(root, side, starters):
    """Read the pitch's goalkeeper-to-forward columns when available."""
    tables = list(root.descendants(
        lambda item: item.tag == "table" and item.has_classes("team")))
    if len(tables) != 2:
        return None, {}
    table = tables[0 if side == "home" else 1]
    row = next((item for item in table.children
                if isinstance(item, _Node) and item.tag == "tr"), None)
    if row is None:
        return None, {}
    columns = [item for item in row.children
               if isinstance(item, _Node) and item.tag == "td"]
    groups = []
    for column in columns:
        ids = []
        for card in column.descendants(
                lambda item: item.tag == "div" and
                item.has_classes("campo_onze_bloco_jogador")):
            try:
                ids.append(int(card.attrs["data-player-id"]))
            except (KeyError, ValueError):
                return None, {}
        if ids:
            groups.append(ids)
    if side == "away":
        groups.reverse()
    starter_ids = {player["id"] for player in starters}
    if (not groups or groups[0] != [starters[0]["id"]] or
            len(groups) < 4 or
            {player_id for group in groups for player_id in group} != starter_ids or
            sum(map(len, groups)) != 11):
        return None, {}
    roles = {groups[0][0]: "GK"}
    for group_index, group in enumerate(groups[1:], start=1):
        role = "DF" if group_index == 1 else "FW" if group_index == len(groups) - 1 else "MF"
        roles.update({player_id: role for player_id in group})
    formation = "-".join(str(len(group)) for group in groups[1:])
    return formation, roles


def _substitutions(starters, bench):
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    for player in starters:
        if "_out_minute" in player:
            outgoing[player["_out_minute"]].append(player)
    for player in bench:
        if "_in_minute" in player:
            incoming[player["_in_minute"]].append(player)
    changes = []
    for minute, out_players in sorted(outgoing.items()):
        in_players = incoming[minute]
        # The roster marks minutes but does not explicitly link a player who
        # left to one who entered. When several changes share a minute, the
        # displayed roster order is the best available pairing on this page.
        for departing, arriving in zip(out_players, in_players):
            arriving["position"] = departing["position"]
            changes.append({"out_id": departing["id"], "in_id": arriving["id"],
                            "minute": minute})
    return changes


def parse_match_html(markup, source_url):
    """Parse teams, lineups, shirt colors and substitution minutes from HTML."""
    canonical, match_id = validate_match_url(source_url)
    if not isinstance(markup, str) or len(markup) > _MAX_HTML_BYTES:
        raise MatchImportError("The match page is invalid or too large.")
    parser = _TreeParser()
    parser.feed(markup)
    reports = parser.root.descendants(
        lambda item: item.tag == "div" and item.attrs.get("id") == "game_report")
    rows = None
    for report in reports:
        candidate = [item for item in report.children
                     if isinstance(item, _Node) and item.has_classes("zz-tpl-row", "game_report")]
        if len(candidate) >= 2:
            rows = candidate
            break
    if rows is None:
        raise MatchImportError("This match has no published lineups on Zerozero.")
    starters_columns = _direct_columns(rows[0])
    bench_columns = _direct_columns(rows[1])
    if len(starters_columns) != 2 or len(bench_columns) != 2:
        raise MatchImportError("The match lineups could not be read.")
    teams = []
    for index, side in enumerate(("home", "away")):
        name_node = starters_columns[index].first(
            lambda item: item.tag == "div" and item.has_classes("subtitle"))
        name = _clean_text(name_node.text()) if name_node else ""
        players = _parse_players(starters_columns[index])
        bench = _parse_players(bench_columns[index])
        if not name or len(players) != 11:
            raise MatchImportError("This match has no complete starting lineup.")
        if len({p["id"] for p in players + bench}) != len(players + bench):
            raise MatchImportError("The match lineup contains duplicate players.")
        # The pitch graphic groups players into tactical columns. If absent,
        # the roster order still identifies the first player as goalkeeper.
        formation, pitch_roles = _pitch_layout(parser.root, side, players)
        fallback_roles = ["GK"] + ["DF"] * 4 + ["MF"] * 3 + ["FW"] * 3
        for player, position in zip(players, fallback_roles):
            player["position"] = pitch_roles.get(player["id"], position)
        for player_index, player in enumerate(bench):
            player["position"] = "GK" if player_index == 0 else "MF"
        changes = _substitutions(players, bench)
        for player in players + bench:
            player.pop("_in_minute", None)
            player.pop("_out_minute", None)
        kit, gk_kit = _pitch_kits(parser.root, players)
        teams.append({
            "side": side,
            "name": name,
            "players": players,
            "bench": bench,
            "formation": formation,
            "kit": kit,
            "gk_kit": gk_kit,
            "substitutions": changes,
        })
    return {"source_url": canonical, "match_id": match_id, "teams": teams}
