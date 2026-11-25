import math
import pygame
from typing import Tuple


def draw_text(surface: pygame.Surface, text: str, pos: Tuple[int, int], color=(230, 230, 230), size=24):
    font = pygame.font.SysFont(None, size)
    surface.blit(font.render(text, True, color), pos)


# The platform's "hold the laser here" control (first used by quick-draw): an
# outlined circle with a thin progress ring just outside it, filling from the top.
HOLD_TARGET_COLOR = (100, 180, 255)
HOLD_RING_COLOR = (255, 255, 255)


def draw_hold_target(surface: pygame.Surface, center: Tuple[float, float], r: float, frac: float,
                     color=HOLD_TARGET_COLOR, ring_color=HOLD_RING_COLOR,
                     width: int = 4, ring_width: int = 2, ring_gap: float = 10):
    """Outlined circle of radius r; frac (0..1) of a ring at r + ring_gap is drawn."""
    cx, cy = int(center[0]), int(center[1])
    pygame.draw.circle(surface, color, (cx, cy), int(r), width)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        rr = int(r + ring_gap)
        rect = pygame.Rect(cx - rr, cy - rr, rr * 2, rr * 2)
        start = 0.5 * math.pi
        pygame.draw.arc(surface, ring_color, rect, start, start + 2 * math.pi * frac, ring_width)


def draw_hamburger(surface: pygame.Surface, center: Tuple[float, float], size: float, color, width: int):
    """Three horizontal bars, size wide, centred on center."""
    cx, cy = center
    gap = size * 0.32
    for dy in (-gap, 0, gap):
        pygame.draw.line(surface, color, (cx - size / 2, cy + dy), (cx + size / 2, cy + dy), width)
