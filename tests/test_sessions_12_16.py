import numpy as np
import pytest


def _sample(index, mjd, wavelength, flux):
    return {
        "observation_id": f"SYNTH-{index}",
        "mjd": float(mjd),
        "wavelength_um": float(wavelength),
        "flux": float(flux),
        "sigma": 1.0,
        "calibration_group": "SYNTHETIC-SESSION-12",
        "wavelength_source": "synthetic_fixture",
        "wavelength_unit": "um",
        "wavelength_validated": True,
        "synthetic_fixture": True,
        "valid": True,
        "source_index": index,
    }


def _samples():
    return [
        _sample(0, 60000.0, 2.0, 10.0),
        _sample(1, 60000.0, 2.2, 12.0),
        _sample(2, 60001.0, 2.0, 11.0),
        _sample(3, 60001.0, 2.2, 13.0),
    ]


def test_spectrotemporal_gls_reconstruction_propagates_shared_calibration_covariance():
    from chronos_spectrotemporal.reconstruction import reconstruct

    samples = _samples()
    covariance = np.eye(4)
    covariance[0, 1] = covariance[1, 0] = 0.2
    covariance[2, 3] = covariance[3, 2] = 0.15

    result = reconstruct(
        samples,
        [2.1],
        [60000.5],
        wavelength_bandwidth_um=0.2,
        time_bandwidth_days=1.0,
        min_neighbors=2,
        measurement_covariance=covariance,
        shared_calibration_fractional_sigma=0.05,
    )

    assert result["valid"] == [[True]]
    assert result["sigma_shared_calibration"][0][0] > 0
    assert result["sigma_total"][0][0] > result["sigma_measurement"][0][0]
    assert result["n_samples"][0][0] == 4
    assert {row["source_index"] for row in result["linear_weights"][0][0]} == {0, 1, 2, 3}
    assert result["covariance_model"]["measurement_covariance_supplied"] is True
    assert result["covariance_model"]["shared_calibration_fractional_sigma"] == 0.05


def test_spectrotemporal_covariance_must_match_original_rows_and_sigma_diagonal():
    from chronos_spectrotemporal.reconstruction import reconstruct

    samples = _samples()
    with pytest.raises(ValueError, match="original input-row order"):
        reconstruct(
            samples, [2.1], [60000.5],
            wavelength_bandwidth_um=0.2, time_bandwidth_days=1.0,
            measurement_covariance=np.eye(3),
        )

    wrong_diagonal = np.eye(4) * 2.0
    with pytest.raises(ValueError, match="diagonal"):
        reconstruct(
            samples, [2.1], [60000.5],
            wavelength_bandwidth_um=0.2, time_bandwidth_days=1.0,
            measurement_covariance=wrong_diagonal,
        )


def test_spectrotemporal_covariance_is_subset_after_invalid_rows_are_masked():
    from chronos_spectrotemporal.reconstruction import reconstruct

    samples = _samples()
    samples.insert(1, _sample(99, 60000.4, 2.1, 1000.0) | {"valid": False})
    covariance = np.eye(5)
    covariance[1, :] = np.nan
    covariance[:, 1] = np.nan
    covariance[0, 2] = covariance[2, 0] = 0.1
    result = reconstruct(
        samples, [2.1], [60000.5],
        wavelength_bandwidth_um=0.2, time_bandwidth_days=1.0,
        measurement_covariance=covariance,
    )
    assert result["valid"] == [[True]]
    assert 99 not in result["source_indices"][0][0]
    assert result["covariance_model"]["covariance_row_source_indices"] == [0, 1, 2, 3]


def test_spectrotemporal_reconstruction_keeps_unsupported_cells_missing():
    from chronos_spectrotemporal.reconstruction import reconstruct

    result = reconstruct(
        _samples(),
        [1.8, 2.1, 2.4],
        [60000.5],
        wavelength_bandwidth_um=0.2,
        time_bandwidth_days=1.0,
        min_neighbors=2,
    )
    assert result["valid"] == [[False, True, False]]
    # Reconstruction returns JSON-safe nulls for unsupported cells.
    assert result["flux"][0][0] is None
    assert result["flux"][0][2] is None


def test_equivalent_width_reports_lsf_sampling_and_possible_blending():
    from chronos_addons.molecular import measure_equivalent_width
    from chronos_addons.spectral import Spectrum

    wave = np.linspace(1.0, 2.0, 101)
    flux = 1.0 - 0.2 * np.exp(-0.5 * ((wave - 1.5) / 0.04) ** 2)
    spectrum = Spectrum(wave, flux, sigma=np.full(wave.size, 0.01))
    result = measure_equivalent_width(
        spectrum,
        [1.4, 1.6],
        [[1.2, 1.3], [1.7, 1.8]],
        resolution={
            "resolving_power": 50.0,
            "source_uri": "https://irsa.ipac.caltech.edu/spherex/dr1/cal/lsf/D2.fits",
            "sha256": "a" * 64,
        },
        potential_blend_intervals_um=[[1.59, 1.64]],
    )
    resolution = result["resolution_diagnostics"]
    assert resolution["status"] == "provided"
    assert resolution["lsf_fwhm_um"] == pytest.approx(0.03)
    assert resolution["samples_per_fwhm"] == pytest.approx(3.0)
    assert resolution["sampling_status"] == "sampled_at_two_or_more_pixels_per_fwhm"
    assert resolution["source_reference_recorded"] is True
    assert result["resolution_diagnostics"]["blend_diagnostics"]["status"] == "possible_blend"


def test_equivalent_width_does_not_call_unverified_resolution_calibrated():
    from chronos_addons.molecular import measure_equivalent_width
    from chronos_addons.spectral import Spectrum

    wave = np.linspace(1.0, 2.0, 101)
    spectrum = Spectrum(wave, np.ones(wave.size), sigma=np.full(wave.size, 0.01))
    with pytest.raises(ValueError, match="disagree"):
        measure_equivalent_width(
            spectrum, [1.4, 1.6], [[1.2, 1.3], [1.7, 1.8]],
            resolution={"resolving_power": 100.0, "lsf_fwhm_um": 0.1},
        )


def test_feature_evolution_preserves_resolution_and_blend_reports():
    from chronos_spectrotemporal.feature_evolution import measure_feature_evolution

    wave = np.linspace(1.0, 2.0, 101)
    flux = (1.0 - 0.2 * np.exp(-0.5 * ((wave - 1.5) / 0.04) ** 2)).tolist()
    epoch = {
        "epoch_id": "E1",
        "mjd": 60000.0,
        "wavelength_um": wave.tolist(),
        "flux": flux,
        "sigma": [0.01] * wave.size,
        "valid": [True] * wave.size,
        "calibration_group": "SYNTHETIC-FEATURE",
        "wavelength_source": "synthetic_fixture",
        "wavelength_unit": "um",
        "wavelength_validated": True,
        "synthetic_fixture": True,
        "resolution": {"lsf_fwhm_um": 0.03},
    }
    result = measure_feature_evolution(
        [epoch], [1.4, 1.6], [[1.2, 1.3], [1.7, 1.8]],
        potential_blend_intervals_um=[[1.59, 1.64]],
    )
    assert result["epochs"][0]["resolution_diagnostics"]["status"] == "provided"
    assert result["epochs"][0]["blend_diagnostics"]["status"] == "possible_blend"


def test_catalogue_association_applies_epoch_differential_parallax():
    pytest.importorskip("astropy")
    from chronos_identity.associations import _propagate
    from chronos_addons.catalogs import angular_separation_arcsec

    source = {
        "ra": 10.0, "dec": 20.0, "epoch_year": 2016.0,
        "pmra_cosdec_masyr": 0.0, "pmdec_masyr": 0.0,
        "parallax_mas": 80.0,
    }
    ra_no_parallax, dec_no_parallax, no_parallax = _propagate(
        {key: value for key, value in source.items() if key != "parallax_mas"}, 2016.25
    )
    ra_with_parallax, dec_with_parallax, parallax = _propagate(source, 2016.25)
    assert parallax["parallax_applied"] is True
    assert parallax["parallax_baseline_au"] > 0
    assert abs(parallax["parallax_shift_east_mas"]) + abs(parallax["parallax_shift_north_mas"]) > 0
    assert angular_separation_arcsec(
        ra_no_parallax, dec_no_parallax, ra_with_parallax, dec_with_parallax
    ) > 0.001
    assert no_parallax["parallax_applied"] is False


def test_catalogue_association_includes_parallax_uncertainty_in_position_error():
    pytest.importorskip("astropy")
    from chronos_identity.associations import _propagate, probabilistic_associations

    source = {
        "source_id": "PX-1",
        "ra": 10.0, "dec": 20.0, "epoch_year": 2016.0,
        "pmra_cosdec_masyr": 0.0, "pmdec_cosdec_masyr": 0.0,
        "parallax_mas": 80.0, "position_sigma_arcsec": 0.05,
        "parallax_error_mas": 0.0,
        "survey": "synthetic catalogue fixture",
        "bandpass": "reference",
        "angular_resolution_arcsec": 0.4,
    }
    ra, dec, _ = _propagate(source, 2016.25)
    candidate = {
        "candidate_id": "C1", "ra": ra, "dec": dec,
        "epoch_year": 2016.25, "position_sigma_arcsec": 0.05,
    }
    without_error = probabilistic_associations(candidate, [source])
    with_error_source = dict(source, parallax_error_mas=10.0)
    with_error = probabilistic_associations(candidate, [with_error_source])
    assert with_error["matches"][0]["parallax_sigma_arcsec"] > 0
    assert with_error["matches"][0]["combined_sigma_arcsec"] > without_error["matches"][0]["combined_sigma_arcsec"]
    assert with_error["matches"][0]["survey_metadata"]["survey"] == "synthetic catalogue fixture"


def test_observation_planner_labels_unverified_feasibility_and_prior_sensitivity():
    from chronos_addons.planner import plan_observations

    candidates = [
        {
            "time": "2027-01-01T00:00:00Z",
            "wavelength_um": 2.1,
            "detector_id": "D2",
            "measurement_type": "spectral_epoch",
            "predictions": {
                "static": {"mean": 1.0, "sigma": 0.1},
                "variable": {"mean": 2.0, "sigma": 0.1},
            },
        },
        {
            "time": "2027-01-02T00:00:00Z",
            "wavelength_um": 3.0,
            "detector_id": "D3",
            "measurement_type": "partner_array",
            "predictions": {
                "static": {"mean": 1.0, "sigma": 0.1},
                "variable": {"mean": 5.0, "sigma": 0.1},
            },
        },
    ]
    result = plan_observations(
        candidates,
        measurement_sigma=0.2,
        alternative_priors={
            "variable_favoured": {"static": 0.2, "variable": 0.8},
            "static_favoured": {"static": 0.8, "variable": 0.2},
        },
    )
    assert result["recommendation_status"] == "forecast_ranked_feasibility_unverified"
    assert result["recommended"]["feasibility"]["status"] == "unverified"
    assert set(result["prior_sensitivity"]) == {"variable_favoured", "static_favoured"}
    assert result["recommended"]["measurement"]["wavelength_um"] == 3.0


def test_observation_planner_preserves_verified_external_feasibility_record():
    from chronos_addons.planner import plan_observations

    candidate = {
        "time": "2027-02-01T00:00:00Z",
        "wavelength_um": 2.2,
        "detector_id": "D2",
        "predictions": {
            "h1": {"mean": 0.0, "sigma": 0.1},
            "h2": {"mean": 4.0, "sigma": 0.1},
        },
        "feasibility": {
            "status": "verified",
            "feasible": True,
            "source_uri": "https://example.org/visibility-report/123",
            "checked_utc": "2026-11-25T10:00:00Z",
            "window_start_utc": "2027-02-01T00:00:00Z",
            "window_end_utc": "2027-02-01T00:30:00Z",
            "constraints": {"target_altitude_deg": 35.0},
        },
    }
    result = plan_observations([candidate])
    assert result["recommendation_status"] == "forecast_ranked_feasibility_verified"
    assert result["recommended"]["feasibility"]["source_uri"] == candidate["feasibility"]["source_uri"]
    assert result["recommended"]["feasibility"]["window"]["end_utc"] > result["recommended"]["feasibility"]["window"]["start_utc"]


def test_observation_planner_rejects_malformed_verified_feasibility_timestamp():
    from chronos_addons.planner import plan_observations

    candidate = {
        "time": "later",
        "predictions": {"h1": {"mean": 0.0}, "h2": {"mean": 1.0}},
        "feasibility": {
            "status": "verified", "feasible": True,
            "source_uri": "https://example.org/report",
            "checked_utc": "2026-11-25T10:00:00",
        },
    }
    with pytest.raises(ValueError, match="timezone"):
        plan_observations([candidate])


def _package_source_file(tmp_path):
    import hashlib
    source = tmp_path / "science.fits"
    payload = b"SIMPLE  fixture native science bytes"
    source.write_bytes(payload)
    return {
        "role": "science_mef",
        "archive_id": "SYNTHETIC-ARCHIVE-ID",
        "product_type": "Level-2 MEF test fixture",
        "release": "SYNTHETIC",
        "detector": "D2",
        "native_uri": "https://example.org/synthetic/science.fits",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "local_path": str(source),
        "compatibility_group": "SYNTHETIC-D2",
    }


def _package_inputs(tmp_path):
    from chronos_causal.evidence_graph import build_evidence_graph
    analysis = {
        "verdict": "unknown",
        "leading_model": "static_source",
        "abstention_reasons": ["synthetic package fixture only"],
    }
    observations = [{
        "observation_id": "SYNTHETIC-OBS-1",
        "mjd": 60000.0,
        "wavelength_um": 2.1,
        "detector_id": "D2",
        "calibration_group": "SYNTHETIC-D2",
    }]
    graph = build_evidence_graph(
        candidate_id="SYNTHETIC-CANDIDATE",
        observations=observations,
        analysis=analysis,
    )
    return analysis, graph


def test_investigation_package_embeds_sources_and_verifies_all_member_hashes(tmp_path):
    import hashlib
    import zipfile
    from chronos_causal.investigation_package import (
        create_investigation_package, verify_investigation_package,
    )

    analysis, graph = _package_inputs(tmp_path)
    source = _package_source_file(tmp_path)
    package_path = tmp_path / "investigation.zip"
    created = create_investigation_package(
        package_path,
        candidate_id="SYNTHETIC-CANDIDATE",
        analysis=analysis,
        evidence_graph=graph,
        source_files=[source],
        reproduction_command="python reproduce.py --package investigation.zip",
        code_commit="a" * 40,
        environment={"python_version": "test-fixture"},
        processing_configuration={"data_class": "synthetic fixture"},
        failed_checks=[{"check": "real_data", "status": "not_run"}],
        include_source_bytes=True,
    )
    verified = verify_investigation_package(package_path)
    assert verified["valid"] is True
    assert created["source_bytes_embedded"] is True
    assert verified["source_bytes_embedded"] is True
    assert verified["candidate_id"] == "SYNTHETIC-CANDIDATE"
    assert created["sha256"] == hashlib.sha256(package_path.read_bytes()).hexdigest()


def test_investigation_package_detects_tampered_member_after_repacking(tmp_path):
    import hashlib
    import zipfile
    from chronos_causal.investigation_package import (
        create_investigation_package, verify_investigation_package,
    )

    analysis, graph = _package_inputs(tmp_path)
    package_path = tmp_path / "tamper-check.zip"
    create_investigation_package(
        package_path,
        candidate_id="SYNTHETIC-CANDIDATE",
        analysis=analysis,
        evidence_graph=graph,
        source_files=[_package_source_file(tmp_path)],
        reproduction_command="python reproduce.py",
        include_source_bytes=True,
    )
    with zipfile.ZipFile(package_path, "r") as original:
        members = {name: original.read(name) for name in original.namelist()}
    members["analysis.json"] = b'{"verdict":"tampered"}\n'
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        for name, payload in members.items():
            changed.writestr(name, payload)
    package_hash = hashlib.sha256(package_path.read_bytes()).hexdigest()
    package_path.with_name(package_path.name + ".sha256").write_text(
        f"{package_hash}  {package_path.name}\n", encoding="utf-8"
    )
    verified = verify_investigation_package(package_path)
    assert verified["valid"] is False
    assert verified["reason"] == "one or more package members failed integrity verification"
    assert any(row["path"] == "analysis.json" for row in verified["failures"])


def test_investigation_package_requires_exact_source_hash_and_reproduction_command(tmp_path):
    import pytest
    from chronos_causal.investigation_package import create_investigation_package

    analysis, graph = _package_inputs(tmp_path)
    source = _package_source_file(tmp_path)
    bad_source = dict(source, sha256="0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        create_investigation_package(
            tmp_path / "bad.zip", candidate_id="SYNTHETIC-CANDIDATE",
            analysis=analysis, evidence_graph=graph, source_files=[bad_source],
            reproduction_command="python reproduce.py",
        )
    with pytest.raises(ValueError, match="reproduction command"):
        create_investigation_package(
            tmp_path / "missing-command.zip", candidate_id="SYNTHETIC-CANDIDATE",
            analysis=analysis, evidence_graph=graph, source_files=[source],
            reproduction_command="",
        )


def test_investigation_package_can_record_external_sources_without_embedding_bytes(tmp_path):
    from chronos_causal.investigation_package import create_investigation_package
    analysis, graph = _package_inputs(tmp_path)
    source = _package_source_file(tmp_path)
    result = create_investigation_package(
        tmp_path / "metadata-only.zip",
        candidate_id="SYNTHETIC-CANDIDATE",
        analysis=analysis,
        evidence_graph=graph,
        source_files=[source],
        reproduction_command="python reproduce.py --retrieve-from-manifest",
        include_source_bytes=False,
    )
    assert result["source_bytes_embedded"] is False


def test_evidence_package_export_api_returns_verifiable_zip(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chronos_causal.api import router
    from chronos_causal.investigation_package import verify_investigation_package

    app = FastAPI()
    app.include_router(router)
    payload = {
        "candidate_id": "SYNTHETIC-API-CANDIDATE",
        "analysis": {"verdict": "unknown", "abstention_reasons": ["synthetic API fixture"]},
        "evidence_graph": {"graph_sha256": "a" * 64, "claim": {"status": "unresolved"}},
        "source_files": [{
            "role": "science_mef",
            "archive_id": "SYNTHETIC-ARCHIVE-ID",
            "product_type": "Level-2 MEF test fixture",
            "release": "SYNTHETIC",
            "detector": "D2",
            "native_uri": "https://example.org/synthetic/science.fits",
            "sha256": "b" * 64,
            "byte_count": 100,
        }],
        "reproduction_command": "python reproduce.py --manifest sources.json",
        "code_commit": "c" * 40,
        "environment": {"python_version": "fixture"},
        "processing_configuration": {"data_class": "synthetic"},
        "failed_checks": [{"check": "real_data", "status": "not_run"}],
    }
    response = TestClient(app).post("/api/v5/evidence/package/export", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    package_path = tmp_path / "api-export.zip"
    package_path.write_bytes(response.content)
    report = verify_investigation_package(package_path)
    assert report["valid"] is True
    assert report["source_bytes_embedded"] is False


def test_evidence_package_http_endpoint_rejects_server_local_paths():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chronos_causal.api import router

    app = FastAPI()
    app.include_router(router)
    payload = {
        "candidate_id": "C",
        "analysis": {"verdict": "unknown"},
        "evidence_graph": {"graph_sha256": "a" * 64},
        "source_files": [{
            "role": "science",
            "product_type": "Level-2 MEF",
            "release": "DR1",
            "detector": "D2",
            "native_uri": "https://example.org/science.fits",
            "sha256": "b" * 64,
            "local_path": "/etc/passwd",
        }],
        "reproduction_command": "python reproduce.py",
    }
    response = TestClient(app).post("/api/v5/evidence/package/export", json=payload)
    assert response.status_code == 422
    assert "source metadata only" in response.json()["detail"]


def test_zero_measured_parallax_still_propagates_its_uncertainty_baseline():
    pytest.importorskip("astropy")
    from chronos_identity.associations import _propagate
    source = {
        "ra": 120.0, "dec": 30.0, "epoch_year": 2016.0,
        "parallax_mas": 0.0, "parallax_error_mas": 12.0,
    }
    _, _, report = _propagate(source, 2016.25)
    assert report["parallax_applied"] is True
    assert report["parallax_baseline_au"] > 0
    assert report["parallax_shift_east_mas"] == pytest.approx(0.0)
    assert report["parallax_shift_north_mas"] == pytest.approx(0.0)


def _population_real_field(field_id="FIELD-1", source_id="YSO-1", *,
                           omit_feature_epochs=(), duplicate_source=False):
    from copy import deepcopy

    rows = []
    band_wavelengths = {
        "blue": [2.82, 2.88],
        "feature": [3.06, 3.10, 3.14],
        "red": [3.32, 3.38],
    }
    for epoch_index, mjd in enumerate((60000.0, 60010.0, 60020.0)):
        for band, wavelengths in band_wavelengths.items():
            if band == "feature" and epoch_index in omit_feature_epochs:
                continue
            for wavelength_index, wavelength in enumerate(wavelengths):
                rows.append({
                    "source_id": source_id,
                    "observation_id": f"{field_id}-E{epoch_index}",
                    "mjd": mjd,
                    "wavelength_um": wavelength,
                    "flux": 10.0,
                    "sigma": 1.0,
                    "flux_unit": "Jy",
                    "calibration_group": "DR1-D2-TEST-CAL",
                    "wavelength_unit": "um",
                    "wavelength_validated": True,
                    "wavelength_source": "CWAVE/CBAND",
                    "wavelength_provenance": {
                        "decision": "compatible",
                        "compatibility_group": "DR1-D2-TEST-CAL",
                        "science_sha256": "a" * 64,
                        "calibration_sha256": "b" * 64,
                        "native_mef_audit_sha256": "c" * 64,
                        "solid_angle_sha256": "d" * 64,
                        "science_uri": "https://example.org/science.fits",
                        "calibration_uri": "https://example.org/wavelength.fits",
                        "solid_angle_uri": "https://example.org/solid-angle.fits",
                        "pixel_valid": True,
                    },
                    "valid": True,
                })
    source = {
        "source_id": source_id,
        "sample_class": "young_stellar_object",
        "classification_reference": "https://example.org/independent-classification",
        "observations": rows,
    }
    return {
        "field_id": field_id,
        "dataset_class": "real",
        "independent_field": True,
        "null_control_id": f"NULL-{field_id}",
        "null_control_to_science_exposure_ratio": 0.25,
        "area_deg2": 0.5,
        "baseline_days": 20.0,
        "null_control_area_deg2": 2.0,
        "null_control_baseline_days": 20.0,
        "n_injected": 100,
        "n_recovered": 90,
        "observed_events": 12,
        "null_events": 8,
        "sources": [source],
    }


def test_population_coverage_requires_feature_and_both_continua_in_same_epochs():
    from chronos_population.coverage import assess_population_coverage

    field = _population_real_field(omit_feature_epochs=(1, 2))
    result = assess_population_coverage(
        [field],
        minimum_independent_fields=1,
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.3, 3.4],
    )
    source = result["fields"][0]["sources"][0]
    assert source["feature_samples"] == 3
    assert source["feature_epochs"] == 1
    assert source["complete_feature_epochs"] == 1
    assert result["eligible_for_predeclared_population_protocol"] is False
    assert "feature_and_both_continua_not_jointly_sampled_per_epoch" in source["reasons"]


def test_population_coverage_passes_only_with_repeated_same_epoch_spectral_coverage():
    from chronos_population.coverage import assess_population_coverage

    result = assess_population_coverage(
        [_population_real_field()],
        minimum_independent_fields=1,
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.3, 3.4],
    )
    assert result["eligible_for_predeclared_population_protocol"] is True
    assert result["fields"][0]["sources"][0]["complete_feature_epochs"] == 3


def test_population_coverage_rejects_same_source_counted_in_multiple_fields():
    from copy import deepcopy
    from chronos_population.coverage import assess_population_coverage

    first = _population_real_field("FIELD-A", "REPEATED-SOURCE")
    second = _population_real_field("FIELD-B", "REPEATED-SOURCE")
    result = assess_population_coverage(
        [first, second],
        minimum_independent_fields=2,
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.3, 3.4],
    )
    for field in result["fields"]:
        assert "source_reused_across_fields" in field["sources"][0]["reasons"]
        assert field["eligible"] is False
    assert result["eligible_for_predeclared_population_protocol"] is False


def _population_coverage_audit(fields, minimum_completeness=0.5):
    from chronos_population.coverage import assess_population_coverage

    return assess_population_coverage(
        fields,
        minimum_independent_fields=1,
        minimum_completeness=minimum_completeness,
        feature_interval_um=[3.05, 3.15],
        blue_continuum_um=[2.8, 2.95],
        red_continuum_um=[3.3, 3.4],
    )


def test_population_event_rate_scales_null_control_to_science_exposure():
    from chronos_population.rates import estimate_event_rate

    field = _population_real_field()
    audit = _population_coverage_audit([field])
    result = estimate_event_rate([field], coverage_audit=audit, draws=1000, seed=19)
    assert result["field_count"] == 1
    assert result["coverage_revalidated"] is True
    included = result["included_fields"][0]
    assert included["null_control_to_science_exposure_ratio"] == pytest.approx(0.25)
    assert included["null_events_expected_in_science_exposure"] == pytest.approx(2.0)
    assert result["event_rate_per_sqdeg_day"]["median"] > 0
    assert result == estimate_event_rate(
        [field], coverage_audit=audit, draws=1000, seed=19
    )


def test_population_event_rate_refuses_synthetic_or_unattested_fields():
    from chronos_population.rates import estimate_event_rate

    valid = _population_real_field("REAL")
    synthetic = _population_real_field("SYNTH")
    synthetic["dataset_class"] = "synthetic"
    unattested = _population_real_field("UNATTESTED")
    unattested["independent_field"] = False
    fields = [valid, synthetic, unattested]
    audit = _population_coverage_audit(fields)
    assert audit["eligible_for_predeclared_population_protocol"] is False
    with pytest.raises(ValueError, match="coverage audit did not pass"):
        estimate_event_rate(fields, coverage_audit=audit, draws=1000, seed=23)


def test_population_event_rate_rejects_missing_null_control_exposure_scale():
    from chronos_population.rates import estimate_event_rate

    field = _population_real_field()
    field.pop("null_control_to_science_exposure_ratio")
    audit = _population_coverage_audit([field])
    assert audit["eligible_for_predeclared_population_protocol"] is False
    with pytest.raises(ValueError, match="coverage audit did not pass"):
        estimate_event_rate([field], coverage_audit=audit, draws=1000, seed=29)


def test_population_event_rate_rejects_modified_coverage_audit_or_field_records():
    from chronos_population.rates import estimate_event_rate

    field = _population_real_field()
    audit = _population_coverage_audit([field])
    forged_audit = dict(audit)
    forged_audit["input_fields_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="field digest mismatch"):
        estimate_event_rate([field], coverage_audit=forged_audit, draws=1000, seed=31)

    modified_field = dict(field)
    modified_field["observed_events"] += 1
    with pytest.raises(ValueError, match="field digest mismatch"):
        estimate_event_rate([modified_field], coverage_audit=audit, draws=1000, seed=31)


def test_population_coverage_derives_null_control_ratio_from_area_time():
    from chronos_population.coverage import assess_population_coverage

    field = _population_real_field()
    field["null_control_to_science_exposure_ratio"] = 0.5
    result = _population_coverage_audit([field])
    assert result["eligible_for_predeclared_population_protocol"] is False
    assert "null_control_exposure_ratio_inconsistent_with_area_time" in result["fields"][0]["reasons"]


def test_population_coverage_rejects_unbridged_calibration_group_changes():
    from chronos_population.coverage import assess_population_coverage

    field = _population_real_field()
    row = field["sources"][0]["observations"][-1]
    row["calibration_group"] = "DR1-D2-SECOND-CAL"
    row["wavelength_provenance"]["compatibility_group"] = "DR1-D2-SECOND-CAL"
    result = _population_coverage_audit([field])
    source = result["fields"][0]["sources"][0]
    assert result["eligible_for_predeclared_population_protocol"] is False
    assert "multiple_calibration_groups_without_verified_bridge" in source["reasons"]


def test_population_event_rate_pools_counts_over_total_area_time_exposure():
    from chronos_population.rates import estimate_event_rate

    one_field = _population_real_field("FIELD-A", "SOURCE-A")
    second_field = _population_real_field("FIELD-B", "SOURCE-B")
    single_audit = _population_coverage_audit([one_field])
    combined_audit = _population_coverage_audit([one_field, second_field])

    single = estimate_event_rate(
        [one_field], coverage_audit=single_audit, draws=10000, seed=71
    )
    combined = estimate_event_rate(
        [one_field, second_field], coverage_audit=combined_audit, draws=10000, seed=71
    )

    assert single["total_science_exposure_sqdeg_days"] == pytest.approx(10.0)
    assert single["event_rate_per_sqdeg_day"]["median"] > 0
    assert combined["total_science_exposure_sqdeg_days"] == pytest.approx(20.0)
    assert [row["science_exposure_sqdeg_days"] for row in combined["included_fields"]] == [10.0, 10.0]
    # Adding an equally representative independent field doubles exposure and
    # expected excess counts; it must not double the pooled rate.
    assert combined["event_rate_per_sqdeg_day"]["median"] == pytest.approx(
        single["event_rate_per_sqdeg_day"]["median"], rel=0.15
    )
