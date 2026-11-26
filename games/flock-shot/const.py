# Units: the screen is 10 U tall (1 U = screen_h / 10 px); x runs 0..WIDTH_U, y is up.
SCREEN_U = 10.0
GROUND_Y = 2.2                   # top of the grass; birds take off from just below it
TOP_ESCAPE_Y = 10.8              # a bird above this has got away

# Birds
BIRD_R = 0.55                    # body radius (drawing)
HIT_R = 0.85                     # a shot this close to a bird's centre hits it (laser aim is rough)
SIZE_PER_ROUND = 0.955            # birds (and their hit circle) shrink this much each round...
SIZE_MIN = 0.5                    # ...down to this fraction
BIRD_SPEED = 3.4                 # U/s in round 1...
SPEED_PER_ROUND = 1.12           # ...times this each round...
SPEED_MAX = 8.5                  # ...up to this
FLY_TIME_S = 6.0                 # seconds in the air before a bird flies off (round 1)...
FLY_TIME_PER_ROUND = 0.9         # ...times this each round...
FLY_TIME_MIN = 2.6
TURN_EVERY_S = (0.5, 1.1)        # birds change heading this often (round 1)...
TURN_PER_ROUND = 0.94            # ...times this each round (twitchier birds)
TURN_MIN_S = 0.22
ESCAPE_SPEEDUP = 1.4             # flying off is faster
FALL_GRAVITY = 14.0              # a hit bird drops

# Rounds
BIRDS_PER_ROUND = 10
SHOTS_PER_VOLLEY = 3             # shells for each release of birds
VOLLEY_GAP_S = 0.9               # pause between releases
TWO_BIRDS_FROM_ROUND = 3         # from this round, birds come in pairs
POINTS_PER_HIT = 100             # + POINTS_ROUND_BONUS * (round - 1)
POINTS_ROUND_BONUS = 50
PERFECT_BONUS = 1000

# Flow
HOLD_TO_START_MS = 400
ROUND_INTRO_S = 1.6
GAME_OVER_DELAY_MS = 1200
PRESS_RADIUS = 0.15              # fraction of screen height: a dot with none this close in the
                                 # previous frame is a new shot (sweeping a held dot doesn't fire)

# Colours: grays + one accent so nothing competes with the red laser dot
FG = (230, 230, 230)
DIM = (150, 150, 150)
FAINT = (70, 74, 84)
BG = (12, 14, 18)
SKY_TOP = (10, 11, 15)
SKY_LOW = (30, 33, 41)
HILL_FAR = (24, 27, 34)
HILL_NEAR = (31, 34, 42)
TREE = (19, 21, 27)
GRASS = (40, 44, 54)
GRASS_DARK = (33, 36, 45)
GRASS_BLADE = (52, 56, 67)
BIRD_LIGHT = (225, 227, 232)     # low-poly bird facets, light to dark
BIRD_MID = (178, 181, 189)
BIRD_DARK = (118, 121, 130)
BIRD_BEAK = (90, 93, 102)
ACCENT = (50, 200, 120)

# Later rounds
RAMP_FROM = 1                    # after this round, difficulty climbs faster:
RAMP_EXTRA = 0.9                 # each round counts as 1 + this rounds of speed/size/turns/time
DECOY_FROM = 3                   # decoys: dark birds you must not shoot; hitting one takes
DECOY_CHANCE = 0.45              # a hit back and costs points. Chance per flight...
DECOY_CHANCE_PER_ROUND = 0.05    # ...plus this each round after DECOY_FROM
DECOY_PENALTY = 200
MOVES_FROM = 2                   # birds get flight styles: zig-zag, stop-and-dash, grass-skimming swoops
MOVES_PER_ROUND = 0.12           # chance a bird gets a style: this * (round - MOVES_FROM + 1)...
MOVES_MAX = 0.8                  # ...up to this
