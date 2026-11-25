"""
World simulation (pure Python, no pygame).

World units: 1 U = cube size, y is up, ground is y = 0, the player's left edge
is at world x = player.x.
"""
import random
from dataclasses import dataclass
from typing import List, Optional

from .const import *
from . import sections as sec

EPS = 1e-4
TOUCH = 1e-3
MAX_SUBSTEP_S = 1.0 / 240.0


@dataclass
class Block:
    x: float
    w: float
    top: float
    bottom: float = 0.0
    ceiling: bool = False   # drawn hatched; physically just a block


@dataclass
class Spike:
    x: float
    base: float          # y of the flat side (ground/top for up, ceiling for down)
    down: bool = False   # hanging spike pointing down

    def hitbox(self):
        s = SPIKE_HITBOX_SHRINK
        # (left, right, bottom, top) -- central part near the base
        if self.down:
            return (self.x + s, self.x + 1 - s, self.base - 0.6, self.base)
        return (self.x + s, self.x + 1 - s, self.base, self.base + 0.6)


@dataclass
class Pit:
    x: float
    w: float


@dataclass
class Pad:
    x: float
    base: float


@dataclass
class Orb:
    x: float
    y: float
    used: bool = False


@dataclass
class Player:
    x: float = 0.0
    y: float = 0.0
    vy: float = 0.0
    grounded: bool = True
    angle: float = 0.0  # degrees, visual only


pattern_extent = sec.parts_extent


class World:
    def __init__(self, seed: Optional[int] = None, sections=None):
        """sections=None: the full library; sections=[]: an empty world (tests)."""
        self.rng = random.Random(seed)
        self.sections = sec.all_sections() if sections is None else sections
        self.player = Player()
        self.speed = SPEED_START
        self.blocks: List[Block] = []
        self.spikes: List[Spike] = []
        self.pits: List[Pit] = []
        self.pads: List[Pad] = []
        self.orbs: List[Orb] = []
        self.gen_x = FIRST_OBSTACLE_AT
        self.dead = False
        self.recent: List[str] = []
        self._generate()

    # -- difficulty / generation ----------------------------------------------
    @property
    def distance(self) -> float:
        return self.player.x

    def difficulty(self) -> float:
        return min(1.0, self.player.x / DIFFICULTY_FULL_AT)

    speed_at = staticmethod(sec.speed_at)
    min_gap_at = staticmethod(sec.min_gap_at)

    def _pick_section(self) -> "sec.Section":
        d = self.difficulty()
        if not self.recent:
            intro = [s for s in self.sections if s.name == sec.INTRO]
            if intro:
                return intro[0]
        avail = [s for s in self.sections if s.is_available(d)] or \
            [min(self.sections, key=lambda s: s.min_d)]
        fresh = [s for s in avail if s.name not in self.recent]
        pool = fresh or avail
        boost = d >= NEW_PATTERN_WEIGHT_FROM
        weights = [NEW_PATTERN_WEIGHT if boost and s.min_d >= d - 0.3 else 1.0 for s in pool]
        return self.rng.choices(pool, weights)[0]

    def add_parts(self, x0: float, parts) -> float:
        """Place a pattern's parts at world x0; returns the pattern's length."""
        for p in parts:
            kind, dx = p[0], x0 + p[1]
            if kind == "spike":
                self.spikes.append(Spike(dx, p[2]))
            elif kind == "hang":
                self.spikes.append(Spike(dx, p[2], down=True))
            elif kind == "block":
                self.blocks.append(Block(dx, p[2], p[3], p[4]))
            elif kind == "ceiling":
                top = p[4] if len(p) > 4 else p[3] + CEILING_THICKNESS
                self.blocks.append(Block(dx, p[2], top, p[3], ceiling=True))
            elif kind == "pit":
                self.pits.append(Pit(dx, p[2]))
            elif kind == "pad":
                self.pads.append(Pad(dx, p[2]))
            elif kind == "orb":
                self.orbs.append(Orb(dx, p[2]))
            else:
                raise ValueError(f"unknown part {kind!r}")
        return pattern_extent(parts)

    def _generate(self):
        horizon = self.player.x + SPAWN_AHEAD
        while self.sections and self.gen_x < horizon:
            section = self._pick_section()
            self.recent = (self.recent + [section.name])[-NO_REPEAT_WINDOW:]
            parts = section.build(self.rng, self.difficulty(), self.gen_x)
            length = self.add_parts(self.gen_x, parts)
            # a breather between sections
            self.gen_x += length + self.min_gap_at(self.gen_x) + SECTION_BREATHER

        cutoff = self.player.x - 30
        self.blocks = [o for o in self.blocks if o.x + o.w > cutoff]
        self.pits = [o for o in self.pits if o.x + o.w > cutoff]
        self.spikes = [o for o in self.spikes if o.x + 1 > cutoff]
        self.pads = [o for o in self.pads if o.x + 1 > cutoff]
        self.orbs = [o for o in self.orbs if o.x + 1 > cutoff]

    # -- queries ----------------------------------------------------------------
    def _over_pit(self, left: float, right: float) -> bool:
        """True if the whole span [left, right] is above a pit (no ground)."""
        return any(p.x <= left and p.x + p.w >= right for p in self.pits)

    def _touching_orb(self) -> Optional[Orb]:
        p = self.player
        cx, cy = p.x + 0.5, p.y + 0.5
        for o in self.orbs:
            if not o.used and (cx - (o.x + 0.5)) ** 2 + (cy - o.y) ** 2 < ORB_REACH ** 2:
                return o
        return None

    def can_act(self) -> bool:
        """Would pressing jump right now do anything? (used by the test bot)"""
        return self.player.grounded or self._touching_orb() is not None

    # -- physics ------------------------------------------------------------------
    def step(self, dt_s: float, jump_held: bool) -> None:
        if self.dead:
            return
        remaining = dt_s
        while remaining > EPS and not self.dead:
            h = min(MAX_SUBSTEP_S, remaining)
            self._substep(h, jump_held)
            remaining -= h
        self._generate()

    def _substep(self, dt: float, jump_held: bool) -> None:
        p = self.player
        if jump_held:
            if p.grounded:
                p.vy = JUMP_VELOCITY
                p.grounded = False
            else:
                orb = self._touching_orb()
                if orb:
                    orb.used = True
                    p.vy = ORB_VELOCITY

        prev_y = p.y
        p.x += self.speed * dt
        p.vy = max(-MAX_FALL_SPEED, p.vy - GRAVITY * dt)
        p.y += p.vy * dt
        self.speed = self.speed_at(p.x)

        left, right = p.x + EPS, p.x + 1.0 - EPS
        overlapping = [b for b in self.blocks if b.x < right and b.x + b.w > left]
        on_ground_span = not self._over_pit(left, right)

        # Land on the highest surface we were above last substep.
        support = None
        if on_ground_span and prev_y >= -TOUCH:
            support = 0.0
        for b in overlapping:
            if b.top <= prev_y + TOUCH and (support is None or b.top > support):
                support = b.top
        if support is not None and p.y <= support:
            p.y = support
            p.vy = 0.0
            p.grounded = True
        else:
            p.grounded = False

        # Solid collisions: block sides/undersides, pit walls, falling in.
        for b in overlapping:
            if p.y < b.top - TOUCH and p.y + 1 > b.bottom + TOUCH:
                self.dead = True
                return
        if p.y < -TOUCH and on_ground_span:
            self.dead = True   # hit the far wall of a pit
            return
        if p.y < -PIT_DEATH_DEPTH:
            self.dead = True
            return

        # Spikes
        s = PLAYER_HITBOX_SHRINK
        pl, pr, pb, pt = p.x + s, p.x + 1 - s, p.y + s, p.y + 1 - s
        for sp in self.spikes:
            l, r, b, t = sp.hitbox()
            if pl < r and pr > l and pb < t and pt > b:
                self.dead = True
                return

        # Jump pads fire on contact
        for pad in self.pads:
            if (pl < pad.x + 0.95 and pr > pad.x + 0.05
                    and pb <= pad.base + 0.4 and pt > pad.base and p.vy <= 0.0):
                p.vy = PAD_VELOCITY
                p.grounded = False

        if p.grounded:
            target = round(p.angle / 90.0) * 90.0
            p.angle += (target - p.angle) * min(1.0, dt * 25)
        else:
            p.angle -= SPIN_DEG_PER_SEC * dt
