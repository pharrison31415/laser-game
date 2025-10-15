from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass
class EngineConfig:
    screen_size: Tuple[int, int]
    cam_index: int
    show_preview: bool
    mirror: bool = False
    debug: bool = False
