import sys
import time
import math

import numpy as np
import cv2
import pygame

from const import *

# -----------------------------
# Utility: simple explosion effect
# -----------------------------

class Explosion:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 4
        self.max_radius = 80
        self.alpha = 255
        self.dead = False

    def update(self, dt):
        # Expand quickly, fade a bit slower
        self.radius += 300 * dt / 1000.0
        self.alpha -= 500 * dt / 1000.0
        if self.radius >= self.max_radius or self.alpha <= 0:
            self.dead = True

    def draw(self, surf):
        # Draw a few concentric circles with decreasing alpha
        r = int(max(2, self.radius))
        a = int(max(0, min(255, self.alpha)))
        for i in range(3):
            rr = max(1, r - i * 6)
            aa = max(0, a - i * 60)
            if aa <= 0:
                continue
            color = (255, 200, 0, aa)  # gold-ish
            circle_surf = pygame.Surface((rr * 2 + 4, rr * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(circle_surf, color, (rr + 2, rr + 2), rr, width=2)
            surf.blit(circle_surf, (self.x - rr - 2, self.y - rr - 2))

# -----------------------------
# Calibration (click 4 corners in camera image)
# -----------------------------

def calibrate_homography(cap):
    """
    Let the user click the four screen corners in the camera image:
    order: TL, TR, BR, BL. Return (H, corners_cam).
    H is 3x3 homography mapping cam->screen coords.
    Press 'q' in the calibration window to abort (returns (None, None)).
    """
    clicked = []

    window_name = "Calibration - Click TL, TR, BR, BL (press q to cancel)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < 4:
            clicked.append((x, y))

    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        disp = frame.copy()
        cv2.putText(disp, f"Click corners: {len(clicked)}/4 (TL, TR, BR, BL)",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)

        for i, (x, y) in enumerate(clicked):
            cv2.circle(disp, (x, y), 6, (0, 255, 0), -1)
            labels = ["TL", "TR", "BR", "BL"]
            label = labels[i] if i < len(labels) else str(i + 1)
            cv2.putText(disp, label, (x + 10, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imshow(window_name, disp)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):  # abort
            cv2.destroyWindow(window_name)
            return None, None

        if len(clicked) == 4:
            break

    cv2.destroyWindow(window_name)

    src = np.array(clicked, dtype=np.float32)
    dst = np.array([
        [0, 0],
        [SCREEN_W - 1, 0],
        [SCREEN_W - 1, SCREEN_H - 1],
        [0, SCREEN_H - 1]
    ], dtype=np.float32)

    # Compute homography (RANSAC helps if clicks are a little off)
    H, mask = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    return H, clicked

# -----------------------------
# Laser detection (in camera space)
# -----------------------------

def find_red_laser_centroid_and_mask(frame_bgr):
    """
    Return (centroid_xy, mask) where centroid_xy is (x, y) in camera pixels or None.
    mask is a binary image marking detected red pixels (uint8 {0,255}).
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    mask1 = cv2.inRange(hsv, LOW1, HIGH1)
    mask2 = cv2.inRange(hsv, LOW2, HIGH2)
    mask = cv2.bitwise_or(mask1, mask2)

    # Clean up noise a little
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)

    # Find contours and pick the largest bright spot
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, mask

    best = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(best)
    if area < MIN_BLOB_AREA:
        return None, mask

    M = cv2.moments(best)
    if M["m00"] <= 0:
        return None, mask

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy), mask

# -----------------------------
# Helpers
# -----------------------------

def cv2_to_pygame_surface(img_bgr):
    """Convert a BGR OpenCV image to a PyGame Surface (RGB)."""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    # PyGame expects (width, height) in make_surface; array must be (W,H,3) after transpose
    surf = pygame.surfarray.make_surface(np.rot90(img_rgb))  # rotate to match surface orientation
    return surf

# -----------------------------
# Main
# -----------------------------

def main():
    pygame.init()
    pygame.display.set_caption("Laser Demo (Calibrate with C, Redo with R, Quit with Esc)")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    # Try to keep the camera at a known resolution (not guaranteed)
    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW if sys.platform.startswith("win") else 0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 60)

    if not cap.isOpened():
        print("ERROR: Could not open camera.")
        pygame.quit()
        return

    font = pygame.font.SysFont(None, 28)
    font_small = pygame.font.SysFont(None, 20)

    H = None  # Homography cam->screen
    corners_cam = None  # [(x,y)*4] as clicked during calibration
    last_trigger = 0.0
    last_pos = None
    explosions = []

    running = True
    while running:
        dt = clock.tick(60)  # ms since last frame

        # 1) Handle PyGame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_c, pygame.K_r):
                    # Enter calibration flow
                    H, corners_cam = calibrate_homography(cap)
                    last_pos = None

        # 2) Capture a camera frame
        ok, frame = cap.read()
        if not ok:
            continue

        # 3) Detect a laser dot + mask in camera space
        cam_pt, mask = find_red_laser_centroid_and_mask(frame)

        # 3b) For the preview: paint detected red pixels as pure red (255,0,0 in RGB)
        # Since OpenCV is BGR, set to (0,0,255) here which becomes (255,0,0) after conversion.
        preview_bgr = frame.copy()
        red_idx = mask > 0
        preview_bgr[red_idx] = (0, 0, 255)

        # 4) Map to screen space if we have a homography
        screen_pt = None
        if cam_pt is not None and H is not None:
            pt = np.array([[cam_pt]], dtype=np.float32)  # shape (1,1,2)
            mapped = cv2.perspectiveTransform(pt, H)[0][0]  # shape (2,)
            x, y = float(mapped[0]), float(mapped[1])

            # Only accept if inside screen bounds
            if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                screen_pt = (x, y)

        # 5) Trigger explosion if newly detected / moved enough
        now = time.time()
        if screen_pt is not None:
            should_trigger = False
            if last_pos is None:
                should_trigger = True
            else:
                dx = screen_pt[0] - last_pos[0]
                dy = screen_pt[1] - last_pos[1]
                if math.hypot(dx, dy) >= TRIGGER_MOVE_THRESHOLD:
                    should_trigger = True

            if should_trigger and (now - last_trigger) >= TRIGGER_COOLDOWN_SEC:
                explosions.append(Explosion(screen_pt[0], screen_pt[1]))
                last_trigger = now
                last_pos = screen_pt
        else:
            last_pos = None

        # 6) Draw main scene
        screen.fill((15, 18, 22))

        # Border
        pygame.draw.rect(screen, (220, 220, 220), (8, 8, SCREEN_W - 16, SCREEN_H - 16), width=2)

        # Calibration status
        status = "Calibrated" if H is not None else "Press C to calibrate (click TL, TR, BR, BL)"
        txt = font.render(status, True, (230, 230, 230))
        screen.blit(txt, (16, 16))

        # Explosions
        for e in explosions:
            e.update(dt)
            e.draw(screen)
        explosions = [e for e in explosions if not e.dead]

        # Dot where the mapped point is
        if screen_pt is not None:
            pygame.draw.circle(screen, (255, 80, 80), (int(screen_pt[0]), int(screen_pt[1])), 5)

        # 7) Draw live camera preview (with red pixels in (255,0,0) and corners overlaid)
        # Resize preview for display
        preview_resized = cv2.resize(preview_bgr, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_AREA)

        # Overlay the calibration corners (if known) on the preview
        if corners_cam is not None and len(corners_cam) == 4:
            # scale corner coordinates to preview size
            sx = PREVIEW_W / float(frame.shape[1])
            sy = PREVIEW_H / float(frame.shape[0])
            labels = ["TL", "TR", "BR", "BL"]
            for i, (cx, cy) in enumerate(corners_cam):
                px = int(cx * sx)
                py = int(cy * sy)
                cv2.circle(preview_resized, (px, py), 5, (0, 255, 0), -1)  # green dot
                cv2.putText(preview_resized, labels[i], (px + 6, py - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            # draw the quad outline
            p = [(int(corners_cam[i][0] * sx), int(corners_cam[i][1] * sy)) for i in range(4)]
            for i in range(4):
                cv2.line(preview_resized, p[i], p[(i + 1) % 4], (0, 200, 0), 1, cv2.LINE_AA)

        # Overlay the detected laser centroid (cyan) on the preview
        if cam_pt is not None:
            sx = PREVIEW_W / float(frame.shape[1])
            sy = PREVIEW_H / float(frame.shape[0])
            px = int(cam_pt[0] * sx)
            py = int(cam_pt[1] * sy)
            cv2.circle(preview_resized, (px, py), 4, (255, 255, 0), -1)  # (B,G,R) ~ yellow/cyan-ish

        # Convert to pygame surface and blit
        preview_surf = cv2_to_pygame_surface(preview_resized)
        # Border + title
        px, py = PREVIEW_POS
        pygame.draw.rect(screen, (40, 45, 50), (px - 4, py - 24, PREVIEW_W + 8, PREVIEW_H + 28))
        title = font_small.render("Camera Preview (red pixels shown as (255,0,0))", True, (220, 220, 220))
        screen.blit(title, (px, py - 20))
        screen.blit(preview_surf, (px, py))
        pygame.draw.rect(screen, (200, 200, 200), (px - 1, py - 1, PREVIEW_W + 2, PREVIEW_H + 2), width=1)

        pygame.display.flip()

    cap.release()
    pygame.quit()


if __name__ == "__main__":
    main()
