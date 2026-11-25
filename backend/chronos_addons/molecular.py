"""Measure pre-specified spectral features without assigning molecular identity."""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import re

import numpy as np

from .spectral import Spectrum

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _resolution_diagnostics(
    spectrum: Spectrum,
    feature_interval_um: tuple[float, float],
    resolution: Mapping[str, Any] | None,
    potential_blend_intervals_um: Sequence[Sequence[float]] | None,
) -> dict[str, Any]:
    lo, hi = feature_interval_um
    center = 0.5 * (lo + hi)
    result: dict[str, Any] = {
        "status": "not_supplied",
        "resolving_power": None,
        "lsf_fwhm_um": None,
        "median_native_spacing_um": None,
        "samples_per_fwhm": None,
        "resolution_elements_across_interval": None,
        "sampling_status": "unknown_without_resolution",
        "source_reference_recorded": False,
        "warning": "A feature measurement without a resolution record is not resolution-validated.",
    }
    fwhm = None
    resolving_power = None
    if resolution is not None:
        if not isinstance(resolution, Mapping):
            raise ValueError("resolution must be a mapping with resolving_power or lsf_fwhm_um")
        raw_fwhm = resolution.get("lsf_fwhm_um")
        raw_r = resolution.get("resolving_power")
        if raw_fwhm is None and raw_r is None:
            raise ValueError("resolution must provide lsf_fwhm_um or resolving_power")
        if raw_r is not None:
            resolving_power = float(raw_r)
            if not math.isfinite(resolving_power) or resolving_power <= 0:
                raise ValueError("resolving_power must be finite and positive")
            from_r = center / resolving_power
        else:
            from_r = None
        if raw_fwhm is not None:
            fwhm = float(raw_fwhm)
            if not math.isfinite(fwhm) or fwhm <= 0:
                raise ValueError("lsf_fwhm_um must be finite and positive")
        else:
            fwhm = from_r
        if fwhm is None or fwhm <= 0:
            raise ValueError("a positive LSF FWHM could not be derived")
        if from_r is not None and not math.isclose(fwhm, from_r, rel_tol=0.25, abs_tol=1e-12):
            raise ValueError("lsf_fwhm_um and resolving_power disagree by more than 25 percent")
        if resolving_power is None:
            resolving_power = center / fwhm

        valid_wave = spectrum.wavelength_um[spectrum.valid]
        spacing = float(np.median(np.diff(valid_wave))) if valid_wave.size > 1 else None
        samples_per_fwhm = fwhm / spacing if spacing is not None and spacing > 0 else None
        sampling_status = (
            "sampled_at_two_or_more_pixels_per_fwhm"
            if samples_per_fwhm is not None and samples_per_fwhm >= 2.0
            else "undersampled_or_insufficient_native_samples"
        )
        source_uri = resolution.get("source_uri")
        source_hash = resolution.get("sha256")
        source_recorded = (
            isinstance(source_uri, str) and source_uri.startswith("https://")
            and isinstance(source_hash, str) and bool(_SHA256.fullmatch(source_hash))
        )
        result.update({
            "status": "provided",
            "resolving_power": float(resolving_power),
            "lsf_fwhm_um": float(fwhm),
            "median_native_spacing_um": spacing,
            "samples_per_fwhm": samples_per_fwhm,
            "resolution_elements_across_interval": float((hi - lo) / fwhm),
            "sampling_status": sampling_status,
            "source_reference_recorded": source_recorded,
            "source_uri": source_uri,
            "source_sha256": source_hash,
            "source_status": "reference_and_hash_recorded" if source_recorded else "unverified_operator_supplied_resolution",
            "warning": "A recorded URI and digest are provenance metadata; the source bytes and LSF validity still require independent verification.",
        })

    blend_rows = []
    for index, raw in enumerate(potential_blend_intervals_um or []):
        if len(raw) != 2:
            raise ValueError(f"potential blend interval {index} must contain [low, high]")
        blend_lo, blend_hi = map(float, raw)
        if not math.isfinite(blend_lo) or not math.isfinite(blend_hi) or not blend_lo < blend_hi:
            raise ValueError(f"potential blend interval {index} must be finite and increasing")
        if fwhm is None:
            overlaps = blend_lo <= hi and blend_hi >= lo
            separation = 0.0 if overlaps else min(abs(blend_hi - lo), abs(blend_lo - hi))
        else:
            expanded_lo, expanded_hi = lo - 0.5 * fwhm, hi + 0.5 * fwhm
            overlaps = blend_lo <= expanded_hi and blend_hi >= expanded_lo
            separation = 0.0 if overlaps else min(abs(blend_hi - expanded_lo), abs(blend_lo - expanded_hi))
        blend_rows.append({
            "interval_um": [blend_lo, blend_hi],
            "within_one_half_fwhm_of_feature": bool(overlaps),
            "separation_um": float(separation),
        })
    possible = [row for row in blend_rows if row["within_one_half_fwhm_of_feature"]]
    result["blend_diagnostics"] = {
        "status": "possible_blend" if possible else (
            "no_declared_neighbor_overlap" if blend_rows else "not_assessed"
        ),
        "potential_blend_intervals_um": blend_rows,
        "possible_blends": possible,
        "warning": "No declared interval overlap is not proof that the feature is physically unblended.",
    }
    return result


def measure_equivalent_width(
    spectrum: Spectrum,
    feature_interval_um: Sequence[float],
    continuum_intervals_um: Sequence[Sequence[float]],
    *,
    resolution: Mapping[str, Any] | None = None,
    potential_blend_intervals_um: Sequence[Sequence[float]] | None = None,
    continuum_model: str = "linear",
) -> dict[str, Any]:
    """Measure equivalent width and report resolution/blend limitations."""
    if len(feature_interval_um) != 2 or len(continuum_intervals_um) != 2 or any(len(x) != 2 for x in continuum_intervals_um):
        raise ValueError("provide one feature interval and exactly two continuum sidebands")
    flo, fhi = map(float, feature_interval_um)
    sides = [tuple(map(float, x)) for x in continuum_intervals_um]
    if not flo < fhi or any(not a < b for a, b in sides) or not (sides[0][1] < flo and fhi < sides[1][0]):
        raise ValueError("continuum sidebands must bracket and not overlap the feature")

    if continuum_model not in {"linear", "constant"}:
        raise ValueError("continuum_model must be 'linear' or 'constant'")
    s = spectrum.normalized()
    resolution_report = _resolution_diagnostics(
        s, (flo, fhi), resolution, potential_blend_intervals_um
    )
    feature_mask = (s.wavelength_um >= flo) & (s.wavelength_um <= fhi) & s.valid
    side_mask = np.zeros(s.wavelength_um.size, bool)
    for side_lo, side_hi in sides:
        side_mask |= (s.wavelength_um >= side_lo) & (s.wavelength_um <= side_hi) & s.valid
    if feature_mask.sum() < 3 or side_mask.sum() < 4:
        raise ValueError("need >=3 feature and >=4 continuum samples")

    xs_wave = s.wavelength_um[side_mask]
    x0 = float(np.mean(xs_wave))
    xs = xs_wave - x0
    xf_wave = s.wavelength_um[feature_mask]
    xf = xf_wave - x0
    design = (np.column_stack([np.ones(xs.size), xs])
              if continuum_model == "linear" else np.ones((xs.size, 1)))
    weights = 1 / s.sigma[side_mask] ** 2 if s.sigma is not None else np.ones(xs.size)
    normal = design.T @ (weights[:, None] * design)
    if np.linalg.cond(normal) > 1e12:
        raise ValueError("continuum sidebands do not constrain stable linear fit")
    covariance = np.linalg.inv(normal)
    beta = covariance @ (design.T @ (weights * s.flux[side_mask]))
    feature_design = (np.column_stack([np.ones(xf.size), xf])
                      if continuum_model == "linear" else np.ones((xf.size, 1)))
    continuum = feature_design @ beta
    if np.any(continuum <= 0) or np.any(~np.isfinite(continuum)):
        raise ValueError("continuum must be finite and positive")

    wave = xf_wave
    dx = np.diff(wave)
    integration_weights = np.empty(wave.size)
    integration_weights[0] = dx[0] / 2
    integration_weights[-1] = dx[-1] / 2
    if wave.size > 2:
        integration_weights[1:-1] = (dx[:-1] + dx[1:]) / 2
    flux = s.flux[feature_mask]
    equivalent_width = float(np.sum(integration_weights * (1 - flux / continuum)))
    ew_sigma = None
    significance = None
    if s.sigma is not None:
        dflux = -integration_weights / continuum
        dbeta = np.sum(
            (integration_weights * flux / continuum ** 2)[:, None] * feature_design,
            axis=0,
        )
        variance = float(
            np.sum((dflux * s.sigma[feature_mask]) ** 2) + dbeta @ covariance @ dbeta
        )
        ew_sigma = float(np.sqrt(max(0, variance)))
        significance = equivalent_width / ew_sigma if ew_sigma > 0 else None

    feature_depth = float(1.0 - np.min(flux / continuum))
    deepest_index = int(np.argmin(flux / continuum))
    deepest_wavelength = float(xf_wave[deepest_index])
    continuum_uncertainty = np.sqrt(np.maximum(
        np.einsum("ij,jk,ik->i", feature_design, covariance, feature_design), 0.0
    ))
    depth_sigma = None
    if s.sigma is not None:
        cmin = float(continuum[deepest_index])
        fmin = float(flux[deepest_index])
        cmin_sigma = float(continuum_uncertainty[deepest_index])
        depth_sigma = float(math.sqrt(
            (float(s.sigma[feature_mask][deepest_index]) / cmin) ** 2
            + (fmin * cmin_sigma / cmin ** 2) ** 2
        ))

    return {
        "feature_interval_um": [flo, fhi],
        "continuum_intervals_um": [list(x) for x in sides],
        "equivalent_width_um": equivalent_width,
        "equivalent_width_sigma_um": ew_sigma,
        "equivalent_width_significance": significance,
        "feature_depth": feature_depth,
        "feature_depth_sigma": depth_sigma,
        "feature_depth_minimum_wavelength_um": deepest_wavelength,
        "continuum_uncertainty_mean": float(np.mean(continuum_uncertainty)),
        "continuum_model": {
            "type": "weighted_" + continuum_model,
            "coefficients": [float(value) for value in beta],
            "intercept": float(beta[0]),
            "slope_per_um": float(beta[1]) if continuum_model == "linear" else 0.0,
            "reference_wavelength_um": x0,
            "coefficient_covariance": covariance.tolist(),
            "n_samples": int(side_mask.sum()),
        },
        "n_feature_samples": int(feature_mask.sum()),
        "n_continuum_samples": int(side_mask.sum()),
        "resolution_diagnostics": resolution_report,
        "blend_diagnostics": resolution_report["blend_diagnostics"],
        "interpretation": "Positive EW is absorption; negative EW is emission under this continuum convention.",
        "limitations": [
            "Feature interval is user supplied; no molecule is identified.",
            "A resolution value is only as valid as the supplied product, detector, wavelength and calibration provenance.",
            "Potential blend intervals are screening flags; no deblending or line-spread-function fit is performed.",
            "Continuum model must be inspected against the source spectrum; compare alternative models before interpretation.",
            "Feature depth is the minimum continuum-normalized pixel value, not an intrinsic deconvolved depth.",
            "Uncertainty uses first-order propagation and an independent-sample assumption.",
        ],
    }
