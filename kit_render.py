import pygame

OUTLINE_COLOR = (20, 20, 20)


def _normalize_pattern(pattern):
    """Map scraped ZeroZero SVG pattern ids to token renderer patterns."""
    pattern = (pattern or "solid").lower()

    if pattern in {"solid", "basic_plain_1-color"}:
        return "solid"

    if "vertical" in pattern and "stripe" in pattern:
        # Example: vertical-2-stripes_3_col-2
        return "vertical_stripes"

    if "horizontal" in pattern or "hoop" in pattern:
        return "hoops"

    if "half" in pattern:
        return "halves"

    return pattern


def _base_square(diameter, pattern, colors):
    """Fill a (diameter x diameter) square with the requested pattern."""
    surf = pygame.Surface((diameter, diameter), pygame.SRCALPHA)

    pattern = _normalize_pattern(pattern)

    if not colors:
        colors = [(200, 200, 200)]

    if pattern == "solid" or len(colors) == 1:
        surf.fill(colors[0])
        return surf

    c1, c2 = colors[0], colors[1]

    if pattern == "stripes":
        # Generic alternating vertical stripes.
        n = 6
        band = diameter / n
        for i in range(n):
            color = c1 if i % 2 == 0 else c2
            rect = pygame.Rect(int(i * band), 0, int(band) + 1, diameter)
            pygame.draw.rect(surf, color, rect)

    elif pattern == "vertical_stripes":
        # Better match for zerozero's "vertical-2-stripes_3_col-2":
        # base color with two vertical accent stripes.
        surf.fill(c1)

        stripe_w = max(2, diameter // 7)
        gap = max(2, diameter // 7)

        total_w = stripe_w * 2 + gap
        start_x = (diameter - total_w) // 2

        pygame.draw.rect(
            surf,
            c2,
            pygame.Rect(start_x, 0, stripe_w, diameter),
        )
        pygame.draw.rect(
            surf,
            c2,
            pygame.Rect(start_x + stripe_w + gap, 0, stripe_w, diameter),
        )

    elif pattern == "hoops":
        n = 6
        band = diameter / n
        for i in range(n):
            color = c1 if i % 2 == 0 else c2
            rect = pygame.Rect(0, int(i * band), diameter, int(band) + 1)
            pygame.draw.rect(surf, color, rect)

    elif pattern == "halves":
        surf.fill(c1)
        pygame.draw.rect(
            surf,
            c2,
            pygame.Rect(diameter // 2, 0, diameter - diameter // 2, diameter),
        )

    else:
        surf.fill(c1)

    return surf


def build_token_texture(pattern, colors, diameter):
    """
    Returns an RGBA pygame.Surface of size (diameter, diameter): the kit
    pattern clipped to a circle, with a dark outline ring.
    """
    pattern_surf = _base_square(diameter, pattern, colors)

    mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(
        mask,
        (255, 255, 255, 255),
        (diameter // 2, diameter // 2),
        diameter // 2,
    )

    pattern_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    pygame.draw.circle(
        pattern_surf,
        OUTLINE_COLOR,
        (diameter // 2, diameter // 2),
        diameter // 2,
        width=2,
    )

    return pattern_surf