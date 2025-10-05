from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
import cv2
from engine.api.frame_data import Point


class LaserInput:
    def __init__(self, max_points_per_color: int, H: np.ndarray | None, mirror: bool = False):
        self.max_points = max_points_per_color
        self.H = H
        self.mirror = mirror

    def set_homography(self, H: np.ndarray):
        self.H = H

    def set_mirror(self, mirror: bool):
        self.mirror = mirror

    def _map_point(self, cam_xy: Tuple[float, float], screen_size: Tuple[int, int]) -> Tuple[float, float] | None:
        if self.H is None:
            # No homography: pass-through, but still drop if out of bounds later
            x, y = cam_xy
        else:
            pt = np.array([[[cam_xy[0], cam_xy[1]]]], dtype=np.float32)
            mapped = cv2.perspectiveTransform(pt, self.H)[0][0]
            x, y = float(mapped[0]), float(mapped[1])

        w, h = screen_size
        if 0 <= x < w and 0 <= y < h:
            if self.mirror:
                x = (w - 1) - x
            return (x, y)
        return None

    def map_and_select(
        self, detections: Dict[str, List[Tuple[float, float, float]]], screen_size: Tuple[int, int]
    ) -> Dict[str, List[Point]]:
        out: Dict[str, List[Point]] = {}
        for color, pts in detections.items():
            mapped: List[Point] = []
            for (x, y, intensity) in pts[: self.max_points * 3]:  # take a few extra before filtering
                m = self._map_point((x, y), screen_size)
                if m is not None:
                    mapped.append(Point(m[0], m[1], intensity))
            # keep top-N by intensity
            mapped.sort(key=lambda p: p.intensity, reverse=True)
            out[color] = mapped[: self.max_points]
        return out
