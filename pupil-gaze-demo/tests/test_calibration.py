import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibration import Calibration


TARGETS = np.array([(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)])


def pupil_for(target):
    # Includes cross-axis coupling and reversed horizontal direction.
    return np.array([0.56, 0.43]) + np.array([[-0.13, 0.025], [0.018, 0.09]]) @ target


def calibrated(noise=0.0):
    result = Calibration()
    rng = np.random.default_rng(732)
    for target in TARGETS:
        result.add(pupil_for(target) + rng.normal(0, noise, 2), target)
    report = result.fit()
    return result, report


class CalibrationTests(unittest.TestCase):
    def test_known_transform_and_unseen_points(self):
        calibration, report = calibrated()
        self.assertTrue(calibration.ready)
        self.assertEqual(report["count"], 9)
        self.assertLess(report["rmse"], 1e-12)
        for target in ((0.25, 0.7), (0.62, 0.22), (0.5, 0.5)):
            np.testing.assert_allclose(calibration.map(pupil_for(target)), target, atol=1e-12)

    def test_noisy_samples_remain_useful(self):
        calibration, report = calibrated(noise=0.0015)
        self.assertGreater(report["rmse"], 0)
        self.assertLess(report["rmse"], 0.05)
        self.assertTrue(np.isfinite(report["loo_rmse"]))
        for target in ((0.2, 0.7), (0.7, 0.25), (0.5, 0.5)):
            np.testing.assert_allclose(calibration.map(pupil_for(target)), target, atol=0.04)

    def test_rejects_constant_tiny_or_collinear_pupil_samples(self):
        datasets = [
            [(0.5, 0.5)] * len(TARGETS),
            [(0.5 + x * 0.003, 0.5 + y * 0.003) for x, y in TARGETS],
            [(0.35 + i * 0.02, 0.35 + i * 0.03) for i in range(len(TARGETS))],
        ]
        for points in datasets:
            with self.subTest(points=points):
                calibration = Calibration()
                for pupil, target in zip(points, TARGETS):
                    calibration.add(pupil, target)
                with self.assertRaises(ValueError):
                    calibration.fit()
                self.assertFalse(calibration.ready)

    def test_rejects_too_few_or_poorly_covered_targets(self):
        for targets in (TARGETS[:4], TARGETS * 0.1 + 0.45):
            calibration = Calibration()
            for target in targets:
                calibration.add(pupil_for(target), target)
            with self.assertRaises(ValueError):
                calibration.fit()

    def test_mapping_is_limited_to_canvas(self):
        calibration, _ = calibrated()
        for target, expected in (((-0.2, 1.2), (0.0, 1.0)), ((1.3, -0.4), (1.0, 0.0))):
            np.testing.assert_allclose(calibration.map(pupil_for(target)), expected)

    def test_new_sample_invalidates_fit_and_reset_clears_samples(self):
        calibration, _ = calibrated()
        calibration.add(pupil_for((0.3, 0.3)), (0.3, 0.3))
        self.assertFalse(calibration.ready)
        with self.assertRaises(ValueError):
            calibration.map((0.5, 0.5))
        calibration.fit()
        calibration.reset()
        self.assertFalse(calibration.ready)
        self.assertEqual(calibration.samples, [])

    def test_saved_samples_round_trip_and_invalid_load_is_atomic(self):
        original, _ = calibrated()
        restored = Calibration()
        restored.load_dict(json.loads(json.dumps(original.to_dict())))
        self.assertTrue(restored.ready)
        point = pupil_for((0.4, 0.7))
        np.testing.assert_allclose(restored.map(point), original.map(point))
        with self.assertRaises(ValueError):
            restored.load_dict({"version": 1, "ready": True, "samples": []})
        np.testing.assert_allclose(restored.map(point), original.map(point))

    def test_nonfinite_coordinates_are_rejected(self):
        calibration = Calibration()
        for bad in ((float("nan"), 0.2), (0.2, float("inf")), (0.2,), (1.1, 0.5)):
            with self.assertRaises(ValueError):
                calibration.add(bad, (0.5, 0.5))
        calibration, _ = calibrated()
        with self.assertRaises(ValueError):
            calibration.map((float("nan"), 0.5))


if __name__ == "__main__":
    unittest.main()
