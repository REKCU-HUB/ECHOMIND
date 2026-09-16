"""Local-only DirectShow camera capture, with a single latest-frame buffer.

Device enumeration never opens a camera. Only the explicitly selected device is
opened, and neither frames nor camera identifiers are transmitted or saved.
"""

from __future__ import annotations

from collections import deque
import threading
import time

import cv2
from cv2_enumerate_cameras import enumerate_cameras


def enumerate_devices() -> list[dict]:
    """Return DirectShow devices without probing any of their video streams."""
    return [
        {
            "index": int(device.index),
            "name": str(device.name),
            "backend": int(device.backend),
            "path": str(device.path),
        }
        for device in enumerate_cameras(cv2.CAP_DSHOW)
    ]


class CameraStream:
    """Capture one selected camera in a background thread.

    ``read_latest`` returns an independent BGR image copy. A sequence number
    changes only when a new valid frame arrives, and timestamps use monotonic
    time. Missing, stopped, or stale video returns ``None`` instead of replaying
    a frozen eye image. Public status values are stopped/connecting/streaming/
    stopping/error; error messages use plain English. Capture properties remain
    at the camera's own defaults.
    """

    STALE_SECONDS = 1.0
    MAX_FAILED_READS = 15

    def __init__(self, index: int, backend: int = cv2.CAP_DSHOW):
        self.index = int(index)
        self.backend = int(backend)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame = None
        self._seq = 0
        self._timestamp = 0.0
        self._status = "stopped"
        self._error = ""
        self._fps = 0.0

    @property
    def status(self) -> str:
        with self._lock:
            if self._status == "streaming" and time.monotonic() - self._timestamp > self.STALE_SECONDS:
                return "connecting"
            return self._status

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def fps(self) -> float:
        with self._lock:
            if not self._timestamp or time.monotonic() - self._timestamp > self.STALE_SECONDS:
                return 0.0
            return self._fps

    @property
    def running(self) -> bool:
        """Whether the capture worker may still own the selected camera."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> "CameraStream":
        """Start once; calling again while running never opens another stream."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop_event.clear()
            self._frame = None
            self._timestamp = 0.0
            self._fps = 0.0
            self._error = ""
            self._status = "connecting"
            self._thread = threading.Thread(
                target=self._run, name=f"EyeCamera-{self.index}", daemon=True
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        """Request release on the capture thread; bound GUI waiting to 3 s.

        OpenCV's Windows driver calls cannot safely be interrupted from another
        thread. If a defective driver blocks, status stays stopping until the
        call returns, and start() will not open a second capture in the interim.
        """
        with self._lock:
            self._stop_event.set()
            self._frame = None
            self._timestamp = 0.0
            self._fps = 0.0
            thread = self._thread
            self._status = "stopping" if thread is not None and thread.is_alive() else "stopped"
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._status = "stopped"

    def read_latest(self):
        """Return ``(sequence, frame_bgr_or_none, monotonic_timestamp)``."""
        with self._lock:
            fresh = (
                self._frame is not None
                and self._status == "streaming"
                and not self._stop_event.is_set()
                and time.monotonic() - self._timestamp <= self.STALE_SECONDS
            )
            return self._seq, self._frame.copy() if fresh else None, self._timestamp

    def _run(self) -> None:
        capture = None
        frame_times = deque(maxlen=45)
        failures = 0
        try:
            capture = cv2.VideoCapture(self.index, self.backend)
            if self._stop_event.is_set():
                return
            if not capture.isOpened():
                raise RuntimeError("Cannot open camera. Close other camera previews or video calls, then reconnect.")
            while not self._stop_event.is_set():
                ok, frame = capture.read()
                now = time.monotonic()
                if self._stop_event.is_set():
                    break
                if not ok or frame is None or frame.size == 0:
                    failures += 1
                    frame_times.clear()
                    with self._lock:
                        self._frame = None
                        self._timestamp = 0.0
                        self._fps = 0.0
                        self._status = "connecting"
                    if failures >= self.MAX_FAILED_READS:
                        raise RuntimeError("Camera video interrupted. Check USB, close other camera apps, then reconnect.")
                    self._stop_event.wait(0.05)
                    continue
                failures = 0
                if frame.ndim == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.ndim == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                if frame.ndim != 3 or frame.shape[2] != 3:
                    raise RuntimeError("Unsupported video format. Select a standard video output in the camera settings.")
                frame_times.append(now)
                elapsed = frame_times[-1] - frame_times[0]
                fps = (len(frame_times) - 1) / elapsed if elapsed > 0 else 0.0
                with self._lock:
                    if self._stop_event.is_set():
                        break
                    self._frame = frame
                    self._seq += 1
                    self._timestamp = now
                    self._fps = fps
                    self._status = "streaming"
        except Exception as exc:
            with self._lock:
                if not self._stop_event.is_set():
                    self._error = str(exc)
                    self._status = "error"
        finally:
            if capture is not None:
                capture.release()
            with self._lock:
                self._frame = None
                self._timestamp = 0.0
                self._fps = 0.0
                if self._stop_event.is_set():
                    self._status = "stopped"
