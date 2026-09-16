"""Publish calibrated real camera gaze to the local AR app; never video."""
import math
import time
import tkinter as tk

from real_gaze import GazePublisher


class CameraARMode:
    def init_camera_ar(self, enabled=False, port=8765):
        self.camera_ar = tk.BooleanVar(value=enabled)
        self.gaze_publisher = GazePublisher(port)
        self.calibration_screen = None
        self.camera_frame_stamp = 0.
        if enabled:
            self.gaze_publisher.start()

    def build_camera_link_control(self, parent):
        self.camera_link_check = tk.Checkbutton(
            parent, text="Link camera to AR", variable=self.camera_ar,
            command=self.toggle_camera_ar, bg="#101719", fg="#64c7c0",
            selectcolor="#253538", activebackground="#101719",
            activeforeground="#9cff57", font=("Segoe UI", 10))
        self.camera_link_check.pack(side="left", padx=(0, 8))
        self.camera_link_label = self.label(parent, "", 9, "#90a6a4")
        self.camera_link_label.pack(side="left")

    def toggle_camera_ar(self):
        if self.camera_ar.get():
            self.gaze_publisher.start()
            self.hint.set("Calibrate, press Esc, then open AR and start fullscreen gaze on the same monitor.")
            self.publish_camera_gaze(time.monotonic())
        else:
            self.publish_camera_gaze(time.monotonic())
            self.gaze_publisher.stop()
            self.camera_link_label.config(text="Link off")

    def calibration_display(self):
        canvas = getattr(self, "full_canvas", None)
        if canvas is None:
            return None
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width <= 1 or height <= 1:
            return None
        return {"width": int(width), "height": int(height)}

    def camera_gaze_state(self, now):
        enabled = bool(self.camera_ar.get()) and not self.is_linked()
        calibrated = bool(self.calibration.ready) and self.calibration_screen is not None
        point = self.point
        finite_point = (point is not None and len(point) == 2 and
                        all(math.isfinite(float(v)) and 0 <= v <= 1 for v in point))
        quality = float(self.detection.quality) if self.detection is not None else 0.
        stamp = self.camera_frame_stamp
        fresh = stamp > 0 and 0 <= now-stamp < .25 and self.last_frame is not None
        if not enabled:
            reason = "disabled"
        elif self.synthetic:
            reason = "synthetic"
        elif self.stream is None:
            reason = "camera_off"
        elif not calibrated:
            reason = "uncalibrated"
        elif self.cal_state is not None or self.full is not None:
            reason = "calibrating"
        elif not fresh:
            reason = "stale_frame"
        elif not finite_point or self.detection is None or quality < .5:
            reason = "eye_lost"
        else:
            reason = "tracking"
        return {
            "enabled": enabled, "active": reason == "tracking", "calibrated": calibrated,
            "x": float(point[0]) if finite_point else .5,
            "y": float(point[1]) if finite_point else .5,
            "quality": quality, "eyes": 2 if self.is_binocular() else 1,
            "reason": reason, "calibration_screen": self.calibration_screen if calibrated else None,
        }

    def publish_camera_gaze(self, now):
        if not hasattr(self, "gaze_publisher"):
            return
        state = self.camera_gaze_state(now)
        self.gaze_publisher.update(state, capture_stamp=self.camera_frame_stamp or None)
        network = self.gaze_publisher.snapshot()
        if not hasattr(self, "camera_link_label"):
            return
        if not state["enabled"]:
            text, color = "Link off", "#90a6a4"
        elif not network.get("online"):
            text, color = "AR offline", "#ffc77a"
        elif state["active"]:
            text, color = "Gaze → AR", "#9cff57"
        else:
            text = {"uncalibrated": "Calibrate first", "calibrating": "Return to AR",
                    "synthetic": "Test input blocked", "camera_off": "Camera off",
                    "eye_lost": "Eyes lost", "stale_frame": "Waiting for video"}.get(state["reason"], "Paused")
            color = "#90a6a4"
        self.camera_link_label.config(text=text, fg=color)
