# Start screen
START_TARGET_RADIUS = 70           # px for the "shoot here" target
HOLD_TO_START_MS = 1000            # how long the laser must stay on the target

# Gameplay difficulty
START_RADIUS = 90                  # initial mole radius (px)
START_DURATION_SEC = 3.0           # initial mole lifetime (seconds)

RADIUS_DECAY_PER_STAGE = 0.75      # radius multiplier per stage
DURATION_DECAY_PER_STAGE = 0.75    # lifetime multiplier per stage

MIN_RADIUS = 14                    # px
MIN_DURATION_SEC = 0.25            # seconds

TARGETS_PER_STAGE = 6              # moles per stage (hit or miss)

# UX
EDGE_MARGIN = 24                   # keep targets off the edges

HIT_POP_DELAY_MS = 1500            # delay before next mole after hit/miss

HUD_COLOR = (230, 230, 230)
MOLE_COLOR = (50, 200, 120)
START_TARGET_COLOR = (70, 180, 110)
START_RING_COLOR = (235, 235, 235)