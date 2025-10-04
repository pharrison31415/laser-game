import random
import math
import pygame
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from engine.api import Game, FrameData
from engine.render.shapes import draw_text


# Start screen
START_TARGET_RADIUS = 70           # px for the "shoot here" target
HOLD_TO_START_MS = 1000            # how long the laser must stay on the target

# Gameplay difficulty
START_RADIUS = 90                  # initial mole radius (px)
START_DURATION_SEC = 3.0           # initial mole lifetime (seconds)
RADIUS_DECAY_PER_STAGE = 0.75      # radius multiplier per stage
DURATION_DECAY_PER_STAGE = 0.75    # lifetime multiplier per stage
MIN_RADIUS = 14                    # px
MIN_DURATION_SEC = 0.45            # seconds
TARGETS_PER_STAGE = 6              # moles per stage (hit or miss)

# UX
EDGE_MARGIN = 24                   # keep targets off the edges
HIT_POP_DELAY_MS = 1500            # delay before next mole after hit/miss
MISS_PENALTY = 0                   # score change on miss
HUD_COLOR = (230, 230, 230)
MOLE_COLOR = (50, 200, 120)
MOLE_MISSED_COLOR = (80, 80, 80)
START_TARGET_COLOR = (70, 180, 110)
START_RING_COLOR = (235, 235, 235)


@dataclass
class Mole:
    x: float
    y: float
    r: float
    expires_at_ms: int
    alive: bool = True
    missed: bool = False


class GameState(Enum):
    Start = 1
    Playing = 2


class WhackAMole(Game):
    def on_load(self, ctx, manifest):
        self.ctx = ctx
        self.manifest = manifest

        random.seed()

        self.state: GameState = GameState.Start
        w, h = ctx.screen_size
        self.start_center = (w // 2, h // 2)
        self._start_hold_ms = 0  # how long the laser has been on the start target

        # Gameplay vars (initialized when game actually starts)
        self.stage = 1
        self.score = 0
        self.stage_attempts = 0
        self.mole: Optional[Mole] = None
        self.next_spawn_ms: int = 0

    # ------------- helpers -------------
    def _begin_game(self):
        # Reset gameplay stats
        self.stage = 1
        self.score = 0
        self.stage_attempts = 0
        self.mole = None
        self.next_spawn_ms = 0
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
        self.mole = Mole(x=x, y=y, r=r, expires_at_ms=now +
                         lifetime, alive=True, missed=False)
        self.stage_attempts += 1

    def _advance_stage_if_needed(self):
        per_stage = int(self.manifest.get("options", {}).get(
            "targets_per_stage", TARGETS_PER_STAGE))
        if self.stage_attempts >= per_stage:
            self.stage += 1
            self.stage_attempts = 0

    # ------------- loop hooks -------------
    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        now = pygame.time.get_ticks()

        if self.state == GameState.Start:
            # Hold-to-start logic: keep the laser on the start target for HOLD_TO_START_MS
            reds = frame.points_by_color.get("red", [])
            if reds:
                for p in reds:
                    dx = p.x - self.start_center[0]
                    dy = p.y - self.start_center[1]
                    if dx * dx + dy * dy <= START_TARGET_RADIUS * START_TARGET_RADIUS:
                        self._start_hold_ms += dt_ms
                        break
                else:
                    # had reds but none in circle
                    self._start_hold_ms = 0
            else:
                self._start_hold_ms = 0

            if self._start_hold_ms >= HOLD_TO_START_MS:
                self._begin_game()
            return  # don't run gameplay while on start screen

        # --------- playing ---------
        if self.mole is None and now >= self.next_spawn_ms:
            self._advance_stage_if_needed()
            self._spawn_new_mole()

        m = self.mole
        if not m:
            return

        # Miss check
        if m.alive and now >= m.expires_at_ms:
            m.alive = False
            m.missed = True
            self.score += MISS_PENALTY
            self.mole = None
            self.next_spawn_ms = now + HIT_POP_DELAY_MS
            return

        # Hit test against red points
        reds = frame.points_by_color.get("red", [])
        if m.alive and reds:
            r2 = m.r * m.r
            for p in reds:
                dx = p.x - m.x
                dy = p.y - m.y
                if dx * dx + dy * dy <= r2:
                    # Hit!
                    self.score += 1
                    m.alive = False
                    self.mole = None
                    self.next_spawn_ms = now + HIT_POP_DELAY_MS
                    break

    def on_draw(self, surface: pygame.Surface) -> None:
        if self.state == GameState.Start:
            self._draw_start_screen(surface)
            return

        draw_text(
            surface, f"Stage {self.stage} | Score: {self.score}", (20, 16), HUD_COLOR, size=26)


        # Draw active mole + lifetime ring
        m = self.mole
        if not m:
            return

        now = pygame.time.get_ticks()
        color = MOLE_COLOR if m.alive else MOLE_MISSED_COLOR
        pygame.draw.circle(
            surface, color, (int(m.x), int(m.y)), int(m.r), width=2)

        # lifetime ring (countdown)
        total = self._current_duration_ms()
        remaining = max(0, m.expires_at_ms - now)
        pct = remaining / total if total > 0 else 0.0
        pct = max(0.0, min(1.0, pct))
        ring_w = 2
        rr = int(m.r + ring_w + 10)

        # Start and end arc angles
        start_angle = 0.5 * math.pi
        end_angle = start_angle + 2 * math.pi * pct

        rect = pygame.Rect(m.x - rr, m.y - rr, rr * 2, rr * 2)
        pygame.draw.arc(surface, (235, 235, 235), rect,
                        start_angle, end_angle, ring_w)

    def _draw_start_screen(self, surface: pygame.Surface) -> None:
        w, h = self.ctx.screen_size
        cx, cy = self.start_center

        # Title & tips
        draw_text(surface, "Whack-a-Mole", (20, 20), HUD_COLOR, size=32)
        draw_text(surface, "Aim a red laser at the target to start",
                  (20, 60), (210, 210, 210), size=22)

        # Pulsing target
        t = pygame.time.get_ticks() * 0.002  # small pulse
        pulse = 1.0 + 0.07 * math.sin(t)
        r = int(START_TARGET_RADIUS * pulse)

        # filled circle
        pygame.draw.circle(surface, START_TARGET_COLOR, (cx, cy), r, width=4)

        # ring shows hold progress
        pct = min(1.0, self._start_hold_ms / HOLD_TO_START_MS) if HOLD_TO_START_MS > 0 else 1.0
        ring_r = int(r + 10)
        ring_w = 2

        # Start and end angles for the arc (start at top, go clockwise)
        start_angle = 0.5 * math.pi
        end_angle = start_angle + 2 * math.pi * pct

        rect = pygame.Rect(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
        pygame.draw.arc(surface, START_RING_COLOR, rect, start_angle, end_angle, ring_w)

        # label
        msg = "Shoot here to start"
        sz = 26
        # center text roughly
        draw_text(surface, msg, (cx - 140, cy - r - 40),
                  (240, 240, 240), size=sz)

    def on_event(self, event: pygame.event.Event) -> None:
        # Keyboard fallback: space/enter starts
        if self.state == GameState.Start and event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._begin_game()

    def on_unload(self) -> None:
        pass


def get_game():
    return WhackAMole()
