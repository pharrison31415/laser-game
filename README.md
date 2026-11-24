# laser-game

This project is a video game platform built with PyGame and OpenCV that uses an extended display and a laser pointer, allowing players to control games by shining the laser on the screen.

## Inspiration

This project was inspired by my father, John Harrison, who developed video games using a similar laser pointer and projector setup.

Each Halloween, he transformed our garage into an arcade, projecting the games onto a suspended bedsheet while trick-or-treaters played _Missle Command_ from our driveway before receiving their candy.

He presented his work at PyCon 2008 -- you can watch his talk on [YouTube](https://www.youtube.com/watch?v=EGSgLuxrgYc).

## Quick Start

This project uses [uv](https://docs.astral.sh/uv/) to manage Python and dependencies. [Install uv](https://docs.astral.sh/uv/getting-started/installation/), then clone the repository and install dependencies:

```
git clone https://github.com/pharrison31415/laser-game.git
cd laser-game
uv sync
```

`uv sync` creates `.venv/` and installs the exact versions pinned in `uv.lock`. It also fetches a suitable Python (3.13+) if you don't have one.

Run pong normally (or include `--debug` to emulate laser dots with mouse clicks):

```
uv run launchers/run.py --preview --game pong
```

Once the program begins, place the game window onto an external display placed in front of the webcam. Press `c` to calibrate. Once it is finished, shoot your lasers at the external display!

Note: It is easier for the computer vision program to find red laser dots in darker environments.

## Games

Games are listed under the `games/` directory:

- `pop-the-balloons`: Shoot the green circles until they all turn gray.
- `quick-draw`: Shoot your half of the screen faster than your opponent. Be careful to not fire too early!
- `whack-a-mole`: Shoot the green circles once they appear. Be quick -- they start to disappear quickly!
- `pong`: The classic arcade game! Shoot lasers at each side of the screen to control each paddle.
- `cube-runner`: Your cube runs on its own -- shine the laser anywhere to jump over spikes, pits, and pillars. Jump pads launch you, orbs give a mid-air jump, and hatched ceilings punish jumping. Endless and randomly generated; the longer you survive, the faster it gets!

## Launcher usage

```
$ uv run launchers/run.py -h
usage: run.py [-h] --game GAME [--preview] [--screen SCREEN]
              [--cam-index CAM_INDEX] [--mirror] [--debug]

Laser Platform Launcher

options:
  -h, --help            show this help message and exit
  --game GAME           Game folder name under games/
  --preview             Show camera preview window
  --screen SCREEN       Screen size WxH, e.g. 1280x720
  --cam-index CAM_INDEX
                        OpenCV camera index
  --mirror              Mirror the game window horizontally
  --debug               Enable mouse clicks to inject synthetic points
```

## Managing dependencies

Dependencies are declared in `pyproject.toml` and locked in `uv.lock` (commit both).

```
uv add <package>          # add a dependency
uv remove <package>       # remove one
uv lock --upgrade         # upgrade everything to the latest allowed versions
uv sync                   # make .venv match the lockfile
```
