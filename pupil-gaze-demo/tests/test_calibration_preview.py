"""Live calibration eye cards retain camera alignment and never show stale locks."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import EyeDemo
from calibration_preview import draw_calibration_preview, preview_bounds
from detector import Detection


class FakeCanvas:
    def __init__(self, width=1000, height=700):
        self.width, self.height = width, height
        self.items = []

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def delete(self, _):
        self.items.clear()

    def _add(self, kind, *coords, **options):
        self.items.append((kind, coords, options))

    def create_rectangle(self, *coords, **options):
        self._add("rectangle", *coords, **options)

    def create_text(self, *coords, **options):
        self._add("text", *coords, **options)

    def create_image(self, *coords, **options):
        self._add("image", *coords, **options)

    def create_line(self, *coords, **options):
        self._add("line", *coords, **options)

    def create_oval(self, *coords, **options):
        self._add("oval", *coords, **options)

    def of_kind(self, kind):
        return [item for item in self.items if item[0] == kind]

    def texts(self):
        return [options["text"] for _, _, options in self.of_kind("text")]


def detection(cx, cy, quality=.85):
    return Detection((cx, cy), (20, 16), 0, (int(cx)-10, int(cy)-8, 20, 16), quality, 40)


def fixture():
    # Distinct horizontal and vertical color ramps expose swaps, extra mirroring,
    # accidental full-frame scaling, and BGR/RGB mistakes in the preview.
    frame = np.zeros((120, 240, 3), np.uint8)
    frame[:, :, 0] = np.arange(240, dtype=np.uint8)
    frame[:, :, 1] = np.arange(120, dtype=np.uint8)[:, None]
    frame[:, :, 2] = 173
    return SimpleNamespace(
        is_binocular=lambda: True,
        is_linked=lambda: False,
        full_canvas=FakeCanvas(),
        synthetic=False,
        last_frame=frame,
        last_frame_time=10.,
        eye_rois=((.1, .2, .45, .8), (.55, .2, .9, .8)),
        binocular_tracker=SimpleNamespace(left=detection(65, 55), right=detection(172, 62)),
        calibration_preview_photos=[],
    )


class CalibrationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.photo_patch = patch("calibration_preview.ImageTk.PhotoImage", side_effect=lambda image: image.copy())
        self.photo_patch.start()
        self.addCleanup(self.photo_patch.stop)

    def test_crops_keep_frame_orientation_and_full_frame_overlay_coordinates(self):
        app = fixture()
        draw_calibration_preview(app, 10.1)
        images = app.full_canvas.of_kind("image")
        self.assertEqual(len(images), 2)
        self.assertEqual(len(app.calibration_preview_photos), 2)
        self.assertEqual(app.full_canvas.texts().count("LOCKED"), 2)
        # Four 2px short crosshair lines, two per independently cropped eye.
        crosses = [item for item in app.full_canvas.of_kind("line") if len(item[1]) == 4]
        for index, (roi, det) in enumerate(zip(app.eye_rois, (app.binocular_tracker.left, app.binocular_tracker.right))):
            _, (ox, oy), opts = images[index]
            image = opts["image"]
            left, top, right, bottom = [int(n*s) for n, s in zip(roi, (240, 120, 240, 120))]
            expected = cv2.cvtColor(cv2.resize(app.last_frame[top:bottom, left:right], image.size), cv2.COLOR_BGR2RGB)
            np.testing.assert_array_equal(np.asarray(image), expected)
            self.assertIs(image, app.calibration_preview_photos[index])
            panel = preview_bounds(1000, 700)
            card_w, image_h = (panel[2]-36)/2, panel[3]-92
            scale = min(card_w/(right-left), image_h/(bottom-top))
            expected_center = (ox+(det.center[0]-left)*scale, oy+(det.center[1]-top)*scale)
            _, line, _ = crosses[index*2]
            np.testing.assert_allclose(((line[0]+line[2])/2, (line[1]+line[3])/2), expected_center)

    def test_stale_or_future_frame_has_no_image_or_false_lock(self):
        for stamp in (9., 11.):
            with self.subTest(frame_time=stamp):
                app = fixture()
                app.last_frame_time = stamp
                app.calibration_preview_photos = [object()]
                draw_calibration_preview(app, 10.)
                self.assertEqual(app.full_canvas.of_kind("image"), [])
                self.assertEqual(app.calibration_preview_photos, [])
                self.assertEqual(app.full_canvas.texts().count("NO VIDEO"), 2)
                self.assertNotIn("LOCKED", app.full_canvas.texts())

    def test_individual_eye_status_survives_loss_of_other_eye(self):
        app = fixture()
        app.binocular_tracker.left = None
        draw_calibration_preview(app, 10.1)
        self.assertIn("NO LOCK", app.full_canvas.texts())
        self.assertEqual(app.full_canvas.texts().count("LOCKED"), 1)
        self.assertEqual(len(app.full_canvas.of_kind("image")), 2)
        app.full_canvas.delete("all")
        app.binocular_tracker.left = detection(65, 55, quality=.52)
        draw_calibration_preview(app, 10.2)
        self.assertIn("LOW QUALITY", app.full_canvas.texts())
        self.assertEqual(app.full_canvas.texts().count("LOCKED"), 1)

    def test_camera_alignment_is_not_recentred_on_moving_pupil(self):
        app = fixture()
        draw_calibration_preview(app, 10.1)
        before = [(coords, np.asarray(opts["image"]).copy()) for _, coords, opts in app.full_canvas.of_kind("image")]
        app.full_canvas.delete("all")
        app.binocular_tracker.left = detection(80, 62)
        app.binocular_tracker.right = detection(190, 70)
        draw_calibration_preview(app, 10.2)
        after = app.full_canvas.of_kind("image")
        for (before_coords, before_pixels), (_, after_coords, opts) in zip(before, after):
            self.assertEqual(before_coords, after_coords)
            np.testing.assert_array_equal(before_pixels, np.asarray(opts["image"]))

    def test_panel_avoids_all_sampling_targets_on_small_and_large_screens(self):
        targets = EyeDemo.targets() + [(.65, .35)]
        for width, height in ((640, 480), (800, 600), (1024, 600), (1920, 1080)):
            for target in targets:
                with self.subTest(size=(width, height), target=target):
                    x, y, w, h = preview_bounds(width, height, target)
                    tx, ty = target[0]*width, target[1]*height
                    near_x, near_y = np.clip(tx, x, x+w), np.clip(ty, y, y+h)
                    self.assertGreater((near_x-tx)**2+(near_y-ty)**2, 24**2)
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x+w, width)
                    self.assertLessEqual(y+h, height)

    def test_every_calibration_stage_keeps_both_live_previews(self):
        states = [
            {"stage": "intro"},
            {"stage": "error", "message": "Try calibration again"},
            {"stage": "point", "index": 0, "validation": False, "started": 10.},
            {"stage": "point", "index": 9, "validation": True, "started": 10.},
            {"stage": "retry", "index": 3, "validation": False, "message": "Hold still"},
            {"stage": "done"},
        ]
        for state in states:
            with self.subTest(stage=state):
                app = EyeDemo.__new__(EyeDemo)
                app.__dict__.update(vars(fixture()))
                app.cal_state = state
                app.point = (.65, .35)
                app.calibration = SimpleNamespace(ready=True)
                app.detection = object()
                app.draw_gaze = lambda canvas, **kwargs: canvas.delete("all")
                app.draw_fullscreen(10.1)
                self.assertEqual(len(app.full_canvas.of_kind("image")), 2)

    def test_single_eye_and_linked_modes_do_not_show_camera_cards(self):
        for binocular, linked in ((False, False), (True, True)):
            app = fixture()
            app.is_binocular = lambda: binocular
            app.is_linked = lambda: linked
            self.assertIsNone(draw_calibration_preview(app, 10.1))
            self.assertEqual(app.full_canvas.items, [])


if __name__ == "__main__":
    unittest.main()
