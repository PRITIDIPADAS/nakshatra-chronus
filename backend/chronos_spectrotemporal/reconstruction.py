"""Calibrated local reconstruction of F(lambda, t) from irregular samples.

Missing samples are never filled. Reconstruction uses native calibrated rows,
preserves their source indices, and supports a shared calibration-group
systematic covariance in addition to measurement covariance.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import hashlib
import math

import numpy as np

from chronos_causal.wavelength_gate import validate_science_wavelength


def _validate_samples(samples: Sequence[Mapping[str, Any]], calibration_group: str | None):
    if not samples:
        raise ValueError("at least one spectral measurement is required")
    groups = {str(row.get("calibration_group", "")) for row in samples}
    if "" in groups:
        raise ValueError("every sample needs an explicit calibration_group")
    if calibration_group is not None:
        if calibration_group not in groups:
            raise ValueError(f"calibration_group {calibration_group!r} is not present")
        selected = [(index, row) for index, row in enumerate(samples)
                    if str(row["calibration_group"]) == calibration_group]
    elif len(groups) == 1:
        selected = list(enumerate(samples))
        calibration_group = next(iter(groups))
    else:
        raise ValueError("samples contain incompatible calibration groups; select one group per reconstruction")

    rows: list[dict[str, Any]] = []
    input_indices: list[int] = []
    for index, raw in selected:
        row = dict(raw)
        if row.get("valid", True) is False:
            continue
        for key in ("mjd", "wavelength_um", "flux", "sigma"):
            try:
                row[key] = float(row[key])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"sample {index} requires numeric {key}") from None
            if not math.isfinite(row[key]):
                raise ValueError(f"sample {index}: {key} must be finite")
        if row["wavelength_um"] <= 0 or row["sigma"] <= 0:
            raise ValueError(f"sample {index}: wavelength and sigma must be positive")
        validate_science_wavelength(row, index=index)
        row["source_index"] = int(row.get("source_index", index))
        rows.append(row)
        input_indices.append(index)
    if not rows:
        raise ValueError("no valid spectral samples remain")
    return rows, calibration_group, input_indices


def _validate_measurement_covariance(
    covariance: Any,
    sigma: np.ndarray,
    *,
    input_count: int,
    selected_indices: Sequence[int],
) -> tuple[np.ndarray, bool]:
    """Return the selected statistical covariance matrix."""
    if covariance is None:
        return np.diag(sigma ** 2), False
    full = np.asarray(covariance, dtype=float)
    expected_shape = (input_count, input_count)
    if full.shape != expected_shape:
        raise ValueError(f"measurement_covariance must have shape {expected_shape} in original input-row order")
    if np.any(~np.isfinite(full)):
        raise ValueError("measurement_covariance must be finite")
    if not np.allclose(full, full.T, rtol=1e-10, atol=1e-12):
        raise ValueError("measurement_covariance must be symmetric")
    selected = full[np.ix_(selected_indices, selected_indices)]
    if not np.allclose(np.diag(selected), sigma ** 2, rtol=1e-5, atol=1e-10):
        raise ValueError("measurement_covariance diagonal must agree with the selected sigma squared")
    try:
        np.linalg.cholesky(selected)
    except np.linalg.LinAlgError as exc:
        raise ValueError("measurement_covariance must be positive definite") from exc
    return selected, True


def _matrix_sha256(matrix: np.ndarray) -> str:
    arr = np.ascontiguousarray(np.asarray(matrix, dtype="<f8"))
    return hashlib.sha256(arr.tobytes()).hexdigest()


def reconstruct(
    samples: Sequence[Mapping[str, Any]],
    wavelength_grid_um: Sequence[float],
    time_grid_mjd: Sequence[float],
    *,
    wavelength_bandwidth_um: float,
    time_bandwidth_days: float,
    min_neighbors: int = 2,
    calibration_group: str | None = None,
    measurement_covariance: Sequence[Sequence[float]] | None = None,
    shared_calibration_fractional_sigma: float = 0.0,
) -> dict[str, Any]:
    """Reconstruct a local F(lambda,t) grid with covariance propagation.

    measurement_covariance is aligned to the original samples list. Its
    diagonal must equal sigma squared. The optional shared calibration
    systematic is one fully correlated multiplicative offset within this
    calibration group: C_cal = outer(f * flux, f * flux).
    """
    rows, group, input_indices = _validate_samples(samples, calibration_group)
    wave_grid = np.asarray(wavelength_grid_um, dtype=float)
    time_grid = np.asarray(time_grid_mjd, dtype=float)
    if wave_grid.ndim != 1 or time_grid.ndim != 1 or not wave_grid.size or not time_grid.size:
        raise ValueError("wavelength and time grids must be non-empty one-dimensional arrays")
    if np.any(~np.isfinite(wave_grid)) or np.any(wave_grid <= 0) or np.any(~np.isfinite(time_grid)):
        raise ValueError("grid values must be finite and wavelengths positive")
    if (
        not math.isfinite(float(wavelength_bandwidth_um))
        or not math.isfinite(float(time_bandwidth_days))
        or wavelength_bandwidth_um <= 0 or time_bandwidth_days <= 0
        or min_neighbors < 1
    ):
        raise ValueError("bandwidths and min_neighbors must be positive")
    if not math.isfinite(float(shared_calibration_fractional_sigma)) or shared_calibration_fractional_sigma < 0:
        raise ValueError("shared_calibration_fractional_sigma must be finite and non-negative")

    wave = np.asarray([row["wavelength_um"] for row in rows], dtype=float)
    time = np.asarray([row["mjd"] for row in rows], dtype=float)
    flux = np.asarray([row["flux"] for row in rows], dtype=float)
    sigma = np.asarray([row["sigma"] for row in rows], dtype=float)

    c_stat, supplied_covariance = _validate_measurement_covariance(
        measurement_covariance, sigma, input_count=len(samples), selected_indices=input_indices
    )
    calibration_vector = float(shared_calibration_fractional_sigma) * flux
    c_cal = np.outer(calibration_vector, calibration_vector)
    c_total = c_stat + c_cal
    try:
        np.linalg.cholesky(c_total)
    except np.linalg.LinAlgError as exc:
        raise ValueError("combined measurement and calibration covariance must be positive definite") from exc

    shape = (time_grid.size, wave_grid.size)
    out_flux = np.full(shape, np.nan)
    out_sigma_measurement = np.full(shape, np.nan)
    out_sigma_calibration = np.full(shape, np.nan)
    out_sigma_total = np.full(shape, np.nan)
    scatter = np.full(shape, np.nan)
    counts = np.zeros(shape, dtype=int)
    n_eff = np.zeros(shape, dtype=float)
    source_indices = [[[] for _ in wave_grid] for _ in time_grid]
    linear_weights = [[[] for _ in wave_grid] for _ in time_grid]

    for ti, target_t in enumerate(time_grid):
        for wi, target_w in enumerate(wave_grid):
            if target_t < np.min(time) or target_t > np.max(time) or target_w < np.min(wave) or target_w > np.max(wave):
                continue
            dw = (wave - target_w) / wavelength_bandwidth_um
            dt = (time - target_t) / time_bandwidth_days
            kernel = np.exp(-0.5 * (dw ** 2 + dt ** 2))
            idx = np.flatnonzero((np.abs(dw) <= 3.0) & (np.abs(dt) <= 3.0))
            if idx.size < min_neighbors:
                continue

            local_sqrt_kernel = np.sqrt(kernel[idx])
            local_c_stat = c_stat[np.ix_(idx, idx)]
            local_c_cal = c_cal[np.ix_(idx, idx)]
            local_c_total = c_total[np.ix_(idx, idx)]
            try:
                # For diagonal covariance, this is exactly kernel / sigma^2.
                solved = np.linalg.solve(local_c_total, np.diag(local_sqrt_kernel))
                precision = local_sqrt_kernel[:, None] * solved
            except np.linalg.LinAlgError:
                continue
            precision_one = precision @ np.ones(idx.size)
            denominator = float(np.sum(precision_one))
            if not math.isfinite(denominator) or denominator <= 0:
                continue
            alpha = precision_one / denominator
            effective = float(1.0 / np.sum(alpha ** 2))
            if not math.isfinite(effective) or effective < min_neighbors * 0.5:
                continue

            estimate = float(alpha @ flux[idx])
            stat_var = float(alpha @ local_c_stat @ alpha)
            cal_var = float(alpha @ local_c_cal @ alpha)
            total_var = float(alpha @ local_c_total @ alpha)
            if min(stat_var, cal_var, total_var) < -1e-10:
                continue

            out_flux[ti, wi] = estimate
            out_sigma_measurement[ti, wi] = math.sqrt(max(stat_var, 0.0))
            out_sigma_calibration[ti, wi] = math.sqrt(max(cal_var, 0.0))
            out_sigma_total[ti, wi] = math.sqrt(max(total_var, 0.0))

            scatter_weights = np.abs(alpha)
            scatter_weights /= scatter_weights.sum()
            scatter[ti, wi] = math.sqrt(max(
                0.0, float(np.sum(scatter_weights * (flux[idx] - estimate) ** 2))
            ))
            counts[ti, wi] = int(idx.size)
            n_eff[ti, wi] = effective
            source_indices[ti][wi] = [rows[j]["source_index"] for j in idx]
            linear_weights[ti][wi] = [
                {"source_index": rows[j]["source_index"], "coefficient": float(alpha[k])}
                for k, j in enumerate(idx)
            ]

    valid = np.isfinite(out_flux) & np.isfinite(out_sigma_measurement) & np.isfinite(out_sigma_total)
    return {
        "calibration_group": group,
        "wavelength_um": wave_grid.tolist(),
        "time_mjd": time_grid.tolist(),
        "flux": out_flux.tolist(),
        "sigma_measurement": out_sigma_measurement.tolist(),
        "sigma_shared_calibration": out_sigma_calibration.tolist(),
        "sigma_total": out_sigma_total.tolist(),
        "local_scatter": scatter.tolist(),
        "valid": valid.tolist(),
        "n_samples": counts.tolist(),
        "effective_n": n_eff.tolist(),
        "source_indices": source_indices,
        "linear_weights": linear_weights,
        "covariance_model": {
            "measurement_covariance_supplied": supplied_covariance,
            "measurement_covariance_sha256": _matrix_sha256(c_stat),
            "shared_calibration_model": "fully correlated multiplicative offset within this calibration group",
            "shared_calibration_fractional_sigma": float(shared_calibration_fractional_sigma),
            "shared_calibration_covariance_sha256": _matrix_sha256(c_cal),
            "total_covariance_sha256": _matrix_sha256(c_total),
            "covariance_row_source_indices": [row["source_index"] for row in rows],
            "covariance_note": "Matrix checksums bind the exact matrices used; covariance is aligned to the original input row order before invalid rows are removed.",
        },
        "method": "two-dimensional local Gaussian-kernel generalized least squares",
        "missing_data_policy": "Cells without local support remain NaN; no extrapolation beyond the sampled wavelength/time envelope.",
        "limitations": [
            "The estimate is a local smoother, not a physical source model or Gaussian-process posterior.",
            "Shared calibration uncertainty is a fully correlated multiplicative approximation unless a full statistical covariance is supplied.",
            "Covariance assumptions and matrices must be justified from calibration data; matrix hashes are integrity labels, not validation certificates.",
            "Local scatter is descriptive and is not silently added to propagated measurement uncertainty.",
            "Wavelength/time confounding from observing cadence can make spectral evolution non-identifiable.",
            "Only observations in one explicitly compatible calibration group are combined.",
        ],
    }
