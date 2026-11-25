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
    # stride contact: near leg reaching forward, far leg pushing off behind
    "run_a": dict(hip=(0.0, 0.78), neck=(0.20, 1.23), head=(0.29, 1.40),
                  n_knee=(0.24, 0.46), n_foot=(0.36, 0.05),
                  f_knee=(-0.13, 0.44), f_foot=(-0.40, 0.20),
                  n_elbow=(-0.13, 1.02), n_hand=(-0.03, 0.84),
                  f_elbow=(0.30, 1.04), f_hand=(0.40, 1.22)),
    # passing: near knee driving up, far leg under the body
    "run_b": dict(hip=(0.0, 0.83), neck=(0.21, 1.28), head=(0.30, 1.45),
                  n_knee=(0.32, 0.64), n_foot=(0.12, 0.33),
                  f_knee=(0.05, 0.44), f_foot=(-0.02, 0.03),
                  n_elbow=(-0.02, 1.01), n_hand=(0.13, 0.93),
                  f_elbow=(0.10, 1.02), f_hand=(0.24, 1.08)),
    # rising: knees tucked, one arm thrown forward
    "jump": dict(hip=(0.0, 0.86), neck=(0.15, 1.31), head=(0.23, 1.49),
                 n_knee=(0.34, 0.78), n_foot=(0.20, 0.44),
                 f_knee=(0.06, 0.54), f_foot=(-0.26, 0.50),
                 n_elbow=(0.33, 1.20), n_hand=(0.46, 1.40),
                 f_elbow=(-0.15, 1.14), f_hand=(-0.32, 1.30)),
    # falling: legs reaching for the next roof, arms up for balance
    "fall": dict(hip=(0.0, 0.80), neck=(0.10, 1.27), head=(0.17, 1.45),
                 n_knee=(0.26, 0.48), n_foot=(0.40, 0.14),
                 f_knee=(0.08, 0.42), f_foot=(0.02, 0.06),
                 n_elbow=(0.22, 1.36), n_hand=(0.28, 1.56),
                 f_elbow=(-0.12, 1.35), f_hand=(-0.22, 1.52)),
    # stumble: pitched forward, arms flung out
    "stumble": dict(hip=(0.0, 0.72), neck=(0.38, 1.08), head=(0.51, 1.21),
                    n_knee=(0.20, 0.40), n_foot=(0.10, 0.03),
                    f_knee=(-0.16, 0.38), f_foot=(-0.36, 0.12),
                    n_elbow=(0.50, 0.92), n_hand=(0.64, 0.78),
                    f_elbow=(0.22, 1.16), f_hand=(0.32, 1.36)),
}


def _swap_sides(j: Dict[str, Vec]) -> Dict[str, Vec]:
    out = dict(j)
    for part in ("knee", "foot", "elbow", "hand"):
        out["n_" + part], out["f_" + part] = j["f_" + part], j["n_" + part]
    return out


# the other half of the stride: same shapes with the legs and arms swapped
POSES["run_c"] = _swap_sides(POSES["run_a"])
POSES["run_d"] = _swap_sides(POSES["run_b"])
RUN_CYCLE = ["run_a", "run_b", "run_c", "run_d"]


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


FACETS = {name: build_pose(j) for name, j in POSES.items()}


def draw(surface, pygame, pose: str, foot_x: float, foot_y: float, ppu: float):
    """Draw a pose with its feet at screen (foot_x, foot_y), ppu pixels per world unit."""
    for pts, color in FACETS[pose]:
        pygame.draw.polygon(surface, color,
                            [(foot_x + x * ppu, foot_y - y * ppu) for x, y in pts])
