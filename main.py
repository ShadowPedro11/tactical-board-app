"""
Football Tactical Board
------------------------
Interactive tactics board built with pygame, sized to real football pitch
dimensions (105m x 68m per IFAB Laws of the Game). Deployed to the web via
pygbag (compiles to WASM), which is why the app runs an async main loop.

Features:
  - Real-size pitch with standard markings.
  - Two teams, each independently: choose the team (from an embedded
    "database" of squads), choose a uniform/kit, choose a formation.
  - Drag a player token to reposition it.
  - Click (without dragging) a player token to open a roster list and
    swap in a different squad player -- this updates the token's number
    and the name label shown below it.

Controls:
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

# ---------------------------------------------------------------------------
# Scale + layout
# ---------------------------------------------------------------------------
SCALE = 10  # pixels per meter
MARGIN_SIDE = 50   # px run-off left/right/bottom of the pitch
TOP_PANEL_H = 132  # px reserved above the pitch for team/kit/formation UI

FIELD_PX_W = int(PITCH_LENGTH_M * SCALE)
FIELD_PX_H = int(PITCH_WIDTH_M * SCALE)

SCREEN_W = FIELD_PX_W + MARGIN_SIDE * 2
SCREEN_H = TOP_PANEL_H + FIELD_PX_H + MARGIN_SIDE

FPS = 60
CLICK_MOVE_THRESHOLD_PX = 6

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


def m_to_px(x_m, y_m):
    return (MARGIN_SIDE + x_m * SCALE, TOP_PANEL_H + y_m * SCALE)


def brightness(color):
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


# ---------------------------------------------------------------------------
# Player token
# ---------------------------------------------------------------------------
class Player:
    def __init__(self, x_m, y_m, number, name, is_gk, side):
        self.x_m = x_m
        self.y_m = y_m
        self.home_m = (x_m, y_m)
        self.number = number
        self.name = name
        self.is_gk = is_gk
        self.side = side
        self.radius_px = int(PLAYER_RADIUS_M * SCALE)

    @property
    def pos_px(self):
        return m_to_px(self.x_m, self.y_m)

    def contains_point(self, px, py):
        cx, cy = self.pos_px
        return (px - cx) ** 2 + (py - cy) ** 2 <= self.radius_px ** 2

    def set_pos_from_px(self, px, py):
        min_x, min_y = m_to_px(0, 0)
        max_x, max_y = m_to_px(PITCH_LENGTH_M, PITCH_WIDTH_M)
        px = max(min_x, min(max_x, px))
        py = max(min_y, min(max_y, py))
        self.x_m = (px - MARGIN_SIDE) / SCALE
        self.y_m = (py - TOP_PANEL_H) / SCALE

    def reset(self):
        self.x_m, self.y_m = self.home_m

    def draw(self, surface, number_font, name_font, texture_cache):
        kit = self.side.current_kit_for(self)
        tex_key = (self.side.team["id"], "GK" if self.is_gk else kit["name"])
        tex = texture_cache.get(tex_key)
        if tex is None:
            tex = build_token_texture(kit["pattern"], kit["colors"], self.radius_px * 2)
            texture_cache[tex_key] = tex

        cx, cy = self.pos_px
        cx, cy = int(cx), int(cy)

        shadow = pygame.Surface((self.radius_px * 2 + 8, self.radius_px * 2 + 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
        surface.blit(shadow, (cx - shadow.get_width() // 2, cy - shadow.get_height() // 2 + 4))

        surface.blit(tex, (cx - self.radius_px, cy - self.radius_px))

        text_color = (255, 255, 255) if brightness(kit["colors"][0]) < 140 else (25, 25, 25)
        num_surf = number_font.render(str(self.number), True, text_color)
        surface.blit(num_surf, num_surf.get_rect(center=(cx, cy)))

        name_surf = name_font.render(self.name, True, (255, 255, 255))
        name_rect = name_surf.get_rect(center=(cx, cy + self.radius_px + 11))
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

    def build_players_from_squad(self):
        squad = self.team["squad"]
        gk = next(p for p in squad if p["position"] == "GK")
        outfield = [p for p in squad if p["position"] != "GK"][:10]

        self.players = []
        gx, gy = gk_slot()
        self.players.append(Player(self._mirror(gx), gy, gk["number"], gk["name"], True, self))

        for (x, y), pdata in zip(outfield_slots(self.formation_name), outfield):
            self.players.append(Player(self._mirror(x), y, pdata["number"], pdata["name"], False, self))

    def apply_formation(self, formation_name):
        self.formation_name = formation_name
        slots = outfield_slots(formation_name)
        for (x, y), pl in zip(slots, self.players[1:]):
            xm = self._mirror(x)
            pl.x_m, pl.y_m = xm, y
            pl.home_m = (xm, y)
        gk = self.players[0]
        gx, gy = gk_slot()
        gk.home_m = (self._mirror(gx), gy)

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
# ---------------------------------------------------------------------------
class Button:
    def __init__(self, rect, text, action):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action  # dict describing what to do on click

    def draw(self, surface, font, mouse_pos):
        hovered = self.rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, COLOR_BUTTON_HOVER if hovered else COLOR_BUTTON, self.rect, border_radius=6)
        pygame.draw.rect(surface, (90, 96, 92), self.rect, width=1, border_radius=6)
        text_surf = font.render(self.text, True, COLOR_BUTTON_TEXT)
        # Truncate long labels so they don't overflow the button
        max_w = self.rect.width - 12
        if text_surf.get_width() > max_w:
            while self.text and font.size(self.text + "...")[0] > max_w:
                self.text = self.text[:-1]
            text_surf = font.render(self.text + "...", True, COLOR_BUTTON_TEXT)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))


def build_buttons(side_a, side_b):
    btn_w, btn_h, gap = 230, 28, 6
    buttons = []

    ax = MARGIN_SIDE
    bx = SCREEN_W - MARGIN_SIDE - btn_w
    y0 = 14

    for i, (side, x) in enumerate(((side_a, ax), (side_b, bx))):
        buttons.append(Button((x, y0, btn_w, btn_h),
                               f"Team: {side.team['name']}",
                               {"kind": "open_team_modal", "side": side}))
        buttons.append(Button((x, y0 + (btn_h + gap), btn_w, btn_h),
                               f"Kit: {side.team['kits'][side.kit_index]['name']}",
                               {"kind": "open_kit_modal", "side": side}))
        buttons.append(Button((x, y0 + 2 * (btn_h + gap), btn_w, btn_h),
                               f"Formation: {side.formation_name}",
                               {"kind": "open_formation_modal", "side": side}))

    reset_w = 150
    buttons.append(Button((SCREEN_W // 2 - reset_w // 2, y0 + (btn_h + gap) // 2, reset_w, btn_h),
                           "Reset positions (R)",
                           {"kind": "reset"}))
    return buttons


class Modal:
    """A centered list of clickable options, with a translucent backdrop."""

    def __init__(self, kind, side, options, player=None):
        self.kind = kind          # "team" | "kit" | "formation" | "player"
        self.side = side
        self.options = options    # list of (label_str, value)
        self.player = player      # only set for kind == "player"

        row_h = 30
        width = 340
        height = min(560, 60 + row_h * len(options))
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (SCREEN_W // 2, SCREEN_H // 2)

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

    def draw(self, surface, title_font, row_font, mouse_pos):
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill(COLOR_MODAL_OVERLAY)
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, COLOR_MODAL_PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 106, 102), self.rect, width=1, border_radius=8)

        title_surf = title_font.render(self.title(), True, COLOR_MODAL_TEXT)
        surface.blit(title_surf, (self.rect.x + 16, self.rect.y + 14))

        pygame.draw.rect(surface, (90, 40, 40), self.close_rect, border_radius=4)
        x_surf = row_font.render("X", True, (240, 240, 240))
        surface.blit(x_surf, x_surf.get_rect(center=self.close_rect.center))

        for row_rect, label, _value in self.rows:
            hovered = row_rect.collidepoint(mouse_pos)
            if hovered:
                pygame.draw.rect(surface, COLOR_MODAL_ROW_HOVER, row_rect, border_radius=4)
            label_surf = row_font.render(label, True, COLOR_MODAL_TEXT)
            surface.blit(label_surf, (row_rect.x + 8, row_rect.centery - label_surf.get_height() // 2))

    def handle_click(self, pos):
        """Returns ('select', value) / ('close', None) / (None, None) if click missed everything."""
        if self.close_rect.collidepoint(pos):
            return "close", None
        for row_rect, _label, value in self.rows:
            if row_rect.collidepoint(pos):
                return "select", value
        if not self.rect.collidepoint(pos):
            return "close", None
        return None, None


def kit_option_label(kit):
    swatch = "/".join("#" for _ in kit["colors"])  # placeholder, real swatch drawn separately if desired
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
    squad_sorted = sorted(side.team["squad"], key=lambda p: (p["position"] != "GK", p["number"]))
    options = [(f"#{p['number']} {p['name']} ({p['position']})", p) for p in squad_sorted]
    return Modal("player", side, options, player=player)


# ---------------------------------------------------------------------------
# Pitch drawing (unchanged geometry, offset now includes the top UI panel)
# ---------------------------------------------------------------------------
def draw_pitch(surface):
    surface.fill(COLOR_BG)

    top_panel_rect = pygame.Rect(0, 0, SCREEN_W, TOP_PANEL_H)
    pygame.draw.rect(surface, COLOR_PANEL_BG, top_panel_rect)

    field_rect = pygame.Rect(*m_to_px(0, 0), FIELD_PX_W, FIELD_PX_H)

    stripe_count = 12
    stripe_w = FIELD_PX_W / stripe_count
    for i in range(stripe_count):
        color = COLOR_PITCH if i % 2 == 0 else COLOR_PITCH_ALT
        rect = pygame.Rect(field_rect.x + i * stripe_w, field_rect.y, stripe_w + 1, field_rect.height)
        pygame.draw.rect(surface, color, rect)

    def line(p1_m, p2_m, width=3):
        pygame.draw.line(surface, COLOR_LINES, m_to_px(*p1_m), m_to_px(*p2_m), width)

    def circle(center_m, radius_m, width=3):
        cx, cy = m_to_px(*center_m)
        pygame.draw.circle(surface, COLOR_LINES, (int(cx), int(cy)), int(radius_m * SCALE), width)

    def rect_outline(x_m, y_m, w_m, h_m, width=3):
        x, y = m_to_px(x_m, y_m)
        pygame.draw.rect(surface, COLOR_LINES, (x, y, w_m * SCALE, h_m * SCALE), width)

    pygame.draw.rect(surface, COLOR_LINES, field_rect, 3)
    line((PITCH_LENGTH_M / 2, 0), (PITCH_LENGTH_M / 2, PITCH_WIDTH_M))
    circle((PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2), CENTER_CIRCLE_RADIUS_M)
    pygame.draw.circle(surface, COLOR_LINES, m_to_px(PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2), 4)

    for x0, direction in ((0, 1), (PITCH_LENGTH_M, -1)):
        pa_w = PENALTY_AREA_DEPTH_M * direction
        pa_y = (PITCH_WIDTH_M - PENALTY_AREA_WIDTH_M) / 2
        rect_outline(x0 if direction == 1 else x0 + pa_w, pa_y, abs(pa_w), PENALTY_AREA_WIDTH_M)

        ga_w = GOAL_AREA_DEPTH_M * direction
        ga_y = (PITCH_WIDTH_M - GOAL_AREA_WIDTH_M) / 2
        rect_outline(x0 if direction == 1 else x0 + ga_w, ga_y, abs(ga_w), GOAL_AREA_WIDTH_M)

        spot_x = x0 + PENALTY_SPOT_DIST_M * direction
        pygame.draw.circle(surface, COLOR_LINES, m_to_px(spot_x, PITCH_WIDTH_M / 2), 4)

        arc_rect = pygame.Rect(0, 0, CENTER_CIRCLE_RADIUS_M * 2 * SCALE, CENTER_CIRCLE_RADIUS_M * 2 * SCALE)
        arc_rect.center = m_to_px(spot_x, PITCH_WIDTH_M / 2)
        if direction == 1:
            start_angle, end_angle = -0.93, 0.93
        else:
            start_angle, end_angle = 3.1416 - 0.93, 3.1416 + 0.93
        pygame.draw.arc(surface, COLOR_LINES, arc_rect, start_angle, end_angle, 3)

        goal_y = (PITCH_WIDTH_M - GOAL_WIDTH_M) / 2
        goal_w = GOAL_DEPTH_M * direction
        rect_outline(x0 if direction == 1 else x0 + goal_w, goal_y, abs(goal_w), GOAL_WIDTH_M, width=2)

    for cx_m, cy_m, a_start, a_end in (
        (0, PITCH_WIDTH_M, 0, 1.5708), #Top.left
        (0, 0, -1.5708, 0), #Bottom.left
        (PITCH_LENGTH_M, PITCH_WIDTH_M, 1.5708, 3.1416), #Bottom.right
        (PITCH_LENGTH_M, 0, 3.1416, 4.7124), #Top.right
    ):
        r = CORNER_ARC_RADIUS_M * SCALE
        rect = pygame.Rect(0, 0, r * 2, r * 2)
        rect.center = m_to_px(cx_m, cy_m)
        pygame.draw.arc(surface, COLOR_LINES, rect, a_start, a_end, 2)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
async def main():
    pygame.init()
    pygame.display.set_caption("Football Tactical Board")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    number_font = pygame.font.SysFont("arial", 15, bold=True)
    name_font = pygame.font.SysFont("arial", 12, bold=True)
    button_font = pygame.font.SysFont("arial", 14, bold=True)
    modal_title_font = pygame.font.SysFont("arial", 18, bold=True)
    modal_row_font = pygame.font.SysFont("arial", 14)
    hint_font = pygame.font.SysFont("arial", 13)

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
            p.draw(screen, number_font, name_font, texture_cache)

        for b in buttons:
            b.draw(screen, button_font, mouse_pos)

        hint = hint_font.render(
            "Drag = move  |  Click = pick player  |  R = reset positions  |  Esc = quit",
            True, (230, 230, 230))
        screen.blit(hint, (MARGIN_SIDE, SCREEN_H - 22))

        if modal is not None:
            modal.draw(screen, modal_title_font, modal_row_font, mouse_pos)

        pygame.display.flip()
        clock.tick(FPS)
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
