from __future__ import annotations
from dataclasses import dataclass
import pygame
from typing import Any, Tuple
from engine.api.config import EngineConfig


@dataclass
class Context:
    screen: pygame.Surface
    clock: pygame.time.Clock
    cfg: EngineConfig
    # engine internals exposed read-only for games if needed:
    resources: dict[str, Any]
    screen_size: Tuple[int, int]
