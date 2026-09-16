"""Only fresh, calibrated camera samples may drive the local AR page."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import EyeDemo


class Value:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def fixture():
    app = EyeDemo.__new__(EyeDemo)
    app.camera_ar = Value(True)
    app.mode = Value("camera")
    app.tracking = Value("two")
    app.calibration = SimpleNamespace(ready=True)
    app.calibration_screen = {"width": 1920, "height": 1080}
    app.camera_frame_stamp = 10.
    app.point = (.25, .75)
    app.detection = SimpleNamespace(quality=.9)
    app.synthetic = False
    app.stream = object()
    app.last_frame = np.zeros((10, 10, 3), np.uint8)
    app.cal_state = None
    app.full = None
    return app


class CameraARModeTests(unittest.TestCase):
    def test_calibrated_camera_coordinates_are_preserved(self):
        state = fixture().camera_gaze_state(10.1)
        self.assertTrue(state["active"])
        self.assertEqual((state["x"], state["y"]), (.25, .75))
        self.assertEqual(state["eyes"], 2)
        self.assertEqual(state["reason"], "tracking")

    def test_uncalibrated_or_unknown_screen_never_maps_relative_motion_to_ar(self):
        for field, value in (("calibration", SimpleNamespace(ready=False)), ("calibration_screen", None)):
            app = fixture()
            setattr(app, field, value)
            state = app.camera_gaze_state(10.1)
            self.assertFalse(state["active"])
            self.assertEqual(state["reason"], "uncalibrated")

    def test_old_or_missing_frames_and_lost_eye_pause_gaze(self):
        cases = (("camera_frame_stamp", 9.74, "stale_frame"),
                 ("last_frame", None, "stale_frame"),
                 ("detection", None, "eye_lost"),
                 ("detection", SimpleNamespace(quality=.4), "eye_lost"),
                 ("stream", None, "camera_off"),
                 ("point", (float("nan"), .5), "eye_lost"))
        for field, value, reason in cases:
            with self.subTest(field=field, reason=reason):
                app = fixture()
                setattr(app, field, value)
                state = app.camera_gaze_state(10.1)
                self.assertFalse(state["active"])
                self.assertEqual(state["reason"], reason)

    def test_calibration_and_native_fullscreen_block_page_activation(self):
        for field, value in (("cal_state", {"stage": "point"}), ("cal_state", {"stage": "done"}), ("full", object())):
            app = fixture()
            setattr(app, field, value)
            self.assertEqual(app.camera_gaze_state(10.1)["reason"], "calibrating")

    def test_accepting_calibration_discards_point_from_previous_mapping(self):
        for previously_calibrated in (False, True):
            with self.subTest(previously_calibrated=previously_calibrated):
                app = fixture()
                app.calibration = SimpleNamespace(ready=previously_calibrated)
                app.point = (.1, .2)
                app.smoothed = np.array(app.point)
                app.cal_text = Mock()
                feature = np.array([.3, .4, .3, .4])
                app.history = [(10., feature, .9)]
                screen = {"width": 1920, "height": 1080}
                model = SimpleNamespace(
                    ready=True, map=lambda point: (.65, .35),
                    validation_errors=lambda point, target: {"left": 0., "right": 0., "fused": 0.})
                app.calibration_display = lambda: screen
                app.cal_state = {
                    "stage": "point", "started": 7., "screen": screen,
                    "validation": True, "model": model,
                    "samples": [feature.copy() for _ in range(10)],
                }
                app.full = Mock()
                app.selecting = False

                app._calibration_tick(10.1)
                self.assertIs(app.calibration, model)
                self.assertEqual(app.cal_state["stage"], "done")
                app.escape()  # No new camera frame has arrived yet.
                state = app.camera_gaze_state(10.11)
                self.assertTrue(state["calibrated"])
                self.assertFalse(state["active"])
                self.assertIsNone(app.point)
                self.assertIsNone(app.smoothed)

                # A subsequently mapped, fresh frame may resume the AR pointer.
                app.point = model.map(feature)
                app.camera_frame_stamp = 10.12
                state = app.camera_gaze_state(10.13)
                self.assertTrue(state["active"])
                self.assertEqual((state["x"], state["y"]), (.65, .35))

    def test_simulations_and_disabled_link_never_publish_live_camera_gaze(self):
        for field, value, reason in (("synthetic", True, "synthetic"),
                                     ("mode", Value("ar"), "disabled"),
                                     ("camera_ar", Value(False), "disabled")):
            app = fixture()
            setattr(app, field, value)
            state = app.camera_gaze_state(10.1)
            self.assertFalse(state["active"])
            self.assertEqual(state["reason"], reason)

    def test_opening_ar_preserves_live_camera_mode_and_calibration(self):
        app = fixture()
        app._opening_ar = False
        app.bridge = SimpleNamespace(port=8878)
        app.hint = Mock()
        app.toggle_camera_ar = Mock()
        calibration = app.calibration
        with patch("ar_mode.threading.Thread") as thread, patch("ar_mode.open_ar_window", return_value="Camera link") as opener:
            app.open_ar()
            thread.call_args.kwargs["target"]()
            opener.assert_called_once_with(8878, camera=True)
        self.assertEqual(app.mode.get(), "camera")
        self.assertIs(app.calibration, calibration)
        self.assertEqual(app._open_ar_result, "Camera link")


if __name__ == "__main__":
    unittest.main()
