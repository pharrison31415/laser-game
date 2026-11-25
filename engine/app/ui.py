"""
Engine-level overlay UI, drawn on top of every game: the pause button, the pause
menu and the game-select menu.

Everything is pressed by dwelling: hold a laser dot (any color, or the mouse with
--debug) on a button until its ring fills. A brief sweep across a button does
nothing, so games that use the whole screen (shine anywhere to jump) don't
pause by accident.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pygame

from engine.api.frame_data import Point

FG = (230, 230, 230)
DIM = (150, 150, 150)
FAINT = (70, 74, 84)
PANEL = (24, 27, 34)
BG = (12, 14, 18)
FILL = (50, 200, 120)

PAUSE_DWELL_MS = 600       # the corner button: quick, but not a sweep
BUTTON_DWELL_MS = 800      # menu buttons


@dataclass
class DwellButton:
    rect: pygame.Rect
    label: str
    action: str
    dwell_ms: float = BUTTON_DWELL_MS
    sublabel: str = ""
    progress: float = 0.0      # 0..1, how full the ring is
    hovered: bool = False

    def update(self, dt_ms: float, points: List[Point], armed: bool) -> bool:
        """Advance the dwell timer; True when the button fires. Not armed: the
        pointer must leave every button once before anything can fire again."""
        self.hovered = any(self.rect.collidepoint(p.x, p.y) for p in points)
        if self.hovered and armed:
            self.progress += dt_ms / self.dwell_ms
        else:
            self.progress = max(0.0, self.progress - dt_ms / 250.0)
        if self.progress >= 1.0:
            self.progress = 0.0
            return True
        return False


class Fonts:
    def __init__(self, screen_h: int):
        self.k = screen_h / 720.0
        self._cache: Dict[int, pygame.font.Font] = {}

    def get(self, size: int) -> pygame.font.Font:
        px = max(10, int(size * self.k))
        if px not in self._cache:
            self._cache[px] = pygame.font.Font(None, px)
        return self._cache[px]


def _ring(surface, center, radius, progress, width):
    if progress <= 0:
        return
    rect = pygame.Rect(0, 0, radius * 2, radius * 2)
    rect.center = center
    start = math.pi / 2
    pygame.draw.arc(surface, FILL, rect, start - progress * 2 * math.pi, start, width)


def _wrap(font, text, width) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if font.size(trial)[0] <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_button(surface, b: DwellButton, fonts: Fonts):
    k = fonts.k
    border = FG if b.hovered else FAINT
    pygame.draw.rect(surface, PANEL, b.rect, border_radius=int(10 * k))
    if b.progress > 0:      # fill from the left as the dwell builds
        fill = b.rect.copy()
        fill.width = int(b.rect.width * b.progress)
        pygame.draw.rect(surface, (30, 70, 52), fill, border_radius=int(10 * k))
    pygame.draw.rect(surface, border, b.rect, max(2, int(2 * k)), border_radius=int(10 * k))
    if b.sublabel:
        title = fonts.get(44).render(b.label, True, FG)
        surface.blit(title, title.get_rect(midtop=(b.rect.centerx, b.rect.y + int(22 * k))))
        font = fonts.get(26)
        y = b.rect.y + int(70 * k)
        for line in _wrap(font, b.sublabel, b.rect.width - int(36 * k))[:6]:
            img = font.render(line, True, DIM)
            surface.blit(img, img.get_rect(midtop=(b.rect.centerx, y)))
            y += font.get_linesize()
    else:
        img = fonts.get(44).render(b.label, True, FG)
        surface.blit(img, img.get_rect(center=b.rect.center))


# -- pause button ------------------------------------------------------------------

class PauseButton:
    """The pause icon in the top-right corner, drawn over the game."""

    def __init__(self, screen_size: Tuple[int, int]):
        w, h = screen_size
        self.size = max(44, int(h * 0.075))
        margin = max(18, int(h * 0.03))
        self.button = DwellButton(
            pygame.Rect(w - margin - self.size, margin, self.size, self.size),
            "", "pause", PAUSE_DWELL_MS)
        # laser points this close to the button are hidden from the game
        self.shield = self.button.rect.inflate(self.size // 4, self.size // 4)

    def update(self, dt_ms, points, armed) -> bool:
        return self.button.update(dt_ms, points, armed)

    def filter(self, points_by_color: Dict[str, List[Point]]) -> Dict[str, List[Point]]:
        return {c: [p for p in pts if not self.shield.collidepoint(p.x, p.y)]
                for c, pts in points_by_color.items()}

    def draw(self, surface):
        b = self.button
        r = b.rect
        color = FG if b.hovered else DIM
        pygame.draw.circle(surface, BG, r.center, r.width // 2)
        pygame.draw.circle(surface, color, r.center, r.width // 2, max(2, r.width // 22))
        bar_w, bar_h = max(3, r.width // 8), r.height * 0.38
        for dx in (-r.width * 0.12, r.width * 0.12):
            pygame.draw.rect(surface, color, (r.centerx + dx - bar_w / 2,
                                              r.centery - bar_h / 2, bar_w, bar_h))
        _ring(surface, r.center, r.width // 2 + max(4, r.width // 10), b.progress,
              max(3, r.width // 12))


# -- menus -------------------------------------------------------------------------

class Menu:
    """A screen of dwell buttons. update() returns the fired button's action."""

    def __init__(self, screen_size, fonts: Fonts, title: str, hint: str):
        self.w, self.h = screen_size
        self.fonts = fonts
        self.title = title
        self.hint = hint
        self.buttons: List[DwellButton] = []
        self.armed = False
        self.hint_y: Optional[int] = None     # None: at the bottom of the screen

    def update(self, dt_ms: float, points: List[Point]) -> Optional[str]:
        # arm only once the pointer is off every button (e.g. the laser that just
        # pressed "pause" or "menu" must not immediately press something here)
        if not self.armed and not any(b.rect.collidepoint(p.x, p.y)
                                      for b in self.buttons for p in points):
            self.armed = True
        for b in self.buttons:
            if b.update(dt_ms, points, self.armed):
                return b.action
        return None

    def draw(self, surface):
        k = self.fonts.k
        img = self.fonts.get(64).render(self.title, True, FG)
        surface.blit(img, img.get_rect(midtop=(self.w // 2, int(60 * k))))
        for b in self.buttons:
            draw_button(surface, b, self.fonts)
        img = self.fonts.get(24).render(self.hint, True, DIM)
        if self.hint_y is None:
            surface.blit(img, img.get_rect(midbottom=(self.w // 2, self.h - int(30 * k))))
        else:
            surface.blit(img, img.get_rect(midtop=(self.w // 2, self.hint_y)))


def pause_menu(screen_size, fonts: Fonts, game_title: str) -> Menu:
    w, h = screen_size
    k = fonts.k
    m = Menu(screen_size, fonts, f"{game_title}: paused",
             "Hold the laser on a button   ·   Esc resume   ·   R restart   ·   M menu")
    gap = int(40 * k)
    bw, bh = min(int(300 * k), (w - int(80 * k) - 2 * gap) // 3), int(110 * k)
    x0 = (w - (3 * bw + 2 * gap)) // 2
    y = int(h * 0.42)
    for i, (label, action) in enumerate([("Resume", "resume"), ("Restart", "restart"),
                                         ("Menu", "menu")]):
        m.buttons.append(DwellButton(pygame.Rect(x0 + i * (bw + gap), y, bw, bh), label, action))
    m.hint_y = y + bh + int(36 * k)
    return m


def game_menu(screen_size, fonts: Fonts, games: List[dict]) -> Menu:
    """One card per game; card action is 'play:<id>'."""
    w, h = screen_size
    k = fonts.k
    m = Menu(screen_size, fonts, "Choose a game",
             "Hold the laser on a game to play   ·   C calibrate   ·   Esc quit")
    cols = min(4, max(1, len(games)))
    rows = math.ceil(len(games) / cols)
    gap = int(28 * k)
    top, bottom = int(160 * k), h - int(80 * k)
    cw = (w - int(80 * k) - (cols - 1) * gap) // cols
    ch = min(int(230 * k), (bottom - top - (rows - 1) * gap) // max(1, rows))
    for i, g in enumerate(games):
        r, c = divmod(i, cols)
        in_row = min(cols, len(games) - r * cols)       # centre a short last row
        x0 = (w - (in_row * cw + (in_row - 1) * gap)) // 2
        rect = pygame.Rect(x0 + c * (cw + gap), top + r * (ch + gap), cw, ch)
        m.buttons.append(DwellButton(rect, g["title"], f"play:{g['id']}",
                                     sublabel=g.get("description", "")))
    return m


def list_games(games_dir: Path, load_manifest: Callable[[Path], dict]) -> List[dict]:
    out = []
    for d in sorted(games_dir.iterdir()):
        if d.name.startswith(("_", ".")) or not (d / "manifest.yaml").exists() \
                or not (d / "main.py").exists():
            continue
        man = load_manifest(d)
        out.append({"id": d.name, "title": man.get("title", d.name),
                    "description": man.get("description", ""), "manifest": man})
    return out
