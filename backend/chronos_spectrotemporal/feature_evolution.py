"""Resolution-aware, predeclared spectral-feature evolution."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from chronos_causal.wavelength_gate import validate_spectral_epoch


def _lab_shape_comparison(epoch, measured, reference, feature_interval, continuum_intervals, continuum_model):
    """Compare a lab shape only after exact unit/provenance/resolution checks."""
    import numpy as np
    reference_id = str(reference.get("reference_id", "")).strip()
    source_uri = str(reference.get("source_uri", "")).strip()
    digest = str(reference.get("sha256", "")).lower()
    if not reference_id or not source_uri.startswith("https://") or len(digest) != 64 or any(
        ch not in "0123456789abcdef" for ch in digest
    ):
        return {"reference_id": reference_id or None, "status": "incompatible_provenance",
                "reason": "Reference ID, HTTPS URI and SHA-256 digest are required."}
    if str(reference.get("wavelength_unit", "")).lower() not in {
        "um", "micron", "microns", "micrometer", "micrometers"
    }:
        return {"reference_id": reference_id, "status": "incompatible_wavelength_units",
                "reason": "Laboratory wavelength unit must be micrometres."}
    observed_unit = str(epoch.get("flux_unit", "")).strip()
    reference_unit = str(reference.get("flux_unit", "")).strip()
    if not observed_unit or not reference_unit or observed_unit != reference_unit:
        return {"reference_id": reference_id, "status": "incompatible_flux_units",
                "reason": "Observed and laboratory intensity units must match exactly and be explicit."}
    resolution = measured["resolution_diagnostics"]
    observed_fwhm = resolution.get("lsf_fwhm_um")
    if observed_fwhm is None:
        return {"reference_id": reference_id, "status": "resolution_unavailable",
                "reason": "Observed epoch has no documented LSF FWHM."}
    observed_fwhm = float(observed_fwhm)
    lab_fwhm = reference.get("lsf_fwhm_um")
    if lab_fwhm is None and reference.get("resolving_power") is not None:
        resolving_power = float(reference["resolving_power"])
        centre = (float(feature_interval[0]) + float(feature_interval[1])) / 2
        if not math.isfinite(resolving_power) or resolving_power <= 0:
            return {"reference_id": reference_id, "status": "invalid_laboratory_resolution",
                    "reason": "Laboratory resolving power must be positive."}
        lab_fwhm = centre / resolving_power
    if lab_fwhm is None:
        return {"reference_id": reference_id, "status": "resolution_unavailable",
                "reason": "Laboratory LSF FWHM or resolving power is required."}
    lab_fwhm = float(lab_fwhm)
    if not math.isfinite(lab_fwhm) or lab_fwhm <= 0:
        return {"reference_id": reference_id, "status": "invalid_laboratory_resolution",
                "reason": "Laboratory LSF FWHM must be positive."}
    if lab_fwhm > observed_fwhm * 1.05:
        return {"reference_id": reference_id, "status": "incompatible_resolution",
                "observed_fwhm_um": observed_fwhm, "laboratory_fwhm_um": lab_fwhm,
                "reason": "Laboratory spectrum has lower resolving power and cannot be upsampled into a valid comparison."}

    lab_wave = np.asarray(reference.get("wavelength_um", []), dtype=float)
    lab_flux = np.asarray(reference.get("intensity", []), dtype=float)
    if lab_wave.ndim != 1 or lab_flux.shape != lab_wave.shape or lab_wave.size < 7:
        return {"reference_id": reference_id, "status": "invalid_reference_spectrum",
                "reason": "Reference wavelength and intensity arrays must be equal one-dimensional arrays with at least seven samples."}
    if np.any(~np.isfinite(lab_wave)) or np.any(lab_wave <= 0) or np.any(~np.isfinite(lab_flux)):
        return {"reference_id": reference_id, "status": "invalid_reference_spectrum",
                "reason": "Reference spectrum contains invalid values."}
    order = np.argsort(lab_wave)
    lab_wave, lab_flux = lab_wave[order], lab_flux[order]
    spacing = np.diff(lab_wave)
    if np.any(spacing <= 0):
        return {"reference_id": reference_id, "status": "invalid_reference_spectrum",
                "reason": "Laboratory wavelengths must be strictly increasing and unique."}
    median_spacing = float(np.median(spacing))
    if np.max(np.abs(spacing - median_spacing)) / median_spacing > 0.05:
        return {"reference_id": reference_id, "status": "nonuniform_reference_sampling",
                "reason": "Laboratory sampling must be approximately uniform for Gaussian convolution."}
    need = [float(feature_interval[0]), float(feature_interval[1]),
            *[float(v) for pair in continuum_intervals for v in pair]]
    if lab_wave[0] > min(need) or lab_wave[-1] < max(need):
        return {"reference_id": reference_id, "status": "insufficient_reference_coverage",
                "reason": "Laboratory spectrum does not span the feature and both continuum intervals."}

    additional_sigma_um = math.sqrt(max(observed_fwhm ** 2 - lab_fwhm ** 2, 0.0)) / 2.354820045
    sigma_pixels = additional_sigma_um / median_spacing
    if sigma_pixels > 0.05:
        radius = max(1, int(math.ceil(4 * sigma_pixels)))
        kernel_x = np.arange(-radius, radius + 1, dtype=float)
        kernel = np.exp(-0.5 * (kernel_x / sigma_pixels) ** 2)
        kernel /= kernel.sum()
        lab_flux = np.convolve(lab_flux, kernel, mode="same")

    observed_wave = np.asarray(epoch["wavelength_um"], dtype=float)
    observed_flux = np.asarray(epoch["flux"], dtype=float)
    valid = np.asarray(epoch.get("valid", np.ones(observed_wave.size, dtype=bool)), dtype=bool)
    lab_on_observed = np.interp(observed_wave, lab_wave, lab_flux)
    feature_mask = ((observed_wave >= feature_interval[0])
                    & (observed_wave <= feature_interval[1]) & valid)
    side_mask = np.zeros(observed_wave.size, dtype=bool)
    for lower, upper in continuum_intervals:
        side_mask |= ((observed_wave >= lower) & (observed_wave <= upper) & valid)
    if feature_mask.sum() < 3 or side_mask.sum() < (4 if continuum_model == "linear" else 2):
        return {"reference_id": reference_id, "status": "insufficient_observed_sampling",
                "reason": "Observed epoch does not sample feature and continua sufficiently."}

    def normalize(values):
        x0 = float(np.mean(observed_wave[side_mask]))
        x = observed_wave[side_mask] - x0
        xf = observed_wave - x0
        design = (np.column_stack([np.ones(x.size), x])
                  if continuum_model == "linear" else np.ones((x.size, 1)))
        design_feature = (np.column_stack([np.ones(xf.size), xf])
                          if continuum_model == "linear" else np.ones((xf.size, 1)))
        beta = np.linalg.lstsq(design, values[side_mask], rcond=None)[0]
        continuum = design_feature @ beta
        if np.any(~np.isfinite(continuum[feature_mask])) or np.any(continuum[feature_mask] <= 0):
            raise ValueError("continuum is non-positive or non-finite")
        return values[feature_mask] / continuum[feature_mask], continuum[feature_mask]

    try:
        observed_norm, observed_continuum = normalize(observed_flux)
        reference_norm, _ = normalize(lab_on_observed)
    except ValueError as exc:
        return {"reference_id": reference_id, "status": "invalid_continuum", "reason": str(exc)}
    residual = observed_norm - reference_norm
    shape_rms = float(np.sqrt(np.mean(residual ** 2)))
    reduced_chi2 = None
    if epoch.get("sigma") is not None:
        sigma = np.asarray(epoch["sigma"], dtype=float)[feature_mask] / observed_continuum
        if np.all(np.isfinite(sigma)) and np.all(sigma > 0):
            reduced_chi2 = float(np.mean((residual / sigma) ** 2))
    return {
        "reference_id": reference_id, "label": reference.get("label"),
        "status": "resolution_matched_shape_comparison",
        "source_uri": source_uri, "sha256": digest,
        "observed_flux_unit": observed_unit, "laboratory_flux_unit": reference_unit,
        "observed_lsf_fwhm_um": observed_fwhm,
        "laboratory_lsf_fwhm_um": lab_fwhm,
        "additional_gaussian_convolution_fwhm_um": math.sqrt(
            max(observed_fwhm ** 2 - lab_fwhm ** 2, 0.0)
        ),
        "continuum_model": continuum_model,
        "normalized_shape_rms": shape_rms,
        "reduced_chi2_using_observation_sigma": reduced_chi2,
        "sample_count": int(feature_mask.sum()),
        "interpretation": "Resolution-matched spectral-shape similarity is candidate evidence only; this does not identify a species.",
        "limitations": [
            "Observed and reference LSFs are assumed Gaussian.",
            "Laboratory reference uncertainty is not available and is not included.",
            "Shape similarity is not molecular identification or proof of physical origin.",
        ],
    }


def measure_feature_evolution(
    epochs: Sequence[Mapping[str, Any]], feature_interval_um, continuum_intervals_um, *,
    potential_blend_intervals_um: Sequence[Sequence[float]] | None = None,
    blend_intervals_um: Sequence[Sequence[float]] | None = None,
    spectral_resolution_R: float | None = None,
    lsf_fwhm_um: float | None = None,
    line_spread_function: Mapping[str, Any] | None = None,
    continuum_model: str = "linear",
    laboratory_references: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    from chronos_addons.spectral import Spectrum
    from chronos_addons.molecular import measure_equivalent_width
    if not epochs:
        raise ValueError("at least one epoch is required")
    if continuum_model not in {"linear", "constant"}:
        raise ValueError("continuum_model must be linear or constant")
    groups = {str(epoch.get("calibration_group", "")).strip() for epoch in epochs}
    if "" in groups:
        raise ValueError("every epoch needs an explicit calibration_group")
    blends = potential_blend_intervals_um if potential_blend_intervals_um is not None else blend_intervals_um
    output = []
    for index, epoch in enumerate(epochs):
        validate_spectral_epoch(epoch, index=index)
        spectrum = Spectrum(wavelength_um=epoch["wavelength_um"], flux=epoch["flux"],
            sigma=epoch.get("sigma"), valid=epoch.get("valid"), flags=epoch.get("flags"),
            hits=epoch.get("hits"), metadata=dict(epoch.get("metadata") or {}))
        resolution = dict(epoch.get("resolution") or {})
        resolving_power = epoch.get("spectral_resolution_R", spectral_resolution_R)
        fwhm = epoch.get("lsf_fwhm_um", lsf_fwhm_um)
        lsf = epoch.get("line_spread_function", line_spread_function)
        if resolving_power is not None:
            resolution.setdefault("resolving_power", resolving_power)
        if fwhm is not None:
            resolution.setdefault("lsf_fwhm_um", fwhm)
        if lsf is not None:
            resolution.setdefault("line_spread_function", dict(lsf))
            if resolution.get("lsf_fwhm_um") is None and lsf.get("fwhm_um") is not None:
                resolution["lsf_fwhm_um"] = lsf["fwhm_um"]
        if not any(k in resolution for k in ("resolving_power", "lsf_fwhm_um")):
            resolution = None
        epoch_blends = epoch.get("potential_blend_intervals_um", blends)
        kwargs = {"resolution": resolution, "potential_blend_intervals_um": epoch_blends}
        primary = measure_equivalent_width(spectrum, feature_interval_um, continuum_intervals_um,
                                           continuum_model=continuum_model, **kwargs)
        alternate_name = "constant" if continuum_model == "linear" else "linear"
        alternate = measure_equivalent_width(spectrum, feature_interval_um, continuum_intervals_um,
                                             continuum_model=alternate_name, **kwargs)
        rd = primary["resolution_diagnostics"]
        bd = rd.get("blend_diagnostics", {})
        lab_comparisons = [
            _lab_shape_comparison(epoch, primary, reference,
                feature_interval_um, continuum_intervals_um, continuum_model)
            for reference in laboratory_references
        ]
        limitations = list(primary["limitations"])
        if rd.get("status") != "provided":
            limitations.append("No documented instrumental resolution was supplied for this epoch.")
        if bd.get("status") == "possible_blend":
            limitations.append("A predeclared nearby interval may blend with this feature.")
        output.append({
            "epoch_id": str(epoch.get("epoch_id", index)), "mjd": epoch.get("mjd"),
            "calibration_group": str(epoch["calibration_group"]),
            "equivalent_width_um": primary["equivalent_width_um"],
            "equivalent_width_sigma_um": primary["equivalent_width_sigma_um"],
            "equivalent_width_significance": primary["equivalent_width_significance"],
            "feature_depth": primary["feature_depth"],
            "feature_depth_sigma": primary["feature_depth_sigma"],
            "continuum_uncertainty_mean": primary["continuum_uncertainty_mean"],
            "continuum_model": primary["continuum_model"],
            "alternate_continuum_model": alternate["continuum_model"],
            "continuum_model_EW_difference_um": primary["equivalent_width_um"] - alternate["equivalent_width_um"],
            "n_feature_samples": primary["n_feature_samples"],
            "resolution_diagnostics": rd, "blend_diagnostics": bd,
            "laboratory_reference_comparisons": lab_comparisons,
            "candidate_molecular_identification": None,
            "limitations": sorted(set(limitations)),
        })
    return {
        "calibration_group": next(iter(groups)) if len(groups) == 1 else None,
        "calibration_groups": sorted(groups), "epochs": output,
        "feature_interval_um": list(feature_interval_um),
        "continuum_intervals_um": [list(x) for x in continuum_intervals_um],
        "continuum_model_selected": continuum_model,
        "laboratory_reference_count": len(laboratory_references),
        "laboratory_comparison_policy": "Laboratory references are compared only when wavelength/intensity units and documented resolution are compatible; higher-resolution reference spectra are convolved to the observed Gaussian LSF. Similarity is candidate evidence only.",
        "potential_blend_intervals_um": [list(x) for x in blends] if blends else None,
        "feature_tracking_policy": "Calibration group is retained per epoch; no cross-group offset is silently removed.",
        "warning": "A wavelength resemblance or feature track is not a molecular identification. Candidate species require compatible laboratory spectra, calibrated units, matched resolution, supporting features and independent review.",
    }
