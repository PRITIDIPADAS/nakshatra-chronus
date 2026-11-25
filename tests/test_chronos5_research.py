import numpy as np
import pytest

def _rows(n=12, scenario="achromatic_variable"):
    from chronos_benchmark.scenarios import generate_scenario
    return generate_scenario(scenario, seed=7, n_observations=n)["observations"]

def test_identifiability_reports_missing_design_dimensions():
    from chronos_causal.identifiability import audit_identifiability
    rows = _rows()
    for row in rows:
        row["wavelength_um"] = 2.0
        row.pop("template_score", None)
    result = audit_identifiability(rows)
    assert result["status"] in {"weakly_identifiable", "not_identifiable"}
    assert result["wavelengths"] == 1
    assert any("wavelength" in item.lower() for item in result["reasons"])

def test_identifiability_screen_identifies_severe_rank_deficiency():
    from chronos_causal.identifiability import audit_identifiability
    rows = _rows()
    for row in rows:
        row["wavelength_um"] = 2.0
        row["template_score"] = 0.5
    result = audit_identifiability(rows)
    assert result["status"] == "not_identifiable"
    assert result["rank"] < len(result["design_columns"])

def test_synthetic_challenge_scenarios_include_transient():
    from chronos_benchmark.scenarios import generate_scenario
    from chronos_causal.inference import investigate
    fixture = generate_scenario("transient", seed=11, n_observations=14)
    result = investigate(fixture["observations"], min_relative_support=0.5, min_delta_bic=2)
    names = {row["name"] for row in result["relative_model_support"]}
    assert "transient" in names

def test_counterfactual_does_not_mutate_input():
    from chronos_benchmark.scenarios import generate_scenario
    from chronos_causal.counterfactual import make_counterfactual
    rows = _rows()
    original = [dict(row) for row in rows]
    altered = make_counterfactual(rows, "transient", amplitude=9)
    assert rows == original
    assert altered["original_rows_mutated"] is False
    assert altered["event_interval_mjd"] is not None

def test_detector_forward_model_is_seed_reproducible():
    from chronos_causal.forward_model import simulate_detector_frame
    kwargs = dict(shape=(20, 20), sources=[{"x": 10.2, "y": 9.7, "expected_electrons": 500}],
                  psf_kernel=[[1,2,1],[2,4,2],[1,2,1]], background_electrons=10,
                  read_noise_electrons=3, seed=42)
    a = simulate_detector_frame(**kwargs)
    b = simulate_detector_frame(**kwargs)
    assert np.allclose(a["measured_electrons"], b["measured_electrons"], equal_nan=True)
    assert a["variance_electrons_squared"] == b["variance_electrons_squared"]

def test_manifest_tampering_is_detected():
    from chronos_causal.provenance import create_manifest, verify_manifest
    row = {"archive_id":"A1","product_type":"MEF","release":"DR1","detector":"D2",
           "sha256":"a"*64,"bytes":123}
    m = create_manifest(project="CHRONOS", calibration_group="DR1-D2", files=[row], software={"commit":"abc"})
    assert verify_manifest(m)["valid"]
    m["files"][0]["bytes"] += 1
    assert not verify_manifest(m)["valid"]

def test_spectrotemporal_does_not_extrapolate():
    from chronos_spectrotemporal.reconstruction import reconstruct
    samples = [
        {"mjd":1,"wavelength_um":1,"flux":10,"sigma":1,"calibration_group":"G"},
        {"mjd":2,"wavelength_um":2,"flux":12,"sigma":1,"calibration_group":"G"},
        {"mjd":3,"wavelength_um":1,"flux":11,"sigma":1,"calibration_group":"G"},
        {"mjd":4,"wavelength_um":2,"flux":13,"sigma":1,"calibration_group":"G"},
    ]
    result = reconstruct(samples, [0.8,1.5,2.2], [0.5,2,4.5],
                         wavelength_bandwidth_um=1,time_bandwidth_days=2,min_neighbors=1)
    assert all(v is False for v in result["valid"][0])
    assert all(v is False for v in result["valid"][-1])

def test_probabilistic_association_keeps_no_match_probability():
    from chronos_identity.associations import probabilistic_associations
    candidate = {"candidate_id":"C1","ra":10,"dec":10,"epoch_year":2026,"position_sigma_arcsec":.2}
    sources = [{"id":"S1","ra":100,"dec":-10,"epoch_year":2016,"position_sigma_arcsec":.2}]
    result = probabilistic_associations(candidate,sources)
    assert result["status"] == "no_supported_counterpart"
    assert result["no_counterpart_probability"] == 1.0

def test_population_estimator_excludes_low_completeness_field():
    from chronos_population.rates import estimate_event_rate
    fields = [
        {"field_id":"good","observed_events":5,"null_events":1,"area_deg2":1,"baseline_days":10,"n_injected":100,"n_recovered":50},
        {"field_id":"bad","observed_events":50,"null_events":0,"area_deg2":1,"baseline_days":10,"n_injected":100,"n_recovered":2},
    ]
    result = estimate_event_rate(fields,minimum_completeness=.1,draws=200,seed=1)
    assert result["field_count"] == 1
    assert result["skipped_fields"][0]["field_id"] == "bad"

def test_causal_api_router_declares_status_and_inference():
    from chronos_causal.api import router
    routes = {route.path for route in router.routes}
    assert "/api/v5/status" in routes
    assert "/api/v5/causal/investigate" in routes
    assert "/api/v5/causal/identifiability" in routes


def test_detector_psf_shift_does_not_wrap_energy_to_opposite_edge():
    from chronos_causal.forward_model import _place_kernel
    frame = np.zeros((12, 12), dtype=float)
    kernel = np.ones((3, 3), dtype=float) / 9
    _place_kernel(frame, kernel, 0.2, 6.0, 90.0)
    assert np.all(frame[:, -2:] == 0)
    assert frame[:, :4].sum() > 0
    assert frame.sum() < 90.0

def test_real_mef_injection_records_when_source_shot_noise_is_enabled():
    from research_discovery.validation.injection_recovery import run_injection_recovery
    image = np.zeros((72, 72), dtype=float)
    variance = np.ones_like(image)
    flags = np.zeros_like(image, dtype=np.uint16)
    psf = np.ones((5, 5), dtype=float)
    deterministic = run_injection_recovery(
        image, variance, flags, psf, flux_levels=[40.0], n_per_level=1,
        snr_threshold=1000, source_exclusion_radius=0, seed=12,
    )
    record = {
        "verification_status": "verified",
        "electrons_per_image_unit": 250.0,
        "science_file_sha256": "a" * 64,
        "science_observation_id": "SYNTHETIC-FIXTURE",
        "science_source_uri": "https://example.invalid/science.fits",
        "detector": "D2",
        "image_unit": "MJy/sr",
        "calibration_uri": "https://example.invalid/calibration.fits",
        "calibration_file_path": "synthetic-fixture-calibration.fits",
        "calibration_sha256": "b" * 64,
        "conversion_method": "unit-test fixture only",
        "verified_by": "unit-test",
        "verified_utc": "2026-01-01T00:00:00Z",
    }
    physical = run_injection_recovery(
        image, variance, flags, psf, flux_levels=[40.0], n_per_level=1,
        snr_threshold=1000, source_exclusion_radius=0, seed=12,
        electrons_per_image_unit=250.0, electron_calibration_record=record,
    )
    assert deterministic["source_photon_noise"]["enabled"] is False
    assert physical["source_photon_noise"]["enabled"] is True
    assert physical["source_photon_noise"]["electrons_per_image_unit"] == 250.0
