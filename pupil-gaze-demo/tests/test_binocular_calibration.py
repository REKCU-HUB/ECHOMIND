import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from binocular_calibration import BinocularCalibration


TARGETS = np.array([(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)])


def left_for(target):
    return np.array([0.26, 0.43]) + np.array([[-0.13, 0.025], [0.018, 0.09]]) @ target


def right_for(target):
    return np.array([0.68, 0.38]) + np.array([[-0.10, -0.013], [-0.019, 0.11]]) @ target


def pair_for(left_target, right_target=None):
    if right_target is None:
        right_target = left_target
    return np.concatenate((left_for(left_target), right_for(right_target)))


def calibrated(noise=0.0):
    result = BinocularCalibration()
    rng = np.random.default_rng(732)
    for target in TARGETS:
        result.add(pair_for(target) + rng.normal(0, noise, 4), target)
    return result, result.fit()


class BinocularCalibrationTests(unittest.TestCase):
    def test_independent_affines_handle_different_origins_and_directions(self):
        model, report = calibrated()
        self.assertTrue(model.ready)
        self.assertEqual(report["count"], 9)
        self.assertEqual(len(report["pupil_span"]), 4)
        self.assertLess(report["rmse"], 1e-12)
        for target in ((0.25, 0.7), (0.62, 0.22), (0.5, 0.5)):
            np.testing.assert_allclose(model.map(pair_for(target)), target, atol=1e-12)
            self.assertLess(max(model.validation_errors(pair_for(target), target).values()), 1e-12)

    def test_noisy_fit_reports_worst_eye_not_just_fused_error(self):
        model, report = calibrated(0.0015)
        self.assertGreater(report["fused_rmse"], 0)
        self.assertEqual(report["rmse"], max(report["left"]["rmse"], report["right"]["rmse"], report["fused_rmse"]))
        self.assertLess(report["rmse"], 0.05)
        self.assertEqual(report["loo_rmse"], max(report["left"]["loo_rmse"], report["right"]["loo_rmse"]))
        np.testing.assert_allclose(model.map(pair_for((0.2, 0.7))), (0.2, 0.7), atol=0.04)

    def test_fusion_is_mean_of_raw_gazes_clipped_only_after_fusion(self):
        model, _ = calibrated()
        # Per-eye clipping would produce (.5, .5), concealing the overshoot.
        pair = pair_for((-0.4, 1.4), (1.0, 0.0))
        np.testing.assert_allclose(model.map(pair), (0.3, 0.7), atol=1e-12)
        np.testing.assert_allclose(model.map(pair_for((-0.3, 1.2))), (0.0, 1.0), atol=1e-12)

    def test_validation_does_not_let_bad_eyes_cancel(self):
        model, _ = calibrated()
        errors = model.validation_errors(pair_for((-0.3, 0.5), (1.3, 0.5)), (0.5, 0.5))
        self.assertLess(errors["fused"], 1e-12)
        self.assertAlmostEqual(errors["left"], 0.8)
        self.assertAlmostEqual(errors["right"], 0.8)

    def test_either_degenerate_eye_rejects_entire_fit(self):
        for failed_eye in (0, 1):
            for mode in ("constant", "tiny", "collinear"):
                with self.subTest(eye=failed_eye, mode=mode):
                    model = BinocularCalibration()
                    for i, target in enumerate(TARGETS):
                        pair = pair_for(target)
                        bad = {"constant": (0.5, 0.5),
                               "tiny": 0.5 + target * 0.003,
                               "collinear": (0.35 + i * 0.02, 0.35 + i * 0.03)}[mode]
                        pair[failed_eye * 2:failed_eye * 2 + 2] = bad
                        model.add(pair, target)
                    with self.assertRaisesRegex(ValueError, "Eye A" if failed_eye == 0 else "Eye B"):
                        model.fit()
                    self.assertFalse(model.ready)
                    with self.assertRaises(ValueError):
                        model.map(pair_for((0.5, 0.5)))

    def test_new_sample_reset_and_failed_refit_invalidate_both_eyes(self):
        model, _ = calibrated()
        model.add(pair_for((0.3, 0.3)), (0.3, 0.3))
        self.assertFalse(model.ready)
        model.fit()
        # Even if a caller corrupts saved samples, a failed refit stays unready.
        model.samples[0]["pupil"] = [0.2, 0.3]
        with self.assertRaises(ValueError):
            model.fit()
        self.assertFalse(model.ready)
        model.reset()
        self.assertEqual(model.samples, [])

    def test_rejects_incomplete_nonfinite_and_out_of_bounds_calibration(self):
        model, _ = calibrated()
        for bad in ((0.1, 0.2), (0.1, 0.2, 0.3), (0.1, 0.2, 0.3, float("nan")),
                    (0.1, float("inf"), 0.2, 0.3), (0.1, 0.2, 0.3, 1.1), None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    model.add(bad, (0.5, 0.5))
                self.assertTrue(model.ready)
                self.assertEqual(len(model.samples), 9)
        for bad in ((0.1, 0.2), (0.1, 0.2, 0.3, float("nan")), None):
            with self.assertRaises(ValueError):
                model.map(bad)
            with self.assertRaises(ValueError):
                model.validation_errors(bad, (0.5, 0.5))

    def test_rejects_too_few_or_poorly_covered_targets(self):
        for targets in (TARGETS[:4], TARGETS * 0.1 + 0.45):
            model = BinocularCalibration()
            for target in targets:
                model.add(pair_for(target), target)
            with self.assertRaises(ValueError):
                model.fit()
            self.assertFalse(model.ready)


if __name__ == "__main__":
    unittest.main()
