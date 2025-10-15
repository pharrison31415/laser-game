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
WINNING_SCORE = 7             # can be overridden by manifest.options.winning_score
PADDLE_W_RATIO = 0.014        # paddle width relative to screen width
PADDLE_H_RATIO = 0.18         # paddle height relative to screen height
PADDLE_EDGE_MARGIN = 18       # px from screen edges

BALL_SIZE = 12                # square ball (px)
BALL_SPEED_START = 0.40       # px/ms initial speed
BALL_SPEED_MAX = 1.4          # px/ms clamp
BALL_SPEED_RAMP = 1.04        # multiply on each paddle hit
BALL_ANGLE_MAX = math.radians(60)  # max deflection from horizontal

SERVE_DELAY_MS = 900          # delay after a point before allowing serve
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

    def clamp(self, h: int):
        half = self.h // 2
        self.y = max(half, min(h - half, self.y))


@dataclass
class Ball:
    x: float
    y: float
    vx: float
    vy: float
    size: int
    speed: float  # magnitude of velocity


class Pong(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.manifest = manifest
        self.w, self.h = ctx.screen_size
        self.mid_x = self.w // 2

        # Read options
        self.winning_score = int(manifest.get(
            "options", {}).get("winning_score", WINNING_SCORE))

        # Geometry
        pw = max(8, int(self.w * PADDLE_W_RATIO))
        ph = max(34, int(self.h * PADDLE_H_RATIO))
        self.left = Paddle(x=PADDLE_EDGE_MARGIN + pw //
                           2, y=self.h/2, w=pw, h=ph)
        self.right = Paddle(
            x=self.w - (PADDLE_EDGE_MARGIN + pw//2), y=self.h/2, w=pw, h=ph)

        # Ball and scoring
        self.ball: Optional[Ball] = None
        self.score_l = 0
        self.score_r = 0
        self.last_point_time = 0
        self.serving_side = random.choice(("left", "right"))  # who serves next

        self._serve(reset_speed=True)

    # ------------- helpers -------------
    def _serve(self, reset_speed: bool):
        now = pygame.time.get_ticks()
        self.last_point_time = now
        # center ball, stopped until serve key/laser bump
        speed = BALL_SPEED_START if reset_speed else min(
            self._ball_speed(), BALL_SPEED_MAX)
        # choose a shallow-ish angle away from serving paddle
        angle = random.uniform(SERVE_MIN_ANGLE, BALL_ANGLE_MAX)
        if self.serving_side == "left":
            dir_x = 1
        else:
            dir_x = -1
        angle = angle if dir_x > 0 else math.pi - angle
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        # stationary until serve: we'll set speed after serve
        self.ball = Ball(x=self.w/2, y=self.h/2, vx=vx,
                         vy=vy, size=BALL_SIZE, speed=0.0)

        # Require a serve action (Space/Enter or a laser detected on serving half)
        self.awaiting_serve = True

    def _ball_speed(self) -> float:
        return BALL_SPEED_START if not self.ball else max(abs(self.ball.vx), abs(self.ball.vy), self.ball.speed)

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

    def _update_paddle_from_laser(self, paddle: Paddle, target_y: Optional[float]):
        if target_y is not None:
            paddle.y = float(target_y)
            paddle.clamp(self.h)

    def _serve_if_ready(self, frame: FrameData):
        # Allow serve after delay; any red point on the serving half or Space/Enter
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

    # ------------- loop hooks -------------
    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        # Paddle control
        lpts = self._points_in_half(frame, left=True)
        rpts = self._points_in_half(frame, left=False)

        ly = self._laser_target_y(lpts)
        ry = self._laser_target_y(rpts)

        self._update_paddle_from_laser(self.left, ly)
        self._update_paddle_from_laser(self.right, ry)

        # Serve logic
        self._serve_if_ready(frame)

        # Ball physics
        if not self.ball:
            return
        b = self.ball

        # If awaiting serve, ball stays at center but we let vx/vy aim
        if self.awaiting_serve:
            b.x = self.w/2
            b.y = self.h/2
            return

        # Integrate
        b.x += b.vx * dt_ms
        b.y += b.vy * dt_ms

        # Top/bottom walls
        if b.y <= 0 + b.size/2:
            b.y = 0 + b.size/2
            b.vy = abs(b.vy)
        elif b.y >= self.h - b.size/2:
            b.y = self.h - b.size/2
            b.vy = -abs(b.vy)

        # Left paddle collision
        if b.x - b.size/2 <= self.left.rect().right and b.x > self.left.rect().right - 24:
            if self.left.rect().colliderect(pygame.Rect(int(b.x - b.size/2), int(b.y - b.size/2), b.size, b.size)):
                # reflect
                offset = (b.y - self.left.y) / (self.left.h/2)
                offset = max(-1.0, min(1.0, offset))
                angle = offset * BALL_ANGLE_MAX
                speed = min((math.hypot(b.vx, b.vy) or BALL_SPEED_START)
                            * BALL_SPEED_RAMP, BALL_SPEED_MAX)
                b.vx = abs(math.cos(angle) * speed)
                b.vy = math.sin(angle) * speed
                b.x = self.left.rect().right + b.size/2 + 0.5

        # Right paddle collision
        if b.x + b.size/2 >= self.right.rect().left and b.x < self.right.rect().left + 24:
            if self.right.rect().colliderect(pygame.Rect(int(b.x - b.size/2), int(b.y - b.size/2), b.size, b.size)):
                offset = (b.y - self.right.y) / (self.right.h/2)
                offset = max(-1.0, min(1.0, offset))
                angle = math.pi - (offset * BALL_ANGLE_MAX)
                speed = min((math.hypot(b.vx, b.vy) or BALL_SPEED_START)
                            * BALL_SPEED_RAMP, BALL_SPEED_MAX)
                b.vx = -abs(math.cos(angle) * speed)
                b.vy = math.sin(angle) * speed
                b.x = self.right.rect().left - b.size/2 - 0.5

        # Scoring (ball out of bounds)
        if b.x < -b.size:  # missed left
            self._reset_point(scored_by="right")
        elif b.x > self.w + b.size:  # missed right
            self._reset_point(scored_by="left")

    def on_draw(self, surface: pygame.Surface) -> None:
        # Midline
        for y in range(0, self.h, 20):
            pygame.draw.rect(surface, MIDLINE_COLOR,
                             (self.mid_x - 2, y, 4, 12))

        # Scores
        draw_text(surface, f"{self.score_l}",
                  (self.mid_x - 80, 24), HUD_COLOR, size=48)
        draw_text(surface, f"{self.score_r}",
                  (self.mid_x + 48, 24), HUD_COLOR, size=48)
        draw_text(surface, "Press Space/Enter to serve • C to calibrate",
                  (20, self.h - 36), (200, 200, 200), size=20)

        # Victory
        if self.score_l >= self.winning_score or self.score_r >= self.winning_score:
            winner = "Left" if self.score_l > self.score_r else "Right"
            draw_text(surface, f"{winner} Wins!", (self.mid_x -
                      110, self.h//2 - 20), WIN_FLASH_COLOR, size=36)
            draw_text(surface, "Press Space/Enter to restart",
                      (self.mid_x - 170, self.h//2 + 16), HUD_COLOR, size=22)
            return

        # Paddles
        pygame.draw.rect(surface, PADDLE_COLOR,
                         self.left.rect(), border_radius=4)
        pygame.draw.rect(surface, PADDLE_COLOR,
                         self.right.rect(), border_radius=4)

        # Ball (during serve sits at center)
        if self.ball:
            b = self.ball
            pygame.draw.rect(surface, BALL_COLOR, (int(
                b.x - b.size/2), int(b.y - b.size/2), b.size, b.size))

        # Serve message
        if getattr(self, "awaiting_serve", False) and pygame.time.get_ticks() - self.last_point_time >= SERVE_DELAY_MS:
            draw_text(surface, "Serve!", (self.mid_x - 40, 64),
                      HUD_COLOR, size=28)

    def on_event(self, event: pygame.event.Event) -> None:
        # Space/Enter serves or restarts after victory
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
