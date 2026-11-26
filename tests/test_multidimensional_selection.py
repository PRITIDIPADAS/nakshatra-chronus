import copy
import json

import pytest


_TEST_CUSTODIAN_SEED = bytes.fromhex("5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a")
_TEST_CUSTODIAN_KEY_ID = "unit-test-independent-field-custodian-v1"


def _test_private_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(_TEST_CUSTODIAN_SEED)


def _sign_test_field(field, index, *, footprint=None):
    import base64, hashlib, os
    from cryptography.hazmat.primitives import serialization
    from chronos_population.independence import FIELD_INDEPENDENCE_SCHEMA, canonical_field_independence_payload
    key = _test_private_key()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    os.environ["CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_KEY_ID"] = _TEST_CUSTODIAN_KEY_ID
    os.environ["CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_PUBLIC_KEY_B64"] = base64.b64encode(public).decode("ascii")
    os.environ["CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_ID"] = "test-independent-custodian"
    os.environ["CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_OUT_OF_BAND_INDEPENDENCE_VERIFIED"] = "true"
    fid = str(field["field_id"])
    group = str(field.get("independence_group_id") or f"REGION-{index}")
    field["independence_group_id"] = group
    field["release"] = str(field.get("release") or "DR1")
    field["science_manifest_sha256"] = hashlib.sha256(f"test-manifest:{fid}".encode()).hexdigest()
    field["preregistration_sha256"] = "d" * 64
    footprint = dict(footprint or {"center_ra_deg": float(index*15), "center_dec_deg": -20.0, "maximum_radius_deg": 0.5})
    field["footprint"] = footprint
    fp_sha = hashlib.sha256(canonical_field_independence_payload(footprint)).hexdigest()
    field["footprint_sha256"] = fp_sha
    payload = {
        "schema": FIELD_INDEPENDENCE_SCHEMA, "field_id": fid,
        "dataset_class": str(field.get("dataset_class", "real")), "release": field["release"],
        "independence_group_id": group, "footprint": footprint, "footprint_sha256": fp_sha,
        "science_manifest_sha256": field["science_manifest_sha256"],
        "preregistration_sha256": field["preregistration_sha256"],
        "custodian_id": "test-independent-custodian", "custodian_role": "independent_custodian",
        "custodian_independent_of_analysis_team": True,
        "attested_utc": "2026-11-26T00:00:00Z",
    }
    field["field_independence_attestation"] = {
        "schema": FIELD_INDEPENDENCE_SCHEMA, "algorithm": "Ed25519", "key_id": _TEST_CUSTODIAN_KEY_ID,
        "payload": payload,
        "signature_base64": base64.b64encode(key.sign(canonical_field_independence_payload(payload))).decode("ascii"),
    }




def _field_records():
    fields = [
        {"field_id": f"F{i}", "dataset_class": "real", "independent_field": True,
         "independence_group_id": f"REGION-{i}"}
        for i in range(5)
    ]
    for i, field in enumerate(fields):
        _sign_test_field(field, i)
    return fields


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
    from chronos_population.selection import (
        RECOVERY_RULE_ID, RECOVERY_RULE_SHA256, _canonical_sha256,
    )

    rows = []
    quality_policy = {
        "policy_id": "test-quality-policy-v1",
        "flag_policy": "photometry",
        "fit_ql_max": 1.0,
        "max_abs_background_to_flux_ratio": 0.2,
    }
    quality_policy_sha256 = _canonical_sha256(quality_policy)
    for field_index in range(5):
        for trial_index in range(4):
            recovered = trial_index != 0
            evidence = {
                "rule_id": RECOVERY_RULE_ID,
                "detector_output_sha256": "e" * 64,
                "injection_truth_sha256": "f" * 64,
                "image_id": f"IMAGE-{field_index}",
                "peak_snr": 6.0 if recovered else 4.0,
                "threshold_sigma": 5.0,
                "separation_pixels": 1.0 if recovered else 3.0,
                "match_radius_pixels": 2.0,
                "fit_ql": 0.5,
                "fit_ql_max": quality_policy["fit_ql_max"],
                "background_fraction": 0.1,
                "background_fraction_max": quality_policy["max_abs_background_to_flux_ratio"],
                "flags": 0,
                "peak_is_local_maximum": recovered,
                "one_to_one_assignment": recovered,
                "primary_selection_rule_passed": recovered,
                "fit_quality_pass": True,
                "background_quality_pass": True,
                "photometry_flags_pass": True,
                "peak_id": f"PEAK-{field_index}-{trial_index}" if recovered else None,
                "injected_xy": [100.0, 100.0],
                "peak_xy": [101.0, 100.0] if recovered else [103.0, 100.0],
            }
            rows.append({
                "trial_id": f"F{field_index}-I{trial_index}",
                "field_id": f"F{field_index}",
                "dataset_class": "real",
                "release": "DR1",
                "recovered": recovered,
                "covariates": {
                    "flux_jy": 0.5, "wavelength_um": 2.5,
                    "crowding_index": 0.4, "background_rms": 0.2,
                    "epoch_count": 4, "detector_zone": "center",
                },
                "method_id": "frozen-chronos-yso-source-detection-v1",
                "processing_config_sha256": "a" * 64,
                "injection_protocol_sha256": "b" * 64,
                "calibration_manifest_sha256": "c" * 64,
                "preregistration_sha256": "d" * 64,
                "recovery_rule_sha256": RECOVERY_RULE_SHA256,
                "quality_policy": dict(quality_policy),
                "quality_policy_sha256": quality_policy_sha256,
                "recovery_evidence": evidence,
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
        _trials()[::2], _bin_spec(), field_records=_field_records(),
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
    with pytest.raises(ValueError, match="independent_field must be true"):
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



def test_source_linked_yso_event_yield_revalidates_source_rows_and_selection_trials():
    from chronos_population.coverage import assess_population_coverage
    from chronos_population.source_linked import estimate_source_linked_event_yield

    preregistration = "d" * 64
    event_definition = "9" * 64
    fields = []
    for field_index in range(5):
        observations = []
        for epoch_index, mjd in enumerate((60000.0, 60002.0, 60004.0)):
            for band_index, wavelength in enumerate((2.9, 3.1, 3.3)):
                observations.append({
                    "measurement_id": f"M-{field_index}-{epoch_index}-{band_index}",
                    "observation_id": f"OBS-{field_index}-{epoch_index}",
                    "mjd": mjd,
                    "wavelength_um": wavelength,
                    "flux": 10.0,
                    "sigma": 0.5,
                    "flux_unit": "Jy",
                    "calibration_group": f"SYNTHETIC-CAL-{field_index}",
                    "wavelength_source": "synthetic_fixture",
                    "wavelength_unit": "um",
                    "wavelength_validated": True,
                    "synthetic_fixture": True,
                    "valid": True,
                })
        fields.append({
            "field_id": f"F{field_index}",
            "dataset_class": "real",
            "independent_field": True,
            "independence_group_id": f"REGION-{field_index}",
            "n_injected": 4,
            "n_recovered": 3,
            "null_control_id": f"NULL-{field_index}",
            "area_deg2": 1.0,
            "baseline_days": 4.0,
            "null_control_area_deg2": 1.0,
            "null_control_baseline_days": 4.0,
            "null_control_to_science_exposure_ratio": 1.0,
            "null_events": 0,
            "observed_events": 1 if field_index == 0 else 0,
            "sources": [{
                "source_id": f"YSO-{field_index}",
                "sample_class": "young_stellar_object",
                "classification_reference": f"https://catalogue.example/YSO-{field_index}",
                "selection_covariates": {
                    "flux_jy": 0.5, "wavelength_um": 2.5,
                    "crowding_index": 0.4, "background_rms": 0.2,
                    "epoch_count": 4, "detector_zone": "center",
                },
                "observations": observations,
            }],
        })

    trials = _trials()
    for trial in trials:
        trial["event_definition_sha256"] = event_definition

    coverage = assess_population_coverage(
        fields,
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.25, 3.4],
        selection_trials=trials,
        selection_bin_spec=_bin_spec(),
        minimum_independent_fields=5,
        minimum_trials_per_selection_cell=20,
        minimum_fields_per_cell=5,
        minimum_completeness=0.5,
    )
    assert coverage["eligible_for_predeclared_population_protocol"] is True
    eligible = next(row for row in coverage["eligible_sources"] if row["source_id"] == "YSO-0")
    assert len(eligible["measurement_lineage"]) == 9

    # A source sample without immutable measurement IDs cannot be used to
    # create event records, even when its aggregate epoch/wavelength counts fit.
    missing_id_fields = copy.deepcopy(fields)
    missing_id_fields[0]["sources"][0]["observations"][0].pop("measurement_id")
    missing_id_coverage = assess_population_coverage(
        missing_id_fields,
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.25, 3.4],
        selection_trials=trials,
        selection_bin_spec=_bin_spec(),
        minimum_independent_fields=5,
        minimum_trials_per_selection_cell=20,
        minimum_fields_per_cell=5,
        minimum_completeness=0.5,
    )
    missing_id_source = next(
        row for field in missing_id_coverage["fields"] if field["field_id"] == "F0"
        for row in field["sources"] if row["source_id"] == "YSO-0"
    )
    assert missing_id_source["eligible"] is False
    assert "invalid_or_unverified_measurement" in missing_id_source["reasons"]

    feature_measurements = [
        f"M-0-{epoch_index}-1" for epoch_index in range(3)
    ]
    event = {
        "event_id": "EVENT-YSO-0-1",
        "field_id": "F0",
        "source_id": "YSO-0",
        "status": "accepted",
        "preregistration_sha256": preregistration,
        "event_definition_sha256": event_definition,
        "event_evidence_uri": "https://example.org/event-evidence/EVENT-YSO-0-1.json",
        "event_evidence_sha256": "e" * 64,
        "classifier_version": "frozen-ysovar-event-rule/1.0",
        "start_mjd": 60000.0,
        "end_mjd": 60004.0,
        "measurement_ids": feature_measurements,
    }
    result = estimate_source_linked_event_yield(
        fields,
        coverage_audit=coverage,
        selection_trials=trials,
        selection_bin_spec=_bin_spec(),
        source_event_records=[event],
        preregistration_sha256=preregistration,
        event_definition_sha256=event_definition,
        draws=2000,
        seed=13,
    )
    assert result["scientific_status"] == "source_selection_weighted_candidate_event_yield_not_population_result"
    assert result["accepted_event_count"] == 1
    assert result["total_source_selection_weighted_event_count"] > 1.0
    assert result["coverage_revalidated"] is True



def test_selection_function_requires_out_of_band_pinned_custodian_key(monkeypatch):
    from chronos_population.selection import fit_selection_function
    fields = _field_records()
    monkeypatch.delenv("CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_KEY_ID", raising=False)
    monkeypatch.delenv("CHRONOS_FIELD_INDEPENDENCE_ATTESTATION_PUBLIC_KEY_B64", raising=False)
    with pytest.raises(ValueError, match="trusted external field-independence custodian"):
        fit_selection_function(_trials(), _bin_spec(), field_records=fields,
                               minimum_trials_per_cell=20, minimum_independent_fields=5)


def test_selection_function_rejects_tampered_custodian_field_identity():
    from chronos_population.selection import fit_selection_function
    fields = _field_records()
    fields[0]["field_independence_attestation"]["payload"]["independence_group_id"] = "FORGED-GROUP"
    with pytest.raises(ValueError, match="signed custodian payload does not match field record"):
        fit_selection_function(_trials(), _bin_spec(), field_records=fields,
                               minimum_trials_per_cell=20, minimum_independent_fields=5)


def test_selection_function_rejects_overlapping_signed_independent_footprints():
    from chronos_population.selection import fit_selection_function
    fields = _field_records()
    _sign_test_field(fields[1], 1, footprint={
        "center_ra_deg": 0.0, "center_dec_deg": -20.0, "maximum_radius_deg": 0.5,
    })
    with pytest.raises(ValueError, match="overlap or cannot be proven disjoint"):
        fit_selection_function(_trials(), _bin_spec(), field_records=fields,
                               minimum_trials_per_cell=20, minimum_independent_fields=5)


def test_selection_function_requires_out_of_band_custodian_identity_and_independence_pins(monkeypatch):
    from chronos_population.selection import fit_selection_function
    fields = _field_records()

    monkeypatch.setenv("CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_ID", "different-custodian")
    with pytest.raises(ValueError, match="signed custodian identity does not match"):
        fit_selection_function(_trials(), _bin_spec(), field_records=fields,
                               minimum_trials_per_cell=20, minimum_independent_fields=5)

    fields = _field_records()
    monkeypatch.delenv("CHRONOS_FIELD_INDEPENDENCE_CUSTODIAN_OUT_OF_BAND_INDEPENDENCE_VERIFIED")
    with pytest.raises(ValueError, match="confirmed out-of-band"):
        fit_selection_function(_trials(), _bin_spec(), field_records=fields,
                               minimum_trials_per_cell=20, minimum_independent_fields=5)


def test_field_independence_signature_requires_custodian_independence_attestation():
    from chronos_population.independence import verify_field_independence_attestation
    fields = _field_records()
    fields[0]["field_independence_attestation"]["payload"]["custodian_independent_of_analysis_team"] = False
    with pytest.raises(ValueError, match="did not attest independence"):
        verify_field_independence_attestation(fields[0])
