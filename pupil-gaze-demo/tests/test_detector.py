"""Behavior tests with synthetic eye images; no camera or personal data needed."""

import math
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detector import PupilDetector


def eye(center=(330, 215), axes=(43, 58), angle=12, glints=True):
    image = np.full((480, 640, 3), 176, dtype=np.uint8)
    cv2.ellipse(image, center, (115, 124), 0, 0, 360, (91, 91, 91), -1)
    cv2.ellipse(image, center, axes, angle, 0, 360, (9, 9, 9), -1)
    if glints:
        cv2.circle(image, (center[0] - 10, center[1] + 13), 7, (252, 252, 252), -1)
        cv2.circle(image, (center[0] + 9, center[1] + 11), 5, (249, 249, 249), -1)
    return image


class PupilDetectorTests(unittest.TestCase):
    def test_pupil_center_and_diameter_with_ir_glints(self):
        result = PupilDetector().detect(eye())
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (330, 215)), 3)
        self.assertLess(abs(min(result.axes) - 86), 6)
        self.assertLess(abs(max(result.axes) - 116), 6)
        self.assertGreaterEqual(result.quality, 0.5)
        self.assertLessEqual(result.quality, 1)

    def test_uniform_blank_has_no_lock(self):
        for intensity in (0, 75, 255):
            self.assertIsNone(PupilDetector().detect(np.full((480, 640, 3), intensity, np.uint8)))

    def test_closed_lid_has_no_lock(self):
        image = np.full((480, 640, 3), 160, np.uint8)
        cv2.ellipse(image, (320, 240), (145, 8), 0, 0, 360, (5, 5, 5), -1)
        self.assertIsNone(PupilDetector().detect(image))

    def test_border_lash_does_not_displace_pupil(self):
        image = eye()
        cv2.ellipse(image, (5, 260), (110, 180), 0, 0, 360, (0, 0, 0), -1)
        result = PupilDetector().detect(image)
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (330, 215)), 3)

    def test_sensor_noise_still_finds_real_pupil(self):
        rng = np.random.default_rng(91)
        image = np.clip(eye().astype(np.float32) + rng.normal(0, 7, (480, 640, 3)), 0, 255).astype(np.uint8)
        result = PupilDetector().detect(image)
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (330, 215)), 4)

    def test_nested_iris_matches_demo_and_selects_pupil_boundary(self):
        # The GUI demo has a bright outer eye, dark circular iris, smaller
        # darker pupil, and a glint. Fitting the iris produces a plausible
        # center but a seriously incorrect diameter and inflated quality.
        detector = PupilDetector()
        for now in (0, 1.5, 4.0, 8.0):
            image = np.full((480, 640, 3), 170, np.uint8)
            center = (int(320 + 80 * math.sin(now * .5)), int(240 + 38 * math.sin(now * .7)))
            cv2.ellipse(image, (320, 240), (300, 170), 0, 0, 360, (115, 115, 115), -1)
            cv2.circle(image, center, 95, (90, 90, 90), -1)
            cv2.ellipse(image, center, (40, 49), 15, 0, 360, (8, 8, 8), -1)
            cv2.circle(image, (center[0] + 15, center[1] - 14), 7, (245, 245, 245), -1)
            result = detector.detect(image)
            self.assertIsNotNone(result)
            self.assertLess(math.dist(result.center, center), 3)
            self.assertLess(abs(min(result.axes) - 80), 6)
            self.assertLess(abs(max(result.axes) - 98), 6)
            self.assertLess(result.threshold, 90)

    def test_nested_iris_is_not_accepted_at_bad_manual_threshold(self):
        image = np.full((480, 640, 3), 170, np.uint8)
        cv2.ellipse(image, (320, 240), (300, 170), 0, 0, 360, (115, 115, 115), -1)
        cv2.circle(image, (320, 240), 95, (90, 90, 90), -1)
        cv2.ellipse(image, (320, 240), (40, 49), 15, 0, 360, (8, 8, 8), -1)
        self.assertIsNone(PupilDetector().detect(image, threshold=105))

    def test_nonborder_eyelash_distractor_is_rejected(self):
        image = eye()
        cv2.ellipse(image, (110, 60), (88, 6), 12, 0, 360, (0, 0, 0), -1)
        result = PupilDetector().detect(image)
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (330, 215)), 3)

    def test_roi_that_excludes_eye_cannot_reuse_other_region(self):
        detector = PupilDetector()
        self.assertIsNotNone(detector.detect(eye()))
        self.assertIsNone(detector.detect(eye(), roi=(0.0, 0.0, 0.22, 0.32)))

    def test_roi_coordinates_map_back_to_full_frame(self):
        result = PupilDetector().detect(eye(), roi=(0.25, 0.10, 0.90, 0.85))
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (330, 215)), 3)
        self.assertLessEqual(result.bbox[0], result.center[0])
        self.assertGreater(result.bbox[0] + result.bbox[2], result.center[0])

    def test_large_frame_coordinates_map_back_after_resize(self):
        image = cv2.resize(eye(), (1280, 960))
        result = PupilDetector().detect(image)
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (660, 430)), 6)
        self.assertLess(abs(min(result.axes) - 172), 12)

    def test_manual_threshold_used_exactly(self):
        result = PupilDetector().detect(eye(), threshold=40)
        self.assertIsNotNone(result)
        self.assertEqual(result.threshold, 40)
        self.assertLess(math.dist(result.center, (330, 215)), 3)

    def test_reacquires_large_eye_movement(self):
        detector = PupilDetector()
        self.assertIsNotNone(detector.detect(eye(center=(200, 240))))
        result = detector.detect(eye(center=(435, 240)))
        self.assertIsNotNone(result)
        self.assertLess(math.dist(result.center, (435, 240)), 3)

    def test_lock_lost_does_not_return_stale_position(self):
        detector = PupilDetector()
        self.assertIsNotNone(detector.detect(eye()))
        self.assertIsNone(detector.detect(np.full((480, 640, 3), 180, np.uint8)))
        self.assertEqual(detector.status, "lost")
        detector.reset()
        self.assertEqual(detector.status, "waiting")

    def test_bad_roi_and_frame_fail_cleanly(self):
        detector = PupilDetector()
        self.assertIsNone(detector.detect(None))
        self.assertIsNone(detector.detect(eye(), roi=(0.8, 0.7, 0.2, 0.1)))
        self.assertIsNone(detector.detect(eye(), roi=(0, 0, 0.01, 0.01)))
        self.assertIsNone(detector.detect(eye(), roi=(0, 0, float("nan"), 1)))


if __name__ == "__main__":
    unittest.main()
