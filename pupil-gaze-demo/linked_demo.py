"""Read mouse coordinates from the local EchoMind AR demo. No image transport."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


def validate_pointer(payload):
    """Only accept explicit, finite simulated pointer state from our bridge."""
    if not isinstance(payload, dict) or payload.get("simulated") is not True or payload.get("source") != "mouse":
        raise ValueError("The AR bridge does not support the mouse-linked demo. Update the EEG/AR app.")
    coordinates = []
    for key in ("x", "y"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("The AR pointer coordinates are invalid.")
        coordinates.append(float(value))
    age = payload.get("age_ms")
    fresh = (isinstance(age, (int, float)) and not isinstance(age, bool)
             and math.isfinite(age) and 0 <= age < 1500)
    return {"online": True, "active": payload.get("active") is True and fresh,
            "x": coordinates[0], "y": coordinates[1], "error": "", "age_ms": age,
            "seq": payload.get("seq", 0)}


class PointerClient:
    def __init__(self, port=8765):
        self.port = int(port)
        if not 1 <= self.port <= 65535:
            raise ValueError("The local AR port must be between 1 and 65535.")
        self.url = f"http://127.0.0.1:{self.port}"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._state = {"online": False, "active": False, "x": .5, "y": .5,
                       "error": "Open EchoMind AR to start the linked demo.", "age_ms": None, "seq": 0}
        self._received_at = 0.

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AR-Pointer-Link")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.2)
        with self._lock:
            self._state.update(online=False, active=False)

    def snapshot(self):
        with self._lock:
            state = dict(self._state)
            if time.monotonic()-self._received_at > .8:
                state.update(online=False, active=False)
            return state

    def _run(self):
        opener = build_opener(ProxyHandler({}))
        while not self._stop.is_set():
            started = time.monotonic()
            ok = False
            try:
                with opener.open(self.url+"/api/pointer?viewer=eye-demo", timeout=.45) as response:
                    payload = response.read(8193)
                    if len(payload) > 8192:
                        raise ValueError("Unexpected response from the local AR bridge.")
                    state = validate_pointer(json.loads(payload))
                if self._stop.is_set():
                    break
                with self._lock:
                    self._state = state
                    self._received_at = time.monotonic()
                ok = True
            except (OSError, ValueError, HTTPError, URLError) as exc:
                message = ("Update and reopen the EchoMind EEG/AR app." if isinstance(exc, HTTPError) and exc.code == 404
                           else "AR link unavailable. Open EchoMind AR and move the mouse over the page.")
                with self._lock:
                    self._state.update(online=False, active=False, error=message)
            self._stop.wait(max(.003, .04-(time.monotonic()-started)) if ok else .5)


def open_ar_window(port=8765, camera=False):
    """Open the existing local demo; start the installed companion if needed.

    Called on a worker thread so the native eye window always stays responsive.
    Only the fixed loopback URL and the user's installed demo executable are used.
    """
    url = f"http://127.0.0.1:{int(port)}"
    page_url = url+("/?input=camera" if camera else "/")
    opener = build_opener(ProxyHandler({}))

    def healthy():
        try:
            with opener.open(url+"/api/health", timeout=.4) as response:
                return json.loads(response.read(4096)).get("service") == "echomind-eeg-demo"
        except (OSError, ValueError, AttributeError):
            return False

    if not healthy():
        companion = Path.home()/"Desktop"/"EchoMind-EEG-Demo"/"EchoMind_EEG_AR_Demo.exe"
        if not companion.is_file():
            return "Start the EchoMind EEG/AR app, then click Open AR again."
        subprocess.Popen([str(companion), "--no-browser", "--port", str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if healthy():
                break
            time.sleep(.25)
        else:
            return "The AR service did not start. Reopen the EchoMind EEG/AR app."

    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))/"Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))/"Google/Chrome/Application/chrome.exe",
    ]
    browser = next((path for path in candidates if path.is_file()), None)
    if browser:
        profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))/"EchoMind EEG Demo"/f"browser-{port}"
        subprocess.Popen([str(browser), f"--app={page_url}", f"--user-data-dir={profile}",
                          "--no-first-run", "--no-default-browser-check", "--window-size=1200,850"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(page_url)
    return ("Calibrate, press Esc, then click Start fullscreen gaze in AR on the same monitor."
            if camera else "Move the mouse over EchoMind AR. The virtual eye and gaze pointer will follow.")
