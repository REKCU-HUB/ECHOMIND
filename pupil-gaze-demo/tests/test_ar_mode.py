"""Mode boundaries must release cameras and never present stale simulated input."""
from collections import deque
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import EyeDemo


class TextValue:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def fake_app():
    app = EyeDemo.__new__(EyeDemo)
    app.mode = TextValue("camera")
    app._active_mode = "camera"
    app._saved_camera_roi = None
    app._demo_eye_xy = np.array([.5, .5])
    app.synthetic = False
    app.roi = (.15, .25, .85, .7)
    app.stream = None
    app.seq = 3
    app.point = (.8, .2)
    app.smoothed = np.array(app.point)
    app.detection = SimpleNamespace(quality=.9)
    app.last_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    app.neutral = np.array([.5, .5])
    app.history = deque([(10., app.neutral, .9)])
    app.cal_state = {"stage": "intro"}
    app.detector = Mock()
    app.calibration = Mock()
    app.bridge = Mock()
    app.hint = TextValue()
    app.cal_text = TextValue()
    app.status_text = TextValue()
    app.camera_heading = Mock()
    app.camera_metrics = Mock()
    app.quality_label = Mock()
    app.direction_label = Mock()
    app._set_camera_controls = Mock()
    app.connect = Mock()
    app.selecting = True
    app.drag_start = (10, 20)
    app.drag_current = (100, 200)
    app.full = None
    app.full_canvas = None
    app.root = Mock()
    app.last_tick = 10.
    app.process_fps = 30.
    app.draw_video = Mock()
    app.draw_gaze = Mock()
    app.gaze = Mock()
    return app


class ARModeTests(unittest.TestCase):
    def test_delayed_camera_connect_is_ignored_after_switching_to_ar(self):
        app = EyeDemo.__new__(EyeDemo)
        app.synthetic = False
        app.mode = TextValue("ar")
        # No camera selector exists in this fixture: opening it is a failure.
        self.assertIsNone(EyeDemo.connect(app))

    def test_switch_releases_camera_and_restores_crop_without_old_detection(self):
        app = fake_app()
        crop = app.roi
        stream = Mock(running=False)
        app.stream = stream
        app.mode.set("ar")
        app.change_mode()
        stream.stop.assert_called_once()
        self.assertIsNone(app.stream)
        self.assertIsNone(app.roi)
        self.assertIsNone(app.point)
        self.assertIsNone(app.detection)
        self.assertEqual(len(app.history), 0)
        self.assertIsNone(app.cal_state)
        self.assertFalse(app.selecting)
        app.bridge.start.assert_called_once()
        app._set_camera_controls.assert_called_with(False)
        self.assertEqual(app._saved_camera_roi, crop)

        app.point = (.1, .9)
        app.detection = SimpleNamespace(quality=0.)
        app.mode.set("camera")
        app.change_mode()
        app.bridge.stop.assert_called_once()
        self.assertEqual(app.roi, crop)
        self.assertIsNone(app.last_frame)
        self.assertIsNone(app.point)
        self.assertIsNone(app.detection)
        app.connect.assert_called_once()
        app._set_camera_controls.assert_called_with(True)

    def test_camera_still_releasing_cannot_enter_linked_mode(self):
        app = fake_app()
        crop = app.roi
        stream = Mock(running=True)
        app.stream = stream
        app.mode.set("ar")
        app.change_mode()
        stream.stop.assert_called_once()
        self.assertEqual(app.mode.get(), "camera")
        self.assertEqual(app._active_mode, "camera")
        self.assertIs(app.stream, stream)
        self.assertEqual(app.roi, crop)
        self.assertIsNone(app.point)
        self.assertIsNone(app.detection)
        app.bridge.start.assert_not_called()
        app._set_camera_controls.assert_not_called()

    def test_linked_pointer_is_exact_and_cleared_on_inactive_or_offline_input(self):
        app = fake_app()
        app.mode.set("ar")
        app.change_mode()
        app.bridge.snapshot.return_value = {"online": True, "active": True, "x": .0, "y": 1.}
        app.tick_linked(10.04)
        self.assertEqual(app.point, (.0, 1.))
        self.assertIsNotNone(app.detection)
        self.assertEqual(app.detection.quality, 0.)
        self.assertIn("SIMULATED", app.quality_label.config.call_args.kwargs["text"])
        self.assertEqual(len(app.history), 0)
        for state in ({"online": True, "active": False}, {"online": False, "active": True}):
            with self.subTest(state=state):
                app.bridge.snapshot.return_value = {**state, "x": .0, "y": 1.}
                app.tick_linked(10.08)
                self.assertIsNone(app.point)
                self.assertIsNone(app.detection)
                self.assertIn("SIMULATED", app.quality_label.config.call_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
