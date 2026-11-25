"""
Rooftop Run world simulation (pure Python, no pygame).

Units: 1 U ~ 1 m, y is up. The runner's feet are at (x .. x + RUNNER_W, y).
"""
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from .const import *

EPS = 1e-3
SUBSTEP_S = 1.0 / 240.0
NO_BOTTOM = -1000.0


@dataclass
class Building:
    x: float
    w: float
    top: float                     # roof (or, for a window building, the floor inside)
    kind: str = "roof"             # roof | window | girder | crumble
    ceil: Optional[float] = None   # window: underside of the wall above the window
    slab_top: Optional[float] = None
    touched_t: Optional[float] = None   # crumble: time since first landed on
    sink_v: float = 0.0
    shattered: bool = False        # window: glass broken
    exit_shattered: bool = False   # window: the pane on the far side, smashed on the way out
    max_drop: float = 0.0          # crumble: how far it can have sunk when you leave it
    collapsed: bool = False        # crumble: knocked down by running into it
    seed: int = 0                  # for facade decoration

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.top - GIRDER_THICKNESS if self.kind == "girder" else NO_BOTTOM


@dataclass
class Crate:
    x: float
    y: float
    smashed: bool = False


@dataclass
class Debris:
    x: float
    building: Building
    y: Optional[float] = None      # None until it starts falling
    vy: float = 0.0
    landed: bool = False
    variant: int = 0               # which piece of alien tech it is (art only)


@dataclass
class Bird:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    flying: bool = False


@dataclass
class Runner:
    x: float = 0.0
    y: float = 0.0
    vy: float = 0.0
    grounded: bool = True
    since_ground: float = 0.0      # time since last standing on something (coyote time)
    since_press: float = 99.0      # time since the jump button was pressed (jump buffer)
    jump_t: float = 99.0           # time since the current jump started
    holding_jump: bool = False     # still holding the button that started this jump
    stumble: float = 0.0           # seconds of stumble left
    rolling: bool = False          # the stumble is a landing roll (after a hard landing)


def air_time(dy: float) -> Optional[float]:
    """Seconds a full-hold jump takes to come back down to height dy (relative to
    takeoff), or None if it can't get that high."""
    t, y, vy = 0.0, 0.0, JUMP_VELOCITY
    t_apex_y = 0.0
    dt = 1.0 / 240.0
    while True:
        g = HOLD_GRAVITY if (t < MAX_HOLD_S and vy > 0) else GRAVITY
        vy = max(-MAX_FALL_SPEED, vy - g * dt)
        y += vy * dt
        t += dt
        if vy < 0:
            if y < dy and t_apex_y < dy:
                return None          # never got that high
            if y <= dy:
                return t
        else:
            t_apex_y = y
        if t > 10:
            return None


class World:
    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.runner = Runner()
        self.speed = SPEED_START
        self.time = 0.0
        self.buildings: List[Building] = []
        self.crates: List[Crate] = []
        self.debris: List[Debris] = []
        self.birds: List[Bird] = []
        self.dead = False
        self.death: Optional[str] = None     # "fell" | "wall"
        self.events: List[tuple] = []        # (kind, x, y) for effects; the game drains it
        self._held = False
        self.support: Optional[Building] = None

        first = Building(-30.0, 30.0 + FIRST_BUILDING_W, 6.0, seed=self.rng.randrange(1 << 30))
        self.buildings.append(first)
        self._add_birds(first)
        self.runner.y = first.top
        self.support = first
        self._generate()

    # -- generation ------------------------------------------------------------
    @property
    def distance(self) -> float:
        return max(0.0, self.runner.x)

    def _unlocked(self, what: str, x: float) -> bool:
        return x >= UNLOCK[what]

    def _difficulty(self, x: float) -> float:
        return min(1.0, x / 2000.0)

    def _gen_speed(self, prev: Building, crates_on_prev: int) -> float:
        """A pessimistic speed for judging the next gap: no further acceleration,
        a possible hard-landing stumble, and every crate on the previous roof hit."""
        v = self.speed * HARD_LANDING_SLOWDOWN
        v *= CRATE_SLOWDOWN ** crates_on_prev
        return max(SPEED_FLOOR, v)

    def _pick_kind(self, x: float, prev: Building) -> str:
        options, weights = ["roof"], [5.0]
        if prev.kind == "roof":
            if self._unlocked("window", x):
                options.append("window"); weights.append(1.6)
            if self._unlocked("girder", x):
                options.append("girder"); weights.append(1.3)
            if self._unlocked("crumble", x):
                options.append("crumble"); weights.append(1.1)
        return self.rng.choices(options, weights)[0]

    def _generate(self):
        r = self.rng
        while self.buildings[-1].right < self.runner.x + SPAWN_AHEAD:
            prev = self.buildings[-1]
            x = prev.right
            d = self._difficulty(x)
            n_crates = sum(1 for c in self.crates if prev.x <= c.x < prev.right)
            v = self._gen_speed(prev, n_crates)
            kind = self._pick_kind(x, prev)
            seed = r.randrange(1 << 30)

            if kind == "window":
                # run straight in through the glass (or tap); a big jump hits the wall above
                floor = max(TOP_MIN, prev.top - r.uniform(0.5, 1.0))
                gap = r.uniform(0.8, 1.3)
                ceil = floor + WINDOW_CEILING
                b = Building(x + gap, max(12.0, v * r.uniform(1.2, 2.4)), floor, "window",
                             ceil=ceil, slab_top=ceil + r.uniform(2.0, 8.0), seed=seed)
                self.buildings.append(b)
                continue

            takeoff = prev.top - prev.max_drop
            lo_top = max(TOP_MIN, takeoff - STEP_DOWN_MAX)
            hi_top = min(TOP_MAX, takeoff + STEP_UP_MAX * (0.5 + 0.5 * d))
            if kind == "crumble":
                # prefer high crumbling roofs: they have room to sink, so they can be long
                lo_top = min(max(lo_top, hi_top - 3.0), hi_top)
            top = r.uniform(lo_top, hi_top) if hi_top > lo_top else lo_top
            t = air_time(top - takeoff)
            reach = v * t if t else 0.0
            frac = r.uniform(0.35 + 0.2 * d, 0.6 + 0.2 * d) * GAP_SAFETY / 0.8
            gap = max(GAP_MIN, min(frac, GAP_SAFETY) * reach)

            if kind == "girder":
                w = max(4.0, v * r.uniform(0.6, 1.2))
            elif kind == "crumble":
                # long enough to feel, short enough that after sinking for its whole
                # length the next roof (at worst TOP_MIN) is at most a half step up
                room = top - (TOP_MIN - STEP_UP_MAX * 0.5)
                secs = min(r.uniform(CRUMBLE_S_MIN, CRUMBLE_S_MAX),
                           crumble_time_for_drop(room) - CRUMBLE_SLACK_S)
                secs = max(0.3, secs)
                w = v * secs
            else:
                w = max(12.0, v * r.uniform(1.6, 4.0))
            b = Building(x + gap, w, top, kind, seed=seed)
            if kind == "crumble":
                # time on it is at most w / v (v is a pessimistic speed)
                b.max_drop = crumble_drop(w / v + CRUMBLE_SLACK_S)
            self.buildings.append(b)

            if kind == "roof":
                self._decorate_roof(b, d)

        cutoff = self.runner.x - 80
        self.buildings = [b for b in self.buildings if b.right > cutoff]
        self.crates = [c for c in self.crates if c.x > cutoff]
        self.debris = [db for db in self.debris if db.x > cutoff]
        self.birds = [bd for bd in self.birds if bd.x > cutoff and bd.y < 60]

    def _decorate_roof(self, b: Building, d: float):
        r = self.rng
        if self._unlocked("crates", b.x) and r.random() < 0.45 + 0.25 * d:
            n = r.randint(1, 2 if d < 0.5 else 3)
            spacing = max(4.0, self.speed * 0.6)
            xs = []
            for _ in range(n):
                cx = r.uniform(b.x + 5, b.right - 4)
                if all(abs(cx - o) >= spacing for o in xs):
                    xs.append(cx)
            for cx in xs:
                self.crates.append(Crate(cx, b.top))
                if r.random() < 0.25:  # stacked pair
                    self.crates.append(Crate(cx, b.top + CRATE_SIZE))
        if self._unlocked("debris", b.x) and b.w > 16 and r.random() < 0.35:
            self.debris.append(Debris(b.x + b.w * r.uniform(0.35, 0.7), b, variant=r.randrange(3)))
        if r.random() < 0.35:
            self._add_birds(b)

    def _add_birds(self, b: Building):
        cx = self.rng.uniform(b.x + 3, max(b.x + 4, b.right - 3))
        for _ in range(self.rng.randint(3, 6)):
            self.birds.append(Bird(cx + self.rng.uniform(-1.5, 1.5), b.top))

    # -- simulation ----------------------------------------------------------------
    def step(self, dt_s: float, held: bool) -> None:
        if self.dead:
            return
        remaining = dt_s
        while remaining > 1e-6 and not self.dead:
            h = min(SUBSTEP_S, remaining)
            self._substep(h, held)
            remaining -= h
        self._update_birds(dt_s)
        self._generate()

    def _near(self, x0: float, x1: float):
        return [b for b in self.buildings if b.x < x1 and b.right > x0]

    def _substep(self, dt: float, held: bool):
        p = self.runner
        self.time += dt

        # input: press edge -> buffered jump; release ends the hold
        pressed = held and not self._held
        self._held = held
        p.since_press = 0.0 if pressed else p.since_press + dt
        if not held:
            p.holding_jump = False
        can_jump = p.grounded or p.since_ground <= COYOTE_S
        if p.since_press <= JUMP_BUFFER_S and can_jump and p.jump_t > COYOTE_S:
            p.vy = JUMP_VELOCITY
            p.grounded = False
            p.since_ground = COYOTE_S + 1   # no second coyote jump
            p.since_press = 99.0
            p.jump_t = 0.0
            p.holding_jump = held
            self.support = None
            self.events.append(("jump", p.x, p.y))
        p.jump_t += dt

        # speed
        if p.stumble > 0:
            p.stumble -= dt
        else:
            self.speed = min(SPEED_MAX, self.speed + ACCEL * dt)

        # crumbling roofs sink
        for b in self.buildings:
            if b.kind == "crumble" and b.touched_t is not None:
                b.touched_t += dt
                if b.touched_t > CRUMBLE_DELAY_S:
                    b.sink_v = min(CRUMBLE_MAX_SINK, b.sink_v + CRUMBLE_ACCEL * dt)
                    b.top -= b.sink_v * dt
                    if b is self.support and p.grounded:
                        p.y = b.top      # standing on it: ride it down (it sinks faster than one step of falling)

        # integrate
        prev_y = p.y
        p.x += self.speed * dt
        rising_held = p.holding_jump and p.vy > 0 and p.jump_t < MAX_HOLD_S
        g = HOLD_GRAVITY if rising_held else GRAVITY
        p.vy = max(-MAX_FALL_SPEED, p.vy - g * dt)
        p.y += p.vy * dt

        left, right = p.x + EPS, p.x + RUNNER_W - EPS
        near = self._near(left, right)

        # landing (or staying on a sinking roof)
        was_grounded = p.grounded
        p.grounded = False
        best = None
        for b in near:
            snap = 0.25 if (was_grounded and b is self.support) else EPS
            if p.vy <= 0 and prev_y >= b.top - snap and p.y <= b.top + EPS:
                if best is None or b.top > best.top:
                    best = b
        if best is not None:
            if not was_grounded:
                if p.vy < HARD_LANDING_VY:
                    self.speed = max(SPEED_FLOOR, self.speed * HARD_LANDING_SLOWDOWN)
                    p.stumble = STUMBLE_S
                    p.rolling = True
                    self.events.append(("hard_landing", p.x, best.top))
                else:
                    self.events.append(("land", p.x, best.top))
            p.y = best.top
            p.vy = 0.0
            p.grounded = True
            p.since_ground = 0.0
            self.support = best
            if best.kind == "crumble" and best.touched_t is None:
                best.touched_t = 0.0
                self.events.append(("crumble", best.x, best.top))
        else:
            p.since_ground += dt
            if not was_grounded or not any(b is self.support for b in near):
                self.support = None

        # walls, window ceilings
        for b in near:
            if b.kind == "window":
                head, prev_head = p.y + RUNNER_H, prev_y + RUNNER_H
                if head > b.ceil and p.y < b.slab_top:
                    was_inside = p.x - self.speed * dt + RUNNER_W > b.x + EPS
                    if was_inside and prev_head <= b.ceil + 0.05:
                        # inside: bump your head
                        p.y = b.ceil - RUNNER_H
                        p.vy = min(p.vy, 0.0)
                        p.holding_jump = False
                    else:
                        return self._die("wall")
                if not b.shattered and p.y < b.ceil and p.y + RUNNER_H > b.top:
                    b.shattered = True
                    self.events.append(("glass", b.x, b.top))
                # crash out through the far pane (just looks and sounds the part: no slowdown)
                if (not b.exit_shattered and p.x + RUNNER_W >= b.right - 0.05
                        and p.y < b.ceil and p.y + RUNNER_H > b.top - 0.5):
                    b.exit_shattered = True
                    self.events.append(("glass_exit", b.right, b.top))
            if p.y < b.top - EPS and p.y + RUNNER_H > b.bottom + EPS:
                if b.kind == "crumble":
                    b.collapsed = True
                    self.events.append(("collapse", b.x, b.top, b.right))
                    return self._die("crumble")
                return self._die("wall")

        if p.y < FALL_DEATH_Y:
            return self._die("fell")

        # crates and debris
        for c in self.crates:
            if not c.smashed and self._overlaps(c.x, c.y, CRATE_SIZE, CRATE_SIZE):
                c.smashed = True
                self.speed = max(SPEED_FLOOR, self.speed * CRATE_SLOWDOWN)
                self.events.append(("crate", c.x, c.y))
        for db in self.debris:
            if db.y is None:
                if p.x > db.x - self.speed * DEBRIS_LEAD_S:
                    db.y = db.building.top + 24.0
                    db.vy = DEBRIS_DROP_VY
                    self.events.append(("debris_warn", db.x, db.building.top))
                continue
            if not db.landed:
                db.vy -= DEBRIS_GRAVITY * dt
                db.y += db.vy * dt
                if db.y <= db.building.top:
                    db.y, db.landed = db.building.top, True
                    self.events.append(("debris_land", db.x, db.y))
            if self._overlaps(db.x, db.y, DEBRIS_SIZE, DEBRIS_SIZE):
                # falling on you: mist. Already on the roof: you ran into it
                return self._die("debris_wall" if db.landed else "debris")

    def _overlaps(self, x, y, w, h) -> bool:
        p = self.runner
        return p.x < x + w and p.x + RUNNER_W > x and p.y < y + h and p.y + RUNNER_H > y

    def _die(self, why: str):
        self.dead = True
        self.death = why
        self.events.append(("death", self.runner.x, self.runner.y))

    def _update_birds(self, dt: float):
        p = self.runner
        for bd in self.birds:
            if not bd.flying and abs(bd.x - p.x) < 6 + self.speed * 0.2:
                bd.flying = True
                bd.vx = self.rng.uniform(3, 9)
                bd.vy = self.rng.uniform(5, 10)
            if bd.flying:
                bd.x += bd.vx * dt
                bd.y += bd.vy * dt
                bd.vy += 2 * dt
