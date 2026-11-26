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
from .world import World, Bird


class State(Enum):
    Start = 1
    Playing = 2
    Over = 3


@dataclass
class Particle:
    x: float          # world units
    y: float
    vx: float
    vy: float
    life: float
    age: float = 0.0
    size: float = 0.12
    color: tuple = FG
    gravity: float = 6.0


@dataclass
class Popup:
    x: float
    y: float
    text: str
    age: float = 0.0


@dataclass
class ShotMark:
    x: float          # screen px
    y: float
    hit: bool
    age: float = 0.0


# A low-poly bird facing right, in units of BIRD_R (y up). Wings are added per frame.
_TAIL = [(-0.85, 0.12), (-1.55, 0.42), (-1.45, -0.12), (-0.95, -0.12)]
_BODY = [(-1.0, 0.12), (-0.45, 0.46), (0.45, 0.42), (0.8, 0.18), (0.62, -0.28), (-0.25, -0.42), (-1.0, -0.12)]
_BELLY = [(-0.25, -0.42), (0.62, -0.28), (0.8, 0.18), (0.1, -0.05)]
_HEAD = [(0.6, 0.38), (0.78, 0.75), (1.1, 0.78), (1.28, 0.5), (1.12, 0.22), (0.8, 0.16)]
_BEAK = [(1.24, 0.6), (1.62, 0.46), (1.2, 0.36)]
_EYE = (1.0, 0.56)


class FlockShot(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.w, self.h = ctx.screen_size
        self.scale = self.h / 720.0
        self.lw = max(2, round(2 * self.scale))
        self.ppu = self.h / SCREEN_U
        self.width_u = self.w / self.ppu
        self.best = 0
        self.key_held = False
        self.laser_points = []
        self.press_r2 = (PRESS_RADIUS * self.h) ** 2
        self.prev_points = []
        self._fonts = {}
        self._backdrop = self._make_backdrop()
        self._grass = self._make_grass()
        self.time = 0.0
        self.state = State.Start
        self._new_world()

    def _new_world(self):
        self.world = World(self.width_u)
        self.particles: List[Particle] = []
        self.popups: List[Popup] = []
        self.shots: List[ShotMark] = []
        self.hold_ms = 0.0
        self.over_ms = 0.0
        self.flash = 0.0
        self.need_release = False

    # -- coordinates ----------------------------------------------------------------
    def _sx(self, x):
        return x * self.ppu

    def _sy(self, y):
        return self.h - y * self.ppu

    # -- input -------------------------------------------------------------------------
    def _presses(self, points):
        """Dots that just appeared: each one is a shot (moving a held dot doesn't fire)."""
        out = [p for p in points
               if not any((p.x - q.x) ** 2 + (p.y - q.y) ** 2 < self.press_r2 for q in self.prev_points)]
        self.prev_points = list(points)
        return out

    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        dt_ms = min(dt_ms, 50.0)
        dt = dt_ms / 1000.0
        self.time += dt
        self.laser_points = list(frame.points_by_color.get("red", []))
        presses = self._presses(self.laser_points)
        held = bool(self.laser_points) or self.key_held
        self._update_effects(dt)

        if self.state == State.Start:
            self.hold_ms = self.hold_ms + dt_ms if held else 0.0
            if self.hold_ms >= HOLD_TO_START_MS:
                self._new_world()
                self.state = State.Playing
            return

        if self.state == State.Playing:
            for p in presses:
                self._shoot(p.x, p.y)
            self.world.step(dt)
            self._consume_events()
            if self.world.over:
                self.state = State.Over
                self.over_ms = 0.0
                self.need_release = held
                self.best = max(self.best, self.world.score)
            return

        if self.state == State.Over:
            self.over_ms += dt_ms
            if not held:
                self.need_release = False
            if self.over_ms >= GAME_OVER_DELAY_MS and held and not self.need_release:
                self._new_world()
                self.state = State.Playing

    def _shoot(self, px, py):
        if self.world.shells <= 0 or not any(b.alive for b in self.world.birds):
            return
        bird = self.world.shoot(px / self.ppu, (self.h - py) / self.ppu)
        self.shots.append(ShotMark(px, py, bird is not None))
        self.flash = 1.0

    def _consume_events(self):
        for ev in self.world.events:
            kind = ev[0]
            if kind == "hit":
                _, x, y, pts = ev
                self._burst(x, y, 16, BIRD_LIGHT, 3.0, 0.14, gravity=2.5, life=1.1)
                self._burst(x, y, 8, BIRD_MID, 2.0, 0.1, gravity=2.5, life=1.3)
                self.popups.append(Popup(x, y + 0.9, f"+{pts}"))
            elif kind == "decoy":
                _, x, y, pts = ev
                self._burst(x, y, 16, BIRD_DARK, 3.0, 0.14, gravity=2.5, life=1.1)
                self.popups.append(Popup(x, y + 0.9, f"-{pts}"))
            elif kind == "takeoff":
                _, x, y = ev
                self._burst(x, y + 0.1, 10, GRASS_BLADE, 2.5, 0.1, up=2.5, gravity=10.0, life=0.6)
            elif kind == "thud":
                _, x, y = ev
                self._burst(x, y + 0.1, 8, GRASS_BLADE, 1.8, 0.1, up=1.5, gravity=10.0, life=0.5)
            elif kind == "round_clear":
                _, rnd, perfect = ev
                if perfect:
                    self.popups.append(Popup(self.width_u / 2, 6.2, f"PERFECT  +{PERFECT_BONUS}"))
        self.world.events.clear()

    # -- effects ----------------------------------------------------------------------
    def _burst(self, x, y, n, color, speed, size, up=0.0, gravity=6.0, life=1.0):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s + up,
                                           random.uniform(0.6, 1.0) * life,
                                           size=size * random.uniform(0.6, 1.3),
                                           color=color, gravity=gravity))

    def _update_effects(self, dt):
        for p in self.particles:
            p.age += dt
            p.vy -= p.gravity * dt
            p.vx *= 1 - 1.5 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
        self.particles = [p for p in self.particles if p.age < p.life]
        for p in self.popups:
            p.age += dt
            p.y += 0.8 * dt
        self.popups = [p for p in self.popups if p.age < 1.0]
        for s in self.shots:
            s.age += dt
        self.shots = [s for s in self.shots if s.age < 0.35]
        self.flash = max(0.0, self.flash - dt * 8)

    # -- drawing -----------------------------------------------------------------------
    def on_draw(self, surface: pygame.Surface) -> None:
        surface.blit(self._backdrop, (0, 0))
        self._draw_clouds(surface)
        for b in self.world.birds:
            self._draw_bird(surface, b)
        surface.blit(self._grass, (0, 0))
        self._draw_particles(surface)
        self._draw_shots(surface)
        if self.flash > 0:              # a quick brightening on each shot
            v = int(26 * self.flash)
            surface.fill((v, v, v), special_flags=pygame.BLEND_RGB_ADD)
        self._draw_hud(surface)
        self._draw_laser_marker(surface)

    def _make_backdrop(self):
        """Sky gradient, two rows of hills and a tree line: drawn once."""
        w, h, u = self.w, self.h, self.ppu
        s = pygame.Surface((w, h))
        for y in range(h):
            f = y / h
            c = tuple(int(SKY_TOP[i] + (SKY_LOW[i] - SKY_TOP[i]) * f) for i in range(3))
            pygame.draw.line(s, c, (0, y), (w, y))
        rnd = random.Random(3)
        for color, base, amp, wl in ((HILL_FAR, 4.1, 0.9, 9.0), (HILL_NEAR, 3.2, 0.6, 6.0)):
            ph = rnd.uniform(0, 6)
            pts = [(0, h)]
            for i in range(0, w + 8, 8):
                x = i / u
                y = base + amp * (0.6 * math.sin(x / wl * 2 * math.pi + ph)
                                  + 0.4 * math.sin(x / wl * 4.7 + ph * 2))
                pts.append((i, self._sy(y)))
            pts.append((w, h))
            pygame.draw.polygon(s, color, pts)
        # a tree line of low-poly pines and round trees just behind the grass
        x = rnd.uniform(-0.5, 0.5)
        while x < self.width_u + 1:
            if rnd.random() < 0.55:
                hgt = rnd.uniform(1.4, 2.6)
                half = hgt * 0.28
                pygame.draw.polygon(s, TREE, [(self._sx(x - half), self._sy(GROUND_Y)),
                                              (self._sx(x), self._sy(GROUND_Y + hgt)),
                                              (self._sx(x + half), self._sy(GROUND_Y))])
            else:
                r = rnd.uniform(0.5, 0.9)
                cx, cy = self._sx(x), self._sy(GROUND_Y + r * 1.1)
                pts = [(cx + math.cos(a) * r * u, cy + math.sin(a) * r * u)
                       for a in [k * math.pi / 4 + 0.3 for k in range(8)]]
                pygame.draw.polygon(s, TREE, pts)
            x += rnd.uniform(0.5, 1.6) if rnd.random() < 0.7 else rnd.uniform(2.0, 4.5)
        return s

    def _make_grass(self):
        """The grass in front of the birds (they rise out of it), drawn once."""
        w, h, u = self.w, self.h, self.ppu
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        gy = self._sy(GROUND_Y)
        rnd = random.Random(5)
        top = [(0, h)]
        x = 0.0
        while x <= w + 10:                      # a jagged top edge of blades
            top.append((x, gy + rnd.uniform(-0.12, 0.08) * u))
            x += rnd.uniform(0.08, 0.2) * u
            top.append((x, gy - rnd.uniform(0.15, 0.45) * u))
            x += rnd.uniform(0.08, 0.2) * u
        top.append((w + 10, h))
        pygame.draw.polygon(s, GRASS, top)
        pygame.draw.rect(s, GRASS_DARK, (0, int(gy + 0.9 * u), w, h))
        for _ in range(int(w / u * 14)):        # strokes of lighter blades
            bx = rnd.uniform(0, w)
            by = rnd.uniform(gy + 0.1 * u, h)
            ln = rnd.uniform(0.15, 0.35) * u
            lean = rnd.uniform(-0.12, 0.12) * u
            col = GRASS_BLADE if by < gy + 0.9 * u else GRASS
            pygame.draw.line(s, col, (bx, by), (bx + lean, by - ln), 1)
        # a few bushes poking up over the grass line
        x = rnd.uniform(0.5, 2.0)
        while x < self.width_u:
            r = rnd.uniform(0.35, 0.6)
            cx, cy = self._sx(x), self._sy(GROUND_Y + r * 0.35)
            pts = [(cx + math.cos(a) * r * u * 1.4, cy - abs(math.sin(a)) * r * u)
                   for a in [k * math.pi / 6 for k in range(7)]]
            pygame.draw.polygon(s, GRASS, pts)
            pygame.draw.lines(s, GRASS_BLADE, False, pts, 1)
            x += rnd.uniform(3.0, 7.0)
        return s

    def _draw_clouds(self, surface):
        u = self.ppu
        span = self.width_u + 8
        rnd = random.Random(11)
        for i in range(5):
            y = rnd.uniform(6.3, 9.2)
            x = (rnd.uniform(0, span) + self.time * rnd.uniform(0.08, 0.2)) % span - 4
            wdt = rnd.uniform(2.0, 3.6)
            cx, cy = self._sx(x), self._sy(y)
            pts = [(cx - wdt * 0.5 * u, cy), (cx - wdt * 0.3 * u, cy - 0.35 * u),
                   (cx - wdt * 0.05 * u, cy - 0.55 * u), (cx + wdt * 0.25 * u, cy - 0.3 * u),
                   (cx + wdt * 0.5 * u, cy)]
            pygame.draw.polygon(surface, (21, 23, 30), pts)

    def _draw_bird(self, surface, b: Bird):
        u = self.ppu * BIRD_R * self.world.size()
        cx, cy = self._sx(b.x), self._sy(b.y)
        face = 1 if b.vx >= 0 else -1
        if b.state == "falling":
            ang = b.spin
        elif b.state == "hit":
            ang = 0.0
        else:
            ang = math.atan2(b.vy, abs(b.vx) + 1e-6) * 0.45
        ca, sa = math.cos(ang), math.sin(ang)

        def tf(pts):
            out = []
            for lx, ly in pts:
                rx, ry = lx * ca - ly * sa, lx * sa + ly * ca
                out.append((cx + face * rx * u, cy - ry * u))
            return out

        if b.state in ("hit", "falling"):
            up = 0.9                                    # wings thrown up
        else:
            up = math.sin(b.flap)
        far = [(-0.35, 0.3), (0.25, 0.32), (-0.1 + 0.2 * up, 0.35 + 1.05 * up), (-0.75, 0.3 + 0.75 * up)]
        near = [(-0.4, 0.22), (0.3, 0.25), (0.05 + 0.25 * up, 0.2 + 1.2 * up), (-0.85, 0.2 + 0.9 * up)]
        if b.decoy:     # decoys: near-black with a light outline, so they read as "not this one"
            dark, mid, light, edge = (16, 17, 21), (34, 36, 43), (52, 55, 64), BIRD_MID
        else:
            dark, mid, light, edge = BIRD_DARK, BIRD_MID, BIRD_LIGHT, BIRD_DARK
        pygame.draw.polygon(surface, dark, tf(far))
        pygame.draw.polygon(surface, dark, tf(_TAIL))
        pygame.draw.polygon(surface, mid, tf(_BODY))
        pygame.draw.polygon(surface, light, tf(_BELLY))
        pygame.draw.polygon(surface, light, tf(_HEAD))
        pygame.draw.polygon(surface, BIRD_BEAK, tf(_BEAK))
        if b.decoy:
            for part in (_TAIL, _BODY, _HEAD):
                pygame.draw.lines(surface, edge, True, tf(part), 1)
        pygame.draw.polygon(surface, light if up < 0 else mid, tf(near))
        pygame.draw.lines(surface, edge, True, tf(near), 1)
        ex, ey = tf([_EYE])[0]
        if b.state in ("hit", "falling"):              # x-ed out eye
            d = max(2, u * 0.1)
            pygame.draw.line(surface, BG, (ex - d, ey - d), (ex + d, ey + d), max(1, self.lw - 1))
            pygame.draw.line(surface, BG, (ex - d, ey + d), (ex + d, ey - d), max(1, self.lw - 1))
        else:
            pygame.draw.circle(surface, BG, (int(ex), int(ey)), max(2, int(u * 0.09)))

    def _draw_particles(self, surface):
        for p in self.particles:
            f = 1 - p.age / p.life
            r = max(1, int(p.size * self.ppu * (0.5 + 0.5 * f)))
            c = tuple(int(BG[i] + (p.color[i] - BG[i]) * min(1.0, f * 1.5)) for i in range(3))
            x, y = self._sx(p.x), self._sy(p.y)
            pygame.draw.polygon(surface, c, [(x, y - r), (x + r, y), (x, y + r), (x - r, y)])

    def _draw_shots(self, surface):
        for s in self.shots:
            f = s.age / 0.35
            r = int((0.25 + 0.6 * f) * self.ppu)
            c = tuple(int(v * (1 - f)) for v in (FG if s.hit else DIM))
            pygame.draw.circle(surface, c, (int(s.x), int(s.y)), r, max(1, self.lw))

    def _draw_laser_marker(self, surface):
        r = max(10, int(self.ppu * 0.45))
        for p in self.laser_points:
            pygame.draw.circle(surface, ACCENT, (int(p.x), int(p.y)), r, max(2, self.lw))

    # -- HUD --------------------------------------------------------------------
    def _font(self, size):
        size = max(12, int(size * self.scale))
        font = self._fonts.get(size)
        if font is None:
            font = self._fonts[size] = pygame.font.SysFont(None, size)
        return font

    def _text(self, surface, text, pos, color, size, anchor="topleft"):
        img = self._font(size).render(text, True, color)
        surface.blit(img, img.get_rect(**{anchor: pos}))

    def _center_text(self, surface, text, y, color, size):
        self._text(surface, text, (self.w // 2, int(y)), color, size, "midtop")

    def _draw_hud(self, surface):
        k = self.scale
        m = int(24 * k)
        wd = self.world
        if self.state != State.Start:
            self._text(surface, f"{wd.score:,}", (m, int(18 * k)), FG, 48)
        if self.best:
            self._text(surface, f"best {self.best:,}", (m, int(60 * k)), DIM, 28)

        y0 = self.h // 4
        if self.state == State.Start:
            self._center_text(surface, "FLOCK SHOT", y0 - 50 * k, FG, 72)
            self._center_text(surface, "Shine the laser on the birds to shoot them.", y0 + 20 * k, FG, 30)
            self._center_text(surface, f"Three shots per flight. Hit {self.world.needed()} of {BIRDS_PER_ROUND} to clear a round.",
                              y0 + 54 * k, DIM, 28)
            self._center_text(surface, "Hold laser (or Space) to start", y0 + 100 * k, FG, 30)
            r = 34 * k
            draw_hold_target(surface, (self.w // 2, y0 + 146 * k + r), r,
                             self.hold_ms / HOLD_TO_START_MS, width=max(2, int(4 * k)))
            return

        self._draw_tally(surface)
        if self.state == State.Over:
            self._center_text(surface, "Game over", y0 - 20 * k, FG, 64)
            self._center_text(surface, f"{wd.hits} of {BIRDS_PER_ROUND} in round {wd.round}, "
                                       f"needed {wd.needed()}", y0 + 34 * k, DIM, 32)
            if self.over_ms >= GAME_OVER_DELAY_MS:
                self._center_text(surface, "Retry?", y0 + 80 * k, DIM, 30)
        elif wd.intro > 0 and not wd.birds:
            self._center_text(surface, f"Round {wd.round}", y0 - 10 * k, FG, 64)
            self._center_text(surface, f"hit {wd.needed()} of {BIRDS_PER_ROUND}",
                              y0 + 44 * k, DIM, 30)
        for p in self.popups:
            f = 1 - p.age
            c = tuple(int(BG[i] + (FG[i] - BG[i]) * min(1.0, f * 2)) for i in range(3))
            self._text(surface, p.text, (int(self._sx(p.x)), int(self._sy(p.y))), c, 34, "center")

    def _draw_tally(self, surface):
        """Along the bottom: round, one mark per bird of the round, shells left."""
        k = self.scale
        wd = self.world
        y = self.h - int(44 * k)
        m = int(28 * k)
        self._text(surface, f"ROUND {wd.round}", (m, y), DIM, 30, "midleft")
        # birds: filled = hit, crossed = got away, outline = still to come
        n = BIRDS_PER_ROUND
        step = int(30 * k)
        r = int(9 * k)
        x0 = self.w // 2 - step * (n - 1) // 2
        need = wd.needed()
        for i in range(n):
            x = x0 + i * step
            res = wd.round_hits[i] if i < len(wd.round_hits) else "todo"
            if res is True and sum(1 for h in wd.round_hits[:i + 1] if h) <= wd.penalty:
                res = False                     # taken back by a decoy hit
            pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
            if res is True:
                pygame.draw.polygon(surface, FG, pts)
            elif res is False:
                pygame.draw.polygon(surface, FAINT, pts, max(1, self.lw - 1))
                d = int(r * 0.6)
                pygame.draw.line(surface, DIM, (x - d, y - d), (x + d, y + d), max(1, self.lw - 1))
                pygame.draw.line(surface, DIM, (x - d, y + d), (x + d, y - d), max(1, self.lw - 1))
            elif res is None:                   # in the air now
                blink = 0.5 + 0.5 * math.sin(self.time * 10)
                c = tuple(int(FAINT[j] + (FG[j] - FAINT[j]) * blink) for j in range(3))
                pygame.draw.polygon(surface, c, pts, max(1, self.lw))
            else:
                pygame.draw.polygon(surface, FAINT, pts, max(1, self.lw - 1))
        # the line to beat: a tick after the needed number of birds
        tx = x0 + int((need - 0.5) * step)
        pygame.draw.line(surface, DIM, (tx, y - r - int(6 * k)), (tx, y + r + int(6 * k)), max(1, self.lw - 1))
        # shells
        sw, sh, gap = int(12 * k), int(30 * k), int(10 * k)
        n_sh = SHOTS_PER_VOLLEY
        for i in range(n_sh):
            x = self.w - m - (n_sh - i) * (sw + gap) + gap
            rect = pygame.Rect(x, y - sh // 2, sw, sh)
            if i < wd.shells and any(b.alive for b in wd.birds):
                pygame.draw.rect(surface, FG, rect, border_radius=int(4 * k))
            else:
                pygame.draw.rect(surface, FAINT, rect, max(1, self.lw - 1), border_radius=int(4 * k))

    def on_event(self, event: pygame.event.Event) -> None:
        keys = (pygame.K_SPACE, pygame.K_RETURN)
        if event.type == pygame.KEYDOWN and event.key in keys:
            self.key_held = True
        elif event.type == pygame.KEYUP and event.key in keys:
            self.key_held = False

    def on_unload(self) -> None:
        pass


def get_game():
    return FlockShot()
