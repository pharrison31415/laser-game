import math
import random
from dataclasses import dataclass
from typing import Optional, List

import pygame
from engine.api import Game, FrameData
from engine.app.context import Context
from engine.render.shapes import draw_text


# -----------------------------
# Tuning constants
# -----------------------------
WINNING_SCORE_DEFAULT = 7

PADDLE_W_RATIO = 0.014        # paddle width relative to screen width
PADDLE_H_RATIO = 0.18         # paddle height relative to screen height
PADDLE_EDGE_MARGIN = 18       # px from screen edges
PADDLE_BORDER_RADIUS = 4

BALL_SIZE = 12                # square ball (px)
BALL_SPEED_START = 0.40       # px/ms initial speed
BALL_SPEED_MAX = 1.4          # px/ms clamp
BALL_SPEED_RAMP = 1.04        # multiply on each paddle hit
BALL_ANGLE_MAX = math.radians(70)   # max deflection from horizontal
SERVE_DELAY_MS = 900
SERVE_MIN_ANGLE = math.radians(20)

HUD_COLOR = (230, 230, 230)
MIDLINE_COLOR = (110, 110, 110)
PADDLE_COLOR = (230, 230, 230)
BALL_COLOR = (230, 230, 230)
WIN_FLASH_COLOR = (255, 255, 255)


@dataclass
class Paddle:
    x: int
    y: float
    w: int
    h: int

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.w // 2), int(self.y - self.h // 2), self.w, self.h)

    def clamp(self, h_total: int):
        half = self.h // 2
        self.y = max(half, min(h_total - half, self.y))


@dataclass
class Ball:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    speed: float
    prev_x: float = 0.0
    prev_y: float = 0.0


class Pong(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.manifest = manifest
        self.w, self.h = ctx.screen_size
        self.mid_x = self.w // 2

        self.winning_score = int(manifest.get("options", {}).get(
            "winning_score", WINNING_SCORE_DEFAULT))

        pw = max(8, int(self.w * PADDLE_W_RATIO))
        ph = max(34, int(self.h * PADDLE_H_RATIO))
        self.left = Paddle(x=PADDLE_EDGE_MARGIN + pw //
                           2, y=self.h / 2, w=pw, h=ph)
        self.right = Paddle(
            x=self.w - (PADDLE_EDGE_MARGIN + pw // 2), y=self.h / 2, w=pw, h=ph)

        self.ball: Optional[Ball] = None
        self.score_l = 0
        self.score_r = 0
        self.last_point_time = 0
        self.serving_side = random.choice(("left", "right"))  # who serves next
        self.awaiting_serve = True

        self._serve(reset_speed=True)

    def _points_in_half(self, frame: FrameData, left: bool):
        reds = frame.points_by_color.get("red", [])
        if left:
            return [p for p in reds if p.x < self.mid_x]
        else:
            return [p for p in reds if p.x >= self.mid_x]

    def _laser_target_y(self, points: List) -> Optional[float]:
        if not points:
            return None
        return float(points[0].y)  # brightest/first point

    def _snap_paddle(self, paddle: Paddle, target_y: Optional[float]):
        if target_y is not None:
            paddle.y = target_y
            paddle.clamp(self.h)

    def _serve(self, reset_speed: bool):
        # Center ball; set direction but keep speed zero until serve trigger
        angle = random.uniform(SERVE_MIN_ANGLE, BALL_ANGLE_MAX)
        dir_x = 1 if self.serving_side == "left" else -1
        angle = angle if dir_x > 0 else math.pi - angle
        vx = math.cos(angle) * BALL_SPEED_START
        vy = math.sin(angle) * BALL_SPEED_START
        speed = BALL_SPEED_START if reset_speed else min(
            self._ball_speed(), BALL_SPEED_MAX)

        self.ball = Ball(
            x=self.w / 2,
            y=self.h / 2,
            vx=vx,
            vy=vy,
            size=BALL_SIZE,
            speed=speed,
            prev_x=self.w / 2,
            prev_y=self.h / 2,
        )
        self.last_point_time = pygame.time.get_ticks()
        self.awaiting_serve = True

    def _ball_speed(self) -> float:
        b = self.ball
        if not b:
            return BALL_SPEED_START
        return max(abs(b.vx), abs(b.vy), b.speed)

    def _serve_if_ready(self, frame: FrameData):
        if not self.awaiting_serve:
            return
        if pygame.time.get_ticks() - self.last_point_time < SERVE_DELAY_MS:
            return
        pts = self._points_in_half(frame, left=(self.serving_side == "left"))
        if pts:
            self.ball.speed = BALL_SPEED_START
            self.awaiting_serve = False

    def _reset_point(self, scored_by: str):
        if scored_by == "left":
            self.score_l += 1
            self.serving_side = "right"
        else:
            self.score_r += 1
            self.serving_side = "left"
        self._serve(reset_speed=True)

    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        # Paddle control: snap instantly to laser Y when present; otherwise stay put
        lpts = self._points_in_half(frame, left=True)
        rpts = self._points_in_half(frame, left=False)
        self._snap_paddle(self.left, self._laser_target_y(lpts))
        self._snap_paddle(self.right, self._laser_target_y(rpts))

        # Serve logic
        self._serve_if_ready(frame)

        # Ball physics
        if not self.ball:
            return
        b = self.ball

        # During serve, keep ball centered and keep prev in sync
        if self.awaiting_serve:
            b.x = self.w / 2
            b.y = self.h / 2
            b.prev_x, b.prev_y = b.x, b.y
            return

        # Save previous for swept tests then integrate
        b.prev_x, b.prev_y = b.x, b.y
        b.x += b.vx * dt_ms
        b.y += b.vy * dt_ms

        # Top/bottom walls
        r = b.size / 2
        if b.y <= r:
            b.y = r
            b.vy = abs(b.vy)
        elif b.y >= self.h - r:
            b.y = self.h - r
            b.vy = -abs(b.vy)

        # Paddle rects
        left_rect = self.left.rect()
        right_rect = self.right.rect()

        # Unified paddle contact (s=-1 for left, +1 for right)
        self._paddle_contact(b, self.left,  left_rect,
                             s=-1, face_x=left_rect.right)
        self._paddle_contact(b, self.right, right_rect,
                             s=+1, face_x=right_rect.left)

        # Scoring (ball out of bounds)
        if b.x < -b.size:
            self._reset_point(scored_by="right")
        elif b.x > self.w + b.size:
            self._reset_point(scored_by="left")

    def _paddle_contact(self, b, paddle, rect, s: int, face_x: float) -> None:
        """
        s = -1 for left paddle (ball moving left -> reflect right)
        s = +1 for right paddle (ball moving right -> reflect left)
        """
        r = b.size / 2
        # Only test if ball moving toward this paddle
        if (s < 0 and b.vx >= 0) or (s > 0 and b.vx <= 0):
            return

        # Swept AABB along x using the leading edge of the ball
        prev_edge = b.prev_x + s * r
        curr_edge = b.x + s * r
        crossed = (s * prev_edge) < (s * face_x) and (s *
                                                      curr_edge) >= (s * face_x)
        if not crossed:
            return

        # Simple y-overlap check (arcade-style)
        top = rect.top - r
        bot = rect.bottom + r
        if not (top <= b.y <= bot):
            return

        # Snap ball just outside the paddle face to avoid sticking
        b.x = face_x - s * r - 0.5 * s

        # Compute bounce angle from contact offset (-1..1), clamp to avoid extremes
        offset = (b.y - paddle.y) / (paddle.h / 2)
        offset = max(-1.0, min(1.0, offset))

        # Angle: mirror across pi for right side so outgoing vx has correct sign
        base = offset * BALL_ANGLE_MAX
        angle = (math.pi - base) if s > 0 else base

        # Speed ramp with cap
        speed_in = math.hypot(b.vx, b.vy) or BALL_SPEED_START
        speed_out = min(speed_in * BALL_SPEED_RAMP, BALL_SPEED_MAX)

        b.vx = math.cos(angle) * speed_out  # sign comes from angle
        b.vy = math.sin(angle) * speed_out

    def on_draw(self, surface: pygame.Surface) -> None:
        # Midline (dashed)
        for y in range(0, self.h, 20):
            pygame.draw.rect(surface, MIDLINE_COLOR,
                             (self.mid_x - 2, y, 4, 12))

        # Scores
        draw_text(surface, f"{self.score_l}",
                  (self.mid_x - 80, 24), HUD_COLOR, size=48)
        draw_text(surface, f"{self.score_r}",
                  (self.mid_x + 48, 24), HUD_COLOR, size=48)
        draw_text(surface, "Space/Enter: serve • C: calibrate",
                  (20, self.h - 36), (200, 200, 200), size=20)

        # Victory screen
        if self.score_l >= self.winning_score or self.score_r >= self.winning_score:
            winner = "Left" if self.score_l > self.score_r else "Right"
            draw_text(surface, f"{winner} Wins!", (self.mid_x -
                      110, self.h // 2 - 20), WIN_FLASH_COLOR, size=36)
            draw_text(surface, "Press Space/Enter to restart",
                      (self.mid_x - 170, self.h // 2 + 16), HUD_COLOR, size=22)
            return

        # Paddles
        pygame.draw.rect(surface, PADDLE_COLOR, self.left.rect(),
                         border_radius=PADDLE_BORDER_RADIUS)
        pygame.draw.rect(surface, PADDLE_COLOR, self.right.rect(),
                         border_radius=PADDLE_BORDER_RADIUS)

        # Ball
        if self.ball:
            b = self.ball
            pygame.draw.rect(surface, BALL_COLOR, (int(
                b.x - b.size / 2), int(b.y - b.size / 2), b.size, b.size))

        # Serve message
        if getattr(self, "awaiting_serve", False) and pygame.time.get_ticks() - self.last_point_time >= SERVE_DELAY_MS:
            draw_text(surface, "Serve!", (self.mid_x - 40, 64),
                      HUD_COLOR, size=28)

    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
            if self.score_l >= self.winning_score or self.score_r >= self.winning_score:
                # restart match
                self.score_l = 0
                self.score_r = 0
                self.serving_side = random.choice(("left", "right"))
                self._serve(reset_speed=True)
            elif getattr(self, "awaiting_serve", False):
                if self.ball:
                    self.ball.speed = BALL_SPEED_START
                self.awaiting_serve = False

    def on_unload(self) -> None:
        pass


def get_game():
    return Pong()
