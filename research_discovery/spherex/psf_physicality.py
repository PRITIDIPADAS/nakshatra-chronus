"""Conservative physicality checks for interpolated empirical PSF stamps."""
from __future__ import annotations

from typing import Any

import numpy as np


def enforce_nonnegative_interpolation_psf(
    psf: np.ndarray,
    *,
    max_negative_peak_fraction: float = 1.0e-3,
    max_negative_total_flux_fraction: float = 1.0e-3,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Clip only very small negative interpolation ringing and renormalize.

    Empirical oversampled PSF models can produce a tiny negative interpolation
    lobe when rendered onto native pixels. A physical intensity PSF must be
    nonnegative, but clipping is allowed only when BOTH the largest negative
    sample is <= 0.1% of the positive peak AND the integrated negative flux is
    <= 0.1% of the integrated positive flux. Larger violations fail closed.

    Returns a float64, unit-sum PSF and an explicit record of all corrections.
    The source array is never modified.
    """
    values = np.asarray(psf, dtype=np.float64)
    if values.ndim != 2 or any(n % 2 == 0 for n in values.shape):
        raise ValueError("PSF must be a two-dimensional odd-sized stamp")
    if not np.isfinite(values).all():
        raise ValueError("PSF contains non-finite values")

    positive = np.clip(values, 0.0, None)
    positive_sum = float(positive.sum())
    peak = float(positive.max()) if positive.size else 0.0
    if not np.isfinite(positive_sum) or positive_sum <= 0 or peak <= 0:
        raise ValueError("PSF must contain finite positive intensity")

    negative_mask = values < 0.0
    negative_count = int(negative_mask.sum())
    negative_abs = float(-values[negative_mask].sum()) if negative_count else 0.0
    max_negative = float(-values[negative_mask].min()) if negative_count else 0.0
    negative_peak_fraction = max_negative / peak
    negative_total_flux_fraction = negative_abs / positive_sum

    if negative_peak_fraction > max_negative_peak_fraction:
        raise ValueError(
            "PSF negative interpolation lobe exceeds the peak-relative limit: "
            f"{negative_peak_fraction:.8g} > {max_negative_peak_fraction:.8g}"
        )
    if negative_total_flux_fraction > max_negative_total_flux_fraction:
        raise ValueError(
            "PSF integrated negative interpolation flux exceeds the limit: "
            f"{negative_total_flux_fraction:.8g} > {max_negative_total_flux_fraction:.8g}"
        )

    corrected = positive / positive_sum
    record = {
        "status": "pass",
        "method": "clip_bounded_negative_interpolation_overshoot_then_renormalize",
        "raw_minimum": float(values.min()),
        "raw_maximum": float(values.max()),
        "raw_sum": float(values.sum()),
        "negative_pixel_count": negative_count,
        "negative_absolute_flux": negative_abs,
        "positive_flux_before_correction": positive_sum,
        "maximum_negative_to_positive_peak_fraction": negative_peak_fraction,
        "negative_to_positive_integrated_flux_fraction": negative_total_flux_fraction,
        "maximum_negative_peak_fraction_allowed": float(max_negative_peak_fraction),
        "maximum_negative_integrated_flux_fraction_allowed": float(max_negative_total_flux_fraction),
        "clipped_pixel_count": negative_count,
        "correction_applied": bool(negative_count),
        "corrected_sum": float(corrected.sum()),
        "interpretation": (
            "Only sub-threshold negative interpolation ringing was clipped; "
            "a larger negative lobe would have been rejected."
        ),
    }
    return corrected, record
