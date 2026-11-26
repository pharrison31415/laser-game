import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import List

import pygame

from engine.api import Game, FrameData
from engine.app.context import Context
from engine.render.shapes import draw_hold_target

from .const import *
from .world import World
from .backdrop import Backdrop
from .juice import Juice


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


@dataclass
class Popup:
    x: float        # world coords: the popup scrolls with the level
    y: float
    text: str
    life: float


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
        self.popups: List[Popup] = []
        self.coins_on = "coins" in VARIANTS
        self.hold_on = "hold" in VARIANTS
        self.t = 0.0
        self._cube = self._make_cube()
        self._ship = self._make_ship()
        self.flying_held = False
        self._fonts = {}
        # camera (only the juice variant moves it): zoom multiplies U, cam_y lifts the view
        self.zoom, self.cam_y, self.shake_x, self.shake_y = 1.0, 0.0, 0.0, 0.0
        self.juice = None
        self.backdrop = Backdrop()
        self._reset()
        self.juice = Juice(self) if "juice" in VARIANTS else None

    # -- setup helpers -------------------------------------------------------
    def _make_cube(self) -> pygame.Surface:
        u = self.U
        surf = pygame.Surface((u, u), pygame.SRCALPHA)
        pygame.draw.rect(surf, ACCENT, (0, 0, u, u))
        inner = u // 4
        pygame.draw.rect(surf, ACCENT_DARK, (inner, inner, u - 2 * inner, u - 2 * inner),
                         max(2, u // 10))
        return surf

    def _make_ship(self) -> pygame.Surface:
        """A small dart pointing right (ship mode), same size box as the cube."""
        u = self.U
        surf = pygame.Surface((u, u), pygame.SRCALPHA)
        body = [(u * 0.02, u * 0.18), (u * 0.98, u * 0.5), (u * 0.02, u * 0.82), (u * 0.28, u * 0.5)]
        pygame.draw.polygon(surf, ACCENT, body)
        pygame.draw.polygon(surf, ACCENT_DARK, [(u * 0.34, u * 0.38), (u * 0.7, u * 0.5),
                                                (u * 0.34, u * 0.62)])
        return surf

    def _reset(self):
        self.world = World()
        self.state = State.Start if self.attempt == 0 else State.Playing
        self.hold_ms = 0.0
        self.dead_ms = 0.0
        self.need_release = False
        if self.state == State.Playing:
            self.attempt += 1
        if self.juice:
            self.juice.reset()

    # -- coordinate helpers --------------------------------------------------
    @property
    def ppu(self) -> float:
        """Pixels per world unit (= U unless the camera zooms)."""
        return self.U * self.zoom

    def _sx(self, wx: float) -> float:
        return self.player_sx + (wx - self.world.player.x) * self.ppu + self.shake_x

    def _sy(self, wy: float) -> float:
        return self.ground_y - (wy - self.cam_y) * self.ppu + self.shake_y

    # -- update --------------------------------------------------------------
    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        dt_ms = min(dt_ms, 50.0)  # avoid huge jumps after stalls
        self.laser_points = list(frame.points_by_color.get("red", []))
        self.laser_held = bool(self.laser_points)
        held = self.laser_held or self.key_held

        self._update_particles(dt_ms / 1000.0)
        if self.juice:
            self.juice.update(dt_ms / 1000.0, self.state == State.Playing)
        self.t += dt_ms / 1000.0

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
            if self.juice:
                self.juice.before_step()
            jump = held and not self.need_release
            g_before = self.world.player.gravity
            self.world.step(dt_ms / 1000.0, jump)
            if self.world.player.gravity != g_before:
                self._on_flip()
            self.flying_held = jump and self.world.flying
            if self.flying_held and random.random() < 0.6:
                self._exhaust()
            self._coin_feedback()
            if self.world.boosting:   # hold variant: a trail while the hold is lifting you
                p = self.world.player
                self.particles.append(Particle(self._sx(p.x + random.uniform(0.2, 0.8)),
                                               self._sy(p.y), -self.world.speed * self.ppu, 60,
                                               0.25, self.ppu / 5))
            if self.juice:
                self.juice.after_step(dt_ms / 1000.0)
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
        if self.coins_on:
            return self.world.score
        return int(self.world.distance)

    def _coin_feedback(self):
        for x, y, pts, mult in self.world.coin_events:
            text = f"+{pts}" if mult < 2 else f"+{pts}  x{mult}"
            self.popups.append(Popup(x, y + 0.6, text, 0.8))
            cx, cy = self._sx(x), self._sy(y)
            for _ in range(10):
                a = random.uniform(0, 2 * math.pi)
                sp = random.uniform(60, 220)
                self.particles.append(Particle(cx, cy, math.cos(a) * sp, math.sin(a) * sp - 120,
                                               random.uniform(0.25, 0.5),
                                               random.uniform(2, self.U / 6)))
        self.world.coin_events.clear()

    def _on_death(self):
        self.state = State.Dead
        self.dead_ms = 0.0
        self.need_release = True
        self.best = max(self.best, self._score())
        if self.juice:
            self.juice.on_death()
            return
        p = self.world.player
        cx, cy = self._sx(p.x + 0.5), self._sy(p.y + 0.5)
        for _ in range(40):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(80, 420)
            self.particles.append(Particle(cx, cy, math.cos(a) * sp, math.sin(a) * sp,
                                           random.uniform(0.4, 0.9),
                                           random.uniform(3, self.U / 4)))

    def _on_flip(self):
        """Gravity flipped: a short spray of accent sparks toward the new 'down'."""
        p = self.world.player
        cx, cy = self._sx(p.x + 0.5), self._sy(p.y + 0.5)
        down = -1.0 if p.gravity < 0 else 1.0     # screen y direction of the new gravity
        for _ in range(14):
            self.particles.append(Particle(cx + random.uniform(-0.5, 0.5) * self.U, cy,
                                           random.uniform(-150, 150), down * random.uniform(150, 400),
                                           random.uniform(0.2, 0.4), random.uniform(2, self.U / 6)))

    def _exhaust(self):
        p = self.world.player
        cx, cy = self._sx(p.x + 0.1), self._sy(p.y + 0.5)
        self.particles.append(Particle(cx, cy + random.uniform(-3, 3),
                                       -random.uniform(150, 300), random.uniform(-40, 120),
                                       random.uniform(0.12, 0.25), random.uniform(2, self.U / 6)))

    def _update_particles(self, dt: float):
        for pt in self.particles:
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.vy += 900 * dt
            pt.life -= dt
        self.particles = [pt for pt in self.particles if pt.life > 0]
        for pu in self.popups:
            pu.y += 1.5 * dt
            pu.life -= dt
        self.popups = [pu for pu in self.popups if pu.life > 0]

    # -- draw ----------------------------------------------------------------
    def on_draw(self, surface: pygame.Surface) -> None:
        j = self.juice
        if j:
            j.camera_shake()
        scroll = self.world.player.x + (pygame.time.get_ticks() / 1000.0 * 3
                                        if self.state == State.Start else 0.0)
        self.backdrop.draw(surface, scroll, self._sy(0), self.ppu, self.cam_y,
                           pygame.time.get_ticks() / 1000.0)
        if j:
            j.draw_background(surface)
        self._draw_ground(surface)
        self._draw_obstacles(surface)
        if self.world.gates:
            self._draw_gates(surface)
        if self.state != State.Dead:
            if j:
                j.draw_trail(surface)
                j.draw_player(surface)
            else:
                self._draw_player(surface)
        for pt in self.particles:
            pygame.draw.rect(surface, ACCENT,
                             (int(pt.x), int(pt.y), int(pt.size), int(pt.size)))
        if j:
            j.draw_fx(surface)
            j.draw_overlay(surface)
        self._draw_laser_marker(surface)
        self._draw_hud(surface)

    def _visible(self, wx: float, w: float) -> bool:
        x = self._sx(wx)
        return x < self.w and x + w * self.ppu > 0

    def _draw_ground(self, surface):
        """The ground, drawn only between pits, so the backdrop shows through the holes."""
        gy = int(self._sy(0))
        holes = sorted((int(self._sx(p.x)), int(self._sx(p.x + p.w)))
                       for p in self.world.pits if self._visible(p.x, p.w))
        spans, x = [], 0
        for x0, x1 in holes:
            if x0 > x:
                spans.append((x, x0))
            x = max(x, x1)
        if x < self.w:
            spans.append((x, self.w))
        tile = self.ppu * 2
        offset = (self.world.player.x * self.ppu - self.shake_x) % tile
        clip = surface.get_clip()
        for s0, s1 in spans:
            surface.set_clip(pygame.Rect(s0, 0, s1 - s0, self.h).clip(clip))
            pygame.draw.rect(surface, SOLID_FILL, (s0, gy, s1 - s0, self.h - gy))
            for i in range(-1, int(self.w // tile) + 2):
                xx = int(i * tile - offset)
                if s0 <= xx < s1:
                    pygame.draw.line(surface, GROUND_SEAM, (xx, gy + 3), (xx, self.h), 1)
            pygame.draw.line(surface, FG, (s0, gy), (s1, gy), self.lw)
        surface.set_clip(clip)
        for x0, x1 in holes:                 # the pit walls
            pygame.draw.line(surface, FG, (x0, gy), (x0, self.h), self.lw)
            pygame.draw.line(surface, FG, (x1, gy), (x1, self.h), self.lw)

    def _hatch(self, surface, rect: pygame.Rect):
        step = max(8, int(self.ppu) // 3)
        clip = surface.get_clip()
        surface.set_clip(rect.clip(clip) if clip else rect)
        for k in range(-rect.height, rect.width, step):
            pygame.draw.line(surface, HATCH, (rect.left + k, rect.bottom),
                             (rect.left + k + rect.height, rect.top), 1)
        surface.set_clip(clip)

    def _draw_obstacles(self, surface):
        u = self.ppu
        lw = self.lw
        if "ship" in VARIANTS:
            self._draw_blocks_merged(surface)
        for b in self.world.blocks:
            if "ship" in VARIANTS or not self._visible(b.x, b.w):
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
            pygame.draw.rect(surface, ACCENT, rect, border_top_left_radius=int(u) // 3,
                             border_top_right_radius=int(u) // 3)
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
            pygame.draw.circle(surface, color, c, int(u * 0.5), max(2, int(u) // 8))
            if o.flip:
                # flip orb: an up and a down chevron instead of the solid core
                for d in (-1, 1):
                    self._chevron(surface, color, c[0], c[1] + d * u * 0.17, d, u * 0.5)
            else:
                pygame.draw.circle(surface, color, c, int(u * 0.2))
        for po in self.world.portals:
            if not self._visible(po.x, 1):
                continue
            self._draw_portal(surface, po)

        for c in self.world.coins:
            if c.taken or not self._visible(c.x, 1):
                continue
            self._draw_coin(surface, c)
        for pu in self.popups:
            img = self._font(30).render(pu.text, True, ACCENT)
            img.set_alpha(int(255 * min(1.0, pu.life / 0.3)))
            surface.blit(img, img.get_rect(center=(int(self._sx(pu.x)), int(self._sy(pu.y)))))


    def _chevron(self, surface, color, cx, cy, d, size):
        """A '^' (d=-1, pointing up on screen) or 'v' (d=+1) centred at (cx, cy)."""
        h = size * 0.35
        pygame.draw.lines(surface, color, False,
                          [(cx - size / 2, cy - d * h), (cx, cy + d * h), (cx + size / 2, cy - d * h)],
                          max(2, self.lw + 1))

    def _draw_portal(self, surface, po):
        """Gravity gate: a tall accent frame with chevrons pointing the new way down."""
        u = self.ppu
        x0, x1 = self._sx(po.x + 0.1), self._sx(po.x + 0.9)
        top, bottom = self._sy(po.top), self._sy(po.bottom)
        rect = pygame.Rect(int(x0), int(top), int(x1 - x0), int(bottom - top))
        pygame.draw.rect(surface, ACCENT_DARK, rect)
        pygame.draw.rect(surface, ACCENT, rect, max(2, self.lw), border_radius=int(u) // 3)
        d = -1 if po.gravity < 0 else 1           # screen direction the new gravity pulls
        # chevrons scroll along the gate in the new gravity direction
        phase = (pygame.time.get_ticks() / 400.0) % 1.0
        n = max(1, int(po.top - po.bottom))
        cx = (x0 + x1) / 2
        clip = surface.get_clip()
        surface.set_clip(rect.inflate(-2 * self.lw, -2 * self.lw).clip(clip))
        for k in range(-1, n + 1):
            wy = po.bottom + k + 0.5 - d * phase   # d=-1 (up): chevrons rise
            self._chevron(surface, ACCENT, cx, self._sy(wy), d, u * 0.55)
        surface.set_clip(clip)

    def _draw_blocks_merged(self, surface):
        """Blocks that touch read as one mass (caves, tunnels): outline every block
        lw outside its edge first, then fill them all, so shared seams vanish."""
        rects = []
        for b in self.world.blocks:
            if not self._visible(b.x, b.w):
                continue
            x0, x1 = round(self._sx(b.x)), round(self._sx(b.x + b.w))
            y0, y1 = round(self._sy(b.top)), round(min(self._sy(b.bottom), self.h + 4))
            rects.append((pygame.Rect(x0, y0, x1 - x0, y1 - y0), b.ceiling))
        for r, _ in rects:
            pygame.draw.rect(surface, FG, r.inflate(2 * self.lw, 2 * self.lw))
        for r, _ in rects:
            pygame.draw.rect(surface, SOLID_FILL, r)
        for r, hatched in rects:
            if hatched:
                self._hatch(surface, r)

    def _draw_gates(self, surface):
        u, lw = self.ppu, self.lw
        for g in self.world.gates:
            if not self._visible(g.x - 0.5, 2):
                continue
            ship = g.mode == "ship"
            color = DIM if g.used else (ACCENT if ship else FG)
            x0 = self._sx(g.x + 0.1)
            top, bottom = self._sy(g.top), self._sy(g.bottom)
            rect = pygame.Rect(int(x0), int(top), int(u * 0.8), int(bottom - top))
            pygame.draw.rect(surface, color, rect, max(2, lw + 1), border_radius=int(u * 0.4))
            inner = rect.inflate(-int(u * 0.36), -int(u * 0.36))
            pygame.draw.rect(surface, color, inner, 1, border_radius=int(u * 0.25))
            # glyphs down the gate: chevrons = "fly from here", squares = "run again"
            cx = rect.centerx
            n = max(1, int((g.top - g.bottom) // 1.5))
            for k in range(n):
                cy = top + (k + 0.5) * (bottom - top) / n
                if ship:
                    pygame.draw.lines(surface, color, False,
                                      [(cx - u * 0.15, cy - u * 0.22), (cx + u * 0.15, cy),
                                       (cx - u * 0.15, cy + u * 0.22)], max(2, lw))
                else:
                    s = int(u * 0.3)
                    pygame.draw.rect(surface, color, (int(cx - s / 2), int(cy - s / 2), s, s), max(2, lw))

    def _draw_coin(self, surface, c):
        # a spinning silver diamond: never a circle, so it doesn't read as an orb
        u = self.ppu
        cx, cy = self._sx(c.x + 0.5), self._sy(c.y)
        r = u * 0.36
        spin = abs(math.cos(self.t * 4.0 + c.x * 0.7))
        rx = max(r * 0.18, r * spin)
        pts = [(cx, cy - r), (cx + rx, cy), (cx, cy + r), (cx - rx, cy)]
        if c.missed:
            pygame.draw.polygon(surface, DIM, pts, 1)
            return
        pygame.draw.polygon(surface, FG, pts)
        k = 0.45
        inner = [(cx, cy - r * k), (cx + rx * k, cy), (cx, cy + r * k), (cx - rx * k, cy)]
        pygame.draw.polygon(surface, ACCENT, inner)

    def _draw_laser_marker(self, surface):
        # show players the camera sees their dot
        r = max(10, int(self.U * 0.45))
        for p in self.laser_points:
            c = (int(p.x), int(p.y))
            pygame.draw.circle(surface, ACCENT, c, r, max(2, self.lw))

    def _draw_player(self, surface):
        p = self.world.player
        img = pygame.transform.rotate(self._ship if self.world.flying else self._cube, p.angle)
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
        """Distance and best in the top-left corner (like rooftop-run); start and crash
        screens in the middle."""
        k = self.scale
        m = int(24 * k)
        self._text(surface, f"{self._score():,}", (m, int(18 * k)), FG, 48)
        if self.best:
            self._text(surface, f"best {self.best:,}", (m, int(60 * k)), DIM, 28)
        if self.coins_on and self.state == State.Playing:   # coins variant: the combo
            wd = self.world
            combo = f"   x{wd.multiplier}" if wd.streak >= 2 else ""
            self._text(surface, f"Coins {wd.coin_count}{combo}", (m, int(90 * k)),
                       ACCENT if wd.streak >= 2 else DIM, 28)
        y0 = self.h // 3
        if self.state == State.Start:
            self._center_text(surface, "CUBE RUNNER", y0 - 60 * k, FG, 64)
            if self.hold_on:
                self._center_text(surface, "Flick the laser for a hop, hold it to jump high. Every jump is a new flick.",
                                  y0 + 10 * k, FG, 30)
            else:
                self._center_text(surface, "Shine the laser anywhere to jump. Hold to keep jumping.",
                                  y0 + 10 * k, FG, 30)
            self._center_text(surface, "Pads launch you. Touch an orb with the laser on to jump again.",
                              y0 + 46 * k, DIM, 28)
            tip = "Never jump into a hatched ceiling!"
            if "gravity" in VARIANTS:
                tip += "  Green gates and @-orbs flip gravity."
            if self.coins_on:
                tip += "  Grab diamonds in a row for a combo."
            self._center_text(surface, tip,
                              y0 + 80 * k, DIM, 28)
            if "ship" in VARIANTS:
                self._center_text(surface, "Through a green gate you fly: hold to climb, let go to sink.",
                                  y0 + 108 * k, ACCENT, 26)
                y0 += 22 * k
            self._center_text(surface, "Hold laser (or Space) to start", y0 + 124 * k, FG, 30)
            r = 34 * k
            draw_hold_target(surface, (self.w // 2, y0 + 170 * k + r), r,
                             self.hold_ms / HOLD_TO_START_MS, width=max(2, int(4 * k)))
        elif self.state == State.Dead:
            if self.juice:
                self.juice.draw_death(surface, y0)
            else:
                self._center_text(surface, "CRASHED!", y0 - 30 * k, FG, 64)
            if self.dead_ms >= DEATH_RESTART_DELAY_MS:
                if self.need_release:
                    msg = "Let go of the laser, then shine it again to retry"
                else:
                    msg = "Shine the laser (or Space) to retry"
                self._center_text(surface, msg, y0 + (40 if self.juice else 30) * k, FG, 30)

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
