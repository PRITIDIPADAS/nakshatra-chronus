"""Track a pre-defined spectral feature across measured epochs."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from chronos_causal.wavelength_gate import validate_spectral_epoch

def measure_feature_evolution(epochs: Sequence[Mapping[str, Any]], feature_interval_um,
                              continuum_intervals_um, *,
                              potential_blend_intervals_um: Sequence[Sequence[float]] | None = None) -> dict[str, Any]:
    from chronos_addons.spectral import Spectrum
    from chronos_addons.molecular import measure_equivalent_width
    if not epochs:
        raise ValueError("at least one epoch is required")
    rows = []
    groups = {str(epoch.get("calibration_group", "")) for epoch in epochs}
    if "" in groups or len(groups) != 1:
        raise ValueError("feature evolution requires one explicit compatible calibration_group across epochs")
    for index, epoch in enumerate(epochs):
        validate_spectral_epoch(epoch, index=index)
        spectrum = Spectrum(
            wavelength_um=epoch["wavelength_um"],
            flux=epoch["flux"],
            sigma=epoch.get("sigma"),
            valid=epoch.get("valid"),
            flags=epoch.get("flags"),
            hits=epoch.get("hits"),
            metadata=dict(epoch.get("metadata") or {}),
        )
        measured = measure_equivalent_width(
            spectrum, feature_interval_um, continuum_intervals_um,
            resolution=epoch.get("resolution"),
            potential_blend_intervals_um=(
                epoch.get("potential_blend_intervals_um")
                if epoch.get("potential_blend_intervals_um") is not None
                else potential_blend_intervals_um
            ),
        )
        rows.append({
            "epoch_id": str(epoch.get("epoch_id", index)),
            "mjd": epoch.get("mjd"),
            "calibration_group": epoch.get("calibration_group"),
            "equivalent_width_um": measured["equivalent_width_um"],
            "equivalent_width_sigma_um": measured["equivalent_width_sigma_um"],
            "equivalent_width_significance": measured["equivalent_width_significance"],
            "n_feature_samples": measured["n_feature_samples"],
            "resolution_diagnostics": measured["resolution_diagnostics"],
            "blend_diagnostics": measured["resolution_diagnostics"]["blend_diagnostics"],
            "limitations": measured["limitations"],
        })
    return {
        "calibration_group": next(iter(groups)),
        "epochs": rows,
        "feature_interval_um": list(feature_interval_um),
        "continuum_intervals_um": [list(x) for x in continuum_intervals_um],
        "potential_blend_intervals_um": (
            [list(x) for x in potential_blend_intervals_um]
            if potential_blend_intervals_um is not None else None
        ),
        "warning": "Tracks a pre-specified band measurement; it does not identify a molecule or establish a physical cause.",
    }
