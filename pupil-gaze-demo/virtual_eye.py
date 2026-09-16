"""Local, procedural eye illustration for the mouse-linked demonstration.

This module does not access a camera, read an image, or infer a person's gaze.
The returned geometry describes the drawn pupil, not a detector measurement.
"""

from functools import lru_cache
import math

import cv2
import numpy as np


@lru_cache(maxsize=4)
def _layers(width, height):
    """Cache the skin, eye aperture and iris texture at each display size."""
    yy, xx = np.mgrid[:height, :width].astype(np.float32)
    u, v = xx / width, yy / height
    rng = np.random.default_rng(142)

    # Low-contrast grain and broad lighting gradients resemble an infrared
    # close-up, while remaining a deliberately synthetic illustration.
    noise = rng.normal(0, 1.25, (height, width)).astype(np.float32)
    skin = 147 + 25 * np.exp(-((u - .52) ** 2 / .24 + (v - .22) ** 2 / .22))
    skin -= 47 * (u - .50) ** 2 + 18 * (v - .48) ** 2
    skin += noise

    eye_x = (u - .5) / .423
    opening = np.maximum(0, 1 - eye_x ** 2) ** .70
    middle = .525 - .025 * eye_x
    top = middle - .235 * opening
    bottom = middle + .225 * opening
    distance_top = v - top
    distance_bottom = bottom - v
    softness = max(1.0 / height, .002)
    aperture = np.clip(np.minimum(distance_top, distance_bottom) / softness, 0, 1)
    aperture *= (np.abs(eye_x) < 1)

    # The orbital fold, upper lid and lower-lid lip surround an almond opening.
    skin -= 51 * np.exp(-((v - (top - .044)) / .035) ** 2) * opening
    skin += 17 * np.exp(-((v - (bottom + .025)) / .020) ** 2) * opening
    skin -= 18 * np.exp(-((v - (bottom + .065)) / .030) ** 2) * opening
    sclera = 204 - 62 * np.abs(eye_x) ** 1.6 - 34 * ((v - .53) / .28) ** 2
    sclera += noise * .4
    base = skin * (1 - aperture) + sclera * aperture

    # Reapply this gentle lid shadow over both the sclera and moving iris.
    shade = 1 - .33 * np.exp(-np.maximum(distance_top, 0) / .044) * aperture
    shade -= .055 * np.exp(-np.maximum(distance_bottom, 0) / .018) * aperture

    radius = max(8, int(min(width * .137, height * .242)))
    pupil_rx = max(3, int(min(width * .050, height * .086)))
    pupil_ry = max(3, int(min(width * .054, height * .093)))
    side = radius * 2 + 5
    center = side // 2
    iy, ix = np.mgrid[:side, :side].astype(np.float32)
    ix, iy = ix - center, iy - center
    rho = np.sqrt((ix / (radius * .97)) ** 2 + (iy / radius) ** 2)
    angle = np.arctan2(iy, ix)

    # Deterministic radial fibers, a scalloped collarette, outer limbus and
    # uneven radial intensity prevent the iris looking like a flat disk.
    fibers = (np.sin(angle * 83 + rho * 11) * 6
              + np.sin(angle * 139 - rho * 24) * 4
              + np.sin(angle * 211 + np.sin(angle * 17) * 2) * 3)
    iris = 83 + 28 * np.exp(-((rho - .65) / .23) ** 2)
    iris += fibers * np.clip((rho - .34) * 2, 0, 1)
    iris -= 29 * np.exp(-((rho - .965) / .035) ** 2)
    iris -= 10 * np.exp(-((rho - (.47 + .025 * np.sin(angle * 29))) / .026) ** 2)
    iris += rng.normal(0, 1.25, (side, side))
    iris -= iy / max(radius, 1) * 3

    pupil_distance = np.sqrt((ix / pupil_rx) ** 2 + (iy / pupil_ry) ** 2)
    pupil_alpha = np.clip((1 - pupil_distance) * max(pupil_rx, pupil_ry), 0, 1)
    iris = iris * (1 - pupil_alpha) + (6 + 3 * np.clip(pupil_distance, 0, 1)) * pupil_alpha

    # Two simulated IR illuminators, with a diffuse halo and crisp cores.
    for gx, gy, gr in ((-.24 * pupil_rx, -.18 * pupil_ry, .17 * pupil_rx),
                      (.35 * pupil_rx, -.26 * pupil_ry, .13 * pupil_rx)):
        d2 = (ix - gx) ** 2 + (iy - gy) ** 2
        halo = np.exp(-d2 / max(2 * (gr * 1.65) ** 2, 1)) * .30
        core = np.clip((gr - np.sqrt(d2)) * 1.5, 0, 1)
        shine = np.maximum(core, halo)
        iris = iris * (1 - shine) + 251 * shine

    iris_alpha = np.clip((1 - rho) * radius, 0, 1).astype(np.float32)
    return (np.clip(base, 0, 255).astype(np.float32), aperture.astype(np.float32),
            shade.astype(np.float32), np.clip(iris, 0, 255).astype(np.float32),
            iris_alpha, center, pupil_rx, pupil_ry)


def render_eye(point=(.5, .5), *, active=True, size=(800, 500), now=None):
    """Return a BGR frame and exact pupil geometry for a normalized point.

    ``point`` follows display coordinates: right increases x, down increases y.
    Values outside 0..1 are clamped. Inactive input draws a dim neutral eye.
    ``now`` is accepted for caller compatibility; drawing has no time state.
    Size is (width, height), axes are full diameters, bbox is (x, y, w, h).
    """
    del now
    width, height = (int(size[0]), int(size[1]))
    if width < 160 or height < 100:
        raise ValueError("Virtual eye size must be at least 160 x 100 pixels")
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        x, y = .5, .5
    if not active or not math.isfinite(x) or not math.isfinite(y):
        x, y = .5, .5
    x, y = min(1, max(0, x)), min(1, max(0, y))
    base, aperture, shade, iris, iris_alpha, patch_center, rx, ry = _layers(width, height)
    cx = int(round(width * (.5 + (x - .5) * .40)))
    cy = int(round(height * (.525 + (y - .5) * .15)))

    gray = base.copy()
    patch_x, patch_y = cx - patch_center, cy - patch_center
    x0, y0 = max(0, patch_x), max(0, patch_y)
    x1, y1 = min(width, patch_x + iris.shape[1]), min(height, patch_y + iris.shape[0])
    ix0, iy0 = x0 - patch_x, y0 - patch_y
    ix1, iy1 = ix0 + x1 - x0, iy0 + y1 - y0
    alpha = iris_alpha[iy0:iy1, ix0:ix1] * aperture[y0:y1, x0:x1]
    roi = gray[y0:y1, x0:x1]
    roi[:] = roi * (1 - alpha) + iris[iy0:iy1, ix0:ix1] * alpha
    gray *= shade
    if not active:
        gray *= .76
    frame = cv2.cvtColor(np.clip(gray, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    return {
        "frame": frame,
        "center": (cx, cy),
        "axes": (rx * 2, ry * 2),
        "angle": 0.0,
        "bbox": (cx - rx, cy - ry, rx * 2, ry * 2),
    }
