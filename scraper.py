#!/usr/bin/env python3
"""
zerozero.pt competition/team/squad scraper.

Workflow
--------
1) scrape a competition page (e.g. a league standings page) -> finds every
   team in the "Classificação" table -> visits each team's page -> pulls
   the full squad list and visible uniform SVGs -> writes everything to a CSV.

2) (optional) build a ready-to-use `TEAMS = [...]` python file out of that
   CSV, in the same shape used by game/roster-building scripts.

Usage
-----
    python scraper.py scrape "https://www.zerozero.pt/competicao/liga-portuguesa" -o players.csv
    python scraper.py build players.csv -o teams_generated.py
"""

import argparse
import csv
import json
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.zerozero.pt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# zerozero.pt squad section labels -> generic position codes
POSITION_MAP = {
    "Guarda Redes": "GK",
    "Defesa": "DF",
    "Médio": "MF",
    "Avançado": "FW",
}

# matches hrefs like /equipa/alaves/37?epoca_id=156 or /equipa/barcelona?epoca_id=156
TEAM_LINK_RE = re.compile(r"^/equipa/([^/?]+)(?:/(\d+))?\?epoca_id=(\d+)")
COLOR_ID_RE = re.compile(r"^color(\d+)")
RGB_RE = re.compile(r"rgba?\(([^)]+)\)", re.IGNORECASE)

KIT_NAMES = ["Home", "Away", "Third", "Fourth", "Fifth"]

DEFAULT_KITS = [
    {"name": "Home", "pattern": "solid", "colors": [(200, 30, 40)]},
    {"name": "Away", "pattern": "solid", "colors": [(255, 255, 255)]},
    {"name": "Third", "pattern": "solid", "colors": [(20, 20, 20)]},
]
DEFAULT_GK_KIT = {"name": "GK", "pattern": "solid", "colors": [(240, 196, 25)]}


def get_soup(session, url):
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_teams(soup):
    """Find every team link inside the standings ("Classificação") table."""
    container = soup.find(id="edition_table") or soup
    teams = {}
    for a in container.find_all("a", href=True):
        m = TEAM_LINK_RE.match(a["href"])
        if not m:
            continue
        href_path = a["href"].split("?")[0]
        name = a.get_text(strip=True)
        entry = teams.setdefault(
            href_path,
            {"slug": m.group(1), "numeric_id": m.group(2), "href": a["href"], "name": ""},
        )
        if name:
            entry["name"] = name
    return list(teams.values())


def parse_age_value(info_text):
    """'29 anos - 6.50 M €' -> ('29', '6.50 M €')."""
    age, value = "", ""
    if not info_text:
        return age, value
    parts = [p.strip() for p in info_text.split("-")]
    if parts:
        m = re.search(r"\d+", parts[0])
        if m:
            age = m.group(0)
    if len(parts) > 1:
        value = parts[1].strip()
    return age, value


def hex_to_rgb(value):
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def css_color_to_rgb(value):
    """Convert '#273e7c' or 'rgb(39,62,124)' to an RGB tuple."""
    if not value:
        return None

    value = value.strip()
    if value.startswith("#"):
        return hex_to_rgb(value)

    m = RGB_RE.match(value)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")[:3]]
        try:
            return tuple(int(float(p)) for p in parts)
        except ValueError:
            return None

    return None


def normalize_uniform_pattern(pattern_id):
    """Map zerozero's plain SVG template id to the script's existing solid pattern."""
    if not pattern_id:
        return "solid"
    if pattern_id.startswith("basic_plain"):
        return "solid"
    return pattern_id


def extract_uniform_from_svg(svg, index):
    """Extract one uniform dict from a zerozero inline shirt SVG."""
    root_group = svg.find("g", id=True, recursive=False)
    pattern_id = root_group.get("id", "") if root_group else ""
    pattern = normalize_uniform_pattern(pattern_id)

    # Colors are encoded as ids like color1, color1_2, color2, color2_5, etc.
    # We keep the first distinct RGB value per numeric color id, in color-id order.
    colors_by_id = {}
    for element in svg.find_all(id=COLOR_ID_RE):
        match = COLOR_ID_RE.match(element.get("id", ""))
        if not match:
            continue

        rgb = css_color_to_rgb(element.get("fill"))
        if rgb is None:
            continue

        color_number = int(match.group(1))
        if color_number not in colors_by_id:
            colors_by_id[color_number] = rgb

    colors = [colors_by_id[i] for i in sorted(colors_by_id)]
    if not colors:
        return None

    return {
        "name": KIT_NAMES[index] if index < len(KIT_NAMES) else f"Kit {index + 1}",
        "pattern": pattern,
        "colors": colors,
    }


def extract_uniforms(soup):
    """Parse visible shirt SVGs from the team header/right wrapper.

    zerozero renders uniforms as inline SVG shirts with viewBox="0 0 200 200".
    Other header icons, such as UEFA ranking badges, use different viewBoxes,
    so this filters those out.
    """
    header = soup.select_one("div.zz-enthdr-right") or soup
    uniforms = []

    for svg in header.find_all("svg"):
        viewbox = svg.get("viewBox") or svg.get("viewbox") or ""
        if viewbox.strip() != "0 0 200 200":
            continue

        uniform = extract_uniform_from_svg(svg, len(uniforms))
        if uniform:
            uniforms.append(uniform)

    return uniforms


def extract_squad(soup, team_id, team_name, uniforms=None):
    """Parse the #team_squad block of a team page into a list of player dicts."""
    squad_div = soup.find("div", id="team_squad")
    if not squad_div:
        return []

    players = []
    current_position = ""
    kits_json = json.dumps(uniforms or [], ensure_ascii=False)

    for child in squad_div.find_all("div", recursive=False):
        classes = child.get("class", []) or []

        if "section" in classes:
            label = child.get_text(strip=True)
            current_position = POSITION_MAP.get(label, label)
            continue

        if "staff_line" in classes:
            for staff in child.find_all("div", class_="staff", recursive=False):
                number_div = staff.find("div", class_="number")
                number = number_div.get_text(strip=True) if number_div else ""
                number = "" if number == "-" else number

                name_div = staff.find("div", class_="name")
                text_div = name_div.find("div", class_="text") if name_div else None
                name_a = text_div.find("a") if text_div else None
                player_name = name_a.get_text(strip=True) if name_a else ""
                player_url = (
                    urljoin(BASE_URL, name_a["href"])
                    if name_a and name_a.get("href")
                    else ""
                )

                flag_div = name_div.find("div", class_="image") if name_div else None
                flag_a = flag_div.find("a", title=True) if flag_div else None
                nationality = flag_a["title"] if flag_a else ""

                span = name_div.find("span", recursive=False) if name_div else None
                age, market_value = parse_age_value(
                    span.get_text(strip=True) if span else ""
                )

                players.append(
                    {
                        "team_id": team_id,
                        "team_name": team_name,
                        "kits_json": kits_json,
                        "position": current_position,
                        "number": number,
                        "player_name": player_name,
                        "age": age,
                        "market_value": market_value,
                        "nationality": nationality,
                        "player_url": player_url,
                    }
                )
    return players


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def scrape_competition(competition_url, delay=1.0):
    session = requests.Session()
    print(f"Fetching competition page: {competition_url}")
    soup = get_soup(session, competition_url)
    teams = extract_teams(soup)
    print(f"Found {len(teams)} teams.")

    all_players = []
    for i, team in enumerate(teams, 1):
        team_url = urljoin(BASE_URL, team["href"])
        team_id = slugify(team["name"]) or team["slug"]
        print(f"[{i}/{len(teams)}] {team['name']} -> {team_url}")
        try:
            team_soup = get_soup(session, team_url)
            uniforms = extract_uniforms(team_soup)
            players = extract_squad(team_soup, team_id, team["name"], uniforms=uniforms)
            print(f"    {len(players)} players found, {len(uniforms)} uniforms found")
            all_players.extend(players)
        except Exception as exc:
            print(f"    ERROR scraping {team_url}: {exc}", file=sys.stderr)
        time.sleep(delay)

    return all_players


def write_csv(players, output_path):
    fieldnames = [
        "team_id",
        "team_name",
        "kits_json",
        "position",
        "number",
        "player_name",
        "age",
        "market_value",
        "nationality",
        "player_url",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(players)
    print(f"Wrote {len(players)} rows to {output_path}")


def load_kits_from_row(row):
    """Read kits_json from a CSV row, with backward compatibility for old CSVs."""
    raw = row.get("kits_json", "")
    if not raw:
        return []

    try:
        kits = json.loads(raw)
    except json.JSONDecodeError:
        return []

    cleaned = []
    for i, kit in enumerate(kits):
        raw_colors = kit.get("colors", [])
        colors = []
        for color in raw_colors:
            if isinstance(color, (list, tuple)) and len(color) == 3:
                try:
                    colors.append(tuple(int(c) for c in color))
                except (TypeError, ValueError):
                    pass
        if not colors:
            continue

        cleaned.append(
            {
                "name": kit.get("name") or (KIT_NAMES[i] if i < len(KIT_NAMES) else f"Kit {i + 1}"),
                "pattern": kit.get("pattern") or "solid",
                "colors": colors,
            }
        )

    return cleaned


def format_colors(colors):
    return "[" + ", ".join(str(tuple(color)) for color in colors) + "]"


def write_kit(f, kit, indent="            "):
    f.write(
        f"{indent}{{\"name\": {kit['name']!r}, "
        f"\"pattern\": {kit['pattern']!r}, "
        f"\"colors\": {format_colors(kit['colors'])}}},\n"
    )


def build_teams_py(csv_path, output_path):
    """Turn a scraped players.csv into a `TEAMS = [...]` python source file."""
    teams = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row["team_id"]
            team = teams.setdefault(
                tid, {"id": tid, "name": row["team_name"], "kits": [], "squad": []}
            )

            if not team["kits"]:
                team["kits"] = load_kits_from_row(row)

            try:
                number = int(row["number"]) if row["number"] else None
            except ValueError:
                number = None
            team["squad"].append(
                {
                    "number": number,
                    "name": row["player_name"],
                    "position": row["position"],
                }
            )

    # auto-number any player missing a shirt number (zerozero.pt often shows "-")
    for team in teams.values():
        used = {p["number"] for p in team["squad"] if p["number"]}
        next_free = 1
        for p in team["squad"]:
            if p["number"] is None:
                while next_free in used:
                    next_free += 1
                p["number"] = next_free
                used.add(next_free)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("TEAMS = [\n")
        for team in teams.values():
            kits = team["kits"] or DEFAULT_KITS
            f.write("    {\n")
            f.write(f"        \"id\": {team['id']!r},\n")
            f.write(f"        \"name\": {team['name']!r},\n")
            f.write("        \"kits\": [\n")
            for kit in kits:
                write_kit(f, kit)
            f.write("        ],\n")
            f.write("        \"gk_kit\": ")
            f.write(
                f"{{\"name\": {DEFAULT_GK_KIT['name']!r}, "
                f"\"pattern\": {DEFAULT_GK_KIT['pattern']!r}, "
                f"\"colors\": {format_colors(DEFAULT_GK_KIT['colors'])}}},\n"
            )
            f.write("        \"squad\": [\n")
            for p in team["squad"]:
                f.write(
                    f"            {{\"number\": {p['number']}, \"name\": {p['name']!r}, "
                    f"\"position\": {p['position']!r}}},\n"
                )
            f.write("        ],\n")
            f.write("    },\n")
        f.write("]\n")
    print(f"Wrote {len(teams)} teams to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Scrape zerozero.pt competition squads.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="Scrape a competition page into a players CSV")
    p_scrape.add_argument("competition_url")
    p_scrape.add_argument("-o", "--output", default="players.csv")
    p_scrape.add_argument(
        "--delay", type=float, default=1.0, help="Seconds to wait between team requests"
    )

    p_build = sub.add_parser("build", help="Convert a players CSV into a TEAMS python file")
    p_build.add_argument("csv_path")
    p_build.add_argument("-o", "--output", default="teams_generated.py")

    args = parser.parse_args()

    if args.command == "scrape":
        players = scrape_competition(args.competition_url, delay=args.delay)
        write_csv(players, args.output)
    elif args.command == "build":
        build_teams_py(args.csv_path, args.output)


if __name__ == "__main__":
    main()
