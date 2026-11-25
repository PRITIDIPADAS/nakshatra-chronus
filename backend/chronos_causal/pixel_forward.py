"""Inspectable pixel-level sky and detector forward model.

All inputs are explicit. Generic defaults are never presented as measured
SPHEREx calibration. The model is a controlled forward experiment until its
parameter provenance has been independently validated.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from .forward_model import _map, _place_kernel

_PARAMETER_NAMES = (
    "source_spectra", "psf", "wavelength_response",
    "background_rate_electrons_per_s", "dark_current_rate_electrons_per_s",
    "read_noise_electrons", "flat_field", "detector_fixed_electrons",
)
_ALLOWED_STATUS = {"measured", "calibrated", "assumed", "illustrative", "placeholder"}


def _json_array(value):
    def clean(item):
        if isinstance(item, list):
            return [clean(part) for part in item]
        if isinstance(item, (float, np.floating)):
            return float(item) if math.isfinite(float(item)) else None
        if isinstance(item, np.generic):
            return item.item()
        return item
    return clean(np.asarray(value).tolist())


def _provenance(parameter_provenance: Mapping[str, Any] | None) -> dict[str, Any]:
    supplied = dict(parameter_provenance or {})
    result = {}
    for name in _PARAMETER_NAMES:
        item = dict(supplied.get(name) or {})
        status = str(item.get("status", "placeholder"))
        if status not in _ALLOWED_STATUS:
            raise ValueError(f"{name}.status must be one of {sorted(_ALLOWED_STATUS)}")
        if status == "measured" and not item.get("source_uri"):
            raise ValueError(f"{name}: measured parameters require source_uri")
        if status == "calibrated" and not item.get("calibration_id"):
            raise ValueError(f"{name}: calibrated parameters require calibration_id")
        result[name] = {
            "status": status,
            "source_uri": item.get("source_uri"),
            "calibration_id": item.get("calibration_id"),
            "notes": str(item.get("notes", "")),
        }
    return result


def simulate_spectral_exposure(*, shape: Sequence[int], mjd: float,
                                exposure_time_s: float,
                                wavelengths_um: Sequence[float],
                                bandwidths_um: Sequence[float],
                                wavelength_response,
                                sources: Sequence[Mapping[str, Any]],
                                psf_kernel,
                                background_rate_electrons_per_s=0.0,
                                dark_current_rate_electrons_per_s=0.0,
                                read_noise_electrons=0.0,
                                flat_field=None,
                                detector_fixed_electrons=None,
                                missing_pixel_mask=None,
                                flags=None, bad_flag_bits: int = 0,
                                wavelength_map_um=None,
                                calibration_nuisance: Mapping[str, float] | None = None,
                                parameter_provenance: Mapping[str, Any] | None = None,
                                seed: int = 1) -> dict[str, Any]:
    """Render one synthetic exposure from explicit sky, response and detector inputs.

    Source spectra are expected photoelectron rates before the supplied
    wavelength response, in electrons s^-1 um^-1. The response is a supplied
    dimensionless throughput map with shape (wavelength, y, x).
    """
    if len(shape) != 2 or any(int(value) <= 0 for value in shape):
        raise ValueError("shape must contain two positive dimensions")
    height, width = int(shape[0]), int(shape[1])
    shape = (height, width)
    mjd, exposure_time_s = float(mjd), float(exposure_time_s)
    if not math.isfinite(mjd) or not math.isfinite(exposure_time_s) or exposure_time_s <= 0:
        raise ValueError("mjd must be finite and exposure_time_s must be positive")
    wave = np.asarray(wavelengths_um, dtype=float)
    band = np.asarray(bandwidths_um, dtype=float)
    if wave.ndim != 1 or wave.size < 1 or band.shape != wave.shape:
        raise ValueError("wavelengths_um and bandwidths_um must be equal non-empty vectors")
    if np.any(~np.isfinite(wave)) or np.any(wave <= 0) or np.any(np.diff(wave) <= 0):
        raise ValueError("wavelengths_um must be finite, positive and strictly increasing")
    if np.any(~np.isfinite(band)) or np.any(band <= 0):
        raise ValueError("bandwidths_um must be finite and positive")
    response = np.asarray(wavelength_response, dtype=float)
    if response.shape != (wave.size, height, width):
        raise ValueError("wavelength_response must have shape (n_wavelengths, height, width)")
    if np.any(~np.isfinite(response)) or np.any(response < 0):
        raise ValueError("wavelength_response must be finite and non-negative")
    psf = np.asarray(psf_kernel, dtype=float)
    if psf.ndim != 2 or any(size % 2 == 0 for size in psf.shape):
        raise ValueError("psf_kernel must be a two-dimensional odd-sized array")
    if np.any(~np.isfinite(psf)) or np.any(psf < 0) or float(psf.sum()) <= 0:
        raise ValueError("psf_kernel must be finite, non-negative and have positive sum")
    psf = psf / psf.sum()

    provenance = _provenance(parameter_provenance)
    nuisance = dict(calibration_nuisance or {})
    nuisance_defaults = {"response_scale": 1.0, "source_scale": 1.0,
                         "background_scale": 1.0, "wavelength_offset_um": 0.0}
    for name, default in nuisance_defaults.items():
        value = float(nuisance.get(name, default))
        if not math.isfinite(value):
            raise ValueError(f"calibration_nuisance.{name} must be finite")
        nuisance[name] = value
    if nuisance["response_scale"] < 0 or nuisance["source_scale"] < 0 or nuisance["background_scale"] < 0:
        raise ValueError("response, source and background nuisance scales must be non-negative")

    response = response * nuisance["response_scale"]
    flat = _map(flat_field, shape, "flat_field", default=1.0)
    background_rate = _map(
        background_rate_electrons_per_s, shape, "background_rate_electrons_per_s"
    )
    dark_rate = _map(
        dark_current_rate_electrons_per_s, shape, "dark_current_rate_electrons_per_s"
    )
    read = _map(read_noise_electrons, shape, "read_noise_electrons")
    detector_fixed = _map(
        detector_fixed_electrons, shape, "detector_fixed_electrons"
    )
    if np.any(flat <= 0) or np.any(background_rate < 0) or np.any(dark_rate < 0):
        raise ValueError("flat field must be positive and background/dark rates non-negative")
    if np.any(read < 0):
        raise ValueError("read noise must be non-negative")

    source_by_wavelength = np.zeros((wave.size, height, width), dtype=float)
    source_metadata = []
    for source_index, source in enumerate(sources):
        try:
            source_id = str(source["source_id"])
            x0, y0 = float(source["x"]), float(source["y"])
            reference_mjd = float(source.get("reference_mjd", mjd))
            vx = float(source.get("dx_pixels_per_day", 0.0))
            vy = float(source.get("dy_pixels_per_day", 0.0))
            spectrum = np.asarray(source["flux_density_electrons_per_s_um"], dtype=float)
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"source {source_index} requires source_id, x, y and flux_density_electrons_per_s_um"
            ) from None
        if spectrum.shape != wave.shape or np.any(~np.isfinite(spectrum)) or np.any(spectrum < 0):
            raise ValueError(f"source {source_index} spectrum must be a non-negative vector matching wavelengths")
        if not all(math.isfinite(value) for value in (x0, y0, reference_mjd, vx, vy)):
            raise ValueError(f"source {source_index} position and motion must be finite")
        x = x0 + vx * (mjd - reference_mjd)
        y = y0 + vy * (mjd - reference_mjd)
        for channel in range(wave.size):
            total = (
                float(spectrum[channel]) * float(band[channel]) * exposure_time_s
                * nuisance["source_scale"]
            )
            stamp = np.zeros(shape, dtype=float)
            _place_kernel(stamp, psf, x, y, total)
            source_by_wavelength[channel] += stamp * response[channel]
        source_metadata.append({
            "source_id": source_id, "x_at_exposure_px": x, "y_at_exposure_px": y,
            "dx_pixels_per_day": vx, "dy_pixels_per_day": vy,
            "flux_density_electrons_per_s_um": spectrum.tolist(),
        })

    source_expected = np.sum(source_by_wavelength, axis=0) * flat
    background_expected = background_rate * exposure_time_s * nuisance["background_scale"] * flat
    dark_expected = dark_rate * exposure_time_s * flat
    detector_fixed_expected = detector_fixed.copy()
    # Only photo-generated source, background and dark-current electrons enter
    # the Poisson draw. The fixed detector term is deterministic and must not
    # be assigned photon shot noise.
    photon_expected = np.clip(
        source_expected + background_expected + dark_expected, 0.0, None
    )
    expected = photon_expected + detector_fixed_expected

    mask = np.zeros(shape, dtype=bool)
    if missing_pixel_mask is not None:
        incoming_mask = np.asarray(missing_pixel_mask, dtype=bool)
        if incoming_mask.shape != shape:
            raise ValueError("missing_pixel_mask must match frame shape")
        mask |= incoming_mask
    if flags is not None:
        flag_array = np.asarray(flags)
        if flag_array.shape != shape:
            raise ValueError("flags must match frame shape")
        if int(bad_flag_bits) < 0:
            raise ValueError("bad_flag_bits cannot be negative")
        if bad_flag_bits:
            mask |= (flag_array.astype(np.uint64) & np.uint64(bad_flag_bits)) != 0

    rng = np.random.default_rng(int(seed))
    poisson_realisation = rng.poisson(photon_expected).astype(float)
    read_realisation = rng.normal(0.0, read, size=shape)
    measured = poisson_realisation + detector_fixed_expected + read_realisation
    variance = photon_expected + read ** 2
    residual = measured - expected
    source_by_wavelength[:, mask] = np.nan
    for array in (source_expected, background_expected, dark_expected,
                  detector_fixed_expected, expected, poisson_realisation, read_realisation,
                  measured, variance, residual):
        array[mask] = np.nan

    if wavelength_map_um is None:
        weighted = np.sum(response * wave[:, None, None], axis=0)
        normalizer = np.sum(response, axis=0)
        effective_wave = np.full(shape, np.nan, dtype=float)
        valid = normalizer > 0
        effective_wave[valid] = weighted[valid] / normalizer[valid]
    else:
        effective_wave = np.asarray(wavelength_map_um, dtype=float).copy()
        if effective_wave.shape != shape or np.any(np.isinf(effective_wave)):
            raise ValueError("wavelength_map_um must match frame shape and contain no infinities")
    effective_wave += nuisance["wavelength_offset_um"]
    effective_wave[mask] = np.nan

    calibration_ready = all(
        item["status"] in {"measured", "calibrated"}
        for item in provenance.values()
    )
    return {
        "model": "spectral pixel forward model",
        "data_class": "synthetic controlled experiment",
        "units": {
            "source_rate": "electrons s^-1 um^-1 before wavelength response",
            "source_integrated": "electrons",
            "detector_signal": "electrons",
            "variance": "electrons squared",
            "wavelength": "micrometres",
            "time": "MJD and seconds",
        },
        "mjd": mjd,
        "exposure_time_s": exposure_time_s,
        "wavelengths_um": wave.tolist(),
        "bandwidths_um": band.tolist(),
        "model_inputs": {
            "psf_kernel_normalized": psf.tolist(),
            "wavelength_response_dimensionless": response.tolist(),
            "flat_field_relative": flat.tolist(),
            "background_rate_electrons_per_s": background_rate.tolist(),
            "dark_current_rate_electrons_per_s": dark_rate.tolist(),
            "read_noise_electrons": read.tolist(),
            "detector_fixed_electrons": detector_fixed.tolist(),
            "bad_flag_bits": int(bad_flag_bits),
        },
        "components": {
            "source_electrons_by_wavelength_before_flat_field": _json_array(source_by_wavelength),
            "source_electrons": _json_array(source_expected),
            "background_electrons": _json_array(background_expected),
            "dark_current_electrons": _json_array(dark_expected),
            "detector_fixed_electrons": _json_array(detector_fixed_expected),
            "photon_generated_expected_electrons": _json_array(photon_expected),
            "expected_total_electrons_including_fixed_detector_term": _json_array(expected),
            "poisson_realisation_electrons": _json_array(poisson_realisation),
            "read_noise_realisation_electrons": _json_array(read_realisation),
            "measured_electrons": _json_array(measured),
            "variance_electrons_squared": _json_array(variance),
            "unexplained_residual_electrons": _json_array(residual),
            "missing_pixel_mask": mask.tolist(),
            "effective_wavelength_map_um": _json_array(effective_wave),
        },
        "sources": source_metadata,
        "calibration_nuisance": nuisance,
        "parameter_provenance": provenance,
        "calibration_ready": calibration_ready,
        "seed": int(seed),
        "original_inputs_mutated": False,
        "limitations": [
            "This is a controlled synthetic forward model, not a SPHEREx raw-readout converter.",
            "Source spectra are supplied in pre-response electron-rate units; a real analysis must derive them from calibrated physical flux and instrument throughput.",
            "The wavelength response and PSF are supplied arrays. Their shape and numeric validity do not establish calibration compatibility.",
            "The PSF is spatially constant in this first implementation.",
            "Noise is Poisson in the expected electron count plus Gaussian read noise; covariance, saturation and nonlinear readout are not modelled here.",
            "Parameters marked assumed, illustrative or placeholder are not measured SPHEREx properties.",
        ],
    }
