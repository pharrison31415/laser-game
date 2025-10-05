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
class HoldCircle:
    cx: int
    cy: int
    r: int


@dataclass
class ShotResult:
    # reaction time relative to go_time; None until fired
    time_ms: Optional[int]
    dnf: bool               # true if exceeded limit
    at_xy: Optional[tuple[int, int]]  # where they shot
    when_ms: Optional[int]  # absolute tick when shot was detected


class Phase(Enum):
    WaitingForReady = 1
    CountdownReady = 2
    CountdownSet = 3
    Armed = 4  # border turns green; waiting for shots
    Results = 5


class QuickDraw(Game):
    def on_load(self, ctx: Context, manifest):
        self.ctx = ctx
        self.manifest = manifest
        self.w, self.h = ctx.screen_size
        self.mid_x = self.w // 2

        # Centered near the bottom
        btn_w = PLAY_AGAIN_WIDTH
        btn_h = PLAY_AGAIN_HEIGHT
        btn_x = (self.w - btn_w) // 2
        btn_y = self.h - btn_h - 60
        self.play_again_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        # Hold circles centered on each half
        self.left_hold = HoldCircle(
            cx=self.w//4,  cy=self.h//2, r=START_TARGET_RADIUS)
        self.right_hold = HoldCircle(
            cx=(self.w*3)//4, cy=self.h//2, r=START_TARGET_RADIUS)

        self._init_state()

    def _init_state(self):
        self.phase: Phase = Phase.WaitingForReady
        self.left_hold_ms: float = 0.0
        self.right_hold_ms: float = 0.0
        self.left_ready_latched: bool = False
        self.right_ready_latched: bool = False

        self.phase_started_ms: int = pygame.time.get_ticks()
        self.go_time_ms: Optional[int] = None
        self.go_delay_ms: int = 0

        self.left_result = ShotResult(
            time_ms=None, dnf=False, at_xy=None, when_ms=None)
        self.right_result = ShotResult(
            time_ms=None, dnf=False, at_xy=None, when_ms=None)

        self.flash_counter: int = 0
        self.last_flash_ms: int = 0
        self.flash_on: bool = False

    # ---------- Helpers ----------
    def _points_in_half(self, frame: FrameData, left: bool):
        reds = frame.points_by_color.get("red", [])
        if left:
            return [p for p in reds if p.x < self.mid_x]
        else:
            return [p for p in reds if p.x >= self.mid_x]

    def _any_point_in_circle(self, pts, cx, cy, r):
        r2 = r * r
        for p in pts:
            dx = p.x - cx
            dy = p.y - cy
            if dx*dx + dy*dy <= r2:
                return p
        return None

    def _advance_phase(self, new_phase: Phase):
        self.phase = new_phase
        self.phase_started_ms = pygame.time.get_ticks()

    # ---------- Update ----------
    def on_update(self, dt_ms: float, frame: FrameData) -> None:
        now = pygame.time.get_ticks()

        # Restart anytime in Results with any laser hit anywhere
        if self.phase == Phase.Results:
            # Look for a red dot inside the replay button
            reds = frame.points_by_color.get("red", [])
            if reds:
                # Slightly padded hit box so it feels easy to click with a jittery laser
                hitbox = self.play_again_rect.inflate(PLAY_AGAIN_HIT_PAD * 2, PLAY_AGAIN_HIT_PAD * 2)
                for p in reds:
                    if hitbox.collidepoint(p.x, p.y):
                        self._init_state()
                        return
            # Handle flashing winner border timing while we wait on replay
            if self.flash_counter < WIN_FLASH_COUNT:
                now = pygame.time.get_ticks()
                if now - self.last_flash_ms >= WIN_FLASH_INTERVAL:
                    self.flash_on = not self.flash_on
                    self.last_flash_ms = now
                    self.flash_counter += 1
            return


        if self.phase == Phase.WaitingForReady:
            # Track hold inside circles
            left_pts = self._points_in_half(frame, left=True)
            right_pts = self._points_in_half(frame, left=False)

            lp = self._any_point_in_circle(
                left_pts,  self.left_hold.cx,  self.left_hold.cy,  self.left_hold.r)
            rp = self._any_point_in_circle(
                right_pts, self.right_hold.cx, self.right_hold.cy, self.right_hold.r)

            # Only accumulate hold time if not yet latched
            if not self.left_ready_latched:
                if lp:
                    self.left_hold_ms += dt_ms
                else:
                    self.left_hold_ms = 0.0

                if self.left_hold_ms >= HOLD_TO_READY_MS:
                    self.left_ready_latched = True

            if not self.right_ready_latched:
                if rp:
                    self.right_hold_ms += dt_ms
                else:
                    self.right_hold_ms = 0.0

                if self.right_hold_ms >= HOLD_TO_READY_MS:
                    self.right_ready_latched = True

            # When both are latched ready (even if not currently holding), move on
            if self.left_ready_latched and self.right_ready_latched:
                self._advance_phase(Phase.CountdownReady)

        elif self.phase == Phase.CountdownReady:
            if now - self.phase_started_ms >= READY_MS:
                self._advance_phase(Phase.CountdownSet)

        elif self.phase == Phase.CountdownSet:
            if now - self.phase_started_ms >= SET_MS:
                # Roll randomized go delay
                delay_sec = random.uniform(GO_DELAY_MIN_SEC, GO_DELAY_MAX_SEC)
                self.go_delay_ms = int(delay_sec * 1000)
                self._advance_phase(Phase.Armed)
                self.go_time_ms = now + self.go_delay_ms
                self.left_result = ShotResult(
                    time_ms=None, dnf=False, at_xy=None, when_ms=None)
                self.right_result = ShotResult(
                    time_ms=None, dnf=False, at_xy=None, when_ms=None)
                self.flash_counter = 0
                self.last_flash_ms = now
                self.flash_on = True  # not used until Results, but init anyway

        elif self.phase == Phase.Armed:
            # Ignore shots before go_time (no false-start penalty in spec; we just ignore)
            reds = frame.points_by_color.get("red", [])
            if not self.go_time_ms:
                self.go_time_ms = now  # fallback

            # Record first valid shot per side occurring at or after go_time
            if now >= self.go_time_ms:
                # Left
                if self.left_result.when_ms is None:
                    lpts = self._points_in_half(frame, left=True)
                    if lpts:
                        # Take the first point (fastest)
                        p = lpts[0]
                        self.left_result.when_ms = now
                        self.left_result.time_ms = now - self.go_time_ms
                        self.left_result.at_xy = (p.x, p.y)

                # Right
                if self.right_result.when_ms is None:
                    rpts = self._points_in_half(frame, left=False)
                    if rpts:
                        p = rpts[0]
                        self.right_result.when_ms = now
                        self.right_result.time_ms = now - self.go_time_ms
                        self.right_result.at_xy = (p.x, p.y)

                # DNF checks
                elapsed_since_go = now - self.go_time_ms
                if elapsed_since_go >= DNF_LIMIT_MS:
                    if self.left_result.when_ms is None:
                        self.left_result.dnf = True
                    if self.right_result.when_ms is None:
                        self.right_result.dnf = True

                # Move to results when both sides have a result (time or DNF)
                def has_outcome(r: ShotResult):
                    return (r.when_ms is not None) or r.dnf

                if (has_outcome(self.left_result) and has_outcome(self.right_result)):
                    self._advance_phase(Phase.Results)
                    self.last_flash_ms = now
                    self.flash_counter = 0
                    self.flash_on = True

        elif self.phase == Phase.Results:
            # Flash winner side a few times
            if self.flash_counter < WIN_FLASH_COUNT:
                if now - self.last_flash_ms >= WIN_FLASH_INTERVAL:
                    self.flash_on = not self.flash_on
                    self.last_flash_ms = now
                    self.flash_counter += 1

        else:
            pass

    # ---------- Draw ----------
    def on_draw(self, surface: pygame.Surface) -> None:
        # Midline
        pygame.draw.line(surface, MIDLINE_COLOR,
                         (self.mid_x, 0), (self.mid_x, self.h), 2)

        # Title
        draw_text(surface, "Quick Draw (Two Players)",
                  (20, 16), HUD_COLOR, size=HUD_FONT_SIZE)

        if self.phase == Phase.WaitingForReady:
            self._draw_hold_targets(surface)
            self._draw_ready_status(surface)
            return

        if self.phase in (Phase.CountdownReady, Phase.CountdownSet):
            self._draw_countdown(surface)
            return

        if self.phase == Phase.Armed:
            self._draw_go_border(surface)
            self._draw_armed_text(surface)
            return

        if self.phase == Phase.Results:
            self._draw_results(surface)
            return

    def _draw_hold_targets(self, surface: pygame.Surface, dim: bool = False):
        # Left
        lw = 4
        color_left = START_TARGET_COLOR if not dim else (90, 90, 90)
        pygame.draw.circle(surface, color_left, (self.left_hold.cx,
                           self.left_hold.cy), self.left_hold.r, lw)
        # pass held progress OR full ring if latched
        self._draw_hold_ring(
            surface, self.left_hold.cx, self.left_hold.cy, self.left_hold.r,
            HOLD_TO_READY_MS if self.left_ready_latched else self.left_hold_ms
        )

        # Right
        color_right = START_TARGET_COLOR if not dim else (90, 90, 90)
        pygame.draw.circle(surface, color_right, (self.right_hold.cx,
                           self.right_hold.cy), self.right_hold.r, lw)
        self._draw_hold_ring(
            surface, self.right_hold.cx, self.right_hold.cy, self.right_hold.r,
            HOLD_TO_READY_MS if self.right_ready_latched else self.right_hold_ms
        )

        # Labels
        draw_text(surface, "Hold to Ready", (self.left_hold.cx - 90,
                  self.left_hold.cy - self.left_hold.r - 36), HUD_COLOR, size=24)
        draw_text(surface, "Hold to Ready", (self.right_hold.cx - 90,
                  self.right_hold.cy - self.right_hold.r - 36), HUD_COLOR, size=24)

    def _draw_hold_ring(self, surface, cx, cy, r, held_ms):
        pct = min(1.0, held_ms / HOLD_TO_READY_MS) if HOLD_TO_READY_MS > 0 else 1.0
        ring_r = int(r + 10)
        rect = pygame.Rect(cx - ring_r, cy - ring_r, ring_r*2, ring_r*2)
        start_angle = 0.5 * math.pi
        end_angle = start_angle + 2 * math.pi * pct
        pygame.draw.arc(surface, START_RING_COLOR,
                        rect, start_angle, end_angle, 2)

    def _draw_ready_status(self, surface):
        ltext = "P1 Ready" if self.left_ready_latched else "P1 Holding..."
        rtext = "P2 Ready" if self.right_ready_latched else "P2 Holding..."
        draw_text(surface, ltext, (20, self.h - 44), READY_COLOR, size=24)
        tw = 220
        draw_text(surface, rtext, (self.w - tw - 20,
                  self.h - 44), READY_COLOR, size=24)

        if self.left_ready_latched and self.right_ready_latched:
            draw_text(surface, "Both ready! Don't move.",
                      (self.mid_x - 160, 60), READY_COLOR, size=24)

    def _draw_countdown(self, surface):
        now = pygame.time.get_ticks()
        if self.phase == Phase.CountdownReady:
            draw_text(surface, "Ready", (self.mid_x - 60, 60),
                      READY_COLOR, size=BIG_FONT_SIZE)
        elif self.phase == Phase.CountdownSet:
            draw_text(surface, "Set", (self.mid_x - 40, 60),
                      SET_COLOR, size=BIG_FONT_SIZE)

    def _draw_go_border(self, surface):
        # Show green border only once the randomized delay has elapsed
        now = pygame.time.get_ticks()
        if self.go_time_ms and now >= self.go_time_ms:
            pygame.draw.rect(surface, GO_BORDER_COLOR, pygame.Rect(
                4, 4, self.w - 8, self.h - 8), width=6)

    def _draw_armed_text(self, surface):
        now = pygame.time.get_ticks()
        if not self.go_time_ms or now < self.go_time_ms:
            draw_text(surface, "...", (self.mid_x - 12, 60),
                      SET_COLOR, size=BIG_FONT_SIZE)
        else:
            draw_text(surface, "FIRE!", (self.mid_x - 60, 60),
                      GO_BORDER_COLOR, size=BIG_FONT_SIZE)

    def _draw_results(self, surface):
        # Winner determination
        l = self.left_result
        r = self.right_result

        # Decide winner (both times present and not DNF)
        left_time = l.time_ms if (
            l.time_ms is not None and not l.dnf) else None
        right_time = r.time_ms if (
            r.time_ms is not None and not r.dnf) else None

        winner = None
        if left_time is not None and right_time is not None:
            if left_time < right_time:
                winner = "left"
            elif right_time < left_time:
                winner = "right"
            else:
                winner = "tie"
        elif left_time is not None and right_time is None:
            winner = "left"
        elif right_time is not None and left_time is None:
            winner = "right"
        elif l.dnf and not r.dnf:
            winner = "right"
        elif r.dnf and not l.dnf:
            winner = "left"
        else:
            winner = "none"

        # Flash winning side border
        if winner in ("left", "right") and self.flash_on:
            if winner == "left":
                rect = pygame.Rect(6, 6, self.mid_x - 12, self.h - 12)
            else:
                rect = pygame.Rect(self.mid_x + 6, 6,
                                   self.mid_x - 12, self.h - 12)
            pygame.draw.rect(surface, WIN_FLASH_COLOR, rect, width=6)

        # Times readout
        y0 = 80

        def fmt_time(t):
            return f"{t:.0f} ms" if t is not None else "--"

        lt = left_time
        rt = right_time
        diff = None
        if lt is not None and rt is not None:
            diff = abs(lt - rt)

        # Labels
        draw_text(surface, "Results", (self.mid_x - 60, 24),
                  HUD_COLOR, size=BIG_FONT_SIZE)
        draw_text(surface, f"P1: {fmt_time(lt)}" + (" (DNF)" if l.dnf else ""),
                  (self.mid_x - 180, y0), HUD_COLOR, size=HUD_FONT_SIZE)
        draw_text(surface, f"P2: {fmt_time(rt)}" + (" (DNF)" if r.dnf else ""),
                  (self.mid_x + 20,  y0), HUD_COLOR, size=HUD_FONT_SIZE)

        if diff is not None:
            draw_text(surface, f"Δ = {diff:.0f} ms", (self.mid_x -
                      45, y0 + 40), HUD_COLOR, size=HUD_FONT_SIZE)

        # Shot dots
        if l.at_xy:
            pygame.draw.circle(surface, (255, 255, 255), l.at_xy, 6)
        if r.at_xy:
            pygame.draw.circle(surface, (255, 255, 255), r.at_xy, 6)

        # Replay button: rectangle + centered label
        pygame.draw.rect(surface, PLAY_AGAIN_COLOR, self.play_again_rect, width=3)

        label = "Shoot here to play again"
        # Rough centering: nudge the text; adjust if your draw_text auto-centers
        text_x = self.play_again_rect.centerx - 170
        text_y = self.play_again_rect.centery - 14
        draw_text(surface, label, (text_x, text_y), PLAY_AGAIN_COLOR, size=24)


    # ---------- Events ----------
    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._init_state()

    def on_unload(self) -> None:
        pass


def get_game():
    return QuickDraw()
