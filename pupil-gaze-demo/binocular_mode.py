"""Two real eye regions from the same camera frame; no generated eye data."""
import tkinter as tk

import numpy as np

from binocular import BinocularTracker
from binocular_calibration import BinocularCalibration
from calibration import Calibration


class BinocularMode:
    def init_binocular(self, enabled=False):
        self.tracking = tk.StringVar(value="two" if enabled else "one")
        self._active_tracking = self.tracking.get()
        self.binocular_tracker = BinocularTracker()
        self.eye_rois = [None, None]
        self._pending_eye_rois = None
        self._selection_eye = None
        self._mono_roi = None
        self.calibration = self.new_calibration()

    def is_binocular(self):
        return getattr(self, "tracking", None) is not None and self.tracking.get() == "two"

    def new_calibration(self):
        return BinocularCalibration() if self.is_binocular() else Calibration()

    def build_tracking_bar(self):
        bar = tk.Frame(self.root, bg="#192326", padx=14, pady=6)
        bar.pack(fill="x", padx=24, pady=(4, 0))
        self.label(bar, "TRACKING", 9, "#90a6a4").pack(side="left", padx=(0, 12))
        self.binocular_controls = []
        for text, value in (("Single eye", "one"), ("Two eyes / one camera", "two")):
            widget = tk.Radiobutton(bar, text=text, value=value, variable=self.tracking,
                                   command=self.change_tracking, bg="#192326", fg="#ecf2ed",
                                   selectcolor="#253538", activebackground="#192326",
                                   activeforeground="#9cff57", font=("Segoe UI", 10))
            widget.pack(side="left", padx=(0, 10))
            self.binocular_controls.append(widget)
        for text, command in (("Select eye A", lambda: self.select_eye(0)),
                              ("Select eye B", lambda: self.select_eye(1)),
                              ("Reset eyes", self.reset_eyes)):
            widget = self.button(bar, text, command)
            widget.pack(side="left", padx=3)
            self.binocular_controls.append(widget)
        self.eye_status = self.label(bar, "", 9, "#64c7c0")
        self.eye_status.pack(side="right", padx=4)

    def change_tracking(self):
        if self.is_linked():
            return
        if self.tracking.get() == getattr(self, "_active_tracking", None):
            return
        self._active_tracking = self.tracking.get()
        self.escape()
        if self.is_binocular():
            self._mono_roi = self.roi
            self.roi = self.combined_eye_roi()
            self.camera_heading.config(text="01  /  BINOCULAR CAMERA")
        else:
            self.roi = self._mono_roi
            self.camera_heading.config(text="01  /  PUPIL CAMERA")
        self.calibration = self.new_calibration()
        self.invalidate()
        self.hint.set("Select eye A, then eye B. Keep both eyes visible and the camera still."
                      if self.is_binocular() else "Single-eye tracking. Set the center or calibrate again.")
        self.update_eye_status()
        self.draw_video()

    def combined_eye_roi(self):
        if not all(roi is not None for roi in self.eye_rois):
            return None
        a, b = self.eye_rois
        return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])

    def select_eye(self, index):
        if self.is_linked():
            return
        if not self.is_binocular():
            self.tracking.set("two")
            self.change_tracking()
        if self.last_frame is None:
            self.hint.set("Connect the camera with both eyes visible before selecting the eye regions.")
            return
        self._pending_eye_rois = list(self.eye_rois)
        self._selection_eye = index
        self.selecting = True
        self.drag_start = self.drag_current = None
        self.hint.set(f"Drag around eye {'AB'[index]} in the full view. Include room for pupil movement; Esc cancels.")
        self.draw_video()

    def accept_eye_roi(self, roi):
        if self._selection_eye is None:
            return
        pending = list(self._pending_eye_rois)
        pending[self._selection_eye] = roi
        self.drag_start = self.drag_current = None
        missing = next((i for i, value in enumerate(pending) if value is None), None)
        if missing is not None:
            self._pending_eye_rois = pending
            self._selection_eye = missing
            self.hint.set(f"Now drag around eye {'AB'[missing]}. Both eyes must have separate, non-overlapping regions.")
            self.draw_video()
            return
        try:
            self.binocular_tracker.set_rois(*pending)
        except ValueError as exc:
            self.hint.set(f"{exc} Try this eye again, or press Esc to cancel.")
            return
        self.eye_rois = pending
        self.roi = self.combined_eye_roi()
        self.selecting = False
        self.cancel_eye_selection()
        self.invalidate()
        self.hint.set("Both eyes selected and cropped. Wait for both pupil boxes, then run 9-point calibration.")
        self.draw_video()

    def cancel_eye_selection(self):
        self._pending_eye_rois = None
        self._selection_eye = None

    def reset_eyes(self):
        if self.is_linked():
            return
        self.eye_rois = [None, None]
        self.binocular_tracker.clear_rois()
        if self.is_binocular():
            self.roi = None
            self.selecting = False
            self.drag_start = self.drag_current = None
            self.cancel_eye_selection()
            self.invalidate()
            self.hint.set("Full view restored. Select eye A and eye B again.")
            self.draw_video()

    def mirror_eye_regions(self):
        if not hasattr(self, "eye_rois"):
            return
        def flip(roi):
            return (1-roi[2], roi[1], 1-roi[0], roi[3]) if roi is not None else None
        self.eye_rois = [flip(roi) for roi in self.eye_rois]
        self._mono_roi = flip(self._mono_roi)
        if all(roi is not None for roi in self.eye_rois):
            self.binocular_tracker.set_rois(*self.eye_rois)
        self.cancel_eye_selection()

    def relative_point(self, feature):
        delta = np.asarray(feature)-self.neutral
        if self.is_binocular():
            delta = delta.reshape(2, 2).mean(axis=0)
        return np.clip(.5+delta*self.gain.get(), 0, 1)

    def eye_overlays(self):
        return [(det, self.neutral[i*2:i*2+2] if self.neutral is not None else None)
                for i, det in enumerate((self.binocular_tracker.left, self.binocular_tracker.right))
                if det is not None]

    def draw_eye_regions(self, canvas, fx, fy, scale, w, h):
        regions = self._pending_eye_rois if self.selecting and self._pending_eye_rois else self.eye_rois
        for i, roi in enumerate(regions):
            if roi is None:
                continue
            a, b, c, d = roi
            color = "#64c7c0" if i == 0 else "#ffc77a"
            canvas.create_rectangle(fx+a*w*scale, fy+b*h*scale, fx+c*w*scale, fy+d*h*scale,
                                    outline=color, dash=(5, 4), width=1)
            canvas.create_text(fx+a*w*scale+8, fy+b*h*scale+8, text=f"EYE {'AB'[i]}",
                               anchor="nw", fill=color, font=("Consolas", 10, "bold"))

    def update_eye_status(self):
        if not hasattr(self, "eye_status"):
            return
        if not self.is_binocular() or self.is_linked():
            self.eye_status.config(text="")
            return
        if not self.binocular_tracker.ready:
            self.eye_status.config(text="Select both eyes")
            self.quality_label.config(text="Select eye A and eye B before tracking", fg="#90a6a4")
        else:
            states = [f"{'AB'[i]} {'LOCK' if det else '--'}" for i, det in
                      enumerate((self.binocular_tracker.left, self.binocular_tracker.right))]
            self.eye_status.config(text=" / ".join(states))
            if self.detection is None:
                self.quality_label.config(text="Both eyes required · Pointer paused", fg="#90a6a4")
