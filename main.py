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

Controls:
  - Left click + drag a player token to move it.
  - Right click a player token to pick a different squad player.
  - Use the buttons above the pitch to change team / kit / formation.
  - Press R to reset both teams to their formation's default positions.
  - Press ESC to quit (desktop only).
"""

import asyncio
import math
import sys
import pygame

from formations import FORMATIONS, outfield_slots, gk_slot, mirror_x
from teams_data import TEAMS
from kit_render import build_token_texture
import tactic_io
import web_accessibility
import match_import
import match_board

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
MAX_ARROWS = 200

# ---------------------------------------------------------------------------
# Responsive layout bounds. Tweak these to taste.
# ---------------------------------------------------------------------------
DEFAULT_WINDOW_W = 1300
DEFAULT_WINDOW_H = 780

MIN_WINDOW_W = 360     # smallest window/canvas we try to support (phones)
MIN_WINDOW_H = 480

MIN_SCALE = 2.5        # allow the whole pitch to fit on narrow screens
MAX_SCALE = 14.0       # px/m ceiling -- stop the pitch getting absurd on 4K/TVs
MOBILE_BREAKPOINT = 680

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
        if self.window_w < MOBILE_BREAKPOINT:
            self.top_panel_h = 196
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
    mobile = layout.window_w < MOBILE_BREAKPOINT
    return {
        "number": pygame.font.SysFont("arial", max(10, int(15 * fs)), bold=True),
        "name": pygame.font.SysFont("arial", max(9, int(12 * fs)), bold=True),
        "button": pygame.font.SysFont("arial", 13 if mobile else max(10, int(14 * fs)), bold=True),
        "modal_title": pygame.font.SysFont("arial", 16 if mobile else max(12, int(18 * fs)), bold=True),
        "modal_row": pygame.font.SysFont("arial", 14 if mobile else max(10, int(14 * fs))),
        "hint": pygame.font.SysFont("arial", 10 if mobile else max(9, int(13 * fs))),
    }


# ---------------------------------------------------------------------------
# Player token
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, x_m, y_m, number, name, position, side, is_gk=False):
        self.x_m = x_m
        self.y_m = y_m
        self.home_m = (x_m, y_m)
        self.number = number
        self.name = name
        self.position = position
        # Goalkeeper is a property of the pitch slot, not of a replacement's
        # natural position in the squad data.
        self.is_gk = is_gk
        self.side = side
        self.player_id = None
        # A match substitution belongs to this board slot. Both identities
        # stay available so the small badge can switch them in either direction.
        self.switch_pair = None
        self.switch_active = False

    @property
    def radius_px(self):
        return LAYOUT.player_radius_px()

    @property
    def pos_px(self):
        return LAYOUT.m_to_px(self.x_m, self.y_m)

    def contains_point(self, px, py):
        cx, cy = self.pos_px
        r = max(18, self.radius_px) if LAYOUT.window_w < MOBILE_BREAKPOINT else self.radius_px
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

    def switch_badge_rect(self):
        if self.switch_pair is None:
            return None
        cx, cy = self.pos_px
        radius = self.radius_px
        size = 21 if LAYOUT.window_w < MOBILE_BREAKPOINT else 19
        return pygame.Rect(int(cx + radius - 5), int(cy - radius - size + 5), size, size)

    def switch_player(self):
        if self.switch_pair is None:
            return False
        self.switch_active = not self.switch_active
        identity = self.switch_pair["after" if self.switch_active else "before"]
        self.name = identity["name"]
        self.number = identity["number"]
        self.position = identity["position"]
        self.player_id = identity.get("id")
        return True

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
        number_key = ("number", self.number, radius_px, text_color)
        num_surf = texture_cache.get(number_key)
        if num_surf is None:
            outline_px = 1 if radius_px < 12 else 2
            outline_color = (0, 0, 0) if text_color == (255, 255, 255) else (255, 255, 255)
            number_text = str(self.number)
            fill = fonts["number"].render(number_text, True, text_color)
            outline = fonts["number"].render(number_text, True, outline_color)
            num_surf = pygame.Surface(
                (fill.get_width() + outline_px * 2, fill.get_height() + outline_px * 2),
                pygame.SRCALPHA,
            )
            for dx in range(-outline_px, outline_px + 1):
                for dy in range(-outline_px, outline_px + 1):
                    if dx or dy:
                        num_surf.blit(outline, (outline_px + dx, outline_px + dy))
            num_surf.blit(fill, (outline_px, outline_px))
            texture_cache[number_key] = num_surf
        surface.blit(num_surf, num_surf.get_rect(center=(cx, cy)))

        if LAYOUT.window_w >= MOBILE_BREAKPOINT:
            name_surf = fonts["name"].render(self.name, True, (255, 255, 255))
            name_rect = name_surf.get_rect(center=(cx, cy + radius_px + 11))
            bg = pygame.Surface((name_rect.width + 8, name_rect.height + 4), pygame.SRCALPHA)
            pygame.draw.rect(bg, (0, 0, 0, 150), bg.get_rect(), border_radius=4)
            surface.blit(bg, (name_rect.x - 4, name_rect.y - 2))
            surface.blit(name_surf, name_rect)

        badge = self.switch_badge_rect()
        if badge is not None:
            pygame.draw.ellipse(surface, (20, 25, 24), badge.inflate(3, 3))
            pygame.draw.ellipse(surface, (244, 184, 54), badge)
            middle = badge.centery
            left, right = badge.x + 4, badge.right - 4
            pygame.draw.line(surface, (20, 25, 24), (left, middle - 3), (right, middle - 3), 2)
            pygame.draw.line(surface, (20, 25, 24), (right, middle + 3), (left, middle + 3), 2)
            pygame.draw.polygon(surface, (20, 25, 24),
                                [(right, middle - 6), (right + 2, middle - 3), (right, middle)])
            pygame.draw.polygon(surface, (20, 25, 24),
                                [(left, middle), (left - 2, middle + 3), (left, middle + 6)])


# ---------------------------------------------------------------------------
# One side (Team A or Team B): owns team/kit/formation state + its 11 tokens
# ---------------------------------------------------------------------------
class TeamSide:
    def __init__(self, label, team, x_dir):
        self.label = label       # "A" or "B", used for UI/layout only
        self.x_dir = x_dir       # +1: attacks left->right, -1: attacks right->left
        self.team = team
        self.kit_index = 0
        self.formation_name = team.get("formation", "4-4-2")
        if self.formation_name not in FORMATIONS:
            self.formation_name = "4-3-3" if team.get("starting_ids") else "4-4-2"
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
        if self.team.get("starting_ids"):
            by_id = {p.get("id"): p for p in squad}
            starters = [by_id[player_id] for player_id in self.team["starting_ids"]]
            return [p for p in starters if p["position"] != "GK"]
        counts = self.formation_position_counts(formation_name)

        picked = []
        goalkeeper = next(p for p in squad if p["position"] == "GK")
        used_numbers = {goalkeeper["number"]}

        for position in ("DF", "MF", "FW"):
            position_players = [p for p in squad if p["position"] == position]
            for pdata in position_players:
                if pdata["number"] in used_numbers:
                    continue
                picked.append(pdata)
                used_numbers.add(pdata["number"])
                if sum(p["position"] == position for p in picked) == counts[position]:
                    break

        needed = 10 - len(picked)
        if needed > 0:
            fallback = [
                p for p in squad
                if p["position"] != "GK" and p["number"] not in used_numbers
            ]
            for pdata in fallback:
                if pdata["number"] in used_numbers:
                    continue
                picked.append(pdata)
                used_numbers.add(pdata["number"])
                if len(picked) == 10:
                    break

        if len(picked) != 10:
            raise ValueError(f"{self.team['name']} has fewer than ten distinct outfield shirt numbers")
        return picked[:10]

    def build_players_from_squad(self):
        squad = self.team["squad"]
        if self.team.get("starting_ids"):
            by_id = {p.get("id"): p for p in squad}
            gk = next(by_id[player_id] for player_id in self.team["starting_ids"]
                      if by_id[player_id]["position"] == "GK")
        else:
            gk = next(p for p in squad if p["position"] == "GK")
        outfield = self.players_for_formation(self.formation_name)

        self.players = []
        gx, gy = gk_slot()
        self.players.append(Player(self._mirror(gx), gy, gk["number"], gk["name"], gk["position"], self, is_gk=True))
        self.players[-1].player_id = gk.get("id")

        for (x, y), pdata in zip(outfield_slots(self.formation_name), outfield):
            self.players.append(Player(self._mirror(x), y, pdata["number"], pdata["name"], pdata["position"], self))
            self.players[-1].player_id = pdata.get("id")

        if self.team.get("substitutions"):
            by_id = {p.get("id"): p for p in squad}
            by_out = {sub["out_id"]: sub for sub in self.team["substitutions"]}
            for player in self.players:
                sub = by_out.get(player.player_id)
                if sub is None or sub["in_id"] not in by_id:
                    continue
                replacement = by_id[sub["in_id"]]
                if (replacement["position"] == "GK") != player.is_gk:
                    continue
                original = by_id[player.player_id]
                player.switch_pair = {
                    "before": dict(original),
                    "after": dict(replacement),
                    "minute": sub.get("minute"),
                }

    def apply_formation(self, formation_name):
        if formation_name not in FORMATIONS:
            raise ValueError(f"Unknown formation: {formation_name}")
        if formation_name == self.formation_name:
            return

        # Reassign the same eleven people to the new slots. Their adjustments
        # relative to the old slots carry over to the new formation.
        available = list(self.players[1:])
        assigned = []
        rows = FORMATIONS[formation_name]
        desired_roles = []
        for row_index, count in enumerate(rows):
            role = "DF" if row_index == 0 else "FW" if row_index == len(rows) - 1 else "MF"
            desired_roles.extend([role] * count)
        for role in desired_roles:
            player = next((p for p in available if p.position == role), available[0])
            available.remove(player)
            assigned.append(player)

        self.formation_name = formation_name
        for player, (x, y) in zip(assigned, outfield_slots(formation_name)):
            dx = player.x_m - player.home_m[0]
            dy = player.y_m - player.home_m[1]
            player.home_m = (self._mirror(x), y)
            player.x_m = max(0, min(PITCH_LENGTH_M, player.home_m[0] + dx))
            player.y_m = max(0, min(PITCH_WIDTH_M, player.home_m[1] + dy))
        self.players = [self.players[0]] + assigned

    def set_team(self, team):
        self.team = team
        self.kit_index = 0
        if team.get("starting_ids"):
            self.formation_name = team.get("formation") or "4-3-3"
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

    def draw(self, surface, font, mouse_pos, focused=False):
        hovered = self.rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, COLOR_BUTTON_HOVER if hovered else COLOR_BUTTON, self.rect, border_radius=6)
        pygame.draw.rect(surface, COLOR_LINES if focused else (90, 96, 92), self.rect,
                         width=2 if focused else 1, border_radius=6)

        self.text = self.base_text
        text_surf = font.render(self.text, True, COLOR_BUTTON_TEXT)
        max_w = self.rect.width - 12
        if text_surf.get_width() > max_w:
            while self.text and font.size(self.text + "...")[0] > max_w:
                self.text = self.text[:-1]
            text_surf = font.render(self.text + "...", True, COLOR_BUTTON_TEXT)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))


def build_buttons(side_a, side_b, tool_mode="move"):
    """Button geometry scales with window width and the layout's margin,
    so it stays proportionate whether the window is 1300px or 380px wide."""
    fs = LAYOUT.font_scale()
    mobile = LAYOUT.window_w < MOBILE_BREAKPOINT
    btn_w = ((LAYOUT.window_w - 2 * LAYOUT.margin_side - 12) // 2
             if mobile else max(150, int(min(230, LAYOUT.window_w * 0.34))))
    btn_h = 40 if mobile else max(28, int(28 * fs))
    gap = 4 if mobile else max(4, int(6 * fs))
    buttons = []

    ax = LAYOUT.margin_side
    bx = LAYOUT.window_w - LAYOUT.margin_side - btn_w
    y0 = 8 if mobile else max(8, int(14 * fs))

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

    reset_w = btn_w if mobile else max(120, int(150 * fs))
    reset_x = ax if mobile else LAYOUT.window_w // 2 - reset_w // 2
    reset_y = y0 + 3 * (btn_h + gap) if mobile else y0 + (btn_h + gap) // 2
    buttons.append(Button((reset_x, reset_y, reset_w, btn_h),
                           "Reset positions (R)",
                           {"kind": "reset"}))
    tool_w = btn_w if mobile else reset_w
    tool_x = bx if mobile else LAYOUT.window_w // 2 - tool_w // 2
    tool_y = reset_y if mobile else reset_y + btn_h + gap
    buttons.append(Button((tool_x, tool_y, tool_w, btn_h),
                          f"Tool: {tool_mode.title()}",
                          {"kind": "open_tools_modal"}))
    return buttons


class Modal:
    """A centered, scrollable list of clickable options.

    The original modal created every row at a fixed y position, so teams with
    large squads could draw rows below the panel. This version keeps the rows
    clipped inside the panel and lets the user scroll the list.
    """

    def __init__(self, kind, side, options, player=None, scroll_y=0):
        self.kind = kind
        self.side = side
        self.options = options
        self.player = player

        fs = LAYOUT.font_scale()
        row_h = 42 if LAYOUT.window_w < MOBILE_BREAKPOINT else max(30, int(30 * fs))
        width = max(260, min(int(LAYOUT.window_w * 0.85), 420))
        height = min(int(LAYOUT.window_h * 0.85), 60 + row_h * len(options))
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (LAYOUT.window_w // 2, LAYOUT.window_h // 2)

        self.row_h = row_h
        self.close_rect = pygame.Rect(self.rect.right - 46, self.rect.y + 7, 38, 38)
        self.list_rect = pygame.Rect(
            self.rect.x + 10,
            self.rect.y + 50,
            self.rect.width - 20,
            self.rect.height - 60,
        )
        self.content_h = self.row_h * len(self.options)
        self.max_scroll = max(0, self.content_h - self.list_rect.height)
        self.scroll_y = max(0, min(int(scroll_y), self.max_scroll))
        self.selected_index = 0

    def title(self):
        if self.kind == "player":
            return f"Replace {self.player.name}"
        return {
            "team": "Choose team",
            "kit": "Choose uniform",
            "formation": "Choose formation",
            "tools": "Tools",
        }[self.kind]

    def _row_rect_for_index(self, index):
        y = self.list_rect.y + index * self.row_h - self.scroll_y
        return pygame.Rect(self.list_rect.x, y, self.list_rect.width, self.row_h - 4)

    def _render_ellipsized(self, font, text, color, max_w):
        if font.size(text)[0] <= max_w:
            return font.render(text, True, color)

        ellipsis = "..."
        clipped = text
        while clipped and font.size(clipped + ellipsis)[0] > max_w:
            clipped = clipped[:-1]
        return font.render((clipped + ellipsis) if clipped else ellipsis, True, color)

    def draw(self, surface, fonts, mouse_pos):
        overlay = pygame.Surface((LAYOUT.window_w, LAYOUT.window_h), pygame.SRCALPHA)
        overlay.fill(COLOR_MODAL_OVERLAY)
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, COLOR_MODAL_PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 106, 102), self.rect, width=1, border_radius=8)

        title_surf = self._render_ellipsized(
            fonts["modal_title"], self.title(), COLOR_MODAL_TEXT, self.rect.width - 76
        )
        surface.blit(title_surf, (self.rect.x + 16, self.rect.y + 14))

        pygame.draw.rect(surface, (90, 40, 40), self.close_rect, border_radius=4)
        x_surf = fonts["modal_row"].render("X", True, (240, 240, 240))
        surface.blit(x_surf, x_surf.get_rect(center=self.close_rect.center))

        old_clip = surface.get_clip()
        surface.set_clip(self.list_rect)

        first_visible = max(0, self.scroll_y // self.row_h)
        last_visible = min(
            len(self.options),
            (self.scroll_y + self.list_rect.height) // self.row_h + 2,
        )

        for index in range(first_visible, last_visible):
            label, _value = self.options[index]
            row_rect = self._row_rect_for_index(index)
            hovered = ((row_rect.collidepoint(mouse_pos) and self.list_rect.collidepoint(mouse_pos))
                       or index == self.selected_index)
            if hovered:
                pygame.draw.rect(surface, COLOR_MODAL_ROW_HOVER, row_rect, border_radius=4)

            label_surf = self._render_ellipsized(
                fonts["modal_row"],
                label,
                COLOR_MODAL_TEXT,
                row_rect.width - 16,
            )
            surface.blit(label_surf, (row_rect.x + 8, row_rect.centery - label_surf.get_height() // 2))

        surface.set_clip(old_clip)

        if self.max_scroll > 0:
            track = pygame.Rect(self.rect.right - 9, self.list_rect.y, 4, self.list_rect.height)
            pygame.draw.rect(surface, (70, 76, 72), track, border_radius=2)
            thumb_h = max(24, int(self.list_rect.height * self.list_rect.height / self.content_h))
            thumb_y = self.list_rect.y + int((self.list_rect.height - thumb_h) * self.scroll_y / self.max_scroll)
            thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
            pygame.draw.rect(surface, (150, 156, 152), thumb, border_radius=2)

    def handle_scroll(self, wheel_y):
        if self.max_scroll <= 0:
            return
        self.scroll_y = max(
            0,
            min(self.max_scroll, self.scroll_y - wheel_y * self.row_h * 3),
        )

    def scroll_pixels(self, delta_y):
        self.scroll_y = max(0, min(self.max_scroll, int(self.scroll_y - delta_y)))

    def move_selection(self, delta):
        if not self.options:
            return
        self.selected_index = max(0, min(len(self.options) - 1, self.selected_index + delta))
        row_top = self.selected_index * self.row_h
        if row_top < self.scroll_y:
            self.scroll_y = row_top
        elif row_top + self.row_h > self.scroll_y + self.list_rect.height:
            self.scroll_y = min(self.max_scroll, row_top + self.row_h - self.list_rect.height)

    def selected_value(self):
        return self.options[self.selected_index][1] if self.options else None

    def handle_click(self, pos):
        if self.close_rect.collidepoint(pos):
            return "close", None

        if self.list_rect.collidepoint(pos):
            index = (pos[1] - self.list_rect.y + self.scroll_y) // self.row_h
            if 0 <= index < len(self.options):
                return "select", self.options[int(index)][1]

        if not self.rect.collidepoint(pos):
            return "close", None
        return None, None


class MatchURLModal:
    """Small keyboard-friendly URL entry for the desktop board."""

    kind = "match_url"

    def __init__(self, text=""):
        self.text = text[:512]
        width = min(LAYOUT.window_w - 24, 670)
        self.rect = pygame.Rect(0, 0, width, 190)
        self.rect.center = (LAYOUT.window_w // 2, LAYOUT.window_h // 2)
        self.close_rect = pygame.Rect(self.rect.right - 46, self.rect.y + 8, 38, 38)
        self.field_rect = pygame.Rect(self.rect.x + 16, self.rect.y + 76, self.rect.width - 32, 44)
        self.submit_rect = pygame.Rect(self.rect.right - 162, self.rect.bottom - 54, 146, 38)
        self.list_rect = pygame.Rect(0, 0, 0, 0)

    def title(self):
        return "Import Zerozero match"

    def draw(self, surface, fonts, mouse_pos):
        overlay = pygame.Surface((LAYOUT.window_w, LAYOUT.window_h), pygame.SRCALPHA)
        overlay.fill(COLOR_MODAL_OVERLAY)
        surface.blit(overlay, (0, 0))
        pygame.draw.rect(surface, COLOR_MODAL_PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surface, (130, 136, 132), self.rect, 1, border_radius=8)
        title = fonts["modal_title"].render(self.title(), True, COLOR_MODAL_TEXT)
        surface.blit(title, (self.rect.x + 16, self.rect.y + 16))
        pygame.draw.rect(surface, (90, 40, 40), self.close_rect, border_radius=4)
        close = fonts["modal_row"].render("X", True, COLOR_MODAL_TEXT)
        surface.blit(close, close.get_rect(center=self.close_rect.center))
        label = fonts["modal_row"].render("Paste a Zerozero match link", True, COLOR_MODAL_TEXT)
        surface.blit(label, (self.field_rect.x, self.field_rect.y - 24))
        pygame.draw.rect(surface, (250, 250, 250), self.field_rect, border_radius=4)
        pygame.draw.rect(surface, (45, 53, 49), self.field_rect, 2, border_radius=4)
        shown = self.text or "https://www.zerozero.pt/jogo/..."
        color = (30, 34, 32) if self.text else (125, 130, 126)
        while shown and fonts["modal_row"].size(shown)[0] > self.field_rect.width - 22:
            shown = shown[1:]
        value = fonts["modal_row"].render(shown, True, color)
        surface.blit(value, (self.field_rect.x + 10,
                             self.field_rect.centery - value.get_height() // 2))
        pygame.draw.rect(surface, COLOR_BUTTON_HOVER if self.submit_rect.collidepoint(mouse_pos)
                         else COLOR_BUTTON, self.submit_rect, border_radius=5)
        submit = fonts["modal_row"].render("Import match", True, COLOR_BUTTON_TEXT)
        surface.blit(submit, submit.get_rect(center=self.submit_rect.center))
        hint = fonts["hint"].render("Enter to import  |  Ctrl+V to paste", True, COLOR_MODAL_TEXT)
        surface.blit(hint, (self.rect.x + 16, self.rect.bottom - 42))

    def handle_click(self, pos):
        if self.close_rect.collidepoint(pos) or not self.rect.collidepoint(pos):
            return "close", None
        if self.submit_rect.collidepoint(pos):
            return "submit", self.text.strip()
        return None, None

def kit_option_label(kit):
    return f"{kit['name']} ({kit['pattern']})"


def build_team_modal(side, teams=None):
    options = [(t["name"], t) for t in (teams if teams is not None else TEAMS)]
    return Modal("team", side, options)


def build_kit_modal(side):
    options = [(kit_option_label(k), i) for i, k in enumerate(side.team["kits"])]
    return Modal("kit", side, options)


def build_formation_modal(side):
    options = [(name, name) for name in FORMATIONS.keys()]
    return Modal("formation", side, options)


def build_player_modal(side, player):
    used_numbers = {p.number for p in side.players if p is not player}
    eligible = [p for p in side.team["squad"]
                if (p["position"] == "GK") == player.is_gk and p["number"] not in used_numbers]
    same_position = [p for p in eligible if p["position"] == player.position]
    other_positions = [p for p in eligible if p["position"] != player.position]

    squad_sorted = (
        sorted(same_position, key=lambda p: p["number"]) +
        sorted(other_positions, key=lambda p: (p["position"] != "GK", p["position"], p["number"]))
    )

    options = [(f"#{p['number']} {p['name']} ({p['position']})", p) for p in squad_sorted]
    if player.switch_pair is not None:
        target = player.switch_pair["before" if player.switch_active else "after"]
        minute = player.switch_pair.get("minute")
        suffix = f" ({minute}')" if minute else ""
        options.insert(0, (f"Switch to #{target['number']} {target['name']}{suffix}", "switch"))
    return Modal("player", side, options, player=player)


def build_tools_modal():
    options = [
        ("Move players", "move"),
        ("Draw arrows", "arrow"),
        ("Place / move ball", "ball"),
        ("Undo last change", "undo"),
        ("Save tactic", "save"),
        ("Load tactic", "load"),
        ("Import Zerozero match", "load_match"),
        ("Import JSON file", "import_json"),
        ("Export JSON", "export_json"),
        ("Export PNG", "export_png"),
        ("Clear arrows and ball", "clear_annotations"),
    ]
    return Modal("tools", None, options)


def pitch_contains(pos):
    x0, y0 = LAYOUT.m_to_px(0, 0)
    x1, y1 = LAYOUT.m_to_px(PITCH_LENGTH_M, PITCH_WIDTH_M)
    return x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1


def player_at_point(players, pos):
    candidates = [p for p in players if p.contains_point(*pos)]
    if not candidates:
        return None
    return min(candidates, key=lambda p: (p.pos_px[0] - pos[0]) ** 2 + (p.pos_px[1] - pos[1]) ** 2)


def px_to_m(pos):
    return (
        max(0.0, min(PITCH_LENGTH_M, (pos[0] - LAYOUT.offset_x) / LAYOUT.scale)),
        max(0.0, min(PITCH_WIDTH_M, (pos[1] - LAYOUT.offset_y) / LAYOUT.scale)),
    )


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("Invalid point in tactic")
    x, y = value
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (x, y)):
        raise ValueError("Invalid coordinates in tactic")
    if not (0 <= x <= PITCH_LENGTH_M and 0 <= y <= PITCH_WIDTH_M):
        raise ValueError("Tactic coordinates lie outside the pitch")
    return float(x), float(y)


def tactic_state(side_a, side_b, arrows, ball):
    def save_side(side):
        saved = {
            "team_id": side.team["id"],
            "kit_index": side.kit_index,
            "formation": side.formation_name,
            "players": [
                {"number": p.number, "name": p.name, "position": p.position,
                 "x_m": p.x_m, "y_m": p.y_m,
                 **({"player_id": p.player_id} if p.player_id is not None else {}),
                 **({"switch_pair": p.switch_pair, "switch_active": p.switch_active}
                    if p.switch_pair is not None else {})}
                for p in side.players
            ],
        }
        if side.team["id"].startswith("zerozero-"):
            saved["team_data"] = side.team
        return saved

    return {
        "version": 1,
        "sides": [save_side(side) for side in (side_a, side_b)],
        "arrows": [[list(start), list(end)] for start, end in arrows],
        "ball": list(ball) if ball is not None else None,
    }


def restore_tactic(state):
    """Validate a saved document fully before returning replacement sides."""
    if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
        raise ValueError("Unsupported tactic version")
    saved_sides = state.get("sides")
    if not isinstance(saved_sides, list) or len(saved_sides) != 2:
        raise ValueError("A tactic must contain two teams")
    team_by_id = {team["id"]: team for team in TEAMS}
    sides = []
    for saved, label, direction in zip(saved_sides, ("A", "B"), (1, -1)):
        if not isinstance(saved, dict) or not isinstance(saved.get("team_id"), str):
            raise ValueError("Unknown team in tactic")
        team_id = saved["team_id"]
        if team_id not in team_by_id:
            team_data = match_board.validate_imported_team_document(saved.get("team_data"))
            if team_data["id"] != team_id:
                raise ValueError("Imported team ID does not match saved tactic")
            team_by_id[team_id] = team_data
        formation = saved.get("formation")
        if not isinstance(formation, str) or formation not in FORMATIONS:
            raise ValueError("Unknown formation in tactic")
        side = TeamSide(label, team_by_id[team_id], direction)
        side.apply_formation(formation)
        kit_index = saved.get("kit_index")
        if type(kit_index) is not int or not 0 <= kit_index < len(side.team["kits"]):
            raise ValueError("Invalid kit in tactic")
        side.kit_index = kit_index
        saved_players = saved.get("players")
        if not isinstance(saved_players, list) or len(saved_players) != 11:
            raise ValueError("A team must have eleven players")
        valid_players = {(p["name"], p["number"], p["position"]) for p in side.team["squad"]}
        used_players = set()
        used_numbers = set()
        for slot, saved_player in zip(side.players, saved_players):
            if not isinstance(saved_player, dict):
                raise ValueError("Invalid player in tactic")
            identity = (saved_player.get("name"), saved_player.get("number"), saved_player.get("position"))
            if (not isinstance(identity[0], str) or type(identity[1]) is not int
                    or not isinstance(identity[2], str)):
                raise ValueError("Invalid player identity in tactic")
            known = identity in valid_players
            if not known:
                raise ValueError(f"Player {identity[0][:40]!r} #{identity[1]} is not in {side.team['name']}")
            if identity in used_players or identity[1] in used_numbers:
                raise ValueError("A duplicate player or shirt number was found in the tactic")
            if (identity[2] == "GK") != slot.is_gk:
                raise ValueError("Goalkeeper is assigned to an invalid slot")
            x_m, y_m = _point((saved_player.get("x_m"), saved_player.get("y_m")))
            slot.name, slot.number, slot.position = identity
            slot.x_m, slot.y_m = x_m, y_m
            player_id = saved_player.get("player_id")
            if player_id is not None:
                if type(player_id) is not int or not any(
                        p.get("id") == player_id and
                        (p["name"], p["number"], p["position"]) == identity
                        for p in side.team["squad"]):
                    raise ValueError("Invalid imported player ID in tactic")
            slot.player_id = player_id
            pair = saved_player.get("switch_pair")
            if pair is not None:
                if not isinstance(pair, dict) or not isinstance(saved_player.get("switch_active"), bool):
                    raise ValueError("Invalid substitution in tactic")
                for stage in ("before", "after"):
                    candidate = pair.get(stage)
                    if not isinstance(candidate, dict):
                        raise ValueError("Invalid substitution player in tactic")
                    candidate_identity = (candidate.get("name"), candidate.get("number"),
                                          candidate.get("position"))
                    if (not isinstance(candidate_identity[0], str)
                            or type(candidate_identity[1]) is not int
                            or not isinstance(candidate_identity[2], str)
                            or candidate_identity not in valid_players
                            or type(candidate.get("id")) is not int
                            or not any(p.get("id") == candidate["id"] and
                                       (p["name"], p["number"], p["position"]) == candidate_identity
                                       for p in side.team["squad"])):
                        raise ValueError("Invalid substitution player in tactic")
                if (pair["before"]["id"], pair["after"]["id"], pair.get("minute")) not in {
                        (change["out_id"], change["in_id"], change["minute"])
                        for change in side.team.get("substitutions", [])}:
                    raise ValueError("Substitution is not recorded for this match")
                active = saved_player["switch_active"]
                selected = pair["after" if active else "before"]
                if (selected["name"], selected["number"], selected["position"]) != identity:
                    raise ValueError("Substitution does not match player in tactic")
                if player_id != selected["id"]:
                    raise ValueError("Substitution player ID does not match tactic")
                slot.switch_pair = pair
                slot.switch_active = active
            else:
                slot.switch_pair = None
                slot.switch_active = False
            used_players.add(identity)
            used_numbers.add(identity[1])
        sides.append(side)
    saved_arrows = state.get("arrows", [])
    if not isinstance(saved_arrows, list) or len(saved_arrows) > MAX_ARROWS:
        raise ValueError("Too many arrows in tactic")
    arrows = []
    for arrow in saved_arrows:
        if not isinstance(arrow, (list, tuple)) or len(arrow) != 2:
            raise ValueError("Invalid arrow in tactic")
        arrows.append((_point(arrow[0]), _point(arrow[1])))
    ball = None if state.get("ball") is None else _point(state["ball"])
    return sides[0], sides[1], arrows, ball


def draw_annotations(surface, arrows, ball, preview=None):
    for start, end in [*arrows, *([preview] if preview else [])]:
        sx, sy = LAYOUT.m_to_px(*start)
        ex, ey = LAYOUT.m_to_px(*end)
        pygame.draw.line(surface, (255, 222, 70), (sx, sy), (ex, ey), max(3, int(LAYOUT.scale * 0.45)))
        angle = math.atan2(ey - sy, ex - sx)
        head = max(9, int(LAYOUT.scale * 1.6))
        spread = 0.55
        left = (ex - head * math.cos(angle - spread), ey - head * math.sin(angle - spread))
        right = (ex - head * math.cos(angle + spread), ey - head * math.sin(angle + spread))
        pygame.draw.polygon(surface, (255, 222, 70), [(ex, ey), left, right])
    if ball is not None:
        center = tuple(round(v) for v in LAYOUT.m_to_px(*ball))
        radius = max(7, round(LAYOUT.scale * 0.9))
        pygame.draw.circle(surface, (20, 20, 20), center, radius + 2)
        pygame.draw.circle(surface, (250, 250, 250), center, radius)
        pygame.draw.circle(surface, (40, 40, 40), center, max(2, radius // 3))


def render_export_surface(side_a, side_b, arrows, ball):
    global LAYOUT
    original_layout = LAYOUT
    try:
        LAYOUT = Layout(1280, 900)
        surface = pygame.Surface((LAYOUT.window_w, LAYOUT.window_h))
        fonts = build_fonts(LAYOUT)
        draw_pitch(surface)
        draw_annotations(surface, arrows, ball)
        textures = {}
        for player in side_a.players + side_b.players:
            player.draw(surface, fonts, textures)
        field = pygame.Rect(*LAYOUT.m_to_px(0, 0), LAYOUT.field_px_w, LAYOUT.field_px_h)
        field.inflate_ip(48, 48)
        field.clamp_ip(surface.get_rect())
        return surface.subsurface(field).copy()
    finally:
        LAYOUT = original_layout


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
def setup_accessibility():
    """Expose keyboard instructions and focus changes to browser assistive tools."""
    if sys.platform != "emscripten":
        return None
    try:
        from platform import window

        document = window.document
        canvas = document.querySelector("canvas")
        if canvas is not None:
            canvas.setAttribute("tabindex", "0")
            canvas.setAttribute(
                "aria-label",
                "Visual football tactical board. Use the accessible controls panel "
                "for labelled team, player and position controls.",
            )
        region = document.createElement("div")
        region.setAttribute("role", "status")
        region.setAttribute("aria-live", "polite")
        region.style.cssText = (
            "position:absolute;width:1px;height:1px;overflow:hidden;"
            "clip-path:inset(50%);white-space:nowrap"
        )
        document.body.appendChild(region)
        return region
    except Exception:
        return None


async def main():
    global LAYOUT

    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Football Tactical Board")

    # RESIZABLE lets the user drag-resize on desktop, and lets a pygbag/web
    # build react to VIDEORESIZE events if the host page resizes the canvas.
    screen = pygame.display.set_mode((LAYOUT.window_w, LAYOUT.window_h), pygame.RESIZABLE)

    clock = pygame.time.Clock()
    fonts = build_fonts(LAYOUT)

    side_a = TeamSide("A", TEAMS[0], x_dir=1)
    side_b = TeamSide("B", TEAMS[1], x_dir=-1)
    imported_teams = {}

    texture_cache = {}
    arrows = []
    ball = None
    tool_mode = "move"
    history = []
    status = ""
    live_region = setup_accessibility()
    try:
        accessible_panel = web_accessibility.create_panel()
    except Exception:
        accessible_panel = None
    panel_dirty = True
    modal = None
    dragged_player = None
    drag_start_pos = (0, 0)
    drag_offset = (0, 0)
    drag_moved = False
    arrow_start = None
    arrow_end = None
    ball_drag = False
    ball_drag_remembered = False
    touch_id = None
    touch_start = (0, 0)
    touch_last = (0, 0)
    touch_moved = False
    touch_scrolling = False
    focus_index = -1

    def announce(message):
        nonlocal status, panel_dirty
        status = message
        panel_dirty = True
        if live_region is not None:
            try:
                live_region.textContent = message
            except Exception:
                pass

    def remember():
        history.append(tactic_state(side_a, side_b, arrows, ball))
        if len(history) > 50:
            history.pop(0)

    def available_teams():
        return [*TEAMS, *imported_teams.values()]

    def register_imported_sides():
        for side in (side_a, side_b):
            if side.team["id"].startswith("zerozero-"):
                imported_teams[side.team["id"]] = side.team

    def toggle_player_substitution(player):
        if player.switch_pair is None:
            return
        target = player.switch_pair["before" if player.switch_active else "after"]
        occupied = {p.number for p in player.side.players if p is not player}
        if target["number"] in occupied:
            announce(f"#{target['number']} is already on the pitch")
            return
        remember()
        player.switch_player()
        announce(f"{player.side.label}: #{player.number} {player.name} on the pitch")

    async def import_match_url(url):
        nonlocal side_a, side_b, arrows, ball, focus_index
        try:
            if sys.platform == "emscripten":
                raise RuntimeError(
                    "This browser cannot read Zerozero HTML directly. "
                    "Import the link in the desktop app, then export its JSON tactic."
                )
            match = await asyncio.to_thread(match_import.load_match, url)
            if not isinstance(match, dict) or len(match.get("teams", [])) != 2:
                raise ValueError("The Zerozero page did not contain two complete teams")
            match_id = match["match_id"]
            teams = [match_board.build_imported_team(data, match_id) for data in match["teams"]]
            loaded_a = TeamSide("A", teams[0], x_dir=1)
            loaded_b = TeamSide("B", teams[1], x_dir=-1)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            announce(f"Match import failed: {exc}")
            return
        remember()
        side_a, side_b = loaded_a, loaded_b
        register_imported_sides()
        arrows, ball = [], None
        focus_index = -1
        announce(f"Imported {side_a.team['name']} vs {side_b.team['name']}")

    def use_tool(value):
        nonlocal side_a, side_b, arrows, ball, tool_mode, focus_index, modal
        if value in ("move", "arrow", "ball"):
            tool_mode = value
            announce({"move": "Move players", "arrow": "Drag on the pitch to draw an arrow",
                      "ball": "Tap or drag on the pitch to place the ball"}[value])
            return
        try:
            if value == "undo":
                if history:
                    side_a, side_b, arrows, ball = restore_tactic(history.pop())
                    register_imported_sides()
                    focus_index = -1
                    announce("Last change undone")
                else:
                    announce("Nothing to undo")
            elif value == "save":
                destination = tactic_io.save_state(tactic_state(side_a, side_b, arrows, ball))
                announce(f"Tactic saved: {destination}")
            elif value == "load":
                loaded = restore_tactic(tactic_io.load_state())
                remember()
                side_a, side_b, arrows, ball = loaded
                register_imported_sides()
                focus_index = -1
                announce("Tactic loaded")
            elif value == "import_json":
                def imported(state, error):
                    nonlocal side_a, side_b, arrows, ball, focus_index, modal
                    if error is not None:
                        announce(str(error))
                        return
                    try:
                        loaded = restore_tactic(state)
                        remember()
                        side_a, side_b, arrows, ball = loaded
                        register_imported_sides()
                        focus_index = -1
                        modal = None
                        announce("JSON tactic imported")
                    except (ValueError, OSError) as exc:
                        announce(str(exc))

                announce("Choose a JSON tactic file")
                tactic_io.import_json_file(imported)
            elif value == "export_json":
                destination = tactic_io.export_json(tactic_state(side_a, side_b, arrows, ball))
                announce(f"JSON exported: {destination}")
            elif value == "load_match":
                modal = MatchURLModal()
                pygame.key.start_text_input()
                announce(modal.title())
            elif value == "export_png":
                board = render_export_surface(side_a, side_b, arrows, ball)
                destination = tactic_io.export_png(board)
                announce(f"Image exported: {destination}")
            elif value == "clear_annotations":
                if arrows or ball is not None:
                    remember()
                    arrows = []
                    ball = None
                    announce("Arrows and ball cleared")
        except (OSError, ValueError, RuntimeError) as exc:
            announce(str(exc))

    def select_modal(value):
        nonlocal modal
        active = modal
        if active is None:
            return
        modal = None
        if active.kind == "tools":
            use_tool(value)
        elif active.kind == "team":
            if active.side.team is not value:
                remember()
                active.side.set_team(value)
                announce(f"{active.side.label}: {value['name']}")
        elif active.kind == "kit":
            if active.side.kit_index != value:
                remember()
                active.side.set_kit(value)
                announce("Uniform changed")
        elif active.kind == "formation":
            if active.side.formation_name != value:
                remember()
                active.side.apply_formation(value)
                announce(f"Formation: {value}")
        elif active.kind == "player":
            player = active.player
            if value == "switch":
                toggle_player_substitution(player)
                return
            identity = (value["name"], value["number"], value["position"])
            if (player.name, player.number, player.position) != identity:
                remember()
                player.name, player.number, player.position = identity
                player.player_id = value.get("id")
                player.switch_pair = None
                player.switch_active = False
                announce(f"Selected {player.name}")

    def activate_button(button):
        nonlocal modal
        action = button.action
        kind = action["kind"]
        if kind == "open_team_modal":
            modal = build_team_modal(action["side"], available_teams())
        elif kind == "open_kit_modal":
            modal = build_kit_modal(action["side"])
        elif kind == "open_formation_modal":
            modal = build_formation_modal(action["side"])
        elif kind == "open_tools_modal":
            modal = build_tools_modal()
        elif kind == "reset":
            if any((p.x_m, p.y_m) != p.home_m for p in side_a.players + side_b.players):
                remember()
                side_a.reset_positions()
                side_b.reset_positions()
                announce("Positions reset")
        if modal is not None:
            announce(modal.title())

    def pointer_down(pos, buttons):
        nonlocal modal, dragged_player, drag_start_pos, drag_offset, drag_moved
        nonlocal arrow_start, arrow_end, ball, ball_drag, ball_drag_remembered, focus_index
        if modal is not None:
            action, value = modal.handle_click(pos)
            if action == "close":
                if modal.kind == "match_url":
                    pygame.key.stop_text_input()
                modal = None
            elif action == "select":
                select_modal(value)
            elif action == "submit":
                pygame.key.stop_text_input()
                modal = None
                announce("Loading Zerozero match...")
                asyncio.create_task(import_match_url(value))
            return

        for index, button in enumerate(buttons):
            if button.rect.collidepoint(pos):
                focus_index = index
                activate_button(button)
                return

        if tool_mode == "move":
            players = side_a.players + side_b.players
            for player in reversed(players):
                badge = player.switch_badge_rect()
                if badge is not None and badge.inflate(8, 8).collidepoint(pos):
                    toggle_player_substitution(player)
                    return
            player = player_at_point(players, pos)
            if player is not None:
                dragged_player = player
                drag_start_pos = pos
                cx, cy = player.pos_px
                drag_offset = (cx - pos[0], cy - pos[1])
                drag_moved = False
                focus_index = len(buttons) + players.index(player)
                announce(f"{player.side.label}: {player.name}, number {player.number}")
        elif tool_mode == "arrow" and pitch_contains(pos):
            arrow_start = px_to_m(pos)
            arrow_end = arrow_start
        elif tool_mode == "ball" and pitch_contains(pos):
            new_ball = px_to_m(pos)
            ball_drag_remembered = False
            if ball != new_ball:
                remember()
                ball_drag_remembered = True
                ball = new_ball
            ball_drag = True

    def pointer_move(pos):
        nonlocal drag_moved, arrow_end, ball, ball_drag_remembered
        if dragged_player is not None:
            dx = pos[0] - drag_start_pos[0]
            dy = pos[1] - drag_start_pos[1]
            if not drag_moved and dx * dx + dy * dy > CLICK_MOVE_THRESHOLD_PX ** 2:
                remember()
                drag_moved = True
            if drag_moved:
                dragged_player.set_pos_from_px(pos[0] + drag_offset[0], pos[1] + drag_offset[1])
        elif arrow_start is not None:
            arrow_end = px_to_m(pos)
        elif ball_drag and pitch_contains(pos):
            new_ball = px_to_m(pos)
            if ball != new_ball:
                if not ball_drag_remembered:
                    remember()
                    ball_drag_remembered = True
                ball = new_ball

    def pointer_up(pos):
        nonlocal modal, dragged_player, drag_moved, arrow_start, arrow_end
        nonlocal ball_drag, ball_drag_remembered
        pointer_move(pos)
        if dragged_player is not None:
            if not drag_moved:
                modal = build_player_modal(dragged_player.side, dragged_player)
                announce(modal.title())
            else:
                announce(f"Moved {dragged_player.name}")
            dragged_player = None
            drag_moved = False
        elif arrow_start is not None:
            sx, sy = LAYOUT.m_to_px(*arrow_start)
            ex, ey = LAYOUT.m_to_px(*arrow_end)
            if (ex - sx) ** 2 + (ey - sy) ** 2 > CLICK_MOVE_THRESHOLD_PX ** 2:
                if len(arrows) >= MAX_ARROWS:
                    announce(f"Arrow limit reached ({MAX_ARROWS})")
                else:
                    remember()
                    arrows.append((arrow_start, arrow_end))
                    announce("Arrow added")
            arrow_start = arrow_end = None
        if ball_drag:
            announce("Ball placed")
        ball_drag = False
        ball_drag_remembered = False

    def focus_description(buttons):
        if focus_index < len(buttons):
            return buttons[focus_index].base_text
        players = side_a.players + side_b.players
        player = players[focus_index - len(buttons)]
        return f"{player.side.label}: {player.name}, number {player.number}; arrow keys move, Enter changes player"

    def panel_state():
        return {
            **tactic_state(side_a, side_b, arrows, ball),
            "teams": available_teams(),
            "formations": list(FORMATIONS),
            "mode": tool_mode,
        }

    def handle_panel_command(command, buttons):
        nonlocal ball, modal
        if not isinstance(command, dict):
            raise ValueError("Invalid accessible control command")
        modal = None
        kind = command.get("type")
        if kind == "load_match":
            url = command.get("url")
            if not isinstance(url, str) or len(url) > 512:
                raise ValueError("Invalid Zerozero match link")
            announce("Loading Zerozero match...")
            asyncio.create_task(import_match_url(url))
            return
        if kind == "action":
            action = command.get("action")
            if action == "reset":
                activate_button(next(b for b in buttons if b.action["kind"] == "reset"))
            elif action in {"undo", "save", "load", "import_json", "export_json",
                            "export_png", "clear_annotations"}:
                use_tool(action)
            else:
                raise ValueError("Unknown board action")
            return
        if kind == "set_mode":
            if command.get("mode") not in {"move", "arrow", "ball"}:
                raise ValueError("Unknown drawing mode")
            use_tool(command["mode"])
            return
        if kind == "add_arrow":
            start, end = _point(command.get("start")), _point(command.get("end"))
            if start != end:
                if len(arrows) >= MAX_ARROWS:
                    raise ValueError("The tactic has too many arrows")
                remember()
                arrows.append((start, end))
                announce("Arrow added")
            return
        if kind == "place_ball":
            point = _point(command.get("point"))
            if ball != point:
                remember()
                ball = point
                announce("Ball placed")
            return

        side_label = command.get("side")
        if side_label not in ("A", "B"):
            raise ValueError("Unknown team side")
        side = side_a if side_label == "A" else side_b
        if kind == "set_team":
            team = next((t for t in available_teams() if t["id"] == command.get("value")), None)
            if team is None:
                raise ValueError("Unknown team")
            if side.team is not team:
                remember()
                side.set_team(team)
                announce(f"{side_label}: {team['name']}")
        elif kind == "set_kit":
            index = command.get("value")
            if type(index) is not int or not 0 <= index < len(side.team["kits"]):
                raise ValueError("Invalid uniform")
            if side.kit_index != index:
                remember()
                side.set_kit(index)
                announce("Uniform changed")
        elif kind == "set_formation":
            formation = command.get("value")
            if not isinstance(formation, str) or formation not in FORMATIONS:
                raise ValueError("Unknown formation")
            if side.formation_name != formation:
                remember()
                side.apply_formation(formation)
                announce(f"Formation: {formation}")
        elif kind in ("select_player", "move_player", "switch_player"):
            slot = command.get("slot")
            if type(slot) is not int or not 0 <= slot < 11:
                raise ValueError("Invalid player slot")
            player = side.players[slot]
            if kind == "switch_player":
                if player.switch_pair is None:
                    raise ValueError("This player has no match substitution")
                toggle_player_substitution(player)
            elif kind == "move_player":
                point = _point((command.get("x_m"), command.get("y_m")))
                if (player.x_m, player.y_m) != point:
                    remember()
                    player.x_m, player.y_m = point
                    announce(f"Moved {player.name}")
            else:
                data = command.get("player")
                if not isinstance(data, dict):
                    raise ValueError("Invalid player")
                identity = (data.get("name"), data.get("number"), data.get("position"))
                if (not isinstance(identity[0], str) or type(identity[1]) is not int
                        or not isinstance(identity[2], str)):
                    raise ValueError("Invalid player")
                known = any((p["name"], p["number"], p["position"]) == identity
                            for p in side.team["squad"])
                occupied = {p.number for p in side.players if p is not player}
                if not known or (identity[2] == "GK") != player.is_gk or identity[1] in occupied:
                    raise ValueError("Player unavailable for this slot")
                if (player.name, player.number, player.position) != identity:
                    remember()
                    player.name, player.number, player.position = identity
                    player.player_id = next((p.get("id") for p in side.team["squad"]
                                             if (p["name"], p["number"], p["position"]) == identity), None)
                    player.switch_pair = None
                    player.switch_active = False
                    announce(f"Selected {player.name}")
        else:
            raise ValueError("Unknown accessible control command")

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        buttons = build_buttons(side_a, side_b, tool_mode)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                LAYOUT.recompute(event.w, event.h)
                screen = pygame.display.set_mode((LAYOUT.window_w, LAYOUT.window_h), pygame.RESIZABLE)
                fonts = build_fonts(LAYOUT)
                texture_cache.clear()  # old textures were sized for the old scale
                if modal is not None:
                    if modal.kind == "match_url":
                        modal = MatchURLModal(modal.text)
                    else:
                        scroll = modal.scroll_y
                        selected = modal.selected_index
                        modal = {
                            "team": lambda: build_team_modal(modal.side, available_teams()),
                            "kit": lambda: build_kit_modal(modal.side),
                            "formation": lambda: build_formation_modal(modal.side),
                            "player": lambda: build_player_modal(modal.side, modal.player),
                            "tools": build_tools_modal,
                        }[modal.kind]()
                        modal.scroll_y = min(modal.max_scroll, scroll)
                        modal.selected_index = min(len(modal.options) - 1, selected)
                buttons = build_buttons(side_a, side_b, tool_mode)

            elif event.type == pygame.KEYDOWN:
                if modal is not None:
                    if modal.kind == "match_url":
                        if event.key == pygame.K_ESCAPE:
                            pygame.key.stop_text_input()
                            modal = None
                        elif event.key == pygame.K_BACKSPACE:
                            modal.text = modal.text[:-1]
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            url = modal.text.strip()
                            pygame.key.stop_text_input()
                            modal = None
                            announce("Loading Zerozero match...")
                            asyncio.create_task(import_match_url(url))
                        elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_v:
                            try:
                                if not pygame.scrap.get_init():
                                    pygame.scrap.init()
                                pasted = pygame.scrap.get(pygame.SCRAP_TEXT)
                                if pasted:
                                    modal.text = (modal.text + pasted.decode("utf-8", "replace")
                                                  .replace("\x00", ""))[:512]
                            except pygame.error:
                                announce("Clipboard unavailable; type the match link")
                    elif event.key == pygame.K_ESCAPE:
                        modal = None
                    elif event.key in (pygame.K_DOWN, pygame.K_TAB):
                        modal.move_selection(-1 if event.mod & pygame.KMOD_SHIFT else 1)
                        announce(modal.options[modal.selected_index][0])
                    elif event.key == pygame.K_UP:
                        modal.move_selection(-1)
                        announce(modal.options[modal.selected_index][0])
                    elif event.key == pygame.K_PAGEUP:
                        modal.move_selection(-8)
                    elif event.key == pygame.K_PAGEDOWN:
                        modal.move_selection(8)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        select_modal(modal.selected_value())
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_s:
                    use_tool("save")
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_o:
                    use_tool("load")
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_e:
                    use_tool("export_png")
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_z:
                    use_tool("undo")
                elif event.key == pygame.K_ESCAPE:
                    if tool_mode != "move":
                        use_tool("move")
                    elif sys.platform != "emscripten":
                        running = False
                elif event.key == pygame.K_r:
                    activate_button(next(b for b in buttons if b.action["kind"] == "reset"))
                elif event.key == pygame.K_TAB:
                    total = len(buttons) + len(side_a.players) + len(side_b.players)
                    focus_index = (focus_index + (-1 if event.mod & pygame.KMOD_SHIFT else 1)) % total
                    announce(focus_description(buttons))
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE) and focus_index >= 0:
                    if focus_index < len(buttons):
                        activate_button(buttons[focus_index])
                    else:
                        player = (side_a.players + side_b.players)[focus_index - len(buttons)]
                        modal = build_player_modal(player.side, player)
                        announce(modal.title())
                elif (event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN)
                      and focus_index >= len(buttons)):
                    players = side_a.players + side_b.players
                    player_index = focus_index - len(buttons)
                    if player_index < len(players):
                        player = players[player_index]
                        step = 2.0 if event.mod & pygame.KMOD_SHIFT else 0.5
                        dx = (-step if event.key == pygame.K_LEFT else step if event.key == pygame.K_RIGHT else 0)
                        dy = (-step if event.key == pygame.K_UP else step if event.key == pygame.K_DOWN else 0)
                        new_pos = (max(0, min(PITCH_LENGTH_M, player.x_m + dx)),
                                   max(0, min(PITCH_WIDTH_M, player.y_m + dy)))
                        if new_pos != (player.x_m, player.y_m):
                            remember()
                            player.x_m, player.y_m = new_pos
                            announce(f"{player.name}: {player.x_m:.1f} m, {player.y_m:.1f} m")

            elif event.type == pygame.TEXTINPUT and modal is not None and modal.kind == "match_url":
                modal.text = (modal.text + event.text)[:512]

            elif event.type == pygame.MOUSEWHEEL and modal is not None:
                modal.handle_scroll(event.y)

            elif event.type == pygame.MOUSEBUTTONDOWN and modal is not None and event.button in (4, 5):
                modal.handle_scroll(1 if event.button == 4 else -1)

            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                  and not getattr(event, "touch", False)):
                pointer_down(event.pos, buttons)

            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 3
                  and modal is None and not getattr(event, "touch", False)):
                player = player_at_point(side_a.players + side_b.players, event.pos)
                if player is not None:
                    modal = build_player_modal(player.side, player)
                    dragged_player = None

            elif (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                  and not getattr(event, "touch", False)):
                pointer_up(event.pos)

            elif event.type == pygame.MOUSEMOTION and not getattr(event, "touch", False):
                pointer_move(event.pos)

            elif event.type == pygame.FINGERDOWN and touch_id is None:
                touch_id = event.finger_id
                touch_start = touch_last = (event.x * LAYOUT.window_w, event.y * LAYOUT.window_h)
                touch_moved = False
                touch_scrolling = modal is not None and modal.list_rect.collidepoint(touch_start)
                if not touch_scrolling:
                    pointer_down(touch_start, buttons)

            elif event.type == pygame.FINGERMOTION and event.finger_id == touch_id:
                pos = (event.x * LAYOUT.window_w, event.y * LAYOUT.window_h)
                dx, dy = pos[0] - touch_start[0], pos[1] - touch_start[1]
                if dx * dx + dy * dy > CLICK_MOVE_THRESHOLD_PX ** 2:
                    touch_moved = True
                if touch_scrolling and modal is not None:
                    modal.scroll_pixels(pos[1] - touch_last[1])
                else:
                    pointer_move(pos)
                touch_last = pos

            elif event.type == pygame.FINGERUP and event.finger_id == touch_id:
                pos = (event.x * LAYOUT.window_w, event.y * LAYOUT.window_h)
                if touch_scrolling and not touch_moved:
                    pointer_down(pos, buttons)
                elif not touch_scrolling:
                    pointer_up(pos)
                touch_id = None
                touch_scrolling = False

        if accessible_panel is not None:
            try:
                for command in accessible_panel.drain_commands():
                    try:
                        handle_panel_command(command, buttons)
                    except (ValueError, TypeError, KeyError) as exc:
                        announce(str(exc))
                if panel_dirty:
                    accessible_panel.update(panel_state())
                    panel_dirty = False
            except Exception as exc:
                accessible_panel = None
                announce(f"Accessible controls unavailable: {exc}")

        draw_pitch(screen)
        draw_annotations(screen, arrows, ball,
                         (arrow_start, arrow_end) if arrow_start is not None else None)
        for p in side_a.players + side_b.players:
            p.draw(screen, fonts, texture_cache)

        players = side_a.players + side_b.players
        if len(buttons) <= focus_index < len(buttons) + len(players):
            player = players[focus_index - len(buttons)]
            pygame.draw.circle(screen, (255, 240, 95), player.pos_px,
                               player.radius_px + 5, width=2)

        for index, b in enumerate(buttons):
            b.draw(screen, fonts["button"], mouse_pos, focused=index == focus_index)

        hint_text = ("Tap player | Drag to move"
                     if LAYOUT.window_w < MOBILE_BREAKPOINT else
                     "Click = pick player  |  Drag = move  |  Tab / Enter = keyboard  |  R = reset")
        hint = fonts["hint"].render(hint_text, True, (230, 230, 230))
        screen.blit(hint, (LAYOUT.margin_side, LAYOUT.window_h - hint.get_height() - 6))
        if status:
            status_surface = fonts["hint"].render(status, True, (255, 237, 144))
            screen.blit(status_surface,
                        (LAYOUT.margin_side, LAYOUT.window_h - hint.get_height() - status_surface.get_height() - 10))

        if modal is not None:
            modal.draw(screen, fonts, mouse_pos)

        pygame.display.flip()
        clock.tick(FPS)
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
