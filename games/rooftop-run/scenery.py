"""
Building and skyline art, all in grays: facades rendered once into cached tiles
(per building style and zoom bucket) and blitted, roof clutter as dim silhouettes
behind the roof line, and a detailed distant skyline.

Nothing here affects gameplay; it only reads a building's seed, size and kind.
"""
import math
import random
from typing import Dict, List, Tuple

import pygame

from .const import *

PPU_STEP = 0.5          # zoom bucket for cached surfaces, in px per unit
FLOORS_PER_TILE = 4     # a facade tile is this many floors tall
_CACHE_MAX = 48
REBUILDS_PER_FRAME = 1  # cached surfaces re-rendered per frame; others reuse the nearest zoom for a moment


class _LRU(dict):
    budget = REBUILDS_PER_FRAME

    def nearest(self, key):
        """A cached entry matching key in all but its last field (the zoom bucket), if
        the rebuild budget for this frame is spent; None means: build it now."""
        if self.budget > 0:
            self.budget -= 1
            return None
        best = None
        for k in self:
            if k[:-1] == key[:-1] and (best is None or abs(k[-1] - key[-1]) < abs(best[-1] - key[-1])):
                best = k
        if best is None:
            return None
        return self[best]

    def __init__(self, size=_CACHE_MAX):
        super().__init__()
        self.size = size

    def put(self, key, value):
        if len(self) >= self.size:
            for k in list(self.keys())[: self.size // 4]:
                del self[k]
        self[key] = value
        return value


def bucket(ppu: float) -> float:
    return max(PPU_STEP, round(ppu / PPU_STEP) * PPU_STEP)


def _shade(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)


def style_seed(b) -> int:
    # b.seed varies per building in the game; mix in x so hand-built scenes vary too
    return (b.seed * 2654435761 + int(b.x * 13)) & 0x7FFFFFFF


# -- facades ---------------------------------------------------------------------

class FacadeStyle:
    """The look of one building, fixed by its seed and width (in world units)."""

    def __init__(self, seed: int, w: float, kind: str):
        r = random.Random(seed)
        self.kind = kind
        self.style = r.choice(["punched", "punched", "grid", "ribbon", "tenement"])
        self.fh = r.choice([2.6, 2.8, 3.0, 3.2])
        self.margin = r.uniform(0.6, 0.9)
        bw = {"tenement": r.uniform(1.7, 2.1), "grid": r.uniform(2.2, 2.8),
              "ribbon": r.uniform(2.4, 3.0)}.get(self.style, r.uniform(1.9, 2.5))
        self.n = max(1, int((w - 2 * self.margin) / bw))
        self.bw = (w - 2 * self.margin) / self.n
        self.group = r.choice([2, 3, 4])
        self.tile_bays = min(self.n, self.group * max(1, round(8 / self.group)))
        self.base = _shade(BUILDING_FILL, r.randint(-4, 3))
        self.lit_p = 0.0 if kind == "crumble" else r.uniform(0.12, 0.35)
        self.cornice = r.choice(["dentil", "coping", "corbel", "band"])
        self.cornice_u = {"coping": 0.55, "band": 0.8}.get(self.cornice, 1.0)
        self.fire_bay = r.randrange(self.tile_bays) if self.style == "tenement" and self.tile_bays >= 2 else None
        self.pipe_bay = (r.randrange(self.tile_bays) if self.style in ("punched", "tenement")
                         and r.random() < 0.5 else None)
        if self.pipe_bay is not None and self.fire_bay is not None and abs(self.pipe_bay - self.fire_bay) < 2:
            self.pipe_bay = None
        self.seed = seed


def _window(s, x, y, w, h, col, base, mull, sill, ppu, blind=0.0):
    pygame.draw.rect(s, col, (x, y, w, h))
    if blind > 0 and col in (WINDOW_LIT, WINDOW_LIT_DIM):     # a blind pulled part way down
        pygame.draw.rect(s, _shade(col, -22), (x, y, w, int(h * blind)))
    dark = _shade(col, -14)
    pygame.draw.line(s, dark, (x, y), (x + w - 1, y), max(1, int(ppu * 0.06)))       # recess shadow
    pygame.draw.line(s, dark, (x, y), (x, y + h - 1), max(1, int(ppu * 0.05)))
    if mull and w > 10:
        pygame.draw.line(s, base, (x + w // 2, y), (x + w // 2, y + h - 1), max(1, int(ppu * 0.05)))
        if h > 14:
            ty = y + int(h * 0.3)
            pygame.draw.line(s, base, (x, ty), (x + w - 1, ty), max(1, int(ppu * 0.04)))
    if sill:
        sh = max(2, int(ppu * 0.12))
        ex = max(1, int(ppu * 0.1))
        pygame.draw.rect(s, BUILDING_LIGHT, (x - ex, y + h, w + 2 * ex, sh))
        pygame.draw.line(s, BUILDING_SHADE, (x - ex, y + h + sh), (x + w + ex - 1, y + h + sh), 1)
        pygame.draw.rect(s, BUILDING_SHADE, (x - ex // 2, y - max(2, int(ppu * 0.14)), w + ex, max(2, int(ppu * 0.14))))


def _blind(r):
    return r.uniform(0.2, 0.6) if r.random() < 0.3 else 0.0


def _window_color(r, lit_p):
    v = r.random()
    if v < lit_p * 0.55:
        return WINDOW_LIT
    if v < lit_p:
        return WINDOW_LIT_DIM
    return WINDOW_DARK if r.random() < 0.8 else _shade(WINDOW_DARK, 6)


def render_floors(st: FacadeStyle, ppu: float) -> pygame.Surface:
    """FLOORS_PER_TILE floors x tile_bays bays of facade, at ppu."""
    W = max(1, round(st.tile_bays * st.bw * ppu))
    fhp = st.fh * ppu
    H = max(1, round(FLOORS_PER_TILE * fhp))
    s = pygame.Surface((W, H)).convert()
    s.fill(st.base)
    r = random.Random(st.seed + 17)
    bwp = st.bw * ppu
    for i in range(FLOORS_PER_TILE):
        yf = i * fhp
        if st.style == "ribbon":
            gy, gh = yf + fhp * 0.28, fhp * 0.46
            pane = bwp / 3
            for k in range(int(round(W / pane))):
                pygame.draw.rect(s, _window_color(r, st.lit_p), (int(k * pane), int(gy), int(pane) + 1, int(gh)))
            pygame.draw.line(s, _shade(WINDOW_DARK, -8), (0, int(gy)), (W, int(gy)), max(1, int(ppu * 0.08)))
            for k in range(int(round(W / pane)) + 1):
                xx = int(k * pane)
                pygame.draw.line(s, BUILDING_LIGHT if k % 3 == 0 else st.base, (xx, int(gy)), (xx, int(gy + gh)),
                                 max(1, int(ppu * (0.1 if k % 3 == 0 else 0.05))))
        else:
            for k in range(st.tile_bays):
                bx = k * bwp
                if st.style == "grid":
                    ww, wh, wy = bwp * 0.78, fhp * 0.62, yf + fhp * 0.2
                    _window(s, int(bx + (bwp - ww) / 2), int(wy), int(ww), int(wh),
                            _window_color(r, st.lit_p), st.base, True, False, ppu, _blind(r))
                elif st.style == "tenement":
                    ww, wh, wy = bwp * 0.42, fhp * 0.5, yf + fhp * 0.26
                    _window(s, int(bx + (bwp - ww) / 2), int(wy), int(ww), int(wh),
                            _window_color(r, st.lit_p), st.base, True, True, ppu, _blind(r))
                else:
                    ww, wh, wy = bwp * 0.5, fhp * 0.52, yf + fhp * 0.24
                    _window(s, int(bx + (bwp - ww) / 2), int(wy), int(ww), int(wh),
                            _window_color(r, st.lit_p), st.base, ww > 0.9 * ppu, True, ppu, _blind(r))
        # floor band / stringcourse
        bh = max(1, int(ppu * (0.16 if st.style in ("punched", "tenement") else 0.1)))
        pygame.draw.rect(s, BUILDING_LIGHT, (0, int(yf), W, bh))
        pygame.draw.line(s, BUILDING_SHADE, (0, int(yf) + bh), (W, int(yf) + bh), 1)
    # pilasters / fins every `group` bays
    pw = max(2, int(ppu * (0.32 if st.style in ("punched", "tenement") else 0.14)))
    for k in range(0, st.tile_bays + 1, st.group):
        xx = int(k * bwp) - pw // 2
        pygame.draw.rect(s, _shade(st.base, 7), (xx, 0, pw, H))
        pygame.draw.line(s, BUILDING_SHADE, (xx + pw, 0), (xx + pw, H), 1)
    if st.pipe_bay is not None:          # drainpipe with brackets, down the whole facade
        px = int(st.pipe_bay * bwp + bwp * 0.06)
        pw = max(2, int(ppu * 0.12))
        pygame.draw.rect(s, BUILDING_SHADE, (px, 0, pw, H))
        pygame.draw.line(s, BUILDING_LIGHT, (px, 0), (px, H), 1)
        for i in range(FLOORS_PER_TILE * 2):
            yy = int(i * fhp / 2)
            pygame.draw.rect(s, FIRE_ESCAPE, (px - 1, yy, pw + 2, max(2, int(ppu * 0.08))))
    if st.style == "tenement":           # window air conditioners
        ra = random.Random(st.seed + 3)
        for i in range(FLOORS_PER_TILE):
            for k in range(st.tile_bays):
                if k != st.fire_bay and k != (st.fire_bay or 0) + 1 and ra.random() < 0.18:
                    aw, ah = bwp * 0.32, max(3, ppu * 0.38)
                    ax, ay = k * bwp + (bwp - aw) / 2, i * fhp + fhp * 0.76 - ah
                    pygame.draw.rect(s, BUILDING_SHADE, (int(ax), int(ay), int(aw), int(ah)))
                    pygame.draw.line(s, BUILDING_LIGHT, (int(ax), int(ay)), (int(ax + aw) - 1, int(ay)), 1)
    if st.fire_bay is not None:
        _fire_escape(s, st, ppu, fhp, bwp)
    if st.kind == "crumble":
        _damage(s, st, ppu, W, H)
    return s


def _fire_escape(s, st, ppu, fhp, bwp):
    """Iron landings with railings, zig-zag stairs between them."""
    x0 = int(st.fire_bay * bwp + bwp * 0.08)
    w = int(min(bwp * 1.6, s.get_width() - x0 - 2))
    iron = FIRE_ESCAPE
    lw = max(1, int(ppu * 0.07))
    for i in range(FLOORS_PER_TILE):
        py = int(i * fhp + fhp * 0.8)
        ry = py - int(ppu * 0.55)
        pygame.draw.line(s, iron, (x0, py), (x0 + w, py), max(2, int(ppu * 0.1)))
        pygame.draw.line(s, iron, (x0, ry), (x0 + w, ry), lw)
        for k in range(0, 7):
            xx = x0 + w * k // 6
            pygame.draw.line(s, iron, (xx, ry), (xx, py), 1)
        # stairs down to the landing below, alternating direction
        nb = py + int(fhp)
        a, c = (x0 + int(w * 0.15), x0 + int(w * 0.85)) if i % 2 == 0 else (x0 + int(w * 0.85), x0 + int(w * 0.15))
        pygame.draw.line(s, iron, (a, py), (c, nb), max(1, int(ppu * 0.09)))
        steps = 6
        for k in range(1, steps):
            t = k / steps
            xx, yy = a + (c - a) * t, py + (nb - py) * t
            pygame.draw.line(s, iron, (xx - ppu * 0.12, yy), (xx + ppu * 0.12, yy), 1)


def _damage(s, st, ppu, W, H):
    """Crumbling buildings: broken windows and hairline cracks across the facade."""
    r = random.Random(st.seed + 5)
    crack = _shade(FIRE_ESCAPE, -6)
    for _ in range(max(3, W // int(ppu * 1.6))):
        x, y = r.uniform(0, W), r.uniform(0, H)
        pts = [(x, y)]
        for _ in range(r.randint(3, 6)):
            x += r.uniform(-0.6, 0.6) * ppu
            y += r.uniform(0.3, 0.9) * ppu
            pts.append((x, y))
        pygame.draw.lines(s, crack, False, pts, max(1, int(ppu * 0.07)))
        if len(pts) > 3 and r.random() < 0.6:          # a branch off the crack
            bx, by = pts[2]
            pygame.draw.line(s, crack, (bx, by), (bx + r.uniform(-0.8, 0.8) * ppu, by + r.uniform(0.3, 0.8) * ppu), 1)
    for _ in range(max(1, W // int(ppu * 4))):   # chunks knocked out of the wall
        x, y, rr = r.uniform(0, W), r.uniform(0, H), r.uniform(0.25, 0.6) * ppu
        poly = [(x + math.cos(a) * rr * r.uniform(0.5, 1.1), y + math.sin(a) * rr * r.uniform(0.5, 1.1))
                for a in [k * math.pi / 3 for k in range(6)]]
        pygame.draw.polygon(s, crack, poly)
        pygame.draw.polygon(s, BUILDING_SHADE, poly, 1)


def render_cornice(st: FacadeStyle, ppu: float, tile_w: int) -> pygame.Surface:
    h = max(2, round(st.cornice_u * ppu))
    s = pygame.Surface((tile_w, h)).convert()
    s.fill(st.base)
    lip = max(2, int(ppu * 0.18))
    pygame.draw.rect(s, BUILDING_LIGHT, (0, 0, tile_w, lip))                    # coping under the roof edge
    pygame.draw.line(s, BUILDING_SHADE, (0, lip), (tile_w, lip), max(1, int(ppu * 0.06)))
    if st.cornice == "dentil":
        dy, dh, step = lip + int(ppu * 0.25), max(2, int(ppu * 0.22)), max(4, ppu * 0.35)
        pygame.draw.rect(s, _shade(st.base, 5), (0, lip + 1, tile_w, dy - lip - 1))
        x = 0.0
        while x < tile_w:
            pygame.draw.rect(s, BUILDING_SHADE, (int(x), dy, max(2, int(step * 0.45)), dh))
            x += step
    elif st.cornice == "corbel":
        step = max(6, ppu * 0.7)
        y0, y1 = lip + 1, h - max(2, int(ppu * 0.15))
        x = 0.0
        while x < tile_w:
            pygame.draw.polygon(s, _shade(st.base, 6), [(x, y0), (x + step, y0), (x + step / 2, y1)])
            pygame.draw.line(s, BUILDING_SHADE, (x + step / 2, y1), (x + step, y0), 1)
            x += step
    elif st.cornice == "band":
        pygame.draw.rect(s, _shade(st.base, 6), (0, lip + int(ppu * 0.15), tile_w, int(ppu * 0.3)))
    pygame.draw.line(s, BUILDING_SHADE, (0, h - 1), (tile_w, h - 1), max(1, int(ppu * 0.08)))
    return s


class Facades:
    def __init__(self):
        self.styles: Dict[tuple, FacadeStyle] = {}
        self.tiles = _LRU(24)       # facade tiles are the big surfaces: keep fewer

    def new_frame(self):
        self.tiles.budget = REBUILDS_PER_FRAME

    def style(self, b) -> FacadeStyle:
        key = (style_seed(b), round(b.w, 3), b.kind)
        st = self.styles.get(key)
        if st is None:
            if len(self.styles) > 256:
                self.styles.clear()
            st = self.styles[key] = FacadeStyle(key[0], b.w, b.kind)
        return st

    def get(self, st: FacadeStyle, ppu: float):
        pb = bucket(ppu)
        key = (st.seed, round(st.bw, 4), st.n, st.kind, pb)
        t = self.tiles.get(key) or self.tiles.nearest(key)
        if t is None:
            floors = render_floors(st, pb)
            t = self.tiles.put(key, (floors, render_cornice(st, pb, floors.get_width()), pb))
        return t

    def draw(self, surface, b, st, ppu, x0, x1, top_y, bottom_y, cornice=True):
        """Facade between screen columns x0..x1, from top_y (a roof edge) down to bottom_y."""
        if top_y >= bottom_y or ppu * st.bw < 12:
            return
        floors, corn, pb = self.get(st, ppu)
        tw, th = floors.get_size()
        clip = surface.get_clip()
        surface.set_clip(pygame.Rect(x0, top_y, x1 - x0, bottom_y - top_y).clip(clip))
        sh = surface.get_height()
        y = top_y
        m = int(st.margin * pb)
        end = x0 + m + round(st.n * st.bw * pb)            # last bay edge
        if cornice:
            for xx in range(x0, x1, corn.get_width()):
                surface.blit(corn, (xx, y))
            y += corn.get_height()
        y += int(pb * 0.3)
        # skip whole tiles above the screen
        if y + th < 0:
            y += ((-y) // th) * th
        while y < min(bottom_y, sh):
            xx = x0 + m
            while xx < end:
                surface.blit(floors, (xx, y), (0, 0, min(tw, end - xx), th))
                xx += tw
            y += th
        surface.set_clip(clip)


# -- roof clutter -----------------------------------------------------------------

def clutter_items(b) -> List[tuple]:
    """Background roof clutter for a building, in units relative to its left edge."""
    r = random.Random(style_seed(b) + 99)
    items = []
    x = r.uniform(2.5, 5.0)
    while x < b.w - 2.5:
        kind = r.choices(["tower", "mast", "vents", "dish", None], [3, 3, 3, 2, 3])[0]
        if kind == "tower" and x + 2.4 < b.w - 1.5:
            items.append(("tower", x, r.uniform(1.6, 2.2), r.uniform(2.0, 3.0)))
            x += r.uniform(7, 12)
        elif kind == "mast":
            items.append(("mast", x, r.uniform(3.5, 6.5), r.random()))
            x += r.uniform(4, 9)
        elif kind == "vents":
            n = r.randint(1, 3)
            items.append(("vents", x, n, r.uniform(0.6, 1.1)))
            x += r.uniform(4, 8)
        elif kind == "dish":
            items.append(("dish", x, r.uniform(0.8, 1.2)))
            x += r.uniform(4, 8)
        elif kind == "sign" and x + 5 < b.w - 1.5:
            items.append(("sign", x, r.uniform(3.5, 5.0), r.uniform(1.2, 1.8)))
            x += r.uniform(8, 12)
        else:
            x += r.uniform(3, 6)
    return items


def draw_clutter(surface, items, sx, sy, ppu, t):
    """sx/sy: world->screen for this building's roof (sx(dx) from left edge, sy(dy) above roof)."""
    C, L = CLUTTER, CLUTTER_LINE
    lw = max(1, int(ppu * 0.08))
    for it in items:
        k = it[0]
        if k == "tower":            # water tower: legs with cross-bracing, a barrel tank, cone roof
            _, x, w, leg = it
            xa, xb = sx(x + 0.2), sx(x + w - 0.2)
            yl, yt = sy(0), sy(leg)
            for xx in (xa, xb, (xa + xb) / 2):
                pygame.draw.line(surface, C, (xx, yl), (xx, yt), max(2, lw))
            pygame.draw.line(surface, C, (xa, yl), (xb, yt), 1)
            pygame.draw.line(surface, C, (xb, yl), (xa, yt), 1)
            th = w * 1.05
            rect = pygame.Rect(int(sx(x)), int(sy(leg + th)), int(w * ppu), int(th * ppu))
            pygame.draw.rect(surface, C, rect)
            for f in (0.3, 0.65):
                yy = rect.top + int(rect.height * f)
                pygame.draw.line(surface, L, (rect.left, yy), (rect.right - 1, yy), 1)
            pygame.draw.line(surface, L, (rect.left, rect.top), (rect.left, rect.bottom), 1)
            pygame.draw.polygon(surface, C, [(sx(x - 0.12), sy(leg + th)), (sx(x + w / 2), sy(leg + th + w * 0.45)),
                                             (sx(x + w + 0.12), sy(leg + th))])
            pygame.draw.line(surface, L, (sx(x - 0.12), sy(leg + th)), (sx(x + w / 2), sy(leg + th + w * 0.45)), 1)
            lx = sx(x + w * 0.75)       # ladder up the side
            for yy in range(int(sy(leg + th)), int(yl), max(3, int(ppu * 0.3))):
                pygame.draw.line(surface, C, (lx, yy), (lx + ppu * 0.25, yy), 1)
        elif k == "mast":           # antenna mast with crossbars and a slow blinking light
            _, x, h, ph = it
            xx = sx(x)
            pygame.draw.line(surface, C, (xx, sy(0)), (xx, sy(h)), max(2, lw))
            for f in (0.55, 0.8):
                yy = sy(h * f)
                pygame.draw.line(surface, C, (xx - ppu * 0.35 * (1.2 - f), yy), (xx + ppu * 0.35 * (1.2 - f), yy), max(1, lw))
            pygame.draw.line(surface, C, (xx, sy(0)), (xx - ppu * 0.6, sy(0)), 1)
            pygame.draw.line(surface, C, (xx - ppu * 0.6, sy(0)), (xx, sy(h * 0.4)), 1)
            on = (t * 0.8 + ph) % 1.0 < 0.35
            pygame.draw.circle(surface, BEACON if on else L, (int(xx), int(sy(h))), max(2, int(ppu * 0.12)))
        elif k == "vents":          # thin vent stacks with caps
            _, x, n, h = it
            for j in range(n):
                xx = sx(x + j * 0.45)
                hh = h * (1 - 0.2 * j)
                pygame.draw.line(surface, C, (xx, sy(0)), (xx, sy(hh)), max(2, int(ppu * 0.14)))
                pygame.draw.rect(surface, L, (int(xx - ppu * 0.15), int(sy(hh)) - 1, int(ppu * 0.3) + 1, max(2, int(ppu * 0.1))))
        elif k == "dish":           # satellite dish on a pole
            _, x, d = it
            xx, top = sx(x), sy(1.3)
            pygame.draw.line(surface, C, (xx, sy(0)), (xx, top), max(1, lw))
            box = pygame.Rect(0, 0, int(d * ppu), int(d * ppu * 0.5))
            box.center = (int(xx - d * ppu * 0.15), int(top - d * ppu * 0.2))
            pygame.draw.ellipse(surface, C, box)
            pygame.draw.arc(surface, L, box, 0.2, 3.0, 1)
            pygame.draw.line(surface, C, box.center, (box.centerx + d * ppu * 0.35, box.top - d * ppu * 0.25), 1)
        elif k == "sign":           # billboard: lattice frame on stilts, blank panel up high
            _, x, w, ph = it
            base = 2.4
            pygame.draw.rect(surface, C, (int(sx(x)), int(sy(base + ph)), int(w * ppu), int(ph * ppu)))
            pygame.draw.rect(surface, L, (int(sx(x)), int(sy(base + ph)), int(w * ppu), int(ph * ppu)), 1)
            for f in (0.15, 0.5, 0.85):
                xx = sx(x + w * f)
                pygame.draw.line(surface, C, (xx, sy(0)), (xx, sy(base)), max(2, lw))
            for f0, f1 in ((0.15, 0.5), (0.5, 0.85)):
                pygame.draw.line(surface, C, (sx(x + w * f0), sy(0)), (sx(x + w * f1), sy(base)), 1)
                pygame.draw.line(surface, C, (sx(x + w * f1), sy(0)), (sx(x + w * f0), sy(base)), 1)


# -- distant skyline ----------------------------------------------------------------

class Skyline:
    """A parallax layer of distant towers, each rendered once per zoom bucket."""

    def __init__(self, layer: int, color, win, spacing, heights):
        self.layer, self.color, self.win = layer, color, win
        self.spacing, self.heights = spacing, heights
        self.cache = _LRU()

    def new_frame(self):
        self.cache.budget = REBUILDS_PER_FRAME

    def tower(self, i: int, ppu: float, depth: int):
        pb = bucket(ppu)
        key = (i, depth, pb)
        t = self.cache.get(key) or self.cache.nearest(key)
        if t is not None:
            return t
        r = random.Random(i * 7919 + self.layer * 1000)
        bw = r.uniform(0.6, 1.0) * self.spacing
        bh = r.uniform(*self.heights)
        W = max(2, int(bw * pb) + 1)
        crown = r.choice(["flat", "flat", "setback", "spire", "antenna", "stepped", "tank"])
        extra = int(pb * (3.5 if crown in ("spire", "antenna") else 1.6))
        s = pygame.Surface((W, depth + extra)).convert()
        s.fill(BG)
        s.set_colorkey(BG)
        c = self.color
        body_top = extra
        pygame.draw.rect(s, c, (0, body_top, W, depth))
        beacon = None
        if crown == "setback":
            iw = int(W * r.uniform(0.45, 0.7))
            pygame.draw.rect(s, c, ((W - iw) // 2, body_top - int(pb * 1.2), iw, int(pb * 1.2) + 1))
        elif crown == "stepped":
            for k in range(3):
                iw = int(W * (0.8 - k * 0.22))
                pygame.draw.rect(s, c, ((W - iw) // 2, body_top - int(pb * 0.5 * (k + 1)), iw, int(pb * 0.5) + 1))
        elif crown == "spire":
            cx = W // 2
            pygame.draw.polygon(s, c, [(cx - W * 0.2, body_top), (cx, body_top - pb * 2.2), (cx + W * 0.2, body_top)])
            pygame.draw.line(s, c, (cx, body_top - pb * 2.2), (cx, 1), max(1, int(pb * 0.06)))
            beacon = (cx, 1)
        elif crown == "tank":           # a little water tower on the roof
            tx, tw = int(W * r.uniform(0.2, 0.6)), max(3, int(pb * 1.1))
            pygame.draw.rect(s, c, (tx, body_top - int(pb * 1.3), tw, int(pb * 0.8)))
            pygame.draw.polygon(s, c, [(tx - 1, body_top - int(pb * 1.3)), (tx + tw / 2, body_top - int(pb * 1.6)),
                                       (tx + tw, body_top - int(pb * 1.3))])
            for lx in (tx + 1, tx + tw - 2):
                pygame.draw.line(s, c, (lx, body_top - int(pb * 0.5)), (lx, body_top), 1)
        elif crown == "antenna":
            cx = int(W * r.uniform(0.3, 0.7))
            pygame.draw.line(s, c, (cx, body_top), (cx, 1), max(1, int(pb * 0.08)))
            pygame.draw.line(s, c, (cx - pb * 0.3, extra // 2), (cx + pb * 0.3, extra // 2), 1)
            beacon = (cx, 1)
        # window speckle
        cw, ch = max(2, int(pb * 0.55)), max(3, int(pb * 0.75))
        ww, wh = max(1, int(pb * 0.22)), max(1, int(pb * 0.28))
        p = r.uniform(0.04, 0.16)
        y = body_top + ch
        while y < body_top + depth:
            x = cw // 2
            while x + ww < W - 1:
                if r.random() < p:
                    pygame.draw.rect(s, self.win, (x, y, ww, wh))
                x += cw
            y += ch
        # split: a small colour-keyed crown and an opaque body (much faster to blit)
        crown_s = s.subsurface((0, 0, W, body_top + 1)).copy()
        crown_s.set_colorkey(BG)
        body_s = pygame.Surface((W, depth)).convert()
        body_s.blit(s, (0, -body_top))
        t = self.cache.put(key, (crown_s, body_s, body_top, beacon, r.random()))
        return t


def draw_skyline(surface, sky: Skyline, factor, ppu, cam_x, base_y, runner_sx, h, w, vfactor_dummy, time):
    spacing = sky.spacing
    first = int(cam_x / spacing) - 2
    depth = int(h * 0.3)
    for i in range(first, first + int(w / (spacing * ppu)) + 4):
        r = random.Random(i * 7919 + sky.layer * 1000)
        bw = r.uniform(0.6, 1.0) * spacing
        bh = r.uniform(*sky.heights)
        x = (i * spacing - cam_x) * ppu + runner_sx * 0.5
        top = base_y - bh * ppu * 0.6 - h * 0.1
        crown, body, body_top, beacon, ph = sky.tower(i, ppu, depth)
        surface.blit(crown, (int(x), int(top) - body_top))
        surface.blit(body, (int(x), int(top)))
        below = int(top) + depth
        if below < h:
            pygame.draw.rect(surface, sky.color, (int(x), below, body.get_width(), h - below))
        if beacon is not None:
            k = 0.5 + 0.5 * math.sin(time * 2.2 + ph * 6.28)
            col = tuple(int(a + (b2 - a) * k * k) for a, b2 in zip(sky.color, SKY_BEACON))
            pygame.draw.circle(surface, col, (int(x) + beacon[0], int(top) - body_top + beacon[1] + 1), max(1, int(ppu * 0.12)))
