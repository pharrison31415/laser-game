import math
# Units: 1 U ~ 1 metre. The runner is RUNNER_W x RUNNER_H. y is up; roofs sit at
# heights of a few U up to ~16 U; falling below FALL_DEATH_Y is a fall to the street.

# Screen
BASE_UNIT_RATIO = 0.055          # px per U = screen_h * this * zoom
RUNNER_X_RATIO = 0.24            # runner's screen x (fraction of width)
ROOF_Y_RATIO = 0.62              # the roof you're on sits this far down the screen
ZOOM_START = 1.0                 # camera zoom at the starting speed...
ZOOM_MAX_SPEED = 0.6             # ...and at top speed (zoomed out to see further ahead)

# Runner
RUNNER_W = 0.8
RUNNER_H = 1.6

# Speed (U/s): you start at a jog and never stop accelerating (up to a cap)
SPEED_START = 9.0
SPEED_MAX = 26.0
ACCEL = 0.45                     # U/s^2 -> top speed after ~40 s of clean running
SPEED_FLOOR = 8.0                # obstacles can't slow you below this

# Jumping: hold to jump higher
GRAVITY = 70.0
JUMP_VELOCITY = 15.0             # tap: apex ~1.6 U
HOLD_GRAVITY = 25.0              # gravity while the jump is held and rising...
MAX_HOLD_S = 0.30                # ...for at most this long: full hold apex ~3.8 U
MAX_FALL_SPEED = 40.0
COYOTE_S = 0.10                  # you can still jump this long after running off an edge
JUMP_BUFFER_S = 0.12             # a press this long before landing still jumps

# Hazards
CRATE_SIZE = 0.8
CRATE_SLOWDOWN = 0.8             # speed multiplier when you smash a crate
DEBRIS_SIZE = 1.3
DEBRIS_GRAVITY = 150.0
DEBRIS_DROP_VY = -22.0           # it's slammed down, not just dropped
DEBRIS_LEAD_S = 1.15             # starts falling when you're this many seconds of running away
HARD_LANDING_VY = -24.0          # landing faster than this makes you stumble...
HARD_LANDING_SLOWDOWN = 0.9      # ...and lose some speed
STUMBLE_S = 0.35
WINDOW_CEILING = 5.0             # window buildings: ceiling height above the floor inside
CRUMBLE_DELAY_S = 0.12           # crumbling buildings start sinking this long after you land
CRUMBLE_ACCEL = 18.0             # U/s^2 sink acceleration...
CRUMBLE_MAX_SINK = 9.0           # ...up to this sink speed (U/s)
CRUMBLE_S_MIN = 1.0              # crumbling roofs are this many seconds of running long...
CRUMBLE_S_MAX = 3.0              # ...at most
CRUMBLE_SLACK_S = 0.1            # extra sink time the generator allows for
CRUMBLE_MIN_TOP = 1.0            # crumbling roofs only where there's room to sink
CRUMBLE_MAX_DEPTH = 8.0          # while you're on one it sinks at most this far by its far end
CRUMBLE_FLOOR = -1.0             # the roof after a crumbling one may be this low (lower than TOP_MIN)
CRUMBLE_MIN_RIDE_V = 3.5         # crumbling roofs are short enough to sink at least this fast (U/s)


def crumble_drop(t: float) -> float:
    """How far a crumbling roof has sunk t seconds after you land on it."""
    t = max(0.0, t - CRUMBLE_DELAY_S)
    ta = CRUMBLE_MAX_SINK / CRUMBLE_ACCEL
    if t < ta:
        return 0.5 * CRUMBLE_ACCEL * t * t
    return 0.5 * CRUMBLE_ACCEL * ta * ta + CRUMBLE_MAX_SINK * (t - ta)


def crumble_ride_cap(depth: float, t: float) -> float:
    """Sink speed limit so a crumbling roof sinks at most depth in t seconds after landing."""
    t = max(1e-3, t - CRUMBLE_DELAY_S)
    a = CRUMBLE_ACCEL
    if 0.5 * a * t * t <= depth:
        return CRUMBLE_MAX_SINK
    disc = max(0.0, a * a * t * t - 2 * a * depth)
    return max(0.5, min(CRUMBLE_MAX_SINK, a * t - math.sqrt(disc)))


def crumble_time_for_drop(drop: float) -> float:
    """Inverse of crumble_drop."""
    ta = CRUMBLE_MAX_SINK / CRUMBLE_ACCEL
    d_a = 0.5 * CRUMBLE_ACCEL * ta * ta
    if drop <= d_a:
        return CRUMBLE_DELAY_S + math.sqrt(2 * max(0.0, drop) / CRUMBLE_ACCEL)
    return CRUMBLE_DELAY_S + ta + (drop - d_a) / CRUMBLE_MAX_SINK
GIRDER_THICKNESS = 0.6
FALL_DEATH_Y = -6.0

# Generation
FIRST_BUILDING_W = 60.0
GAP_MIN = 1.5
GAP_SAFETY = 0.8                 # gaps use at most this fraction of a full-hold jump
STEP_UP_MAX = 2.2                # max roof rise (full-hold apex is ~3.8)
WINDOW_CLEARANCE = 0.4           # a window jump's apex stays this far under the wall above the glass
STEP_DOWN_MAX = 7.0
TOP_MIN, TOP_MAX = 2.0, 16.0
SPAWN_AHEAD = 140.0              # build this far past the runner (camera zooms out a lot)
# distance (U) at which each building type / hazard starts appearing
UNLOCK = {
    "crates": 120,
    "window": 350,
    "girder": 650,
    "crumble": 750,
    "debris": 100,
}

# Flow
DEATH_RESTART_DELAY_MS = 900
HOLD_TO_START_MS = 400

# Colours: grays + one accent so nothing competes with the red laser dot
# runner flip book: run-cycle stills per second = BASE + PER_SPEED * speed, capped
RUN_FPS_BASE = 4.5
RUN_FPS_PER_SPEED = 0.8
RUN_FPS_MAX = 19.0

FG = (230, 230, 230)
DIM = (150, 150, 150)
BG = (12, 14, 18)
SKY_FAR = (17, 19, 24)           # parallax skyline layers (barely above BG)
SKY_NEAR = (22, 25, 31)
BUILDING_FILL = (46, 50, 60)
FACADE_LINE = (60, 64, 76)       # window grid on facades
BUILDING_SHADE = (37, 40, 49)    # recesses, shadow lines, the shaded side of a building
BUILDING_LIGHT = (58, 62, 74)    # floor bands, sills, cornice coping
WINDOW_DARK = (30, 33, 41)
WINDOW_LIT_DIM = (62, 66, 76)
WINDOW_LIT = (80, 84, 94)
FIRE_ESCAPE = (28, 30, 37)
CLUTTER = (31, 34, 42)           # roof clutter silhouettes (behind the roof line)
CLUTTER_LINE = (42, 46, 56)
BEACON = (120, 122, 128)         # blinking mast light (gray, never red)
SKY_FAR_WIN = (24, 27, 33)       # skyline window speckle
SKY_NEAR_WIN = (32, 35, 43)
SKY_BEACON = (85, 87, 94)
INTERIOR = (32, 36, 45)           # inside a window building
GLASS = (110, 130, 140)
ACCENT = (50, 200, 120)          # the runner
ALIEN = (140, 225, 255)          # falling wreckage: outlined alien tech
ALIEN_DIM = (55, 100, 125)
