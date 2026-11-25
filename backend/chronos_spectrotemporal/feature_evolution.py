"""Track a pre-defined spectral feature across measured epochs."""
from __future__ import annotations
from typing import Any, Mapping, Sequence

def measure_feature_evolution(epochs: Sequence[Mapping[str, Any]], feature_interval_um,
                              continuum_intervals_um) -> dict[str, Any]:
    from chronos_addons.spectral import Spectrum
    from chronos_addons.molecular import measure_equivalent_width
    if not epochs:
        raise ValueError("at least one epoch is required")
    rows = []
    for index, epoch in enumerate(epochs):
        spectrum = Spectrum(
            wavelength_um=epoch["wavelength_um"],
            flux=epoch["flux"],
            sigma=epoch.get("sigma"),
            valid=epoch.get("valid"),
            flags=epoch.get("flags"),
            hits=epoch.get("hits"),
            metadata=dict(epoch.get("metadata") or {}),
        )
        measured = measure_equivalent_width(spectrum, feature_interval_um, continuum_intervals_um)
        rows.append({
            "epoch_id": str(epoch.get("epoch_id", index)),
            "mjd": epoch.get("mjd"),
            "calibration_group": epoch.get("calibration_group"),
            "equivalent_width_um": measured["equivalent_width_um"],
            "equivalent_width_sigma_um": measured["equivalent_width_sigma_um"],
            "equivalent_width_significance": measured["equivalent_width_significance"],
            "n_feature_samples": measured["n_feature_samples"],
            "limitations": measured["limitations"],
        })
    return {
        "epochs": rows,
        "feature_interval_um": list(feature_interval_um),
        "continuum_intervals_um": [list(x) for x in continuum_intervals_um],
        "warning": "Tracks a pre-specified band measurement; it does not identify a molecule or establish a physical cause.",
    }
