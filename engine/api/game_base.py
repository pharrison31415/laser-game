from __future__ import annotations

import pygame

from engine.app.context import Context

from .frame_data import FrameData


class Game:
    """
    Base interface games should implement.
    """

    def on_load(self, ctx: Context, manifest: dict) -> None:
        """Called once after the game module loads."""
        ...

    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        """Called every frame; dt_ms is milliseconds elapsed."""
        ...

    def on_draw(self, surface: pygame.Surface) -> None:
        """Draw your game to the provided surface."""
        ...

    def on_event(self, event: pygame.event.Event) -> None:
        """Optional: Handle pygame events (keyboard, etc.)."""
        ...

    def on_unload(self) -> None:
        """Optional: cleanup when the game exits."""
        ...
