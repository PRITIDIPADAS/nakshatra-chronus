"""Local reconstruction of F(lambda, t) from irregular calibrated samples.

Only interpolates inside the observed wavelength/time envelope. It preserves
missing grid cells and reports the source rows used for every estimate.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
import numpy as np

def _validate_samples(samples: Sequence[Mapping[str, Any]], calibration_group: str | None):
    if not samples:
        raise ValueError("at least one spectral measurement is required")
    groups = {str(r.get("calibration_group", "")) for r in samples}
    if "" in groups:
        raise ValueError("every sample needs an explicit calibration_group")
    if calibration_group is not None:
        if calibration_group not in groups:
            raise ValueError(f"calibration_group {calibration_group!r} is not present")
        selected = [r for r in samples if str(r["calibration_group"]) == calibration_group]
    elif len(groups) == 1:
        selected = list(samples)
        calibration_group = next(iter(groups))
    else:
        raise ValueError("samples contain incompatible calibration groups; select one group per reconstruction")
    rows = []
    for i, raw in enumerate(selected):
        r = dict(raw)
        if r.get("valid", True) is False:
            continue
        for key in ("mjd", "wavelength_um", "flux", "sigma"):
            try:
                r[key] = float(r[key])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"sample {i} requires numeric {key}") from None
            if not math.isfinite(r[key]):
                raise ValueError(f"sample {i}: {key} must be finite")
        if r["wavelength_um"] <= 0 or r["sigma"] <= 0:
            raise ValueError(f"sample {i}: wavelength and sigma must be positive")
        r["source_index"] = int(r.get("source_index", i))
        rows.append(r)
    if not rows:
        raise ValueError("no valid spectral samples remain")
    return rows, calibration_group

def reconstruct(samples: Sequence[Mapping[str, Any]], wavelength_grid_um: Sequence[float],
                time_grid_mjd: Sequence[float], *, wavelength_bandwidth_um: float,
                time_bandwidth_days: float, min_neighbors: int = 2,
                calibration_group: str | None = None) -> dict[str, Any]:
    rows, group = _validate_samples(samples, calibration_group)
    wave_grid = np.asarray(wavelength_grid_um, float)
    time_grid = np.asarray(time_grid_mjd, float)
    if wave_grid.ndim != 1 or time_grid.ndim != 1 or not wave_grid.size or not time_grid.size:
        raise ValueError("wavelength and time grids must be non-empty one-dimensional arrays")
    if np.any(~np.isfinite(wave_grid)) or np.any(wave_grid <= 0) or np.any(~np.isfinite(time_grid)):
        raise ValueError("grid values must be finite and wavelengths positive")
    if wavelength_bandwidth_um <= 0 or time_bandwidth_days <= 0 or min_neighbors < 1:
        raise ValueError("bandwidths and min_neighbors must be positive")
    wave = np.asarray([r["wavelength_um"] for r in rows])
    time = np.asarray([r["mjd"] for r in rows])
    flux = np.asarray([r["flux"] for r in rows])
    sigma = np.asarray([r["sigma"] for r in rows])
    shape = (time_grid.size, wave_grid.size)
    out_flux = np.full(shape, np.nan)
    out_sigma = np.full(shape, np.nan)
    scatter = np.full(shape, np.nan)
    counts = np.zeros(shape, dtype=int)
    n_eff = np.zeros(shape, dtype=float)
    provenance = [[[] for _ in wave_grid] for _ in time_grid]
    for ti, target_t in enumerate(time_grid):
        for wi, target_w in enumerate(wave_grid):
            if target_t < np.min(time) or target_t > np.max(time) or target_w < np.min(wave) or target_w > np.max(wave):
                continue
            dw = (wave - target_w) / wavelength_bandwidth_um
            dt = (time - target_t) / time_bandwidth_days
            keep = (np.abs(dw) <= 3.0) & (np.abs(dt) <= 3.0)
            idx = np.flatnonzero(keep)
            if idx.size < min_neighbors:
                continue
            weights = np.exp(-0.5 * (dw[idx] ** 2 + dt[idx] ** 2)) / (sigma[idx] ** 2)
            total = float(np.sum(weights))
            if not math.isfinite(total) or total <= 0:
                continue
            wn = weights / total
            effective = float(1.0 / np.sum(wn ** 2))
            if effective < min_neighbors * 0.5:
                continue
            estimate = float(np.sum(wn * flux[idx]))
            out_flux[ti, wi] = estimate
            out_sigma[ti, wi] = float(np.sqrt(np.sum((wn * sigma[idx]) ** 2)))
            scatter[ti, wi] = float(np.sqrt(max(0.0, np.sum(wn * (flux[idx] - estimate) ** 2))))
            counts[ti, wi] = int(idx.size)
            n_eff[ti, wi] = effective
            provenance[ti][wi] = [rows[j]["source_index"] for j in idx]
    valid = np.isfinite(out_flux) & np.isfinite(out_sigma)
    return {
        "calibration_group": group,
        "wavelength_um": wave_grid.tolist(),
        "time_mjd": time_grid.tolist(),
        "flux": out_flux.tolist(),
        "sigma_measurement": out_sigma.tolist(),
        "local_scatter": scatter.tolist(),
        "valid": valid.tolist(),
        "n_samples": counts.tolist(),
        "effective_n": n_eff.tolist(),
        "source_indices": provenance,
        "method": "two-dimensional local Gaussian kernel regression with inverse-variance weighting",
        "missing_data_policy": "Cells without local support remain NaN; no extrapolation beyond the sampled wavelength/time envelope.",
        "limitations": [
            "The estimate is a local smoother, not a physical source model or a Gaussian-process posterior.",
            "The reported sigma propagates supplied independent measurement errors; covariance and calibration systematics are not included.",
            "Local scatter is reported separately and is not silently added to the measurement uncertainty.",
            "Wavelength/time confounding from the observing cadence can make spectral evolution non-identifiable.",
            "Only observations in one explicitly compatible calibration group are combined.",
        ],
    }
