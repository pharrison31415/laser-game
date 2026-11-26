"""
`juice` experiment (CUBE_VARIANT=juice): presentation only, no rule changes.

A moving camera (eases up to follow high jumps, zooms out a little with speed,
shakes on impacts), a two-layer parallax skyline that pulses on every launch, a
fading trail, landing dust, squash and stretch, a shattering death, distance
milestones, a "new best" moment and death text that names what killed you.

The game (main.py) owns the camera numbers (zoom, cam_y, shake_x/y) that its
_sx/_sy read; everything else lives here. Effects are in world units so they
stay put on screen while the camera moves.
"""
import math
import random
from dataclasses import dataclass
from typing import List

import pygame

from .const import *

ZOOM_AT_MAX_SPEED = 0.84        # zoom out a little at top speed: see further ahead
CAM_MAX_Y_SCREEN = 6.5          # keep the cube no more than this many U above the ground line
TRAIL_LEN = 10
MILESTONE_EVERY = 100
SKY_FAR = (18, 20, 26)
SKY_NEAR = (24, 27, 34)
SKY_EDGE = (36, 40, 50)
SKY_PULSE = (14, 18, 18)        # added to the skyline on a beat (a touch of green-gray)

DEATH_TEXT = {
    "spike": "SPIKED",
    "wall": "HIT A WALL",
    "ceiling": "HIT A CEILING",
    "pit": "FELL INTO A PIT",
}


@dataclass
class Bit:
    """A particle or a shard, in world units (y up)."""
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: tuple
    gravity: float = 40.0
    angle: float = 0.0
    spin: float = 0.0
    shard: bool = False


@dataclass
class Popup:
    text: str
    sub: str
    t: float = 0.0
    dur: float = 1.1


def _lerp(c0, c1, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))


def _add(c, d, k):
    return tuple(min(255, int(a + b * k)) for a, b in zip(c, d))


class Juice:
    def __init__(self, game):
        self.g = game
        self.time = 0.0
        self.reset()

    # -- lifecycle ---------------------------------------------------------------
    def reset(self):
        g = self.g
        self.bits: List[Bit] = []
        self.trail = []              # (x, y, angle) world positions, newest last
        self.rings = []              # (x, y, age) expanding launch / death rings
        self.popups: List[Popup] = []
        self.shake = 0.0
        self.pulse = 0.0
        self.flash = 0.0
        self.squash = 0.0            # >0 squashed flat (landing), <0 stretched tall (launch)
        self.milestone = MILESTONE_EVERY
        self.passed_best = False
        self.best_at_start = g.best
        self.new_best = False
        self._prev = None
        g.zoom = self._target_zoom()
        g.cam_y = 0.0

    def _target_zoom(self):
        w = self.g.world
        f = (w.speed - SPEED_START) / (SPEED_MAX - SPEED_START)
        return 1.0 + (ZOOM_AT_MAX_SPEED - 1.0) * max(0.0, min(1.0, f))

    # -- update ------------------------------------------------------------------
    def before_step(self):
        p = self.g.world.player
        self._prev = (p.grounded, p.vy, p.y, sum(o.used for o in self.g.world.orbs))

    def after_step(self, dt):
        """Turn what just happened in the world into effects (called while playing)."""
        g, w = self.g, self.g.world
        p = w.player
        if self._prev is None:
            return
        was_grounded, prev_vy, prev_y, used = self._prev
        if not was_grounded and p.grounded and not w.dead:
            impact = min(1.0, -prev_vy / 25.0)
            self.squash = max(self.squash, 0.18 + 0.25 * impact)
            n = 4 + int(8 * impact)
            for _ in range(n):
                side = random.choice((-1, 1))
                self.bits.append(Bit(p.x + 0.5 + side * 0.4, p.y + 0.05,
                                     side * random.uniform(1.0, 4.0) + w.speed * 0.15,
                                     random.uniform(0.5, 3.0), *([random.uniform(0.25, 0.45)] * 2),
                                     random.uniform(0.10, 0.2), DIM, gravity=18.0))
            if impact > 0.6:
                self.shake = max(self.shake, 0.12)
        if p.vy > prev_vy + 5:      # launched: jump, pad or orb
            self.squash = -0.22
            self.pulse = 1.0
            strong = p.vy > JUMP_VELOCITY + 3          # pad
            orb = sum(o.used for o in w.orbs) > used
            if strong or orb:
                self.rings.append([p.x + 0.5, p.y + (0.0 if strong else 0.5), 0.0])
                self.shake = max(self.shake, 0.1)
        # trail
        self.trail.append((p.x, p.y, p.angle))
        del self.trail[:-TRAIL_LEN]
        # progress
        d = int(w.distance)
        if self.best_at_start > 0 and not self.passed_best and d > self.best_at_start:
            self.passed_best = True
            self.popups.append(Popup("NEW BEST", "", dur=1.6))
            self.flash = max(self.flash, 0.5)

    def on_death(self):
        g, w = self.g, self.g.world
        p = w.player
        self.new_best = int(w.distance) > self.best_at_start
        self.shake = 0.7
        self.flash = 1.0
        self.rings.append([p.x + 0.5, p.y + 0.5, 0.0])
        cx, cy = p.x + 0.5, p.y + 0.5
        # the cube breaks into its own pieces: a 3x3 of chunks flung outward, plus sparks
        for i in range(3):
            for j in range(3):
                ox, oy = (i - 1) / 3, (j - 1) / 3
                a = math.atan2(oy, ox) if (i, j) != (1, 1) else random.uniform(0, 6.28)
                s = random.uniform(5, 11)
                self.bits.append(Bit(cx + ox, cy + oy, math.cos(a) * s - w.speed * 0.25,
                                     math.sin(a) * s + 6, 1.4, 1.4, 1 / 3 + 0.04,
                                     ACCENT if (i + j) % 2 else ACCENT_DARK, gravity=40.0,
                                     angle=p.angle, spin=random.uniform(-720, 720), shard=True))
        for _ in range(26):
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(4, 16)
            life = random.uniform(0.3, 0.8)
            self.bits.append(Bit(cx, cy, math.cos(a) * s, math.sin(a) * s + 3, life, life,
                                 random.uniform(0.08, 0.18), ACCENT, gravity=30.0))

    def update(self, dt, playing):
        g = self.g
        self.time += dt
        for b in self.bits:
            b.x += b.vx * dt
            b.vy -= b.gravity * dt
            b.y += b.vy * dt
            if b.shard and b.vy < 0:
                floor = self._floor_under(b.x, b.y - b.vy * dt) + 0.17
                if b.y < floor:
                    b.y, b.vy, b.vx, b.spin = floor, -b.vy * 0.35, b.vx * 0.6, b.spin * 0.5
            b.angle += b.spin * dt
            b.life -= dt
        self.bits = [b for b in self.bits if b.life > 0]
        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < 0.45]
        for pu in self.popups:
            pu.t += dt
        self.popups = [pu for pu in self.popups if pu.t < pu.dur]
        self.shake = max(0.0, self.shake - dt * 1.8)
        self.pulse = max(0.0, self.pulse - dt * 3.5)
        self.flash = max(0.0, self.flash - dt * 4.0)
        self.squash *= math.exp(-dt * 14)
        if not playing:
            if g.state.name == "Start":
                self.trail.clear()
            return
        # camera: zoom with speed; rise to keep high jumps on screen, settle back down
        g.zoom += (self._target_zoom() - g.zoom) * min(1.0, dt * 1.5)
        p = g.world.player
        target = max(0.0, p.y - CAM_MAX_Y_SCREEN * 0.7)
        g.cam_y += (target - g.cam_y) * min(1.0, dt * (4.0 if target > g.cam_y else 2.0))
        g.cam_y = max(g.cam_y, p.y - CAM_MAX_Y_SCREEN, 0.0)

    def _floor_under(self, x, y):
        """Highest surface at world x that is below height y (for bouncing shards)."""
        w = self.g.world
        floor = -99.0 if w._over_pit(x - 0.1, x + 0.1) else 0.0
        for bl in w.blocks:
            if bl.x <= x <= bl.x + bl.w and floor < bl.top <= y + 0.2:
                floor = bl.top
        return floor

    def camera_shake(self):
        g = self.g
        amp = self.shake * g.U * 0.5
        if amp > 0.5:
            g.shake_x = random.uniform(-amp, amp)
            g.shake_y = random.uniform(-amp, amp)
        else:
            g.shake_x = g.shake_y = 0.0

    # -- drawing -------------------------------------------------------------------
    def draw_background(self, surface):
        g = self.g
        """Flash / beat pulse, added on top of the game's Backdrop."""
        if self.flash > 0:
            k = self.flash * 0.6
            surface.fill((int(48 * k), int(50 * k), int(54 * k)), special_flags=pygame.BLEND_RGB_ADD)
        elif self.pulse > 0.02:     # a faint green-gray wash on each beat
            surface.fill(tuple(int(c * self.pulse * 0.5) for c in SKY_PULSE),
                         special_flags=pygame.BLEND_RGB_ADD)

    def _cube_poly(self, cx, cy, half, angle, sx=1.0, sy=1.0, foot_y=None):
        a = math.radians(-angle)
        ca, sa = math.cos(a), math.sin(a)
        pts = []
        for ux, uy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            x, y = ux * half, uy * half
            x, y = x * ca - y * sa, x * sa + y * ca
            if foot_y is None:
                pts.append((cx + x * sx, cy + y * sy))
            else:   # scale about the cube's feet so a squash stays on the ground
                pts.append((cx + x * sx, foot_y + (cy + y - foot_y) * sy))
        return pts

    def draw_trail(self, surface):
        g = self.g
        n = len(self.trail)
        if n < 2:
            return
        ppu = g.ppu
        for k, (x, y, ang) in enumerate(self.trail[:-1]):
            f = (k + 1) / n
            half = ppu * 0.5 * (0.35 + 0.5 * f)
            pts = self._cube_poly(g._sx(x + 0.5), g._sy(y + 0.5), half, ang)
            pygame.draw.polygon(surface, _lerp(BG, ACCENT_DARK, 0.3 + 0.7 * f), pts)

    def draw_player(self, surface):
        g = self.g
        p = g.world.player
        s = self.squash
        if g.state.name == "Start":      # idle: breathe while waiting for the first press
            s = 0.06 * math.sin(self.time * 5)
        sx, sy = 1 + s * 0.8, 1 - s
        ppu = g.ppu
        cx, cy = g._sx(p.x + 0.5), g._sy(p.y + 0.5)
        foot = g._sy(p.y)
        pygame.draw.polygon(surface, ACCENT, self._cube_poly(cx, cy, ppu / 2, p.angle, sx, sy, foot))
        inner = ppu / 2 - ppu // 4
        pygame.draw.polygon(surface, ACCENT_DARK,
                            self._cube_poly(cx, cy, inner, p.angle, sx, sy, foot),
                            max(2, int(ppu) // 10))

    def draw_fx(self, surface):
        g = self.g
        ppu = g.ppu
        for b in self.bits:
            k = b.life / b.max_life
            if b.shard:
                half = b.size * ppu / 2 * (0.6 + 0.4 * k)
                pts = self._cube_poly(g._sx(b.x), g._sy(b.y), half, b.angle)
                pygame.draw.polygon(surface, _lerp(BG, b.color, min(1.0, k * 2)), pts)
            else:
                sz = max(2, int(b.size * ppu * (0.4 + 0.6 * k)))
                pygame.draw.rect(surface, _lerp(BG, b.color, k),
                                 (int(g._sx(b.x)) - sz // 2, int(g._sy(b.y)) - sz // 2, sz, sz))
        for x, y, age in self.rings:
            k = age / 0.45
            r = int(ppu * (0.6 + 2.6 * k))
            pygame.draw.circle(surface, _lerp(ACCENT, BG, k), (int(g._sx(x)), int(g._sy(y))),
                               r, max(1, int(g.lw * 2 * (1 - k))))

    def draw_overlay(self, surface):
        g = self.g
        k = g.scale
        for pu in self.popups:
            f = pu.t / pu.dur
            grow = 1 + 0.25 * (1 - min(1.0, pu.t / 0.12))    # pops in slightly big
            fade = 1.0 if f < 0.6 else 1 - (f - 0.6) / 0.4
            color = _lerp(BG, ACCENT if pu.text == "NEW BEST" else FG, fade)
            img = g._font(int(84 * grow)).render(pu.text, True, color)
            y = g.h * 0.16 - 20 * k * f
            surface.blit(img, img.get_rect(center=(g.w // 2, int(y))))


    def draw_death(self, surface, y0):
        g = self.g
        k = g.scale
        t = g.dead_ms / 1000.0
        grow = 1 + 0.35 * max(0.0, 1 - t / 0.15)
        cause = DEATH_TEXT.get(g.world.death_cause, "CRASHED!")
        img = g._font(int(72 * grow)).render(cause, True, FG)
        surface.blit(img, img.get_rect(midtop=(g.w // 2, int(y0 - 70 * k))))
        if self.new_best and self.best_at_start > 0:
            g._center_text(surface, "NEW BEST!", y0 - 8 * k, ACCENT, 44)
