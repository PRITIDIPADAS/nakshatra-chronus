"""Fail-closed coverage audit before a single population investigation.

This gate checks the shape of supplied evidence. It does not independently
authenticate a classification, a null control, or an assertion of field
independence. A feature-evolution sample must cover the feature and both
continuum sidebands repeatedly within the same distinct epochs.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from chronos_causal.wavelength_gate import validate_science_wavelength
from .selection import fit_selection_function, predict_selection_probability


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a positive integer") from None
    if number < 1 or number != value:
        raise ValueError(f"{label} must be a positive integer")
    return number


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def assess_population_coverage(
    fields: Sequence[Mapping[str, Any]],
    *,
    target_class: str = "young_stellar_object",
    feature_interval_um: Sequence[float],
    blue_continuum_um: Sequence[float],
    red_continuum_um: Sequence[float],
    minimum_independent_fields: int = 5,
    minimum_epochs_per_source: int = 3,
    minimum_feature_samples: int = 3,
    minimum_continuum_samples: int = 4,
    minimum_median_snr: float = 5.0,
    minimum_completeness: float = 0.5,
    selection_trials: Sequence[Mapping[str, Any]] | None = None,
    selection_bin_spec: Mapping[str, Any] | None = None,
    minimum_trials_per_selection_cell: int = 20,
    minimum_fields_per_cell: int | None = None,
    minimum_selection_probability: float = 0.05,
) -> dict[str, Any]:
    """Audit field, source, wavelength, cadence, injection and null-control coverage.

    null_control_to_science_exposure_ratio is science solid-angle times time
    divided by null-control solid-angle times time. It is required because raw
    null counts cannot be subtracted from science counts without a scale.
    """
    if not fields:
        raise ValueError("at least one field is required")
    target_class = str(target_class).strip()
    if not target_class:
        raise ValueError("target_class must be non-empty")

    minimum_independent_fields = _positive_int(
        minimum_independent_fields, "minimum_independent_fields"
    )
    minimum_epochs_per_source = _positive_int(
        minimum_epochs_per_source, "minimum_epochs_per_source"
    )
    minimum_feature_samples = _positive_int(
        minimum_feature_samples, "minimum_feature_samples"
    )
    minimum_continuum_samples = _positive_int(
        minimum_continuum_samples, "minimum_continuum_samples"
    )
    minimum_fields_per_cell = _positive_int(
        minimum_independent_fields if minimum_fields_per_cell is None else minimum_fields_per_cell,
        "minimum_fields_per_cell",
    )
    if minimum_fields_per_cell > minimum_independent_fields:
        raise ValueError("minimum_fields_per_cell cannot exceed minimum_independent_fields")
    if not math.isfinite(float(minimum_median_snr)) or minimum_median_snr < 0:
        raise ValueError("minimum_median_snr must be finite and non-negative")
    if not math.isfinite(float(minimum_completeness)) or not 0 < minimum_completeness <= 1:
        raise ValueError("minimum_completeness must be in (0, 1]")

    intervals = [feature_interval_um, blue_continuum_um, red_continuum_um]
    if any(len(interval) != 2 for interval in intervals):
        raise ValueError("feature and continuum intervals require lower and upper wavelengths")
    try:
        feature, blue, red = [
            tuple(float(value) for value in interval) for interval in intervals
        ]
    except (TypeError, ValueError):
        raise ValueError("wavelength intervals must contain finite numbers") from None
    if any(not all(math.isfinite(value) for value in interval) for interval in (feature, blue, red)):
        raise ValueError("wavelength intervals must contain finite numbers")
    if not (0 < blue[0] < blue[1] < feature[0] < feature[1] < red[0] < red[1]):
        raise ValueError("continuum and feature intervals must be positive, ordered and non-overlapping")

    selection_fit: dict[str, Any] | None = None
    selection_error: str | None = None
    if selection_trials and selection_bin_spec:
        try:
            selection_fit = fit_selection_function(
                selection_trials, selection_bin_spec, field_records=fields,
                minimum_trials_per_cell=minimum_trials_per_selection_cell,
                minimum_independent_fields=minimum_independent_fields,
                minimum_fields_per_cell=minimum_fields_per_cell,
                minimum_detection_probability=minimum_selection_probability,
            )
        except (ValueError, TypeError, KeyError, ImportError) as exc:
            selection_error = str(exc)
    else:
        selection_error = "real-field multidimensional injection trials and predeclared bin edges are required"

    # Detect reused source identities before evaluating any one field. Reusing
    # one catalogue source in overlapping fields must not inflate the sample.
    source_field_memberships: dict[str, set[str]] = defaultdict(set)
    for field in fields:
        field_id = str(field.get("field_id", "")).strip()
        for source in field.get("sources") or []:
            source_id = str(source.get("source_id", "")).strip()
            if source_id:
                source_field_memberships[source_id].add(field_id)

    selection_field_counts = {
        row["field_id"]: row
        for row in (selection_fit or {}).get("field_trial_counts", [])
    }
    field_reports: list[dict[str, Any]] = []
    eligible_sources: list[dict[str, Any]] = []
    seen_field_ids: set[str] = set()
    failure_counts: dict[str, int] = {}

    for field in fields:
        field_id = str(field.get("field_id", "")).strip()
        reasons: list[str] = []
        if not field_id:
            reasons.append("field_id_missing")
        elif field_id in seen_field_ids:
            reasons.append("duplicate_field_id")
        seen_field_ids.add(field_id)

        dataset_class = str(field.get("dataset_class", field.get("data_class", "unverified"))).lower()
        if dataset_class != "real":
            reasons.append("field_not_labelled_real")
        if field.get("independent_field") is not True:
            reasons.append("independence_not_attested")
        if not str(field.get("null_control_id", "")).strip():
            reasons.append("null_control_not_identified")
        if selection_fit is None or selection_fit.get("supported") is not True:
            reasons.append("multidimensional_selection_function_missing_or_unsupported")

        area = _finite_positive(field.get("area_deg2"))
        if area is None:
            reasons.append("survey_area_missing_or_invalid")
        baseline_days = _finite_positive(field.get("baseline_days"))
        if baseline_days is None:
            reasons.append("survey_baseline_missing_or_invalid")
        null_area = _finite_positive(field.get("null_control_area_deg2"))
        if null_area is None:
            reasons.append("null_control_area_missing_or_invalid")
        null_days = _finite_positive(field.get("null_control_baseline_days"))
        if null_days is None:
            reasons.append("null_control_baseline_missing_or_invalid")
        null_ratio = _finite_positive(field.get("null_control_to_science_exposure_ratio"))
        if null_ratio is None:
            reasons.append("null_control_exposure_ratio_missing_or_invalid")
        if all(value is not None for value in (area, baseline_days, null_area, null_days, null_ratio)):
            derived_ratio = (area * baseline_days) / (null_area * null_days)
            if not math.isclose(null_ratio, derived_ratio, rel_tol=1e-6, abs_tol=1e-12):
                reasons.append("null_control_exposure_ratio_inconsistent_with_area_time")

        injected = field.get("n_injected", 0)
        recovered = field.get("n_recovered", 0)
        try:
            injected_count = int(injected)
            recovered_count = int(recovered)
            if isinstance(injected, bool) or isinstance(recovered, bool):
                raise ValueError
            if injected_count != injected or recovered_count != recovered:
                raise ValueError
            if injected_count <= 0 or recovered_count < 0 or recovered_count > injected_count:
                raise ValueError
            completeness = recovered_count / injected_count
        except (TypeError, ValueError, OverflowError):
            completeness = None
            reasons.append("injection_completeness_missing")
        else:
            if completeness < minimum_completeness:
                reasons.append("completeness_below_threshold")
            if selection_fit is not None and selection_fit.get("supported") is True:
                field_trials = selection_field_counts.get(field_id)
                if field_trials is None:
                    reasons.append("selection_trials_missing_for_field")
                elif (
                    int(field_trials.get("injected", -1)) != injected_count
                    or int(field_trials.get("recovered", -1)) != recovered_count
                ):
                    reasons.append("selection_trial_count_mismatch")

        source_reports: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for source in field.get("sources") or []:
            source_id = str(source.get("source_id", "")).strip()
            source_reasons: list[str] = []
            if not source_id:
                source_reasons.append("source_id_missing")
            elif source_id in seen_source_ids:
                source_reasons.append("duplicate_source_id_within_field")
            seen_source_ids.add(source_id)

            if source_id and len(source_field_memberships[source_id]) > 1:
                source_reasons.append("source_reused_across_fields")
            if str(source.get("sample_class", "")).lower() != target_class:
                source_reasons.append("sample_class_mismatch")
            selection_prediction: dict[str, Any] = {
                "status": "selection_function_unavailable",
                "selection_probability": None,
                "selection_weight": None,
            }
            if selection_fit is not None and selection_fit.get("supported") is True:
                covariates = source.get("selection_covariates")
                if not isinstance(covariates, Mapping):
                    source_reasons.append("selection_covariates_missing")
                else:
                    selection_prediction = predict_selection_probability(selection_fit, covariates)
                    if selection_prediction.get("status") != "supported":
                        source_reasons.append("source_outside_supported_selection_function")
            if not str(source.get("classification_reference", "")).strip():
                source_reasons.append("independent_classification_reference_missing")

            valid_rows: list[tuple[float, float, float, str]] = []
            measurement_keys: set[tuple[str, float, str]] = set()
            valid_measurement_ids: set[str] = set()
            valid_observation_ids: set[str] = set()
            valid_mjds: list[float] = []
            epoch_samples: dict[float, dict[str, set[float]]] = {}
            flux_units: set[str] = set()
            for index, row in enumerate(source.get("observations") or []):
                if row.get("valid", True) is False:
                    continue
                try:
                    validate_science_wavelength(row, index=index)
                    mjd = float(row["mjd"])
                    wavelength = float(row["wavelength_um"])
                    flux = float(row["flux"])
                    sigma = float(row["sigma"])
                    observation_id = str(row.get("observation_id", "")).strip()
                    measurement_id = str(row.get("measurement_id", "")).strip()
                    calibration_group = str(row["calibration_group"]).strip()
                    flux_unit = str(row.get("flux_unit", "")).strip()
                    if not observation_id:
                        raise ValueError("observation_id is required for an auditable sample")
                    if not flux_unit:
                        raise ValueError("flux_unit must be explicit")
                    if not all(math.isfinite(value) for value in (mjd, wavelength, flux, sigma)) or sigma <= 0:
                        raise ValueError("measurement values must be finite and sigma positive")
                    measurement_key = (observation_id, round(wavelength, 8), calibration_group)
                    if measurement_key in measurement_keys:
                        source_reasons.append("duplicate_measurement_rows")
                        continue
                    measurement_keys.add(measurement_key)
                    if measurement_id:
                        valid_measurement_ids.add(measurement_id)
                    valid_observation_ids.add(observation_id)
                    valid_mjds.append(mjd)
                    flux_units.add(flux_unit)
                    epoch = round(mjd, 7)
                    bands = epoch_samples.setdefault(epoch, {
                        "feature": set(), "blue": set(), "red": set()
                    })
                    if feature[0] <= wavelength <= feature[1]:
                        bands["feature"].add(round(wavelength, 8))
                    if blue[0] <= wavelength <= blue[1]:
                        bands["blue"].add(round(wavelength, 8))
                    if red[0] <= wavelength <= red[1]:
                        bands["red"].add(round(wavelength, 8))
                    valid_rows.append((mjd, wavelength, abs(flux) / sigma, calibration_group))
                except (ValueError, TypeError, KeyError, OverflowError):
                    source_reasons.append("invalid_or_unverified_measurement")

            if len(flux_units) > 1:
                source_reasons.append("inconsistent_flux_units")
            calibration_groups = sorted({row[3] for row in valid_rows})
            if len(calibration_groups) > 1 and source.get("calibration_bridge_verified") is not True:
                source_reasons.append("multiple_calibration_groups_without_verified_bridge")

            epoch_count = len(epoch_samples)
            feature_samples = sum(len(value["feature"]) for value in epoch_samples.values())
            blue_samples = sum(len(value["blue"]) for value in epoch_samples.values())
            red_samples = sum(len(value["red"]) for value in epoch_samples.values())
            feature_epochs = sum(bool(value["feature"]) for value in epoch_samples.values())
            continuum_epochs = sum(
                bool(value["blue"]) and bool(value["red"])
                for value in epoch_samples.values()
            )
            complete_feature_epochs = sum(
                bool(value["feature"]) and bool(value["blue"]) and bool(value["red"])
                for value in epoch_samples.values()
            )

            snrs = sorted(row[2] for row in valid_rows)
            if not snrs:
                median_snr = 0.0
            elif len(snrs) % 2:
                median_snr = snrs[len(snrs) // 2]
            else:
                median_snr = (snrs[len(snrs) // 2 - 1] + snrs[len(snrs) // 2]) / 2

            if epoch_count < minimum_epochs_per_source:
                source_reasons.append("insufficient_independent_epochs")
            if feature_samples < minimum_feature_samples:
                source_reasons.append("insufficient_feature_sampling")
            if blue_samples + red_samples < minimum_continuum_samples:
                source_reasons.append("insufficient_continuum_sampling")
            if feature_epochs < minimum_epochs_per_source:
                source_reasons.append("feature_not_sampled_across_required_epochs")
            if continuum_epochs < minimum_epochs_per_source:
                source_reasons.append("both_continua_not_sampled_across_required_epochs")
            if complete_feature_epochs < minimum_epochs_per_source:
                source_reasons.append("feature_and_both_continua_not_jointly_sampled_per_epoch")
            if median_snr < minimum_median_snr:
                source_reasons.append("median_snr_below_threshold")

            source_report = {
                "source_id": source_id,
                "epoch_count": epoch_count,
                "feature_samples": feature_samples,
                "blue_continuum_samples": blue_samples,
                "red_continuum_samples": red_samples,
                "feature_epochs": feature_epochs,
                "continuum_epochs": continuum_epochs,
                "complete_feature_epochs": complete_feature_epochs,
                "median_snr": median_snr,
                "measurement_ids": sorted(valid_measurement_ids),
                "observation_ids": sorted(valid_observation_ids),
                "mjd_min": min(valid_mjds) if valid_mjds else None,
                "mjd_max": max(valid_mjds) if valid_mjds else None,
                "baseline_days": max(valid_mjds) - min(valid_mjds) if len(valid_mjds) > 1 else 0.0,
                "selection": selection_prediction,
                "flux_units": sorted(flux_units),
                "calibration_groups": sorted({row[3] for row in valid_rows}),
                "eligible": not source_reasons,
                "reasons": sorted(set(source_reasons)),
            }
            source_reports.append(source_report)
            if source_report["eligible"]:
                eligible_sources.append({
                    "field_id": field_id,
                    "source_id": source_id,
                    "epoch_count": epoch_count,
                    "complete_feature_epochs": complete_feature_epochs,
                    "measurement_ids": sorted(valid_measurement_ids),
                    "observation_ids": sorted(valid_observation_ids),
                    "mjd_min": min(valid_mjds) if valid_mjds else None,
                    "mjd_max": max(valid_mjds) if valid_mjds else None,
                    "baseline_days": max(valid_mjds) - min(valid_mjds) if len(valid_mjds) > 1 else 0.0,
                    "selection_probability": selection_prediction.get("selection_probability"),
                    "selection_weight": selection_prediction.get("selection_weight"),
                    "selection_cell_id": selection_prediction.get("cell_id"),
                    "calibration_groups": source_report["calibration_groups"],
                })

        if not any(source["eligible"] for source in source_reports):
            reasons.append("no_source_passed_coverage_gates")
        for reason in set(reasons):
            failure_counts[reason] = failure_counts.get(reason, 0) + 1

        field_reports.append({
            "field_id": field_id,
            "dataset_class": dataset_class,
            "eligible": not reasons,
            "reasons": sorted(set(reasons)),
            "injection_completeness": completeness,
            "null_control_id": field.get("null_control_id"),
            "null_control_to_science_exposure_ratio": null_ratio,
            "area_deg2": area,
            "baseline_days": baseline_days,
            "null_control_area_deg2": null_area,
            "null_control_baseline_days": null_days,
            "sources": source_reports,
        })

    eligible_fields = sum(row["eligible"] for row in field_reports)
    if eligible_fields < minimum_independent_fields:
        failure_counts["too_few_independent_fields"] = 1
    passed = (
        selection_fit is not None and selection_fit.get("supported") is True
        and eligible_fields >= minimum_independent_fields
        and all(row["eligible"] for row in field_reports)
    )
    input_digest = hashlib.sha256(json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")).hexdigest()
    selection_trials_digest = hashlib.sha256(json.dumps(
        list(selection_trials or []), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, default=str,
    ).encode("utf-8")).hexdigest()
    return {
        "input_fields_sha256": input_digest,
        "input_selection_trials_sha256": selection_trials_digest,
        "selection_function": selection_fit,
        "selection_function_error": selection_error,
        "status": "coverage_passed_preregistration_required" if passed else "not_ready_or_infeasible",
        "eligible_for_predeclared_population_protocol": passed,
        "target_class": target_class,
        "predeclared_intervals_um": {
            "feature": list(feature), "blue_continuum": list(blue), "red_continuum": list(red)
        },
        "thresholds": {
            "minimum_independent_fields": minimum_independent_fields,
            "minimum_epochs_per_source": minimum_epochs_per_source,
            "minimum_feature_samples": minimum_feature_samples,
            "minimum_continuum_samples": minimum_continuum_samples,
            "minimum_median_snr": minimum_median_snr,
            "minimum_completeness": minimum_completeness,
            "minimum_trials_per_selection_cell": int(minimum_trials_per_selection_cell),
            "minimum_fields_per_selection_cell": minimum_fields_per_cell,
            "minimum_selection_probability": float(minimum_selection_probability),
        },
        "field_count": len(field_reports),
        "eligible_field_count": eligible_fields,
        "eligible_sources": eligible_sources,
        "fields": field_reports,
        "failure_counts": failure_counts,
        "next_step": (
            "Freeze the inclusion, exclusion, null-control, exposure-scaling and multidimensional selection protocol before measuring outcomes."
            if passed else
            "Do not calculate a population result; improve or document infeasible archive coverage."
        ),
        "limitations": [
            "Checks supplied records only; it does not query the archive or independently validate source classification.",
            "CWAVE/CBAND provenance is required for every valid real measurement.",
            "Independent-field and source-identification attestations remain operator supplied.",
            "Feature and both continuum intervals must be measured within the same repeated epochs; aggregate sample counts alone are not enough.",
            "The joint-bin selection function uses fixed bins and refuses unsupported covariate cells; it does not extrapolate.",
            "Selection-function recovery and per-field injected/recovered totals must derive from the same frozen production-selection trial records.",
            "Per-field completeness totals are checked against the individual selection trials; they cannot be supplied as a separate optimistic summary.",
            "Selection-function validity still depends on the injection distribution representing the target population and on independent calibration review.",
            "A coverage pass is not evidence for a physical population trend.",
        ],
    }
