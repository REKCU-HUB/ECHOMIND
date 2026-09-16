"""Local, model-free dark-pupil detection for a close-up eye camera.

OpenCV thresholding/contours/ellipse fitting are used without pretrained weights.
``quality`` is a heuristic image/shape quality score, NOT measured accuracy or a
probability that an eye is looking at a particular screen location. Coordinates
refer to the original input frame, including when a normalized ROI is supplied.
"""

from dataclasses import dataclass
import math
from typing import Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class Detection:
    center: tuple[float, float]
    axes: tuple[float, float]
    angle: float
    bbox: tuple[int, int, int, int]
    quality: float
    threshold: int


class PupilDetector:
    """Find a compact dark ellipse with a brighter surrounding iris.

    Automatic mode considers several intensity thresholds, rejecting boundary
    shadows, thin eyelash/closed-lid shapes, poor ellipse fits and low-contrast
    regions. A previous location is only a small ranking preference; it cannot
    create a detection or prevent reacquisition after a large eye movement.
    """

    def __init__(self, min_quality: float = 0.5, max_width: int = 640):
        self.min_quality = float(min_quality)
        self.max_width = max(64, int(max_width))
        self.status = "waiting"
        self.reason = "Waiting for camera video"
        self._previous = None
        self._misses = 0

    def reset(self):
        self._previous = None
        self._misses = 0
        self.status = "waiting"
        self.reason = "Waiting for a clearly visible pupil"

    def _lost(self, reason):
        self._misses += 1
        if self._misses > 5:
            self._previous = None
        self.status = "lost"
        self.reason = reason
        return None

    def detect(self, frame_bgr, roi=None, threshold=None) -> Optional[Detection]:
        if frame_bgr is None or not isinstance(frame_bgr, np.ndarray) or frame_bgr.size == 0:
            return self._lost("No camera video received")
        if frame_bgr.ndim not in (2, 3) or frame_bgr.dtype != np.uint8:
            return self._lost("Unsupported camera video format")
        full_h, full_w = frame_bgr.shape[:2]
        if roi is None:
            x0, y0, x1, y1 = 0, 0, full_w, full_h
        else:
            try:
                bounds = np.asarray(roi, dtype=float)
                if bounds.shape != (4,) or not np.isfinite(bounds).all():
                    raise ValueError("Invalid ROI")
                bounds = np.clip(bounds, 0.0, 1.0)
                x0, y0 = int(bounds[0] * full_w), int(bounds[1] * full_h)
                x1, y1 = int(bounds[2] * full_w), int(bounds[3] * full_h)
            except (TypeError, ValueError):
                return self._lost("Select a valid eye region again")
        if x1 - x0 < 24 or y1 - y0 < 24:
            return self._lost("Eye region too small; select a larger region")
        image = frame_bgr[y0:y1, x0:x1]
        if image.ndim == 3:
            if image.shape[2] not in (3, 4):
                return self._lost("Unsupported camera video format")
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY)
        scale = min(1.0, self.max_width / image.shape[1])
        if scale < 1.0:
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(image, (5, 5), 0)
        h, w = gray.shape
        lo, hi = np.percentile(gray, (1, 95))
        if float(hi - lo) < 12:
            return self._lost("Image contrast is too low, or the eye is outside the camera view")

        if threshold is None:
            otsu = float(cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[0])
            # Low-percentile offsets still find a pupil when a large border
            # shadow makes the darkest several percentiles exactly zero.
            quantiles = np.percentile(gray, (1, 3, 6, 10, 16, 22))
            levels = sorted({int(np.clip(t, 3, 220)) for t in
                             [*list(quantiles + 8), *list(quantiles + 20),
                              otsu * 0.55, otsu * 0.75, otsu]})
            # Nearby thresholds produce the same contours and waste CPU time.
            levels = [t for i, t in enumerate(levels) if i == 0 or t - levels[i - 1] >= 4]
        else:
            try:
                if not math.isfinite(float(threshold)):
                    raise ValueError("Invalid threshold")
                levels = [int(np.clip(threshold, 0, 255))]
            except (TypeError, ValueError):
                return self._lost("Invalid threshold setting")

        best = None
        best_rank = -1.0
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        short_side = min(h, w)
        min_diameter = max(7.0, short_side * 0.025)
        max_diameter = short_side * 0.72
        min_area = math.pi * (min_diameter / 2.0) ** 2 * 0.55
        for level in levels:
            mask = cv2.threshold(gray, level, 255, cv2.THRESH_BINARY_INV)[1]
            # Opening removes narrow lashes/bridges; RETR_EXTERNAL ignores
            # bright glint holes without moving the pupil's external edge.
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]
            for contour in contours:
                area = cv2.contourArea(contour)
                if len(contour) < 12 or area < min_area or area > w * h * 0.40:
                    continue
                bx, by, bw, bh = cv2.boundingRect(contour)
                # Border-connected shadows are common on close-up IR cameras.
                if bx < 2 or by < 2 or bx + bw >= w - 1 or by + bh >= h - 1:
                    continue
                if min(bw, bh) / max(bw, bh) < 0.23:
                    continue
                try:
                    (cx, cy), (ax, ay), angle = cv2.fitEllipse(contour)
                except cv2.error:
                    continue
                if not all(math.isfinite(v) for v in (cx, cy, ax, ay, angle)):
                    continue
                minor, major = min(ax, ay), max(ax, ay)
                if minor < min_diameter or major > max_diameter or minor / major < 0.28:
                    continue
                if not (bx <= cx <= bx + bw and by <= cy <= by + bh):
                    continue
                ellipse_area = math.pi * ax * ay / 4.0
                fill = area / max(ellipse_area, 1.0)
                if not 0.68 <= fill <= 1.20:
                    continue
                hull_area = cv2.contourArea(cv2.convexHull(contour))
                solidity = area / max(hull_area, 1.0)
                if solidity < 0.77:
                    continue
                radians = math.radians(angle)
                co, si = math.cos(radians), math.sin(radians)
                points = contour[:, 0, :].astype(np.float64) - (cx, cy)
                u = (co * points[:, 0] + si * points[:, 1]) / (ax * 0.5)
                v = (-si * points[:, 0] + co * points[:, 1]) / (ay * 0.5)
                residual = np.abs(np.sqrt(u * u + v * v) - 1.0)
                fit_error = float(np.mean(np.minimum(residual, 1.0)))
                if fit_error > 0.17 or float(np.percentile(residual, 90)) > 0.32:
                    continue

                # Evaluate inside and outside the fitted ellipse in a small
                # local patch. Medians tolerate a few saturated IR reflections.
                radius = int(math.ceil(major * 0.82))
                lx, ly = max(0, int(cx) - radius), max(0, int(cy) - radius)
                rx, ry = min(w, int(cx) + radius + 1), min(h, int(cy) + radius + 1)
                yy, xx = np.ogrid[ly:ry, lx:rx]
                dx, dy = xx - cx, yy - cy
                eu = (co * dx + si * dy) / (ax * 0.5)
                ev = (-si * dx + co * dy) / (ay * 0.5)
                er = eu * eu + ev * ev
                patch = gray[ly:ry, lx:rx]
                # Use most of the ellipse interior, rather than its very
                # center: an iris candidate can contain a smaller black pupil
                # at its center and otherwise masquerade as a strong dark disk.
                inside = patch[er < 0.84 ** 2]
                outside = patch[(er > 1.10 ** 2) & (er < 1.45 ** 2)]
                if inside.size < 12 or outside.size < 24:
                    continue
                inner_low, inner_value = np.percentile(inside, (20, 65))
                inner_low, inner_value = float(inner_low), float(inner_value)
                outer_value = float(np.median(outside))
                contrast = outer_value - inner_value
                if contrast < 12:
                    continue
                # A broad dark-pupil/bright-iris mixture inside one ellipse
                # indicates a nested iris boundary, not the pupil boundary.
                # The 65th percentile deliberately tolerates small IR glints.
                if inner_value - inner_low > max(24.0, contrast * 0.65):
                    continue
                # Require a meaningful fraction of the ring to be brighter;
                # an isolated dark lash inside a dark iris is not enough.
                bright_ring = float(np.mean(outside > inner_value + 12))
                if bright_ring < 0.48:
                    continue
                fit_score = float(np.clip(1.0 - fit_error / 0.17, 0.0, 1.0))
                contrast_score = float(np.clip((contrast - 8.0) / 72.0, 0.0, 1.0))
                fill_score = float(np.clip(1.0 - abs(1.0 - fill) / 0.32, 0.0, 1.0))
                dark_score = float(np.clip(1.0 - (inner_value - lo) / max(hi - lo, 1.0), 0.0, 1.0))
                quality = (0.33 * contrast_score + 0.29 * fit_score + 0.17 * fill_score
                           + 0.09 * solidity + 0.07 * bright_ring + 0.05 * dark_score)
                quality = float(np.clip(quality, 0.0, 1.0))
                if quality < self.min_quality:
                    continue
                center = (cx / scale + x0, cy / scale + y0)
                rank = quality
                if self._previous is not None:
                    distance = math.dist(center, self._previous)
                    closeness = math.exp(-distance / max(major / scale * 1.5, 1.0))
                    rank *= 0.94 + 0.06 * closeness
                if rank > best_rank:
                    # A tied score favors the tighter threshold rather than a
                    # later dark iris region that merely includes the pupil.
                    best_rank = rank
                    best = Detection(
                        center=center, axes=(ax / scale, ay / scale), angle=float(angle),
                        bbox=(x0 + int(bx / scale), y0 + int(by / scale),
                              int(math.ceil(bw / scale)), int(math.ceil(bh / scale))),
                        quality=quality, threshold=level,
                    )
        if best is None:
            return self._lost("Pupil not locked: open your eye, adjust the camera, or crop closer to the eye")
        self._previous = best.center
        self._misses = 0
        self.status = "tracking"
        self.reason = "Dark pupil contour detected"
        return best
