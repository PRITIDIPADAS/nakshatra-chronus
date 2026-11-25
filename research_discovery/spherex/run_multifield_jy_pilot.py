#!/usr/bin/env python3
"""Sequential multi-region SPHEREx DR1 D2 calibrated Jy injection pilot.

Each field is independently retrieved and passed through run_real_field_audit,
which requires exact science->Spectral-WCS and science->absolute-gain provenance,
a same-release/detector/date solid-angle map, a native MEF compatibility audit,
and a completed local Jy injection/recovery report. This is not a blind four-
baseline benchmark or a YSO population discovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIELDS = (
    {"name": "Taurus_Auriga", "ra_deg": 65.7, "dec_deg": 26.0, "role": "star_forming_region"},
    {"name": "Perseus_NGC1333", "ra_deg": 52.30, "dec_deg": 31.30, "role": "star_forming_region"},
    {"name": "Orion_A", "ra_deg": 83.80, "dec_deg": -5.40, "role": "star_forming_region"},
    {"name": "Rho_Ophiuchi", "ra_deg": 246.75, "dec_deg": -24.60, "role": "star_forming_region"},
    {"name": "Lupus_III", "ra_deg": 242.10, "dec_deg": -39.10, "role": "star_forming_region"},
    {"name": "HighLatitude_Control", "ra_deg": 180.0, "dec_deg": 60.0, "role": "control"},
)
SCHEMA = "chronos-spherex-multifield-jy-pilot/1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def summarize_field_record(
    field: dict,
    summary: dict | None,
    *,
    return_code: int,
    log_path: str,
    error: str | None = None,
    injection_report: dict | None = None,
    injection_report_path: str | None = None,
    injection_report_sha256: str | None = None,
) -> dict:
    """Apply strict per-field gates and bind local-SNR rows to their native exposure."""
    summary = summary if isinstance(summary, dict) else {}
    injection_report = injection_report if isinstance(injection_report, dict) else {}
    audit = summary.get("native_mef_audit") or {}
    compatibility = audit.get("calibration_compatibility") or {}
    gain = summary.get("absolute_gain_validation") or {}
    provenance = summary.get("archive_provenance") or {}
    links = provenance.get("exact_product_links") or {}
    science = summary.get("science") or {}
    injection = summary.get("calibrated_jy_injection_evaluation") or {}
    photon_noise = injection.get("source_photon_noise") or {}
    electron_derivation = injection.get("electron_calibration_derivation") or {}
    electron_record = electron_derivation.get("record") or {}
    gain_link = electron_record.get("provenance_link") or {}
    photon_record = photon_noise.get("calibration_record") or {}
    photon_gain_link = photon_record.get("provenance_link") or {}
    flux_bins = injection.get("flux_summary") or []
    measured_poisson_bins = (
        len(flux_bins) == 3
        and all(
            float(row.get("source_poisson_expected_electrons") or 0.0) > 0
            and float(row.get("source_poisson_variance_added_image_units2") or 0.0) > 0
            for row in flux_bins
        )
    )
    conversion_valid_fraction = photon_noise.get("conversion_map_valid_fraction")
    zero_recovery_all_flux_levels = (
        len(flux_bins) == 3
        and all(
            int(float(row.get("n_recovered") or 0)) == 0
            for row in flux_bins
        )
    )
    report_rows = injection_report.get("injections") or []
    report_bins = injection_report.get("flux_summary") or []
    response_diagnostics = injection_report.get("local_response_diagnostics") or {}
    report_science = injection_report.get("science_provenance") or {}
    report_photon = injection_report.get("source_photon_noise") or {}
    report_calibration = report_photon.get("calibration_record") or {}
    report_science_matches = (
        bool(science.get("sha256"))
        and report_science.get("science_sha256") == science.get("sha256")
    )
    report_calibration_matches = (
        bool(electron_record.get("calibration_sha256"))
        and report_calibration.get("calibration_sha256") == electron_record.get("calibration_sha256")
    )
    report_identity_matches = report_science_matches and report_calibration_matches
    report_bins_match = len(report_bins) == len(flux_bins) == 3
    if report_bins_match:
        for compact_bin, detailed_bin in zip(flux_bins, report_bins):
            try:
                report_bins_match = report_bins_match and (
                    abs(float(compact_bin.get("flux_level")) - float(detailed_bin.get("flux_level"))) <= 1e-12
                    and int(float(compact_bin.get("n_injected"))) == int(float(detailed_bin.get("n_injected")))
                    and int(float(compact_bin.get("n_recovered"))) == int(float(detailed_bin.get("n_recovered")))
                )
            except (TypeError, ValueError):
                report_bins_match = False
    try:
        expected_injection_rows = sum(
            int(float(row.get("n_injected") or 0))
            for row in flux_bins
        ) if flux_bins else 0
    except (TypeError, ValueError, OverflowError):
        expected_injection_rows = -1
        report_bins_match = False
    local_snr_diagnostic_rows = sum(
        isinstance(row, dict)
        and row.get("baseline_local_max_snr_within_match_radius") is not None
        and row.get("post_injection_local_max_snr_within_match_radius") is not None
        and row.get("local_snr_delta_within_match_radius") is not None
        and row.get("post_injection_local_peak_offset_within_match_radius_px") is not None
        for row in report_rows
    )
    source_only_diagnostic_rows = sum(
        isinstance(row, dict)
        and row.get("source_only_local_max_snr_within_match_radius") is not None
        and row.get("source_only_local_peak_offset_within_match_radius_px") is not None
        and row.get("source_only_peak_list_recovered") in (0, 1)
        and row.get("source_only_diagnostic_uses_injected_variance") is True
        and row.get("source_only_reference_local_max_snr_preinjection_variance") is not None
        and row.get("source_only_reference_uses_preinjection_variance") is True
        for row in report_rows
    )
    peak_selection_rule = response_diagnostics.get("peak_selection_rule") or {}
    peak_selection_diagnostic_rows = sum(
        isinstance(row, dict)
        and "post_injection_local_peak_selected_by_exact_peak_rule" in row
        and "post_injection_local_peak_detector_window_max_snr" in row
        and "post_injection_local_peak_competitor_snr_margin" in row
        and "post_injection_local_peak_suppressed_by_stronger_neighbor" in row
        and "nearest_selected_peak_distance_px" in row
        and "nearest_selected_peak_x_px" in row
        and "nearest_selected_peak_y_px" in row
        and "nearest_selected_peak_snr" in row
        for row in report_rows
    )
    report_rows_match_bins = report_bins_match and len(report_rows) == expected_injection_rows
    if report_rows_match_bins:
        for compact_bin in flux_bins:
            try:
                level = float(compact_bin.get("flux_level"))
                bin_rows = [
                    row for row in report_rows
                    if abs(float(row.get("flux_level")) - level) <= 1e-12
                ]
                report_rows_match_bins = report_rows_match_bins and (
                    len(bin_rows) == int(float(compact_bin.get("n_injected")))
                    and sum(int(row.get("recovered", 0)) for row in bin_rows)
                    == int(float(compact_bin.get("n_recovered")))
                )
            except (TypeError, ValueError, OverflowError):
                report_rows_match_bins = False
    peak_selection_diagnostics_complete = (
        peak_selection_rule.get("exact_production_predicate_recorded_per_injection") is True
        and peak_selection_rule.get("window_width_px") == 11
        and peak_selection_rule.get("minimum_separation_px") == 5
        and report_identity_matches
        and report_rows_match_bins
        and expected_injection_rows > 0
        and peak_selection_diagnostic_rows == len(report_rows) == expected_injection_rows
    )
    local_snr_diagnostics_complete = (
        response_diagnostics.get("available") is True
        and response_diagnostics.get("does_not_change_recovery_or_peak_matching") is True
        and report_identity_matches
        and report_rows_match_bins
        and expected_injection_rows > 0
        and local_snr_diagnostic_rows == len(report_rows) == expected_injection_rows
    )
    source_only_bins = injection_report.get("new_unmatched_peak_summary") or []
    source_only_flux_bin_counts_match = (
        isinstance(source_only_bins, list)
        and len(source_only_bins) == len(flux_bins) == 3
        and report_rows_match_bins
    )
    if source_only_flux_bin_counts_match:
        for compact_bin, source_bin in zip(flux_bins, source_only_bins):
            try:
                level = float(compact_bin.get("flux_level"))
                source_level = float(source_bin.get("flux_level"))
                n_injected = int(float(compact_bin.get("n_injected")))
                reported_count = float(source_bin.get("source_only_peak_list_recovered_count"))
                reported_fraction = float(source_bin.get("source_only_peak_list_recovered_fraction"))
                bin_rows = [
                    row for row in report_rows
                    if abs(float(row.get("flux_level")) - level) <= 1e-12
                ]
                row_count = sum(
                    int(row.get("source_only_peak_list_recovered", 0))
                    for row in bin_rows
                )
                source_only_flux_bin_counts_match = (
                    source_only_flux_bin_counts_match
                    and abs(source_level - level) <= 1e-12
                    and n_injected > 0
                    and len(bin_rows) == n_injected
                    and reported_count >= 0
                    and reported_count <= n_injected
                    and reported_count.is_integer()
                    and int(reported_count) == row_count
                    and 0.0 <= reported_fraction <= 1.0
                    and abs(reported_fraction - row_count / n_injected) <= 1e-12
                )
            except (TypeError, ValueError, OverflowError, ZeroDivisionError):
                source_only_flux_bin_counts_match = False
    source_only_diagnostics_complete = (
        response_diagnostics.get("isolated_source_response_available") is True
        and response_diagnostics.get("source_only_uses_injected_variance") is True
        and response_diagnostics.get("source_only_preinjection_variance_reference_available") is True
        and response_diagnostics.get("source_only_peak_list_recovery_is_diagnostic_not_primary") is True
        and report_identity_matches
        and report_rows_match_bins
        and expected_injection_rows > 0
        and source_only_diagnostic_rows == len(report_rows) == expected_injection_rows
        and source_only_flux_bin_counts_match
    )
    diagnostic_flux_bins = []
    if report_bins_match:
        for compact_bin in flux_bins:
            try:
                level = float(compact_bin.get("flux_level"))
                bin_rows = [
                    row for row in report_rows
                    if abs(float(row.get("flux_level")) - level) <= 1e-12
                ]
                def median_metric(key):
                    values = sorted(
                        float(row[key]) for row in bin_rows
                        if row.get(key) is not None
                    )
                    if not values:
                        return None
                    middle = len(values) // 2
                    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
                threshold = float(injection_report.get("threshold_snr", 5.0))
                diagnostic_flux_bins.append({
                    "flux_level_jy": level,
                    "injection_rows": len(bin_rows),
                    "recovered_rows": sum(int(row.get("recovered", 0)) for row in bin_rows),
                    "baseline_local_max_snr_ge_threshold": sum(
                        float(row["baseline_local_max_snr_within_match_radius"]) >= threshold
                        for row in bin_rows
                        if row.get("baseline_local_max_snr_within_match_radius") is not None
                    ),
                    "post_injection_local_max_snr_ge_threshold": sum(
                        float(row["post_injection_local_max_snr_within_match_radius"]) >= threshold
                        for row in bin_rows
                        if row.get("post_injection_local_max_snr_within_match_radius") is not None
                    ),
                    "median_baseline_local_max_snr": median_metric("baseline_local_max_snr_within_match_radius"),
                    "median_post_injection_local_max_snr": median_metric("post_injection_local_max_snr_within_match_radius"),
                    "median_local_snr_delta": median_metric("local_snr_delta_within_match_radius"),
                    "median_source_only_local_max_snr": median_metric("source_only_local_max_snr_within_match_radius"),
                    "median_source_only_reference_local_max_snr_preinjection_variance": median_metric(
                        "source_only_reference_local_max_snr_preinjection_variance"
                    ),
                    "source_only_peak_list_recovered_count": sum(
                        int(row.get("source_only_peak_list_recovered", 0))
                        for row in bin_rows
                    ),
                    "source_only_peak_list_recovered_fraction": (
                        sum(int(row.get("source_only_peak_list_recovered", 0)) for row in bin_rows)
                        / len(bin_rows) if bin_rows else None
                    ),
                })
            except (TypeError, ValueError, OverflowError):
                diagnostic_flux_bins.append({
                    "flux_level_jy": compact_bin.get("flux_level"),
                    "diagnostic_summary_error": "invalid per-injection diagnostic value",
                })
    recovery_investigation = {
        "zero_recovery_at_all_flux_levels": zero_recovery_all_flux_levels,
        "flux_bin_recoveries": [
            {
                "flux_level_jy": row.get("flux_level"),
                "n_injected": row.get("n_injected"),
                "n_recovered": row.get("n_recovered"),
                "completeness": row.get("completeness"),
            }
            for row in flux_bins
        ],
        "injection_rows": len(report_rows),
        "expected_injection_rows": expected_injection_rows,
        "local_snr_diagnostic_rows": local_snr_diagnostic_rows,
        "local_snr_diagnostics_complete": local_snr_diagnostics_complete,
        "source_only_diagnostic_rows": source_only_diagnostic_rows,
        "source_only_flux_bin_counts_match_injection_rows": source_only_flux_bin_counts_match,
        "source_only_diagnostics_complete": source_only_diagnostics_complete,
        "peak_selection_diagnostic_rows": peak_selection_diagnostic_rows,
        "peak_selection_diagnostics_complete": peak_selection_diagnostics_complete,
        "injection_report_identity_matches_science_and_gain": report_identity_matches,
        "injection_report_flux_bins_match_compact_summary": report_bins_match,
        "injection_report_recovery_counts_match_rows": report_rows_match_bins,
        "injection_report_sha256": injection_report_sha256,
        "injection_report_path": injection_report_path,
        "local_snr_flux_bin_diagnostics": diagnostic_flux_bins,
        "interpretation": (
            "Zero recovery at every tested flux level is retained as a field-level anomaly for investigation; "
            "it is not converted to a successful sensitivity result."
            if zero_recovery_all_flux_levels else
            "Per-field recovery counts are retained without pooling field-specific flux levels. Local maximum SNR is diagnostic only and does not replace peak-list recovery."
        ),
    }

    checks = {
        "native_mef_audit_compatible": compatibility.get("status") == "compatible",
        "spectral_wcs_exact_provenance_link": bool(links.get("spectral_wcs")),
        "absolute_gain_exact_provenance_link": bool(links.get("absolute_gain")),
        "solid_angle_explicitly_supplemental": provenance.get("solid_angle_map_pipeline_input") is False,
        "absolute_gain_pixels_masked_not_filled": bool(gain.get("invalid_pixels_are_not_interpolated")),
        "absolute_gain_structure_valid": gain.get("status") in {
            "structure_units_pass_with_invalid_pixels_explicitly_masked",
            "structure_and_units_pass",
        },
        "jy_injection_completed": injection.get("status") == "completed",
        "source_poisson_noise_modelled": bool(photon_noise.get("enabled") and photon_noise.get("physically_modelled")),
        "source_poisson_is_not_mislabelled_human_verified": (
            photon_noise.get("independent_human_reviewed") is False
            and photon_noise.get("calibration_review_status") == "pending"
        ),
        "source_poisson_flux_bin_variances_measured": measured_poisson_bins,
        "injection_report_matches_science_and_calibration": report_identity_matches,
        "local_snr_diagnostics_complete_and_count_bound": local_snr_diagnostics_complete,
        "source_only_diagnostics_complete_and_count_bound": source_only_diagnostics_complete,
        "source_only_flux_bin_counts_match_injection_rows": source_only_flux_bin_counts_match,
        "peak_selection_diagnostics_complete_and_count_bound": peak_selection_diagnostics_complete,
        "electron_conversion_map_valid_fraction_gt_99pct": (
            isinstance(conversion_valid_fraction, (int, float))
            and 0.99 < float(conversion_valid_fraction) <= 1.0
        ),
        "electron_conversion_derived_from_exact_gain": bool(
            electron_derivation.get("absolute_gain_uri")
            and electron_derivation.get("absolute_gain_sha256")
            and electron_record.get("verification_status") == "derived_pending_independent_review"
            and electron_record.get("calibration_uri") == electron_derivation.get("absolute_gain_uri")
            and electron_record.get("calibration_sha256") == electron_derivation.get("absolute_gain_sha256")
        ),
        "electron_conversion_live_irsa_relation_and_md5": (
            gain_link.get("input_table") == "spherex.provenance_input"
            and gain_link.get("status") == "verified_from_live_irsa_foreign_key_query"
            and gain_link.get("artifact_md5_status") == "pass"
            and gain_link.get("inputid") == gain_link.get("calibration_planeid")
            and gain_link.get("outputid") == gain_link.get("science_planeid")
            and gain_link.get("science_native_uri") == electron_record.get("science_source_uri")
            and gain_link.get("calibration_native_uri") == electron_record.get("calibration_uri")
            and gain_link.get("calibration_sha256") == electron_record.get("calibration_sha256")
            and photon_gain_link.get("input_table") == "spherex.provenance_input"
            and photon_gain_link.get("status") == "verified_from_live_irsa_foreign_key_query"
            and photon_gain_link.get("artifact_md5_status") == "pass"
            and photon_gain_link.get("inputid") == photon_gain_link.get("calibration_planeid")
            and photon_gain_link.get("outputid") == photon_gain_link.get("science_planeid")
            and photon_gain_link.get("calibration_sha256") == electron_record.get("calibration_sha256")
            and photon_record.get("calibration_sha256") == electron_record.get("calibration_sha256")
        ),
        "electron_conversion_review_status_is_explicit": electron_derivation.get("independent_review_status") == "pending",
        "science_native_uri_present": bool(science.get("uri")),
        "science_sha256_present": bool(science.get("sha256")),
        "science_detector_is_D2": science.get("detector") == "D2",
        "science_release_is_DR1": str(science.get("release", "")).lower() == "dr1",
        "subprocess_exit_zero": return_code == 0,
        "no_runner_error": error is None,
    }
    eligible = all(checks.values())
    metrics = {
        "nominal_local_5sigma_sensitivity_jy": injection.get("five_sigma_sensitivity_jy"),
        "flux_summary": injection.get("flux_summary"),
        "baseline_detections": injection.get("n_baseline_detections"),
        "source_poisson_noise": photon_noise,
        "electron_calibration_derivation": electron_derivation,
    }
    return {
        "field": field,
        "status": "completed_calibrated_jy_pilot" if eligible else "incomplete_or_review_required",
        "eligible_for_multi_field_pilot_summary": eligible,
        "checks": checks,
        "metrics": {**metrics, "recovery_investigation": recovery_investigation},
        "recovery_investigation": recovery_investigation,
        "science": {
            key: (science.get("image_bunit") if key == "image_unit" else science.get(key))
            for key in ("uri", "sha256", "observation_id", "detector", "release",
                        "pipeline_version", "processing_date", "exposure_time_s", "image_unit")
        },
        "calibration_uris": {
            key: ((summary.get("selected_products") or {}).get(key) or {}).get("uri")
            for key in ("spectral_wcs", "solid_angle", "absolute_gain")
        },
        "calibration_link_status": {
            key: (links.get(key) or {}).get("status")
            for key in ("spectral_wcs", "absolute_gain")
        },
        "archive_input_relation_count": provenance.get("input_relation_count"),
        "injection_report_sha256": injection_report_sha256,
        "injection_report_path": injection_report_path,
        "error": error,
        "return_code": return_code,
        "log_path": log_path,
    }


def audit_predeclared_field_manifest(records: list[dict]) -> dict:
    """Require every predeclared field and role exactly once in the aggregate."""
    expected = {row["name"]: row["role"] for row in FIELDS}
    names = [str((row.get("field") or {}).get("name") or "") for row in records]
    counts = {name: names.count(name) for name in set(names)}
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    missing = sorted(name for name in expected if counts.get(name, 0) == 0)
    unexpected = sorted(name for name in counts if name not in expected)
    role_mismatches = sorted(
        name for name, role in expected.items()
        if counts.get(name) == 1
        and next((row.get("field") or {}).get("role") for row in records
                 if (row.get("field") or {}).get("name") == name) != role
    )
    valid = (
        len(records) == len(FIELDS)
        and not duplicates and not missing and not unexpected and not role_mismatches
    )
    return {
        "valid": valid,
        "expected_field_count": len(FIELDS),
        "returned_field_count": len(records),
        "missing_fields": missing,
        "duplicate_fields": duplicates,
        "unexpected_fields": unexpected,
        "role_mismatches": role_mismatches,
        "field_order": names,
    }


def aggregate_report(records: list[dict], *, started_utc: str,
                     finished_utc: str, code_revision: str | None) -> dict:
    """Aggregate field-level completeness without assuming equal flux thresholds."""
    completed = [row for row in records if row["eligible_for_multi_field_pilot_summary"]]
    failed = [row for row in records if not row["eligible_for_multi_field_pilot_summary"]]
    field_manifest = audit_predeclared_field_manifest(records)
    zero_recovery_fields = [
        row["field"]["name"] for row in records
        if (row.get("recovery_investigation") or {}).get("zero_recovery_at_all_flux_levels") is True
    ]
    fields_missing_local_snr_diagnostics = [
        row["field"]["name"] for row in records
        if (row.get("recovery_investigation") or {}).get("local_snr_diagnostics_complete") is not True
    ]
    results = {
        "schema": SCHEMA,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "code_revision": code_revision,
        "archive": "NASA/IPAC IRSA SPHEREx DR1",
        "requested_detector": "D2",
        "predeclared_fields": list(FIELDS),
        "field_count_requested": len(FIELDS),
        "field_count_returned": len(records),
        "field_manifest_audit": field_manifest,
        "field_count_completed": len(completed),
        "field_count_incomplete": len(failed),
        "field_results": records,
        "completed_fields": [row["field"]["name"] for row in completed],
        "incomplete_fields": [row["field"]["name"] for row in failed],
        "recovery_anomalies": {
            "fields_with_zero_recovery_at_all_flux_levels": zero_recovery_fields,
            "fields_missing_complete_local_snr_diagnostics": fields_missing_local_snr_diagnostics,
            "zero_recovery_is_not_relabelled_as_successful_sensitivity": True,
        },
        "science_observation_ids_unique": (
            len({row["science"].get("observation_id") for row in completed})
            == len(completed)
        ),
        "science_file_hashes_unique": (
            len({row["science"].get("sha256") for row in completed}) == len(completed)
        ),
        "per_field_flux_summaries": {
            row["field"]["name"]: row["metrics"]["flux_summary"] for row in completed
        },
        "statistical_boundary": [
            "Flux levels are field-specific multiples of each field's measured local 5-sigma sensitivity; do not pool them as identical absolute flux bins.",
            "Each injection/recovery result is local to one detector position and one native exposure.",
            "Region centers are predeclared and widely separated, but survey overlap and statistical independence are not independently custodian-attested.",
            "Every predeclared field name and role must appear exactly once; duplicate, missing, unexpected or role-mismatched fields invalidate the aggregate.",
            "Injection truth and random seed are visible to this evaluation; this is not a blind benchmark.",
            "The four CHRONOS methods are not run by this workflow; no comparative advantage is measured.",
            "No source classification or YSO population estimate is produced by a completeness injection test.",
            "The solid-angle map is supplemental; only Spectral-WCS and absolute-gain products are required to have exact provenance_input links.",
            "The absolute-gain matrix is used for calibration validation and must not be applied a second time to Level-2 science pixels.",
            "Zero recovery at every tested flux level is retained as a field-level anomaly; it must be investigated and is not hidden by a passed archive or calibration gate.",
        ],
        "scientific_gate_status": {
            "single_field_real_data_pilot": "completed" if completed else "not_completed",
            "multi_field_calibrated_jy_evaluation": (
                "completed_exploratory_for_predeclared_regions"
                if len(completed) == len(FIELDS)
                and field_manifest["valid"]
                and results_unique_placeholder(completed)
                else "not_satisfied"
            ),
            "independent_blind_four_baseline_benchmark": "not_satisfied",
            "population_level_yso_discovery": "not_satisfied",
            "independent_astronomical_reproduction": "not_satisfied",
            "validated_scientific_release": "not_satisfied",
        },
    }
    results["report_sha256"] = sha256_json(results)
    return results


def results_unique_placeholder(completed: list[dict]) -> bool:
    obs = [row["science"].get("observation_id") for row in completed]
    hashes = [row["science"].get("sha256") for row in completed]
    return (
        all(obs) and all(hashes)
        and len(set(obs)) == len(obs)
        and len(set(hashes)) == len(hashes)
    )


def validate_aggregate_report(report: dict) -> dict:
    """Fail closed unless the aggregate itself proves the complete field contract."""
    errors = []
    if not isinstance(report, dict):
        return {"valid": False, "errors": ["aggregate report must be an object"]}

    expected = {row["name"]: row["role"] for row in FIELDS}
    audit = report.get("field_manifest_audit") or {}
    if audit.get("valid") is not True:
        errors.append("predeclared field manifest is missing or invalid")
    if audit.get("expected_field_count") != len(FIELDS):
        errors.append("field manifest expected count differs from the predeclared protocol")
    if audit.get("returned_field_count") != len(FIELDS):
        errors.append("field manifest returned count differs from the predeclared protocol")
    if any(audit.get(key) for key in (
        "missing_fields", "duplicate_fields", "unexpected_fields", "role_mismatches"
    )):
        errors.append("field manifest contains missing, duplicate, unexpected or role-mismatched rows")

    fields = report.get("field_results")
    if not isinstance(fields, list) or len(fields) != len(FIELDS):
        errors.append("aggregate must contain exactly one result row per predeclared field")
        fields = fields if isinstance(fields, list) else []
    names = [str((row.get("field") or {}).get("name") or "") for row in fields]
    if set(names) != set(expected) or len(names) != len(expected):
        errors.append("aggregate field names do not exactly match the predeclared field set")
    for row in fields:
        field = row.get("field") or {}
        name = str(field.get("name") or "<unnamed>")
        if expected.get(name) != field.get("role"):
            errors.append(f"{name}: field role differs from the predeclared manifest")
        if row.get("eligible_for_multi_field_pilot_summary") is not True:
            errors.append(f"{name}: field-level eligibility gate did not pass")
        checks = row.get("checks")
        if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
            errors.append(f"{name}: one or more strict field checks are false or absent")
        summary_digest = str(row.get("summary_sha256") or "").lower()
        if len(summary_digest) != 64 or any(ch not in "0123456789abcdef" for ch in summary_digest):
            errors.append(f"{name}: real-field summary SHA-256 is missing or invalid")
        injection_digest = str(row.get("injection_report_sha256") or "").lower()
        if len(injection_digest) != 64 or any(ch not in "0123456789abcdef" for ch in injection_digest):
            errors.append(f"{name}: per-injection report SHA-256 is missing or invalid")
        investigation = row.get("recovery_investigation") or {}
        if investigation.get("local_snr_diagnostics_complete") is not True:
            errors.append(f"{name}: local per-injection SNR diagnostics are incomplete or unbound")
        if investigation.get("source_only_diagnostics_complete") is not True:
            errors.append(f"{name}: isolated source-only response diagnostics are incomplete or unbound")
        if investigation.get("source_only_flux_bin_counts_match_injection_rows") is not True:
            errors.append(f"{name}: source-only peak-list counts do not match the detailed injection rows")
        if investigation.get("peak_selection_diagnostics_complete") is not True:
            errors.append(f"{name}: exact detector peak-selection diagnostics are incomplete or unbound")
        if investigation.get("injection_report_identity_matches_science_and_gain") is not True:
            errors.append(f"{name}: per-injection report is not bound to the science/gain pair")
        science = row.get("science") or {}
        science_digest = str(science.get("sha256") or "").lower()
        if len(science_digest) != 64 or any(ch not in "0123456789abcdef" for ch in science_digest):
            errors.append(f"{name}: native science SHA-256 is missing or invalid")
        if not science.get("observation_id"):
            errors.append(f"{name}: science observation ID is missing")
        if science.get("detector") != "D2" or str(science.get("release", "")).lower() != "dr1":
            errors.append(f"{name}: science product is not the requested DR1 D2 product")

    if report.get("field_count_requested") != len(FIELDS):
        errors.append("requested field count differs from the predeclared protocol")
    if report.get("field_count_returned") != len(FIELDS):
        errors.append("returned field count differs from the predeclared protocol")
    if report.get("field_count_completed") != len(FIELDS):
        errors.append("not all predeclared fields completed")
    if report.get("field_count_incomplete") != 0:
        errors.append("aggregate contains incomplete fields")
    if report.get("science_observation_ids_unique") is not True:
        errors.append("science observation IDs are not unique")
    if report.get("science_file_hashes_unique") is not True:
        errors.append("native science-file SHA-256 values are not unique")

    gate = (report.get("scientific_gate_status") or {}).get("multi_field_calibrated_jy_evaluation")
    if gate != "completed_exploratory_for_predeclared_regions":
        errors.append("multi-field exploratory scientific gate is not satisfied")

    # The report digest is calculated over the complete report before this
    # field is inserted. Recompute it so post-hoc edits cannot pass unnoticed.
    claimed_digest = str(report.get("report_sha256") or "").lower()
    digest_payload = dict(report)
    digest_payload.pop("report_sha256", None)
    actual_digest = sha256_json(digest_payload)
    if len(claimed_digest) != 64 or claimed_digest != actual_digest:
        errors.append("aggregate report SHA-256 is missing or does not match its contents")

    return {
        "valid": not errors,
        "errors": errors,
        "verified_field_count": len(fields),
        "verified_field_names": sorted(names),
        "aggregate_report_sha256": actual_digest,
    }


def run_field(field: dict, root: Path, *, release: str,
              bandpass: str, code_revision: str | None) -> dict:
    field_dir = root / "fields" / field["name"]
    field_dir.mkdir(parents=True, exist_ok=True)
    log_path = field_dir / "runner.log"
    command = [
        sys.executable, "-m", "research_discovery.spherex.run_real_field_audit",
        "--field", f"{field['name']},{field['ra_deg']},{field['dec_deg']}",
        "--bandpass", bandpass,
        "--release", release,
        "--out", str(field_dir / "data"),
    ]
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    summary_path = field_dir / "data" / "real_field_audit_summary.json"
    summary = None
    error = None
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            error = f"summary_read_error:{type(exc).__name__}:{exc}"
    else:
        error = "field runner did not produce real_field_audit_summary.json"
    if completed.returncode != 0:
        error = error or f"field runner exited with status {completed.returncode}"
    injection_report_path = (
        summary_path.parent / "calibrated_injection" / "calibrated_jy_injection_recovery.json"
    )
    injection_report = None
    injection_report_sha256 = None
    if injection_report_path.is_file():
        try:
            injection_report = json.loads(injection_report_path.read_text(encoding="utf-8"))
            injection_report_sha256 = sha256_file(injection_report_path)
        except (OSError, json.JSONDecodeError) as exc:
            error = error or f"injection_report_read_error:{type(exc).__name__}:{exc}"
    record = summarize_field_record(
        field,
        summary,
        return_code=completed.returncode,
        log_path=str(log_path.relative_to(root)),
        error=error,
        injection_report=injection_report,
        injection_report_path=(
            str(injection_report_path.relative_to(root))
            if injection_report_path.is_file() else None
        ),
        injection_report_sha256=injection_report_sha256,
    )
    if summary_path.is_file():
        record["summary_sha256"] = sha256_file(summary_path)
        record["summary_path"] = str(summary_path.relative_to(root))
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/spherex_multifield_jy_pilot"))
    parser.add_argument("--release", choices=("dr1",), default="dr1")
    parser.add_argument("--bandpass", default="SPHEREx-D2")
    parser.add_argument("--code-revision", default=None)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    records = []
    for index, field in enumerate(FIELDS, start=1):
        print(f"[{index}/{len(FIELDS)}] {field['name']}: retrieving a native D2 Level-2 exposure", flush=True)
        record = run_field(field, args.out, release=args.release,
                           bandpass=args.bandpass, code_revision=args.code_revision)
        records.append(record)
        print(json.dumps({
            "field": field["name"],
            "status": record["status"],
            "checks_passed": sum(record["checks"].values()),
            "checks_total": len(record["checks"]),
            "error": record["error"],
        }), flush=True)
        if args.stop_on_error and not record["eligible_for_multi_field_pilot_summary"]:
            break
    report = aggregate_report(
        records, started_utc=started,
        finished_utc=datetime.now(timezone.utc).isoformat(),
        code_revision=args.code_revision,
    )
    report_path = args.out / "multi_field_jy_pilot_summary.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    final_gate = validate_aggregate_report(report)
    print(json.dumps({
        "report": str(report_path),
        "report_sha256": report["report_sha256"],
        "field_count_requested": report["field_count_requested"],
        "field_count_returned": report.get("field_count_returned"),
        "field_count_completed": report["field_count_completed"],
        "field_count_incomplete": report["field_count_incomplete"],
        "gate_status": report["scientific_gate_status"]["multi_field_calibrated_jy_evaluation"],
        "strict_aggregate_validation": final_gate,
    }, indent=2), flush=True)
    if not final_gate["valid"]:
        raise SystemExit(
            "Strict multi-field acceptance validation failed: "
            + "; ".join(final_gate["errors"])
            + f". Inspect {report_path} and the per-field runner logs."
        )


if __name__ == "__main__":
    main()
