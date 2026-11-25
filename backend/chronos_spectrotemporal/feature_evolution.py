"""Resolution-aware, predeclared spectral-feature evolution."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from chronos_causal.wavelength_gate import validate_spectral_epoch


def measure_feature_evolution(
    epochs: Sequence[Mapping[str, Any]], feature_interval_um, continuum_intervals_um, *,
    potential_blend_intervals_um: Sequence[Sequence[float]] | None = None,
    blend_intervals_um: Sequence[Sequence[float]] | None = None,
    spectral_resolution_R: float | None = None,
    lsf_fwhm_um: float | None = None,
    line_spread_function: Mapping[str, Any] | None = None,
    continuum_model: str = "linear",
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
            "candidate_molecular_identification": None,
            "limitations": sorted(set(limitations)),
        })
    return {
        "calibration_group": next(iter(groups)) if len(groups) == 1 else None,
        "calibration_groups": sorted(groups), "epochs": output,
        "feature_interval_um": list(feature_interval_um),
        "continuum_intervals_um": [list(x) for x in continuum_intervals_um],
        "continuum_model_selected": continuum_model,
        "potential_blend_intervals_um": [list(x) for x in blends] if blends else None,
        "feature_tracking_policy": "Calibration group is retained per epoch; no cross-group offset is silently removed.",
        "warning": "A wavelength resemblance or feature track is not a molecular identification. Candidate species require compatible laboratory spectra, calibrated units, matched resolution, supporting features and independent review.",
    }
