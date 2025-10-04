from __future__ import annotations
from pathlib import Path
import numpy as np


class HomographyStore:
    def __init__(self, profile_name: str = "default"):
        root = Path(__file__).resolve().parents[2] / "runtime" / "cache" / "homographies"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{profile_name}.npz"

    def load_or_none(self):
        if self.path.exists():
            data = np.load(self.path)
            return data["H"]
        return None

    def save(self, H: np.ndarray):
        np.savez_compressed(self.path, H=H)
