"""
World simulation (pure Python, no pygame).

World units: 1 U = cube size, y is up, ground is y = 0, the player's left edge
is at world x = player.x.
"""
import math
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
    flip: bool = False   # gravity-flip orb: flips gravity instead of jumping


@dataclass
class Portal:
    """Gravity gate, 1 U wide, spanning [bottom, top]: passing through sets gravity."""
    x: float
    bottom: float
    top: float
    gravity: float       # +1 normal (falls down), -1 flipped (falls up)


@dataclass
class ShipGate:
    """Ship/cube gate: passing it turns you into a ship (flying) or back into a cube."""
    x: float
    mode: str            # "ship" or "cube": what you become passing through
    bottom: float = 0.0  # drawn gate span (it triggers at any height)
    top: float = PORTAL_HEIGHT
    used: bool = False


@dataclass
class Coin:
    x: float             # left edge of its cell (centre at x + 0.5), like orbs
    y: float             # centre height
    taken: bool = False
    missed: bool = False


@dataclass
class Player:
    x: float = 0.0
    y: float = 0.0
    vy: float = 0.0
    grounded: bool = True
    angle: float = 0.0  # degrees, visual only
    gravity: float = 1.0  # +1 normal, -1 upside down (runs on undersides, jumps downward)
    mode: str = "cube"  # "cube" or "ship"
    jump_t: float = 99.0    # time since the last ground jump (hold variant)
    holding: bool = False   # still holding the press that started this jump (hold variant)
    since_press: float = 99.0   # time since the last press edge (hold variant)


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
        self.portals: List[Portal] = []      # gravity gates
        self.gates: List[ShipGate] = []      # ship/cube gates
        self.coins: List[Coin] = []
        # coins variant: score = distance + coin points (COIN_POINTS x combo multiplier)
        self.coin_count = 0
        self.coin_points = 0
        self.streak = 0
        self.best_streak = 0
        self.coins_missed = 0
        self.coin_events = []   # (x, y, points, multiplier) for the renderer to pop up
        # hold variant: variable jump height, a bit stronger gravity
        self.hold = "hold" in VARIANTS
        self.boosting = False
        self._held = False      # input last substep: the hold variant jumps on press edges
        self.gravity = HOLD_VARIANT_GRAVITY if self.hold else GRAVITY
        self.jump_v = HOLD_JUMP_VELOCITY if self.hold else JUMP_VELOCITY
        self.pad_v = HOLD_PAD_VELOCITY if self.hold else PAD_VELOCITY
        self.orb_v = HOLD_ORB_VELOCITY if self.hold else ORB_VELOCITY
        self.gen_x = FIRST_OBSTACLE_AT
        self.dead = False
        self.death_cause: Optional[str] = None   # "spike" | "wall" | "ceiling" | "pit" (display only)
        self.recent: List[str] = []
        self._generate()

    # -- difficulty / generation ----------------------------------------------
    @property
    def distance(self) -> float:
        return self.player.x

    @property
    def score(self) -> int:
        return int(self.distance) + self.coin_points

    @property
    def multiplier(self) -> int:
        return max(1, min(COMBO_MAX, self.streak))

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
        enabled = [s for s in self.sections
                   if getattr(s, "variant", None) is None or s.variant in VARIANTS]
        avail = [s for s in enabled if s.is_available(d)] or \
            [min(enabled, key=lambda s: s.min_d)]
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
            elif kind == "fliporb":
                self.orbs.append(Orb(dx, p[2], flip=True))
            elif kind == "portal":
                self.portals.append(Portal(dx, p[2], p[3], p[4]))
            elif kind == "gate":
                self.gates.append(ShipGate(dx, *p[2:]))
            elif kind == "coin":
                self.coins.append(Coin(dx, p[2]))
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
        self.portals = [o for o in self.portals if o.x + 1 > cutoff]
        self.gates = [o for o in self.gates if o.x + 1 > cutoff]
        self.coins = [o for o in self.coins if o.x + 1 > cutoff]

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

    @property
    def flying(self) -> bool:
        return self.player.mode == "ship"

    def can_act(self) -> bool:
        """Would pressing jump right now do anything? (used by the test bot)"""
        if self.flying:
            return True
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
        if self.coins:
            self._check_missed_coins()
        self._generate()

    def _gates(self) -> None:
        p = self.player
        for g in self.gates:
            if not g.used and p.x + 0.5 >= g.x + 0.5:
                g.used = True
                if g.mode != p.mode:
                    p.mode = g.mode
                    p.angle = 0.0
                    p.grounded = False
                    if g.mode == "ship":
                        p.vy = max(-SHIP_MAX_VY, min(SHIP_MAX_VY, p.vy))

    def _ship_substep(self, dt: float, held: bool) -> None:
        """Flying: hold to climb, release to sink. Floors and '#' roofs are safe to
        slide along; block sides, hatched ceilings, spikes and pits are not."""
        p = self.player
        prev_y = p.y
        p.x += self.speed * dt
        p.vy += (SHIP_LIFT if held else -SHIP_GRAVITY) * dt
        p.vy = max(-SHIP_MAX_VY, min(SHIP_MAX_VY, p.vy))
        p.y += p.vy * dt
        self.speed = self.speed_at(p.x)

        left, right = p.x + EPS, p.x + 1.0 - EPS
        overlapping = [b for b in self.blocks if b.x < right and b.x + b.w > left]
        on_ground_span = not self._over_pit(left, right)

        support = 0.0 if on_ground_span and prev_y >= -TOUCH else None
        for b in overlapping:
            if b.top <= prev_y + TOUCH and (support is None or b.top > support):
                support = b.top
        roof = SHIP_CEILING_Y
        for b in overlapping:
            if not b.ceiling and b.bottom >= prev_y + 1 - TOUCH and b.bottom < roof:
                roof = b.bottom
        p.grounded = False
        if support is not None and p.y <= support:
            p.y, p.vy, p.grounded = support, max(0.0, p.vy), True
        if p.y + 1 >= roof:
            p.y, p.vy = roof - 1, min(0.0, p.vy)

        for b in overlapping:
            if p.y < b.top - TOUCH and p.y + 1 > b.bottom + TOUCH:
                self.dead = True
                return
        if (p.y < -TOUCH and on_ground_span) or p.y < -PIT_DEATH_DEPTH:
            self.dead = True
            return
        s = PLAYER_HITBOX_SHRINK
        pl, pr, pb, pt = p.x + s, p.x + 1 - s, p.y + s, p.y + 1 - s
        for sp in self.spikes:
            l, r, b, t = sp.hitbox()
            if pl < r and pr > l and pb < t and pt > b:
                self.dead = True
                return
        # nose follows the flight path (visual only)
        target = math.degrees(math.atan2(p.vy, self.speed))
        p.angle += (target - p.angle) * min(1.0, dt * 20)

    def _check_missed_coins(self):
        for c in self.coins:
            if not c.taken and not c.missed and c.x + 1.0 < self.player.x:
                c.missed = True
                self.coins_missed += 1
                self.streak = 0     # a missed coin breaks the combo

    def _collect_coins(self):
        p = self.player
        cx, cy = p.x + 0.5, p.y + 0.5
        for c in self.coins:
            if not c.taken and (cx - (c.x + 0.5)) ** 2 + (cy - c.y) ** 2 < COIN_REACH ** 2:
                c.taken = True
                self.coin_count += 1
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                pts = COIN_POINTS * self.multiplier
                self.coin_points += pts
                self.coin_events.append((c.x + 0.5, c.y, pts, self.multiplier))

    def _hold_input(self, held: bool) -> None:
        """Hold variant: every jump needs its own press (holding through a landing does not
        jump again); a press up to HOLD_JUMP_BUFFER_S before landing or reaching an orb
        still counts. How long the press is held sets the jump height."""
        p = self.player
        if held and not self._held:
            p.since_press = 0.0
        self._held = held
        if not held:
            p.holding = False
        if p.since_press > HOLD_JUMP_BUFFER_S:
            return
        if p.grounded:
            p.vy = self.jump_v
            p.grounded = False
            p.jump_t = 0.0
            p.holding = held
            p.since_press = 99.0
        else:
            orb = self._touching_orb()
            if orb:
                orb.used = True
                p.since_press = 99.0
                if orb.flip:
                    self._set_gravity(-1.0, 0.0)
                    return
                p.vy = self.orb_v
                p.holding = False

    def _substep(self, dt: float, jump_held: bool) -> None:
        if self.player.gravity < 0:
            self._substep_flipped(dt, jump_held)
            return
        p = self.player
        if self.gates:
            self._gates()
            if p.mode == "ship":
                self._ship_substep(dt, jump_held)
                return
        p.since_press += dt
        if self.hold:
            self._hold_input(jump_held)
        elif jump_held:
            if p.grounded:
                p.vy = self.jump_v
                p.grounded = False
                p.jump_t = 0.0
                p.holding = True
            else:
                orb = self._touching_orb()
                if orb:
                    orb.used = True
                    if orb.flip:
                        self._set_gravity(-1.0, 0.0)
                        return
                    p.vy = self.orb_v
                    p.holding = False
        else:
            p.holding = False

        g = self.gravity
        if (self.hold and p.holding and p.vy > 0
                and HOLD_GRACE_S - EPS <= p.jump_t < MAX_HOLD_S):
            g = HOLD_GRAVITY      # still holding: float higher
        self.boosting = g == HOLD_GRAVITY   # for the renderer's trail
        p.jump_t += dt

        prev_y = p.y
        p.x += self.speed * dt
        p.vy = max(-MAX_FALL_SPEED, p.vy - g * dt)
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
                # came up from below its underside -> ceiling; otherwise ran into its side
                hit_under = b.bottom > 0 and prev_y + 1 <= b.bottom + 0.05
                self.death_cause = "ceiling" if b.ceiling or hit_under else "wall"
                return
        if p.y < -TOUCH and on_ground_span:
            self.dead = True   # hit the far wall of a pit
            self.death_cause = "pit"
            return
        if p.y < -PIT_DEATH_DEPTH:
            self.dead = True
            self.death_cause = "pit"
            return

        # Spikes
        s = PLAYER_HITBOX_SHRINK
        pl, pr, pb, pt = p.x + s, p.x + 1 - s, p.y + s, p.y + 1 - s
        for sp in self.spikes:
            l, r, b, t = sp.hitbox()
            if pl < r and pr > l and pb < t and pt > b:
                self.dead = True
                self.death_cause = "spike"
                return

        # Jump pads fire on contact
        for pad in self.pads:
            if (pl < pad.x + 0.95 and pr > pad.x + 0.05
                    and pb <= pad.base + 0.4 and pt > pad.base and p.vy <= 0.0):
                p.vy = self.pad_v
                p.grounded = False
                p.holding = False

        if self.coins:
            self._collect_coins()

        if self.portals:
            self._check_portals()

        if p.grounded:
            target = round(p.angle / 90.0) * 90.0
            p.angle += (target - p.angle) * min(1.0, dt * 25)
        else:
            p.angle -= SPIN_DEG_PER_SEC * dt

    # -- gravity flip (CUBE_VARIANT=gravity) --------------------------------------
    def _set_gravity(self, g: float, vy: float) -> None:
        p = self.player
        p.gravity = g
        p.vy = vy
        p.grounded = False

    def _check_portals(self) -> None:
        p = self.player
        for po in self.portals:
            if (po.gravity != p.gravity and p.x < po.x + 1 and p.x + 1 > po.x
                    and p.y < po.top and p.y + 1 > po.bottom):
                self._set_gravity(po.gravity, p.vy * FLIP_PORTAL_DAMP)
                return

    def _substep_flipped(self, dt: float, jump_held: bool) -> None:
        """Upside down: falls up, lands on the undersides of solid blocks, jumps
        downward. Hatched ceilings stay deadly from below; flying off the top of
        the screen is a fall. The mirror image of the normal substep."""
        p = self.player
        if jump_held:
            if p.grounded:
                p.vy = -JUMP_VELOCITY
                p.grounded = False
            else:
                orb = self._touching_orb()
                if orb:
                    orb.used = True
                    if orb.flip:
                        self._set_gravity(1.0, 0.0)
                        return
                    p.vy = -ORB_VELOCITY

        prev_top = p.y + 1.0
        p.x += self.speed * dt
        p.vy = min(MAX_FALL_SPEED, p.vy + GRAVITY * dt)
        p.y += p.vy * dt
        self.speed = self.speed_at(p.x)

        left, right = p.x + EPS, p.x + 1.0 - EPS
        overlapping = [b for b in self.blocks if b.x < right and b.x + b.w > left]

        # "Land" on the lowest solid underside we were below last substep.
        support = None
        for b in overlapping:
            if not b.ceiling and b.bottom >= prev_top - TOUCH and (support is None or b.bottom < support):
                support = b.bottom
        if support is not None and p.y + 1.0 >= support:
            p.y = support - 1.0
            p.vy = 0.0
            p.grounded = True
        else:
            p.grounded = False

        # the floor is still solid: a downward jump can't go through it
        if p.y < 0.0 and not self._over_pit(left, right):
            p.y = 0.0
            p.vy = max(p.vy, 0.0)

        for b in overlapping:
            if p.y < b.top - TOUCH and p.y + 1 > b.bottom + TOUCH:
                self.dead = True
                return
        if p.y > FLIP_TOP_DEATH or p.y < -PIT_DEATH_DEPTH:
            self.dead = True
            return

        s = PLAYER_HITBOX_SHRINK
        pl, pr, pb, pt = p.x + s, p.x + 1 - s, p.y + s, p.y + 1 - s
        for sp in self.spikes:
            l, r, b, t = sp.hitbox()
            if pl < r and pr > l and pb < t and pt > b:
                self.dead = True
                return

        self._check_portals()

        if p.grounded:
            target = round(p.angle / 90.0) * 90.0
            p.angle += (target - p.angle) * min(1.0, dt * 25)
        else:
            p.angle += SPIN_DEG_PER_SEC * dt
