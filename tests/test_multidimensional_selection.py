import copy
import json

import pytest


def _field_records():
    return [
        {"field_id": f"F{i}", "dataset_class": "real", "independent_field": True,
         "independence_group_id": f"REGION-{i}"}
        for i in range(5)
    ]


def _bin_spec():
    return {
        "edges": {
            "flux_jy": [0.01, 1.0, 10.0],
            "wavelength_um": [2.0, 3.0, 4.0],
            "crowding_index": [0.0, 1.0, 2.0],
            "background_rms": [0.0, 0.5, 1.0],
            "epoch_count": [1, 3, 6],
        },
        "detector_zone_levels": ["center", "middle", "edge"],
    }


def _trials():
    rows = []
    for field_index in range(5):
        for trial_index in range(4):
            rows.append({
                "trial_id": f"F{field_index}-I{trial_index}",
                "field_id": f"F{field_index}",
                "dataset_class": "real",
                "release": "DR1",
                "recovered": trial_index != 0,
                "covariates": {
                    "flux_jy": 0.5, "wavelength_um": 2.5,
                    "crowding_index": 0.4, "background_rms": 0.2,
                    "epoch_count": 4, "detector_zone": "center",
                },
                "method_id": "frozen-chronos-yso-source-detection-v1",
                "processing_config_sha256": "a" * 64,
                "injection_protocol_sha256": "b" * 64,
                "calibration_manifest_sha256": "c" * 64,
            })
    return rows


def test_joint_selection_function_uses_fixed_bins_and_jeffreys_intervals():
    from chronos_population.selection import fit_selection_function, predict_selection_probability

    fitted = fit_selection_function(
        _trials(), _bin_spec(), field_records=_field_records(),
        minimum_trials_per_cell=20, minimum_independent_fields=5,
    )
    assert fitted["supported"] is True
    assert fitted["trial_count"] == 20
    assert fitted["independent_field_count"] == 5
    assert fitted["supported_cell_count"] == 1
    prediction = predict_selection_probability(fitted, {
        "flux_jy": 0.5, "wavelength_um": 2.5,
        "crowding_index": 0.4, "background_rms": 0.2,
        "epoch_count": 4, "detector_zone": "center",
    })
    assert prediction["status"] == "supported"
    assert 0 < prediction["selection_probability"] < 1
    assert prediction["selection_weight"] == pytest.approx(1 / prediction["selection_probability"])
    json.dumps(fitted, allow_nan=False)


def test_selection_function_never_extrapolates_or_borrows_neighboring_detector_zone():
    from chronos_population.selection import fit_selection_function, predict_selection_probability

    fitted = fit_selection_function(
        _trials(), _bin_spec(), field_records=_field_records(),
        minimum_trials_per_cell=20, minimum_independent_fields=5,
    )
    outside = predict_selection_probability(fitted, {
        "flux_jy": 50, "wavelength_um": 2.5,
        "crowding_index": 0.4, "background_rms": 0.2,
        "epoch_count": 4, "detector_zone": "center",
    })
    unknown_zone = predict_selection_probability(fitted, {
        "flux_jy": 0.5, "wavelength_um": 2.5,
        "crowding_index": 0.4, "background_rms": 0.2,
        "epoch_count": 4, "detector_zone": "unregistered-zone",
    })
    assert outside["status"] == "outside_predeclared_support"
    assert unknown_zone["status"] == "outside_predeclared_support"
    assert outside["selection_probability"] is None


def test_selection_function_refuses_sparse_cells_and_mixed_frozen_provenance():
    from chronos_population.selection import fit_selection_function

    sparse = fit_selection_function(
        _trials()[:10], _bin_spec(), field_records=_field_records(),
        minimum_trials_per_cell=20, minimum_independent_fields=5,
    )
    assert sparse["supported"] is False
    mixed = _trials()
    mixed[-1]["processing_config_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="mix frozen provenance"):
        fit_selection_function(mixed, _bin_spec(), field_records=_field_records(),
                               minimum_trials_per_cell=10, minimum_independent_fields=5)


def test_selection_function_requires_independent_real_fields_and_calibration_hashes():
    from chronos_population.selection import fit_selection_function

    fields = _field_records()
    fields[0]["independent_field"] = False
    with pytest.raises(ValueError, match="at least 5 independently attested real fields"):
        fit_selection_function(_trials(), _bin_spec(), field_records=fields,
                               minimum_trials_per_cell=20, minimum_independent_fields=5)
    bad = _trials()
    bad[0]["calibration_manifest_sha256"] = "not-a-digest"
    with pytest.raises(ValueError, match="calibration_manifest_sha256"):
        fit_selection_function(bad, _bin_spec(), field_records=_field_records(),
                               minimum_trials_per_cell=20, minimum_independent_fields=5)


def test_yso_coverage_now_fails_closed_without_a_multidimensional_selection_model():
    from chronos_population.coverage import assess_population_coverage

    result = assess_population_coverage(
        [{"field_id": "SYNTH-FIELD", "dataset_class": "synthetic",
          "independent_field": True, "n_injected": 100, "n_recovered": 90,
          "null_control_id": "SYNTH-NULL", "sources": []}],
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.25, 3.4],
    )
    assert result["eligible_for_predeclared_population_protocol"] is False
    assert result["selection_function"] is None
    assert result["selection_function_error"]
    assert result["failure_counts"]["multidimensional_selection_function_missing_or_unsupported"] == 1
