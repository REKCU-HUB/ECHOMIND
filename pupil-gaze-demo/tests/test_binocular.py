"""One-camera binocular behavior tested without personal camera images."""
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from binocular import BinocularTracker, validate_rois


def eye(center=(330, 215)):
    frame = np.full((480, 640, 3), 176, dtype=np.uint8)
    cv2.ellipse(frame, center, (115, 124), 0, 0, 360, (91,)*3, -1)
    cv2.ellipse(frame, center, (43, 58), 12, 0, 360, (9,)*3, -1)
    cv2.circle(frame, (center[0]-10, center[1]+13), 7, (252,)*3, -1)
    return frame


class BinocularTests(unittest.TestCase):
    def setUp(self):
        self.tracker = BinocularTracker()
        self.tracker.set_rois((0, 0, .5, 1), (.5, 0, 1, 1))
        self.frame = np.concatenate((eye((280, 230)), eye((355, 200))), axis=1)

    def test_two_pupils_have_distinct_full_frame_coordinates(self):
        result = self.tracker.detect(self.frame)
        self.assertIsNotNone(result)
        np.testing.assert_allclose(result.feature, (280/1280, 230/480, 995/1280, 200/480), atol=.005)
        self.assertAlmostEqual(result.quality, min(result.left.quality, result.right.quality))
        self.assertIs(result.left, self.tracker.left)
        self.assertIs(result.right, self.tracker.right)
        self.assertIsNot(self.tracker.left_detector, self.tracker.right_detector)

    def test_one_eye_lost_keeps_current_other_overlay_but_no_combined_sample(self):
        self.assertIsNotNone(self.tracker.detect(self.frame))
        self.frame[:, 640:] = 176
        self.assertIsNone(self.tracker.detect(self.frame))
        self.assertIsNotNone(self.tracker.left)
        self.assertIsNone(self.tracker.right)
        self.assertIn("paused", self.tracker.reason)
        self.frame[:, :640] = 176
        self.assertIsNone(self.tracker.detect(self.frame))
        self.assertIsNone(self.tracker.left)
        self.assertIsNone(self.tracker.right)

    def test_second_eye_cannot_fill_missing_first_eye(self):
        self.frame[:, :640] = 176
        self.assertIsNone(self.tracker.detect(self.frame))
        self.assertIsNone(self.tracker.left)
        self.assertIsNotNone(self.tracker.right)

    def test_independent_motion_and_reacquisition(self):
        first = self.tracker.detect(self.frame)
        moved = self.tracker.detect(np.concatenate((eye((390, 245)), eye((355, 200))), axis=1))
        self.assertGreater(moved.feature[0]-first.feature[0], .07)
        np.testing.assert_allclose(moved.feature[2:], first.feature[2:], atol=.001)
        self.tracker.detect(np.full_like(self.frame, 176))
        self.assertIsNotNone(self.tracker.detect(self.frame))

    def test_manual_threshold_applies_to_both_eyes(self):
        result = self.tracker.detect(self.frame, threshold=40)
        self.assertEqual(result.left.threshold, 40)
        self.assertEqual(result.right.threshold, 40)

    def test_invalid_regions_are_rejected_atomically(self):
        original = self.tracker.rois
        for bad in ((0, 0, 1.1, 1), (0, 0, float("nan"), 1),
                    (.5, 0, .1, 1), (0, 0, 0, 1), (0, 0, 1), None):
            with self.assertRaises(ValueError):
                self.tracker.set_rois(bad, (.5, 0, 1, 1))
            self.assertEqual(self.tracker.rois, original)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.tracker.set_rois((0, 0, .6, 1), (.4, 0, 1, 1))
        self.assertEqual(self.tracker.rois, original)

    def test_touching_regions_and_selection_order_are_valid(self):
        self.assertEqual(validate_rois((.5, 0, 1, 1), (0, 0, .5, 1)),
                         ((.5, 0, 1, 1), (0, 0, .5, 1)))

    def test_bad_frame_and_tiny_regions_never_return_stale_samples(self):
        self.assertIsNotNone(self.tracker.detect(self.frame))
        for bad in (None, np.zeros((2, 2, 2), np.uint8), np.zeros((2, 2), float)):
            self.assertIsNone(self.tracker.detect(bad))
            self.assertIsNone(self.tracker.left)
            self.assertIsNone(self.tracker.right)
        self.tracker.set_rois((0, 0, .01, .01), (.5, 0, 1, 1))
        self.assertIsNone(self.tracker.detect(self.frame))
        self.assertIn("24 x 24", self.tracker.reason)

    def test_reset_keeps_regions_clear_removes_them(self):
        self.assertIsNotNone(self.tracker.detect(self.frame))
        self.tracker.reset()
        self.assertTrue(self.tracker.ready)
        self.assertIsNone(self.tracker.left)
        self.assertIsNone(self.tracker.right)
        self.assertIsNone(self.tracker.left_detector._previous)
        self.assertIsNone(self.tracker.right_detector._previous)
        self.tracker.clear_rois()
        self.assertFalse(self.tracker.ready)
        self.assertIsNone(self.tracker.detect(self.frame))
        self.assertIn("Select", self.tracker.reason)

    def test_resolution_change_keeps_normalized_coordinates(self):
        original = self.tracker.detect(self.frame)
        resized = self.tracker.detect(cv2.resize(self.frame, (2560, 960)))
        np.testing.assert_allclose(resized.feature, original.feature, atol=.002)


if __name__ == "__main__":
    unittest.main()
