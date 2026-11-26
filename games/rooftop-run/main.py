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
from .world import World, RUNNER_W, RUNNER_H
from . import sprites
from . import scenery


class State(Enum):
    Start = 1
    Playing = 2
    Dead = 3


@dataclass
class Particle:
    x: float          # world units
    y: float
    vx: float
    vy: float
    life: float
    color: tuple
    size: float       # world units
    gravity: float = 30.0


DEATH_TEXT = {
    "fell": "then fell to the street.",
    "wall": "then ran into a wall.",
    "crumble": "then knocked down a building.",
    "debris": "then got turned into a fine mist.",
    "debris_wall": "before you were turned into a fine mist.",
}


class RooftopRun(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.w, self.h = ctx.screen_size
        self.scale = self.h / 720.0
        self.lw = max(2, round(2 * self.scale))
        self.base_ppu = self.h * BASE_UNIT_RATIO
        self.runner_sx = self.w * RUNNER_X_RATIO
        self.roof_sy = self.h * ROOF_Y_RATIO
        self.best = 0
        self.attempt = 0
        self.key_held = False
        self.laser_points = []
        self.particles: List[Particle] = []
        self._fonts = {}
        self._shake_x = self._shake_y = 0.0
        self.thud = 0.0
        self._facades = scenery.Facades()
        self._clutter = {}
        self._sky = [scenery.Skyline(0, SKY_FAR, SKY_FAR_WIN, 9.0, (6, 20)),
                     scenery.Skyline(1, SKY_NEAR, SKY_NEAR_WIN, 7.0, (3, 14))]
        self._reset()

    def _reset(self):
        self.world = World()
        self.state = State.Start if self.attempt == 0 else State.Playing
        self.hold_ms = 0.0
        self.dead_ms = 0.0
        self.need_release = False
        self.shake = 0.0
        self.particles = []
        self.stride = 0.0              # run-cycle frame counter (see _runner_pose)
        self._snap_camera()
        if self.state == State.Playing:
            self.attempt += 1

    # -- camera ----------------------------------------------------------------
    def _target_zoom(self) -> float:
        f = (self.world.speed - SPEED_START) / (SPEED_MAX - SPEED_START)
        return ZOOM_START + (ZOOM_MAX_SPEED - ZOOM_START) * max(0.0, min(1.0, f))

    def _target_cam_y(self) -> float:
        w = self.world
        if w.support is not None:
            y = w.support.top
            # near the edge, lower the view so the roof you'll land on is on screen
            nxt = next((b for b in w.buildings if b.x > w.runner.x), None)
            if nxt is not None and nxt.x - w.runner.x < max(8.0, w.speed * 1.4):
                y = min(y, nxt.top + 4.0)
            return y
        if w.dead and w.death == "fell":
            return self.cam_y
        # in the air: look at the next roof ahead so you can see where you'll land
        ahead = [b for b in w.buildings if b.right > w.runner.x + 1]
        return ahead[0].top if ahead else self.cam_y

    def _snap_camera(self):
        self.zoom = self._target_zoom()
        self.cam_y = self.world.runner.y

    def _update_camera(self, dt: float):
        self.zoom += (self._target_zoom() - self.zoom) * min(1.0, dt * 1.5)
        target = self._target_cam_y()
        # never let the runner leave the top/bottom of the screen
        self.cam_y += (target - self.cam_y) * min(1.0, dt * 3.0)
        ry = self.world.runner.y
        span_up = self.roof_sy / self.ppu - RUNNER_H - 1
        span_down = (self.h - self.roof_sy) / self.ppu - 1
        if not (self.world.dead and self.world.death == "fell"):
            self.cam_y = max(ry - span_up, min(ry + span_down, self.cam_y))
        self.shake = max(0.0, self.shake - dt * 1.6)
        self.thud = max(0.0, self.thud - dt * 5.0)

    @property
    def ppu(self) -> float:
        return self.base_ppu * self.zoom

    def _sx(self, wx: float) -> float:
        return self.runner_sx + (wx - self.world.runner.x) * self.ppu + self._shake_x

    def _sy(self, wy: float) -> float:
        return self.roof_sy - (wy - self.cam_y) * self.ppu + self._shake_y

    # -- update ------------------------------------------------------------------
    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        dt_ms = min(dt_ms, 50.0)
        dt = dt_ms / 1000.0
        self.laser_points = list(frame.points_by_color.get("red", []))
        held = bool(self.laser_points) or self.key_held
        self._update_particles(dt)

        if self.state == State.Start:
            self.hold_ms = self.hold_ms + dt_ms if held else 0.0
            if self.hold_ms >= HOLD_TO_START_MS:
                self.attempt += 1
                self.state = State.Playing
                self.need_release = True     # don't jump with the press that started the run
            self._update_camera(dt)
            return

        if self.state == State.Playing:
            if self.need_release and not held:
                self.need_release = False
            self.world.step(dt, held and not self.need_release)
            # flip-book cadence: faster with speed, but capped so the stills stay readable
            self.stride += dt * min(RUN_FPS_MAX, RUN_FPS_BASE + RUN_FPS_PER_SPEED * self.world.speed)
            self._consume_events()
            if self.world.dead:
                self.state = State.Dead
                self.dead_ms = 0.0
                self.need_release = True
                self.best = max(self.best, int(self.world.distance))
            self._update_camera(dt)
            return

        if self.state == State.Dead:
            self.dead_ms += dt_ms
            self._update_camera(dt)
            if not held:
                self.need_release = False
            if self.dead_ms >= DEATH_RESTART_DELAY_MS and held and not self.need_release:
                self._reset()
                self.need_release = True

    def _burst(self, x, y, n, color, speed, size, up=0.0, gravity=30.0, carry=0.3, life=1.0):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, math.cos(a) * s + self.world.speed * carry,
                                           math.sin(a) * s + up, random.uniform(0.4, 1.0) * life,
                                           color, random.uniform(0.5, 1.0) * size, gravity))

    def _consume_events(self):
        for kind, x, y, *extra in self.world.events:
            if kind == "glass":
                self._burst(x, y + 2.5, 26, GLASS, 8, 0.25, up=2)
                self.shake = max(self.shake, 0.25)
            elif kind == "glass_exit":
                # shards spray out ahead of the runner and rain down outside
                self._burst(x, y + 2.5, 34, GLASS, 7, 0.25, up=3, carry=0.85)
                self.shake = max(self.shake, 0.3)
            elif kind == "crate":
                self._burst(x + CRATE_SIZE / 2, y + CRATE_SIZE / 2, 14, DIM, 7, 0.3, up=4)
                self.shake = max(self.shake, 0.2)
            elif kind == "hard_landing":
                self._burst(x + RUNNER_W / 2, y, 10, DIM, 4, 0.2, up=2)
                self.shake = max(self.shake, 0.35)
            elif kind == "land":
                self._burst(x + RUNNER_W / 2, y, 3, DIM, 2, 0.15, up=1)
            elif kind == "debris_land":
                self._burst(x + DEBRIS_SIZE / 2, y, 28, DIM, 9, 0.3, up=3)
                self.shake = max(self.shake, 0.7)
                self.thud = 1.0         # a downward jolt on top of the shake
            elif kind == "collapse":
                self._collapse(x, y, extra[0])
            elif kind == "crumble":
                self.shake = max(self.shake, 0.2)
            elif kind == "death":
                if self.world.death in ("debris", "debris_wall"):
                    # a fine green mist: lots of tiny, slow, drifting specks
                    for _ in range(4):
                        self._burst(x + RUNNER_W / 2, y + RUNNER_H / 2, 60, ACCENT, 5, 0.07,
                                    up=1, gravity=-0.5, carry=0.15, life=2.2)
                    self.shake = max(self.shake, 0.6)
                else:
                    self._burst(x + RUNNER_W / 2, y + RUNNER_H / 2, 30, ACCENT, 9, 0.25, up=3)
                self.shake = max(self.shake, 0.5)
        self.world.events.clear()

    def _collapse(self, x0: float, top: float, x1: float):
        """A knocked-down building: the whole visible block bursts into rubble."""
        bottom = top - (self.h - self.roof_sy) / self.ppu - 4
        n = int(min(260, (x1 - x0) * (top - bottom) * 0.25))
        for _ in range(n):
            px, py = random.uniform(x0, x1), random.uniform(bottom, top)
            near_top = (py - bottom) / max(1.0, top - bottom)
            self.particles.append(Particle(
                px, py, random.uniform(-3, 6) + self.world.speed * 0.2, random.uniform(0, 8) * near_top,
                random.uniform(0.8, 1.8), random.choice((BUILDING_FILL, FACADE_LINE, DIM)),
                random.uniform(0.2, 0.6), gravity=35.0))
        self.shake = max(self.shake, 0.9)

    def _update_particles(self, dt: float):
        for pt in self.particles:
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.vy -= pt.gravity * dt
            pt.life -= dt
        self.particles = [pt for pt in self.particles if pt.life > 0]

    # -- draw -------------------------------------------------------------------
    def on_draw(self, surface: pygame.Surface) -> None:
        amp = self.shake * self.ppu * 0.4
        self._shake_x = random.uniform(-amp, amp) if amp > 0.5 else 0.0
        self._shake_y = random.uniform(-amp, amp) if amp > 0.5 else 0.0
        if self.thud > 0:               # debris impact: the whole view dips, then springs back
            self._shake_y += self.thud * self.thud * self.ppu * 0.5
        self._facades.new_frame()
        for sky in self._sky:
            sky.new_frame()
        self._draw_skyline(surface, self._sky[0], 0.15, 0.35)
        self._draw_skyline(surface, self._sky[1], 0.4, 0.6)
        self._draw_buildings(surface)
        self._draw_props(surface)
        if self.state != State.Dead:
            self._draw_runner(surface)
        for pt in self.particles:
            s = max(2, int(pt.size * self.ppu))
            pygame.draw.rect(surface, pt.color, (int(self._sx(pt.x)), int(self._sy(pt.y)), s, s))
        self._draw_laser_marker(surface)
        self._draw_hud(surface)

    def _draw_skyline(self, surface, sky, factor, vfactor):
        """Distant city silhouettes, scrolling slower than the rooftops (parallax)."""
        ppu = self.base_ppu * (0.5 + 0.5 * self.zoom)
        base_y = self.h - (self.cam_y * vfactor * 0.3) * ppu * 0.2
        scenery.draw_skyline(surface, sky, factor, ppu, self.world.runner.x * factor, base_y,
                             self.runner_sx, self.h, self.w, vfactor, self.world.time)

    def _visible(self, x: float, w: float) -> bool:
        sx = self._sx(x)
        return sx < self.w and sx + w * self.ppu > 0

    def _draw_buildings(self, surface):
        lw = self.lw
        ppu = self.ppu
        bottom = self.h + 10
        t = self.world.time
        shown = []
        for b in self.world.buildings:
            if b.collapsed or not self._visible(b.x, b.w):
                continue
            jitter = 0.0
            if b.kind == "crumble" and b.touched_t is not None and b.touched_t > CRUMBLE_DELAY_S * 0.5:
                jitter = random.uniform(-0.08, 0.08) * ppu
            shown.append((b, jitter))

        # roof clutter first, so every roof line and wall is drawn over it
        for b, jitter in shown:
            if b.kind == "girder":
                continue
            key = (scenery.style_seed(b), b.w)
            items = self._clutter.get(key)
            if items is None:
                if len(self._clutter) > 256:
                    self._clutter.clear()
                items = self._clutter[key] = scenery.clutter_items(b)
            bx = self._sx(b.x) + jitter
            ry = self._sy(b.slab_top if b.kind == "window" else b.top)
            scenery.draw_clutter(surface, items, lambda d: bx + d * ppu, lambda d: ry - d * ppu, ppu, t)

        for b, jitter in shown:
            x0 = int(self._sx(b.x) + jitter)
            x1 = int(self._sx(b.right) + jitter)
            top = int(self._sy(b.top))
            if b.kind == "girder":
                th = max(4, int(GIRDER_THICKNESS * ppu))
                pygame.draw.rect(surface, BUILDING_FILL, (x0, top, x1 - x0, th))
                fl = max(1, th // 6)        # flanges
                pygame.draw.rect(surface, BUILDING_LIGHT, (x0, top, x1 - x0, fl))
                pygame.draw.rect(surface, BUILDING_SHADE, (x0, top + th - fl, x1 - x0, fl))
                step = max(8, int(ppu * 0.8))
                rr = max(1, int(ppu * 0.05))
                for k, xx in enumerate(range(x0, x1 - step, step)):  # truss zig-zag with rivets
                    a, c = (top + th - fl, top + fl) if k % 2 == 0 else (top + fl, top + th - fl)
                    pygame.draw.line(surface, BUILDING_LIGHT, (xx, a), (xx + step, c), max(1, lw - 1))
                    if k % 2 == 0:
                        pygame.draw.line(surface, BUILDING_SHADE, (xx, top + fl), (xx, top + th - fl), 1)
                    if rr > 1:
                        pygame.draw.circle(surface, BUILDING_LIGHT, (xx, top + fl + rr), rr)
                pygame.draw.rect(surface, FG, (x0, top, x1 - x0, th), lw)
                continue

            st = self._facades.style(b)
            pygame.draw.rect(surface, st.base, (x0, top, x1 - x0, bottom - top))
            if b.kind == "window":
                self._facades.draw(surface, b, st, ppu, x0, x1, top, bottom, cornice=False)
            else:
                self._facades.draw(surface, b, st, ppu, x0, x1, top, bottom)
            sw = max(2, int(0.35 * ppu))     # the shaded side, light from the left
            pygame.draw.rect(surface, BUILDING_SHADE, (x1 - sw, top, sw, bottom - top))
            pygame.draw.line(surface, BUILDING_LIGHT, (x0 + lw, top), (x0 + lw, bottom), 1)
            if b.kind == "crumble":
                rnd = random.Random(b.seed)
                for _ in range(3):  # cracks
                    cx = rnd.uniform(0.2, 0.8)
                    pts, yy = [], top
                    xx = x0 + (x1 - x0) * cx
                    while yy < min(bottom, top + ppu * 6):
                        pts.append((xx, yy))
                        xx += rnd.uniform(-0.6, 0.6) * ppu
                        yy += rnd.uniform(0.5, 1.2) * ppu
                    if len(pts) > 1:
                        pygame.draw.lines(surface, FG, False, pts, max(1, lw - 1))
            pygame.draw.line(surface, FG, (x0, top), (x1, top), lw)
            pygame.draw.line(surface, FG, (x0, top), (x0, bottom), lw)
            pygame.draw.line(surface, FG, (x1, top), (x1, bottom), lw)

            if b.kind == "window":
                self._draw_window_block(surface, b, st, x0, x1, top)

    def _draw_window_block(self, surface, b, st, x0, x1, top):
        """The open storey you run through, and the block of floors above it."""
        lw, ppu = self.lw, self.ppu
        ceil, slab = int(self._sy(b.ceil)), int(self._sy(b.slab_top))
        pygame.draw.rect(surface, INTERIOR, (x0, ceil, x1 - x0, top - ceil))
        cw = max(3, int(0.5 * ppu))
        cx = b.x + 5.0
        while cx < b.right - 2:
            px = int(self._sx(cx))
            # back-wall windows between the columns, then the column with a capital
            for f in (-3.5, -1.8, 1.8 - 0.5):
                wx = int(self._sx(cx + f))
                if x0 < wx < x1 - int(1.2 * ppu):
                    pygame.draw.rect(surface, WINDOW_DARK, (wx, int(self._sy(b.top + 3.6)), int(1.1 * ppu), int(2.2 * ppu)))
            pygame.draw.rect(surface, BUILDING_FILL, (px, ceil, cw, top - ceil))
            pygame.draw.rect(surface, BUILDING_LIGHT, (px - cw // 3, ceil, cw + 2 * (cw // 3), max(2, cw // 2)))
            cx += 7.0
        lx = b.x + 2.0                       # ceiling lights
        while lx < b.right - 1:
            pygame.draw.rect(surface, WINDOW_LIT, (int(self._sx(lx)), ceil, int(0.9 * ppu), max(2, int(0.12 * ppu))))
            lx += 3.5
        pygame.draw.line(surface, BUILDING_SHADE, (x0, ceil + max(2, cw // 2)), (x1, ceil + max(2, cw // 2)), 1)
        pygame.draw.rect(surface, st.base, (x0, slab, x1 - x0, ceil - slab))
        self._facades.draw(surface, b, st, ppu, x0, x1, slab, ceil)
        sw = max(2, int(0.35 * ppu))
        pygame.draw.rect(surface, BUILDING_SHADE, (x1 - sw, slab, sw, ceil - slab))
        pygame.draw.rect(surface, FG, (x0, slab, x1 - x0, ceil - slab), lw)
        for side, broken in ((x0, b.shattered), (x1, b.exit_shattered)):
            if broken:
                continue
            inward = 1 if side == x0 else -1
            for k in range(3):
                xx = side + inward * k * lw * 2
                pygame.draw.line(surface, GLASS, (xx, ceil), (xx, top), 1 if k else lw)

    def _draw_props(self, surface):
        ppu = self.ppu
        cs = int(CRATE_SIZE * ppu)
        for c in self.world.crates:
            if c.smashed or not self._visible(c.x, CRATE_SIZE):
                continue
            x, y = int(self._sx(c.x)), int(self._sy(c.y + CRATE_SIZE))
            pygame.draw.rect(surface, FACADE_LINE, (x, y, cs, cs))
            pygame.draw.rect(surface, DIM, (x, y, cs, cs), max(1, self.lw - 1))
            pygame.draw.line(surface, DIM, (x, y), (x + cs, y + cs), 1)
            pygame.draw.line(surface, DIM, (x + cs, y), (x, y + cs), 1)
        ds = DEBRIS_SIZE * ppu
        for db in self.world.debris:
            if db.y is None or not self._visible(db.x - 2, DEBRIS_SIZE + 4):
                continue
            cx, cy = self._sx(db.x + DEBRIS_SIZE / 2), self._sy(db.y + DEBRIS_SIZE / 2)
            if not db.landed:
                # warning shadow on the roof, growing as it falls
                h = max(0.0, db.y - db.building.top)
                k = max(0.15, 1 - h / 24)
                sw = ds * (0.6 + 0.8 * k)
                sh = max(4, int(0.3 * ppu))
                pygame.draw.ellipse(surface, ALIEN_DIM,
                                    (int(cx - sw / 2), int(self._sy(db.building.top) - sh / 2), int(sw), sh))
                ang = db.y * 0.35
            else:
                ang = 0.0
            self._draw_alien(surface, cx, cy, ds * 0.62, ang, db.variant)
        for bd in self.world.birds:
            if not self._visible(bd.x, 1):
                continue
            x, y = self._sx(bd.x), self._sy(bd.y + 0.25)
            s = 0.25 * ppu
            flap = math.sin(self.world.time * 25 + bd.x) * s * 0.6 if bd.flying else s * 0.3
            pygame.draw.lines(surface, DIM, False, [(x - s, y - flap), (x, y), (x + s, y - flap)], 2)

    def _runner_pose(self) -> str:
        p = self.world.runner
        if p.stumble > 0 and p.rolling and p.grounded:
            # landing roll: its stills spread over the stumble time
            done = 1.0 - p.stumble / STUMBLE_S
            roll = sprites.ROLL_CYCLE
            return roll[min(len(roll) - 1, int(done * len(roll)))]
        if p.stumble > 0:
            return "stumble"
        if not p.grounded:
            return "jump" if p.vy > 0 else "fall"
        return sprites.RUN_CYCLE[int(self.stride) % len(sprites.RUN_CYCLE)]

    def _draw_alien(self, surface, cx, cy, r, ang, variant):
        """Wreckage of some alien machine: a dark silhouette with a bright outline
        and inner circuitry. Three designs; ang spins it while it falls."""
        lw = max(1, self.lw)
        thin = max(1, lw - 1)

        def pt(a, rr):
            return (cx + math.cos(ang + a) * rr, cy + math.sin(ang + a) * rr)

        def ring(n, rr, off=0.0):
            return [pt(off + 2 * math.pi * k / n, rr) for k in range(n)]

        pulse = 0.5 + 0.5 * math.sin(self.world.time * 9 + variant)
        core = tuple(int(c * (0.55 + 0.45 * pulse)) for c in ALIEN)
        if variant == 0:            # hex core: hexagon, counter-rotated triangle, spokes, nodes
            hexa = ring(6, r)
            tri = [pt(-2 * ang + math.pi / 2 + 2 * math.pi * k / 3, r * 0.45) for k in range(3)]
            pygame.draw.polygon(surface, BG, hexa)
            pygame.draw.polygon(surface, ALIEN, hexa, lw)
            pygame.draw.polygon(surface, ALIEN_DIM, ring(6, r * 0.72, math.pi / 6), thin)
            for k in (0, 2, 4):
                pygame.draw.line(surface, ALIEN_DIM, hexa[k], tri[k // 2], thin)
            pygame.draw.polygon(surface, ALIEN, tri, thin)
            for k in (1, 3, 5):
                pygame.draw.circle(surface, ALIEN, (int(hexa[k][0]), int(hexa[k][1])), max(2, int(r * 0.12)), thin)
        elif variant == 1:          # ring drone: segmented ring, four fins, crosshair
            fins = []
            for k in range(4):
                a = math.pi / 4 + k * math.pi / 2
                fins.append([pt(a - 0.28, r * 0.78), pt(a, r * 1.12), pt(a + 0.28, r * 0.78)])
            pygame.draw.circle(surface, BG, (int(cx), int(cy)), int(r * 0.82))
            for f in fins:
                pygame.draw.polygon(surface, BG, f)
                pygame.draw.lines(surface, ALIEN, False, f, lw)
            box = pygame.Rect(0, 0, int(r * 1.6), int(r * 1.6)); box.center = (int(cx), int(cy))
            for k in range(4):      # ring broken into four arcs
                a0 = -ang + k * math.pi / 2 + 0.18
                pygame.draw.arc(surface, ALIEN, box, a0, a0 + math.pi / 2 - 0.36, lw)
            inner = box.inflate(-int(r * 0.8), -int(r * 0.8))
            pygame.draw.arc(surface, ALIEN_DIM, inner, -ang, -ang + 4.2, thin)
            for k in range(4):
                a = k * math.pi / 2
                pygame.draw.line(surface, ALIEN_DIM, pt(a, r * 0.25), pt(a, r * 0.55), thin)
        else:                       # shard relic: long diamond, nested diamond, glyph ticks
            outer = [pt(0, r * 1.1), pt(math.pi / 2, r * 0.55), pt(math.pi, r * 1.1), pt(-math.pi / 2, r * 0.55)]
            inner = [pt(0, r * 0.7), pt(math.pi / 2, r * 0.3), pt(math.pi, r * 0.7), pt(-math.pi / 2, r * 0.3)]
            pygame.draw.polygon(surface, BG, outer)
            pygame.draw.polygon(surface, ALIEN, outer, lw)
            pygame.draw.polygon(surface, ALIEN_DIM, inner, thin)
            for s in (-0.85, -0.55, 0.55, 0.85):
                a = pt(0, r * s)
                d = 0.12 * r
                pygame.draw.line(surface, ALIEN_DIM, (a[0] - math.sin(ang) * d, a[1] + math.cos(ang) * d),
                                 (a[0] + math.sin(ang) * d, a[1] - math.cos(ang) * d), thin)
            for s in (-1, 1):
                q = pt(0, r * 0.95 * s)
                pygame.draw.circle(surface, ALIEN, (int(q[0]), int(q[1])), max(2, int(r * 0.08)))
        pygame.draw.circle(surface, core, (int(cx), int(cy)), max(2, int(r * 0.16)))

    def _draw_runner(self, surface):
        p = self.world.runner
        sprites.draw(surface, pygame, self._runner_pose(),
                     self._sx(p.x + RUNNER_W / 2), self._sy(p.y), self.ppu)

    def _draw_laser_marker(self, surface):
        r = max(10, int(self.base_ppu * 0.45))
        for p in self.laser_points:
            pygame.draw.circle(surface, ACCENT, (int(p.x), int(p.y)), r, max(2, self.lw))

    # -- HUD --------------------------------------------------------------------
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
        self._text(surface, f"{int(self.world.distance):,} m", (m, int(18 * k)), FG, 48)
        if self.best:
            self._text(surface, f"best {self.best:,} m", (m, int(60 * k)), DIM, 28)
        y0 = self.h // 4
        if self.state == State.Start:
            self._center_text(surface, "ROOFTOP RUN", y0 - 50 * k, FG, 72)
            self._center_text(surface, "Shine the laser to jump. Hold it longer to jump higher.",
                              y0 + 20 * k, FG, 30)
            self._center_text(surface, "Let go before each jump. Crates slow you down; falling wreckage kills.",
                              y0 + 54 * k, DIM, 28)
            self._center_text(surface, "Hold laser (or Space) to start", y0 + 100 * k, FG, 30)
            r = 34 * k
            draw_hold_target(surface, (self.w // 2, y0 + 146 * k + r), r,
                             self.hold_ms / HOLD_TO_START_MS, width=max(2, int(4 * k)))
        elif self.state == State.Dead:
            self._center_text(surface, f"You ran {int(self.world.distance):,} m,", y0 - 20 * k, FG, 56)
            self._center_text(surface, DEATH_TEXT.get(self.world.death, ""), y0 + 26 * k, FG, 40)
            if self.dead_ms >= DEATH_RESTART_DELAY_MS:
                self._center_text(surface, "Retry?", y0 + 80 * k, DIM, 30)

    # -- events -----------------------------------------------------------------
    def on_event(self, event: pygame.event.Event) -> None:
        keys = (pygame.K_SPACE, pygame.K_UP, pygame.K_w)
        if event.type == pygame.KEYDOWN and event.key in keys:
            self.key_held = True
        elif event.type == pygame.KEYUP and event.key in keys:
            self.key_held = False

    def on_unload(self) -> None:
        pass


def get_game():
    return RooftopRun()
