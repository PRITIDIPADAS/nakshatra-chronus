"""Gaussian weighted and generalized least-squares fits with explicit error models."""
from __future__ import annotations
import math
import numpy as np

_LOG_2PI = math.log(2.0 * math.pi)


def _validate_covariance(covariance, sigma, n):
    cov = np.asarray(covariance, dtype=float)
    s = np.asarray(sigma, dtype=float).reshape(-1)
    if cov.shape != (n, n) or np.any(~np.isfinite(cov)):
        raise ValueError("covariance must be finite, square and match the measurements")
    if not np.allclose(cov, cov.T, rtol=1e-10, atol=1e-12):
        raise ValueError("covariance matrix must be symmetric")
    diagonal = np.diag(cov)
    if not np.allclose(diagonal, s ** 2, rtol=1e-5, atol=1e-10):
        raise ValueError("covariance diagonal must agree with the supplied sigma squared")
    try:
        lower = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as exc:
        raise ValueError("covariance matrix must be positive definite") from exc
    logdet = float(2.0 * np.sum(np.log(np.diag(lower))))
    return cov, lower, logdet


def fit_gaussian_linear(values, sigma, design, covariance=None):
    y = np.asarray(values, dtype=float).reshape(-1)
    s = np.asarray(sigma, dtype=float).reshape(-1)
    x = np.asarray(design, dtype=float)
    if x.ndim != 2 or x.shape[0] != y.size or s.size != y.size:
        raise ValueError("regression arrays have incompatible shapes")
    if y.size <= x.shape[1] or np.any(~np.isfinite(y)) or np.any(~np.isfinite(s)) or np.any(s <= 0) or np.any(~np.isfinite(x)):
        raise ValueError("regression requires finite data, positive sigma and more rows than parameters")

    if covariance is None:
        root_w = 1.0 / s
        wx, wy = x * root_w[:, None], y * root_w
        logdet = float(np.sum(2.0 * np.log(s)))
        covariance_label = "independent Gaussian errors"
    else:
        _, lower, logdet = _validate_covariance(covariance, s, y.size)
        wx = np.linalg.solve(lower, x)
        wy = np.linalg.solve(lower, y)
        covariance_label = "supplied full covariance"

    beta, _, rank, _ = np.linalg.lstsq(wx, wy, rcond=None)
    if rank < x.shape[1]:
        raise ValueError("design matrix is rank deficient; the observations do not separate these effects")
    prediction = x @ beta
    residual = y - prediction
    if covariance is None:
        whitened_residual = residual / s
    else:
        whitened_residual = np.linalg.solve(lower, residual)
    standardized = residual / s
    chi2 = float(whitened_residual @ whitened_residual)
    loglike = float(-0.5 * (chi2 + logdet + y.size * _LOG_2PI))
    return {
        "coefficients": beta.tolist(),
        "prediction": prediction.tolist(),
        "residual": residual.tolist(),
        "standardized_residual": standardized.tolist(),
        "whitened_residual": whitened_residual.tolist(),
        "chi2": chi2,
        "dof": int(y.size - x.shape[1]),
        "log_likelihood": loglike,
        "n": int(y.size),
        "k": int(x.shape[1]),
        "noise_model": covariance_label,
        "covariance_supplied": covariance is not None,
    }


def bic(log_likelihood: float, n: int, parameters: int) -> float:
    if n <= 0 or parameters < 0:
        raise ValueError("invalid BIC dimensions")
    return float(parameters * math.log(n) - 2.0 * log_likelihood)
