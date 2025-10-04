from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Point:
    x: float
    y: float
    intensity: float


@dataclass
class FrameData:
    timestamp: float
    # e.g. {"red": [Point, Point, ...], "green": [...]} (already mapped to screen coords)
    points_by_color: Dict[str, List[Point]]
