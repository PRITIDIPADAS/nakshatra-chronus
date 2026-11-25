from __future__ import annotations

import copy
import numpy as np
import pytest


def _real_provenance():
    return {
        "decision": "compatible",
        "compatibility_group": "DR1:D2:7.1:2026-191",
        "science_uri": "https://irsa.ipac.caltech.edu/spherex/dr1/science.fits",
        "science_sha256": "a" * 64,
        "calibration_uri": "https://irsa.ipac.caltech.edu/spherex/dr1/spectral_wcs.fits",
        "calibration_sha256": "b" * 64,
        "native_mef_audit_sha256": "c" * 64,
        "solid_angle_uri": "https://irsa.ipac.caltech.edu/spherex/dr1/solid_angle.fits",
        "solid_angle_sha256": "d" * 64,
        "pixel_valid": True,
    }


def _row():
    return {
        "observation_id": "OBS-001",
        "mjd": 60000.0,
        "wavelength_um": 2.1,
        "wavelength_unit": "um",
        "wavelength_source": "CWAVE/CBAND",
        "wavelength_validated": True,
        "wavelength_provenance": _real_provenance(),
        "calibration_group": "DR1:D2:7.1:2026-191",
        "flux": 12.0,
        "sigma": 0.2,
        "sky_x": 10.0,
        "sky_y": 11.0,
        "sky_sigma": 0.1,
        "detector_x": 100.0,
        "detector_y": 200.0,
        "detector_sigma": 0.2,
        "detector_id": "D2",
    }


def test_causal_schema_accepts_a_hash_linked_cwave_cband_measurement():
    from chronos_causal.schema import normalize_observations
    rows = [_row() | {"observation_id": f"OBS-{i}"} for i in range(3)]
    accepted = normalize_observations(rows)
    assert len(accepted) == 3
    assert accepted[0]["wavelength_source"] == "CWAVE/CBAND"


@pytest.mark.parametrize("source", ["WCS-WAVE", "WCS-W", "band center only", "", "display wavelength"])
def test_causal_schema_rejects_display_or_fallback_wavelengths(source):
    from chronos_causal.schema import normalize_observations
    rows = [_row() | {"observation_id": f"OBS-{i}", "wavelength_source": source}
            for i in range(3)]
    with pytest.raises(ValueError, match="CWAVE/CBAND"):
        normalize_observations(rows)


def test_causal_schema_rejects_unverified_or_mismatched_calibration_provenance():
    from chronos_causal.schema import normalize_observations
    rows = [_row() | {"observation_id": f"OBS-{i}"} for i in range(3)]
    rows[1]["wavelength_provenance"] = copy.deepcopy(_real_provenance())
    rows[1]["wavelength_provenance"]["compatibility_group"] = "DR1:D3:7.1:2026-191"
    with pytest.raises(ValueError, match="calibration_group"):
        normalize_observations(rows)


def test_causal_schema_rejects_a_bad_hash_or_invalid_calibration_pixel():
    from chronos_causal.schema import normalize_observations
    bad_hash = [_row() | {"observation_id": f"OBS-{i}"} for i in range(3)]
    bad_hash[0]["wavelength_provenance"]["calibration_sha256"] = "not-a-hash"
    with pytest.raises(ValueError, match="calibration_sha256"):
        normalize_observations(bad_hash)

    invalid_pixel = [_row() | {"observation_id": f"OBS-{i}"} for i in range(3)]
    invalid_pixel[0]["wavelength_provenance"]["pixel_valid"] = False
    with pytest.raises(ValueError, match="invalid in CWAVE/CBAND"):
        normalize_observations(invalid_pixel)


def test_synthetic_benchmark_rows_are_explicitly_labelled_and_still_admitted():
    from chronos_benchmark.scenarios import generate_scenario
    from chronos_causal.schema import normalize_observations
    fixture = generate_scenario("achromatic_variable", seed=42, n_observations=10)
    assert fixture["data_class"] == "synthetic measurement-level fixture"
    assert all(row["wavelength_source"] == "synthetic_fixture" for row in fixture["observations"])
    assert len(normalize_observations(fixture["observations"])) == 10


def test_spectral_reconstruction_rejects_unverified_or_display_grade_wavelengths():
    from chronos_spectrotemporal.reconstruction import reconstruct
    sample = {
        "mjd": 60000.0, "wavelength_um": 2.1, "flux": 10.0, "sigma": 0.3,
        "calibration_group": "DR1:D2:7.1:2026-191",
        "wavelength_source": "WCS-WAVE", "wavelength_unit": "um",
        "wavelength_validated": True,
    }
    with pytest.raises(ValueError, match="CWAVE/CBAND"):
        reconstruct([sample], [2.1], [60000.0], wavelength_bandwidth_um=0.1,
                    time_bandwidth_days=1.0, min_neighbors=1)


def test_feature_evolution_rejects_unverified_wavelength_arrays():
    from chronos_spectrotemporal.feature_evolution import measure_feature_evolution
    epoch = {
        "epoch_id": "E1", "mjd": 60000.0,
        "wavelength_um": [1.0, 1.1, 1.2], "flux": [10.0, 9.0, 10.0],
        "sigma": [0.2, 0.2, 0.2], "valid": [True, True, True],
        "calibration_group": "DR1:D2:7.1:2026-191",
        "wavelength_source": "WCS-WAVE", "wavelength_unit": "um",
        "wavelength_validated": True,
    }
    with pytest.raises(ValueError, match="CWAVE/CBAND"):
        measure_feature_evolution([epoch], [1.05, 1.15], [[1.0, 1.02], [1.18, 1.2]])


def test_spectral_epoch_rejects_valid_pixels_with_nan_wavelengths():
    from chronos_causal.wavelength_gate import validate_spectral_epoch
    epoch = {
        "wavelength_um": [1.0, float("nan"), 1.2],
        "flux": [1.0, 1.0, 1.0],
        "valid": [True, True, True],
        "wavelength_unit": "um", "wavelength_source": "CWAVE/CBAND",
        "wavelength_validated": True, "calibration_group": "DR1:D2:7.1:2026-191",
        "wavelength_provenance": _real_provenance(),
    }
    with pytest.raises(ValueError, match="finite and positive"):
        validate_spectral_epoch(epoch, index=0)
    epoch["wavelength_um"][1] = float("inf")
    with pytest.raises(ValueError, match="finite and positive"):
        validate_spectral_epoch(epoch, index=0)


def test_spectral_epoch_allows_masked_invalid_wavelength_pixels():
    from chronos_causal.wavelength_gate import validate_spectral_epoch
    epoch = {
        "wavelength_um": [1.0, float("nan"), 1.2],
        "flux": [1.0, float("nan"), 1.0],
        "valid": [True, False, True],
        "wavelength_unit": "um", "wavelength_source": "CWAVE/CBAND",
        "wavelength_validated": True, "calibration_group": "DR1:D2:7.1:2026-191",
        "wavelength_provenance": _real_provenance(),
    }
    validate_spectral_epoch(epoch, index=0)
