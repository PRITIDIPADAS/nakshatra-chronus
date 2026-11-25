"""Gaussian weighted regression with stated, supplied measurement errors."""
from __future__ import annotations
import math
import numpy as np

_LOG_2PI = math.log(2.0 * math.pi)

def fit_gaussian_linear(values, sigma, design):
    y = np.asarray(values, dtype=float).reshape(-1)
    s = np.asarray(sigma, dtype=float).reshape(-1)
    x = np.asarray(design, dtype=float)
    if x.ndim != 2 or x.shape[0] != y.size or s.size != y.size:
        raise ValueError("regression arrays have incompatible shapes")
    if y.size <= x.shape[1] or np.any(~np.isfinite(y)) or np.any(~np.isfinite(s)) or np.any(s <= 0) or np.any(~np.isfinite(x)):
        raise ValueError("regression requires finite data, positive sigma and more rows than parameters")
    root_w = 1.0 / s
    wx, wy = x * root_w[:, None], y * root_w
    beta, _, rank, _ = np.linalg.lstsq(wx, wy, rcond=None)
    if rank < x.shape[1]:
        raise ValueError("design matrix is rank deficient; the observations do not separate these effects")
    prediction = x @ beta
    residual = y - prediction
    z = residual / s
    chi2 = float(z @ z)
    loglike = float(-0.5 * (chi2 + np.sum(2.0 * np.log(s)) + y.size * _LOG_2PI))
    return {
        "coefficients": beta.tolist(),
        "prediction": prediction.tolist(),
        "residual": residual.tolist(),
        "standardized_residual": z.tolist(),
        "chi2": chi2,
        "dof": int(y.size - x.shape[1]),
        "log_likelihood": loglike,
        "n": int(y.size),
        "k": int(x.shape[1]),
    }

def bic(log_likelihood: float, n: int, parameters: int) -> float:
    if n <= 0 or parameters < 0:
        raise ValueError("invalid BIC dimensions")
    return float(parameters * math.log(n) - 2.0 * log_likelihood)
