from __future__ import annotations
import sys
import threading
import time
import cv2
from typing import Callable, Optional, Tuple

# V4L2 values for CAP_PROP_AUTO_EXPOSURE (Linux)
_V4L2_MANUAL_EXPOSURE = 1


class Camera:
    """
    exposure:
        None  -> leave the camera's auto exposure alone.
        float -> fixed exposure in the driver's units (V4L2: 100 us steps, so 150 = 15 ms).
                 Auto exposure in a dark room makes many webcams drop to ~10 fps;
                 a fixed exposure keeps the full frame rate (and makes the laser dot
                 stand out more against the projected image).
    """

    def __init__(self, index: int, target_size: Tuple[int, int], fps: int = 30,
                 exposure: Optional[float] = None):
        self.index = index
        self.target_size = target_size
        self.fps = fps
        self.exposure = exposure
        self.cap: Optional[cv2.VideoCapture] = None
        self._restore_auto_exposure: Optional[float] = None

    def open(self) -> bool:
        if sys.platform.startswith("win"):
            backend = cv2.CAP_DSHOW
        elif sys.platform.startswith("linux"):
            backend = cv2.CAP_V4L2
        else:
            backend = cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.index, backend)
        if not self.cap.isOpened():
            return False
        # MJPG must be requested before the size: uncompressed YUYV at 720p is
        # limited to ~10 fps over USB 2 on typical webcams.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        w, h = self.target_size
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Note: don't shrink CAP_PROP_BUFFERSIZE to 1 -- with V4L2 the driver then
        # has nowhere to put the next frame while we decode, costing ~1/3 of the
        # frame rate. CameraWorker reads continuously, so frames don't go stale.
        if self.exposure is not None:
            self._restore_auto_exposure = self.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, _V4L2_MANUAL_EXPOSURE)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, float(self.exposure))
        return True

    def describe(self) -> str:
        if self.cap is None:
            return "camera closed"
        fcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        fcc_s = "".join(chr((fcc >> 8 * i) & 0xFF) for i in range(4))
        exp = "auto" if self.exposure is None else f"{self.exposure:g}"
        return (f"{int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                f"{int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} {fcc_s} "
                f"@ {self.cap.get(cv2.CAP_PROP_FPS):g} fps, exposure {exp}")

    def read(self):
        if self.cap is None:
            return False, None
        return self.cap.read()

    def close(self):
        if self.cap is not None:
            # V4L2 controls outlive the process; put auto exposure back.
            if self._restore_auto_exposure is not None:
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, self._restore_auto_exposure)
            self.cap.release()
            self.cap = None


class CameraWorker:
    """
    Runs capture and detection on two background threads so the game can render at
    its own frame rate instead of waiting on the camera. Capture (incl. JPEG decode)
    and detection overlap, since OpenCV releases the GIL; detection always works on
    the newest frame and skips any it couldn't keep up with.

    The main thread polls `latest()` for the most recent detections. `read()` (used
    by calibration) blocks until a frame newer than the last one it returned.
    """

    def __init__(self, camera: Camera, detect: Callable):
        self.camera = camera
        self._detect = detect
        self._cond = threading.Condition()
        self._frame = None
        self._frame_id = 0
        self._read_id = 0        # last frame handed out by read()
        self._detected_id = 0    # last frame the detection thread processed
        self._detections: dict = {}
        self._detect_enabled = True
        self._running = False
        self._threads: list[threading.Thread] = []
        self.frames_captured = 0
        self.frames_detected = 0

    def start(self):
        self._running = True
        for target, name in ((self._capture_loop, "camera-capture"),
                             (self._detect_loop, "camera-detect")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def _capture_loop(self):
        while self._running:
            ok, frame = self.camera.read()
            if not ok:
                time.sleep(0.005)
                continue
            with self._cond:
                self._frame = frame
                self._frame_id += 1
                self.frames_captured += 1
                self._cond.notify_all()

    def _detect_loop(self):
        while self._running:
            with self._cond:
                self._cond.wait_for(
                    lambda: not self._running or
                    (self._detect_enabled and self._frame_id != self._detected_id),
                    timeout=0.2)
                if not self._running or not self._detect_enabled \
                        or self._frame_id == self._detected_id:
                    continue
                frame, self._detected_id = self._frame, self._frame_id
            dets = self._detect(frame)
            with self._cond:
                self._detections = dets
                self.frames_detected += 1

    def latest(self) -> dict:
        with self._cond:
            return self._detections

    def set_detection_enabled(self, enabled: bool):
        """Calibration runs its own detection; skip the duplicate work meanwhile."""
        with self._cond:
            self._detect_enabled = enabled
            self._cond.notify_all()

    def read(self, timeout: float = 1.0):
        with self._cond:
            if not self._cond.wait_for(lambda: self._frame_id != self._read_id, timeout):
                return False, None
            self._read_id = self._frame_id
            return True, self._frame

    def stop(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        for t in self._threads:
            t.join(timeout=2.0)
