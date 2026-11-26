"""
Flock Shot rules, in pure Python (no pygame): birds take off from the grass and
weave around the sky; each release of birds comes with a few shells; shoot
enough birds in a round of ten to go on to the next, faster round.

Coordinates: U, x from 0 (left) to width, y up, the grass top at GROUND_Y.
"""
import math
import random
from dataclasses import dataclass
from typing import List, Optional

from .const import *


@dataclass
class Bird:
    x: float
    y: float
    vx: float
    vy: float
    speed: float
    fly_left: float               # seconds until it flies off
    turn_in: float
    state: str = "flying"         # flying | escaping | hit | falling | gone
    t: float = 0.0                # time in the current state
    flap: float = 0.0             # wing animation phase
    spin: float = 0.0
    order: int = 0                # which of the round's ten birds this is
    decoy: bool = False           # must not be shot
    style: str = "glide"          # glide | zigzag | dash | swoop
    pause: float = 0.0            # dash style: seconds of hovering left

    @property
    def alive(self) -> bool:
        return self.state in ("flying", "escaping")


class World:
    def __init__(self, width_u: float, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.width = width_u
        self.round = 1
        self.score = 0
        self.round_hits: List[Optional[bool]] = []   # per bird released: True hit, False escaped, None in the air
        self.birds: List[Bird] = []
        self.shells = 0
        self.next_volley_in = ROUND_INTRO_S
        self.intro = ROUND_INTRO_S        # > 0: the round's title is showing
        self.over = False
        self.round_result: Optional[str] = None    # "clear" / "perfect" while between rounds
        self.penalty = 0                  # decoys hit this round (each takes a hit back)
        self.events: List[tuple] = []     # (kind, x, y, ...) for the renderer

    # -- difficulty ----------------------------------------------------------------
    def level(self) -> float:
        """How many rounds of difficulty in: round - 1, climbing faster after RAMP_FROM."""
        return self.round - 1 + RAMP_EXTRA * max(0, self.round - RAMP_FROM)

    def speed(self) -> float:
        return min(SPEED_MAX, BIRD_SPEED * SPEED_PER_ROUND ** self.level())

    def fly_time(self) -> float:
        return max(FLY_TIME_MIN, FLY_TIME_S * FLY_TIME_PER_ROUND ** self.level())

    def size(self) -> float:
        """Bird scale this round (1 = round 1): smaller birds are harder to hit."""
        return max(SIZE_MIN, SIZE_PER_ROUND ** self.level())

    def needed(self) -> int:
        """Hits needed to clear this round."""
        return min(9, 6 + int(self.level()) // 2)

    def turn_every(self) -> float:
        k = TURN_PER_ROUND ** self.level()
        lo, hi = TURN_EVERY_S
        return self.rng.uniform(max(TURN_MIN_S, lo * k), max(TURN_MIN_S * 1.5, hi * k))

    def volley_size(self) -> int:
        left = BIRDS_PER_ROUND - len(self.round_hits)
        return min(left, 2 if self.round >= TWO_BIRDS_FROM_ROUND else 1)

    @property
    def hits(self) -> int:
        return sum(1 for h in self.round_hits if h) - self.penalty

    # -- actions -----------------------------------------------------------------------
    def shoot(self, x: float, y: float) -> Optional[Bird]:
        """A shot at (x, y). Returns the bird hit, if any. No shells: nothing happens."""
        if self.over or self.shells <= 0 or not any(b.alive for b in self.birds):
            return None
        self.shells -= 1
        best, best_d = None, HIT_R * self.size()
        for b in self.birds:
            if b.alive:
                d = math.hypot(b.x - x, b.y - y)
                if d < best_d:
                    best, best_d = b, d
        if best is None:
            self.events.append(("miss", x, y))
            if self.shells == 0:          # out of shells: the rest of the volley flies off
                for b in self.birds:
                    if b.state == "flying":
                        self._escape(b)
            return None
        best.state, best.t = "hit", 0.0
        if best.decoy:
            self.penalty += 1
            self.score = max(0, self.score - DECOY_PENALTY)
            self.events.append(("decoy", best.x, best.y, DECOY_PENALTY))
        else:
            self._record(best, True)
            pts = POINTS_PER_HIT + POINTS_ROUND_BONUS * (self.round - 1)
            self.score += pts
            self.events.append(("hit", best.x, best.y, pts))
        if self.shells == 0:
            for b in self.birds:
                if b.state == "flying":
                    self._escape(b)
        return best

    # -- simulation -----------------------------------------------------------------------
    def step(self, dt: float) -> None:
        if self.over:
            return
        self.intro = max(0.0, self.intro - dt)
        for b in self.birds:
            self._move(b, dt)
        self.birds = [b for b in self.birds if b.state != "gone"]

        if not self.birds:
            if len(self.round_hits) >= BIRDS_PER_ROUND:
                self._end_round()
                return
            self.next_volley_in -= dt
            if self.next_volley_in <= 0:
                self._release()

    def _release(self):
        n = self.volley_size()
        decoys = 0
        if self.round >= DECOY_FROM:
            p = DECOY_CHANCE + DECOY_CHANCE_PER_ROUND * (self.round - DECOY_FROM)
            decoys = 1 if self.rng.random() < p else 0
        for k in range(n + decoys):
            x = self.rng.uniform(1.5, self.width - 1.5)
            ang = math.radians(self.rng.uniform(55, 125))
            s = self.speed()
            b = Bird(x, GROUND_Y - 0.6, math.cos(ang) * s, math.sin(ang) * s, s,
                     self.fly_time() + 0.4 * k, self.turn_every())
            if k >= n:
                b.decoy = True
            else:
                b.order = len(self.round_hits)
                self.round_hits.append(None)
                b.style = self._pick_style()
            self.birds.append(b)
            self.events.append(("takeoff", b.x, GROUND_Y))
        self.shells = SHOTS_PER_VOLLEY
        self.next_volley_in = VOLLEY_GAP_S

    def _pick_style(self) -> str:
        if self.round < MOVES_FROM:
            return "glide"
        p = min(MOVES_MAX, MOVES_PER_ROUND * (self.round - MOVES_FROM + 1))
        if self.rng.random() >= p:
            return "glide"
        return self.rng.choice(["zigzag", "dash", "swoop"])

    def _record(self, b: Bird, hit: bool):
        if not b.decoy:
            self.round_hits[b.order] = hit

    def _escape(self, b: Bird):
        b.state, b.t = "escaping", 0.0
        ang = math.radians(self.rng.uniform(70, 110))
        s = b.speed * ESCAPE_SPEEDUP
        b.vx, b.vy = math.cos(ang) * s, math.sin(ang) * s
        self._record(b, False)
        self.events.append(("escape", b.x, b.y))

    def _move(self, b: Bird, dt: float):
        b.t += dt
        if b.state == "hit":                    # a moment frozen in the air, then it drops
            if b.t > 0.35:
                b.state, b.t, b.vx, b.vy = "falling", 0.0, 0.0, 0.0
            return
        if b.state == "falling":
            b.vy -= FALL_GRAVITY * dt
            b.y += b.vy * dt
            b.spin += dt * 9
            if b.y < GROUND_Y - 0.8:
                b.state = "gone"
                self.events.append(("thud", b.x, GROUND_Y))
            return
        b.flap += dt * (9 if b.state == "flying" else 13)
        if b.state == "flying":
            b.fly_left -= dt
            if b.pause > 0:                     # dash style: hovering, then a fast dash
                b.pause -= dt
                b.flap += dt * 6
                if b.pause <= 0:
                    ang = math.atan2(b.vy, b.vx)
                    s = b.speed * 2.0
                    b.vx, b.vy = math.cos(ang) * s, math.sin(ang) * s
                    b.turn_in = self.rng.uniform(0.35, 0.6)
                b.fly_left += dt * 0.5          # hovering doesn't use up all its time
                return
            if b.fly_left <= 0:
                self._escape(b)
            else:
                b.turn_in -= dt
                if b.turn_in <= 0 and b.style != "glide" and self._styled_turn(b):
                    pass
                elif b.turn_in <= 0:
                    b.turn_in = self.turn_every()
                    # mostly sideways and up, sometimes dipping; never towards the grass
                    lo = 15 if b.y > GROUND_Y + 3 else 35
                    ang = math.radians(self.rng.uniform(lo, 180 - lo))
                    if b.y > 7.5 and self.rng.random() < 0.6:
                        ang = -ang                  # high up: dive back down
                    if self.rng.random() < 0.5:
                        ang = math.pi - ang         # left or right
                    b.vx, b.vy = math.cos(ang) * b.speed, math.sin(ang) * b.speed
                # walls: bounce off the sides, the top, and the grass
                if (b.x < 0.8 and b.vx < 0) or (b.x > self.width - 0.8 and b.vx > 0):
                    b.vx = -b.vx
                if b.y > SCREEN_U - 1.0 and b.vy > 0:
                    b.vy = -b.vy
                low = GROUND_Y + (0.55 if b.style == "swoop" else 1.2)
                if b.y < low and b.vy < 0 and b.t > 0.6:
                    b.vy = -b.vy
        b.x += b.vx * dt
        b.y += b.vy * dt
        if b.state == "escaping" and (b.y > TOP_ESCAPE_Y or b.x < -2 or b.x > self.width + 2):
            b.state = "gone"

    def _styled_turn(self, b: Bird) -> bool:
        """A turn in the bird's flight style. Returns False to use a normal turn."""
        r = self.rng
        if b.style == "zigzag":                 # sharp reversals, quickly
            ang = math.atan2(b.vy, b.vx)
            ang = math.pi - ang + r.uniform(-0.4, 0.4) if r.random() < 0.6 else -ang
            b.vx, b.vy = math.cos(ang) * b.speed * 1.15, math.sin(ang) * b.speed * 1.15
            b.turn_in = r.uniform(0.28, 0.45)
            return True
        if b.style == "dash":                   # stop, hover, then shoot off
            b.vx *= 0.08
            b.vy *= 0.08
            b.pause = r.uniform(0.35, 0.6)
            b.turn_in = 99.0
            ang = math.radians(r.uniform(-50, 50) + (0 if r.random() < 0.5 else 180))
            b.vx, b.vy = math.cos(ang) * 0.3, math.sin(ang) * 0.3
            return True
        if b.style == "swoop" and b.y > GROUND_Y + 3 and r.random() < 0.6:
            # dive steeply to skim the grass (partly hidden), then climb out
            ang = math.radians(r.uniform(-75, -55))
            if r.random() < 0.5:
                ang = math.pi - ang
            b.vx, b.vy = math.cos(ang) * b.speed * 1.3, math.sin(ang) * b.speed * 1.3
            b.turn_in = r.uniform(0.6, 0.9)
            return True
        return False

    def _end_round(self):
        if self.hits < self.needed():
            self.over = True
            self.events.append(("game_over", self.hits))
            return
        perfect = self.hits == BIRDS_PER_ROUND
        if perfect:
            self.score += PERFECT_BONUS
        self.events.append(("round_clear", self.round, perfect))
        self.round_result = "perfect" if perfect else "clear"
        self.round += 1
        self.round_hits = []
        self.penalty = 0
        self.intro = ROUND_INTRO_S + 0.6
        self.next_volley_in = self.intro
