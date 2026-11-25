import argparse
import sys
from pathlib import Path
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.app.loop import run_game


def main():
    parser = argparse.ArgumentParser(description="Laser Platform Launcher")
    parser.add_argument("--game", default=None,
                        help="Game folder name under games/ to start in (default: the game-select menu)")
    parser.add_argument("--preview", action="store_true", help="Show camera preview window")
    parser.add_argument("--screen", default="1280x720", help="Screen size WxH, e.g. 1280x720")
    parser.add_argument("--cam-index", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--mirror", action="store_true", help="Mirror the game window horizontally")
    parser.add_argument("--debug", action="store_true", help="Enable mouse clicks to inject synthetic points")
    parser.add_argument("--exposure", type=float, default=None,
                        help="Fixed camera exposure in driver units (V4L2: 100us steps, e.g. 150 = 15ms). "
                             "Default: camera auto exposure")
    parser.add_argument("--stats", action="store_true", help="Print render and camera fps every 5 seconds")
    parser.add_argument("--no-camera", action="store_true",
                        help="Don't use the camera or look for laser dots; play with the mouse "
                             "(implies --debug) and keyboard")
    args = parser.parse_args()

    w, h = map(int, args.screen.lower().split("x"))

    run_game(
        game_id=args.game,
        screen_size=(w, h),
        cam_index=args.cam_index,
        show_preview=args.preview,
        mirror=args.mirror,
        debug=args.debug,
        exposure=args.exposure,
        stats=args.stats,
        camera=not args.no_camera,
    )


if __name__ == "__main__":
    main()
