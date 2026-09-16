"""Two independent pupil tracks from separate regions of one camera frame.

Both pupils must be visible in the same frame before a combined sample is
returned. This module does not infer a second eye or treat detection quality
as measured gaze accuracy. Per-eye detections remain available for preview
when only one eye is visible.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from detector import Detection, PupilDetector


def validate_rois(left_roi, right_roi):
    """Validate two normalized, ordered, nonoverlapping image rectangles.

    Rectangle order is x0, y0, x1, y1. Eye labels follow the user's selection;
    they do not assume an anatomical left/right direction or camera mirror.
    A shared edge is permitted, but a shared image area is not.
    """
    validated = []
    for roi in (left_roi, right_roi):
        try:
            values = np.asarray(roi, dtype=float)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Select a valid rectangle for each eye.") from exc
        if (values.shape != (4,) or not np.isfinite(values).all()
                or np.any(values < 0) or np.any(values > 1)):
            raise ValueError("Eye regions must use four finite coordinates between 0 and 1.")
        x0, y0, x1, y1 = (float(v) for v in values)
        if x0 >= x1 or y0 >= y1:
            raise ValueError("Each eye region must have a positive width and height.")
        validated.append((x0, y0, x1, y1))
    left, right = validated
    if (max(left[0], right[0]) < min(left[2], right[2])
            and max(left[1], right[1]) < min(left[3], right[3])):
        raise ValueError("Eye regions overlap. Select a separate region around each eye.")
    return left, right


@dataclass(frozen=True)
class BinocularDetection:
    left: Detection
    right: Detection
    feature: tuple[float, float, float, float]
    quality: float


class BinocularTracker:
    """Require two fresh pupil detections; never reuse the missing eye.

    ``feature`` contains full-frame normalized left x/y then right x/y.
    ``left`` and ``right`` contain this frame's independently detected pupils
    for overlays, even when ``detect`` returns None. ``reset`` keeps the ROIs;
    ``clear_rois`` removes them. Invalid ROI updates leave the previous valid
    configuration intact.
    """

    def __init__(self, min_quality=0.5, max_width=640):
        self.left_detector = PupilDetector(min_quality, max_width)
        self.right_detector = PupilDetector(min_quality, max_width)
        self.left_roi = None
        self.right_roi = None
        self.reset()

    @property
    def ready(self):
        return self.left_roi is not None and self.right_roi is not None

    @property
    def rois(self):
        return (self.left_roi, self.right_roi)

    def reset(self):
        self.left_detector.reset()
        self.right_detector.reset()
        self.left = None
        self.right = None
        self._frame_shape = None
        self.status = "waiting"
        self.reason = ("Waiting for both pupils" if self.ready else
                       "Select a separate region around each eye.")

    def clear_rois(self):
        self.left_roi = None
        self.right_roi = None
        self.reset()

    def set_rois(self, left_roi, right_roi):
        left, right = validate_rois(left_roi, right_roi)
        self.left_roi, self.right_roi = left, right
        self.reset()

    def detect(self, frame, threshold=None):
        self.left = None
        self.right = None
        if not self.ready:
            self.status = "waiting"
            self.reason = "Select a separate region around each eye."
            return None
        if (not isinstance(frame, np.ndarray) or frame.size == 0
                or frame.ndim not in (2, 3) or frame.dtype != np.uint8
                or (frame.ndim == 3 and frame.shape[2] not in (3, 4))):
            self.status = "lost"
            self.reason = "No valid camera video received."
            return None
        h, w = frame.shape[:2]
        if self._frame_shape != (h, w):
            self.left_detector.reset()
            self.right_detector.reset()
            self._frame_shape = (h, w)
        for roi in self.rois:
            x0, y0, x1, y1 = roi
            if int(x1*w)-int(x0*w) < 24 or int(y1*h)-int(y0*h) < 24:
                self.status = "lost"
                self.reason = "Each eye region must be at least 24 x 24 camera pixels. Select larger regions."
                return None
        self.left = self.left_detector.detect(frame, roi=self.left_roi, threshold=threshold)
        self.right = self.right_detector.detect(frame, roi=self.right_roi, threshold=threshold)
        if self.left is None or self.right is None:
            self.status = "lost"
            if self.left is None and self.right is None:
                self.reason = "Both pupils are missing. Keep both eyes visible and adjust the eye regions."
            elif self.left is None:
                self.reason = "First eye is not locked. Binocular pointer paused."
            else:
                self.reason = "Second eye is not locked. Binocular pointer paused."
            return None
        self.status = "tracking"
        self.reason = "Both pupils detected in the same camera frame."
        lx, ly = self.left.center
        rx, ry = self.right.center
        return BinocularDetection(
            left=self.left, right=self.right,
            feature=(lx/w, ly/h, rx/w, ry/h),
            quality=min(self.left.quality, self.right.quality),
        )
