from __future__ import annotations
import pygame
from typing import Dict, List, Tuple

from engine.api.config import EngineConfig
from engine.api.frame_data import Point

_BTN_NAME = {1: "left", 2: "middle", 3: "right"}


class DebugPointInjector:
    """
    Hold-only debug injector:
    - While a mouse button is down, emit a synthetic point of the mapped color every frame.
    - Position updates with mouse motion.
    - Respects --mirror by converting window coords -> logical coords.
    """

    def __init__(self, cfg: EngineConfig, debug_manifest: dict):
        self.enabled = cfg.debug and debug_manifest.get("enabled", False)
        self.mirror = cfg.mirror
        self.buttons: Dict[str, str] = debug_manifest.get(
            "buttons", {"left": "red"})
        self.intensity: float = float(debug_manifest.get("intensity", 9999))

        # held positions by button name -> (x, y) in logical coords
        self._points: Dict[str, Tuple[float, float]] = {}

    def _to_logical(self, x: int, y: int, w: int, h: int) -> Tuple[float, float]:
        if self.mirror:
            x = (w - 1) - x
        return float(x), float(y)

    def handle_pygame_event(self, event: pygame.event.Event, screen_size: Tuple[int, int]) -> None:
        if not self.enabled:
            return
        w, h = screen_size

        if event.type == pygame.MOUSEBUTTONDOWN:
            btn_name = _BTN_NAME.get(event.button)
            color = self.buttons.get(btn_name)
            if color:
                lx, ly = self._to_logical(*event.pos, w, h)
                self._points[btn_name] = (lx, ly)

        elif event.type == pygame.MOUSEBUTTONUP:
            btn_name = _BTN_NAME.get(event.button)
            if btn_name in self._points:
                del self._points[btn_name]

        elif event.type == pygame.MOUSEMOTION:
            # Update any held buttons to the new position
            if self._points:
                lx, ly = self._to_logical(*event.pos, w, h)
                for btn_name in list(self._points.keys()):
                    self._points[btn_name] = (lx, ly)

        # Defensive: if window loses focus, clear held
        elif event.type == pygame.WINDOWFOCUSLOST:
            self._points.clear()

    def emit_points(self) -> Dict[str, List[Point]]:
        """
        Return {color: [Point,...]} for the current frame.
        Only emits while buttons are held; no time-based persistence.
        """
        if not self.enabled or not self._points:
            return {}

        out: Dict[str, List[Point]] = {}
        for btn_name, (x, y) in self._points.items():
            color = self.buttons.get(btn_name)
            if not color:
                continue
            out.setdefault(color, []).append(Point(x, y, self.intensity))
        return out
