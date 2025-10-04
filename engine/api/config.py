from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass
class EngineConfig:
    screen_size: Tuple[int, int]
    colors: Sequence[str]
    max_points_per_color: int
    cam_index: int
    profile: str
    show_preview: bool
    mirror: bool = False
