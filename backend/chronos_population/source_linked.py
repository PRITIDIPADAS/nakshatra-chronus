"""Source-linked, inverse-probability weighted YSO event-yield estimator.

This module refuses aggregate event counts: every counted event must be tied
to an eligible source and to the exact valid measurement rows that establish
its observed time interval. It corrects source-catalogue inclusion only.
Event-detection efficiency and contamination remain distinct, unsolved gates.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from chronos_population.rates import _revalidate_coverage, _count, _positive_finite


def estimate_source_linked_event_yield(
    fields: Sequence[Mapping[str, Any]],
    *,
    coverage_audit: Mapping[str, Any],
    selection_trials: Sequence[Mapping[str, Any]],
    selection_bin_spec: Mapping[str, Any],
    source_event_records: Sequence[Mapping[str, Any]],
    preregistration_sha256: str,
    event_definition_sha256: str,
    draws: int = 10000,
    seed: int = 1,
) -> dict[str, Any]:
    """Estimate a source-selection-weighted candidate-event yield per area-day.

    Source selection probabilities are obtained from the frozen, multidimensional
    injection model and applied as Horvitz-Thompson inverse-probability weights.
    Event rows are required to link to at least two distinct source measurement
    epochs. A field-level null-control event count is kept separate and scaled
    only by its declared science/control area-time ratio.

    This is not a final YSO population rate: event-detection completeness,
    event-level contamination composition, cross-field covariance, and
    independent astronomical review remain separate requirements.
    """
    if not fields:
        raise ValueError("real field records are required")
    if not source_event_records:
        raise ValueError("source_event_records are required; aggregate observed_events alone are not accepted")
    if not isinstance(selection_bin_spec, Mapping):
        raise ValueError("the frozen multidimensional selection bin specification is required")

    preregistration = str(preregistration_sha256 or "").lower()
    event_definition = str(event_definition_sha256 or "").lower()
    for value, label in (
        (preregistration, "preregistration_sha256"),
        (event_definition, "event_definition_sha256"),
    ):
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError(f"{label} must be a 64-character SHA-256 digest")

    if not isinstance(coverage_audit, Mapping):
        raise ValueError("a complete coverage audit is required")
    thresholds = coverage_audit.get("thresholds") or {}
    minimum_completeness = float(thresholds.get("minimum_completeness", float("nan")))
    verified = _revalidate_coverage(
        fields, coverage_audit, minimum_completeness,
        selection_trials=selection_trials, selection_bin_spec=selection_bin_spec,
    )
    selection = verified.get("selection_function") or {}
    frozen = selection.get("frozen_provenance") or {}
    if frozen.get("preregistration_sha256") != preregistration:
        raise ValueError("source-event preregistration digest does not match the frozen selection trials")
    trial_event_definitions = {
        str(row.get("event_definition_sha256", "")).lower()
        for row in selection_trials
    }
    if trial_event_definitions != {event_definition}:
        raise ValueError("event_definition_sha256 must be frozen identically into every source-selection injection trial")

    eligible_sources = {}
    for source in verified.get("eligible_sources") or []:
        field_id = str(source.get("field_id", "")).strip()
        source_id = str(source.get("source_id", "")).strip()
        key = (field_id, source_id)
        if not all(key) or key in eligible_sources:
            raise ValueError("coverage audit contains a duplicate or malformed eligible source key")
        probability = source.get("selection_probability")
        weight = source.get("selection_weight")
        try:
            probability = float(probability)
            weight = float(weight)
        except (TypeError, ValueError):
            raise ValueError(f"eligible source {key} has no numeric selection probability/weight") from None
        if not math.isfinite(probability) or not 0 < probability <= 1:
            raise ValueError(f"eligible source {key} has an invalid selection probability")
        if not math.isfinite(weight) or weight <= 0 or not math.isclose(
            weight, 1.0 / probability, rel_tol=1e-8, abs_tol=1e-10
        ):
            raise ValueError(f"eligible source {key} has an inconsistent inverse-probability weight")
        lineage = source.get("measurement_lineage")
        if not isinstance(lineage, list) or not lineage:
            raise ValueError(f"eligible source {key} has no measurement-level lineage")
        lineage_by_id = {}
        for row in lineage:
            measurement_id = str(row.get("measurement_id", "")).strip()
            if not measurement_id or measurement_id in lineage_by_id:
                raise ValueError(f"eligible source {key} has duplicate/missing measurement IDs")
            mjd = float(row.get("mjd"))
            if not math.isfinite(mjd):
                raise ValueError(f"eligible source {key} has a non-finite measurement MJD")
            lineage_by_id[measurement_id] = {
                "mjd": mjd,
                "observation_id": str(row.get("observation_id", "")).strip(),
                "wavelength_um": float(row.get("wavelength_um")),
            }
        eligible_sources[key] = {
            "selection_probability": probability,
            "selection_weight": weight,
            "measurement_lineage": lineage_by_id,
            "mjd_min": min(row["mjd"] for row in lineage_by_id.values()),
            "mjd_max": max(row["mjd"] for row in lineage_by_id.values()),
        }

    fields_by_id = {}
    for index, field in enumerate(fields):
        field_id = str(field.get("field_id", "")).strip()
        if not field_id or field_id in fields_by_id:
            raise ValueError(f"field {index} has a missing or duplicate field_id")
        if str(field.get("dataset_class", field.get("data_class", "unverified"))).lower() != "real":
            raise ValueError(f"field {field_id} is not labelled real")
        if field.get("independent_field") is not True:
            raise ValueError(f"field {field_id} lacks an independent-field attestation")
        fields_by_id[field_id] = field

    grouped_events: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    event_ids: set[str] = set()
    for index, raw in enumerate(source_event_records):
        if not isinstance(raw, Mapping):
            raise ValueError(f"source event {index} must be an object")
        event_id = str(raw.get("event_id", "")).strip()
        field_id = str(raw.get("field_id", "")).strip()
        source_id = str(raw.get("source_id", "")).strip()
        if not event_id or event_id in event_ids:
            raise ValueError("event_id values must be globally unique and non-empty")
        event_ids.add(event_id)
        if field_id not in fields_by_id:
            raise ValueError(f"event {event_id} references an unknown field")
        key = (field_id, source_id)
        if key not in eligible_sources:
            raise ValueError(f"event {event_id} does not belong to a source that passed the full source-selection/coverage gate")
        if str(raw.get("status", "")).lower() != "accepted":
            raise ValueError(f"event {event_id} must be accepted by the frozen event rule")
        if str(raw.get("preregistration_sha256", "")).lower() != preregistration:
            raise ValueError(f"event {event_id} preregistration digest mismatch")
        if str(raw.get("event_definition_sha256", "")).lower() != event_definition:
            raise ValueError(f"event {event_id} event-definition digest mismatch")
        try:
            start = float(raw.get("start_mjd"))
            end = float(raw.get("end_mjd"))
        except (TypeError, ValueError):
            raise ValueError(f"event {event_id} requires finite start_mjd and end_mjd") from None
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ValueError(f"event {event_id} interval must be finite and have positive duration")

        measurement_ids = raw.get("measurement_ids")
        if not isinstance(measurement_ids, list) or len(measurement_ids) < 2:
            raise ValueError(f"event {event_id} must cite at least two measurement_ids")
        if any(not isinstance(item, str) or not item.strip() for item in measurement_ids):
            raise ValueError(f"event {event_id} measurement_ids must be non-empty strings")
        if len(set(measurement_ids)) != len(measurement_ids):
            raise ValueError(f"event {event_id} repeats a measurement_id")
        lineage = eligible_sources[key]["measurement_lineage"]
        missing_measurements = sorted(set(measurement_ids) - set(lineage))
        if missing_measurements:
            raise ValueError(
                f"event {event_id} references measurements absent from the verified source series: {missing_measurements}"
            )
        event_rows = [lineage[item] for item in measurement_ids]
        measurement_epochs = sorted({row["mjd"] for row in event_rows})
        if len(measurement_epochs) < 2:
            raise ValueError(f"event {event_id} must be supported by at least two distinct measured epochs")
        if start < measurement_epochs[0] - 1e-7 or end > measurement_epochs[-1] + 1e-7:
            raise ValueError(f"event {event_id} interval extends beyond its cited measurements")
        grouped_events[field_id][key].append({
            "event_id": event_id,
            "source_id": source_id,
            "start_mjd": start,
            "end_mjd": end,
            "measurement_ids": sorted(measurement_ids),
            "measurement_epochs_mjd": measurement_epochs,
            "selection_probability": eligible_sources[key]["selection_probability"],
            "selection_weight": eligible_sources[key]["selection_weight"],
        })

    if len(event_ids) == 0:
        raise ValueError("no accepted source-linked events were supplied")

    draws = _count(draws, "draws")
    if draws < 1000:
        raise ValueError("draws must be at least 1000")
    if isinstance(seed, bool) or int(seed) != seed or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    rng = np.random.default_rng(int(seed))

    total_excess = np.zeros(draws, dtype=float)
    total_exposure = 0.0
    field_reports = []
    accepted_source_keys = set()

    for field_id, field in fields_by_id.items():
        required = (
            "observed_events", "null_events", "area_deg2", "baseline_days",
            "null_control_area_deg2", "null_control_baseline_days",
            "null_control_to_science_exposure_ratio", "null_control_id",
        )
        missing = [name for name in required if name not in field]
        if missing:
            raise ValueError(f"field {field_id} is missing {missing}")
        events_here = [
            event for source_events in grouped_events[field_id].values()
            for event in source_events
        ]
        observed = _count(field["observed_events"], f"field {field_id} observed_events")
        null = _count(field["null_events"], f"field {field_id} null_events")
        if observed != len(events_here):
            raise ValueError(
                f"field {field_id} observed_events must equal its accepted source_event_records count"
            )
        if not str(field.get("null_control_id", "")).strip():
            raise ValueError(f"field {field_id} requires a named null control")
        area = _positive_finite(field["area_deg2"], f"field {field_id} area_deg2")
        days = _positive_finite(field["baseline_days"], f"field {field_id} baseline_days")
        control_area = _positive_finite(field["null_control_area_deg2"], f"field {field_id} null_control_area_deg2")
        control_days = _positive_finite(field["null_control_baseline_days"], f"field {field_id} null_control_baseline_days")
        control_ratio = _positive_finite(
            field["null_control_to_science_exposure_ratio"],
            f"field {field_id} null_control_to_science_exposure_ratio",
        )
        derived_ratio = (area * days) / (control_area * control_days)
        if not math.isclose(control_ratio, derived_ratio, rel_tol=1e-6, abs_tol=1e-12):
            raise ValueError(f"field {field_id} null-control exposure ratio disagrees with its area-time denominators")

        # Resample source clusters, not individual wavelength rows or event
        # rows. Multiple candidate events from one source share a bootstrap
        # multiplier, avoiding a false independent-event assumption.
        by_source = {}
        for key, source_events in grouped_events[field_id].items():
            if key in accepted_source_keys:
                raise ValueError(f"source {key} appears in duplicate field contributions")
            accepted_source_keys.add(key)
            weight = eligible_sources[key]["selection_weight"]
            by_source[key[1]] = len(source_events) * weight
        source_contributions = np.asarray(list(by_source.values()), dtype=float)
        if source_contributions.size:
            source_event_draws = (
                rng.poisson(1.0, size=(draws, source_contributions.size))
                @ source_contributions
            )
        else:
            source_event_draws = np.zeros(draws, dtype=float)

        null_mean_science = rng.gamma(shape=null + 0.5, scale=control_ratio, size=draws)
        null_count_draws = rng.poisson(null_mean_science)
        # The source-selection weights apply only to the science-source event
        # sample. The null control remains on its separately recorded
        # area-time exposure scale.
        total_excess += source_event_draws - null_count_draws
        exposure = area * days
        total_exposure += exposure
        field_reports.append({
            "field_id": field_id,
            "source_count_with_events": len(by_source),
            "accepted_source_events": observed,
            "source_selection_weighted_events": float(source_contributions.sum()),
            "null_events_control_exposure": null,
            "null_control_id": str(field["null_control_id"]),
            "null_control_to_science_exposure_ratio": control_ratio,
            "null_events_expected_science_exposure": null * control_ratio,
            "science_area_deg2": area,
            "science_baseline_days": days,
            "science_exposure_sqdeg_days": exposure,
        })

    if total_exposure <= 0:
        raise ValueError("total science area-time exposure must be positive")
    rates = np.maximum(total_excess, 0.0) / total_exposure
    q16, median, q84 = np.quantile(rates, [0.16, 0.50, 0.84])
    q025, q975 = np.quantile(rates, [0.025, 0.975])
    return {
        "scientific_status": "source_selection_weighted_candidate_event_yield_not_population_result",
        "field_count": len(field_reports),
        "accepted_event_count": len(event_ids),
        "source_count_with_events": sum(row["source_count_with_events"] for row in field_reports),
        "total_source_selection_weighted_event_count": float(sum(
            row["source_selection_weighted_events"] for row in field_reports
        )),
        "total_science_exposure_sqdeg_days": total_exposure,
        "event_yield_per_sqdeg_day": {
            "median": float(median),
            "lower_68": float(q16),
            "upper_68": float(q84),
            "lower_95": float(q025),
            "upper_95": float(q975),
        },
        "field_reports": field_reports,
        "source_event_records_sha256": __import__("hashlib").sha256(
            __import__("json").dumps(
                list(source_event_records), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False, default=str,
            ).encode("utf-8")
        ).hexdigest(),
        "selection_function": {
            "schema": selection.get("schema"),
            "bin_spec_sha256": selection.get("bin_spec_sha256"),
            "injection_trials_sha256": selection.get("injection_trials_sha256"),
            "frozen_provenance": frozen,
            "correction": "Horvitz-Thompson inverse probability weight 1/p(source detected)",
        },
        "preregistration_sha256": preregistration,
        "event_definition_sha256": event_definition,
        "draws": draws,
        "seed": int(seed),
        "coverage_revalidated": True,
        "limits": [
            "Source inclusion is corrected using the predeclared multidimensional source-selection function; cells outside its support are excluded upstream.",
            "Event-detection completeness is not corrected by this estimator and requires a separate event-level injection/recovery model.",
            "Null-control events are scaled by the supplied area-time ratio; source-level control matching and contamination composition are not modelled.",
            "The event uncertainty resamples source clusters with a Poisson multiplier but does not model cross-field covariance or overdispersion.",
            "The rate is conditional on the source catalogue, event rule, field independence, injection representativeness, and null-control assumptions.",
            "A source-selection-weighted yield is not a validated YSO population result or discovery; independent calibration, custody, event-detection efficiency, contamination review and astronomical reproduction remain necessary.",
        ],
    }
