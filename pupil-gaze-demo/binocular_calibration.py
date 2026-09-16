"""Calibrate two real pupils from one camera, then average their gaze estimates.

Features are ``(left_x, left_y, right_x, right_y)`` in normalized full-frame
coordinates. Each eye has its own affine calibration. Neither calibration
residual nor averaging is a claim of improved real-world gaze accuracy.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from calibration import Calibration, _point


def _features(value: Iterable[float], *, bounded: bool = True) -> tuple[float, ...]:
    try:
        values = tuple(float(v) for v in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Both eyes need two finite pupil coordinates.") from exc
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        raise ValueError("Both eyes need two finite pupil coordinates.")
    if bounded and not all(0.0 <= v <= 1.0 for v in values):
        raise ValueError("Calibration coordinates must be between 0 and 1.")
    return values


def _raw_map(model: Calibration, point: Iterable[float]) -> np.ndarray:
    """Use the shared affine fit without Calibration.map's output clipping.

    Clip only the final fused cursor: clipping each eye first would conceal
    disagreement outside the screen and bias the mean toward its center.
    """
    pupil = np.asarray(_point(point, bounded=False))
    normalized = (pupil - model._origin) / model._scale
    screen = np.array([normalized[0], normalized[1], 1.0]) @ model._coefficients
    if not np.all(np.isfinite(screen)):
        raise ValueError("Pupil coordinates cannot form a finite gaze estimate.")
    return screen


class BinocularCalibration:
    """Two independent, validated 2D fits with equal-weight gaze fusion.

    Both eyes must be present for add/map/validation. If either fit fails,
    the entire calibration stays unready; there is no silent single-eye
    fallback. The caller should reset after changing either eye region,
    image mirroring, camera position, or the video source.
    """

    MIN_POINTS = Calibration.MIN_POINTS

    def __init__(self) -> None:
        self.samples: list[dict[str, list[float]]] = []
        self._left: Calibration | None = None
        self._right: Calibration | None = None
        self._report: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return bool(self._left and self._right and self._left.ready and self._right.ready)

    def _clear_fit(self) -> None:
        self._left = None
        self._right = None
        self._report = None

    def reset(self) -> None:
        self.samples.clear()
        self._clear_fit()

    def add(self, pupil_xy: Iterable[float], target_xy: Iterable[float]) -> None:
        # Validate the complete pair before changing samples or a valid fit.
        pupil = _features(pupil_xy)
        target = _point(target_xy)
        self.samples.append({"pupil": list(pupil), "target": list(target)})
        self._clear_fit()

    def fit(self) -> dict[str, Any]:
        self._clear_fit()
        left, right = Calibration(), Calibration()
        try:
            for sample in self.samples:
                pupil = _features(sample["pupil"])
                target = _point(sample["target"])
                left.add(pupil[:2], target)
                right.add(pupil[2:], target)
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid binocular calibration data. Please calibrate again.") from exc

        reports = {}
        for label, model in (("left", left), ("right", right)):
            try:
                reports[label] = model.fit()
            except ValueError as exc:
                raise ValueError(f"Eye {'A' if label == 'left' else 'B'}: {exc}") from exc

        predictions = np.array([
            (_raw_map(left, sample["pupil"][:2]) + _raw_map(right, sample["pupil"][2:])) / 2
            for sample in self.samples
        ])
        targets = np.array([sample["target"] for sample in self.samples])
        fused_rmse = float(np.sqrt(np.mean(np.sum((predictions - targets) ** 2, axis=1))))
        loo_errors = [reports[eye]["loo_rmse"] for eye in ("left", "right")]
        self._report = {
            "count": len(self.samples),
            # A good fused score must never hide a poor individual eye fit.
            "rmse": max(reports["left"]["rmse"], reports["right"]["rmse"], fused_rmse),
            "loo_rmse": max(loo_errors) if all(value is not None for value in loo_errors) else None,
            "pupil_span": reports["left"]["pupil_span"] + reports["right"]["pupil_span"],
            "left": reports["left"],
            "right": reports["right"],
            "fused_rmse": fused_rmse,
        }
        self._left, self._right = left, right
        return dict(self._report)

    def _map_eyes(self, pupil_xy: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
        if not self.ready:
            raise ValueError("Complete binocular gaze calibration first.")
        pupil = _features(pupil_xy, bounded=False)
        return _raw_map(self._left, pupil[:2]), _raw_map(self._right, pupil[2:])

    def map(self, pupil_xy: Iterable[float]) -> tuple[float, float]:
        left, right = self._map_eyes(pupil_xy)
        fused = np.clip((left + right) / 2, 0.0, 1.0)
        return float(fused[0]), float(fused[1])

    def validation_errors(self, pupil_xy: Iterable[float], target_xy: Iterable[float]) -> dict[str, float]:
        """Return unclipped per-eye and fused distances to a held-out target.

        The caller must check both individual errors as well as fused error:
        two incorrect eye estimates can cancel when averaged.
        """
        target = np.asarray(_point(target_xy))
        left, right = self._map_eyes(pupil_xy)
        return {
            "left": float(np.linalg.norm(left - target)),
            "right": float(np.linalg.norm(right - target)),
            "fused": float(np.linalg.norm((left + right) / 2 - target)),
        }
