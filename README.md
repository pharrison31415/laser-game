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

This opens a game-select menu: click the laser on a game's card (turn it on over the card) to play it.
Add `--game pong` to skip the menu and start in a game.

While playing, click the laser on the menu button in the top-right corner (or press `Esc`)
to pause. Sweeping the dot onto a button doesn't press it, so games played anywhere on the
screen don't pause by accident. The pause menu has Resume, Restart and Menu (back to game
select), chosen the same way, so you can switch games without restarting the program. In the game-select menu, `Esc` quits.

Once the program begins, place the game window onto an external display placed in front of the webcam. Press `c` (or click the laser on Calibrate in the game-select menu) to calibrate. Once it is finished, shoot your lasers at the external display!

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
  Temporary experiments, combinable with commas: `CUBE_VARIANT=juice` (game feel), `gravity`
  (gravity flips), `ship` (flying), `hold` (tap to hop, hold to jump higher) and `coins`
  (combo pickups), e.g. `CUBE_VARIANT=hold,juice uv run launchers/run.py --game cube-runner`.
- `rooftop-run`: One-button rooftop runner. You never stop running and keep speeding up; shine the
  laser to jump the gaps between buildings, holding it longer to jump higher. Crates slow you
  down; crash through windows, cross girders, and get off crumbling roofs fast. Falling, hitting a
  wall, or getting hit by falling wreckage ends the run.
- `flock-shot`: Birds burst out of the grass and weave across the sky; shine the laser on one to
  shoot it. Each flight of birds comes with three shots, and each round has ten birds: hit enough
  of them to go on to the next round, where the birds are faster, twitchier and smaller. From
  round 3 some birds zig-zag, stop and dash, or skim the grass; from round 4 dark decoy birds
  join in: hitting one takes back a hit.

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
  (0 to 1, reached at distance 350) from which it can appear. A blank line ends the header.
- One character is one cube. The last line is the ground: `-` is ground, a space is a pit.
- `#` is a block (over a pit it becomes a pillar), `=` is a deadly hatched ceiling, `^` is a spike,
  `v` is a hanging spike, `J` is a jump pad and `o` is an orb.
- Experimental: `c` is a coin (only with `CUBE_VARIANT=coins`; sections without any get coins
  placed automatically), and a `variant: hold` header line makes the section appear only with
  `CUBE_VARIANT=hold` (variable-height jump: a tap hops ~1.4 cubes, a full hold ~2.6; every jump needs a new press).
- Start and end with at least 3 columns of ground.
- Gravity flip (experimental, only with `CUBE_VARIANT=gravity`; give the section a
  `variant: gravity` header line): `u` is a gravity portal that turns you upside down and `d` one
  that turns you back. A vertical run of the same letter in one column is one gate (drawn as a green
  frame with chevrons); touching any part of it flips you. Upside down you fall up, run along the
  undersides of `#` blocks (draw a rail of them about 6 rows up), and jumps go downward; `v` spikes
  are the hazards on a rail, hatched `=` stays deadly from below, and flying off the top of the
  screen is a fall. `@` is a flip orb: touch it with the laser on to flip gravity either way.
  Start and end these sections in normal gravity on the ground.
- Draw for a speed of 8.5 cubes per second (`DRAW_SPEED`). The game stretches the section to the current speed, so it
  plays the same at any speed. A jump covers about 5 columns and reaches about 2.6 cubes high;
  a pad reaches about 5 cubes high.
- Flying (experimental, only with `CUBE_VARIANT=ship`): `>` is a ship portal and `<` turns
  you back into a cube. Stack the character vertically to draw the gate's height; it triggers
  at any height in its column. While flying, holding the laser climbs and letting go sinks
  (smooth, with momentum, up to about 1 cube per column either way). Sliding along the floor,
  a block's top or under a `#` roof is safe; a block's side, any `=` ceiling, spikes and pits
  kill. Add `variant: ship` to the header of a flying section, start it with a `>`, and end it
  with a `<` followed by flat runway.

## Managing dependencies

Dependencies are declared in `pyproject.toml` and locked in `uv.lock` (commit both).

```
uv add <package>          # add a dependency
uv remove <package>       # remove one
uv lock --upgrade         # upgrade everything to the latest allowed versions
uv sync                   # make .venv match the lockfile
```
