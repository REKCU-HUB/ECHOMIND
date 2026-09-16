"""Mouse-driven eye-demo transport, separate from EEG intent confirmation."""
from __future__ import annotations

import math
import threading
import time


class PointerState:
    STALE_SECONDS = 1.5
    CONSUMER_SECONDS = 1.0

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._sequences = {}
        self._owner = None
        self._x = self._y = .5
        self._seq = 0
        self._active = False
        self._updated = None
        self._consumer_seen = None

    @staticmethod
    def _number(value, name, low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number")
        if not low <= value <= high or not math.isfinite(value):
            raise ValueError(f"{name} is out of range")
        return value

    def update(self, payload):
        client = payload.get("client_id")
        if not isinstance(client, str) or not client.strip() or len(client) > 128:
            raise ValueError("client_id must be a non-empty string, at most 128 characters")
        seq = payload.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= 9007199254740991:
            raise ValueError("seq must be a non-negative safe integer")
        x = self._number(payload.get("x"), "x", 0, 1)
        y = self._number(payload.get("y"), "y", 0, 1)
        active = payload.get("active")
        if not isinstance(active, bool):
            raise ValueError("active must be a boolean")
        viewport = payload.get("viewport")
        if not isinstance(viewport, dict):
            raise ValueError("viewport must contain width and height")
        self._number(viewport.get("width"), "viewport.width", 1, 65536)
        self._number(viewport.get("height"), "viewport.height", 1, 65536)
        with self._lock:
            if seq <= self._sequences.get(client, -1):
                raise ValueError("Pointer sequence must increase; stale update rejected")
            self._sequences[client] = seq
            # Closing a previous AR window must not cancel the current window.
            if active or client == self._owner or self._owner is None:
                self._owner = client
                self._x, self._y, self._seq = x, y, seq
                self._active = active
                self._updated = self._clock()
            return self._snapshot()

    def snapshot(self, consumer=False):
        with self._lock:
            if consumer:
                self._consumer_seen = self._clock()
            return self._snapshot()

    def _snapshot(self):
        now = self._clock()
        age = None if self._updated is None else max(0, now - self._updated)
        connected = self._consumer_seen is not None and now - self._consumer_seen < self.CONSUMER_SECONDS
        return {
            "x": self._x, "y": self._y, "active": bool(self._active and age is not None and age < self.STALE_SECONDS),
            "seq": self._seq, "age_ms": None if age is None else round(age * 1000),
            "consumer_connected": connected, "simulated": True, "source": "mouse",
        }
