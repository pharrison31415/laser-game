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
DEBRIS_SLOWDOWN = 0.7            # being hit by / running into fallen debris
DEBRIS_GRAVITY = 40.0
HARD_LANDING_VY = -24.0          # landing faster than this makes you stumble...
HARD_LANDING_SLOWDOWN = 0.9      # ...and lose some speed
STUMBLE_S = 0.35
WINDOW_CEILING = 5.0             # window buildings: ceiling height above the floor inside
CRUMBLE_DELAY_S = 0.25           # crumbling buildings start sinking this long after you land
CRUMBLE_ACCEL = 3.0              # U/s^2 sink acceleration
CRUMBLE_DROP_BUDGET = 3.0        # generator assumes the roof may have sunk this far when you leave
GIRDER_THICKNESS = 0.6
FALL_DEATH_Y = -6.0

# Generation
FIRST_BUILDING_W = 60.0
GAP_MIN = 1.5
GAP_SAFETY = 0.8                 # gaps use at most this fraction of a full-hold jump
STEP_UP_MAX = 2.2                # max roof rise (full-hold apex is ~3.8)
STEP_DOWN_MAX = 7.0
TOP_MIN, TOP_MAX = 2.0, 16.0
SPAWN_AHEAD = 140.0              # build this far past the runner (camera zooms out a lot)
# distance (U) at which each building type / hazard starts appearing
UNLOCK = {
    "crates": 120,
    "window": 350,
    "girder": 650,
    "crumble": 950,
    "debris": 1300,
}

# Flow
DEATH_RESTART_DELAY_MS = 900
HOLD_TO_START_MS = 400

# Colours: grays + one accent so nothing competes with the red laser dot
# runner flip book: run-cycle stills per second = BASE + PER_SPEED * speed, capped
RUN_FPS_BASE = 3.0
RUN_FPS_PER_SPEED = 0.55
RUN_FPS_MAX = 13.0

FG = (230, 230, 230)
DIM = (150, 150, 150)
BG = (12, 14, 18)
SKY_FAR = (17, 19, 24)           # parallax skyline layers (barely above BG)
SKY_NEAR = (22, 25, 31)
BUILDING_FILL = (46, 50, 60)
FACADE_LINE = (60, 64, 76)       # window grid on facades
INTERIOR = (32, 36, 45)           # inside a window building
GLASS = (110, 130, 140)
ACCENT = (50, 200, 120)          # the runner
