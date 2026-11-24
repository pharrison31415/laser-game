from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from typing import List, Tuple, Optional


class HomographyStore:
    """
    Camera -> screen calibration, stored as plain, human-readable JSON:

        {"H": [[...], [...], [...]], "corners_cam": [[x, y], ...]}   # corners optional

    Older calibrations saved as default.npz are converted on first load.
    """

    def __init__(self):
        root = Path(__file__).resolve(
        ).parents[2] / "runtime" / "cache" / "homographies"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "default.json"
        self.legacy_path = root / "default.npz"

    def load(self):
        """
        Returns (H or None, corners_cam or None)
        corners_cam is a list of 4 (x,y) in camera space (TL, TR, BR, BL) if stored.
        """
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            H = np.array(data["H"], dtype=np.float64)
            corners = data.get("corners_cam")
            corners_cam = [tuple(map(int, pt)) for pt in corners] if corners else None
            return H, corners_cam

        if self.legacy_path.exists():
            data = np.load(self.legacy_path, allow_pickle=False)
            H = data["H"]
            corners_cam = None
            if "corners_cam" in data.files:
                corners_cam = [tuple(map(int, pt)) for pt in data["corners_cam"].tolist()]
            self.save(H, corners_cam)  # migrate to JSON; the .npz is left in place
            return H, corners_cam

        return None, None

    def save(self, H: np.ndarray, corners_cam: Optional[List[Tuple[int, int]]] = None):
        data = {"H": np.asarray(H, dtype=np.float64).tolist()}
        if corners_cam is not None:
            data["corners_cam"] = [[int(x), int(y)] for (x, y) in corners_cam]
        tmp = self.path.with_suffix(".json.tmp")
        # one matrix row / corner per line: readable and diff-friendly
        lines = ['  "H": [\n' + ",\n".join(f"    {json.dumps(r)}" for r in data["H"]) + "\n  ]"]
        if "corners_cam" in data:
            lines.append(f'  "corners_cam": {json.dumps(data["corners_cam"])}')
        tmp.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
        tmp.replace(self.path)
