# laser-game

This project is a video game platform built with PyGame and OpenCV that uses an extended display and a laser pointer, allowing players to control games by shining the laser on the screen.

## Inspiration

This project was inspired by my father, John Harrison, who developed video games using a similar laser pointer and projector setup.

Each Halloween, he transformed our garage into an arcade, projecting the games onto a suspended bedsheet while trick-or-treaters played _Missle Command_ from our driveway before receiving their candy.

He presented his work at PyCon 2008 -- you can watch his talk on [YouTube](https://www.youtube.com/watch?v=EGSgLuxrgYc).

## Quick Start

Clone the repository, start a virtual environemnt, and install dependencies:

```
git clone https://github.com/pharrison31415/laser-game.git
cd laser-game
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run pong normally (or include `--debug` to emulate laser dots with mouse clicks):

```
python launchers/run.py --preview --game pong
```

Once the program begins, place the game window onto an external display placed in front of the webcam. Press `c` to calibrate. Once it is finished, shoot your lasers at the external display!

Note: It is easier for the computer vision program to find red laser dots in darker environments.

## Games

Games are listed under the `games/` directory:

- `pop-the-balloons`: Shoot the green circles until they all turn gray.
- `quick-draw`: Shoot your half of the screen faster than your opponent. Be careful to not fire too early!
- `whack-a-mole`: Shoot the green circles once they appear. Be quick -- they start to disappear quickly!
- `pong`: The classic arcade game! Shoot lasers at each side of the screen to control each paddle.

## Launcher usage

```
$ python launchers/run.py -h
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
