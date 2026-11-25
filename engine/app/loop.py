from __future__ import annotations
import sys
import traceback
import time
from pathlib import Path
import cv2
import pygame

from engine.api.config import EngineConfig
from engine.api.frame_data import FrameData
from engine.app.context import Context
from engine.app.loader import load_game_manifest, load_game_module
from engine.app import ui
from engine.input.debug_points import DebugPointInjector
from engine.video.camera import Camera, CameraWorker
from engine.detect.color_tracker import ColorTracker
from engine.calib.homography import HomographyStore
from engine.input.laser_input import LaserInput


GAMES_DIR = Path(__file__).resolve().parents[2] / "games"
MENU_DEBUG = {"enabled": True, "buttons": {"left": "red"}}


class Session:
    """The current game (if any) and which screen is showing: the game itself,
    its pause menu, or the game-select menu."""

    def __init__(self, ctx: Context, cfg: EngineConfig, games: list[dict]):
        self.ctx, self.cfg, self.games = ctx, cfg, games
        self.fonts = ui.Fonts(ctx.screen_size[1])
        self.pause_button = ui.PauseButton(ctx.screen_size)
        self.menu_injector = DebugPointInjector(cfg, MENU_DEBUG)
        self.mode = "menu"
        self.game = None
        self.game_id: str | None = None
        self.manifest: dict = {}
        self.injector = self.menu_injector
        self.overlay: ui.Menu | None = None
        self.frozen: pygame.Surface | None = None   # last game frame, shown while paused
        self.block_until_release = False             # keep a UI press from reaching the game
        self.open_menu()

    # -- transitions ----------------------------------------------------------------
    def unload(self):
        if self.game is not None:
            try:
                self.game.on_unload()
            finally:
                self.game = None

    def load(self, game_id: str) -> bool:
        self.unload()
        try:
            game_root = GAMES_DIR / game_id
            manifest = load_game_manifest(game_root)
            game = load_game_module(game_root).get_game()
            self.ctx.resources = {}
            game.on_load(self.ctx, manifest)
        except Exception:
            print(f"ERROR: could not load game {game_id!r}:", file=sys.stderr)
            traceback.print_exc()
            return False
        self.game, self.game_id, self.manifest = game, game_id, manifest
        self.injector = DebugPointInjector(self.cfg, manifest.get("debug_click", {}) or {})
        pygame.display.set_caption(f"Laser Platform – {manifest.get('title', game_id)}")
        self.mode, self.overlay = "game", None
        self.block_until_release = True
        return True

    def open_menu(self):
        self.unload()
        self.mode = "menu"
        self.overlay = ui.game_menu(self.ctx.screen_size, self.fonts, self.games)
        self.injector = self.menu_injector
        pygame.display.set_caption("Laser Platform")

    def pause(self, frame: pygame.Surface):
        self.mode = "paused"
        self.frozen = frame.copy()
        self.overlay = ui.pause_menu(self.ctx.screen_size, self.fonts,
                                     self.manifest.get("title", self.game_id))

    def resume(self):
        self.mode, self.overlay, self.frozen = "game", None, None
        self.block_until_release = True

    def act(self, action: str | None) -> bool:
        """Run a menu action. Returns False to quit the program."""
        if action == "resume":
            self.resume()
        elif action == "restart":
            if not self.load(self.game_id):
                self.open_menu()
        elif action == "menu":
            self.open_menu()
        elif action and action.startswith("play:"):
            if not self.load(action[5:]):
                self.open_menu()
        elif action == "quit":
            return False
        return True

    def key_action(self, key) -> str | None:
        """Engine keys. Games never see Esc (it pauses) or, while a menu is up, any key."""
        if self.mode == "game":
            return "pause" if key == pygame.K_ESCAPE else None
        if self.mode == "paused":
            return {pygame.K_ESCAPE: "resume", pygame.K_p: "resume",
                    pygame.K_r: "restart", pygame.K_m: "menu"}.get(key)
        # game-select menu: Esc quits, 1-9 picks a game
        if key == pygame.K_ESCAPE:
            return "quit"
        if pygame.K_1 <= key <= pygame.K_9 and key - pygame.K_1 < len(self.games):
            return "play:" + self.games[key - pygame.K_1]["id"]
        return None

    # -- per frame -------------------------------------------------------------------------
    def frame(self, dt: float, points_by_color: dict, surface: pygame.Surface) -> bool:
        all_points = [p for pts in points_by_color.values() for p in pts]

        if self.mode == "game":
            if self.pause_button.update(dt, all_points, armed=not self.block_until_release):
                self.pause(surface)       # surface still holds the previous game frame
                return self.frame(0, points_by_color, surface)
            if self.block_until_release:
                if not all_points:
                    self.block_until_release = False
                game_points = {c: [] for c in points_by_color}
            else:
                game_points = self.pause_button.filter(points_by_color)
            caps = self.manifest.get("max_points_per_color", {}) or {}
            game_points = {c: pts[:int(caps.get(c, 0))] for c, pts in game_points.items()}
            surface.fill(ui.BG)
            self.game.on_update(dt, FrameData(timestamp=time.time(), points_by_color=game_points))
            self.game.on_draw(surface)
            self.pause_button.draw(surface)
            return True

        # a menu is up
        action = self.overlay.update(dt, all_points)
        if self.mode == "paused":
            surface.blit(self.frozen, (0, 0))
            shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            shade.fill((8, 9, 12, 200))
            surface.blit(shade, (0, 0))
        else:
            surface.fill(ui.BG)
        self.overlay.draw(surface)
        for p in all_points:       # show where the laser is, since nothing else does here
            pygame.draw.circle(surface, ui.FILL, (int(p.x), int(p.y)),
                               max(8, int(12 * self.fonts.k)), 2)
        return self.act(action)


def run_game(
    game_id: str | None,
    screen_size: tuple[int, int],
    cam_index: int,
    show_preview: bool,
    mirror: bool = False,
    debug: bool = False,
    exposure: float | None = None,
    stats: bool = False,
    camera: bool = True,
):
    """Run the platform. Starts in game_id, or at the game-select menu if None.
    camera=False: don't open the camera or look for laser dots at all; the mouse
    (as with --debug) and keyboard are the only input."""
    if not camera:
        debug = True
    pygame.init()
    pygame.display.set_caption("Laser Platform")
    screen = pygame.display.set_mode(screen_size)
    clock = pygame.time.Clock()

    cfg = EngineConfig(
        screen_size=screen_size,
        cam_index=cam_index,
        show_preview=show_preview,
        mirror=mirror,
        debug=debug,
    )

    games = ui.list_games(GAMES_DIR, load_game_manifest)
    if game_id is not None and game_id not in {g["id"] for g in games}:
        print(f"ERROR: no game {game_id!r} under games/ "
              f"(have: {', '.join(g['id'] for g in games)})", file=sys.stderr)
        pygame.quit()
        return

    # camera & detection
    # OpenCV's thread pool busy-waits between frames: with the default (one thread
    # per core) the game used ~4 cores of CPU for no gain. Detection takes ~5 ms
    # single-threaded, well within the 33 ms between camera frames.
    # Detect every color any game uses (the menus accept any of them); each game
    # then only receives its own colors, capped by its manifest.
    colors = sorted({c for g in games for c in g["manifest"].get("colors", [])} or {"red"})
    cam = tracker = worker = None
    H = None
    if camera:
        cv2.setNumThreads(1)
        cam = Camera(index=cam_index, target_size=(1280, 720), fps=30, exposure=exposure)
        if not cam.open():
            print("ERROR: could not open camera", file=sys.stderr)
            pygame.quit()
            return
        print(f"camera: {cam.describe()}")

        tracker = ColorTracker(colors=colors, show_preview=show_preview)
        H_store = HomographyStore()
        H, corners_cam = H_store.load()
        if corners_cam:
            tracker.set_preview_corners_cam(corners_cam)
        else:
            tracker.set_preview_corners_from_H(H, screen_size)

        # Capture + detection run on a background thread; the render loop below
        # never waits for the camera.
        worker = CameraWorker(cam, tracker.detect)
        worker.start()
    else:
        print("camera: off (--no-camera); use the mouse to play")

    # Pass mirror to input layer so points are mirrored for gameplay
    max_points = {c: 3 for c in colors}
    for g in games:
        for c, n in (g["manifest"].get("max_points_per_color") or {}).items():
            max_points[c] = max(max_points.get(c, 0), int(n))
    input_layer = LaserInput(max_points=max_points, H=H, mirror=mirror)

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

    session = Session(ctx, cfg, games)
    if game_id is not None and not session.load(game_id):
        session.open_menu()

    running = True
    frames, stats_t, stats_cam, stats_det = 0, time.time(), 0, 0
    try:
        while running:
            dt = clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    action = session.key_action(event.key)
                    if action == "pause":
                        session.pause(render_surface)
                        continue
                    if action is not None:
                        running = session.act(action)
                        continue
                    if event.key == pygame.K_c and camera:
                        worker.set_detection_enabled(False)
                        H = tracker.auto_calibrate(
                            screen, screen_size, worker)
                        worker.set_detection_enabled(True)
                        corners = getattr(tracker, "_corners_cam", [])
                        H_store.save(H, corners_cam=corners if len(
                            corners) == 4 else None)
                        input_layer.set_homography(H)
                        if len(corners) == 4:
                            tracker.set_preview_corners_cam(corners)
                        else:
                            tracker.set_preview_corners_from_H(H, screen_size)

                # Debug injector
                session.injector.handle_pygame_event(event, screen_size)

                if session.mode == "game":
                    session.game.on_event(event)

            # Latest laser detections from the camera thread (may repeat
            # between camera frames; the game renders at its own rate)
            detections = worker.latest() if camera else {}
            if camera:
                tracker.present_preview()
            points_by_color = input_layer.map_and_select(
                detections, screen_size)

            # Merge synthetic debug points
            synthetic = session.injector.emit_points()
            for color, pts in synthetic.items():
                merged = (points_by_color.get(color, []) + pts)
                merged.sort(key=lambda p: p.intensity, reverse=True)
                points_by_color[color] = merged

            if not running:
                break
            running = session.frame(dt, points_by_color, render_surface)
            pygame.draw.rect(render_surface, (220, 220, 220),
                             (8, 8, screen_size[0] - 16, screen_size[1] - 16), 1)

            # Present to window
            if mirror:
                flipped = pygame.transform.flip(render_surface, True, False)
                screen.blit(flipped, (0, 0))

            pygame.display.flip()

            if stats and camera:
                frames += 1
                now = time.time()
                if now - stats_t >= 5.0:
                    span = now - stats_t
                    cam_frames, det_frames = worker.frames_captured, worker.frames_detected
                    print(f"render {frames / span:5.1f} fps   "
                          f"camera {(cam_frames - stats_cam) / span:5.1f} fps   "
                          f"detect {(det_frames - stats_det) / span:5.1f} fps")
                    frames, stats_t = 0, now
                    stats_cam, stats_det = cam_frames, det_frames

    finally:
        if camera:
            worker.stop()
            cam.close()
            tracker.teardown()
        session.unload()
        pygame.quit()
