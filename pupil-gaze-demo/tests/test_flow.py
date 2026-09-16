"""Calibration flow checks without a display or a camera."""

from collections import deque
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import EyeDemo
from calibration import Calibration
from binocular_calibration import BinocularCalibration


class TextValue:
    def set(self, value):
        self.value = value


def pupil_for(target):
    return np.array([0.56, 0.43]) + np.array([[-0.13, 0.025], [0.018, 0.09]]) @ target


def fake_app():
    app = EyeDemo.__new__(EyeDemo)
    app.cal_state = {"stage": "intro"}
    app.calibration = Calibration()
    app.cal_text = TextValue()
    app.detection = SimpleNamespace(quality=0.9)
    app.history = deque(maxlen=120)
    app.smoothed = None
    with patch("app.time.monotonic", return_value=100.0):
        app.begin_points()
    return app


def sample_point(app, target, pupil_factory=pupil_for):
    """Deliver distinct camera frames, then the end of this target's interval."""
    started = app.cal_state["started"]
    for index in range(15):
        stamp = started + 1.3 + index * 0.04
        app.history.append((stamp, pupil_factory(target), 0.9))
        app._calibration_tick(stamp)
    app._calibration_tick(started + 2.31)


class CalibrationFlowTests(unittest.TestCase):
    def test_binocular_flow_installs_two_maps_only_after_both_validate(self):
        app = fake_app()
        app.tracking = SimpleNamespace(get=lambda: "two")
        app.calibration = BinocularCalibration()
        app.cal_state = {"stage": "intro"}
        app.begin_points()
        def two_pupils(target):
            return np.concatenate((pupil_for(target), np.array([.70, .40]) + np.array(target)*.10))
        for target in app.targets():
            sample_point(app, target, two_pupils)
        self.assertFalse(app.calibration.ready)
        sample_point(app, (.65, .35), two_pupils)
        self.assertEqual(app.cal_state["stage"], "done")
        self.assertIsInstance(app.calibration, BinocularCalibration)
        np.testing.assert_allclose(app.calibration.map(two_pupils((.2, .8))), (.2, .8))

    def test_binocular_validation_rejects_one_incorrect_eye(self):
        app = fake_app()
        app.tracking = SimpleNamespace(get=lambda: "two")
        app.calibration = BinocularCalibration()
        app.cal_state = {"stage": "intro"}
        app.begin_points()
        def two_pupils(target):
            return np.concatenate((pupil_for(target), np.array([.70, .40]) + np.array(target)*.10))
        for target in app.targets():
            sample_point(app, target, two_pupils)
        sample_point(app, (.65, .35), lambda target: np.concatenate((pupil_for(target), [.705, .495])))
        self.assertEqual(app.cal_state["stage"], "error")
        self.assertFalse(app.calibration.ready)

    def test_repeated_camera_frame_cannot_fill_sample_quota(self):
        app = fake_app()
        stamp = app.cal_state["started"] + 1.3
        app.history.append((stamp, pupil_for((0.5, 0.5)), 0.9))
        for now in np.linspace(stamp, stamp + 0.12, 20):
            app._calibration_tick(float(now))
        self.assertEqual(len(app.cal_state["samples"]), 1)
        app._calibration_tick(app.cal_state["started"] + 6.1)
        self.assertEqual(app.cal_state["stage"], "retry")
        self.assertEqual(app.cal_state["index"], 0)
        self.assertEqual(app.cal_state["model"].samples, [])

    def test_retry_keeps_completed_targets_but_discards_failed_point_samples(self):
        app = fake_app()
        sample_point(app, (0.5, 0.5))
        self.assertEqual(app.cal_state["index"], 1)
        model = app.cal_state["model"]
        app.cal_state["samples"] = [pupil_for((0.12, 0.12))]
        app.detection = None
        app._calibration_tick(app.cal_state["started"] + 6.1)
        self.assertEqual(app.cal_state["stage"], "retry")
        with patch("app.time.monotonic", return_value=110.0):
            app.begin_points()
        self.assertEqual(app.cal_state["stage"], "point")
        self.assertEqual(app.cal_state["index"], 1)
        self.assertIs(app.cal_state["model"], model)
        self.assertEqual(len(model.samples), 1)
        self.assertEqual(app.cal_state["samples"], [])

    def test_stale_frame_not_sampled_even_if_detection_object_remains(self):
        app = fake_app()
        app.history.append((100.0, pupil_for((0.5, 0.5)), 0.9))
        app._calibration_tick(101.5)
        self.assertEqual(app.cal_state["samples"], [])

    def test_new_calibration_is_installed_only_after_independent_validation(self):
        app = fake_app()
        original = app.calibration
        for target in app.targets():
            sample_point(app, target)
        self.assertTrue(app.cal_state["validation"])
        self.assertTrue(app.cal_state["model"].ready)
        self.assertIs(app.calibration, original)
        sample_point(app, (0.65, 0.35))
        self.assertEqual(app.cal_state["stage"], "done")
        self.assertTrue(app.calibration.ready)
        np.testing.assert_allclose(app.calibration.map(pupil_for((0.2, 0.8))), (0.2, 0.8))

    def test_failed_validation_does_not_install_bad_fit_and_space_starts_fresh(self):
        app = fake_app()
        original = app.calibration
        for target in app.targets():
            sample_point(app, target)
        sample_point(app, (0.15, 0.85))
        self.assertEqual(app.cal_state["stage"], "error")
        self.assertIs(app.calibration, original)
        self.assertFalse(app.calibration.ready)
        with patch("app.time.monotonic", return_value=150.0):
            app.begin_points()
        self.assertEqual(app.cal_state["index"], 0)
        self.assertFalse(app.cal_state["validation"])
        self.assertEqual(app.cal_state["model"].samples, [])

    def test_roi_accounts_for_letterboxing_and_reverse_drag(self):
        app = EyeDemo.__new__(EyeDemo)
        app.last_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        app.view_transform = (0.5, 20.0, 40.0)
        app.drag_start = (260.0, 220.0)
        app.drag_current = (100.0, 100.0)
        app.selecting = True
        app.hint = TextValue()
        app.invalidate = lambda: None
        app.roi_end(SimpleNamespace(x=100.0, y=100.0))
        np.testing.assert_allclose(app.roi, (0.25, 0.25, 0.75, 0.75))
        self.assertFalse(app.selecting)
        self.assertIsNone(app.drag_start)


if __name__ == "__main__":
    unittest.main()
