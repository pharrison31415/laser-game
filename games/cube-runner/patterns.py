"""
Obstacle pattern library.

Each pattern is a function (rng, difficulty) -> list of parts, registered with
the minimum difficulty (0..1) at which it can appear. A pattern whose geometry
depends on the scroll speed can also take a keyword v (U/s); every registered
pattern accepts v=, and it is passed on only to those that declare it. Patterns randomize their
own sizes so the same pattern plays differently each time.

Parts (all positions in units relative to the pattern start, y is up, 0 = ground):
    ("spike", dx, base)              spike pointing up, sitting on y=base
    ("hang",  dx, top)               spike pointing down, hanging from y=top
    ("block", dx, w, top, bottom)    solid rectangle (bottom=0 rests on ground;
                                     bottom<0 is a pillar rising out of a pit)
    ("ceiling", dx, w, bottom)       hatched overhead slab: jumping into it kills
    ("pit",   dx, w)                 hole in the ground
    ("pad",   dx, base)              jump pad: launches you high on contact
    ("orb",   dx, y)                 mid-air orb: laser while touching = extra jump
"""
import inspect
import math

from .const import GRAVITY, JUMP_VELOCITY, SPEED_START


PATTERNS = []  # list of (min_difficulty, name, fn)
PILLAR = -6.0   # bottom for pillars standing in pits


def step_w(r, d, base=5):
    """Width of a stair step / landing area: wider at higher speed."""
    return base + round(3 * d) + r.randint(0, 1)


def pattern(min_d):
    def deco(fn):
        wants_v = "v" in inspect.signature(fn).parameters

        def call(r, d, v=None):
            return fn(r, d, v=v) if wants_v else fn(r, d)
        call.__name__ = fn.__name__
        PATTERNS.append((min_d, fn.__name__, call))
        return call
    return deco


def S(dx, base=0.0): return ("spike", dx, base)
def H(dx, top): return ("hang", dx, top)
def B(dx, w, top, bottom=0.0): return ("block", dx, w, top, bottom)
def P(dx, w): return ("pit", dx, w)
def J(dx, base=0.0): return ("pad", dx, base)
def O(dx, y): return ("orb", dx, y)


def spikes(dx, n, base=0.0):
    return [S(dx + i, base) for i in range(n)]


def ceiling(dx, w, bottom=1.8):
    return ("ceiling", dx, w, bottom)


# --- basics ------------------------------------------------------------------

@pattern(0.00)
def single_spike(r, d):
    return [S(0)]


@pattern(0.00)
def low_block(r, d):
    return [B(0, r.randint(2, 4), 1)]


@pattern(0.05)
def small_pit(r, d):
    return [P(0, r.randint(2, 3))]


@pattern(0.08)
def double_spike(r, d):
    return spikes(0, 2)


@pattern(0.46)
def triple_spike(r, d):
    return spikes(0, 3)


@pattern(0.30)
def two_blocks(r, d):
    w1, w2, g = r.randint(2, 3), r.randint(2, 3), r.randint(5, 6) + round(2 * d)
    return [B(0, w1, 1), B(w1 + g, w2, 1)]


@pattern(0.28)
def pad_over_spikes(r, d):
    return [J(0)] + spikes(3, r.randint(3, 4))


@pattern(0.20)
def pad_over_pit(r, d):
    return [J(0), P(2, r.randint(3, 5))]


@pattern(0.36)
def stairs_two(r, d):
    w1, w2 = step_w(r, d), r.randint(2, 4)
    return [B(0, w1, 1), B(w1, w2, 2)]


@pattern(0.25)
def spaced_spikes(r, d):
    # spikes with landing room between them: rhythm jumps
    # gap grows with difficulty because jumps carry further at higher speed
    n = r.randint(2, 3)
    gap = r.randint(7, 8) + round(2 * d)
    return [S(i * gap) for i in range(n)]


# --- don't-jump patterns -----------------------------------------------------

@pattern(0.10)
def low_tunnel(r, d):
    # a ceiling you must run under -- jumping hits your head
    return [ceiling(0, r.randint(4, 7))]


@pattern(0.55)
def spiked_ceiling_over_platform(r, d):
    # high enough that jumping ONTO the platform is safe; jumping again on it is not
    w = r.randint(6, 8)
    top = 4.2
    return [B(0, w, 1), ceiling(1, w - 2, top)] + [H(1 + i, top) for i in range(w - 2)]


@pattern(0.60)
def tunnel_then_spike(r, d):
    w = r.randint(4, 6)
    return [ceiling(0, w), S(w + 2)]


@pattern(0.75)
def tunnel_spike_tunnel(r, d, v=None):
    # jump the spike between the tunnels and land before the second one: its
    # distance grows with the jump length at speed (9 at the starting speed)
    w = r.randint(3, 4)
    jump_len = (v or SPEED_START) * 2 * JUMP_VELOCITY / GRAVITY
    gap = max(9, 4 + math.ceil(jump_len))
    return [ceiling(0, w), S(w + 2), ceiling(w + gap, w)]


# --- pads --------------------------------------------------------------------

@pattern(0.13)
def pad_onto_wall(r, d):
    return [J(0), B(4, r.randint(3, 5), r.choice([3, 4]))]


@pattern(0.22)
def pad_to_floating_ledge(r, d, v=None):
    # the pad's arc flattens out with speed: at high speed the ledge must start
    # further away, or you hit its front face while still rising
    v = v or SPEED_START
    x = max(4, round(v * 0.4))
    w = r.randint(4, 6)
    return [J(0), B(x, w, 4.5, 3.5)] + spikes(x + 1, w - 1)


@pattern(0.70)
def pad_on_block(r, d):
    return [B(0, 4, 1), J(2, 1), P(5, 4), B(9, 3, 2)]


# --- blocks & platforms ------------------------------------------------------

@pattern(0.33)
def spike_then_block(r, d):
    return [S(0), B(3, r.randint(2, 4), 1)]


@pattern(0.40)
def platform_with_spike(r, d):
    sx = step_w(r, d, base=5)
    return [B(0, sx + r.randint(3, 5), 1), S(sx, 1)]


@pattern(0.50)
def stairs_three(r, d):
    w1, w2 = step_w(r, d), step_w(r, d)
    w3 = step_w(r, d, base=5)
    out = [B(0, w1, 1), B(w1, w2, 2), B(w1 + w2, w3, 3)]
    if r.random() < 0.5:
        out.append(S(w1 + w2 + w3 - 3, 3))
    return out


@pattern(0.43)
def floating_platform_over_spikes(r, d):
    w = r.randint(6, 8)
    return [B(0, w, 2, 1.5)] + spikes(1, w - 2)


@pattern(0.57)
def pyramid(r, d):
    w = step_w(r, d)
    return [B(i * w, w, h) for i, h in enumerate((1, 2, 3, 2, 1))]


@pattern(0.60)
def spike_gauntlet(r, d):
    return [B(0, 3, 1), S(3), S(4), B(5, 2, 1), S(7), B(8, 2, 1)]


@pattern(0.70)
def tower(r, d):
    w = step_w(r, d)
    top_w = 2 * w + 2
    return [B(0, w, 1), B(w, w, 2), B(2 * w, top_w, 3), S(2 * w + top_w // 2 + 1, 3)]


# --- pits --------------------------------------------------------------------

@pattern(0.38)
def pit_then_spike(r, d):
    return [P(0, 2), S(r.randint(5, 6))]


@pattern(0.48)
def stepping_stones(r, d):
    n = r.randint(2, 3)
    out = [P(0, 4 * n + 2)]
    for i in range(n):
        out.append(B(2 + 4 * i, 2, 1, PILLAR))
    return out


@pattern(0.52)
def triple_pit(r, d):
    w = r.randint(2, 3)
    sep = w + r.randint(5, 6)
    return [P(0, w), P(sep, w), P(2 * sep, w)]


@pattern(0.63)
def rising_pillars(r, d):
    return [P(0, 12), B(2, 2, 1, PILLAR), B(6, 2, 2, PILLAR), B(10, 2, 1, PILLAR)]


@pattern(0.65)
def block_over_pit_edge(r, d):
    return [B(0, 3, 1), P(3, 3), B(6, 3, 1)]


# --- orbs --------------------------------------------------------------------

@pattern(0.16)
def orb_over_wide_pit(r, d):
    return [P(0, r.randint(7, 8)), O(2, 2.0)]


@pattern(0.65)
def orb_spike_field(r, d):
    return spikes(0, 9) + [O(2, 2.0), O(6, 2.2)]


@pattern(0.72)
def orb_to_high_block(r, d):
    return spikes(0, 2) + [O(2, 2.0), B(5, r.randint(3, 5), 4)]


@pattern(0.80)
def orb_chain_over_pit(r, d):
    return [P(0, 14), O(2, 2.0), O(6, 2.2), O(10, 2.2)]
