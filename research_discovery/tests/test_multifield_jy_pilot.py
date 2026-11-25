from research_discovery.spherex.run_multifield_jy_pilot import (
    FIELDS,
    aggregate_report,
    summarize_field_record,
)


def _summary():
    return {
        "native_mef_audit": {"calibration_compatibility": {"status": "compatible"}},
        "absolute_gain_validation": {
            "status": "structure_units_pass_with_invalid_pixels_explicitly_masked",
            "invalid_pixels_are_not_interpolated": True,
        },
        "archive_provenance": {
            "exact_product_links": {
                "spectral_wcs": {"status": "verified"},
                "absolute_gain": {"status": "verified"},
            },
            "solid_angle_map_pipeline_input": False,
            "input_relation_count": 14,
        },
        "science": {
            "uri": "https://irsa.example/science.fits", "sha256": "a" * 64,
            "observation_id": "obs-1", "detector": "D2", "release": "dr1",
            "pipeline_version": "7.0.5", "processing_date": "2026-198",
            "exposure_time_s": 100.0, "image_unit": "MJy/sr",
        },
        "selected_products": {
            "spectral_wcs": {"uri": "https://irsa.example/wcs.fits"},
            "solid_angle": {"uri": "https://irsa.example/area.fits"},
            "absolute_gain": {"uri": "https://irsa.example/gain.fits"},
        },
        "calibrated_jy_injection_evaluation": {
            "status": "completed",
            "five_sigma_sensitivity_jy": 1e-4,
            "flux_summary": [
                {
                    "flux_level": level, "n_injected": 20, "n_recovered": 18,
                    "source_poisson_expected_electrons": 200.0,
                    "source_poisson_variance_added_image_units2": 0.02,
                }
                for level in (0.5e-4, 1e-4, 2e-4)
            ],
            "n_baseline_detections": 10,
            "source_photon_noise": {
                "enabled": True, "physically_modelled": True,
                "calibration_review_status": "pending",
                "independent_human_reviewed": False,
                "conversion_map_valid_fraction": 0.9999,
                "calibration_record": {
                    "verification_status": "derived_pending_independent_review",
                    "science_source_uri": "https://irsa.example/science.fits",
                    "calibration_uri": "https://irsa.example/gain.fits",
                    "calibration_sha256": "b" * 64,
                    "provenance_link": {
                        "input_table": "spherex.provenance_input",
                        "status": "verified_from_live_irsa_foreign_key_query",
                        "artifact_md5_status": "pass",
                        "inputid": "gain-plane", "calibration_planeid": "gain-plane",
                        "outputid": "science-plane", "science_planeid": "science-plane",
                        "science_native_uri": "https://irsa.example/science.fits",
                        "calibration_native_uri": "https://irsa.example/gain.fits",
                        "calibration_sha256": "b" * 64,
                    },
                },
            },
            "electron_calibration_derivation": {
                "absolute_gain_uri": "https://irsa.example/gain.fits",
                "absolute_gain_sha256": "b" * 64,
                "independent_review_status": "pending",
                "record": {
                    "verification_status": "derived_pending_independent_review",
                    "science_source_uri": "https://irsa.example/science.fits",
                    "calibration_uri": "https://irsa.example/gain.fits",
                    "calibration_sha256": "b" * 64,
                    "provenance_link": {
                        "input_table": "spherex.provenance_input",
                        "status": "verified_from_live_irsa_foreign_key_query",
                        "artifact_md5_status": "pass",
                        "inputid": "gain-plane", "calibration_planeid": "gain-plane",
                        "outputid": "science-plane", "science_planeid": "science-plane",
                        "science_native_uri": "https://irsa.example/science.fits",
                        "calibration_native_uri": "https://irsa.example/gain.fits",
                        "calibration_sha256": "b" * 64,
                    },
                },
            },
        },
    }


def test_six_predeclared_fields_include_independent_control_region():
    assert len(FIELDS) == 6
    assert sum(field["role"] == "control" for field in FIELDS) == 1


def test_field_summary_requires_all_provenance_and_jy_gates():
    record = summarize_field_record(
        FIELDS[0], _summary(), return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is True
    assert record["checks"]["spectral_wcs_exact_provenance_link"] is True
    assert record["checks"]["absolute_gain_exact_provenance_link"] is True
    assert record["checks"]["solid_angle_explicitly_supplemental"] is True


def test_field_summary_fails_closed_when_gain_link_or_injection_is_missing():
    summary = _summary()
    summary["archive_provenance"]["exact_product_links"]["absolute_gain"] = None
    summary["calibrated_jy_injection_evaluation"]["status"] = "failed"
    record = summarize_field_record(
        FIELDS[0], summary, return_code=1, log_path="field.log",
        error="calibration failure",
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["absolute_gain_exact_provenance_link"] is False
    assert record["checks"]["jy_injection_completed"] is False
    assert record["checks"]["subprocess_exit_zero"] is False


def test_aggregate_never_claims_blind_or_population_discovery():
    records = []
    for index, field in enumerate(FIELDS):
        summary = _summary()
        summary["science"]["observation_id"] = f"obs-{index}"
        summary["science"]["sha256"] = f"{index:064x}"
        records.append(summarize_field_record(
            field, summary, return_code=0, log_path=f"{field['name']}.log"
        ))
    report = aggregate_report(
        records, started_utc="2026-11-25T00:00:00Z",
        finished_utc="2026-11-25T00:01:00Z", code_revision="a" * 40,
    )
    assert report["field_count_completed"] == 6
    assert report["science_observation_ids_unique"] is True
    assert report["science_file_hashes_unique"] is True
    assert report["scientific_gate_status"]["multi_field_calibrated_jy_evaluation"] == "completed_exploratory_for_predeclared_regions"
    assert report["scientific_gate_status"]["independent_blind_four_baseline_benchmark"] == "not_satisfied"
    assert report["scientific_gate_status"]["population_level_yso_discovery"] == "not_satisfied"


def test_aggregate_rejects_duplicate_exposure_identity_from_multifield_gate():
    records = []
    for field in FIELDS:
        records.append(summarize_field_record(
            field, _summary(), return_code=0, log_path=f"{field['name']}.log"
        ))
    report = aggregate_report(
        records, started_utc="a", finished_utc="b", code_revision=None
    )
    assert report["field_count_completed"] == 6
    assert report["science_observation_ids_unique"] is False
    assert report["scientific_gate_status"]["multi_field_calibrated_jy_evaluation"] == "not_satisfied"


def test_query_report_is_hashed_and_failures_remain_visible():
    records = [
        summarize_field_record(
            field, _summary(), return_code=0, log_path="field.log"
        ) for field in FIELDS
    ]
    records[0]["eligible_for_multi_field_pilot_summary"] = False
    report = aggregate_report(
        records, started_utc="a", finished_utc="b", code_revision=None
    )
    assert report["field_count_incomplete"] == 1
    assert len(report["report_sha256"]) == 64


def test_field_summary_preserves_exact_native_image_bunit():
    summary = _summary()
    summary["science"].pop("image_unit")
    summary["science"]["image_bunit"] = "MJy / sr"
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["science"]["image_unit"] == "MJy / sr"
    assert record["eligible_for_multi_field_pilot_summary"] is True


def test_field_summary_requires_real_poisson_variance_diagnostics_for_all_flux_bins():
    summary = _summary()
    summary["calibrated_jy_injection_evaluation"]["flux_summary"][1].pop(
        "source_poisson_variance_added_image_units2"
    )
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["source_poisson_flux_bin_variances_measured"] is False


def test_field_summary_rejects_gain_link_without_live_archive_md5():
    summary = _summary()
    summary["calibrated_jy_injection_evaluation"]["source_photon_noise"][
        "calibration_record"
    ]["provenance_link"]["artifact_md5_status"] = "not_checked"
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["electron_conversion_live_irsa_relation_and_md5"] is False


def test_field_summary_requires_explicit_pending_review_not_human_signoff():
    summary = _summary()
    summary["calibrated_jy_injection_evaluation"]["source_photon_noise"][
        "independent_human_reviewed"
    ] = True
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["source_poisson_is_not_mislabelled_human_verified"] is False
