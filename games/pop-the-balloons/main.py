from __future__ import annotations
import random
import pygame
from engine.api import Game, FrameData
from engine.render.shapes import draw_text


class PopTheBalloons(Game):
    def on_load(self, ctx, manifest):
        self.ctx = ctx
        self.manifest = manifest
        self.balloons = []
        self.score = 0
        w, h = ctx.screen_size
        n = manifest.get("options", {}).get("balloon_count", 12)
        for _ in range(n):
            x = random.randint(60, w - 60)
            y = random.randint(60, h - 60)
            r = random.randint(16, 28)
            self.balloons.append([x, y, r, True])  # x,y,r,alive

    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        reds = frame.points_by_color.get("red", [])
        if not reds:
            return
        for p in reds:
            for b in self.balloons:
                if not b[3]:
                    continue
                dx = p.x - b[0]
                dy = p.y - b[1]
                if dx * dx + dy * dy <= (b[2] * b[2]):
                    b[3] = False
                    self.score += 1

    def on_draw(self, surface: pygame.Surface) -> None:
        draw_text(surface, "Pop the Balloons — press C to calibrate", (20, 20), size=24)
        draw_text(surface, f"Score: {self.score}", (20, 52), size=24)
        for (x, y, r, alive) in self.balloons:
            color = (50, 200, 80) if alive else (45, 45, 45)
            pygame.draw.circle(surface, color, (int(x), int(y)), int(r), width=0)

    def on_unload(self) -> None:
        pass


def get_game():
    return PopTheBalloons()
