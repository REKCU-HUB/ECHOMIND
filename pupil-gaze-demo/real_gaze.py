"""Publish calibrated camera coordinates to the local AR page; never images.

The UI only replaces a small latest-value snapshot. A daemon worker does all
HTTP work, and includes time spent in its queue in every frame's freshness age.
"""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


REASONS = frozenset({"disabled", "uncalibrated", "calibrating", "tracking",
                     "eye_lost", "camera_off", "stale_frame", "synthetic"})
MAX_FRAME_AGE_MS = 250.
MAX_SAMPLE_AGE_MS = 86_400_000.
DEFAULTS = {"enabled": False, "active": False, "calibrated": False,
            "x": .5, "y": .5, "quality": 0., "eyes": 2, "reason": "disabled",
            "sample_age_ms": 0., "calibration_screen": None}


class _NoRedirects(HTTPRedirectHandler):
    """A local service cannot redirect gaze data to a remote destination."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _number(value, name, lower=0., upper=1.):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not lower <= value <= upper):
        raise ValueError(f"{name} must be a finite number between {lower:g} and {upper:g}.")
    return float(value)


def validate_gaze(fields):
    """Copy and normalize camera state; unknown fields cannot enter transport."""
    if not isinstance(fields, dict) or set(fields)-set(DEFAULTS):
        raise ValueError("Only calibrated camera coordinate fields may be published.")
    result = {**DEFAULTS, **fields}
    for key in ("enabled", "active", "calibrated"):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be true or false.")
    for key in ("x", "y", "quality"):
        result[key] = _number(result[key], key)
    result["sample_age_ms"] = _number(result["sample_age_ms"], "sample_age_ms", 0., MAX_SAMPLE_AGE_MS)
    if type(result["eyes"]) is not int or result["eyes"] not in (1, 2):
        raise ValueError("eyes must be 1 or 2.")
    if not isinstance(result["reason"], str) or result["reason"] not in REASONS:
        raise ValueError("The camera tracking reason is invalid.")
    screen = result["calibration_screen"]
    if screen is not None:
        if (not isinstance(screen, dict) or set(screen) != {"width", "height"}
                or any(type(screen[key]) is not int or not 1 <= screen[key] <= 65536
                       for key in ("width", "height"))):
            raise ValueError("Calibration screen dimensions must be positive pixel counts.")
        result["calibration_screen"] = dict(screen)
    if not result["enabled"]:
        result.update(active=False, reason="disabled")
    elif result["active"]:
        if not result["calibrated"] or screen is None:
            result.update(active=False, reason="uncalibrated")
        elif result["quality"] < .5:
            result.update(active=False, reason="eye_lost")
        elif result["reason"] != "tracking":
            result["active"] = False
    return result


class GazePublisher:
    """Nonblocking loopback publisher for real, already calibrated camera data.

    ``update(fields, capture_stamp=...)`` takes the camera's original monotonic
    capture timestamp. If unavailable, the caller can supply ``sample_age_ms``;
    both methods also count all later queue time. Repeated worker heartbeats
    never renew the age of the underlying camera frame.
    """
    def __init__(self, port=8765):
        if isinstance(port, bool):
            raise ValueError("The local AR port must be between 1 and 65535.")
        self.port = int(port)
        if not 1 <= self.port <= 65535:
            raise ValueError("The local AR port must be between 1 and 65535.")
        self.url = f"http://127.0.0.1:{self.port}/api/gaze"
        self.client_id = str(uuid.uuid4())
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._seq = 0
        self._latest = dict(DEFAULTS)
        self._updated_at = time.monotonic()
        self._received_at = 0.
        self._state = {"online": False, "active": False, "enabled": False,
                       "error": "Open EchoMind AR to connect real gaze.", "seq": 0,
                       "reason": "disabled", "received_at": None}

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive() and not self._stop.is_set():
                return
            self._stop = threading.Event()
            self._wake = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(self._stop, self._wake),
                                            daemon=True, name="AR-Real-Gaze-Link")
            self._thread.start()

    def update(self, fields, capture_stamp=None):
        values = validate_gaze(fields)
        now = time.monotonic()
        if capture_stamp is not None:
            stamp = _number(capture_stamp, "capture_stamp", 0., now+.001)
            values["sample_age_ms"] = min(MAX_SAMPLE_AGE_MS, max(
                values["sample_age_ms"], max(0., now-stamp)*1000.))
        with self._lock:
            self._latest = values
            self._updated_at = now
        self._wake.set()

    publish = update

    def stop(self):
        """Return immediately; worker sends a final disabled packet if possible."""
        with self._lock:
            self._latest = {**self._latest, "enabled": False, "active": False,
                            "reason": "disabled"}
            self._state.update(online=False, active=False, enabled=False,
                               reason="disabled", error="")
        self._stop.set()
        self._wake.set()

    def _current(self, now):
        # Caller holds the lock. The source timestamp is never changed here.
        values = dict(self._latest)
        values["sample_age_ms"] = min(MAX_SAMPLE_AGE_MS, values["sample_age_ms"]
                                       + max(0., now-self._updated_at)*1000.)
        if values["active"] and values["sample_age_ms"] >= MAX_FRAME_AGE_MS:
            values.update(active=False, reason="stale_frame")
        return values

    def snapshot(self):
        now = time.monotonic()
        with self._lock:
            state = dict(self._state)
            current = self._current(now)
            state.update(enabled=current["enabled"], reason=current["reason"])
            if now-self._received_at >= 1. or self._stop.is_set():
                state.update(online=False, active=False)
            state["active"] = state["active"] and current["active"] and state["online"]
            return state

    def _packet(self, *, disabled=False):
        with self._lock:
            values = self._current(time.monotonic())
            if disabled:
                values.update(enabled=False, active=False, reason="disabled")
            self._seq += 1
            return {**values, "source": "camera", "simulated": False,
                    "client_id": self.client_id, "seq": self._seq}

    def _send(self, opener, payload):
        request = Request(self.url, data=json.dumps(payload, allow_nan=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(request, timeout=.35) as response:
            data = response.read(8193)
        if len(data) > 8192:
            raise ValueError("Unexpected response from the local AR bridge.")
        result = json.loads(data)
        if (not isinstance(result, dict) or result.get("source") != "camera"
                or result.get("simulated") is not False
                or type(result.get("active")) is not bool
                or result.get("seq") != payload["seq"]):
            raise ValueError("Update and reopen the EchoMind EEG/AR app.")
        return result

    def _run(self, stop, wake):
        opener = build_opener(ProxyHandler({}), _NoRedirects())
        next_send = 0.
        try:
            while not stop.is_set():
                wake.wait(max(0., next_send-time.monotonic()))
                wake.clear()
                if stop.is_set():
                    break
                # Coalesce camera updates to 25 Hz; no image processing waits on HTTP.
                if time.monotonic() < next_send:
                    continue
                payload = self._packet()
                try:
                    result = self._send(opener, payload)
                    now = time.monotonic()
                    with self._lock:
                        if self._thread is threading.current_thread() and not stop.is_set():
                            self._received_at = now
                            self._state.update(online=True, active=result["active"],
                                               enabled=payload["enabled"], seq=payload["seq"],
                                               received_at=now, error="")
                    next_send = now+.04
                except (OSError, ValueError, HTTPError, URLError):
                    with self._lock:
                        if self._thread is threading.current_thread():
                            self._state.update(online=False, active=False,
                                error="AR gaze link unavailable. Open or update the EchoMind EEG/AR app.")
                    next_send = time.monotonic()+.35
        finally:
            # No redirect/proxy can move this best-effort cleanup off loopback.
            if self._thread is threading.current_thread():
                try:
                    self._send(opener, self._packet(disabled=True))
                except (OSError, ValueError, HTTPError, URLError):
                    pass
