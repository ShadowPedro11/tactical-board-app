"""
Formation templates for the tactical board.

Each formation is defined purely as outfield "lines" (goalkeeper excluded,
since the GK always sits in a fixed slot). For example "4-3-3" means
4 defenders, 3 midfielders, 3 forwards -- 10 outfield players total.

Positions are generated generically from these counts so adding a new
formation is just adding one line to FORMATIONS.
"""

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

# Depth (x, meters from a team's own goal line) of the first and last
# outfield line. Intermediate lines are spread evenly between them.
FIRST_LINE_X_M = 14.0
LAST_LINE_X_M = 48.0

# Keep tokens this far from the touchline when spreading a line across
# the pitch width.
Y_MARGIN_M = 7.0

FORMATIONS = {
    "4-4-2": [4, 4, 2],
    "4-3-3": [4, 3, 3],
    "3-5-2": [3, 5, 2],
    "4-2-3-1": [4, 2, 3, 1],
    "5-3-2": [5, 3, 2],
    "3-4-3": [3, 4, 3],
}

GK_X_M = 3.0

def _line_ys(count):
    if count == 1:
        return [PITCH_WIDTH_M / 2]

    if count == 2:
        # Narrower pair, useful for striker pairs or double pivots
        return [
            PITCH_WIDTH_M * 0.38,
            PITCH_WIDTH_M * 0.62,
        ]

    return _linspace(Y_MARGIN_M, PITCH_WIDTH_M - Y_MARGIN_M, count)


def _linspace(start, stop, n):
    if n == 1:
        return [(start + stop) / 2]
    step = (stop - start) / (n - 1)
    return [start + step * i for i in range(n)]


def outfield_slots(formation_name):
    """
    Returns a flat list of (x_m, y_m) for the 10 outfield slots of a
    formation, in defender-to-forward, top-to-bottom order, for a team
    attacking from left (x=0) toward right (x=105). Mirror for the other
    side by doing x' = PITCH_LENGTH_M - x.
    """
    lines = FORMATIONS[formation_name]
    line_xs = _linspace(FIRST_LINE_X_M, LAST_LINE_X_M, len(lines))

    slots = []
    for count, x in zip(lines, line_xs):
        ys = _line_ys(count)
        for y in ys:
            slots.append((x, y))
    return slots


def gk_slot():
    return (GK_X_M, PITCH_WIDTH_M / 2)


def mirror_x(x_m):
    return PITCH_LENGTH_M - x_m
