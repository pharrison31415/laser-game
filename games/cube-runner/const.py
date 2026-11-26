# All distances are in "units" (U), where 1 U = the player's cube size.
# U is derived from screen height so the game scales with resolution.
UNIT_RATIO = 0.06                 # U = screen_h * UNIT_RATIO
GROUND_Y_RATIO = 0.80             # ground line as fraction of screen height
PLAYER_X_RATIO = 0.22             # player's fixed screen x (fraction of width)

# Physics (U, seconds)
GRAVITY = 62.0                    # U / s^2
JUMP_VELOCITY = 18.0              # U / s  -> apex ~2.6 U, air time ~0.58 s
PAD_VELOCITY = 25.0               # jump pads: apex ~5 U
ORB_VELOCITY = 17.0               # mid-air orbs
MAX_FALL_SPEED = 30.0             # U / s
SPEED_START = 9.5                 # U / s horizontal scroll speed
DRAW_SPEED = 8.5                  # drawn sections are drawn for this speed (stretched to the real one)
SPEED_MAX = 15.0
SPEED_RAMP_PER_UNIT = 0.006       # speed gained per U travelled
SPIN_DEG_PER_SEC = 400            # cube rotation while airborne
CEILING_THICKNESS = 2.0           # hatched overhead slabs
PIT_DEATH_DEPTH = 1.0             # falling this far below ground = dead

# Ship mode (variant "ship"): portals turn the cube into a ship that climbs
# while the laser is held and sinks when it's released.
SHIP_LIFT = 42.0                  # U / s^2 upward while held
SHIP_GRAVITY = 38.0               # U / s^2 downward while released
SHIP_MAX_VY = 9.0                 # U / s, either direction
SHIP_CEILING_Y = 10.0             # hard flight ceiling (safe to bump), y of the ship's top
PORTAL_HEIGHT = 5.0               # default gate height when drawn as a single character

# Hitboxes
SPIKE_HITBOX_SHRINK = 0.30        # fraction trimmed from each side of a spike
PLAYER_HITBOX_SHRINK = 0.08       # forgiving player hitbox vs spikes
ORB_REACH = 1.1                   # player-center to orb-center distance to use it

# Level generation
FIRST_OBSTACLE_AT = 18.0          # U ahead of player at start
DIFFICULTY_FULL_AT = 350.0        # distance at which difficulty reaches 1.0
GAP_MIN = 5.5
GAP_LANDING_ROOM = 1.5            # extra runway beyond one full jump (see World.min_gap_at)
SPAWN_AHEAD = 40.0                # generate this many U past the screen edge
NO_REPEAT_WINDOW = 3              # don't reuse any of the last N sections
NEW_PATTERN_WEIGHT = 3.0          # recently unlocked sections are this much likelier...
NEW_PATTERN_WEIGHT_FROM = 0.3      # ...but only once difficulty reaches this
SECTION_BREATHER = 2.0            # extra empty runway between sections

# Flow
DEATH_RESTART_DELAY_MS = 900      # ignore input briefly after crashing
HOLD_TO_START_MS = 400            # hold laser this long to start

# Colors -- kept minimal (grays + one green accent, no reds) so nothing on
# screen competes with the red laser dot for the camera.
FG = (230, 230, 230)              # outlines, spikes, text
DIM = (170, 170, 170)             # secondary text, used orbs, meters
BG = (12, 14, 18)                 # engine background (also shows through pits)
SOLID_FILL = (52, 56, 66)         # block / spike / ground fill: must read vs. BG on a projector
GROUND_SEAM = (66, 70, 82)
HATCH = (90, 94, 106)             # diagonal hatching on ceilings
ACCENT = (50, 200, 120)           # player and helpers (pads, orbs)
ACCENT_DARK = (20, 80, 50)

# Gravity flip (CUBE_VARIANT=gravity): portals and flip orbs turn gravity upside down
FLIP_TOP_DEATH = 13.0             # flying above this height (off the top of the screen) = dead
FLIP_PORTAL_DAMP = 0.5            # vertical speed kept when passing a gravity portal

# Variable-height jump (CUBE_VARIANT=hold): a tap hops, holding jumps higher.
# Presses up to HOLD_GRACE_S all give the same hop, so a laser flick (~4 frames
# of camera latency) is still a clean tap.
HOLD_VARIANT_GRAVITY = 70.0       # replaces GRAVITY in the hold variant
HOLD_JUMP_VELOCITY = 14.0         # tap: apex ~1.4 U
HOLD_GRACE_S = 4 / 60             # holding counts only after this long...
HOLD_GRAVITY = 5.0                # ...then gravity is this weak while held and rising...
MAX_HOLD_S = 0.21                 # ...until this: a full hold peaks at ~2.6 U (the normal jump)
HOLD_JUMP_BUFFER_S = 0.10        # every jump needs a fresh press; this early still counts
HOLD_PAD_VELOCITY = 26.6          # pads / orbs reach the same heights as normal under the
HOLD_ORB_VELOCITY = 18.1          # stronger gravity

# Coins (CUBE_VARIANT=coins): optional pickups placed off the safe line
COIN_REACH = 0.85                 # player-center to coin-center distance to collect it
COIN_POINTS = 10                  # per coin, times the combo multiplier
COMBO_MAX = 5                     # multiplier = consecutive coins without missing one, capped
COIN_SPACING = 6.0                # auto-placed coins are at least this far apart

# TEMPORARY experiment switch: CUBE_VARIANT=ship,gravity,... (comma-separated)
import os as _os
VARIANTS = set(v.strip() for v in _os.environ.get("CUBE_VARIANT", "").split(",") if v.strip())
