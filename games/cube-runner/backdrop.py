"""
Abstract geometric backdrop: a dim vertical gradient, a slowly scrolling grid of
large tiles, and outlined squares floating at a few depths (nearer ones are
larger, lighter and scroll faster). All monochrome and only a few shades above
the background, so obstacles (white outlines) always read in front.
"""
import math
import random

import pygame

TOP = (8, 9, 12)                 # gradient: darker at the top of the screen...
BOTTOM = (19, 21, 27)            # ...lighter towards the ground
GRID = (21, 24, 30)
GRID_BEVEL = (25, 28, 35)
TILE_U = 4.0                     # grid tile size, in cubes
GRID_FACTOR = 0.12               # grid scrolls at this fraction of the ground speed

# floating squares: (parallax factor, spacing U, size range U, color, fill, line width, salt)
LAYERS = [
    (0.22, 7.0, (1.2, 2.4), (24, 27, 34), None, 1, 101),
    (0.40, 9.0, (2.0, 3.6), (30, 33, 41), (15, 17, 22), 2, 202),
]


class Backdrop:
    def __init__(self):
        self._grad = None

    def _gradient(self, w, h):
        if self._grad is None or self._grad.get_size() != (w, h):
            g = pygame.Surface((1, h)).convert()
            for y in range(h):
                k = y / max(1, h - 1)
                g.set_at((0, y), tuple(int(a + (b - a) * k) for a, b in zip(TOP, BOTTOM)))
            self._grad = pygame.transform.scale(g, (w, h))
        return self._grad

    def draw(self, surface, scroll, ground_y, ppu, cam_y, time_s):
        """scroll: world x of the camera; ground_y: screen y of the ground line;
        cam_y: camera height in U (deeper layers follow it less)."""
        w, h = surface.get_size()
        surface.blit(self._gradient(w, h), (0, 0))

        # tiled grid: each tile has a faint bevel line inside its top-left corner
        t = TILE_U * ppu * 1.4
        ox = -(scroll * GRID_FACTOR * ppu) % t
        oy = (ground_y + cam_y * ppu * 0.1) % t
        bev = max(2, int(t * 0.08))
        x = ox - t
        while x < w:
            pygame.draw.line(surface, GRID, (int(x), 0), (int(x), h), 1)
            pygame.draw.line(surface, GRID_BEVEL, (int(x) + bev, 0), (int(x) + bev, h), 1)
            x += t
        y = oy - t
        while y < h:
            pygame.draw.line(surface, GRID, (0, int(y)), (w, int(y)), 1)
            pygame.draw.line(surface, GRID_BEVEL, (0, int(y) + bev), (w, int(y) + bev), 1)
            y += t

        # floating outlined squares, slowly turning; some with a square inside
        for factor, spacing, sizes, color, fill, lw, salt in LAYERS:
            cam = scroll * factor
            first = int(cam / spacing) - 2
            n = int(w / (spacing * ppu)) + 4
            base = ground_y + cam_y * ppu * factor
            for i in range(first, first + n):
                r = random.Random(i * 7919 + salt)
                if r.random() < 0.35:
                    continue                      # gaps keep it from reading as a pattern
                size = r.uniform(*sizes) * ppu
                cx = (i * spacing + r.uniform(0, spacing * 0.6) - cam) * ppu
                # some sit below the ground line: hidden by the ground, seen through pits
                cy = base - r.uniform(-5.0, 11.0) * ppu
                ang = r.uniform(0, math.pi / 2) + time_s * r.uniform(-0.25, 0.25)
                pts = _square(cx, cy, size / 2, ang)
                if fill:
                    pygame.draw.polygon(surface, fill, pts)
                pygame.draw.polygon(surface, color, pts, lw)
                if r.random() < 0.45:
                    pygame.draw.polygon(surface, color, _square(cx, cy, size * 0.22, ang), 1)


def _square(cx, cy, half, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + half * (c * dx - s * dy), cy + half * (s * dx + c * dy))
            for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
