# Football Tactical Board

An interactive football (soccer) tactics board built in Python with `pygame`,
sized to real pitch dimensions, and deployed as a static web app on
**GitHub Pages** via [`pygbag`](https://github.com/pygame-web/pygbag) (which
compiles the pygame app to WebAssembly).

## What's included

- A pitch drawn to scale: **105m x 68m**, at 10 pixels per meter, with all
  standard markings (halfway line, center circle, penalty areas, goal areas,
  penalty spots/arcs, corner arcs, goals).
- **22 draggable player tokens** (11 per side), each sized consistently with
  the pitch scale (~1.3m "footprint" radius).
- **Team selection** from an embedded team database (`teams_data.py`) — pick
  either side's team independently.
- **Uniform selection** — each team has multiple kits (e.g. Home/Away/Third),
  each with a pattern (`solid`, `stripes`, `hoops`, `halves`) and 1-2 colors.
  Goalkeepers always wear their team's dedicated GK kit.
- **Formation selection** — 4-4-2, 4-3-3, 3-5-2, 4-2-3-1, 5-3-2, 3-4-3 — chosen
  independently per team.
- **Player picker** — click a token (without dragging it) to open that team's
  roster and swap in a different squad player. This updates the token's
  number and the name label shown underneath it.
- Drag-and-drop repositioning, a formation reset (`R` or button), and quit (`Esc`).
- A GitHub Actions workflow that automatically builds and deploys to
  GitHub Pages on every push to `main`.

## Project structure

```
football-tactics-board/
├── main.py                       # app loop, UI (buttons/modals), pitch + token drawing
├── formations.py                  # formation templates -> pitch-position slots
├── teams_data.py                  # embedded team "database" (squads + kits)
├── kit_render.py                   # builds a circular kit-pattern texture for a token
├── requirements.txt                # pygame-ce + pygbag
├── .github/workflows/deploy.yml    # builds with pygbag, deploys to Pages
└── README.md
```

### About the team "database"

`teams_data.py` holds the team/kit/roster data as a plain Python list of
dicts — effectively an embedded, read-only database. That's a deliberate
choice for a static site: GitHub Pages can't run a server-side database, so
everything has to ship as static files that run entirely in the browser.
If you later want teams to be editable/persisted (e.g. user-created squads),
the natural upgrade path is swapping this module for calls to a real backend
or browser storage — the rest of the app only depends on the data shape
(`team["kits"]`, `team["squad"]`, etc.), not on where it comes from.

Team names and kits here are original/fictional, not real clubs, since real
crests/kits are trademarked and licensed.

## Running locally

```bash
pip install -r requirements.txt
python main.py
```

Controls:
- **Left click + drag** a player token to move it.
- **Left click (no drag)** a player token to open its team's roster and swap
  in a different player — updates the token's number and name label.
- **Team / Kit / Formation buttons** above the pitch (one set per side) open
  a picker list.
- **R** — reset both teams to their formation's default positions.
- **Esc** — quit.

## Deploying to GitHub Pages

1. Push this repository to GitHub (see below if you're starting from scratch).
2. In your repo, go to **Settings → Pages** and set **Source** to
   **"GitHub Actions"**.
3. Push to `main` — the included workflow (`.github/workflows/deploy.yml`)
   will:
   - install `pygbag`,
   - run `python -m pygbag --build main.py`, which compiles the app to
     WASM + HTML/JS into `build/web`,
   - publish `build/web` as your GitHub Pages site.
4. Your app will be live at `https://<your-username>.github.io/<repo-name>/`.

### Pushing this project to GitHub for the first time

```bash
cd football-tactics-board
git init
git add .
git commit -m "Initial tactics board: field + 22 players"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

Then flip on GitHub Actions as the Pages source as described above — no need
to manually build or maintain a `gh-pages` branch, CI handles it.

## Testing the web build locally (optional)

You can preview the WASM build in a local browser before pushing:

```bash
pip install pygbag
python -m pygbag main.py
```

This starts a local server (usually `http://localhost:8000`) serving the
same build that will run on GitHub Pages.

## Notes on scale

| Element | Real size | Notes |
|---|---|---|
| Pitch | 105m x 68m | Standard IFAB/FIFA size (not variable min/max range) |
| Penalty area | 16.5m x 40.32m | |
| Goal area | 5.5m x 18.32m | |
| Penalty spot | 11m from goal line | |
| Center circle | 9.15m radius | |
| Goal | 7.32m wide | |
| Player token | ~1.3m radius footprint | chosen for a visible/draggable token at this scale, not an official figure |

## Next steps (not yet built)

- Multiple formation presets (4-3-3, 3-5-2, etc.)
- Drawing arrows/movement paths
- Saving/loading a tactic as JSON
- Ball token
- Mobile touch support tuning
