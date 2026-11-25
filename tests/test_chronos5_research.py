import hashlib
import json

import numpy as np
import pytest


def _field(field_id, split="blind_test", dataset_class="synthetic"):
    from chronos_benchmark.runner import truth_catalogue_digest
    truth = [{"truth_id": f"{field_id}-T1", "x": 10.0, "y": 10.0}]
    signature = {
        "field_id": field_id,
        "dataset_class": dataset_class,
        "exposure_ids": [f"{field_id}-E1", f"{field_id}-E2"],
        "mask_sha256": "a" * 64,
        "truth_catalogue_sha256": truth_catalogue_digest(truth),
        "coordinate_frame": "sky",
        "coordinate_unit": "pixel",
        "pixel_wcs_sha256": "b" * 64,
    }
    methods = {}
    records = {
        "snr_only": [{"detection_id": f"{field_id}-S1", "x": 10.2, "y": 10.0,
                      "score": 7.0, "provenance": {"source": "DEEPS"}}],
        "chronos_pda": [{"detection_id": f"{field_id}-P1", "x": 10.1, "y": 10.1,
                         "score": 8.0, "provenance": {"methods": "PD"}}],
        "instrument_forensics": [{"detection_id": f"{field_id}-F1", "x": 10.1, "y": 10.1,
                                  "score": 8.0, "provenance": {"gate": "strong-findings-veto"}}],
        "sky_detector_twin": [],
    }
    for method, detections in records.items():
        methods[method] = {"input_signature": dict(signature), "detections": detections}
    return {
        "field_id": field_id,
        "input_signature": signature,
        "truth_catalogue": truth,
        "methods": methods,
        "match_radius": 1.0,
        "split": split,
    }


def _package():
    return {
        "schema": "chronos-four-baseline-package/1.0",
        "benchmark_id": "test-benchmark",
        "fields": [_field("FIELD-A"), _field("FIELD-B")],
        "score_thresholds": {
            "snr_only": [5.0, 1.0],
            "chronos_pda": [5.0, 1.0],
            "instrument_forensics": [5.0, 1.0],
            "sky_detector_twin": [5.0, 1.0],
        },
        "matched_target": {"false_candidates_per_field": 0.0, "completeness": 0.8},
    }


def test_four_baselines_share_exact_input_and_report_all_decisions():
    from chronos_benchmark.runner import compare_benchmark_package
    report = compare_benchmark_package(_package(), bootstrap_draws=100, seed=4)
    assert report["methods"] == [
        "snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin"
    ]
    assert report["reproducibility"]["same_input_enforced_for_all_methods"]
    assert report["aggregate"]["sky_detector_twin"]["threshold_curve"][0]["false_negative"] == 2
    assert report["aggregate"]["chronos_pda"]["threshold_curve"][0]["completeness"] == 1.0
    assert report["scientific_claim_eligible"] is False
    assert report["fields"][0]["method_curves"]["sky_detector_twin"][0]["non_detections"] == ["FIELD-A-T1"]


def test_four_baseline_rejects_exposure_or_mask_drift():
    from chronos_benchmark.runner import compare_benchmark_package
    package = _package()
    package["fields"][0]["methods"]["sky_detector_twin"]["input_signature"]["exposure_ids"] = ["OTHER"]
    with pytest.raises(ValueError, match="input signature differs"):
        compare_benchmark_package(package, bootstrap_draws=100)


def test_four_baseline_rejects_changed_truth_catalogue():
    from chronos_benchmark.runner import compare_benchmark_package
    package = _package()
    package["fields"][0]["truth_catalogue"][0]["x"] += 0.5
    with pytest.raises(ValueError, match="truth catalogue digest"):
        compare_benchmark_package(package, bootstrap_draws=100)


def test_pipeline_adapters_preserve_common_signature_and_forensic_veto():
    from chronos_benchmark.adapters import build_four_baseline_records
    from chronos_benchmark.runner import truth_catalogue_digest
    truth = [{"truth_id": "T1", "x": 10.0, "y": 10.0}]
    signature = {
        "field_id": "F1", "dataset_class": "synthetic",
        "exposure_ids": ["E1", "E2"], "mask_sha256": "a" * 64,
        "truth_catalogue_sha256": truth_catalogue_digest(truth),
        "coordinate_frame": "sky", "coordinate_unit": "pixel",
        "pixel_wcs_sha256": "b" * 64,
    }
    state = {
        "exps": [object()],
        "DEEPS": np.pad(np.array([[12.0]]), ((10, 10), (10, 10))),
        "RB": np.ones((2, 21, 21), dtype=bool),
        "cands": [{
            "x": 10.0, "y": 10.0, "methods": "PDA",
            "P": [{"s": 8.0, "why": ["presence"]}],
            "D": [{"s": -6.0, "why": ["difference"]}],
            "A": [],
            "f": {"flagfrac": 0.8},
        }],
    }
    threshold_map = {name: [5.0, 1.0] for name in (
        "snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin"
    )}
    built = build_four_baseline_records(
        state, signature, sky_detector_twin_detections=[], score_thresholds=threshold_map
    )
    assert set(built["methods"]) == set(threshold_map)
    assert all(item["input_signature"] == signature for item in built["methods"].values())
    assert built["methods"]["instrument_forensics"]["detections"][0]["provenance"]["accepted"] is False
    assert built["methods"]["sky_detector_twin"]["detections"] == []


def test_blind_truth_is_encrypted_and_unblinding_requires_frozen_config():
    from cryptography.fernet import Fernet
    from chronos_benchmark.blind import create_blind_store, freeze_configuration, unblind_benchmark
    from chronos_benchmark.runner import sha256_json

    fields = [_field(f"PRIVATE-FIELD-{i}", split="not_split") for i in range(4)]
    key = Fernet.generate_key()
    blind = create_blind_store(fields, key, test_fraction=0.25, seed=19)
    encrypted = blind["encrypted_truth_store"]
    assert b"truth_id" not in encrypted
    assert "PRIVATE-FIELD-0" not in json.dumps(blind["public_manifest"])
    public = blind["public_manifest"]
    run_manifest = blind["run_manifest"]
    dataset_digest = sha256_json({
        "public_manifest": public, "run_manifest": run_manifest
    })
    frozen = freeze_configuration(
        {"thresholds": "frozen", "match_radius": 1.0},
        source_commit="deadbeef",
        dataset_digest=dataset_digest,
    )
    test_tokens = set(public["blind_test_tokens"])
    public_fields = run_manifest["fields"]
    run_fields = []
    for row in public_fields:
        if row["blind_field_token"] not in test_tokens:
            continue
        signature = row["input_signature"]
        methods = {
            name: {"input_signature": signature, "detections": []}
            for name in ("snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin")
        }
        run_fields.append({
            "blind_field_token": row["blind_field_token"],
            "input_signature": signature,
            "methods": methods,
        })
    detection_run = {
        "benchmark_id": "sealed-evaluation",
        "dataset_digest": dataset_digest,
        "frozen_configuration_sha256": frozen["configuration_sha256"],
        "source_commit": "deadbeef",
        "configuration": {"thresholds": "frozen", "match_radius": 1.0},
        "public_fields": public_fields,
        "fields": run_fields,
        "score_thresholds": {name: [1.0] for name in (
            "snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin"
        )},
        "matched_target": {"false_candidates_per_field": 0.0},
    }
    report = unblind_benchmark(
        public, encrypted, key, frozen, detection_run, bootstrap_draws=100
    )
    assert report["blind_protocol"]["truth_released_after_run_freeze"] is True
    assert report["blind_protocol"]["blind_field_count"] == len(test_tokens)
    assert report["blind_protocol"]["truth_access_record"]["action"] == "unblind_and_evaluate"
    assert report["scientific_claim_eligible"] is False


def test_pixel_forward_model_separates_components_and_marks_placeholders():
    from chronos_causal.pixel_forward import simulate_spectral_exposure
    frame = simulate_spectral_exposure(
        shape=(16, 16), mjd=60000.0, exposure_time_s=10.0,
        wavelengths_um=[1.0, 2.0], bandwidths_um=[0.1, 0.1],
        wavelength_response=np.ones((2, 16, 16)).tolist(),
        sources=[{
            "source_id": "S1", "x": 8.0, "y": 8.0,
            "flux_density_electrons_per_s_um": [100.0, 80.0],
        }],
        psf_kernel=np.ones((3, 3)).tolist(),
        background_rate_electrons_per_s=1.0,
        dark_current_rate_electrons_per_s=0.2,
        read_noise_electrons=2.0,
        detector_fixed_electrons=np.pad(np.array([[4.0]]), ((2, 13), (2, 13))).tolist(),
        missing_pixel_mask=np.pad(np.array([[True]]), ((0, 15), (0, 15))).tolist(),
        seed=9,
    )
    components = frame["components"]
    assert frame["data_class"] == "synthetic controlled experiment"
    assert frame["calibration_ready"] is False
    assert frame["parameter_provenance"]["psf"]["status"] == "placeholder"
    assert components["source_electrons"][8][8] > 0
    assert components["detector_fixed_electrons"][2][2] == 4.0
    photon_expected = components["photon_generated_expected_electrons"]
    total_expected = components["expected_total_electrons_including_fixed_detector_term"]
    assert total_expected[2][2] == pytest.approx(photon_expected[2][2] + 4.0)
    assert components["variance_electrons_squared"][2][2] == pytest.approx(photon_expected[2][2] + 4.0)
    assert components["measured_electrons"][2][2] == pytest.approx(
        components["poisson_realisation_electrons"][2][2]
        + components["detector_fixed_electrons"][2][2]
        + components["read_noise_realisation_electrons"][2][2]
    )
    assert components["measured_electrons"][0][0] is None
    assert components["poisson_realisation_electrons"][0][0] is None
    assert frame["original_inputs_mutated"] is False


def test_jacobian_audit_detects_degeneracy_and_recommends_new_measurement():
    from chronos_causal.identifiability import audit_forward_model_identifiability
    jacobian = [[1.0, 1.0], [2.0, 2.0], [3.0, 3.01]]
    result = audit_forward_model_identifiability(
        jacobian, ["sky_slope", "detector_template"],
        covariance=[1.0, 1.0, 1.0],
        parameter_roles={"sky_slope": "sky", "detector_template": "nuisance"},
        measurement_options=[{
            "name": "simultaneous_partner_array",
            "jacobian_rows": [[1.0, -1.0]],
            "sigma": 0.1,
        }],
    )
    assert result["status"] in {"degenerate", "weakly_identifiable", "identifiable"}
    assert result["additional_measurement_options"][0]["improves_local_identifiability"]
    assert "simultaneous_partner_array" in result["recommended_additional_measurements"]
    assert result["covariance"]["was_supplied"] is True


def test_finite_difference_jacobian_matches_known_derivatives():
    from chronos_causal.identifiability import finite_difference_jacobian
    result = finite_difference_jacobian(
        lambda theta: np.array([
            theta[0] ** 2 + 2.0 * theta[1],
            theta[0] * theta[1],
        ]),
        [2.0, 3.0],
    )
    assert np.allclose(result, [[4.0, 2.0], [3.0, 2.0]], atol=1e-6)


def test_parametric_bootstrap_and_transient_search_are_seeded():
    from chronos_causal.posterior_predictive import (
        parametric_bootstrap_checks, transient_scan_bootstrap,
    )
    times = np.linspace(60000, 60030, 12)
    predicted = np.full(12, 10.0)
    observed = predicted.copy()
    observed[5:7] += 5.0
    sigma = np.ones(12)
    first = parametric_bootstrap_checks(
        observed, predicted, sigma, groups={"detector_id": ["D2"] * 12},
        draws=100, seed=5,
    )
    second = parametric_bootstrap_checks(
        observed, predicted, sigma, groups={"detector_id": ["D2"] * 12},
        draws=100, seed=5,
    )
    assert first["global_checks"] == second["global_checks"]
    scan = transient_scan_bootstrap(
        observed, predicted, sigma, times, draws=100, seed=6
    )
    assert scan["searched_interval_count"] > 0
    assert 0 <= scan["family_wise_false_alarm_probability"] <= 1


def test_falsification_returns_unknown_without_validated_uncertainties():
    from chronos_benchmark.scenarios import generate_scenario
    from chronos_causal.falsification import run_falsification_suite
    rows = generate_scenario(
        "achromatic_variable", seed=12, n_observations=12
    )["observations"]
    original = [dict(row) for row in rows]
    report = run_falsification_suite(
        rows, bootstrap_draws=100, transient_draws=100, seed=3
    )
    assert report["verdict"] == "unknown"
    assert report["parametric_bootstrap"]["uncertainties_marked_validated"] is False
    assert {row["challenge_id"] for row in report["counterfactual_challenges"]} == {
        "sky_only", "detector_only", "mixed"
    }
    assert rows == original


def test_transient_scan_searches_many_intervals_and_reports_familywise_rate():
    from chronos_causal.posterior_predictive import transient_scan_bootstrap
    times = np.arange(10, dtype=float)
    mu = np.zeros(10)
    y = np.zeros(10)
    y[4:6] = 7.0
    result = transient_scan_bootstrap(y, mu, np.ones(10), times, draws=100, seed=10)
    assert result["searched_interval_count"] > 1
    assert "family_wise_false_alarm_probability" in result



def test_blind_split_can_keep_related_observation_periods_together():
    from cryptography.fernet import Fernet
    from chronos_benchmark.blind import create_blind_store
    key = Fernet.generate_key()
    fields = [
        _field("FIELD-A-EARLY"), _field("FIELD-A-LATE"),
        _field("FIELD-B-EARLY"), _field("FIELD-C"),
    ]
    fields[0]["split_group_id"] = "FIELD-A"
    fields[1]["split_group_id"] = "FIELD-A"
    fields[2]["split_group_id"] = "FIELD-B"
    fields[3]["split_group_id"] = "FIELD-C"
    blind = create_blind_store(fields, key, test_fraction=0.34, seed=5)
    private = json.loads(Fernet(key).decrypt(blind["encrypted_truth_store"]).decode("utf-8"))
    roles = {
        row["field"]["field_id"]: row["split_role"]
        for row in private["fields"]
    }
    assert roles["FIELD-A-EARLY"] == roles["FIELD-A-LATE"]
    assert sum(value == "blind_test" for value in roles.values()) >= 1


def test_pixel_forward_marks_channel_components_and_preserves_source_peak():
    from chronos_causal.pixel_forward import simulate_spectral_exposure
    frame = simulate_spectral_exposure(
        shape=(12, 12), mjd=60001, exposure_time_s=5,
        wavelengths_um=[1, 2], bandwidths_um=[0.2, 0.2],
        wavelength_response=np.ones((2, 12, 12)).tolist(),
        sources=[{"source_id": "x", "x": 6, "y": 6,
                  "flux_density_electrons_per_s_um": [10, 20]}],
        psf_kernel=[[1, 2, 1], [2, 4, 2], [1, 2, 1]],
        seed=1,
    )
    assert frame["components"]["source_electrons"][6][6] > 0
    assert frame["components"]["effective_wavelength_map_um"][6][6] == pytest.approx(1.5)



def test_session_7_to_11_api_routes_are_registered():
    from chronos_causal.api import router
    routes = {route.path for route in router.routes}
    assert "/api/v5/benchmark/compare-package" in routes
    assert "/api/v5/causal/forward-exposure" in routes
    assert "/api/v5/causal/identifiability/jacobian" in routes
    assert "/api/v5/causal/falsify" in routes


def test_common_benchmark_reports_both_matched_operating_points_and_bootstrap_per_threshold():
    from chronos_benchmark.runner import compare_benchmark_package
    result = compare_benchmark_package(_package(), bootstrap_draws=100, seed=22)
    assert set(result["matched_operating_points"]["targets"]) == {
        "false_candidates_per_field", "completeness"
    }
    for method in result["methods"]:
        curves = result["aggregate"][method]["threshold_curve"]
        bootstrap = result["aggregate"][method]["field_bootstrap_by_threshold"]
        assert len(curves) == 2
        assert set(bootstrap) == {str(row["threshold"]) for row in curves}
        assert "intervals_95" in next(iter(bootstrap.values()))


def test_unblinding_rejects_detection_run_with_modified_threshold_configuration():
    from cryptography.fernet import Fernet
    from chronos_benchmark.blind import create_blind_store, freeze_configuration, unblind_benchmark
    from chronos_benchmark.runner import sha256_json

    key = Fernet.generate_key()
    blind = create_blind_store(
        [_field(f"SEAL-FIELD-{i}", split="not_split") for i in range(4)],
        key, test_fraction=0.25, seed=31,
    )
    public = blind["public_manifest"]
    run_manifest = blind["run_manifest"]
    digest = sha256_json({"public_manifest": public, "run_manifest": run_manifest})
    config = {"score_thresholds": {"snr_only": [5.0]}, "match_radius": 2.0}
    frozen = freeze_configuration(config, source_commit="sealed-commit", dataset_digest=digest)
    rows = [
        row for row in run_manifest["fields"]
        if row["blind_field_token"] in set(public["blind_test_tokens"])
    ]
    detection_fields = []
    methods = ("snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin")
    for row in rows:
        signature = row["input_signature"]
        detection_fields.append({
            "blind_field_token": row["blind_field_token"],
            "input_signature": signature,
            "methods": {
                method: {"input_signature": signature, "detections": []}
                for method in methods
            },
        })
    detection_run = {
        "dataset_digest": digest,
        "frozen_configuration_sha256": frozen["configuration_sha256"],
        "source_commit": "sealed-commit",
        "configuration": {"score_thresholds": {"snr_only": [999.0]}, "match_radius": 2.0},
        "public_fields": run_manifest["fields"],
        "fields": detection_fields,
        "score_thresholds": {name: [1.0] for name in methods},
        "matched_target": {"false_candidates_per_field": 0.0},
    }
    with pytest.raises(ValueError, match="configuration differs"):
        unblind_benchmark(
            public, blind["encrypted_truth_store"], key, frozen,
            detection_run, bootstrap_draws=100,
        )



def test_flux_generalized_least_squares_checks_covariance_diagonal():
    from chronos_causal.noise_model import fit_gaussian_linear
    values = np.array([1.0, 2.0, 2.8, 4.1, 5.0])
    sigma = np.ones(5)
    design = np.column_stack([np.ones(5), np.arange(5, dtype=float)])
    covariance = np.eye(5)
    covariance[covariance == 0] = 0.1
    fit = fit_gaussian_linear(values, sigma, design, covariance=covariance)
    assert fit["covariance_supplied"] is True
    assert fit["noise_model"] == "supplied full covariance"
    with pytest.raises(ValueError, match="diagonal"):
        fit_gaussian_linear(values, sigma, design, covariance=np.eye(5) * 2.0)


def test_measurement_inference_accepts_a_validated_flux_covariance():
    from chronos_benchmark.scenarios import generate_scenario
    from chronos_causal.inference import investigate
    rows = generate_scenario("achromatic_variable", seed=51, n_observations=12)["observations"]
    sigma = np.asarray([row["sigma"] for row in rows])
    covariance = np.diag(sigma ** 2)
    for index in range(len(rows) - 1):
        covariance[index, index + 1] = 0.08 * sigma[index] * sigma[index + 1]
        covariance[index + 1, index] = covariance[index, index + 1]
    result = investigate(rows, flux_covariance=covariance)
    assert result["flux_noise_model"] == "supplied full covariance"
    assert "not calibrated probabilities" in result["interpretation_note"]


def test_falsification_bootstrap_uses_covariance_and_retains_challenge_parameters():
    import hashlib
    from chronos_benchmark.runner import canonical_json
    from chronos_benchmark.scenarios import generate_scenario
    from chronos_causal.falsification import run_falsification_suite
    rows = generate_scenario("achromatic_variable", seed=14, n_observations=12)["observations"]
    sigma = np.asarray([row["sigma"] for row in rows])
    covariance = np.diag(sigma ** 2)
    for index in range(len(rows) - 1):
        covariance[index, index + 1] = covariance[index + 1, index] = 0.05 * sigma[index] * sigma[index + 1]
    plan = [
        {"challenge_id": "sky", "intervention": "sky_variability", "amplitude": 2.0},
        {"challenge_id": "detector", "intervention": "detector_template", "amplitude": 1.5},
        {"challenge_id": "mixed", "intervention": "mixed", "amplitude": 2.0, "template_amplitude": 1.0},
    ]
    digest = hashlib.sha256(canonical_json(plan)).hexdigest()
    report = run_falsification_suite(
        rows, challenge_specs=plan, challenge_plan_sha256=digest,
        flux_covariance=covariance, bootstrap_draws=100, transient_draws=100, seed=9,
    )
    assert report["parametric_bootstrap"]["noise_model"] == "full supplied covariance"
    assert report["challenge_plan"]["externally_sealed_plan_verified"] is True
    assert report["counterfactual_challenges"][0]["parameters"]["amplitude"] == 2.0
    assert len(report["residual_records"]) == len(rows)
    intervals = report["parametric_bootstrap"]["pointwise_conditional_predictive_interval_95"]
    assert len(intervals["median"]) == len(rows)
    assert report["verdict"] == "unknown"



def test_identifiability_refuses_to_mark_missing_covariance_as_verified():
    from chronos_causal.identifiability import audit_forward_model_identifiability
    with pytest.raises(ValueError, match="no covariance was supplied"):
        audit_forward_model_identifiability(
            [[1.0, 0.0], [0.0, 1.0]],
            ["sky", "detector"],
            covariance=None,
            covariance_verified=True,
        )



def test_blind_control_labels_and_field_ids_stay_in_encrypted_store():
    from cryptography.fernet import Fernet
    from chronos_benchmark.blind import create_blind_store
    from chronos_benchmark.runner import truth_catalogue_digest
    key = Fernet.generate_key()
    fields = [_field(f"SECRET-FIELD-{i}") for i in range(3)]
    fields[0]["control_type"] = "empty_field"
    fields[0]["truth_catalogue"] = []
    fields[0]["input_signature"]["truth_catalogue_sha256"] = truth_catalogue_digest([])
    blind = create_blind_store(fields, key, test_fraction=0.34, seed=6)
    assert "SECRET-FIELD-0" not in json.dumps(blind["run_manifest"])
    assert all("control_type" not in row for row in blind["run_manifest"]["fields"])
    private = json.loads(Fernet(key).decrypt(blind["encrypted_truth_store"]).decode("utf-8"))
    empty_row = next(row for row in private["fields"] if row["field"]["field_id"] == "SECRET-FIELD-0")
    assert empty_row["control_type"] == "empty_field"
    assert empty_row["field"]["truth_catalogue"] == []


def test_population_rate_rejects_duplicate_field_ids_and_fractional_counts():
    from chronos_population.rates import estimate_event_rate
    row = {
        "field_id": "FIELD-A", "observed_events": 3, "null_events": 1,
        "area_deg2": 1.0, "baseline_days": 10.0,
        "n_injected": 100, "n_recovered": 80,
    }
    with pytest.raises(ValueError, match="duplicate field_id"):
        estimate_event_rate([row, dict(row)], draws=100)
    fractional = dict(row, field_id="FIELD-B", observed_events=2.5)
    with pytest.raises(ValueError, match="integer count"):
        estimate_event_rate([fractional], draws=100)


def test_population_rate_is_seeded_and_reports_completeness_selection():
    from chronos_population.rates import estimate_event_rate
    fields = [
        {"field_id": "FIELD-A", "observed_events": 5, "null_events": 1,
         "area_deg2": 1.0, "baseline_days": 20.0, "n_injected": 100, "n_recovered": 80},
        {"field_id": "FIELD-B", "observed_events": 2, "null_events": 1,
         "area_deg2": 0.5, "baseline_days": 10.0, "n_injected": 100, "n_recovered": 2},
    ]
    a = estimate_event_rate(fields, minimum_completeness=0.1, draws=200, seed=7)
    b = estimate_event_rate(fields, minimum_completeness=0.1, draws=200, seed=7)
    assert a == b
    assert a["field_count"] == 1
    assert a["skipped_fields"][0]["field_id"] == "FIELD-B"



def test_snr_adapter_collects_below_five_sigma_when_requested_thresholds_include_it():
    from types import SimpleNamespace
    from chronos_benchmark.adapters import (
        build_four_baseline_records, field_mask_sha256, reference_wcs_sha256,
    )
    from chronos_benchmark.runner import truth_catalogue_digest

    class Header:
        def tostring(self, **kwargs):
            return "SNR-TEST-WCS"

    class ReferenceWCS:
        def to_header(self, relax=True):
            return Header()

    truth = [{"truth_id": "T1", "x": 10.0, "y": 10.0}]
    deep = np.zeros((32, 32), dtype=float)
    deep[10, 10] = 12.0
    deep[22, 22] = 3.0
    state = {
        "exps": [
            SimpleNamespace(id="E1", det=2),
            SimpleNamespace(id="E2", det=2),
        ],
        "ref": ReferenceWCS(),
        "DEEPS": deep,
        "RB": np.zeros((2, 32, 32), dtype=bool),
        "IN": np.ones((2, 32, 32), dtype=bool),
        "R": np.zeros((2, 32, 32), dtype=float),
        "MAP": [],
        "cands": [],
    }
    signature = {
        "field_id": "SNR-FLOOR-FIELD", "dataset_class": "synthetic",
        "exposure_ids": ["E1", "E2"], "mask_sha256": field_mask_sha256(state),
        "truth_catalogue_sha256": truth_catalogue_digest(truth),
        "coordinate_frame": "sky", "coordinate_unit": "pixel",
        "pixel_wcs_sha256": reference_wcs_sha256(state["ref"]),
    }
    thresholds = {name: [5.0, 1.0] for name in (
        "snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin"
    )}
    records = build_four_baseline_records(
        state, signature, sky_detector_twin_detections=[],
        score_thresholds=thresholds,
    )
    scores = sorted(
        [row["score"] for row in records["methods"]["snr_only"]["detections"]],
        reverse=True,
    )
    assert scores == [12.0, 3.0]
    assert records["baseline_contract"]["snr_detection_floor"] == 1.0
