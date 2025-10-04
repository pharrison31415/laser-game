# -----------------------------
# Configuration (tweak as needed)
# -----------------------------

SCREEN_W, SCREEN_H = 1280, 720     # PyGame window (projected) size
CAM_INDEX = 0                      # Webcam index
CAM_WIDTH, CAM_HEIGHT = 1280, 720  # Request these from the camera (best effort)

# Preview box (in-window live camera view)
PREVIEW_W = 360
PREVIEW_H = int(PREVIEW_W * 9 / 16)  # keep 16:9 by default
PREVIEW_MARGIN = 12
PREVIEW_POS = (SCREEN_W - PREVIEW_W - PREVIEW_MARGIN, PREVIEW_MARGIN)

# Red laser HSV thresholds (works for many cheap red lasers; adjust as needed)
# Note: red wraps around the hue wheel, so we use two ranges and OR them.
LOW1 = (0, 120, 180)
HIGH1 = (8, 255, 255)
LOW2 = (170, 120, 180)
HIGH2 = (180, 255, 255)

# Minimum area (in pixels) for a blob to be considered a laser dot
MIN_BLOB_AREA = 8

# Debounce: only trigger a new explosion if the last detected dot moved this many pixels or after cooldown
TRIGGER_MOVE_THRESHOLD = 8
TRIGGER_COOLDOWN_SEC = 0.06
