"""Local camera tracking and loopback-only AR simulation. No image uploads or recording."""
from __future__ import annotations

import argparse
from collections import deque
import ctypes
import math
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from calibration import Calibration
from camera import CameraStream, enumerate_devices
from detector import PupilDetector
from ar_mode import ARLinkedMode
from binocular_mode import BinocularMode
from calibration_preview import draw_calibration_preview
from camera_ar_mode import CameraARMode

BG = "#101719"
PANEL = "#192326"
FG = "#ecf2ed"
MUTED = "#90a6a4"
GREEN = "#9cff57"
TEAL = "#64c7c0"
AMBER = "#ffc77a"


def direction(point):
    x, y = point
    horizontal = "LEFT" if x < .38 else "RIGHT" if x > .62 else ""
    vertical = "UP" if y < .38 else "DOWN" if y > .62 else ""
    return " / ".join(filter(None, (vertical, horizontal))) or "CENTER"


class EyeDemo(ARLinkedMode, BinocularMode, CameraARMode):
    def __init__(self, root, synthetic=False, ar_demo=False, ar_port=8765, binocular=False, camera_ar=False):
        self.root = root
        self.synthetic = synthetic
        root.title("EchoMind · Pupil & Gaze Demo")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app.ico"
        if icon.exists():
            root.iconbitmap(str(icon))
        width = min(1460, root.winfo_screenwidth()-60)
        height = min(1010, root.winfo_screenheight()-100)
        root.geometry(f"{width}x{height}")
        root.minsize(min(width, 1100), min(height, 860))
        root.configure(bg=BG)
        self.stream = None
        self.seq = -1
        self.detector = PupilDetector()
        self.calibration = Calibration()
        self.roi = None
        self.neutral = None
        self.history = deque(maxlen=120)
        self.point = None
        self.smoothed = None
        self.last_frame = None
        self.detection = None
        self.last_detection_time = 0.
        self.last_frame_time = 0.
        self.last_tick = time.monotonic()
        self.process_fps = 0.
        self.view_transform = (1, 0, 0)
        self.selecting = False
        self.drag_start = None
        self.drag_current = None
        self.full = None
        self.full_canvas = None
        self.cal_state = None
        self.closed = False
        # This eye camera delivers mirrored input. Flip before detection so
        # the preview, pupil geometry and relative gaze share one orientation.
        self.mirror = tk.BooleanVar(value=True)
        self.auto = tk.BooleanVar(value=True)
        self.threshold = tk.DoubleVar(value=50)
        self.gain = tk.DoubleVar(value=5)
        self.status_text = tk.StringVar(value="Checking USB Camera…")
        self.hint = tk.StringVar(value="Keep the camera still and the entire pupil clearly visible.")
        self.cal_text = tk.StringVar(value="Not calibrated · Relative pupil motion")
        self.init_binocular(binocular)
        self.init_ar_link(ar_demo, ar_port)
        self.init_camera_ar(camera_ar, ar_port)
        self._style()
        self._build()
        self.devices = []
        self.refresh_devices()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda _: self.escape())
        root.after(80, self.tick)
        if ar_demo:
            root.after(120, self.change_mode)
        elif synthetic:
            self.status_text.set("Synthetic test · Camera off")
        elif any(d["name"].casefold() == "usb camera" for d in self.devices):
            root.after(150, self.connect)

    def _style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=FG, arrowcolor=GREEN, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", FG)])

    def label(self, parent, text="", size=10, color=FG, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size), **kw)

    def button(self, parent, text, command, primary=False, **kw):
        return tk.Button(parent, text=text, command=command,
                         bg=GREEN if primary else "#2a393c", fg=BG if primary else FG,
                         activebackground=TEAL, activeforeground=BG, relief="flat",
                         bd=0, padx=13, pady=8, cursor="hand2",
                         font=("Segoe UI", 10), **kw)

    def _build(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=24, pady=(14, 9))
        self.label(head, "ECHO MIND", 21).pack(side="left")
        self.label(head, " /  EYE TRACKING LAB", 11, GREEN).pack(side="left", padx=12)
        self.label(head, "LOCAL PROCESSING  ·  NO RECORDING", 10, MUTED).pack(side="right")
        self.build_mode_bar()

        bar = tk.Frame(self.root, bg=PANEL, padx=14, pady=10)
        bar.pack(fill="x", padx=24)
        self.label(bar, "Camera", color=MUTED).pack(side="left", padx=(0, 10))
        self.camera_choice = ttk.Combobox(bar, state="readonly", width=28)
        self.camera_choice.pack(side="left")
        self.button(bar, "Refresh", self.refresh_devices).pack(side="left", padx=6)
        self.button(bar, "Connect", self.connect, True).pack(side="left", padx=3)
        self.button(bar, "Stop", self.disconnect).pack(side="left", padx=3)
        self.label(bar, textvariable=self.status_text, color=MUTED).pack(side="right", padx=5)
        self.build_tracking_bar()

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=10)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2, minsize=350)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        title = tk.Frame(left, bg=PANEL, padx=15, pady=8)
        title.pack(fill="x")
        self.camera_heading = self.label(title, "01  /  PUPIL CAMERA", 11, GREEN)
        self.camera_heading.pack(side="left")
        self.camera_metrics = self.label(title, "Waiting for video", 9, MUTED)
        self.camera_metrics.pack(side="right")
        self.video = tk.Canvas(left, bg="#080d0e", highlightthickness=0)
        self.video.pack(fill="both", expand=True)
        self.video.bind("<ButtonPress-1>", self.roi_start)
        self.video.bind("<B1-Motion>", self.roi_drag)
        self.video.bind("<ButtonRelease-1>", self.roi_end)
        toolbar = tk.Frame(left, bg=PANEL, padx=12, pady=8)
        toolbar.pack(fill="x")
        self.button(toolbar, "Crop eye", self.select_roi).pack(side="left", padx=(0, 5))
        self.button(toolbar, "Reset crop", self.reset_roi).pack(side="left", padx=(0, 5))
        self.button(toolbar, "Set center", self.set_neutral).pack(side="left")
        tk.Checkbutton(toolbar, text="Flip horizontally", variable=self.mirror,
                       command=self.mirror_changed, bg=PANEL, fg=FG, selectcolor=BG,
                       activebackground=PANEL, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(side="right")
        hint_label = self.label(left, textvariable=self.hint, size=9, color=MUTED,
                                wraplength=630, anchor="w", justify="left")
        hint_label.pack(fill="x", padx=15, pady=(0, 12), side="bottom", before=self.video)
        toolbar.pack_configure(side="bottom", before=self.video)

        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        self.label(right, "02  /  GAZE POINTER", 11, GREEN).pack(anchor="w", pady=(8, 10))
        self.gaze = tk.Canvas(right, bg=PANEL, width=320, height=150, highlightthickness=0)
        self.gaze.pack(fill="both", expand=True)
        self.direction_label = self.label(right, "—", 25)
        self.direction_label.pack(anchor="w", pady=(12, 0))
        self.quality_label = self.label(right, "Waiting for pupil", 10, MUTED)
        self.quality_label.pack(anchor="w", pady=(3, 6))
        self.label(right, textvariable=self.cal_text, size=9, color=TEAL,
                   wraplength=440, justify="left").pack(anchor="w", pady=(0, 12))
        self.calibrate_button = self.button(right, "9-point calibration", self.start_calibration, True)
        self.calibrate_button.pack(fill="x", pady=(0, 7))
        self.button(right, "Fullscreen demo  /  Esc to return", self.open_demo).pack(fill="x")

        controls = tk.Frame(self.root, bg=PANEL, padx=16, pady=8)
        controls.pack(fill="x", padx=24, pady=(0, 12))
        self.label(controls, "Detection", 10, TEAL).grid(row=0, column=0, padx=(0, 16))
        tk.Checkbutton(controls, text="Auto threshold", variable=self.auto,
                       command=self.invalidate, bg=PANEL, fg=FG, selectcolor=BG,
                       activebackground=PANEL, activeforeground=FG,
                       font=("Segoe UI", 10)).grid(row=0, column=1)
        self.label(controls, "Threshold", 9, MUTED).grid(row=0, column=2, padx=(20, 0))
        self.threshold_scale = tk.Scale(controls, from_=5, to=160, orient="horizontal",
                         variable=self.threshold, resolution=1, length=200,
                         bg=PANEL, fg=FG, troughcolor=BG, highlightthickness=0,
                         activebackground=GREEN, font=("Segoe UI", 9))
        self.threshold_scale.grid(row=0, column=3)
        self.threshold_scale.bind("<ButtonRelease-1>", lambda _: self.invalidate() if not self.auto.get() else None)
        self.label(controls, "Motion gain", 9, MUTED).grid(row=0, column=4, padx=(20, 0))
        tk.Scale(controls, from_=2, to=15, orient="horizontal", variable=self.gain,
                 resolution=.5, length=165, bg=PANEL, fg=FG, troughcolor=BG,
                 highlightthickness=0, activebackground=GREEN,
                 font=("Segoe UI", 9)).grid(row=0, column=5)
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=24, pady=(0, 8))
        self.footer_note = self.label(footer, "Dark pupil + ellipse fit  /  Quality is a detection score, not gaze accuracy", 9, MUTED)
        self.footer_note.pack(side="left")
        self.label(footer, "DEMO  ·  v1.3", 9, GREEN).pack(side="right")
        self.camera_controls = [widget for parent in (bar, toolbar, controls)
                                for widget in parent.winfo_children()
                                if isinstance(widget, (tk.Button, tk.Checkbutton, tk.Scale, ttk.Combobox))]
        self.camera_controls.append(self.calibrate_button)
        self.camera_controls.append(self.camera_link_check)
        self.camera_controls.extend(self.binocular_controls)
        # Reserve the fixed bottom controls before allocating the elastic
        # preview area, including when a selection hint wraps to two lines.
        footer.pack_configure(before=body, side="bottom")
        controls.pack_configure(before=body, side="bottom")
        if self.is_binocular():
            self.camera_heading.config(text="01  /  BINOCULAR CAMERA")
            self.hint.set("Select eye A, then eye B. Keep both eyes visible and run 9-point calibration.")

    def refresh_devices(self):
        if self.synthetic:
            self.devices = []
            self.camera_choice["values"] = ["Synthetic eye · Test mode"]
            self.camera_choice.current(0)
            return
        try:
            self.devices = enumerate_devices()
            self.camera_choice["values"] = [f'{d["name"]}  [{d["index"]}]' for d in self.devices]
            chosen = next((i for i, d in enumerate(self.devices) if d["name"].casefold() == "usb camera"), None)
            if self.devices:
                if chosen is None:
                    self.camera_choice.set("Select a camera")
                else:
                    self.camera_choice.current(chosen)
                self.status_text.set("Select a camera and connect")
            else:
                self.status_text.set("No camera found · Check USB")
        except Exception as exc:
            self.status_text.set(f"Camera list failed: {exc}")

    def connect(self):
        if self.synthetic or self.is_linked():
            return
        index = self.camera_choice.current()
        if index < 0 or index >= len(self.devices):
            self.status_text.set("Select a camera first")
            return
        if not self.disconnect():
            return
        device = self.devices[index]
        self.stream = CameraStream(device["index"], device["backend"])
        self.stream.start()
        self.status_text.set("Connecting to " + device["name"])

    def disconnect(self):
        if self.stream:
            self.stream.stop()
            if self.stream.running:
                self.status_text.set("Releasing camera · Try again shortly")
                self.point = self.detection = self.last_frame = None
                return False
            self.stream = None
        self.seq = -1
        self.last_frame = None
        self.invalidate()
        self.status_text.set("Camera stopped")
        return True

    def invalidate(self):
        self.calibration_screen = None
        self.detector.reset()
        self.calibration.reset()
        self.history.clear()
        self.neutral = None
        self.point = self.smoothed = self.detection = None
        if hasattr(self, "binocular_tracker"):
            self.binocular_tracker.reset()
        self.cal_state = None
        self.cal_text.set("Not calibrated · Relative pupil motion")
        self.hint.set("After changing the image or detection settings, set the center or calibrate again.")

    def mirror_changed(self):
        self.mirror_eye_regions()
        if self.roi:
            x0, y0, x1, y1 = self.roi
            self.roi = (1-x1, y0, 1-x0, y1)
        if self.last_frame is not None:
            self.last_frame = cv2.flip(self.last_frame, 1)
        self.selecting = False
        self.drag_start = self.drag_current = None
        self.invalidate()

    def select_roi(self):
        if self.is_binocular():
            self.select_eye(0)
            return
        self.selecting = True
        self.drag_start = self.drag_current = None
        self.hint.set("Drag around the whole eye, leaving room for pupil movement. Release to crop; Esc cancels.")
        # Update the transform immediately, before a new drag can start.
        self.draw_video()

    def reset_roi(self):
        if self.is_binocular():
            self.reset_eyes()
            return
        self.roi = None
        self.selecting = False
        self.drag_start = self.drag_current = None
        self.invalidate()
        self.hint.set("Full view restored. Use Crop eye to crop and enlarge the eye region.")

    def roi_start(self, event):
        if self.selecting and self.last_frame is not None:
            self.drag_start = (event.x, event.y)
            self.drag_current = self.drag_start

    def roi_drag(self, event):
        if self.drag_start:
            self.drag_current = (event.x, event.y)

    def roi_end(self, event):
        if not self.drag_start or self.last_frame is None:
            return
        scale, ox, oy = self.view_transform
        h, w = self.last_frame.shape[:2]
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        a, b = sorted((np.clip((x0-ox)/scale/w, 0, 1), np.clip((x1-ox)/scale/w, 0, 1)))
        c, d = sorted((np.clip((y0-oy)/scale/h, 0, 1), np.clip((y1-oy)/scale/h, 0, 1)))
        if b-a > .06 and d-c > .06:
            if self.is_binocular():
                self.accept_eye_roi((float(a), float(c), float(b), float(d)))
                return
            self.roi = (float(a), float(c), float(b), float(d))
            self.invalidate()
            self.hint.set("Eye cropped. Use Crop eye to select again, or Reset crop for the full view.")
        else:
            if self.is_binocular():
                self.hint.set("Selection too small. Draw this eye region again, or press Esc to cancel.")
                self.drag_start = self.drag_current = None
                return
            self.hint.set("Selection too small; previous crop kept. Include the whole eye with some margin.")
        self.drag_start = self.drag_current = None
        self.selecting = False

    def set_neutral(self):
        now = time.monotonic()
        points = [p for t, p, q in self.history if now-t < .7 and q >= .5]
        if len(points) >= 5 and self.detection:
            self.calibration.reset()
            self.cal_text.set("Relative pupil mode · Current position is the center")
            self.neutral = np.median(points, axis=0)
            self.smoothed = None
            self.hint.set("Center set. Look around to see relative pupil movement.")
        else:
            self.hint.set("Wait for a steady pupil detection before setting the center.")

    def synthetic_frame(self, now):
        if self.is_binocular():
            frame = np.full((360, 900, 3), 175, dtype=np.uint8)
            for x in (225, 675):
                cx, cy = int(x+35*math.sin(now*.5)), int(180+20*math.sin(now*.7))
                cv2.ellipse(frame, (x, 180), (170, 100), 0, 0, 360, (210, 210, 210), -1)
                cv2.circle(frame, (cx, cy), 50, (100, 100, 100), -1)
                cv2.ellipse(frame, (cx, cy), (20, 26), 10, 0, 360, (8, 8, 8), -1)
                cv2.circle(frame, (cx+7, cy-8), 3, (245, 245, 245), -1)
            return frame
        frame = np.full((480, 640, 3), 170, dtype=np.uint8)
        cx = int(320 + 80*math.sin(now*.5))
        cy = int(240 + 38*math.sin(now*.7))
        cv2.ellipse(frame, (320, 240), (300, 170), 0, 0, 360, (115, 115, 115), -1)
        cv2.circle(frame, (cx, cy), 95, (90, 90, 90), -1)
        cv2.ellipse(frame, (cx, cy), (40, 49), 15, 0, 360, (8, 8, 8), -1)
        cv2.circle(frame, (cx+15, cy-14), 7, (245, 245, 245), -1)
        return frame

    def tick(self):
        if self.closed:
            return
        now = time.monotonic()
        if self._open_ar_result is not None:
            self.hint.set(self._open_ar_result)
            self._open_ar_result = None
        if self.is_linked():
            self.publish_camera_gaze(now)
            self.tick_linked(now)
            return
        frame = None
        if self.synthetic:
            frame = self.synthetic_frame(now)
        elif self.stream:
            seq, latest, stamp = self.stream.read_latest()
            if seq != self.seq and latest is not None and now-stamp < .6:
                self.seq, frame = seq, latest
            if self.stream.error:
                self.status_text.set(self.stream.error)
            elif latest is not None:
                self.status_text.set(f"USB live  ·  {self.stream.fps:.0f} fps")
        if frame is not None:
            self.camera_frame_stamp = now if self.synthetic else stamp
            self.last_frame_time = now
            if self.mirror.get():
                frame = cv2.flip(frame, 1)
            if self.last_frame is not None and self.last_frame.shape != frame.shape:
                self.invalidate()
                self.selecting = False
                self.drag_start = self.drag_current = None
                self.cancel_eye_selection()
                self.hint.set("Camera resolution changed. Check both eye regions and recalibrate.")
            self.last_frame = frame
            detector_threshold = None if self.auto.get() else int(self.threshold.get())
            self.detection = (self.binocular_tracker.detect(frame, threshold=detector_threshold)
                              if self.is_binocular() else
                              self.detector.detect(frame, roi=self.roi, threshold=detector_threshold))
            dt = max(now-self.last_tick, .001)
            self.last_tick = now
            self.process_fps = .85*self.process_fps + .15/dt
            if self.detection and self.detection.quality >= .5:
                det = self.detection
                h, w = frame.shape[:2]
                p = np.array(det.feature if self.is_binocular() else [det.center[0]/w, det.center[1]/h])
                self.history.append((now, p, det.quality))
                self.last_detection_time = now
                if self.neutral is None:
                    recent = [v for t, v, q in self.history if now-t < .6]
                    if len(recent) >= 10:
                        self.neutral = np.median(recent, axis=0)
                mapped = np.array(self.calibration.map(p)) if self.calibration.ready else (
                    self.relative_point(p) if self.neutral is not None else np.array([.5, .5]))
                alpha = 1-math.exp(-min(dt, .1)/.085)
                self.smoothed = mapped if self.smoothed is None else self.smoothed+(mapped-self.smoothed)*alpha
                self.point = tuple(self.smoothed)
            else:
                # A blink or rejected candidate must never display a stale live cursor.
                self.point = self.smoothed = self.detection = None
                self.history.clear()
        if not self.synthetic and (not self.stream or now-self.last_detection_time > .6):
            self.point = self.smoothed = self.detection = None
        if not self.synthetic and now-self.last_frame_time > .6:
            self.last_frame = None
            self.binocular_tracker.reset()
            self.history.clear()
            if self.stream and not self.stream.error:
                self.status_text.set("Waiting for camera video…")
        self._calibration_tick(now)
        self.draw_video()
        self.draw_gaze(self.gaze)
        if self.full_canvas:
            self.draw_fullscreen(now)
        if self.detection:
            self.direction_label.config(text=direction(self.point) if self.point else "CENTER", fg=GREEN)
            lock = "Both pupils locked" if self.is_binocular() else "Pupil locked"
            self.quality_label.config(text=f"Quality {round(self.detection.quality*100)} / 100   ·   {lock}", fg=TEAL)
        else:
            self.direction_label.config(text="NOT LOCKED", fg=MUTED)
            self.quality_label.config(text="Blink / obstruction / no video · Pointer paused", fg=MUTED)
        self.update_eye_status()
        self.publish_camera_gaze(now)
        self.root.after(20, self.tick)

    def draw_video(self):
        canvas = self.video
        cw, ch = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        canvas.delete("all")
        if self.last_frame is None:
            canvas.create_text(cw/2, ch/2, text="USB CAMERA\nWaiting for video", fill=MUTED,
                               font=("Segoe UI", 17), justify="center")
            return
        frame = self.last_frame
        h, w = frame.shape[:2]
        cropped = self.roi is not None and not self.selecting
        left, top, right, bottom = 0, 0, w, h
        if cropped:
            a, b, c, d = self.roi
            left, top = int(a*w), int(b*h)
            right, bottom = int(c*w), int(d*h)
        preview = frame[top:bottom, left:right]
        ph, pw = preview.shape[:2]
        # Keep captions outside the eye image, even for a very shallow crop.
        picture_height = max(1, ch-71)
        scale = min(cw/pw, picture_height/ph)
        dw, dh = max(1, round(pw*scale)), max(1, round(ph*scale))
        ox, oy = (cw-dw)/2, 38+(picture_height-dh)/2
        # Detection and gaze stay in full-frame coordinates. Only the preview
        # is cropped; this translation applies equally to every overlay.
        fx, fy = ox-left*scale, oy-top*scale
        self.view_transform = (scale, fx, fy)
        rgb = cv2.cvtColor(cv2.resize(preview, (dw, dh)), cv2.COLOR_BGR2RGB)
        self.video_photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        canvas.create_image(ox, oy, anchor="nw", image=self.video_photo)
        if self.roi and self.selecting:
            a, b, c, d = self.roi
            canvas.create_rectangle(fx+a*w*scale, fy+b*h*scale, fx+c*w*scale, fy+d*h*scale,
                                    outline=TEAL, dash=(5, 4), width=1)
        overlays = [(self.detection, self.neutral)] if self.detection else []
        if self.is_binocular() and not self.is_linked():
            overlays = self.eye_overlays()
        for detection, neutral in overlays:
            det = detection
            cx, cy = fx+det.center[0]*scale, fy+det.center[1]*scale
            x, y, bw, bh = det.bbox
            pad = 12
            canvas.create_rectangle(max(ox, fx+x*scale-pad), max(oy, fy+y*scale-pad),
                                    min(ox+dw, fx+(x+bw)*scale+pad), min(oy+dh, fy+(y+bh)*scale+pad),
                                    outline=GREEN, width=3)
            angle = math.radians(det.angle)
            pts = []
            for t in np.linspace(0, 2*math.pi, 70):
                ex, ey = det.axes[0]*.5*math.cos(t)*scale, det.axes[1]*.5*math.sin(t)*scale
                pts.extend((cx+ex*math.cos(angle)-ey*math.sin(angle),
                            cy+ex*math.sin(angle)+ey*math.cos(angle)))
            canvas.create_line(*pts, fill=FG, width=2)
            canvas.create_line(cx-10, cy, cx+10, cy, fill=FG, width=3)
            canvas.create_line(cx, cy-10, cx, cy+10, fill=FG, width=3)
            if neutral is not None:
                nx, ny = fx+neutral[0]*w*scale, fy+neutral[1]*h*scale
                canvas.create_oval(nx-5, ny-5, nx+5, ny+5, outline=FG, width=2)
                canvas.create_line(nx, ny, cx, cy, fill=GREEN, width=3, dash=(7, 5), arrow="last")
        if self.detection:
            caption = "GAZE: " + (direction(self.point) if self.point else "CENTER")
            quality = f"PUPIL LOCK  /  Q {round(self.detection.quality*100)}"
        else:
            caption, quality = "GAZE: --", "SEARCHING FOR PUPIL"
        if self.is_linked():
            quality = "SIMULATED EYE / MOUSE INPUT" if self.point else "SIMULATED EYE / WAITING FOR AR"
        elif self.is_binocular():
            quality = "BOTH EYES LOCKED" if self.detection else "BOTH EYES REQUIRED / POINTER PAUSED"
        canvas.create_rectangle(0, 0, cw, 38, fill="#101719", outline="")
        source_label = ("SYNTHETIC / CROP" if cropped else "SYNTHETIC TEST") if self.synthetic else (
            "LIVE / EYE CROP" if cropped else "LIVE / USB CAMERA")
        if self.is_linked():
            source_label = "AR LINK / SIMULATED"
        elif self.is_binocular():
            source_label = "LIVE / TWO EYES" if not self.synthetic else "SYNTHETIC / TWO EYES"
            self.draw_eye_regions(canvas, fx, fy, scale, w, h)
        canvas.create_text(16, 19, text=source_label,
                           anchor="w", fill=GREEN, font=("Consolas", 11, "bold"))
        canvas.create_text(cw-14, 19, text=caption, anchor="e", fill=FG,
                           font=("Consolas", 11, "bold"))
        canvas.create_rectangle(0, ch-33, cw, ch, fill="#101719", outline="")
        canvas.create_text(16, ch-16, text=quality, anchor="w", fill=GREEN,
                           font=("Consolas", 11, "bold"))
        if self.drag_start and self.drag_current:
            canvas.create_rectangle(*self.drag_start, *self.drag_current, outline=AMBER, width=2)
        self.camera_metrics.config(text=f"{'Eye ' if cropped else ''}{pw} × {ph}   {self.process_fps:.0f} fps")

    def draw_gaze(self, canvas, full=False):
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        margin = 50 if full else 25
        for x in (.25, .5, .75):
            canvas.create_line(w*x, margin, w*x, h-margin, fill="#2d3b3d", dash=(2, 6))
        for y in (.25, .5, .75):
            canvas.create_line(margin, h*y, w-margin, h*y, fill="#2d3b3d", dash=(2, 6))
        canvas.create_oval(w/2-4, h/2-4, w/2+4, h/2+4, fill=MUTED, outline="")
        label = "CALIBRATED GAZE" if self.calibration.ready else "RELATIVE PUPIL MOTION"
        if self.is_linked():
            label = "AR PAGE POINTER / SIMULATED"
        canvas.create_text(18, 16, text=label, anchor="nw", fill=MUTED, font=("Consolas", 10))
        if self.point:
            x, y = self.point[0]*w, self.point[1]*h
            # AR mode preserves the exact viewport coordinate, including edges.
            if not self.is_linked():
                x, y = np.clip(x, 28, w-28), np.clip(y, 28, h-28)
            canvas.create_line(w/2, h/2, x, y, fill="#436945", dash=(5, 5))
            canvas.create_oval(x-22, y-22, x+22, y+22, outline="#395939", width=9)
            canvas.create_oval(x-12, y-12, x+12, y+12, outline=GREEN, width=2)
            canvas.create_oval(x-4, y-4, x+4, y+4, fill=GREEN, outline="")
        else:
            canvas.create_text(w/2, h/2+34, text="Move the mouse over EchoMind AR" if self.is_linked() else "Waiting for a visible pupil", fill=MUTED,
                               font=("Segoe UI", 12))

    def ensure_fullscreen(self):
        if self.full:
            return
        self.full = tk.Toplevel(self.root)
        self.full.title("EchoMind · Gaze Stage")
        self.full.configure(bg=BG)
        # Use the same monitor as the main window before expanding.
        self.full.geometry(f"800x600+{self.root.winfo_x()}+{self.root.winfo_y()}")
        self.full.attributes("-fullscreen", True)
        self.full_canvas = tk.Canvas(self.full, bg=BG, highlightthickness=0)
        self.calibration_preview_photos = []
        self.full_canvas.pack(fill="both", expand=True)
        self.full.bind("<Escape>", lambda _: self.escape())
        self.full.bind("<space>", lambda _: self.begin_points())
        self.full.protocol("WM_DELETE_WINDOW", self.escape)
        self.full.focus_force()

    def open_demo(self):
        self.ensure_fullscreen()
        self.cal_state = None

    def start_calibration(self):
        if self.is_linked():
            self.hint.set("AR linked demo uses the page pointer directly; no calibration is needed.")
            return
        if not self.detection:
            self.hint.set("Connect a camera and wait for a steady green pupil box before calibrating.")
            return
        self.ensure_fullscreen()
        self.cal_state = {"stage": "intro"}

    def begin_points(self):
        if self.cal_state is None:
            return
        if self.cal_state["stage"] in ("intro", "error", "retry"):
            if self.cal_state["stage"] == "retry":
                self.cal_state.update(stage="point", started=time.monotonic(), samples=[])
            else:
                self.cal_state = {"stage": "point", "index": 0, "started": time.monotonic(),
                                  "samples": [], "model": self.new_calibration(), "validation": False,
                                  "screen": self.calibration_display()}

    def _calibration_tick(self, now):
        state = self.cal_state
        if not state or state["stage"] != "point":
            return
        if state.get("screen") and state["screen"] != self.calibration_display():
            state.update(stage="error", message="Display size changed. Press Space to recalibrate on this monitor.")
            return
        elapsed = now-state["started"]
        if elapsed > 1.2 and self.detection and self.detection.quality >= .55 and self.history:
            stamp, p, q = self.history[-1]
            if stamp > state.get("last_sample", 0) and now-stamp < .15:
                state["samples"].append(p.copy())
                state["last_sample"] = stamp
        if elapsed < 2.3:
            return
        if len(state["samples"]) < 10:
            if elapsed > 6:
                state.update(stage="retry", message="Not enough valid samples. Check the pupil box, then press Space to retry this point.")
            return
        samples = np.array(state["samples"])
        pupil = np.median(samples, axis=0)
        if np.max(np.std(samples, axis=0)) > .02:
            state.update(stage="retry", message="Too much eye or camera movement. Hold your gaze and press Space to retry this point.")
            return
        targets = self.targets()
        if state["validation"]:
            error = float(np.linalg.norm(np.array(state["model"].map(pupil)) - np.array((.65, .35))))
            if self.is_binocular():
                errors = state["model"].validation_errors(pupil, (.65, .35))
                error = max(errors["left"], errors["right"], errors["fused"])
            if error > .18:
                state.update(stage="error", message=f"Validation error is too high (normalized distance {error:.2f}).\nKeep the camera still, improve the eye view, and press Space to recalibrate.")
                return
            self.calibration = state["model"]
            self.calibration_screen = state.get("screen")
            # The displayed point still belongs to the previous mapping. Wait
            # for a new camera frame before publishing a calibrated position.
            self.point = self.smoothed = None
            self.cal_text.set(f"Calibrated · Validation error: {error*100:.1f}% in normalized frame units. Recalibrate after moving the camera.")
            if self.is_binocular():
                self.cal_text.set(f"Binocular calibrated · Validation A {errors['left']*100:.1f}% / "
                                  f"B {errors['right']*100:.1f}% / fused {errors['fused']*100:.1f}% "
                                  "(normalized distance). Recalibrate after moving the camera.")
            self.cal_state = {"stage": "done", "error": error}
            return
        state["model"].add(pupil, targets[state["index"]])
        state["index"] += 1
        if state["index"] == len(targets):
            try:
                report = state["model"].fit()
                if report["rmse"] > .13:
                    raise ValueError("Samples are inconsistent. Keep looking at each point while it is shown.")
                state["validation"] = True
            except ValueError as exc:
                state.update(stage="error", message=f"Calibration failed: {exc}\nPress Space to restart, or Esc to return and adjust.")
                return
        state.update(started=now, samples=[], last_sample=now)

    @staticmethod
    def targets():
        return [(.5, .5), (.12, .12), (.5, .12), (.88, .12),
                (.88, .5), (.88, .88), (.5, .88), (.12, .88), (.12, .5)]

    def draw_fullscreen(self, now):
        canvas = self.full_canvas
        w, h = canvas.winfo_width(), canvas.winfo_height()
        state = self.cal_state
        if not state or state["stage"] == "done":
            self.draw_gaze(canvas, full=True)
            title = "Calibrated · Following your gaze" if self.calibration.ready else "Relative pupil motion · Screen position not calibrated"
            footer = "In-app gaze pointer  ·  Keep your head and camera still  ·  Esc to return"
            if self.is_linked():
                title = "AR linked demo · Simulated gaze"
                footer = "Mouse coordinates from the AR page  ·  Simulated eye movement  ·  Esc to return"
            title_y = 28 if state and state["stage"] == "done" and self.is_binocular() else 65
            canvas.create_text(w/2, title_y, text=title, fill=FG, font=("Segoe UI", 22))
            canvas.create_text(w/2, h-48, text=footer,
                               fill=MUTED, font=("Segoe UI", 13))
            if state and state["stage"] == "done":
                draw_calibration_preview(self, now, self.point)
            return
        canvas.delete("all")
        stage = state["stage"]
        if stage in ("intro", "error"):
            bounds = draw_calibration_preview(self, now)
            title = "Look at each of the 9 green points" if stage == "intro" else "Calibration needs another try"
            msg = ("Keep your head and camera still. Look at each point for about 2.3 seconds.\nOne separate validation point follows.\n\nPress Space when ready. Esc cancels."
                   if stage == "intro" else state["message"])
            title_y = max(h/2-80, bounds[1]+bounds[3]+36) if bounds else h/2-80
            canvas.create_text(w/2, title_y, text=title, fill=GREEN, font=("Segoe UI", 25))
            canvas.create_text(w/2, title_y+52, text=msg, anchor="n", fill=FG, font=("Segoe UI", 15), justify="center", width=w-160)
            return
        point = (.65, .35) if state["validation"] else self.targets()[state["index"]]
        draw_calibration_preview(self, now, point)
        x, y = point[0]*w, point[1]*h
        canvas.create_oval(x-24, y-24, x+24, y+24, outline=GREEN, width=2)
        canvas.create_oval(x-6, y-6, x+6, y+6, fill=GREEN, outline="")
        caption = "Validation · Look at the green point" if state["validation"] else f"{state['index']+1} / 9   Look at the green point and hold still"
        canvas.create_text(w/2, 35, text=caption, fill=FG, font=("Segoe UI", 16))
        if stage == "retry":
            caption = state["message"]
        elif now-state["started"] < 1.2:
            caption = "Look at the green point…"
        else:
            caption = "Sampling…" if self.detection else "Pupil not detected · Waiting for a clear view…"
        canvas.create_text(w/2, h-40, text=caption + "   ·   Esc to cancel", fill=TEAL,
                           font=("Segoe UI", 13), width=w-100)

    def escape(self):
        self.cal_state = None
        if self.full:
            self.full.destroy()
            self.full = self.full_canvas = None
            self.calibration_preview_photos = []
        if self.selecting:
            self.hint.set("Selection cancelled; previous eye crop kept." if self.roi else "Selection cancelled; showing the full view.")
        self.selecting = False
        self.drag_start = self.drag_current = None
        self.cancel_eye_selection()

    def close(self):
        self.closed = True
        self.bridge.stop()
        self.gaze_publisher.stop()
        if self.stream:
            self.stream.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--synthetic", action="store_true", help="Clearly labeled synthetic eye for UI verification")
    modes.add_argument("--ar-demo", action="store_true", help="Start in mouse-linked EchoMind AR demo mode")
    parser.add_argument("--binocular", action="store_true", help="Track two eye regions from one camera")
    parser.add_argument("--camera-ar", action="store_true", help="Publish calibrated camera gaze to the local AR page")
    parser.add_argument("--ar-port", type=int, default=8765, help="Local EchoMind AR companion port")
    parser.add_argument("--open-ar", action="store_true", help="Also open the local EchoMind AR window")
    args = parser.parse_args()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    app = EyeDemo(root, synthetic=args.synthetic, ar_demo=args.ar_demo, ar_port=args.ar_port,
                  binocular=args.binocular, camera_ar=args.camera_ar)
    if args.open_ar:
        root.after(400, app.open_ar)
    root.mainloop()


if __name__ == "__main__":
    main()
