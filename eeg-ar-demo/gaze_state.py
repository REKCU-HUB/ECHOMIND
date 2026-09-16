"""Ephemeral real-camera gaze transport, independent of simulated EEG state.

Only normalized coordinates and tracking status are accepted. Camera images,
calibration samples and identity data are neither accepted nor persisted here.
"""
from __future__ import annotations

from collections import OrderedDict
import math
import threading
import time
from uuid import UUID


class GazeState:
    CONNECTED_SECONDS = 1.0
    ACTIVE_SECONDS = .350
    MAX_INITIAL_SAMPLE_AGE_MS = 250
    MAX_CLIENTS = 128
    REASONS = frozenset({
        "disabled", "uncalibrated", "calibrating", "tracking", "eye_lost",
        "camera_off", "stale_frame", "synthetic",
    })
    FIELDS = frozenset({
        "client_id", "seq", "enabled", "active", "calibrated", "x", "y",
        "quality", "eyes", "reason", "sample_age_ms", "calibration_screen",
        "source", "simulated",
    })

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._sequences = OrderedDict()
        self._owner = None
        self._updated = None
        self._sample_age_ms = 0.
        self._state = {
            "enabled": False, "active": False, "calibrated": False,
            "x": .5, "y": .5, "quality": 0., "eyes": 2,
            "reason": "disabled", "calibration_screen": None, "seq": 0,
        }

    @staticmethod
    def _number(value, name, low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number")
        # Check the bounds before isfinite, which can overflow on huge integers.
        if not low <= value <= high or not math.isfinite(value):
            raise ValueError(f"{name} is out of range")
        return value

    @classmethod
    def _validate(cls, payload):
        if not isinstance(payload, dict) or set(payload) != cls.FIELDS:
            raise ValueError("Gaze packets must contain exactly the coordinate and status fields; images are not accepted")
        client = payload["client_id"]
        if not isinstance(client, str) or len(client) != 36:
            raise ValueError("client_id must be a UUID string")
        try:
            client = str(UUID(client))
        except (ValueError, AttributeError):
            raise ValueError("client_id must be a UUID string") from None
        seq = payload["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= 9007199254740991:
            raise ValueError("seq must be a non-negative safe integer")
        if payload["source"] != "camera" or payload["simulated"] is not False:
            raise ValueError("The real gaze bridge only accepts source camera with simulated false")
        for name in ("enabled", "active", "calibrated"):
            if not isinstance(payload[name], bool):
                raise ValueError(f"{name} must be a boolean")
        for name in ("x", "y", "quality"):
            cls._number(payload[name], name, 0, 1)
        cls._number(payload["sample_age_ms"], "sample_age_ms", 0, 86_400_000)
        eyes = payload["eyes"]
        if isinstance(eyes, bool) or not isinstance(eyes, int) or eyes not in (1, 2):
            raise ValueError("eyes must be 1 or 2")
        reason = payload["reason"]
        if not isinstance(reason, str) or reason not in cls.REASONS:
            raise ValueError("Unknown gaze tracking reason")
        screen = payload["calibration_screen"]
        if screen is not None:
            if not isinstance(screen, dict) or set(screen) != {"width", "height"}:
                raise ValueError("calibration_screen must be null or contain width and height")
            for name in ("width", "height"):
                value = screen[name]
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65536:
                    raise ValueError(f"calibration_screen.{name} must be a positive integer")
        return client, seq

    def update(self, payload):
        client, seq = self._validate(payload)
        with self._lock:
            if seq <= self._sequences.get(client, -1):
                raise ValueError("Gaze sequence must increase; stale update rejected")
            self._sequences[client] = seq
            self._sequences.move_to_end(client)
            # Keep the currently controlling client's replay protection when
            # evicting old entries; clients otherwise have a bounded lifetime.
            while len(self._sequences) > self.MAX_CLIENTS:
                oldest = next(iter(self._sequences))
                if oldest == self._owner:
                    self._sequences.move_to_end(oldest)
                    continue
                self._sequences.popitem(last=False)
            # A closing prior app instance cannot disable the newer owner.
            if payload["enabled"] or client == self._owner or self._owner is None:
                self._owner = client
                self._updated = self._clock()
                self._sample_age_ms = payload["sample_age_ms"]
                self._state = {name: payload[name] for name in self._state}
                if self._state["calibration_screen"] is not None:
                    self._state["calibration_screen"] = dict(self._state["calibration_screen"])
            return self._snapshot()

    def snapshot(self):
        with self._lock:
            return self._snapshot()

    def _snapshot(self):
        now = self._clock()
        receipt_age = None if self._updated is None else max(0., now - self._updated)
        sample_age = None if receipt_age is None else receipt_age * 1000 + self._sample_age_ms
        connected = receipt_age is not None and receipt_age < self.CONNECTED_SECONDS
        state = dict(self._state)
        if state["calibration_screen"] is not None:
            state["calibration_screen"] = dict(state["calibration_screen"])
        if not connected:
            reason = "disconnected"
        elif not state["enabled"]:
            reason = "disabled"
        elif state["reason"] in {"calibrating", "camera_off", "synthetic"}:
            reason = state["reason"]
        elif not state["calibrated"] or state["calibration_screen"] is None:
            reason = "uncalibrated"
        elif self._sample_age_ms >= self.MAX_INITIAL_SAMPLE_AGE_MS or sample_age >= self.ACTIVE_SECONDS * 1000:
            reason = "stale_frame"
        elif not state["active"] or state["quality"] < .5 or state["reason"] != "tracking":
            reason = "eye_lost" if state["reason"] == "tracking" else state["reason"]
        else:
            reason = "tracking"
        state.update({
            "source": "camera", "simulated": False, "connected": connected,
            "active": reason == "tracking", "reason": reason,
            "age_ms": None if sample_age is None else round(sample_age),
        })
        return state
