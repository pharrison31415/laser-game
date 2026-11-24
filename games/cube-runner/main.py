import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import List

import pygame

from engine.api import Game, FrameData
from engine.app.context import Context

from .const import *
from .world import World


# ---------------------------------------------------------------------------
# Game wrapper
# ---------------------------------------------------------------------------

class State(Enum):
    Start = 1
    Playing = 2
    Dead = 3


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    size: float


class CubeRunner(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.manifest = manifest
        self.w, self.h = ctx.screen_size
        self.U = max(12, int(self.h * UNIT_RATIO))
        self.ground_y = int(self.h * GROUND_Y_RATIO)
        self.player_sx = int(self.w * PLAYER_X_RATIO)

        self.best = 0
        self.attempt = 0
        self.key_held = False
        self.laser_held = False
        self.laser_points = []
        self.scale = self.h / 720.0          # text / line scaling vs. the 720p baseline
        self.lw = max(2, round(2 * self.scale))
        self.particles: List[Particle] = []
        self._cube = self._make_cube()
        self._fonts = {}
        self._reset()

    # -- setup helpers -------------------------------------------------------
    def _make_cube(self) -> pygame.Surface:
        u = self.U
        surf = pygame.Surface((u, u), pygame.SRCALPHA)
        pygame.draw.rect(surf, ACCENT, (0, 0, u, u))
        inner = u // 4
        pygame.draw.rect(surf, ACCENT_DARK, (inner, inner, u - 2 * inner, u - 2 * inner),
                         max(2, u // 10))
        return surf

    def _reset(self):
        self.world = World()
        self.state = State.Start if self.attempt == 0 else State.Playing
        self.hold_ms = 0.0
        self.dead_ms = 0.0
        self.need_release = False
        if self.state == State.Playing:
            self.attempt += 1

    # -- coordinate helpers --------------------------------------------------
    def _sx(self, wx: float) -> float:
        return self.player_sx + (wx - self.world.player.x) * self.U

    def _sy(self, wy: float) -> float:
        return self.ground_y - wy * self.U

    # -- update --------------------------------------------------------------
    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        dt_ms = min(dt_ms, 50.0)  # avoid huge jumps after stalls
        self.laser_points = list(frame.points_by_color.get("red", []))
        self.laser_held = bool(self.laser_points)
        held = self.laser_held or self.key_held

        self._update_particles(dt_ms / 1000.0)

        if self.state == State.Start:
            self.hold_ms = self.hold_ms + dt_ms if held else 0.0
            if self.hold_ms >= HOLD_TO_START_MS:
                self.attempt += 1
                self.state = State.Playing
                # player is still holding: don't jump instantly at start
                self.need_release = True
            return

        if self.state == State.Playing:
            if self.need_release and not held:
                self.need_release = False
            self.world.step(dt_ms / 1000.0, held and not self.need_release)
            if self.world.dead:
                self._on_death()
            return

        if self.state == State.Dead:
            self.dead_ms += dt_ms
            if not held:
                self.need_release = False
            if self.dead_ms >= DEATH_RESTART_DELAY_MS and held and not self.need_release:
                self._reset()
                self.need_release = True

    def _score(self) -> int:
        return int(self.world.distance)

    def _on_death(self):
        self.state = State.Dead
        self.dead_ms = 0.0
        self.need_release = True
        self.best = max(self.best, self._score())
        p = self.world.player
        cx, cy = self._sx(p.x + 0.5), self._sy(p.y + 0.5)
        for _ in range(40):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(80, 420)
            self.particles.append(Particle(cx, cy, math.cos(a) * sp, math.sin(a) * sp,
                                           random.uniform(0.4, 0.9),
                                           random.uniform(3, self.U / 4)))

    def _update_particles(self, dt: float):
        for pt in self.particles:
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.vy += 900 * dt
            pt.life -= dt
        self.particles = [pt for pt in self.particles if pt.life > 0]

    # -- draw ----------------------------------------------------------------
    def on_draw(self, surface: pygame.Surface) -> None:
        # background is the engine's plain dark fill
        self._draw_ground(surface)
        self._draw_obstacles(surface)
        if self.state != State.Dead:
            self._draw_player(surface)
        for pt in self.particles:
            pygame.draw.rect(surface, ACCENT,
                             (int(pt.x), int(pt.y), int(pt.size), int(pt.size)))
        self._draw_laser_marker(surface)
        self._draw_hud(surface)

    def _visible(self, wx: float, w: float) -> bool:
        x = self._sx(wx)
        return x < self.w and x + w * self.U > 0

    def _draw_ground(self, surface):
        gy = self.ground_y
        pygame.draw.rect(surface, SOLID_FILL, (0, gy, self.w, self.h - gy))
        tile = self.U * 2
        offset = (self.world.player.x * self.U) % tile
        for i in range(-1, self.w // tile + 2):
            x = int(i * tile - offset)
            pygame.draw.line(surface, GROUND_SEAM, (x, gy + 3), (x, self.h), 1)
        pygame.draw.line(surface, FG, (0, gy), (self.w, gy), self.lw)
        # pits: cut holes out of the ground
        for p in self.world.pits:
            if not self._visible(p.x, p.w):
                continue
            x0, x1 = int(self._sx(p.x)), int(self._sx(p.x + p.w))
            pygame.draw.rect(surface, BG, (x0, gy - self.lw, x1 - x0, self.h - gy + self.lw))
            pygame.draw.line(surface, FG, (x0, gy), (x0, self.h), self.lw)
            pygame.draw.line(surface, FG, (x1, gy), (x1, self.h), self.lw)

    def _hatch(self, surface, rect: pygame.Rect):
        step = max(8, self.U // 3)
        clip = surface.get_clip()
        surface.set_clip(rect.clip(clip) if clip else rect)
        for k in range(-rect.height, rect.width, step):
            pygame.draw.line(surface, HATCH, (rect.left + k, rect.bottom),
                             (rect.left + k + rect.height, rect.top), 1)
        surface.set_clip(clip)

    def _draw_obstacles(self, surface):
        u = self.U
        lw = self.lw
        for b in self.world.blocks:
            if not self._visible(b.x, b.w):
                continue
            bottom = min(self._sy(b.bottom), self.h + 4)
            top = self._sy(b.top)
            rect = pygame.Rect(int(self._sx(b.x)), int(top), int(b.w * u), int(bottom - top))
            pygame.draw.rect(surface, SOLID_FILL, rect)
            if b.ceiling:
                # hatched so an overhead slab never reads as a platform to land on
                self._hatch(surface, rect)
            pygame.draw.rect(surface, FG, rect, lw)
        for s in self.world.spikes:
            if not self._visible(s.x, 1):
                continue
            x, base = self._sx(s.x), self._sy(s.base)
            tip = base + u if s.down else base - u
            pts = [(x, base), (x + u / 2, tip), (x + u, base)]
            pygame.draw.polygon(surface, SOLID_FILL, pts)
            pygame.draw.polygon(surface, FG, pts, lw)
        for pad in self.world.pads:
            if not self._visible(pad.x, 1):
                continue
            x, base = self._sx(pad.x), self._sy(pad.base)
            ph = int(u * 0.4)
            rect = pygame.Rect(int(x + u * 0.05), int(base - ph), int(u * 0.9), ph)
            pygame.draw.rect(surface, ACCENT, rect, border_top_left_radius=u // 3,
                             border_top_right_radius=u // 3)
            # up-chevrons above the pad: "this launches you"
            cx = x + u / 2
            for k in range(2):
                cy = base - ph - u * (0.35 + 0.35 * k)
                pygame.draw.lines(surface, ACCENT, False,
                                  [(cx - u * 0.3, cy + u * 0.2), (cx, cy - u * 0.05),
                                   (cx + u * 0.3, cy + u * 0.2)], max(2, lw + 1))
        for o in self.world.orbs:
            if not self._visible(o.x, 1):
                continue
            c = (int(self._sx(o.x + 0.5)), int(self._sy(o.y)))
            color = DIM if o.used else ACCENT
            pygame.draw.circle(surface, color, c, int(u * 0.5), max(2, u // 8))
            pygame.draw.circle(surface, color, c, int(u * 0.2))

    def _draw_laser_marker(self, surface):
        # show players the camera sees their dot
        r = max(10, int(self.U * 0.45))
        for p in self.laser_points:
            c = (int(p.x), int(p.y))
            pygame.draw.circle(surface, ACCENT, c, r, max(2, self.lw))

    def _draw_player(self, surface):
        p = self.world.player
        img = pygame.transform.rotate(self._cube, p.angle)
        cx, cy = self._sx(p.x + 0.5), self._sy(p.y + 0.5)
        surface.blit(img, img.get_rect(center=(int(cx), int(cy))))

    def _font(self, size):
        size = max(12, int(size * self.scale))
        font = self._fonts.get(size)
        if font is None:
            font = self._fonts[size] = pygame.font.SysFont(None, size)
        return font

    def _text(self, surface, text, pos, color, size):
        surface.blit(self._font(size).render(text, True, color), pos)

    def _center_text(self, surface, text, y, color, size):
        img = self._font(size).render(text, True, color)
        surface.blit(img, img.get_rect(midtop=(self.w // 2, int(y))))

    def _draw_hud(self, surface):
        k = self.scale
        m = int(24 * k)
        self._text(surface, f"Attempt {max(1, self.attempt)}", (m, int(20 * k)), FG, 36)
        self._text(surface, f"Distance {self._score()}   Best {self.best}",
                   (m, int(56 * k)), FG, 30)

        frac = (self.world.speed - SPEED_START) / (SPEED_MAX - SPEED_START)
        bar_w, bar_h = int(self.w * 0.25), max(8, int(12 * k))
        bx, by = self.w - bar_w - m, int(26 * k)
        pygame.draw.rect(surface, DIM, (bx, by, bar_w, bar_h), 1)
        pygame.draw.rect(surface, DIM, (bx + 1, by + 1, int((bar_w - 2) * frac), bar_h - 2))
        self._text(surface, "speed", (bx, by + bar_h + int(4 * k)), DIM, 24)

        y0 = self.h // 3
        if self.state == State.Start:
            self._center_text(surface, "CUBE RUNNER", y0 - 60 * k, FG, 64)
            self._center_text(surface, "Shine the laser anywhere to jump. Hold to keep jumping.",
                              y0 + 10 * k, FG, 30)
            self._center_text(surface, "Pads launch you. Touch an orb with the laser on to jump again.",
                              y0 + 46 * k, DIM, 28)
            self._center_text(surface, "Never jump into a hatched ceiling!",
                              y0 + 80 * k, DIM, 28)
            self._center_text(surface, "Hold laser (or Space) to start", y0 + 124 * k, FG, 30)
            frac = min(1.0, self.hold_ms / HOLD_TO_START_MS)
            bw, bh = int(240 * k), max(8, int(12 * k))
            bx = self.w // 2 - bw // 2
            by = int(y0 + 162 * k)
            pygame.draw.rect(surface, DIM, (bx, by, bw, bh), 1)
            pygame.draw.rect(surface, ACCENT, (bx + 1, by + 1, int((bw - 2) * frac), bh - 2))
        elif self.state == State.Dead:
            self._center_text(surface, "CRASHED!", y0 - 30 * k, FG, 64)
            if self.dead_ms >= DEATH_RESTART_DELAY_MS:
                if self.need_release:
                    msg = "Let go of the laser, then shine it again to retry"
                else:
                    msg = "Shine the laser (or Space) to retry"
                self._center_text(surface, msg, y0 + 30 * k, FG, 30)

        self._text(surface, "Laser/Space: jump  •  C: calibrate  •  Esc: quit",
                   (int(20 * k), self.h - int(36 * k)), DIM, 24)

    # -- events --------------------------------------------------------------
    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
            self.key_held = True
        elif event.type == pygame.KEYUP and event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
            self.key_held = False

    def on_unload(self) -> None:
        pass


def get_game():
    return CubeRunner()
