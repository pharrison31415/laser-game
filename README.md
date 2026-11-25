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

Start the arcade (or include `--debug` to emulate laser dots with mouse clicks):

```
uv run launchers/run.py --preview
```

This opens a game-select menu: hold the laser on a game's card until it fills to play it.
Add `--game pong` to skip the menu and start in a game.

While playing, hold the laser on the pause button in the top-right corner (or press `Esc`)
to pause. The pause menu has Resume, Restart and Menu (back to game select), all chosen
the same way by holding the laser on them, so you can switch games without restarting
the program. In the game-select menu, `Esc` quits.

Once the program begins, place the game window onto an external display placed in front of the webcam. Press `c` to calibrate. Once it is finished, shoot your lasers at the external display!

Note: It is easier for the computer vision program to find red laser dots in darker environments.

## Games

Games are listed under the `games/` directory:

- `pop-the-balloons`: Shoot the green circles until they all turn gray.
- `quick-draw`: Shoot your half of the screen faster than your opponent. Be careful to not fire too early!
- `whack-a-mole`: Shoot the green circles once they appear. Be quick -- they start to disappear quickly!
- `pong`: The classic arcade game! Shoot lasers at each side of the screen to control each paddle.
- `cube-runner`: Your cube runs on its own -- shine the laser anywhere to jump over spikes, pits, and pillars. Jump pads launch you, orbs give a mid-air jump, and hatched ceilings punish jumping. Endless and randomly generated; the longer you survive, the faster it gets!
  The level is a chain of ~10-second sections (Rooftops, Cave, Pillar Hop, Spike Rhythm, ...);
  see [Drawing cube-runner sections](#drawing-cube-runner-sections).
- `rooftop-run`: One-button rooftop runner. You never stop running and keep speeding up; shine the
  laser to jump the gaps between buildings, holding it longer to jump higher. Crates and falling debris
  slow you down; crash through windows, cross girders, and get off crumbling roofs fast. Falling or
  hitting a wall ends the run.

## Launcher usage

```
$ uv run launchers/run.py -h
usage: run.py [-h] [--game GAME] [--preview] [--screen SCREEN]
              [--cam-index CAM_INDEX] [--mirror] [--debug]
              [--exposure EXPOSURE] [--stats] [--no-camera]

Laser Platform Launcher

options:
  -h, --help            show this help message and exit
  --game GAME           Game folder name under games/ to start in (default:
                        the game-select menu)
  --preview             Show camera preview window
  --screen SCREEN       Screen size WxH, e.g. 1280x720
  --cam-index CAM_INDEX
                        OpenCV camera index
  --mirror              Mirror the game window horizontally
  --debug               Enable mouse clicks to inject synthetic points
  --exposure EXPOSURE   Fixed camera exposure in driver units (V4L2: 100us
                        steps, e.g. 150 = 15ms). Default: camera auto exposure
  --stats               Print render and camera fps every 5 seconds
  --no-camera           Don't use the camera or look for laser dots; play with
                        the mouse (implies --debug) and keyboard
```

If the camera runs slowly in a dim room (check with `--stats`), auto exposure is
probably lengthening each frame: try `--exposure 150` and adjust until the laser
dot is still detected reliably.

## Drawing cube-runner sections

Cube-runner levels are chains of sections. Some are generated from themes (one obstacle
family on a steady rhythm), and some are drawn by hand as ASCII art in
`games/cube-runner/sections/*.txt`. To add a section, add a file:

```
title: Rooftops
min_d: 0.2

                                              ^
                         ##########    ##############
               #######   ##########    ##############    #######
     #######   #######   ##########    ##############    #######
-----                                                           --------
```

- `title` is the section's display name (not shown in the game). `min_d` is the difficulty
  (0 to 1, reached at distance 500) from which it can appear. A blank line ends the header.
- One character is one cube. The last line is the ground: `-` is ground, a space is a pit.
- `#` is a block (over a pit it becomes a pillar), `=` is a deadly hatched ceiling, `^` is a spike,
  `v` is a hanging spike, `J` is a jump pad and `o` is an orb.
- Start and end with at least 3 columns of ground.
- Draw for the starting speed. The game stretches the section to the current speed, so it
  plays the same at any speed. A jump covers about 5 columns and reaches about 2.6 cubes high;
  a pad reaches about 5 cubes high.

## Managing dependencies

Dependencies are declared in `pyproject.toml` and locked in `uv.lock` (commit both).

```
uv add <package>          # add a dependency
uv remove <package>       # remove one
uv lock --upgrade         # upgrade everything to the latest allowed versions
uv sync                   # make .venv match the lockfile
```
