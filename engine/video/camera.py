from __future__ import annotations
import sys
import cv2
from typing import Tuple, Optional


class Camera:
    def __init__(self, index: int, target_size: Tuple[int, int], fps: int = 60):
        self.index = index
        self.target_size = target_size
        self.fps = fps
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
        self.cap = cv2.VideoCapture(self.index, backend)
        w, h = self.target_size
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.cap.isOpened():
            return False
        return True

    def read(self):
        if self.cap is None:
            return False, None
        return self.cap.read()

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
