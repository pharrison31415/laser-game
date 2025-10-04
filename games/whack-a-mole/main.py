import random
import math
import pygame
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from engine.api import Game, FrameData
from engine.app.context import Context
from engine.render.shapes import draw_text

from .const import *


@dataclass
class Mole:
    x: float
    y: float
    r: float
    expires_at_ms: int
    hit: bool = False


@dataclass
class HitEffect:
    x: float
    y: float
    expires_at_ms: int


class GameState(Enum):
    Start = 1
    Playing = 2


class WhackAMole(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.manifest = manifest

        # random.seed()

        w, h = ctx.screen_size
        self.start_center = (w // 2, h // 2)

        self._init_game()

    def _init_game(self):
        self.state: GameState = GameState.Start
        self._start_hold_ms = 0
        self.stage = 1
        self.score = 0
        self.stage_mole_count = 0
        self.mole: Optional[Mole] = None
        self.hit_effects: list[HitEffect] = []
        self.next_spawn_ms: int = 0

    def _begin_gameplay(self):
        self.state = GameState.Playing
        self._spawn_new_mole()

    def _current_radius(self) -> float:
        r = START_RADIUS * (RADIUS_DECAY_PER_STAGE ** (self.stage - 1))
        return max(MIN_RADIUS, r)

    def _current_duration_ms(self) -> int:
        sec = START_DURATION_SEC * \
            (DURATION_DECAY_PER_STAGE ** (self.stage - 1))
        sec = max(MIN_DURATION_SEC, sec)
        return int(sec * 1000)

    def _random_position(self, radius: float) -> tuple[int, int]:
        w, h = self.ctx.screen_size
        margin = int(radius + EDGE_MARGIN)
        x = random.randint(margin, max(margin, w - margin))
        y = random.randint(margin, max(margin, h - margin))
        return x, y

    def _spawn_new_mole(self):
        now = pygame.time.get_ticks()
        r = self._current_radius()
        x, y = self._random_position(r)
        lifetime = self._current_duration_ms()
        self.mole = Mole(x=x, y=y, r=r,
                         expires_at_ms=now + lifetime, hit=False)
        self.stage_mole_count += 1

    def _maybe_advance_stage(self):
        if self.stage_mole_count >= TARGETS_PER_STAGE:
            self.stage += 1
            self.stage_mole_count = 0

    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        now = pygame.time.get_ticks()

        if self.state == GameState.Start:
            self._state_start_on_update(dt_ms, frame)
        elif self.state == GameState.Playing:
            self._state_playing_on_update(frame, now)
        else:
            raise ValueError(
                f"self.state is not a member of GameState, its {self.state}")

    def _state_start_on_update(self, dt_ms: float, frame: FrameData):
        # Hold-to-start logic: keep the laser on the start target
        reds = frame.points_by_color.get("red", [])
        if reds:
            for p in reds:
                dx = p.x - self.start_center[0]
                dy = p.y - self.start_center[1]
                if dx * dx + dy * dy <= START_TARGET_RADIUS * START_TARGET_RADIUS:
                    self._start_hold_ms += dt_ms
                    break
            else:
                # Reds, but none in circle
                self._start_hold_ms = 0
        else:
            # No reds
            self._start_hold_ms = 0

        if self._start_hold_ms >= HOLD_TO_START_MS:
            self._begin_gameplay()

    def _state_playing_on_update(self, frame: FrameData, now: int):
        if self.mole is None and now >= self.next_spawn_ms:
            self._maybe_advance_stage()
            self._spawn_new_mole()

        if not self.mole:
            return

        # Expired mole check
        if self.mole.expires_at_ms <= now and not self.mole.hit:
            self.mole = None
            self.next_spawn_ms = now + HIT_POP_DELAY_MS
            return

        # Hit test against red points
        reds = frame.points_by_color.get("red", [])
        if reds:
            r2 = self.mole.r * self.mole.r
            for p in reds:
                dx = p.x - self.mole.x
                dy = p.y - self.mole.y
                if dx * dx + dy * dy <= r2:
                    # Hit!
                    self.mole.hit = True
                    self.score += 1
                    self.hit_effects.append(HitEffect(
                        x=p.x,
                        y=p.y,
                        expires_at_ms=now + HIT_FX_DURATION_MS
                    ))
                    self.mole = None
                    self.next_spawn_ms = now + HIT_POP_DELAY_MS
                    break

        # Update hit effects list
        self.hit_effects = [
            e for e in self.hit_effects if now < e.expires_at_ms]

    def on_draw(self, surface: pygame.Surface) -> None:
        if self.state == GameState.Start:
            self._draw_start_screen(surface)
            return

        # Stage Score
        draw_text(
            surface, f"Stage {self.stage} | Score: {self.score}", (20, 16), HUD_COLOR, size=26)

        # Draw hit effect
        for e in self.hit_effects:
            draw_text(surface, "Hit!", (e.x - 20, e.y - 40),
                      HUD_COLOR, size=HIT_FX_TEXT_SIZE)

        if not self.mole:
            return

        # Draw mole
        pygame.draw.circle(
            surface, MOLE_COLOR, (int(self.mole.x), int(self.mole.y)), int(self.mole.r), width=2)

        # Draw lifetime ring
        self._draw_lifetime_ring(surface)

    def _draw_start_screen(self, surface: pygame.Surface):
        cx, cy = self.start_center

        # HUD text
        draw_text(surface, "Whack-a-Mole", (20, 20), HUD_COLOR, size=32)
        draw_text(surface, "Aim a red laser at the target to start",
                  (20, 60), (210, 210, 210), size=22)

        # Pulsing math
        t = pygame.time.get_ticks() * 0.002
        pulse = 1.0 + 0.07 * math.sin(t)
        r = int(START_TARGET_RADIUS * pulse)

        # Target circle
        pygame.draw.circle(surface, START_TARGET_COLOR, (cx, cy), r, width=4)

        # Arc math
        pct = min(1.0, self._start_hold_ms /
                  HOLD_TO_START_MS) if HOLD_TO_START_MS > 0 else 1.0
        ring_r = int(r + 10)
        ring_w = 2
        start_angle = 0.5 * math.pi
        end_angle = start_angle + 2 * math.pi * pct

        # Draw progress arc
        rect = pygame.Rect(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
        pygame.draw.arc(surface, START_RING_COLOR, rect,
                        start_angle, end_angle, ring_w)

        # Shoot here text
        draw_text(surface, "Shoot here to start", (cx - 140, cy - r - 40),
                  (240, 240, 240), size=26)

    def _draw_lifetime_ring(self, surface: pygame.Surface):
        now = pygame.time.get_ticks()

        # Arithmetic
        total = self._current_duration_ms()
        remaining = max(0, self.mole.expires_at_ms - now)
        pct = remaining / total if total > 0 else 0.0
        pct = max(0.0, min(1.0, pct))
        ring_w = 2
        rr = int(self.mole.r + ring_w + 10)

        # Start and end arc angles
        start_angle = 0.5 * math.pi
        end_angle = start_angle + 2 * math.pi * pct

        # Draw lifetime ring
        rect = pygame.Rect(self.mole.x - rr, self.mole.y - rr, rr * 2, rr * 2)
        pygame.draw.arc(surface, (235, 235, 235), rect,
                        start_angle, end_angle, ring_w)

    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            # Keyboard fallback: space/enter restarts
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._init_game()

    def on_unload(self) -> None:
        pass


def get_game():
    return WhackAMole()
