from __future__ import annotations
from typing import Dict, List, Tuple
import cv2
import numpy as np
import math
import time


# Default HSV ranges per color (tweak via config later if desired)
DEFAULT_RANGES = {
    "red": [
        ((0, 120, 180), (8, 255, 255)),
        ((170, 120, 180), (180, 255, 255)),
    ],
    "green": [
        ((35, 80, 120), (85, 255, 255)),
    ],
    "blue": [
        ((95, 80, 120), (130, 255, 255)),
    ],
}

MIN_BLOB_AREA = 8
KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))


class ColorTracker:
    def __init__(self, colors: List[str], show_preview: bool = False, preview_name: str = "Preview"):
        self.colors = colors
        self.show_preview = show_preview
        self.preview_name = preview_name
        if self.show_preview:
            cv2.namedWindow(self.preview_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.preview_name, 640, 360)

    def _mask_for_color(self, hsv, color_name: str):
        ranges = DEFAULT_RANGES.get(color_name, [])
        if not ranges:
            return np.zeros(hsv.shape[:2], dtype=np.uint8)
        masks = []
        for lo, hi in ranges:
            masks.append(cv2.inRange(hsv, lo, hi))
        mask = masks[0]
        for m in masks[1:]:
            mask = cv2.bitwise_or(mask, m)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL, iterations=1)
        return mask

    def detect(self, frame_bgr) -> Dict[str, List[Tuple[int, int, float]]]:
        """
        Returns camera-space detections: {color: [(x,y,intensity), ...], ...}
        """
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        out: Dict[str, List[Tuple[int, int, float]]] = {}
        overlay = frame_bgr.copy()

        for color in self.colors:
            mask = self._mask_for_color(hsv, color)
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            points: List[Tuple[int, int, float]] = []
            for c in cnts:
                area = cv2.contourArea(c)
                if area < MIN_BLOB_AREA:
                    continue
                M = cv2.moments(c)
                if M["m00"] <= 0:
                    continue
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                # crude intensity proxy: mean value in small patch or area
                intensity = float(area)
                points.append((cx, cy, intensity))

            # sort by intensity/area descending
            points.sort(key=lambda p: p[2], reverse=True)
            out[color] = points

            if self.show_preview:
                overlay[mask > 0] = (0, 0, 255) if color == "red" else overlay[mask > 0]
                for (x, y, _) in points[:3]:
                    cv2.circle(overlay, (x, y), 4, (255, 255, 0), -1)

        if self.show_preview:
            cv2.putText(
                overlay, time.strftime("%H:%M:%S"),
                (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA
            )
            cv2.imshow(self.preview_name, overlay)
            cv2.waitKey(1)

        return out

    def auto_calibrate(self, screen, screen_size, camera) -> np.ndarray:
        """
        Minimal auto-calibration: show 4 corner dots; user aims laser steadily.
        Returns 3x3 homography mapping camera->screen. Esc to abort (returns identity).
        """
        w, h = screen_size
        corners_screen = [(20, 20), (w - 20, 20), (w - 20, h - 20), (20, h - 20)]
        labels = ["TL", "TR", "BR", "BL"]
        detected_cam = []
        font = None

        import pygame
        font = pygame.font.SysFont(None, 28)

        STABLE_FRAMES = 6
        STABLE_PIXELS = 4
        TIMEOUT = 6.0

        for idx, (sx, sy) in enumerate(corners_screen):
            stable = 0
            last = None
            import time as _t
            t0 = _t.time()

            while True:
                screen.fill((0, 0, 0))
                msg = f"Calibrating {labels[idx]} ({idx+1}/4) — hold laser steady; Esc to cancel"
                screen.blit(font.render(msg, True, (240, 240, 240)), (16, 16))
                for j, (cx, cy) in enumerate(corners_screen):
                    color = (255, 0, 0) if j == idx else (90, 0, 0)
                    pygame.draw.circle(screen, color, (cx, cy), 10)
                pygame.display.flip()

                for ev in pygame.event.get():
                    if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                        return np.eye(3, dtype=np.float32)

                ok, frame = camera.read()
                if not ok:
                    continue
                detections = self.detect(frame)
                red_pts = detections.get("red", [])
                cam_pt = (int(red_pts[0][0]), int(red_pts[0][1])) if red_pts else None

                if cam_pt is not None:
                    if last is None:
                        stable = 1
                    else:
                        dx = cam_pt[0] - last[0]
                        dy = cam_pt[1] - last[1]
                        stable = stable + 1 if (dx * dx + dy * dy) ** 0.5 <= STABLE_PIXELS else 1
                    last = cam_pt
                    if stable >= STABLE_FRAMES:
                        detected_cam.append(cam_pt)
                        break

                if (_t.time() - t0) > TIMEOUT:
                    return np.eye(3, dtype=np.float32)

        src = np.array(detected_cam, dtype=np.float32)
        dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
        H, _ = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if H is None:
            H = np.eye(3, dtype=np.float32)
        return H

    def teardown(self):
        if self.show_preview:
            try:
                cv2.destroyWindow(self.preview_name)
            except Exception:
                pass
        cv2.destroyAllWindows()
