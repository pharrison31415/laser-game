from __future__ import annotations
import sys
import time
from pathlib import Path
import pygame

from engine.api.config import EngineConfig
from engine.api.frame_data import FrameData
from engine.app.context import Context
from engine.app.loader import load_game_manifest, load_game_module
from engine.video.camera import Camera
from engine.detect.color_tracker import ColorTracker
from engine.calib.homography import HomographyStore
from engine.input.laser_input import LaserInput


def run_game(
    game_id: str,
    screen_size: tuple[int, int],
    colors: list[str],
    max_points_per_color: int,
    cam_index: int,
    profile: str,
    show_preview: bool,
    mirror: bool = False,
):
    pygame.init()
    pygame.display.set_caption(f"Laser Platform – {game_id}")
    screen = pygame.display.set_mode(screen_size)
    clock = pygame.time.Clock()

    cfg = EngineConfig(
        screen_size=screen_size,
        colors=colors,
        max_points_per_color=max_points_per_color,
        cam_index=cam_index,
        profile=profile,
        show_preview=show_preview,
        mirror=mirror,
    )

    # load game
    games_dir = Path(__file__).resolve().parents[2] / "games"
    game_root = games_dir / game_id
    manifest = load_game_manifest(game_root)
    module = load_game_module(game_root)
    game = module.get_game()

    # camera & detection
    cam = Camera(index=cam_index, target_size=(1280, 720), fps=60)
    if not cam.open():
        print("ERROR: could not open camera", file=sys.stderr)
        pygame.quit()
        return

    tracker = ColorTracker(
        colors=colors, show_preview=show_preview, preview_name="Preview")
    H_store = HomographyStore(profile_name=profile)
    H, corners_cam = H_store.load()
    if corners_cam:
        tracker.set_preview_corners_cam(corners_cam)
    else:
        tracker.set_preview_corners_from_H(H, screen_size)

    # Pass mirror to input layer so points are mirrored for gameplay
    input_layer = LaserInput(
        max_points_per_color=max_points_per_color, H=H)

    # Render target: draw to off-screen if mirroring, otherwise draw directly to screen
    render_surface = screen if not mirror else pygame.Surface(
        screen_size).convert()

    ctx = Context(
        screen=render_surface,
        clock=clock,
        cfg=cfg,
        resources={},
        screen_size=screen_size,
    )

    game.on_load(ctx, manifest)

    running = True
    try:
        while running:
            dt = clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_c:
                        H = tracker.auto_calibrate(
                            screen, screen_size, cam)
                        corners = getattr(tracker, "_corners_cam", [])
                        H_store.save(H, corners_cam=corners if len(
                            corners) == 4 else None)
                        input_layer.set_homography(H)
                        if len(corners) == 4:
                            tracker.set_preview_corners_cam(corners)
                        else:
                            tracker.set_preview_corners_from_H(H, screen_size)
                game.on_event(event)

            ok, frame_bgr = cam.read()
            if not ok:
                continue

            detections = tracker.detect(frame_bgr)
            points_by_color = input_layer.map_and_select(
                detections, screen_size)
            frame_data = FrameData(timestamp=time.time(),
                                   points_by_color=points_by_color)

            # ---- draw to render_surface ----
            render_surface.fill((12, 14, 18))
            game.on_update(dt, frame_data)
            game.on_draw(render_surface)
            pygame.draw.rect(render_surface, (220, 220, 220),
                             (8, 8, screen_size[0] - 16, screen_size[1] - 16), 1)

            # ---- present to window ----
            if mirror:
                flipped = pygame.transform.flip(render_surface, True, False)
                screen.blit(flipped, (0, 0))

            pygame.display.flip()

    finally:
        cam.close()
        tracker.teardown()
        game.on_unload()
        pygame.quit()
