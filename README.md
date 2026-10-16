# Football Tactical Board

A responsive football tactics board built with native browser HTML, CSS,
JavaScript, and SVG. The active app lives in [`web/`](web/). Its pitch, players,
and annotations are SVG elements; it does not run Pygame or Pygbag. The static
board deploys to GitHub Pages. A small Python server can host the board and
provide Zerozero match-link imports locally or on a web service.

## Features

- A 105 m × 68 m pitch with the usual markings. The display scale adapts to the
  window size, while player positions stay in pitch coordinates.
- Two independently configurable teams, with draggable player tokens, shirt
  numbers, names, outfield kits, and goalkeeper kits.
- Seven formations per side: 4-4-2, 4-3-3, 4-1-2-3, 3-5-2, 4-2-3-1,
  5-3-2, and 3-4-3.
- A player picker for changing the on-field eleven from each club's squad.
- Import a Zerozero match link through the Python server to place both starting
  elevens on the board with match uniforms and recorded substitutions.
- Move players, draw movement arrows, and place or move a ball. Undo the latest
  edit or clear the annotations.
- Save in the browser, import or export a portable version 1 tactic JSON file,
  and export the board as a PNG image.
- Native HTML controls, keyboard actions, and labelled player tokens for
  assistive technology.
- A bundled snapshot of 18 Portuguese clubs and their squads in
  [`web/teams.json`](web/teams.json). Club and player names are real; the data
  and kit patterns are static and may become outdated. The app is not
  affiliated with those clubs.

## Run locally

Use Python 3.12 for the server:

```bash
python tools/serve.py
```

Open `http://127.0.0.1:8000/`. The server serves [`web/`](web/) and provides
the same-origin `/api/match` route for Zerozero links. It uses Python's
standard library and the project's [`match_import.py`](match_import.py) and
[`match_board.py`](match_board.py), with no package installation. Set a different
port with `python tools/serve.py --port 8001`. For web hosting, the server also
accepts `PORT` from the environment and `--host 0.0.0.0`.

Node.js 22 or newer is used for browser code checks and tests:

```bash
npm run check
npm test
```

The app has no JavaScript package dependencies or bundling step. You can also
run `npm run dev` to start the local server. Opening `web/index.html` as a
`file:` URL will not load `teams.json` in some browsers; use the server.

## Controls

| Action | Mouse / touch | Keyboard |
| --- | --- | --- |
| Move a player | Drag the token | Focus a token; arrow keys move by 0.5 m, or 2 m with `Shift` |
| Change an on-field player | Select a token and choose from the squad | Focus a token and press `Enter` or `Space` |
| Switch a substituted player | Select its gold switch badge | Focus the badge and press `Enter` or `Space` |
| Change team, kit, or formation | Use the labelled selectors above the pitch | Use the native selectors |
| Import a Zerozero match | Paste the link in **Import a match** and select **Import link** | `Enter` submits the link |
| Choose move, arrow, or ball mode | Select the mode above the pitch | Focus and activate a mode button |
| Undo the latest edit | Select **Undo** | `Ctrl+Z` |
| Clear arrows and ball | Select **Clear annotations** | Focus and activate the button |
| Save or reopen a tactic | Select **Save in browser** or **Load saved tactic** | `Ctrl+S` or `Ctrl+O` |
| Import or export JSON | Select **Import JSON** or **Export JSON** | Focus and activate the button |
| Export a PNG | Select **Export PNG** | `Ctrl+E` |
| Return players to formation positions | Select **Reset positions** | `R` |

The player picker is a native dialog. The browser saves the latest tactic in
local storage under `tactical-board.tactic.v1`; JSON and PNG exports download as
`tactic-export.json` and `tactic.png`. **Import JSON** accepts version 1 files
from the earlier desktop app, including imported teams and substitution pairs.
Existing `tactic.json` files can be opened through **Import JSON**.

### Import a Zerozero match

Open the hosted app or start the local server, then paste a match link such as
`https://www.zerozero.pt/jogo/2026-10-10-maritimo-fc-porto/12278041` into
**Import a match**, and select **Import link**. The server downloads the public
match report and returns both teams, starting players, available formations,
uniforms, and recorded substitutions. Missing uniform colors use placeholder
colors. A gold switch badge appears next to a player with a substitution;
select it again to return to the starter. JSON saves and exports preserve the
switch state.

Link import requires an internet connection and a Zerozero match page with
complete lineups. GitHub Pages serves only static files and cannot read
Zerozero's match HTML directly because Zerozero does not allow cross-origin
browser requests. The hosted app described below runs the Python importer and
the browser page at the same origin, so the link import works in the browser.
To move a tactic to GitHub Pages, select **Export JSON** on the hosted or local
app, then **Import JSON** on the Pages board.

### Accessibility and small screens

The team, kit, formation, file, and tool controls are labelled HTML elements.
Players and substitution badges can receive keyboard focus, and the current
action or error appears in a live status message. The SVG pitch supports
pointer dragging, while the player dialog uses a native browser dialog.

On narrow screens (under 680 px), the board shows shirt numbers without player
name labels so tokens remain legible. Names remain available in the player
picker and player labels for assistive technology.

## Data and scraper

[`web/teams.json`](web/teams.json) contains the club identifiers, names, kits,
goalkeeper kits, and squads loaded by the browser app. Editing this file and
republishing updates the bundled snapshot. The live app does not fetch squads
automatically. A Zerozero match import creates separate match-specific team
data within the tactic, which travels with an exported JSON file.

[`teams_data.py`](teams_data.py) remains available to the Python data tools and
legacy desktop implementation. The browser reads `web/teams.json` directly.

The optional [`scraper.py`](scraper.py) can collect a competition's teams and
players from zerozero.pt into a CSV, then convert the CSV to a Python `TEAMS`
file. Install its dependencies separately:

```bash
python -m pip install -r requirements-scraper.txt
python scraper.py scrape "https://www.zerozero.pt/competicao/liga-portuguesa" -o players.csv
python scraper.py build players.csv -o teams_generated.py
```

Review the generated data before replacing `teams_data.py`. The scraper
depends on the source site's current HTML structure, and its output is a
snapshot rather than a live feed.

## Project structure

| Path | Purpose |
| --- | --- |
| [`web/index.html`](web/index.html) | Browser controls and SVG board element |
| [`web/app.js`](web/app.js) | Pointer, keyboard, file, and match import actions |
| [`web/state.js`](web/state.js) | Tactic model, validation, formations, and undo |
| [`web/board-svg.js`](web/board-svg.js) | SVG pitch, uniforms, players, and annotations |
| [`web/teams.json`](web/teams.json) | Bundled club, kit, and squad snapshot |
| [`tools/serve.py`](tools/serve.py) | Static server with a Zerozero match endpoint |
| [`render.yaml`](render.yaml) | Render web service deployment configuration |
| [`match_import.py`](match_import.py) | Fetch and parse a Zerozero match report |
| [`match_board.py`](match_board.py) | Validate and normalize imported match teams |
| [`scraper.py`](scraper.py) | Optional competition scraper and data generator |
| [`requirements-scraper.txt`](requirements-scraper.txt) | Optional scraper dependencies |
| [`tests/`](tests/) | Match parser, local server, and legacy Python checks |
| [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) | Pull request checks and GitHub Pages deployment |

The older Pygame code in `main.py` and its supporting modules remains in the
repository for reference; the active browser app and Pages deployment use
`web/`.

## Deploy to GitHub Pages

1. In the repository's **Settings → Pages**, select **GitHub Actions** as the
   source.
2. Run `npm run check` and `npm test`. Check the Python match service with
   `python -m unittest tests.test_match_import tests.test_match_board tests.test_data_and_formations tests.test_serve -v`.
3. Push to `main`, or start the workflow manually. After the checks pass, the
   workflow publishes `web/` directly to GitHub Pages. Pull requests run the
   checks without publishing.

The published URL follows the pattern
`https://<your-username>.github.io/<repo-name>/`.

GitHub Pages cannot run `/api/match`; link import requires a Python web service.

## Deploy with browser link import

[`render.yaml`](render.yaml) defines a Render web service that serves both the
board and `/api/match` from the same address. To publish it:

1. Push this repository, including `render.yaml`, to GitHub.
2. In the Render dashboard, choose **New → Blueprint**, connect the GitHub
   repository, and deploy the Blueprint. The configuration uses Render's Free
   web service plan and starts `tools/serve.py` on Render's `PORT`.
3. Open the service's `https://<service-name>.onrender.com/` address. Paste a
   Zerozero match URL into **Import a match** and select **Import link**.

Use the Render address as the live board when you want link import. The GitHub
Pages address continues to serve the static board. Render's Free service may
take about a minute to wake after 15 minutes without traffic. Match import also
depends on Zerozero allowing requests from the hosting service; if Zerozero
changes its page or blocks the host, the app displays an import error.

## Pitch dimensions

| Element | Size |
| --- | --- |
| Pitch | 105 m × 68 m |
| Penalty area | 16.5 m × 40.32 m |
| Goal area | 5.5 m × 18.32 m |
| Penalty spot | 11 m from the goal line |
| Center circle | 9.15 m radius |
| Goal | 7.32 m wide |

Player token size is a drawing choice, not a rule of the game.
