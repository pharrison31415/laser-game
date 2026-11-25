import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import List

import pygame

from engine.api import Game, FrameData
from engine.app.context import Context

from .const import *
from .world import World, RUNNER_W, RUNNER_H
from . import sprites


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


DEATH_TEXT = {"fell": "then fell to the street.", "wall": "then ran into a wall."}


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
            return w.support.top
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

    def _burst(self, x, y, n, color, speed, size, up=0.0, gravity=30.0, carry=0.3):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            s = random.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, math.cos(a) * s + self.world.speed * carry,
                                           math.sin(a) * s + up, random.uniform(0.4, 1.0),
                                           color, random.uniform(0.5, 1.0) * size, gravity))

    def _consume_events(self):
        for kind, x, y in self.world.events:
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
                self._burst(x + DEBRIS_SIZE / 2, y, 16, DIM, 6, 0.3, up=3)
                self.shake = max(self.shake, 0.45)
            elif kind == "debris_hit":
                self.shake = max(self.shake, 0.5)
            elif kind == "crumble":
                self.shake = max(self.shake, 0.2)
            elif kind == "death":
                self._burst(x + RUNNER_W / 2, y + RUNNER_H / 2, 30, ACCENT, 9, 0.25, up=3)
                self.shake = max(self.shake, 0.5)
        self.world.events.clear()

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
        self._draw_skyline(surface, 0.15, SKY_FAR, 9.0, (6, 20), 0.35)
        self._draw_skyline(surface, 0.4, SKY_NEAR, 7.0, (3, 14), 0.6)
        self._draw_buildings(surface)
        self._draw_props(surface)
        if self.state != State.Dead:
            self._draw_runner(surface)
        for pt in self.particles:
            s = max(2, int(pt.size * self.ppu))
            pygame.draw.rect(surface, pt.color, (int(self._sx(pt.x)), int(self._sy(pt.y)), s, s))
        self._draw_laser_marker(surface)
        self._draw_hud(surface)

    def _draw_skyline(self, surface, factor, color, spacing, heights, vfactor):
        """Distant city silhouettes, scrolling slower than the rooftops (parallax)."""
        ppu = self.base_ppu * (0.5 + 0.5 * self.zoom)
        cam_x = self.world.runner.x * factor
        first = int(cam_x / spacing) - 2
        base_y = self.h - (self.cam_y * vfactor * 0.3) * ppu * 0.2
        for i in range(first, first + int(self.w / (spacing * ppu)) + 4):
            r = random.Random(i * 7919 + int(factor * 1000))
            bw = r.uniform(0.6, 1.0) * spacing
            bh = r.uniform(*heights)
            x = (i * spacing - cam_x) * ppu + self.runner_sx * 0.5
            top = base_y - bh * ppu * 0.6 - self.h * 0.1
            pygame.draw.rect(surface, color, (int(x), int(top), int(bw * ppu) + 1, self.h))

    def _visible(self, x: float, w: float) -> bool:
        sx = self._sx(x)
        return sx < self.w and sx + w * self.ppu > 0

    def _facade(self, surface, b, x0, x1, top_wy, bottom_sy):
        """Grid of dark window frames on a building face."""
        ppu = self.ppu
        col, row = 2.0, 2.6
        if ppu * col < 10:
            return
        y = top_wy - 1.4
        rnd = random.Random(b.seed)
        offs = rnd.uniform(0.3, 1.0)
        while True:
            sy = self._sy(y)
            if sy > bottom_sy or sy > self.h:
                break
            cx = b.x + offs
            while cx + 1.0 < x1:
                if cx >= x0:
                    pygame.draw.rect(surface, FACADE_LINE,
                                     (int(self._sx(cx)), int(sy), int(1.0 * ppu), int(1.3 * ppu)), 1)
                cx += col
            y -= row

    def _draw_buildings(self, surface):
        lw = self.lw
        bottom = self.h + 10
        for b in self.world.buildings:
            if not self._visible(b.x, b.w):
                continue
            jitter = 0.0
            if b.kind == "crumble" and b.touched_t is not None and b.touched_t > CRUMBLE_DELAY_S * 0.5:
                jitter = random.uniform(-0.08, 0.08) * self.ppu
            x0 = int(self._sx(b.x) + jitter)
            x1 = int(self._sx(b.right) + jitter)
            top = int(self._sy(b.top))
            if b.kind == "girder":
                th = max(4, int(GIRDER_THICKNESS * self.ppu))
                pygame.draw.rect(surface, BUILDING_FILL, (x0, top, x1 - x0, th))
                step = max(8, int(self.ppu * 0.8))
                for k, xx in enumerate(range(x0, x1 - step, step)):  # truss zig-zag
                    a, c = (top + th, top) if k % 2 == 0 else (top, top + th)
                    pygame.draw.line(surface, FACADE_LINE, (xx, a), (xx + step, c), 1)
                pygame.draw.rect(surface, FG, (x0, top, x1 - x0, th), lw)
                continue

            pygame.draw.rect(surface, BUILDING_FILL, (x0, top, x1 - x0, bottom - top))
            self._facade(surface, b, b.x, b.right, b.top, bottom)
            if b.kind == "crumble":
                rnd = random.Random(b.seed)
                for _ in range(3):  # cracks
                    cx = rnd.uniform(0.2, 0.8)
                    pts, yy = [], top
                    xx = x0 + (x1 - x0) * cx
                    while yy < min(bottom, top + self.ppu * 6):
                        pts.append((xx, yy))
                        xx += rnd.uniform(-0.6, 0.6) * self.ppu
                        yy += rnd.uniform(0.5, 1.2) * self.ppu
                    if len(pts) > 1:
                        pygame.draw.lines(surface, FG, False, pts, 1)
            pygame.draw.line(surface, FG, (x0, top), (x1, top), lw)
            pygame.draw.line(surface, FG, (x0, top), (x0, bottom), lw)
            pygame.draw.line(surface, FG, (x1, top), (x1, bottom), lw)

            if b.kind == "window":
                ceil, slab = int(self._sy(b.ceil)), int(self._sy(b.slab_top))
                # interior: lit back wall with support columns, and the wall above the window
                pygame.draw.rect(surface, INTERIOR, (x0, ceil, x1 - x0, top - ceil))
                cw = max(3, int(0.5 * self.ppu))
                cx = b.x + 5.0
                while cx < b.right - 2:
                    pygame.draw.rect(surface, BUILDING_FILL, (int(self._sx(cx)), ceil, cw, top - ceil))
                    cx += 7.0
                pygame.draw.rect(surface, BUILDING_FILL, (x0, slab, x1 - x0, ceil - slab))
                self._facade(surface, b, b.x, b.right, b.slab_top, ceil - 4)
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
                pygame.draw.ellipse(surface, DIM,
                                    (int(cx - sw / 2), int(self._sy(db.building.top) - sh / 2), int(sw), sh))
                ang = db.y * 0.6
            else:
                ang = 0.3
            pts = [(cx + math.cos(ang + a) * ds * 0.7, cy + math.sin(ang + a) * ds * 0.7)
                   for a in (0, 1.9, 3.3, 4.6)]
            pygame.draw.polygon(surface, BUILDING_FILL, pts)
            pygame.draw.polygon(surface, FG, pts, self.lw)
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
            self._center_text(surface, "Let go before each jump. Crates and debris slow you down.",
                              y0 + 54 * k, DIM, 28)
            self._center_text(surface, "Hold laser (or Space) to start", y0 + 100 * k, FG, 30)
            frac = min(1.0, self.hold_ms / HOLD_TO_START_MS)
            bw, bh = int(240 * k), max(8, int(12 * k))
            bx, by = self.w // 2 - bw // 2, int(y0 + 138 * k)
            pygame.draw.rect(surface, DIM, (bx, by, bw, bh), 1)
            pygame.draw.rect(surface, ACCENT, (bx + 1, by + 1, int((bw - 2) * frac), bh - 2))
        elif self.state == State.Dead:
            self._center_text(surface, f"You ran {int(self.world.distance):,} m,", y0 - 20 * k, FG, 56)
            self._center_text(surface, DEATH_TEXT.get(self.world.death, ""), y0 + 26 * k, FG, 40)
            if self.dead_ms >= DEATH_RESTART_DELAY_MS:
                msg = ("Let go of the laser, then shine it again to retry" if self.need_release
                       else "Shine the laser (or Space) to retry")
                self._center_text(surface, msg, y0 + 80 * k, DIM, 30)
        self._text(surface, "Laser/Space: jump (hold = higher)  •  C: calibrate  •  Esc: pause",
                   (int(20 * k), self.h - int(36 * k)), DIM, 24)

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
