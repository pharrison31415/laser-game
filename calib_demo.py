import sys
import time
import math
import numpy as np
import cv2
import pygame

# -----------------------------
# Configuration
# -----------------------------
SCREEN_W, SCREEN_H = 1280, 720
CAM_INDEX = 0
CAM_WIDTH, CAM_HEIGHT = 1280, 720

# Red thresholds
LOW1 = (0, 120, 180)
HIGH1 = (8, 255, 255)
LOW2 = (170, 120, 180)
HIGH2 = (180, 255, 255)

MIN_BLOB_AREA = 8
TRIGGER_MOVE_THRESHOLD = 8
TRIGGER_COOLDOWN_SEC = 0.06

# Auto-calibration
CALIB_DOT_RADIUS = 12
CALIB_BG_COLOR = (0, 0, 0)
CALIB_DOT_COLOR = (255, 0, 0)
CALIB_TEXT_COLOR = (240, 240, 240)
CALIB_STABLE_FRAMES = 6
CALIB_STABLE_PIXELS = 4
CALIB_TIMEOUT_SEC = 6.0
CALIB_SETTLE_MS = 250

# One and only webcam window
PREVIEW_WIN = "Webcam Preview"

# -----------------------------
# Effects
# -----------------------------
class Explosion:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.radius = 4
        self.max_radius = 80
        self.alpha = 255
        self.dead = False
    def update(self, dt):
        self.radius += 300 * dt / 1000.0
        self.alpha -= 500 * dt / 1000.0
        if self.radius >= self.max_radius or self.alpha <= 0:
            self.dead = True
    def draw(self, surf):
        r = int(max(2, self.radius))
        a = int(max(0, min(255, self.alpha)))
        for i in range(3):
            rr = max(1, r - i * 6)
            aa = max(0, a - i * 60)
            if aa <= 0: continue
            color = (255, 200, 0, aa)
            circle_surf = pygame.Surface((rr * 2 + 4, rr * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(circle_surf, color, (rr + 2, rr + 2), rr, width=2)
            surf.blit(circle_surf, (self.x - rr - 2, self.y - rr - 2))

# -----------------------------
# Vision
# -----------------------------
def find_red_laser_centroid_and_mask(frame_bgr):
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(cv2.inRange(hsv, LOW1, HIGH1), cv2.inRange(hsv, LOW2, HIGH2))
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts: return None, mask
    best = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(best) < MIN_BLOB_AREA: return None, mask
    M = cv2.moments(best)
    if M["m00"] <= 0: return None, mask
    cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
    return (cx, cy), mask

def draw_preview_frame(frame_bgr, mask, cam_pt, corners_cam=None, looking_for:str|None=None):
    """Return a BGR frame with overlays for the single preview window."""
    preview = frame_bgr.copy()
    if mask is not None:
        preview[mask > 0] = (0, 0, 255)  # paint thresholded pixels pure red
    if cam_pt is not None:
        cv2.circle(preview, cam_pt, 6, (255, 255, 0), -1)
    if corners_cam and len(corners_cam) == 4:
        labels = ("TL","TR","BR","BL")
        for i, (x, y) in enumerate(corners_cam):
            cv2.circle(preview, (int(x), int(y)), 6, (0, 255, 0), -1)
            cv2.putText(preview, labels[i], (int(x)+8, int(y)-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2, cv2.LINE_AA)
        for i in range(4):
            p1 = tuple(map(int, corners_cam[i]))
            p2 = tuple(map(int, corners_cam[(i+1)%4]))
            cv2.line(preview, p1, p2, (0, 200, 0), 2, cv2.LINE_AA)
    if looking_for:
        cv2.putText(preview, looking_for, (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    return preview

# -----------------------------
# Auto-calibration (uses the same PREVIEW_WIN)
# -----------------------------
def auto_calibrate(cap, screen, font, font_small, ensure_preview_visible, corners_out_holder):
    """
    Shows corner dots in the PyGame window, uses the single OpenCV PREVIEW_WIN
    for the webcam view. Returns (H, corners_cam) or (None, None) if aborted/fails.
    """
    # If preview is hidden, turn it on for calibration and remember to restore after
    restore_preview = False
    if ensure_preview_visible is not None and not ensure_preview_visible():
        cv2.namedWindow(PREVIEW_WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(PREVIEW_WIN, 640, 360)
        restore_preview = True

    corners_screen = [
        (0 + 20, 0 + 20),                          # TL
        (SCREEN_W - 20, 0 + 20),                   # TR
        (SCREEN_W - 20, SCREEN_H - 20),            # BR
        (0 + 20, SCREEN_H - 20)                    # BL
    ]
    labels = ["TL", "TR", "BR", "BL"]
    detected_cam = []

    cv2.namedWindow(PREVIEW_WIN, cv2.WINDOW_NORMAL)  # idempotent
    cv2.resizeWindow(PREVIEW_WIN, 640, 360)

    for idx, (sx, sy) in enumerate(corners_screen):
        stable_count = 0
        last_xy = None
        start_time = time.time()
        pygame.time.delay(CALIB_SETTLE_MS)

        while True:
            # Draw calibration dots (no overlay on them)
            screen.fill(CALIB_BG_COLOR)
            msg = f"Auto-calibrating: {labels[idx]} ({idx+1}/4). Esc=abort"
            screen.blit(font.render(msg, True, CALIB_TEXT_COLOR), (16, 16))
            dim = (90, 0, 0)
            for j, (cx, cy) in enumerate(corners_screen):
                color = CALIB_DOT_COLOR if j == idx else dim
                pygame.draw.circle(screen, color, (int(cx), int(cy)), CALIB_DOT_RADIUS)
                screen.blit(font_small.render(labels[j], True, (200,200,200)), (int(cx)+14, int(cy)-14))
            pygame.display.flip()

            # Handle abort
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if restore_preview: 
                        try: cv2.destroyWindow(PREVIEW_WIN)
                        except: pass
                    return None, None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if restore_preview: 
                        try: cv2.destroyWindow(PREVIEW_WIN)
                        except: pass
                    return None, None

            ok, frame = cap.read()
            if not ok: 
                continue
            cam_pt, mask = find_red_laser_centroid_and_mask(frame)

            # Update the single preview window
            looking_for = f"Looking for {labels[idx]}..."
            prev = draw_preview_frame(frame, mask, cam_pt, None, looking_for)
            cv2.imshow(PREVIEW_WIN, prev)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                if restore_preview: 
                    try: cv2.destroyWindow(PREVIEW_WIN)
                    except: pass
                return None, None

            # Stability check
            if cam_pt is not None:
                if last_xy is None:
                    stable_count = 1
                else:
                    dx = cam_pt[0] - last_xy[0]; dy = cam_pt[1] - last_xy[1]
                    stable_count = stable_count + 1 if math.hypot(dx, dy) <= CALIB_STABLE_PIXELS else 1
                last_xy = cam_pt
                if stable_count >= CALIB_STABLE_FRAMES:
                    detected_cam.append(cam_pt); break

            # Timeout
            if (time.time() - start_time) > CALIB_TIMEOUT_SEC:
                print(f"Calibration timeout on {labels[idx]}.")
                if restore_preview: 
                    try: cv2.destroyWindow(PREVIEW_WIN)
                    except: pass
                return None, None

    src = np.array(detected_cam, dtype=np.float32)
    dst = np.array([[0,0],[SCREEN_W-1,0],[SCREEN_W-1,SCREEN_H-1],[0,SCREEN_H-1]], dtype=np.float32)
    H, _ = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)

    # Publish corners to main loop for later overlay; keep the one window
    if corners_out_holder is not None:
        corners_out_holder[:] = detected_cam

    # If we temporarily showed the preview, hide it again
    if restore_preview:
        try: cv2.destroyWindow(PREVIEW_WIN)
        except: pass

    return H, detected_cam

# -----------------------------
# Main
# -----------------------------
def main():
    pygame.init()
    pygame.display.set_caption("Laser Demo (Auto-calibrate with C, Toggle preview with P, Esc to Quit)")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW if sys.platform.startswith("win") else 0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 60)
    if not cap.isOpened():
        print("ERROR: Could not open camera."); pygame.quit(); return

    font = pygame.font.SysFont(None, 28)
    font_small = pygame.font.SysFont(None, 20)

    H = None
    corners_cam = []  # filled after calibration
    last_trigger = 0.0
    last_pos = None
    explosions = []
    show_preview = True

    # Create the single preview window up front
    if show_preview:
        cv2.namedWindow(PREVIEW_WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(PREVIEW_WIN, 640, 360)

    def is_preview_visible():
        # crude: if we intended it visible, assume window exists
        return show_preview

    running = True
    while running:
        dt = clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_c, pygame.K_r):
                    H, _ = auto_calibrate(cap, screen, font, font_small, is_preview_visible, corners_cam)
                    last_pos = None
                elif event.key == pygame.K_p:
                    show_preview = not show_preview
                    if show_preview:
                        cv2.namedWindow(PREVIEW_WIN, cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(PREVIEW_WIN, 640, 360)
                    else:
                        try: cv2.destroyWindow(PREVIEW_WIN)
                        except: pass

        ok, frame = cap.read()
        if not ok: continue

        cam_pt, mask = find_red_laser_centroid_and_mask(frame)

        # Update the single OpenCV preview if visible
        if show_preview:
            prev = draw_preview_frame(frame, mask, cam_pt, corners_cam if len(corners_cam)==4 else None, None)
            cv2.imshow(PREVIEW_WIN, prev)
            cv2.waitKey(1)  # keep window responsive

        # Map to screen space
        screen_pt = None
        if cam_pt is not None and H is not None:
            pt = np.array([[cam_pt]], dtype=np.float32)
            mapped = cv2.perspectiveTransform(pt, H)[0][0]
            x, y = float(mapped[0]), float(mapped[1])
            if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                screen_pt = (x, y)

        # Trigger explosions
        now = time.time()
        if screen_pt is not None:
            moved = (last_pos is None) or (math.hypot(screen_pt[0]-last_pos[0], screen_pt[1]-last_pos[1]) >= TRIGGER_MOVE_THRESHOLD)
            if moved and (now - last_trigger) >= TRIGGER_COOLDOWN_SEC:
                explosions.append(Explosion(screen_pt[0], screen_pt[1]))
                last_trigger = now
                last_pos = screen_pt
        else:
            last_pos = None

        # Draw PyGame scene
        screen.fill((15, 18, 22))
        pygame.draw.rect(screen, (220, 220, 220), (8, 8, SCREEN_W - 16, SCREEN_H - 16), width=2)

        status = ("Calibrated (C=recalibrate, P=toggle preview)" if H is not None
                  else "Press C to auto-calibrate (P=toggle preview)")
        screen.blit(font.render(status, True, (230, 230, 230)), (16, 16))

        for e in explosions:
            e.update(dt); e.draw(screen)
        explosions = [e for e in explosions if not e.dead]

        if screen_pt is not None:
            pygame.draw.circle(screen, (255, 80, 80), (int(screen_pt[0]), int(screen_pt[1])), 5)

        pygame.display.flip()

    # Cleanup
    cap.release()
    try: cv2.destroyWindow(PREVIEW_WIN)
    except: pass
    cv2.destroyAllWindows()
    pygame.quit()

if __name__ == "__main__":
    main()
