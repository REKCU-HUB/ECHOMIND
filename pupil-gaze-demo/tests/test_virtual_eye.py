"""Geometric and interface checks for the procedural demonstration eye."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from virtual_eye import render_eye, _layers


class VirtualEyeTests(unittest.TestCase):
    def test_output_format_and_direction(self):
        neutral = render_eye()
        self.assertEqual(neutral["frame"].shape, (500, 800, 3))
        self.assertEqual(neutral["frame"].dtype, np.uint8)
        left, right = render_eye((0, .5)), render_eye((1, .5))
        up, down = render_eye((.5, 0)), render_eye((.5, 1))
        self.assertLess(left["center"][0], neutral["center"][0])
        self.assertGreater(right["center"][0], neutral["center"][0])
        self.assertLess(up["center"][1], neutral["center"][1])
        self.assertGreater(down["center"][1], neutral["center"][1])

    def test_pupil_stays_inside_eye_at_extreme_points(self):
        for width, height in ((800, 500), (640, 480), (320, 200)):
            aperture = _layers(width, height)[1]
            for x in (0, .5, 1):
                for y in (0, .5, 1):
                    result = render_eye((x, y), size=(width, height))
                    cx, cy = result["center"]
                    rx, ry = np.array(result["axes"]) / 2
                    for theta in np.linspace(0, np.pi * 2, 64):
                        px, py = round(cx + rx * np.cos(theta)), round(cy + ry * np.sin(theta))
                        self.assertGreater(aperture[py, px], .99)
                    bx, by, bw, bh = result["bbox"]
                    self.assertGreaterEqual(min(bx, by), 0)
                    self.assertLessEqual(bx + bw, width)
                    self.assertLessEqual(by + bh, height)

    def test_inactive_neutral_and_frame_does_not_mutate_cache(self):
        neutral = render_eye()
        inactive = render_eye((1, 0), active=False)
        self.assertEqual(inactive["center"], neutral["center"])
        self.assertLess(inactive["frame"].mean(), neutral["frame"].mean())
        original = neutral["frame"].copy()
        neutral["frame"][:] = 0
        self.assertTrue(np.array_equal(render_eye()["frame"], original))

    def test_normalized_point_clamping(self):
        self.assertEqual(render_eye((-5, 20))["center"], render_eye((0, 1))["center"])
        self.assertEqual(render_eye((float("nan"), .2))["center"], render_eye()["center"])


if __name__ == "__main__":
    unittest.main()
