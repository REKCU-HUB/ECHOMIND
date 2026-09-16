"""Mouse-linked presentation mode for the native eye demo window."""
from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import ttk

import numpy as np

from detector import Detection
from linked_demo import PointerClient, open_ar_window
from virtual_eye import render_eye


class ARLinkedMode:
    def init_ar_link(self, ar_demo=False, ar_port=8765):
        self.mode = tk.StringVar(value="ar" if ar_demo else "camera")
        self.bridge = PointerClient(ar_port)
        self._active_mode = "camera"
        self._saved_camera_roi = None
        self._demo_eye_xy = np.array([.5, .5])
        self._opening_ar = False
        self._open_ar_result = None

    def is_linked(self):
        return getattr(self, "mode", None) is not None and self.mode.get() == "ar"

    def build_mode_bar(self):
        modes = tk.Frame(self.root, bg="#101719")
        modes.pack(fill="x", padx=24, pady=(0, 12))
        self.label(modes, "INPUT", 9, "#90a6a4").pack(side="left", padx=(0, 15))
        for text, value in (("Live camera", "camera"), ("AR linked demo", "ar")):
            tk.Radiobutton(modes, text=text, value=value, variable=self.mode,
                           command=self.change_mode, bg="#101719", fg="#ecf2ed",
                           selectcolor="#253538", activebackground="#101719",
                           activeforeground="#9cff57", font=("Segoe UI", 11),
                           cursor="hand2").pack(side="left", padx=(0, 20))
        self.build_camera_link_control(modes)
        self.button(modes, "Open EchoMind AR ↗", self.open_ar).pack(side="right")

    def _set_camera_controls(self, enabled):
        for widget in self.camera_controls:
            state = "readonly" if enabled and isinstance(widget, ttk.Combobox) else "normal" if enabled else "disabled"
            widget.configure(state=state)
            if isinstance(widget, tk.Button):
                if not hasattr(widget, "camera_bg"):
                    widget.camera_bg = widget.cget("bg")
                widget.configure(bg=widget.camera_bg if enabled else "#253134", disabledforeground="#81918f")
        self.calibrate_button.configure(text="9-point calibration" if enabled else "Calibration not needed")

    def change_mode(self):
        requested = self.mode.get()
        if requested == self._active_mode:
            return
        self.escape()
        if requested == "ar":
            saved_roi = self.roi
            if not self.disconnect():
                self.mode.set("camera")
                return
            self._saved_camera_roi = saved_roi
            self.roi = None
            self._active_mode = "ar"
            self._demo_eye_xy = np.array([.5, .5])
            self.bridge.start()
            self._set_camera_controls(False)
            self.camera_heading.config(text="01  /  SIMULATED EYE")
            self.hint.set("Move the mouse over EchoMind AR. The virtual pupil and gaze point follow the page pointer.")
            self.cal_text.set("MOUSE-LINKED DEMO · No calibration needed")
            self.status_text.set("Waiting for EchoMind AR")
            if hasattr(self, "footer_note"):
                self.footer_note.config(text="SIMULATED EYE · Driven by the AR page mouse · Camera off")
        else:
            self.bridge.stop()
            self._active_mode = "camera"
            self.roi = self._saved_camera_roi
            self.last_frame = None
            self.invalidate()
            self._set_camera_controls(True)
            self.camera_heading.config(text="01  /  BINOCULAR CAMERA" if self.is_binocular() else "01  /  PUPIL CAMERA")
            self.status_text.set("Live camera mode")
            if hasattr(self, "footer_note"):
                self.footer_note.config(text="Dark pupil + ellipse fit  /  Quality is a detection score, not gaze accuracy")
            if not self.synthetic:
                self.connect()
        self.update_eye_status()

    def open_ar(self):
        if self._opening_ar:
            return
        camera = not self.is_linked()
        if camera and not self.camera_ar.get():
            self.camera_ar.set(True)
            self.toggle_camera_ar()
        self._opening_ar = True
        self.hint.set("Opening the local EchoMind AR window…")

        def worker():
            try:
                result = open_ar_window(self.bridge.port, camera=camera)
            except OSError:
                result = "Could not open AR. Start the EchoMind EEG/AR app, then try Open AR again."
            self._open_ar_result = result
            self._opening_ar = False

        threading.Thread(target=worker, name="Open-EchoMind-AR", daemon=True).start()

    def tick_linked(self, now):
        state = self.bridge.snapshot()
        active = state["online"] and state["active"]
        self.point = (state["x"], state["y"]) if active else None
        desired = np.array(self.point if active else (.5, .5))
        dt = max(now-self.last_tick, .001)
        self.last_tick = now
        self.process_fps = .85*self.process_fps + .15/dt
        self._demo_eye_xy += (desired-self._demo_eye_xy)*(1-math.exp(-min(dt, .2)/.045))
        rendered = render_eye(tuple(self._demo_eye_xy), active=active, now=now)
        self.last_frame = rendered["frame"]
        self.last_frame_time = now
        # The metadata below is known drawing geometry, never camera confidence.
        self.detection = Detection(center=rendered["center"], axes=rendered["axes"],
                                   angle=rendered["angle"], bbox=rendered["bbox"],
                                   quality=0., threshold=0) if active else None
        self.neutral = np.array([.5, .5])
        if not state["online"]:
            self.status_text.set("AR link offline · Click Open AR")
            self.quality_label.config(text="SIMULATED · Waiting for the local AR link", fg="#90a6a4")
        elif not active:
            self.status_text.set("AR connected · Move over the page")
            self.quality_label.config(text="SIMULATED · Pointer outside AR / page inactive", fg="#90a6a4")
        else:
            self.status_text.set("AR LINK LIVE  ·  Mouse input")
            self.quality_label.config(text=f"SIMULATED · Page X {state['x']*100:.0f}%  /  Y {state['y']*100:.0f}%", fg="#64c7c0")
        self.draw_video()
        self.camera_metrics.config(text=f"VIRTUAL  ·  {self.process_fps:.0f} fps")
        self.draw_gaze(self.gaze)
        if self.full_canvas:
            self.draw_fullscreen(now)
        self.direction_label.config(text=self.pointer_direction() if active else "WAITING", fg="#9cff57" if active else "#90a6a4")
        self.root.after(20, self.tick)

    def pointer_direction(self):
        if not self.point:
            return "CENTER"
        x, y = self.point
        horizontal = "LEFT" if x < .38 else "RIGHT" if x > .62 else ""
        vertical = "UP" if y < .38 else "DOWN" if y > .62 else ""
        return " / ".join(filter(None, (vertical, horizontal))) or "CENTER"
