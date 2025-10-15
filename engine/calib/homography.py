from __future__ import annotations
from pathlib import Path
import numpy as np
from typing import List, Tuple, Optional


class HomographyStore:
    def __init__(self):
        root = Path(__file__).resolve(
        ).parents[2] / "runtime" / "cache" / "homographies"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"default.npz"

    def load(self):
        """
        Returns (H or None, corners_cam or None)
        corners_cam is a list of 4 (x,y) in camera space (TL, TR, BR, BL) if stored.
        """

        if not self.path.exists():
            return None, None

        data = np.load(self.path, allow_pickle=True)
        H = data["H"]
        corners_cam = data["corners_cam"] if "corners_cam" in data.files else None
        if corners_cam is not None:
            corners_cam = [tuple(map(int, pt)) for pt in corners_cam.tolist()]
        return H, corners_cam

    def save(self, H: np.ndarray, corners_cam: Optional[List[Tuple[int, int]]] = None):
        if corners_cam is None:
            np.savez_compressed(self.path, H=H)
        else:
            np.savez_compressed(self.path, H=H, corners_cam=np.array(
                corners_cam, dtype=np.int32))
