"""
The runner, drawn as low-poly cubist stills: a handful of fixed poses, each made
of flat-shaded facets, swapped between (never interpolated), like a flip book.

A pose is a skeleton of joints in world units, feet at y = 0, facing +x. Each
bone becomes a quad split into two triangles of different shades, the torso and
head become a few facets, and limbs on the far side are drawn darker, behind
the body. The facets are built once per pose; drawing is just a transform.
"""
import math
from typing import Dict, List, Tuple

Vec = Tuple[float, float]

# shades of the accent green, light -> dark
LIGHT = (120, 235, 170)
MID = (50, 200, 120)
SHADE = (32, 150, 92)
DARK = (22, 104, 66)
FAR_A = (20, 96, 62)        # far-side limbs (behind the body)
FAR_B = (13, 66, 43)

# (pose name) -> joints. hip/neck/head are shared; "n_" = near side, "f_" = far side.
POSES: Dict[str, Dict[str, Vec]] = {
    # support: far foot planted under the hip; near heel whipped up under the
    # glutes as its knee swings through; arms passing with elbows bent
    "run_a": dict(hip=(0.0, 0.77), neck=(0.29, 1.17), head=(0.41, 1.32),
                  f_knee=(0.10, 0.40), f_foot=(0.00, 0.03),
                  n_knee=(0.16, 0.42), n_foot=(-0.22, 0.58),
                  n_elbow=(-0.14, 1.04), n_hand=(-0.20, 0.82),
                  f_elbow=(0.42, 0.96), f_hand=(0.58, 1.14)),
    # drive: near leg fully extended behind, toe pushing off; far knee punched
    # up to hip height; near arm back, far arm thrown forward
    "run_b": dict(hip=(0.0, 0.78), neck=(0.30, 1.19), head=(0.42, 1.34),
                  n_knee=(-0.20, 0.42), n_foot=(-0.43, 0.04),
                  f_knee=(0.38, 0.68), f_foot=(0.26, 0.28),
                  n_elbow=(-0.06, 1.06), n_hand=(-0.18, 0.86),
                  f_elbow=(0.46, 0.98), f_hand=(0.60, 1.20)),
    # flight: both feet off the roof, legs scissored wide: far shin reaching
    # for the next step, near leg trailing with the heel kicked high
    "run_c": dict(hip=(0.0, 0.86), neck=(0.29, 1.27), head=(0.41, 1.42),
                  f_knee=(0.32, 0.58), f_foot=(0.42, 0.16),
                  n_knee=(-0.22, 0.52), n_foot=(-0.50, 0.78),
                  n_elbow=(-0.04, 1.12), n_hand=(-0.20, 0.94),
                  f_elbow=(0.44, 1.06), f_hand=(0.60, 1.24)),
    # rising: a long explosive leap, lead knee high, trail leg stretched back,
    # one arm punched up at the far roof, the other swung back
    "jump": dict(hip=(0.0, 0.90), neck=(0.24, 1.35), head=(0.35, 1.51),
                 n_knee=(0.40, 0.84), n_foot=(0.36, 0.44),
                 f_knee=(-0.24, 0.62), f_foot=(-0.54, 0.36),
                 n_elbow=(0.42, 1.40), n_hand=(0.62, 1.58),
                 f_elbow=(-0.04, 1.16), f_hand=(-0.28, 1.20)),
    # falling: bracing to land: legs reaching ahead for the roof, torso
    # sitting back, arms thrown wide and high for balance
    "fall": dict(hip=(0.0, 0.82), neck=(0.05, 1.30), head=(0.10, 1.48),
                 n_knee=(0.32, 0.56), n_foot=(0.50, 0.20),
                 f_knee=(0.18, 0.44), f_foot=(0.24, 0.06),
                 n_elbow=(0.32, 1.42), n_hand=(0.52, 1.58),
                 f_elbow=(-0.20, 1.38), f_hand=(-0.38, 1.56)),
    # stumble: pitched hard forward, one foot scrambling underneath, the other
    # leg kicked up behind, one arm grabbing at the roof, one wheeling back
    "stumble": dict(hip=(0.0, 0.70), neck=(0.42, 1.00), head=(0.58, 1.08),
                    n_knee=(0.24, 0.36), n_foot=(0.22, 0.02),
                    f_knee=(-0.24, 0.56), f_foot=(-0.54, 0.74),
                    n_elbow=(0.58, 0.82), n_hand=(0.74, 0.66),
                    f_elbow=(0.20, 1.20), f_hand=(0.02, 1.38)),
}


def _swap_sides(j: Dict[str, Vec]) -> Dict[str, Vec]:
    out = dict(j)
    for part in ("knee", "foot", "elbow", "hand"):
        out["n_" + part], out["f_" + part] = j["f_" + part], j["n_" + part]
    return out


# the other half of the stride: same shapes with the legs and arms swapped
POSES["run_d"] = _swap_sides(POSES["run_a"])
POSES["run_e"] = _swap_sides(POSES["run_b"])
POSES["run_f"] = _swap_sides(POSES["run_c"])
RUN_CYCLE = ["run_a", "run_b", "run_c", "run_d", "run_e", "run_f"]


# -- building facets ---------------------------------------------------------------

def _bone(a: Vec, b: Vec, wa: float, wb: float, light, dark) -> List[tuple]:
    """A tapered quad from a to b, overlapping past both joints so bent knees and
    elbows don't show a gap, split along its diagonal into two shades."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    a = (a[0] - ux * wa * 0.35, a[1] - uy * wa * 0.35)
    b = (b[0] + ux * wb * 0.35, b[1] + uy * wb * 0.35)
    a1 = (a[0] + px * wa / 2, a[1] + py * wa / 2)
    a2 = (a[0] - px * wa / 2, a[1] - py * wa / 2)
    b1 = (b[0] + px * wb / 2, b[1] + py * wb / 2)
    b2 = (b[0] - px * wb / 2, b[1] - py * wb / 2)
    return [([a1, b1, b2], light), ([a1, b2, a2], dark)]


def _foot(ankle: Vec, knee: Vec, light, dark) -> List[tuple]:
    """A wedge shoe pointing forward, tilted a little with the shin."""
    tilt = max(-0.5, min(0.5, (ankle[0] - knee[0]) * 1.2))
    c, s = math.cos(tilt), math.sin(tilt)

    def rot(x, y):
        return (ankle[0] + x * c - y * s, ankle[1] + x * s + y * c)
    heel, toe, top = rot(-0.07, -0.03), rot(0.20, -0.03), rot(0.0, 0.08)
    return [([heel, toe, top], light), ([heel, top, rot(-0.06, 0.05)], dark)]


def _leg(j, side, light, dark):
    hip, knee, foot = j["hip"], j[side + "knee"], j[side + "foot"]
    return (_bone(hip, knee, 0.22, 0.15, light, dark)
            + _bone(knee, foot, 0.15, 0.11, dark, light)
            + _foot(foot, knee, light, dark))


def _arm(j, side, light, dark):
    sh = (j["neck"][0] - 0.03, j["neck"][1] - 0.07)
    elbow, hand = j[side + "elbow"], j[side + "hand"]
    return (_bone(sh, elbow, 0.13, 0.11, light, dark)
            + _bone(elbow, hand, 0.11, 0.09, dark, light))


def _torso(j) -> List[tuple]:
    hip, neck = j["hip"], j["neck"]
    dx, dy = neck[0] - hip[0], neck[1] - hip[1]
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    px, py = -uy, ux          # points backwards (to -x) for an upright body

    def at(t, w):             # t along the spine, w across it (+ = back)
        return (hip[0] + ux * n * t + px * w, hip[1] + uy * n * t + py * w)
    back_sh, front_sh = at(1.05, 0.15), at(1.0, -0.17)
    chest = at(0.62, -0.20)
    front_hip, back_hip = at(-0.05, -0.12), at(-0.02, 0.14)
    mid_back = at(0.55, 0.17)
    return [
        ([back_sh, front_sh, chest], LIGHT),            # shoulders, catching the light
        ([back_sh, chest, mid_back], MID),
        ([mid_back, chest, front_hip], SHADE),          # belly
        ([mid_back, front_hip, back_hip], DARK),        # lower back
    ]


def _head(j) -> List[tuple]:
    cx, cy = j["head"]
    r = 0.17
    pts = [(cx + r * 1.05 * math.cos(a), cy + r * math.sin(a))
           for a in (math.radians(d) for d in (-80, -20, 35, 95, 150, 215))]
    neck = (j["neck"][0] + 0.02, j["neck"][1] - 0.02)
    c = (cx + 0.02, cy + 0.01)
    return [
        ([neck, pts[0], pts[5]], DARK),                 # neck / jaw
        ([c, pts[0], pts[1]], MID),                     # face
        ([c, pts[1], pts[2]], LIGHT),                   # brow, lit from the front
        ([c, pts[2], pts[3]], LIGHT),
        ([c, pts[3], pts[4]], MID),                     # crown
        ([c, pts[4], pts[5]], SHADE),                   # back of the head
        ([c, pts[5], pts[0]], DARK),
    ]


def build_pose(j: Dict[str, Vec]) -> List[tuple]:
    """Facets of a pose, back to front: [(points, color), ...]."""
    return (_arm(j, "f_", FAR_A, FAR_B) + _leg(j, "f_", FAR_A, FAR_B)
            + _torso(j) + _head(j)
            + _leg(j, "n_", MID, SHADE) + _arm(j, "n_", LIGHT, MID))


# -- landing roll ------------------------------------------------------------------
# A forward shoulder roll after a hard landing: absorb, two tumbling stills of
# the same tucked ball turned forward about its middle, then up into the sprint.
POSES["roll_1"] = dict(   # impact: deep crouch, torso diving, arms reaching for the roof
    hip=(-0.08, 0.40), neck=(0.32, 0.70), head=(0.47, 0.66),
    n_knee=(0.30, 0.46), n_foot=(0.16, 0.05),
    f_knee=(0.12, 0.12), f_foot=(-0.28, 0.07),
    n_elbow=(0.50, 0.46), n_hand=(0.66, 0.28),
    f_elbow=(0.48, 0.52), f_hand=(0.68, 0.38))
POSES["roll_4"] = dict(   # up out of the roll: back foot planted and driving, low lean
    hip=(0.0, 0.66), neck=(0.34, 1.02), head=(0.48, 1.12),
    n_knee=(-0.04, 0.30), n_foot=(-0.30, 0.05),
    f_knee=(0.36, 0.64), f_foot=(0.20, 0.30),
    n_elbow=(0.50, 0.86), n_hand=(0.62, 1.06),
    f_elbow=(0.06, 0.88), f_hand=(-0.06, 0.68))
_TUCK = dict(             # tucked ball about (0, 0): back rounded, chin down, shins out, one arm out
    hip=(-0.14, -0.14), neck=(0.06, 0.24), head=(0.26, 0.26),
    n_knee=(0.30, -0.14), n_foot=(0.10, -0.46),
    f_knee=(0.24, -0.06), f_foot=(0.00, -0.34),
    n_elbow=(0.16, 0.02), n_hand=(0.36, -0.12),
    f_elbow=(-0.12, 0.08), f_hand=(-0.28, -0.08))


def _rolled(j: Dict[str, Vec], deg: float, x: float) -> Dict[str, Vec]:
    """j turned by deg (negative = forward) about (0, 0), set down on the roof at x."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    out = {k: (vx * c - vy * s + x, vx * s + vy * c) for k, (vx, vy) in j.items()}
    low = min(p[1] for pts, _ in build_pose(out) for p in pts)
    return {k: (vx, vy - low) for k, (vx, vy) in out.items()}


POSES["roll_2"] = _rolled(_TUCK, -140, 0.10)
POSES["roll_3"] = _rolled(_TUCK, -235, 0.10)
ROLL_CYCLE = ["roll_1", "roll_2", "roll_3", "roll_4"]

FACETS = {name: build_pose(j) for name, j in POSES.items()}


def draw(surface, pygame, pose: str, foot_x: float, foot_y: float, ppu: float):
    """Draw a pose with its feet at screen (foot_x, foot_y), ppu pixels per world unit."""
    for pts, color in FACETS[pose]:
        pygame.draw.polygon(surface, color,
                            [(foot_x + x * ppu, foot_y - y * ppu) for x, y in pts])
