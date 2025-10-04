from engine.app.loop import run_game
import argparse
import sys
from pathlib import Path
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Laser Platform Launcher")
    parser.add_argument("--game", required=True,
                        help="Game folder name under games/")
    parser.add_argument("--profile", default="default",
                        help="Calibration profile name")
    parser.add_argument("--preview", action="store_true",
                        help="Show camera preview window")
    parser.add_argument("--colors", default="red",
                        help='Comma list of colors to track (red,green,blue)')
    parser.add_argument("--max-points", type=int, default=3,
                        help="Top-N points per color")
    parser.add_argument("--screen", default="1280x720",
                        help="Screen size WxH, e.g. 1280x720")
    parser.add_argument("--cam-index", type=int, default=0,
                        help="OpenCV camera index")
    parser.add_argument("--mirror", action="store_true",
                        help="Mirror the game window horizontally")
    args = parser.parse_args()

    w, h = map(int, args.screen.lower().split("x"))

    run_game(
        game_id=args.game,
        screen_size=(w, h),
        colors=[c.strip() for c in args.colors.split(",") if c.strip()],
        max_points_per_color=args.max_points,
        cam_index=args.cam_index,
        profile=args.profile,
        show_preview=args.preview,
        mirror=args.mirror,
    )


if __name__ == "__main__":
    main()
