from research_discovery.spherex.run_multifield_jy_pilot import (
    FIELDS,
    aggregate_report,
    summarize_field_record,
    validate_aggregate_report,
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


def _injection_report(summary):
    injection = summary["calibrated_jy_injection_evaluation"]
    science = summary["science"]
    calibration = injection["electron_calibration_derivation"]["record"]
    rows = []
    for flux_bin in injection["flux_summary"]:
        for index in range(int(flux_bin["n_injected"])):
            baseline_snr = 4.0 + (index % 3) * 0.1
            post_snr = baseline_snr + 1.0
            rows.append({
                "flux_level": flux_bin["flux_level"],
                "x": 100.25 + index,
                "y": 200.75 + index,
                "recovered": int(index < int(flux_bin["n_recovered"])),
                "baseline_local_max_snr_within_match_radius": baseline_snr,
                "post_injection_local_max_snr_within_match_radius": post_snr,
                "local_snr_delta_within_match_radius": post_snr - baseline_snr,
                "post_injection_local_peak_offset_within_match_radius_px": 0.75,
            })
    return {
        "threshold_snr": 5.0,
        "science_provenance": {"science_sha256": science["sha256"]},
        "source_photon_noise": {
            "calibration_record": {
                "calibration_sha256": calibration["calibration_sha256"]
            }
        },
        "local_response_diagnostics": {
            "available": True,
            "match_radius_px": 2.5,
            "extended_radius_px": 5.0,
            "threshold_snr": 5.0,
            "does_not_change_recovery_or_peak_matching": True,
        },
        "flux_summary": [dict(row) for row in injection["flux_summary"]],
        "injections": rows,
    }


def _record(field, summary, **kwargs):
    return summarize_field_record(
        field,
        summary,
        injection_report=_injection_report(summary),
        injection_report_path="data/calibrated_injection/calibrated_jy_injection_recovery.json",
        injection_report_sha256="c" * 64,
        **kwargs,
    )


def test_six_predeclared_fields_include_independent_control_region():
    assert len(FIELDS) == 6
    assert sum(field["role"] == "control" for field in FIELDS) == 1


def test_field_summary_requires_all_provenance_and_jy_gates():
    record = _record(
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
    record = _record(
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
        records.append(_record(
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


def test_zero_recovery_at_all_flux_levels_is_explicitly_flagged_in_aggregate():
    records = []
    for index, field in enumerate(FIELDS):
        summary = _summary()
        summary["science"]["observation_id"] = f"obs-zero-{index}"
        summary["science"]["sha256"] = f"{index + 100:064x}"
        if index == 4:
            for row in summary["calibrated_jy_injection_evaluation"]["flux_summary"]:
                row["n_recovered"] = 0
                row["completeness"] = 0.0
        records.append(_record(
            field, summary, return_code=0, log_path=f"{field['name']}.log"
        ))
    flagged = records[4]
    assert flagged["eligible_for_multi_field_pilot_summary"] is True
    assert flagged["recovery_investigation"]["zero_recovery_at_all_flux_levels"] is True
    report = aggregate_report(
        records, started_utc="2026-11-25T00:00:00Z",
        finished_utc="2026-11-25T00:01:00Z", code_revision="b" * 40,
    )
    assert report["recovery_anomalies"]["fields_with_zero_recovery_at_all_flux_levels"] == [
        "Lupus_III"
    ]
    assert report["recovery_anomalies"]["zero_recovery_is_not_relabelled_as_successful_sensitivity"] is True


def test_aggregate_rejects_duplicate_exposure_identity_from_multifield_gate():
    records = []
    for field in FIELDS:
        records.append(_record(
            field, _summary(), return_code=0, log_path=f"{field['name']}.log"
        ))
    report = aggregate_report(
        records, started_utc="a", finished_utc="b", code_revision=None
    )
    assert report["field_count_completed"] == 6
    assert report["science_observation_ids_unique"] is False
    assert report["scientific_gate_status"]["multi_field_calibrated_jy_evaluation"] == "not_satisfied"



def test_aggregate_rejects_duplicate_or_missing_predeclared_field():
    records = []
    for index, field in enumerate(FIELDS):
        summary = _summary()
        summary["science"]["observation_id"] = f"obs-{index}"
        summary["science"]["sha256"] = f"{index + 1:064x}"
        records.append(_record(
            field, summary, return_code=0, log_path=f"{field['name']}.log"
        ))
    # Six rows are insufficient if one declared field was duplicated.
    records[-1]["field"] = dict(records[0]["field"])
    report = aggregate_report(
        records, started_utc="a", finished_utc="b", code_revision=None
    )
    audit = report["field_manifest_audit"]
    assert audit["valid"] is False
    assert audit["duplicate_fields"]
    assert audit["missing_fields"]
    assert report["scientific_gate_status"]["multi_field_calibrated_jy_evaluation"] == "not_satisfied"


def test_query_report_is_hashed_and_failures_remain_visible():
    records = [
        _record(
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
    record = _record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["science"]["image_unit"] == "MJy / sr"
    assert record["eligible_for_multi_field_pilot_summary"] is True


def test_field_summary_requires_real_poisson_variance_diagnostics_for_all_flux_bins():
    summary = _summary()
    summary["calibrated_jy_injection_evaluation"]["flux_summary"][1].pop(
        "source_poisson_variance_added_image_units2"
    )
    record = _record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["source_poisson_flux_bin_variances_measured"] is False


def test_field_summary_rejects_gain_link_without_live_archive_md5():
    summary = _summary()
    # The gate cross-checks the separately retained electron-derivation and
    # photon-noise records; invalidate both copies to test an absent archive MD5.
    injection = summary["calibrated_jy_injection_evaluation"]
    injection["source_photon_noise"]["calibration_record"][
        "provenance_link"
    ]["artifact_md5_status"] = "not_checked"
    injection["electron_calibration_derivation"]["record"]["provenance_link"][
        "artifact_md5_status"
    ] = "not_checked"
    record = _record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["electron_conversion_live_irsa_relation_and_md5"] is False


def test_field_summary_requires_explicit_pending_review_not_human_signoff():
    summary = _summary()
    summary["calibrated_jy_injection_evaluation"]["source_photon_noise"][
        "independent_human_reviewed"
    ] = True
    record = _record(
        FIELDS[0], summary, return_code=0, log_path="field.log"
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["source_poisson_is_not_mislabelled_human_verified"] is False


def _complete_report():
    records = []
    for index, field in enumerate(FIELDS):
        summary = _summary()
        summary["science"]["observation_id"] = f"obs-{index}"
        summary["science"]["sha256"] = f"{index + 1:064x}"
        record = _record(
            field, summary, return_code=0, log_path=f"{field['name']}.log"
        )
        record["summary_sha256"] = f"{index + 20:064x}"
        record["summary_path"] = f"fields/{field['name']}/real_field_audit_summary.json"
        records.append(record)
    return aggregate_report(
        records, started_utc="2026-11-25T00:00:00Z",
        finished_utc="2026-11-25T00:01:00Z", code_revision="a" * 40,
    )


def test_final_aggregate_gate_requires_exact_field_manifest_and_report_digest():
    report = _complete_report()
    result = validate_aggregate_report(report)
    assert result["valid"] is True
    assert result["verified_field_count"] == 6
    assert result["verified_field_names"] == sorted(field["name"] for field in FIELDS)
    assert result["aggregate_report_sha256"] == report["report_sha256"]


def test_final_aggregate_gate_rejects_duplicate_field_even_when_six_rows_completed():
    report = _complete_report()
    report["field_results"][-1]["field"] = dict(report["field_results"][0]["field"])
    result = validate_aggregate_report(report)
    assert result["valid"] is False
    assert any("field names" in error or "manifest" in error for error in result["errors"])
    assert any("SHA-256" in error for error in result["errors"])


def test_final_aggregate_gate_rejects_modified_or_incomplete_summary():
    report = _complete_report()
    report["field_results"][0]["summary_sha256"] = "not-a-digest"
    result = validate_aggregate_report(report)
    assert result["valid"] is False
    assert any("summary SHA-256" in error for error in result["errors"])

    report = _complete_report()
    report["field_count_completed"] = 5
    result = validate_aggregate_report(report)
    assert result["valid"] is False
    assert any("not all predeclared fields completed" in error for error in result["errors"])


def test_field_summary_requires_bound_per_injection_local_snr_report():
    summary = _summary()
    report = _injection_report(summary)
    report["science_provenance"]["science_sha256"] = "f" * 64
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log",
        injection_report=report, injection_report_sha256="d" * 64,
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["checks"]["injection_report_matches_science_and_calibration"] is False
    assert record["checks"]["local_snr_diagnostics_complete_and_count_bound"] is False


def test_field_summary_requires_all_60_local_snr_rows_and_bin_recovery_consistency():
    summary = _summary()
    report = _injection_report(summary)
    report["injections"].pop()
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log",
        injection_report=report, injection_report_sha256="d" * 64,
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["recovery_investigation"]["local_snr_diagnostics_complete"] is False

    report = _injection_report(summary)
    report["injections"][0]["recovered"] = 0
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log",
        injection_report=report, injection_report_sha256="d" * 64,
    )
    assert record["eligible_for_multi_field_pilot_summary"] is False
    assert record["recovery_investigation"]["injection_report_recovery_counts_match_rows"] is False


def test_field_summary_retains_local_snr_diagnostics_as_diagnostic_not_recovery():
    summary = _summary()
    report = _injection_report(summary)
    record = summarize_field_record(
        FIELDS[0], summary, return_code=0, log_path="field.log",
        injection_report=report, injection_report_sha256="d" * 64,
    )
    investigation = record["recovery_investigation"]
    assert record["eligible_for_multi_field_pilot_summary"] is True
    assert investigation["local_snr_diagnostics_complete"] is True
    assert investigation["local_snr_diagnostic_rows"] == 60
    assert len(investigation["local_snr_flux_bin_diagnostics"]) == 3
    assert "does not replace peak-list recovery" in investigation["interpretation"]


def test_final_aggregate_gate_rejects_missing_injection_report_digest_or_local_snr_rows():
    report = _complete_report()
    report["field_results"][0]["injection_report_sha256"] = None
    result = validate_aggregate_report(report)
    assert result["valid"] is False
    assert any("per-injection report SHA-256" in error for error in result["errors"])

    report = _complete_report()
    report["field_results"][0]["recovery_investigation"]["local_snr_diagnostics_complete"] = False
    result = validate_aggregate_report(report)
    assert result["valid"] is False
    assert any("local per-injection SNR diagnostics" in error for error in result["errors"])
