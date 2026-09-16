"""Eye crop preview regressions without Tk windows or camera access."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import EyeDemo


class FakeCanvas:
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
    y, x = np.indices((80, 120), dtype=np.uint8)
    # Each source pixel encodes its full-frame location, exposing wrong crops.
    app.last_frame = np.stack((x, y, np.full_like(x, 7)), axis=2)
    app.roi = (.25, .25, .75, .75)
    app.selecting = False
    app.drag_start = app.drag_current = None
    app.video = FakeCanvas()
    app.camera_metrics = Mock()
    app.hint = Mock()
    app.invalidate = Mock()
    app.process_fps = 30
    app.synthetic = True
    app.detection = None
    app.neutral = None
    app.point = None
    app.full = None
    return app


class PreviewCropTests(unittest.TestCase):
    def setUp(self):
        self.photo_patch = patch("app.ImageTk.PhotoImage", side_effect=lambda im: im.copy())
        self.photo_patch.start()
        self.addCleanup(self.photo_patch.stop)

    def test_cropped_pixels_and_tracking_overlay_share_full_frame_coordinates(self):
        app = fake_app()
        app.detection = SimpleNamespace(center=(60, 40), bbox=(54, 34, 12, 12),
                                        axes=(12, 12), angle=0, quality=.9)
        app.neutral = (.4, .4)
        app.draw_video()

        image = np.asarray(app.video_photo)
        self.assertEqual(image.shape, (160, 240, 3))
        np.testing.assert_array_equal(image[0, 0], (7, 20, 30))
        np.testing.assert_array_equal(image[-1, -1], (7, 59, 89))
        lines = [(args, kw) for name, args, kw in app.video.items if name == "create_line"]
        self.assertIn((110, 118, 130, 118), [args for args, _ in lines])
        self.assertIn((120, 108, 120, 128), [args for args, _ in lines])
        arrow = next(args for args, kw in lines if kw.get("arrow") == "last")
        np.testing.assert_allclose(arrow, (72, 86, 120, 118))
        self.assertEqual(app.detection.center, (60, 40))

    def test_reselection_shows_whole_frame_and_escape_restores_existing_crop(self):
        app = fake_app()
        app.select_roi()
        self.assertTrue(app.selecting)
        np.testing.assert_array_equal(np.asarray(app.video_photo)[0, 0], (7, 0, 0))
        np.testing.assert_array_equal(np.asarray(app.video_photo)[-1, -1], (7, 79, 119))
        app.drag_start, app.drag_current = (20, 50), (80, 100)
        app.escape()
        app.draw_video()
        self.assertEqual(app.roi, (.25, .25, .75, .75))
        self.assertFalse(app.selecting)
        self.assertIsNone(app.drag_start)
        np.testing.assert_array_equal(np.asarray(app.video_photo)[0, 0], (7, 20, 30))
        app.invalidate.assert_not_called()

    def test_reset_discards_crop_and_pending_selection(self):
        app = fake_app()
        app.selecting = True
        app.drag_start = (20, 50)
        app.drag_current = (80, 100)
        app.reset_roi()
        app.draw_video()
        self.assertIsNone(app.roi)
        self.assertFalse(app.selecting)
        self.assertIsNone(app.drag_start)
        self.assertIsNone(app.drag_current)
        np.testing.assert_array_equal(np.asarray(app.video_photo)[0, 0], (7, 0, 0))
        np.testing.assert_array_equal(np.asarray(app.video_photo)[-1, -1], (7, 79, 119))
        app.invalidate.assert_called_once_with()

    def test_mirror_preserves_selected_eye_and_flips_its_pixels(self):
        app = fake_app()
        app.roi = (.125, .25, .625, .75)
        app.selecting = True
        app.drag_start = (10, 20)
        app.mirror_changed()
        app.draw_video()
        self.assertEqual(app.roi, (.375, .25, .875, .75))
        self.assertFalse(app.selecting)
        self.assertIsNone(app.drag_start)
        image = np.asarray(app.video_photo)
        np.testing.assert_array_equal(image[0, 0], (7, 20, 74))
        np.testing.assert_array_equal(image[-1, -1], (7, 59, 15))
        app.invalidate.assert_called_once_with()

    def test_binocular_camera_has_separate_overlays_and_neutral_origins(self):
        app = fake_app()
        app.is_binocular = lambda: True
        app.draw_eye_regions = Mock()
        app.roi = None
        app.point = (.75, .5)
        app.detection = SimpleNamespace(quality=.9)
        app.neutral = np.array([.25, .525, .75, .525])
        app.binocular_tracker = SimpleNamespace(
            left=SimpleNamespace(center=(40, 40), bbox=(34, 34, 12, 12), axes=(12, 12), angle=0),
            right=SimpleNamespace(center=(100, 40), bbox=(94, 34, 12, 12), axes=(12, 12), angle=0))
        app.draw_video()
        arrows = [args for name, args, kw in app.video.items
                  if name == "create_line" and kw.get("arrow") == "last"]
        self.assertEqual(len(arrows), 2)
        np.testing.assert_allclose(arrows, [(60, 122, 80, 118), (180, 122, 200, 118)])
        text = " ".join(kw.get("text", "") for _, _, kw in app.video.items)
        self.assertIn("BOTH EYES LOCKED", text)
        self.assertNotIn("Q 0", text)


if __name__ == "__main__":
    unittest.main()
