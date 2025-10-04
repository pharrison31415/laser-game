from __future__ import annotations
import pygame
from engine.api import Game, FrameData
from engine.render.shapes import draw_text


class TemplateGame(Game):
    def on_load(self, ctx, manifest):
        self.ctx = ctx
        self.manifest = manifest
        self.points = []

    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        self.points = frame.points_by_color.get("red", [])

    def on_draw(self, surface: pygame.Surface) -> None:
        draw_text(surface, "Template Game — aim the laser!", (20, 20), size=28)
        for p in self.points:
            pygame.draw.circle(surface, (255, 80, 80), (int(p.x), int(p.y)), 8)

    def on_unload(self) -> None:
        pass


def get_game():
    return TemplateGame()
