"""
Football Tactical Board (responsive)
-------------------------------------
Same app as before, but the pitch, UI panel, fonts and player tokens now all
scale to the actual window size instead of a fixed 1200x830-ish canvas. This
makes it work on any monitor size, in a resized browser tab (pygbag), and on
narrow phone screens.

How the responsiveness works
-----------------------------
- All the *real-world* pitch numbers (105m x 68m, penalty box, etc.) stay as
  they were -- those are facts about football, not about pixels.
- Every *pixel* number that used to be a fixed module-level constant
  (SCALE, SCREEN_W, SCREEN_H, MARGIN_SIDE, TOP_PANEL_H, player radius in
  px, font sizes) now lives on a single `Layout` object that is recomputed
  from the current window size:
      scale = how many px per meter fits in the available space
      offset_x/offset_y = where the pitch is centered/letterboxed
  Player positions are stored in meters (x_m, y_m), so when `Layout`
  changes, every token, line, and button just re-projects to new pixel
  coordinates automatically -- nothing needs to be rescaled by hand.
- The pygame window is created with `pygame.RESIZABLE`. On desktop this
  lets the user drag-resize it; in a pygbag/web build, if the surrounding
  page dispatches a canvas resize, pygame receives a `VIDEORESIZE` event
  and we rebuild the layout, fonts, and texture cache to match.

Controls (unchanged):
  - Left click + drag a player token to move it.
  - Left click (no drag) a player token to pick a different squad player.
  - Use the buttons above the pitch to change team / kit / formation.
  - Press R to reset both teams to their formation's default positions.
  - Press ESC to quit (desktop only).
"""

import asyncio
import pygame

from formations import FORMATIONS, outfield_slots, gk_slot, mirror_x
from teams_data import TEAMS
from kit_render import build_token_texture

# ---------------------------------------------------------------------------
# Real-world pitch dimensions (IFAB Laws of the Game, standard size)
# These never change -- they describe the pitch, not the screen.
# ---------------------------------------------------------------------------
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

PENALTY_AREA_DEPTH_M = 16.5
PENALTY_AREA_WIDTH_M = 40.32
GOAL_AREA_DEPTH_M = 5.5
GOAL_AREA_WIDTH_M = 18.32
PENALTY_SPOT_DIST_M = 11.0
CENTER_CIRCLE_RADIUS_M = 9.15
CORNER_ARC_RADIUS_M = 1.0
GOAL_WIDTH_M = 7.32
GOAL_DEPTH_M = 2.0

PLAYER_RADIUS_M = 1.3

FPS = 60
CLICK_MOVE_THRESHOLD_PX = 6

# ---------------------------------------------------------------------------
# Responsive layout bounds. Tweak these to taste.
# ---------------------------------------------------------------------------
DEFAULT_WINDOW_W = 1300
DEFAULT_WINDOW_H = 780

MIN_WINDOW_W = 360     # smallest window/canvas we try to support (phones)
MIN_WINDOW_H = 480

MIN_SCALE = 3.2        # px/m floor -- below this, tokens/text stop shrinking
MAX_SCALE = 14.0       # px/m ceiling -- stop the pitch getting absurd on 4K/TVs

MARGIN_FRACTION = 0.03      # side margin as a fraction of window width
TOP_PANEL_FRACTION = 0.16   # top UI panel height as a fraction of window height
TOP_PANEL_MIN = 96
TOP_PANEL_MAX = 170

BASE_SCALE_FOR_FONTS = 10.0  # the scale the original fixed layout used to be)

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
COLOR_BG = (32, 96, 46)
COLOR_PITCH = (46, 125, 66)
COLOR_PITCH_ALT = (42, 118, 61)
COLOR_LINES = (240, 240, 240)
COLOR_PANEL_BG = (24, 28, 26)
COLOR_BUTTON = (52, 58, 55)
COLOR_BUTTON_HOVER = (70, 78, 74)
COLOR_BUTTON_TEXT = (235, 235, 235)
COLOR_MODAL_OVERLAY = (0, 0, 0, 150)
COLOR_MODAL_PANEL = (40, 44, 42)
COLOR_MODAL_ROW_HOVER = (66, 72, 69)
COLOR_MODAL_TEXT = (235, 235, 235)


def brightness(color):
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


# ---------------------------------------------------------------------------
# Layout: the one place that knows about pixels. Recomputed on resize.
# ---------------------------------------------------------------------------
class Layout:
    def __init__(self, window_w, window_h):
        self.recompute(window_w, window_h)

    def recompute(self, window_w, window_h):
        self.window_w = max(int(window_w), MIN_WINDOW_W)
        self.window_h = max(int(window_h), MIN_WINDOW_H)

        self.top_panel_h = int(
            max(TOP_PANEL_MIN, min(TOP_PANEL_MAX, self.window_h * TOP_PANEL_FRACTION))
        )
        self.margin_side = int(max(16, self.window_w * MARGIN_FRACTION))

        avail_w = self.window_w - 2 * self.margin_side
        avail_h = self.window_h - self.top_panel_h - self.margin_side

        # Fit the pitch into whatever space is left, without distorting it.
        scale_w = avail_w / PITCH_LENGTH_M
        scale_h = avail_h / PITCH_WIDTH_M
        self.scale = max(MIN_SCALE, min(MAX_SCALE, scale_w, scale_h))

        self.field_px_w = PITCH_LENGTH_M * self.scale
        self.field_px_h = PITCH_WIDTH_M * self.scale

        # Center the pitch (letterbox) in any extra leftover space.
        self.offset_x = (self.window_w - self.field_px_w) / 2
        self.offset_y = self.top_panel_h + (avail_h - self.field_px_h) / 2

    def m_to_px(self, x_m, y_m):
        return (self.offset_x + x_m * self.scale, self.offset_y + y_m * self.scale)

    def player_radius_px(self):
        return max(7, int(PLAYER_RADIUS_M * self.scale))

    def font_scale(self):
        """Relative size multiplier vs. the original fixed-scale design."""
        return max(0.6, min(1.6, self.scale / BASE_SCALE_FOR_FONTS))


# Global layout instance -- replaced (recomputed) on every resize.
LAYOUT = Layout(DEFAULT_WINDOW_W, DEFAULT_WINDOW_H)


def build_fonts(layout):
    fs = layout.font_scale()
    return {
        "number": pygame.font.SysFont("arial", max(10, int(15 * fs)), bold=True),
        "name": pygame.font.SysFont("arial", max(9, int(12 * fs)), bold=True),
        "button": pygame.font.SysFont("arial", max(10, int(14 * fs)), bold=True),
        "modal_title": pygame.font.SysFont("arial", max(12, int(18 * fs)), bold=True),
        "modal_row": pygame.font.SysFont("arial", max(10, int(14 * fs))),
        "hint": pygame.font.SysFont("arial", max(9, int(13 * fs))),
    }


# ---------------------------------------------------------------------------
# Player token
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, x_m, y_m, number, name, position, side):
        self.x_m = x_m
        self.y_m = y_m
        self.home_m = (x_m, y_m)
        self.number = number
        self.name = name
        self.position = position
        self.is_gk = position == "GK"
        self.side = side

    @property
    def radius_px(self):
        return LAYOUT.player_radius_px()

    @property
    def pos_px(self):
        return LAYOUT.m_to_px(self.x_m, self.y_m)

    def contains_point(self, px, py):
        cx, cy = self.pos_px
        r = self.radius_px
        return (px - cx) ** 2 + (py - cy) ** 2 <= r ** 2

    def set_pos_from_px(self, px, py):
        min_x, min_y = LAYOUT.m_to_px(0, 0)
        max_x, max_y = LAYOUT.m_to_px(PITCH_LENGTH_M, PITCH_WIDTH_M)
        px = max(min_x, min(max_x, px))
        py = max(min_y, min(max_y, py))
        self.x_m = (px - LAYOUT.offset_x) / LAYOUT.scale
        self.y_m = (py - LAYOUT.offset_y) / LAYOUT.scale

    def reset(self):
        self.x_m, self.y_m = self.home_m

    def draw(self, surface, fonts, texture_cache):
        kit = self.side.current_kit_for(self)
        radius_px = self.radius_px
        # Include radius in the cache key so a resize (different radius)
        # doesn't reuse a texture sized for the old scale.
        tex_key = (self.side.team["id"], "GK" if self.is_gk else kit["name"], radius_px)
        tex = texture_cache.get(tex_key)
        if tex is None:
            tex = build_token_texture(kit["pattern"], kit["colors"], radius_px * 2)
            texture_cache[tex_key] = tex

        cx, cy = self.pos_px
        cx, cy = int(cx), int(cy)

        shadow = pygame.Surface((radius_px * 2 + 8, radius_px * 2 + 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
        surface.blit(shadow, (cx - shadow.get_width() // 2, cy - shadow.get_height() // 2 + 4))

        surface.blit(tex, (cx - radius_px, cy - radius_px))

        text_color = (255, 255, 255) if brightness(kit["colors"][0]) < 140 else (25, 25, 25)
        num_surf = fonts["number"].render(str(self.number), True, text_color)
        surface.blit(num_surf, num_surf.get_rect(center=(cx, cy)))

        name_surf = fonts["name"].render(self.name, True, (255, 255, 255))
        name_rect = name_surf.get_rect(center=(cx, cy + radius_px + 11))
        bg = pygame.Surface((name_rect.width + 8, name_rect.height + 4), pygame.SRCALPHA)
        pygame.draw.rect(bg, (0, 0, 0, 150), bg.get_rect(), border_radius=4)
        surface.blit(bg, (name_rect.x - 4, name_rect.y - 2))
        surface.blit(name_surf, name_rect)


# ---------------------------------------------------------------------------
# One side (Team A or Team B): owns team/kit/formation state + its 11 tokens
# ---------------------------------------------------------------------------
class TeamSide:
    def __init__(self, label, team, x_dir):
        self.label = label       # "A" or "B", used for UI/layout only
        self.x_dir = x_dir       # +1: attacks left->right, -1: attacks right->left
        self.team = team
        self.kit_index = 0
        self.formation_name = "4-4-2"
        self.players = []
        self.build_players_from_squad()

    def _mirror(self, x_m):
        return mirror_x(x_m) if self.x_dir == -1 else x_m

    def formation_position_counts(self, formation_name=None):
        rows = FORMATIONS[formation_name or self.formation_name]
        return {
            "DF": rows[0],
            "MF": sum(rows[1:-1]),
            "FW": rows[-1],
        }

    def players_for_formation(self, formation_name=None):
        squad = self.team["squad"]
        counts = self.formation_position_counts(formation_name)

        picked = []
        used_numbers = set()

        for position in ("DF", "MF", "FW"):
            position_players = [p for p in squad if p["position"] == position]
            for pdata in position_players[:counts[position]]:
                picked.append(pdata)
                used_numbers.add(pdata["number"])

        needed = 10 - len(picked)
        if needed > 0:
            fallback = [
                p for p in squad
                if p["position"] != "GK" and p["number"] not in used_numbers
            ]
            picked.extend(fallback[:needed])

        return picked[:10]

    def build_players_from_squad(self):
        squad = self.team["squad"]
        gk = next(p for p in squad if p["position"] == "GK")
        outfield = self.players_for_formation(self.formation_name)

        self.players = []
        gx, gy = gk_slot()
        self.players.append(Player(self._mirror(gx), gy, gk["number"], gk["name"], gk["position"], self))

        for (x, y), pdata in zip(outfield_slots(self.formation_name), outfield):
            self.players.append(Player(self._mirror(x), y, pdata["number"], pdata["name"], pdata["position"], self))

    def apply_formation(self, formation_name):
        self.formation_name = formation_name
        self.build_players_from_squad()

    def set_team(self, team):
        self.team = team
        self.kit_index = 0
        self.build_players_from_squad()

    def set_kit(self, index):
        self.kit_index = index

    def current_kit_for(self, player):
        if player.is_gk:
            return self.team["gk_kit"]
        return self.team["kits"][self.kit_index]

    def reset_positions(self):
        for p in self.players:
            p.reset()


# ---------------------------------------------------------------------------
# Simple UI: buttons + modal option lists (no external GUI library needed)
# All rects below are derived from LAYOUT, so they move/resize automatically.
# ---------------------------------------------------------------------------
class Button:
    def __init__(self, rect, text, action):
        self.rect = pygame.Rect(rect)
        self.base_text = text
        self.text = text
        self.action = action

    def draw(self, surface, font, mouse_pos):
        hovered = self.rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, COLOR_BUTTON_HOVER if hovered else COLOR_BUTTON, self.rect, border_radius=6)
        pygame.draw.rect(surface, (90, 96, 92), self.rect, width=1, border_radius=6)

        self.text = self.base_text
        text_surf = font.render(self.text, True, COLOR_BUTTON_TEXT)
        max_w = self.rect.width - 12
        if text_surf.get_width() > max_w:
            while self.text and font.size(self.text + "...")[0] > max_w:
                self.text = self.text[:-1]
            text_surf = font.render(self.text + "...", True, COLOR_BUTTON_TEXT)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))


def build_buttons(side_a, side_b):
    """Button geometry scales with window width and the layout's margin,
    so it stays proportionate whether the window is 1300px or 380px wide."""
    fs = LAYOUT.font_scale()
    btn_w = max(150, int(min(230, LAYOUT.window_w * 0.34)))
    btn_h = max(22, int(28 * fs))
    gap = max(4, int(6 * fs))
    buttons = []

    ax = LAYOUT.margin_side
    bx = LAYOUT.window_w - LAYOUT.margin_side - btn_w
    y0 = max(8, int(14 * fs))

    for side, x in ((side_a, ax), (side_b, bx)):
        buttons.append(Button((x, y0, btn_w, btn_h),
                               f"Team: {side.team['name']}",
                               {"kind": "open_team_modal", "side": side}))
        buttons.append(Button((x, y0 + (btn_h + gap), btn_w, btn_h),
                               f"Kit: {side.team['kits'][side.kit_index]['name']}",
                               {"kind": "open_kit_modal", "side": side}))
        buttons.append(Button((x, y0 + 2 * (btn_h + gap), btn_w, btn_h),
                               f"Formation: {side.formation_name}",
                               {"kind": "open_formation_modal", "side": side}))

    reset_w = max(120, int(150 * fs))
    buttons.append(Button((LAYOUT.window_w // 2 - reset_w // 2, y0 + (btn_h + gap) // 2, reset_w, btn_h),
                           "Reset positions (R)",
                           {"kind": "reset"}))
    return buttons


class Modal:
    """A centered list of clickable options, with a translucent backdrop.
    Sized/centered from LAYOUT so it works on small screens too."""

    def __init__(self, kind, side, options, player=None):
        self.kind = kind
        self.side = side
        self.options = options
        self.player = player

        fs = LAYOUT.font_scale()
        row_h = max(24, int(30 * fs))
        width = max(240, min(int(LAYOUT.window_w * 0.85), 340))
        height = min(int(LAYOUT.window_h * 0.85), 60 + row_h * len(options))
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (LAYOUT.window_w // 2, LAYOUT.window_h // 2)

        self.row_h = row_h
        self.rows = []
        y = self.rect.y + 50
        for label, value in options:
            row_rect = pygame.Rect(self.rect.x + 10, y, self.rect.width - 20, row_h - 4)
            self.rows.append((row_rect, label, value))
            y += row_h

        self.close_rect = pygame.Rect(self.rect.right - 34, self.rect.y + 8, 24, 24)

    def title(self):
        return {
            "team": "Choose team",
            "kit": "Choose uniform",
            "formation": "Choose formation",
            "player": "Choose player",
        }[self.kind]

    def draw(self, surface, fonts, mouse_pos):
        overlay = pygame.Surface((LAYOUT.window_w, LAYOUT.window_h), pygame.SRCALPHA)
        overlay.fill(COLOR_MODAL_OVERLAY)
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, COLOR_MODAL_PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 106, 102), self.rect, width=1, border_radius=8)

        title_surf = fonts["modal_title"].render(self.title(), True, COLOR_MODAL_TEXT)
        surface.blit(title_surf, (self.rect.x + 16, self.rect.y + 14))

        pygame.draw.rect(surface, (90, 40, 40), self.close_rect, border_radius=4)
        x_surf = fonts["modal_row"].render("X", True, (240, 240, 240))
        surface.blit(x_surf, x_surf.get_rect(center=self.close_rect.center))

        for row_rect, label, _value in self.rows:
            hovered = row_rect.collidepoint(mouse_pos)
            if hovered:
                pygame.draw.rect(surface, COLOR_MODAL_ROW_HOVER, row_rect, border_radius=4)
            label_surf = fonts["modal_row"].render(label, True, COLOR_MODAL_TEXT)
            surface.blit(label_surf, (row_rect.x + 8, row_rect.centery - label_surf.get_height() // 2))

    def handle_click(self, pos):
        if self.close_rect.collidepoint(pos):
            return "close", None
        for row_rect, _label, value in self.rows:
            if row_rect.collidepoint(pos):
                return "select", value
        if not self.rect.collidepoint(pos):
            return "close", None
        return None, None


def kit_option_label(kit):
    return f"{kit['name']} ({kit['pattern']})"


def build_team_modal(side):
    options = [(t["name"], t) for t in TEAMS]
    return Modal("team", side, options)


def build_kit_modal(side):
    options = [(kit_option_label(k), i) for i, k in enumerate(side.team["kits"])]
    return Modal("kit", side, options)


def build_formation_modal(side):
    options = [(name, name) for name in FORMATIONS.keys()]
    return Modal("formation", side, options)


def build_player_modal(side, player):
    same_position = [p for p in side.team["squad"] if p["position"] == player.position]
    other_positions = [p for p in side.team["squad"] if p["position"] != player.position]

    squad_sorted = (
        sorted(same_position, key=lambda p: p["number"]) +
        sorted(other_positions, key=lambda p: (p["position"] != "GK", p["position"], p["number"]))
    )

    options = [(f"#{p['number']} {p['name']} ({p['position']})", p) for p in squad_sorted]
    return Modal("player", side, options, player=player)


# ---------------------------------------------------------------------------
# Pitch drawing -- every measurement comes from LAYOUT now.
# ---------------------------------------------------------------------------
def draw_pitch(surface):
    surface.fill(COLOR_BG)

    top_panel_rect = pygame.Rect(0, 0, LAYOUT.window_w, LAYOUT.top_panel_h)
    pygame.draw.rect(surface, COLOR_PANEL_BG, top_panel_rect)

    field_rect = pygame.Rect(*LAYOUT.m_to_px(0, 0), LAYOUT.field_px_w, LAYOUT.field_px_h)

    line_w = max(1, round(3 * LAYOUT.scale / BASE_SCALE_FOR_FONTS))

    stripe_count = 12
    stripe_w = LAYOUT.field_px_w / stripe_count
    for i in range(stripe_count):
        color = COLOR_PITCH if i % 2 == 0 else COLOR_PITCH_ALT
        rect = pygame.Rect(field_rect.x + i * stripe_w, field_rect.y, stripe_w + 1, field_rect.height)
        pygame.draw.rect(surface, color, rect)

    def line(p1_m, p2_m, width=line_w):
        pygame.draw.line(surface, COLOR_LINES, LAYOUT.m_to_px(*p1_m), LAYOUT.m_to_px(*p2_m), width)

    def circle(center_m, radius_m, width=line_w):
        cx, cy = LAYOUT.m_to_px(*center_m)
        pygame.draw.circle(surface, COLOR_LINES, (int(cx), int(cy)), int(radius_m * LAYOUT.scale), width)

    def rect_outline(x_m, y_m, w_m, h_m, width=line_w):
        x, y = LAYOUT.m_to_px(x_m, y_m)
        pygame.draw.rect(surface, COLOR_LINES, (x, y, w_m * LAYOUT.scale, h_m * LAYOUT.scale), width)

    pygame.draw.rect(surface, COLOR_LINES, field_rect, line_w)
    line((PITCH_LENGTH_M / 2, 0), (PITCH_LENGTH_M / 2, PITCH_WIDTH_M))
    circle((PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2), CENTER_CIRCLE_RADIUS_M)
    pygame.draw.circle(surface, COLOR_LINES, LAYOUT.m_to_px(PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2), max(2, line_w + 1))

    for x0, direction in ((0, 1), (PITCH_LENGTH_M, -1)):
        pa_w = PENALTY_AREA_DEPTH_M * direction
        pa_y = (PITCH_WIDTH_M - PENALTY_AREA_WIDTH_M) / 2
        rect_outline(x0 if direction == 1 else x0 + pa_w, pa_y, abs(pa_w), PENALTY_AREA_WIDTH_M)

        ga_w = GOAL_AREA_DEPTH_M * direction
        ga_y = (PITCH_WIDTH_M - GOAL_AREA_WIDTH_M) / 2
        rect_outline(x0 if direction == 1 else x0 + ga_w, ga_y, abs(ga_w), GOAL_AREA_WIDTH_M)

        spot_x = x0 + PENALTY_SPOT_DIST_M * direction
        pygame.draw.circle(surface, COLOR_LINES, LAYOUT.m_to_px(spot_x, PITCH_WIDTH_M / 2), max(2, line_w + 1))

        arc_rect = pygame.Rect(0, 0, CENTER_CIRCLE_RADIUS_M * 2 * LAYOUT.scale, CENTER_CIRCLE_RADIUS_M * 2 * LAYOUT.scale)
        arc_rect.center = LAYOUT.m_to_px(spot_x, PITCH_WIDTH_M / 2)
        if direction == 1:
            start_angle, end_angle = -0.93, 0.93
        else:
            start_angle, end_angle = 3.1416 - 0.93, 3.1416 + 0.93
        pygame.draw.arc(surface, COLOR_LINES, arc_rect, start_angle, end_angle, line_w)

        goal_y = (PITCH_WIDTH_M - GOAL_WIDTH_M) / 2
        goal_w = GOAL_DEPTH_M * direction
        rect_outline(x0 if direction == 1 else x0 + goal_w, goal_y, abs(goal_w), GOAL_WIDTH_M, width=max(1, line_w - 1))

    for cx_m, cy_m, a_start, a_end in (
        (0, PITCH_WIDTH_M, 0, 1.5708),
        (0, 0, -1.5708, 0),
        (PITCH_LENGTH_M, PITCH_WIDTH_M, 1.5708, 3.1416),
        (PITCH_LENGTH_M, 0, 3.1416, 4.7124),
    ):
        r = CORNER_ARC_RADIUS_M * LAYOUT.scale
        rect = pygame.Rect(0, 0, r * 2, r * 2)
        rect.center = LAYOUT.m_to_px(cx_m, cy_m)
        pygame.draw.arc(surface, COLOR_LINES, rect, a_start, a_end, max(1, line_w - 1))


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
async def main():
    global LAYOUT

    pygame.init()
    pygame.display.set_caption("Football Tactical Board")

    # RESIZABLE lets the user drag-resize on desktop, and lets a pygbag/web
    # build react to VIDEORESIZE events if the host page resizes the canvas.
    screen = pygame.display.set_mode((LAYOUT.window_w, LAYOUT.window_h), pygame.RESIZABLE)

    clock = pygame.time.Clock()
    fonts = build_fonts(LAYOUT)

    side_a = TeamSide("A", TEAMS[0], x_dir=1)
    side_b = TeamSide("B", TEAMS[1], x_dir=-1)

    texture_cache = {}
    modal = None
    dragged_player = None
    drag_start_pos = (0, 0)
    drag_moved = False

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        buttons = build_buttons(side_a, side_b)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                LAYOUT.recompute(event.w, event.h)
                screen = pygame.display.set_mode((LAYOUT.window_w, LAYOUT.window_h), pygame.RESIZABLE)
                fonts = build_fonts(LAYOUT)
                texture_cache.clear()  # old textures were sized for the old scale
                if modal is not None:
                    # Rebuild the open modal so it re-centers at the new size.
                    modal = {
                        "team": build_team_modal,
                        "kit": build_kit_modal,
                        "formation": build_formation_modal,
                    }.get(modal.kind, lambda s: None)(modal.side) if modal.kind != "player" else \
                        build_player_modal(modal.side, modal.player)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r and modal is None:
                    side_a.reset_positions()
                    side_b.reset_positions()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if modal is not None:
                    action, value = modal.handle_click(event.pos)
                    if action == "close":
                        modal = None
                    elif action == "select":
                        if modal.kind == "team":
                            modal.side.set_team(value)
                        elif modal.kind == "kit":
                            modal.side.set_kit(value)
                        elif modal.kind == "formation":
                            modal.side.apply_formation(value)
                        elif modal.kind == "player":
                            modal.player.number = value["number"]
                            modal.player.name = value["name"]
                            modal.player.position = value["position"]
                            modal.player.is_gk = value["position"] == "GK"
                        modal = None
                    continue

                clicked_button = next((b for b in buttons if b.rect.collidepoint(event.pos)), None)
                if clicked_button is not None:
                    act = clicked_button.action
                    if act["kind"] == "open_team_modal":
                        modal = build_team_modal(act["side"])
                    elif act["kind"] == "open_kit_modal":
                        modal = build_kit_modal(act["side"])
                    elif act["kind"] == "open_formation_modal":
                        modal = build_formation_modal(act["side"])
                    elif act["kind"] == "reset":
                        side_a.reset_positions()
                        side_b.reset_positions()
                    continue

                for p in reversed(side_a.players + side_b.players):
                    if p.contains_point(*event.pos):
                        dragged_player = p
                        drag_start_pos = event.pos
                        drag_moved = False
                        break

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragged_player is not None:
                    if not drag_moved:
                        modal = build_player_modal(dragged_player.side, dragged_player)
                    dragged_player = None

            elif event.type == pygame.MOUSEMOTION:
                if dragged_player is not None:
                    dx = event.pos[0] - drag_start_pos[0]
                    dy = event.pos[1] - drag_start_pos[1]
                    if dx * dx + dy * dy > CLICK_MOVE_THRESHOLD_PX ** 2:
                        drag_moved = True
                    dragged_player.set_pos_from_px(*event.pos)

        draw_pitch(screen)
        for p in side_a.players + side_b.players:
            p.draw(screen, fonts, texture_cache)

        for b in buttons:
            b.draw(screen, fonts["button"], mouse_pos)

        hint = fonts["hint"].render(
            "Drag = move  |  Click = pick player  |  R = reset positions  |  Esc = quit",
            True, (230, 230, 230))
        screen.blit(hint, (LAYOUT.margin_side, LAYOUT.window_h - hint.get_height() - 6))

        if modal is not None:
            modal.draw(screen, fonts, mouse_pos)

        pygame.display.flip()
        clock.tick(FPS)
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())