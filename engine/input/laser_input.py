from typing import Dict, List, Tuple
import numpy as np
import cv2
from engine.api.frame_data import Point


class LaserInput:
    """
    Maps camera-space detections to screen space and selects the top-N points per color.
    `max_points` must be a Dict[str, int] coming from the game's manifest, e.g.:

        max_points_per_color:
          red: 3
          green: 1
          blue: 0   # 0 means ignore this color

    Colors not present in the dict default to 0 (ignored).
    """

    def __init__(self, max_points: Dict[str, int], H: np.ndarray | None, mirror: bool = False):
        # normalize keys
        self.max_points_per_color: Dict[str, int] = {
            str(k).lower(): int(v) for k, v in (max_points or {}).items()}
        self.H = H
        self.mirror = mirror

    def set_homography(self, H: np.ndarray):
        self.H = H

    def set_mirror(self, mirror: bool):
        self.mirror = mirror

    def set_max_points_per_color(self, mapping: Dict[str, int]) -> None:
        self.max_points_per_color = {
            str(k).lower(): int(v) for k, v in mapping.items()}

    def _limit_for(self, color: str) -> int:
        # default to 0 for unspecified colors
        return int(self.max_points_per_color.get(color.lower(), 0))

    def _map_point(self, cam_xy: Tuple[float, float], screen_size: Tuple[int, int]) -> Tuple[float, float] | None:
        if self.H is None:
            x, y = cam_xy
        else:
            pt = np.array([[[cam_xy[0], cam_xy[1]]]], dtype=np.float32)
            mapped = cv2.perspectiveTransform(pt, self.H)[0][0]
            x, y = float(mapped[0]), float(mapped[1])

        w, h = screen_size
        if 0 <= x < w and 0 <= y < h:
            # post-H mirror so logical input matches mirrored presentation
            if self.mirror:
                x = (w - 1) - x
            return (x, y)
        return None

    def map_and_select(
        self, detections: Dict[str, List[Tuple[float, float, float]]], screen_size: Tuple[int, int]
    ) -> Dict[str, List[Point]]:
        out: Dict[str, List[Point]] = {}
        for color, pts in detections.items():
            cap = self._limit_for(color)
            if cap <= 0:
                out[color] = []
                continue

            # grab a few extra before bounds/mapping filtering
            pre_cap = max(1, cap * 3)
            mapped: List[Point] = []
            for (x, y, intensity) in pts[:pre_cap]:
                m = self._map_point((x, y), screen_size)
                if m is not None:
                    mapped.append(Point(m[0], m[1], intensity))

            mapped.sort(key=lambda p: p.intensity, reverse=True)
            out[color] = mapped[:cap]
        return out
