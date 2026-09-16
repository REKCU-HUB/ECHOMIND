"""Small, local affine calibration for a camera-fixed pupil tracking demo.

Coordinates on both sides are normalized to [0, 1].  Each sample represents
the median pupil position measured while the user looks at one screen target.
The residual is a calibration diagnostic, not a claim of gaze accuracy.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


def _point(value: Iterable[float], *, bounded: bool = True) -> tuple[float, float]:
    try:
        values = tuple(float(v) for v in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Coordinates must contain two finite numbers.") from exc
    if len(values) != 2 or not all(math.isfinite(v) for v in values):
        raise ValueError("Coordinates must contain two finite numbers.")
    if bounded and not all(0.0 <= v <= 1.0 for v in values):
        raise ValueError("Calibration coordinates must be between 0 and 1.")
    return values  # type: ignore[return-value]


class Calibration:
    """Fit an affine map without dependencies beyond NumPy.

    ``samples`` contains dictionaries with ``pupil`` and ``target`` pairs.
    Calling ``add`` invalidates any previous fit.  Call ``fit`` again once a
    complete set of samples has been collected.  Calibration should be reset
    after moving the camera, changing its crop, or changing image mirroring.
    """

    MIN_POINTS = 5
    MIN_PUPIL_SPAN = 0.01
    MIN_TARGET_SPAN = 0.35

    def __init__(self) -> None:
        self.samples: list[dict[str, list[float]]] = []
        self._coefficients: np.ndarray | None = None
        self._origin: np.ndarray | None = None
        self._scale: np.ndarray | None = None
        self._report: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return self._coefficients is not None

    def _clear_fit(self) -> None:
        self._coefficients = None
        self._origin = None
        self._scale = None
        self._report = None

    def reset(self) -> None:
        self.samples.clear()
        self._clear_fit()

    def add(self, pupil_xy: Iterable[float], target_xy: Iterable[float]) -> None:
        pupil = _point(pupil_xy)
        target = _point(target_xy)
        self.samples.append({"pupil": list(pupil), "target": list(target)})
        self._clear_fit()

    def fit(self) -> dict[str, Any]:
        self._clear_fit()
        if len(self.samples) < self.MIN_POINTS:
            raise ValueError("At least 5 distinct calibration points are needed. Complete calibration first.")

        try:
            pupil = np.array([_point(s["pupil"]) for s in self.samples], dtype=float)
            target = np.array([_point(s["target"]) for s in self.samples], dtype=float)
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid calibration data. Please calibrate again.") from exc

        for points, label in ((target, "Target"), (pupil, "Pupil")):
            if len(np.unique(np.round(points, 5), axis=0)) < self.MIN_POINTS:
                raise ValueError(f"Too many repeated {label.lower()} positions. Calibrate again, looking at each point.")

        pupil_span = np.ptp(pupil, axis=0)
        target_span = np.ptp(target, axis=0)
        if np.any(pupil_span < self.MIN_PUPIL_SPAN):
            raise ValueError("Pupil movement is too small. Keep the camera still and look at each target.")
        if np.any(target_span < self.MIN_TARGET_SPAN):
            raise ValueError("Targets do not cover enough of the display. Spread calibration points across the screen.")

        # Check the unscaled geometry too: standardizing a nearly flat sample
        # cloud must not turn it into apparently healthy two-dimensional data.
        for points, label in ((pupil, "Pupil"), (target, "Target")):
            singular = np.linalg.svd(points - points.mean(axis=0), compute_uv=False)
            if singular[0] <= 1e-12 or singular[1] / singular[0] < 0.025:
                raise ValueError(f"{label} positions are almost collinear. Repeat calibration in all four directions.")

        origin = pupil.mean(axis=0)
        scale = pupil.std(axis=0)
        design = np.column_stack(((pupil - origin) / scale, np.ones(len(pupil))))
        coefficients, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
        if rank != 3 or not np.all(np.isfinite(coefficients)):
            raise ValueError("Calibration data cannot form a 2D mapping. Please try again.")

        residual = design @ coefficients - target
        rmse = float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))
        # A loose rejection threshold catches mismatched samples and random
        # detections. Normal measurement noise is reported rather than hidden.
        if rmse > 0.25:
            raise ValueError("Pupil movement does not match the targets consistently. Adjust the camera and recalibrate.")

        # PRESS gives leave-one-out prediction error without repeatedly fitting.
        # High-leverage layouts can make this undefined; it is diagnostic only.
        q, _ = np.linalg.qr(design, mode="reduced")
        remaining = 1.0 - np.sum(q * q, axis=1)
        loo_rmse = None
        if np.all(remaining > 1e-7):
            loo = residual / remaining[:, None]
            loo_rmse = float(np.sqrt(np.mean(np.sum(loo * loo, axis=1))))

        self._origin = origin
        self._scale = scale
        self._coefficients = coefficients
        self._report = {
            "count": len(self.samples),
            "rmse": rmse,
            "loo_rmse": loo_rmse,
            "pupil_span": pupil_span.tolist(),
        }
        return dict(self._report)

    def map(self, pupil_xy: Iterable[float]) -> tuple[float, float]:
        if not self.ready:
            raise ValueError("Complete gaze calibration first.")
        pupil = np.asarray(_point(pupil_xy, bounded=False))
        normalized = (pupil - self._origin) / self._scale
        screen = np.array([normalized[0], normalized[1], 1.0]) @ self._coefficients
        screen = np.clip(screen, 0.0, 1.0)
        return float(screen[0]), float(screen[1])

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe samples. Never trust serialized fit coefficients."""
        return {
            "version": 1,
            "ready": self.ready,
            "samples": [
                {"pupil": list(s["pupil"]), "target": list(s["target"])}
                for s in self.samples
            ],
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        """Validate and re-fit saved samples; leave this object intact on error."""
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unsupported calibration data version.")
        samples = data.get("samples")
        if not isinstance(samples, list) or len(samples) > 1000:
            raise ValueError("Invalid calibration data format.")
        restored = Calibration()
        try:
            for sample in samples:
                restored.add(sample["pupil"], sample["target"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid calibration data format.") from exc
        if data.get("ready"):
            restored.fit()
        self.samples = restored.samples
        self._coefficients = restored._coefficients
        self._origin = restored._origin
        self._scale = restored._scale
        self._report = restored._report
