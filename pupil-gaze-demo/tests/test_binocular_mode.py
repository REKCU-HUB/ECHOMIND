"""Binocular UI state and camera flow checks without windows or a camera."""
from collections import deque
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import EyeDemo
from binocular import BinocularTracker
from binocular_calibration import BinocularCalibration
from calibration import Calibration
from detector import PupilDetector


class Value:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Canvas:
    def __init__(self):
        self.items = []

    def winfo_width(self):
        return 240

    def winfo_height(self):
        return 231

    def delete(self, _):
        self.items.clear()

    def __getattr__(self, method):
        if method.startswith("create_"):
            return lambda *args, **kwargs: self.items.append((method, args, kwargs))
        raise AttributeError(method)


def fake_app():
    app = EyeDemo.__new__(EyeDemo)
    app.tracking = Value("two")
    app._active_tracking = "two"
    app.mode = Value("camera")
    app._active_mode = "camera"
    app._saved_camera_roi = None
    app.binocular_tracker = BinocularTracker()
    app.eye_rois = [None, None]
    app._pending_eye_rois = None
    app._selection_eye = None
    app._mono_roi = None
    app.roi = None
    app.selecting = False
    app.drag_start = app.drag_current = None
    app.full = app.full_canvas = app.cal_state = None
    app.synthetic = False
    app.closed = False
    app.stream = None
    app.seq = -1
    app.detector = PupilDetector()
    app.calibration = BinocularCalibration()
    app.history = deque(maxlen=120)
    app.point = app.smoothed = app.detection = app.neutral = None
    app.last_tick = 9.9
    app.last_detection_time = app.last_frame_time = 0.
    app.process_fps = 30.
    app._open_ar_result = None
    y, x = np.indices((80, 120), dtype=np.uint8)
    app.last_frame = np.stack((x, y, np.full_like(x, 7)), axis=2)
    app.view_transform = (1., 0., 0.)
    app.auto, app.mirror, app.gain, app.threshold = Value(True), Value(False), Value(5), Value(50)
    app.hint, app.cal_text, app.status_text = Value(), Value(), Value()
    for name in ("camera_heading", "camera_metrics", "quality_label", "direction_label",
                 "eye_status", "footer_note", "gaze", "root", "bridge"):
        setattr(app, name, Mock())
    app.draw_video = Mock()
    app.draw_gaze = Mock()
    app.connect = Mock()
    app._set_camera_controls = Mock()
    app.video = Canvas()
    return app


def selected_app():
    app = fake_app()
    app.eye_rois = [(0.1, 0.25, 0.4, 0.75), (0.6, 0.2, 0.9, 0.8)]
    app.binocular_tracker.set_rois(*app.eye_rois)
    app.roi = app.combined_eye_roi()
    return app


def paired_eye_frame():
    eye = np.full((480, 640, 3), 176, dtype=np.uint8)
    cv2.ellipse(eye, (320, 230), (115, 124), 0, 0, 360, (91,)*3, -1)
    cv2.ellipse(eye, (320, 230), (43, 58), 12, 0, 360, (9,)*3, -1)
    return np.concatenate((eye, eye), axis=1)


class BinocularModeTests(unittest.TestCase):
    def test_two_selections_commit_together_then_crop_to_union(self):
        app = fake_app()
        a, b = (0.1, 0.25, 0.4, 0.75), (0.6, 0.2, 0.9, 0.8)
        app.select_eye(0)
        app.accept_eye_roi(a)
        self.assertTrue(app.selecting)
        self.assertEqual(app._selection_eye, 1)
        self.assertEqual(app.eye_rois, [None, None])
        self.assertFalse(app.binocular_tracker.ready)
        app.accept_eye_roi(b)
        self.assertEqual(app.eye_rois, [a, b])
        self.assertTrue(app.binocular_tracker.ready)
        self.assertEqual(app.roi, (0.1, 0.2, 0.9, 0.8))
        self.assertFalse(app.selecting)
        self.assertIsNone(app._selection_eye)
        self.assertIsNone(app._pending_eye_rois)

    def test_escape_discards_pending_first_eye_and_preserves_committed_regions(self):
        for app in (fake_app(), selected_app()):
            with self.subTest(selected=app.binocular_tracker.ready):
                original, crop = list(app.eye_rois), app.roi
                app.select_eye(0)
                # Staged first-eye data must not mutate the saved configuration.
                app._pending_eye_rois[0] = (.05, .1, .35, .9)
                app.drag_start, app.drag_current = (10, 20), (40, 70)
                app.escape()
                self.assertEqual(app.eye_rois, original)
                self.assertEqual(app.roi, crop)
                self.assertIsNone(app._pending_eye_rois)
                self.assertIsNone(app._selection_eye)
                self.assertFalse(app.selecting)
                self.assertIsNone(app.drag_start)

    def test_overlap_keeps_previous_pair_and_allows_retry(self):
        app = selected_app()
        original, crop = list(app.eye_rois), app.roi
        app.select_eye(1)
        app.accept_eye_roi((.2, .2, .8, .8))
        self.assertEqual(app.eye_rois, original)
        self.assertEqual(app.binocular_tracker.rois, tuple(original))
        self.assertEqual(app.roi, crop)
        self.assertTrue(app.selecting)
        self.assertEqual(app._selection_eye, 1)
        self.assertIn("overlap", app.hint.get())
        app.accept_eye_roi((.65, .15, .95, .85))
        self.assertFalse(app.selecting)
        self.assertEqual(app.eye_rois[1], (.65, .15, .95, .85))

    def test_tiny_second_drag_keeps_two_eye_selection_active(self):
        app = fake_app()
        app.select_eye(0)
        app.accept_eye_roi((.1, .2, .4, .8))
        app.drag_start = app.drag_current = (70, 30)
        app.roi_end(SimpleNamespace(x=72, y=32))
        self.assertTrue(app.selecting)
        self.assertEqual(app._selection_eye, 1)
        self.assertEqual(app._pending_eye_rois[0], (.1, .2, .4, .8))
        self.assertIsNone(app.drag_start)

    def test_union_preview_is_real_crop_and_reselection_restores_full_frame(self):
        app = selected_app()
        with patch("app.ImageTk.PhotoImage", side_effect=lambda im: im.copy()):
            EyeDemo.draw_video(app)
            pixels = np.asarray(app.video_photo)
            self.assertEqual(pixels.shape, (120, 240, 3))
            np.testing.assert_array_equal(pixels[0, 0], (7, 16, 12))
            np.testing.assert_array_equal(pixels[-1, -1], (7, 63, 107))
            app.select_eye(1)
            EyeDemo.draw_video(app)
            np.testing.assert_array_equal(np.asarray(app.video_photo)[0, 0], (7, 0, 0))
            app.escape()
            EyeDemo.draw_video(app)
            np.testing.assert_array_equal(np.asarray(app.video_photo)[0, 0], (7, 16, 12))

    def test_mirror_moves_both_regions_without_swapping_identity_and_resets_samples(self):
        app = selected_app()
        app._mono_roi = (.05, .1, .3, .9)
        original_frame = app.last_frame.copy()
        app.history.append((10, np.array([.2, .4, .7, .5]), .9))
        app.neutral = np.array([.2, .4, .7, .5])
        app.point = (.7, .8)
        app.select_eye(1)
        app.mirror_changed()
        np.testing.assert_allclose(app.eye_rois, [(0.6, .25, .9, .75), (.1, .2, .4, .8)])
        np.testing.assert_allclose(app.binocular_tracker.rois, app.eye_rois)
        np.testing.assert_allclose(app._mono_roi, (.7, .1, .95, .9))
        np.testing.assert_allclose(app.roi, (.1, .2, .9, .8))
        np.testing.assert_array_equal(app.last_frame, original_frame[:, ::-1])
        self.assertEqual(len(app.history), 0)
        self.assertIsNone(app.neutral)
        self.assertIsNone(app.point)
        self.assertIsNone(app._pending_eye_rois)

    def test_switching_back_restores_single_eye_crop_and_model(self):
        app = selected_app()
        app.tracking.set("one")
        app._active_tracking = "one"
        app.roi = (.15, .25, .45, .75)
        original_crop = app.roi
        app.calibration = Calibration()
        app.tracking.set("two")
        app.change_tracking()
        self.assertIsInstance(app.calibration, BinocularCalibration)
        self.assertEqual(app.roi, app.combined_eye_roi())
        # Clicking the already-selected radio must not replace the mono crop.
        app.change_tracking()
        app.tracking.set("one")
        app.change_tracking()
        self.assertIsInstance(app.calibration, Calibration)
        self.assertEqual(app.roi, original_crop)
        self.assertFalse(app.calibration.ready)

    def test_missing_eye_never_maps_or_keeps_a_fused_pointer(self):
        app = fake_app()
        app.eye_rois = [(0, 0, .5, 1), (.5, 0, 1, 1)]
        app.binocular_tracker.set_rois(*app.eye_rois)
        frame = paired_eye_frame()
        missing = frame.copy()
        missing[:, 640:] = 176
        app.calibration = Mock(ready=True)
        app.calibration.map.return_value = (.25, .75)
        app.stream = Mock(error=None, fps=30.)
        app.stream.read_latest.side_effect = [(1, frame, 10.), (2, missing, 10.04)]
        app._calibration_tick = Mock()
        with patch("app.time.monotonic", return_value=10.):
            app.tick()
        self.assertEqual(app.point, (.25, .75))
        self.assertEqual(app.calibration.map.call_count, 1)
        with patch("app.time.monotonic", return_value=10.04):
            app.tick()
        self.assertIsNone(app.point)
        self.assertIsNone(app.detection)
        self.assertIsNone(app.smoothed)
        self.assertEqual(app.calibration.map.call_count, 1)
        self.assertEqual(len(app.history), 0)
        self.assertIsNotNone(app.binocular_tracker.left)
        self.assertIsNone(app.binocular_tracker.right)
        self.assertEqual(len(app.eye_overlays()), 1)

    def test_ar_round_trip_preserves_regions_but_never_reuses_simulation_samples(self):
        app = selected_app()
        original, crop = list(app.eye_rois), app.roi
        app.mode.set("ar")
        app.change_mode()
        self.assertIsNone(app.roi)
        app.select_eye(0)
        self.assertFalse(app.selecting)
        self.assertEqual(app.eye_rois, original)
        app.reset_eyes()
        self.assertEqual(app.eye_rois, original)
        app.point = (.8, .2)
        app.neutral = np.array([.5, .5])  # Simulated eye uses a 2D neutral.
        app.detection = SimpleNamespace(quality=0.)
        app.mode.set("camera")
        app.change_mode()
        self.assertEqual(app.roi, crop)
        self.assertEqual(app.eye_rois, original)
        self.assertIsInstance(app.calibration, BinocularCalibration)
        self.assertIsNone(app.point)
        self.assertIsNone(app.neutral)
        self.assertIsNone(app.detection)
        self.assertEqual(len(app.history), 0)
        app.connect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
