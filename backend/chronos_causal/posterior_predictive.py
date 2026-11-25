"""Residual checks for a fitted measurement-level model."""
from __future__ import annotations
import numpy as np

def residual_checks(observed, predicted, sigma):
    y = np.asarray(observed, float).reshape(-1)
    mu = np.asarray(predicted, float).reshape(-1)
    s = np.asarray(sigma, float).reshape(-1)
    if y.size == 0 or y.size != mu.size or y.size != s.size or np.any(~np.isfinite(y)) or np.any(~np.isfinite(mu)) or np.any(~np.isfinite(s)) or np.any(s <= 0):
        raise ValueError("observed, predicted and positive sigma arrays must be finite and equal length")
    z = (y - mu) / s
    return {
        "n": int(z.size),
        "mean_standardized_residual": float(np.mean(z)),
        "rms_standardized_residual": float(np.sqrt(np.mean(z ** 2))),
        "maximum_absolute_standardized_residual": float(np.max(np.abs(z))),
        "fraction_beyond_3_sigma": float(np.mean(np.abs(z) > 3)),
        "standardized_residuals": z.tolist(),
        "warning": "Descriptive residual diagnostics only; this is not a calibrated posterior predictive p-value.",
    }
