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
SPEED_START = 8.5                 # U / s horizontal scroll speed
SPEED_MAX = 12.5
SPEED_RAMP_PER_UNIT = 0.004       # speed gained per U travelled
SPIN_DEG_PER_SEC = 400            # cube rotation while airborne
CEILING_THICKNESS = 2.0           # hatched overhead slabs
PIT_DEATH_DEPTH = 1.0             # falling this far below ground = dead

# Hitboxes
SPIKE_HITBOX_SHRINK = 0.30        # fraction trimmed from each side of a spike
PLAYER_HITBOX_SHRINK = 0.08       # forgiving player hitbox vs spikes
ORB_REACH = 1.1                   # player-center to orb-center distance to use it

# Level generation
FIRST_OBSTACLE_AT = 18.0          # U ahead of player at start
DIFFICULTY_FULL_AT = 500.0        # distance at which difficulty reaches 1.0
GAP_START = 9.0                   # U of empty runway between patterns
GAP_MIN = 5.5
GAP_LANDING_ROOM = 1.5            # extra runway beyond one full jump (see World.min_gap_at)
GAP_SHRINK_PER_UNIT = 0.006
SPAWN_AHEAD = 40.0                # generate this many U past the screen edge
NO_REPEAT_WINDOW = 3              # don't reuse any of the last N patterns
NEW_PATTERN_WEIGHT = 3.0          # recently unlocked patterns are this much likelier...
NEW_PATTERN_WEIGHT_FROM = 0.3      # ...but only once difficulty reaches this

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
