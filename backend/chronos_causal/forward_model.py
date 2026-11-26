"""Electron-domain exposure simulator for controlled detector experiments.

This is a generic detector experiment model. It is not a SPHEREx raw-data
converter or a claim that unspecified instrument parameters are known.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
import numpy as np

def _map(value, shape, label, *, default=0.0):
    if value is None:
        return np.full(shape, default, dtype=float)
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = np.full(shape, float(arr), dtype=float)
    if arr.shape != shape or np.any(~np.isfinite(arr)):
        raise ValueError(f"{label} must be a finite scalar or an array matching frame shape")
    return arr.copy()

def _place_kernel(frame, kernel, x, y, total):
    """Deposit a normalized PSF with bilinear sub-pixel shifts and no edge wrap."""
    height, width = frame.shape
    kh, kw = kernel.shape
    left = int(math.floor(x)) - kw // 2
    top = int(math.floor(y)) - kh // 2
    frac_x = x - math.floor(x)
    frac_y = y - math.floor(y)
    for iy in range(kh):
        for ix in range(kw):
            value = total * float(kernel[iy, ix])
            px, py = left + ix, top + iy
            contributions = (
                (px, py, (1.0 - frac_x) * (1.0 - frac_y)),
                (px + 1, py, frac_x * (1.0 - frac_y)),
                (px, py + 1, (1.0 - frac_x) * frac_y),
                (px + 1, py + 1, frac_x * frac_y),
            )
            for xx, yy, weight in contributions:
                if 0 <= xx < width and 0 <= yy < height:
                    frame[yy, xx] += value * weight

def simulate_detector_frame(*, shape: Sequence[int], sources: Sequence[Mapping[str, Any]],
                             psf_kernel, background_electrons=0.0,
                             dark_current_electrons=0.0, read_noise_electrons=0.0,
                             flat_field=None, hot_pixel_electrons=None,
                             persistence_electrons=None, bad_pixel_mask=None,
                             nonlinearity_per_electron: float = 0.0,
                             crosstalk_fraction: float = 0.0,
                             crosstalk_axis: int = 1, seed: int = 1) -> dict[str, Any]:
    if len(shape) != 2 or any(int(x) <= 0 for x in shape):
        raise ValueError("shape must contain two positive dimensions")
    shape = (int(shape[0]), int(shape[1]))
    psf = np.asarray(psf_kernel, dtype=float)
    if psf.ndim != 2 or np.any(~np.isfinite(psf)) or np.any(psf < 0) or float(psf.sum()) <= 0:
        raise ValueError("PSF kernel must be a finite, non-negative 2-D array with positive sum")
    psf = psf / psf.sum()
    if not math.isfinite(nonlinearity_per_electron) or nonlinearity_per_electron < 0:
        raise ValueError("nonlinearity_per_electron must be finite and non-negative")
    if not 0 <= crosstalk_fraction < 0.25 or crosstalk_axis not in (0, 1):
        raise ValueError("crosstalk fraction must be in [0, 0.25) and axis must be 0 or 1")
    background = _map(background_electrons, shape, "background_electrons")
    dark = _map(dark_current_electrons, shape, "dark_current_electrons")
    read = _map(read_noise_electrons, shape, "read_noise_electrons")
    flat = _map(flat_field, shape, "flat_field", default=1.0)
    hot = _map(hot_pixel_electrons, shape, "hot_pixel_electrons")
    persistence = _map(persistence_electrons, shape, "persistence_electrons")
    if np.any(background < 0) or np.any(dark < 0) or np.any(read < 0) or np.any(hot < 0) or np.any(persistence < 0):
        raise ValueError("background, dark, read noise, hot-pixel and persistence terms must be non-negative")
    if np.any(flat <= 0):
        raise ValueError("flat-field response must be positive")
    rng = np.random.default_rng(int(seed))
    source_map = np.zeros(shape, dtype=float)
    for index, source in enumerate(sources):
        try:
            x, y, electrons = float(source["x"]), float(source["y"]), float(source["expected_electrons"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"source {index} requires numeric x, y and expected_electrons") from None
        if not all(math.isfinite(v) for v in (x, y, electrons)) or electrons < 0:
            raise ValueError(f"source {index} values must be finite and expected_electrons non-negative")
        _place_kernel(source_map, psf, x, y, electrons)
    incident = (source_map + background + dark) * flat + hot + persistence
    incident = np.clip(incident, 0.0, None)
    nonlinear_expected = incident * (1.0 + nonlinearity_per_electron * incident)
    poisson = rng.poisson(nonlinear_expected).astype(float)
    if crosstalk_fraction:
        shifted = np.zeros_like(poisson)
        if crosstalk_axis == 1:
            shifted[:, 1:] = poisson[:, :-1]
        else:
            shifted[1:, :] = poisson[:-1, :]
        poisson = (1.0 - crosstalk_fraction) * poisson + crosstalk_fraction * shifted
    noise = rng.normal(0.0, read, size=shape)
    measured = poisson + noise
    variance = nonlinear_expected + read ** 2
    mask = np.zeros(shape, dtype=bool) if bad_pixel_mask is None else np.asarray(bad_pixel_mask, dtype=bool)
    if mask.shape != shape:
        raise ValueError("bad_pixel_mask must match frame shape")
    measured[mask] = np.nan
    variance[mask] = np.nan
    return {
        "expected_source_electrons": source_map.tolist(),
        "expected_detector_electrons": nonlinear_expected.tolist(),
        "measured_electrons": measured.tolist(),
        "variance_electrons_squared": variance.tolist(),
        "bad_pixel_mask": mask.tolist(),
        "seed": int(seed),
        "parameters": {
            "read_noise_electrons": float(np.mean(read)),
            "nonlinearity_per_electron": nonlinearity_per_electron,
            "crosstalk_fraction": crosstalk_fraction,
            "crosstalk_axis": crosstalk_axis,
            "psf_shape": list(psf.shape),
            "source_count": len(sources),
        },
        "noise_model": "Poisson photon plus background/dark shot noise, followed by Gaussian read noise",
        "limitations": [
            "Electron-domain controlled simulation, not calibrated SPHEREx raw-readout reconstruction.",
            "PSF is supplied by the caller and is assumed spatially constant within this frame.",
            "Nonlinearity is a simplified quadratic response; use instrument calibration coefficients for real experiments.",
            "Crosstalk is a simple one-direction neighbour coupling, not the mission detector's calibrated crosstalk geometry.",
            "Persistence, hot pixels, flat field and bad-pixel masks must come from documented instrument products.",
            "Output is useful for controlled injection experiments only after parameters and units are independently justified.",
        ],
    }
