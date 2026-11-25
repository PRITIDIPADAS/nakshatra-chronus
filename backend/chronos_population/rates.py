"""Exploratory event-rate estimates with completeness and scaled null controls.

A population-rate calculation must repeat the fail-closed coverage audit on
the exact submitted field records. The audit's input digest binds the result
to the data, while the calculation below independently recomputes that audit
rather than trusting a caller-supplied boolean.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math

import numpy as np


def _count(value: Any, label: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a non-negative integer count")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a non-negative integer count") from None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f"{label} must be a non-negative integer count")
    return int(number)


def _positive_finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be finite and positive") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _revalidate_coverage(
    fields: Sequence[Mapping[str, Any]],
    coverage_audit: Mapping[str, Any] | None,
    minimum_completeness: float,
) -> dict[str, Any]:
    if not isinstance(coverage_audit, Mapping):
        raise ValueError("a complete coverage_audit is required before population-rate estimation")
    intervals = coverage_audit.get("predeclared_intervals_um")
    thresholds = coverage_audit.get("thresholds")
    if not isinstance(intervals, Mapping) or not isinstance(thresholds, Mapping):
        raise ValueError("coverage_audit is missing its predeclared intervals or thresholds")
    if not math.isclose(
        float(thresholds.get("minimum_completeness", float("nan"))),
        float(minimum_completeness),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("rate minimum_completeness must match the coverage-audit threshold")
    try:
        from chronos_population.coverage import assess_population_coverage
        verified = assess_population_coverage(
            fields,
            target_class=str(coverage_audit["target_class"]),
            feature_interval_um=intervals["feature"],
            blue_continuum_um=intervals["blue_continuum"],
            red_continuum_um=intervals["red_continuum"],
            minimum_independent_fields=thresholds["minimum_independent_fields"],
            minimum_epochs_per_source=thresholds["minimum_epochs_per_source"],
            minimum_feature_samples=thresholds["minimum_feature_samples"],
            minimum_continuum_samples=thresholds["minimum_continuum_samples"],
            minimum_median_snr=thresholds["minimum_median_snr"],
            minimum_completeness=thresholds["minimum_completeness"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"coverage_audit cannot be independently recomputed: {exc}") from exc
    if verified.get("eligible_for_predeclared_population_protocol") is not True:
        raise ValueError(
            "Population rate blocked: independently recomputed coverage audit did not pass "
            f"({verified.get('failure_counts')})"
        )
    if coverage_audit.get("input_fields_sha256") != verified.get("input_fields_sha256"):
        raise ValueError("coverage_audit field digest mismatch")
    return verified


def estimate_event_rate(
    fields: Sequence[Mapping[str, Any]],
    *,
    coverage_audit: Mapping[str, Any],
    minimum_completeness: float = 0.1,
    draws: int = 10000,
    seed: int = 1,
) -> dict[str, Any]:
    """Estimate a conditional event rate per square-degree-day.

    null_control_to_science_exposure_ratio equals science solid-angle times
    time divided by null-control solid-angle times time. The control count is
    drawn from a Gamma-Poisson posterior predictive model scaled onto the
    science exposure before subtracting it from the observed count.

    This remains an exploratory model. It assumes Poisson counts, matched
    controls and scalar completeness; it does not handle clustering, field
    covariance or a multidimensional selection function.
    """
    if not fields:
        raise ValueError("at least one independent field is required")
    if not math.isfinite(float(minimum_completeness)) or not 0 < minimum_completeness <= 1:
        raise ValueError("minimum_completeness must be in (0, 1]")
    draws = _count(draws, "draws")
    if draws < 100:
        raise ValueError("draws must be at least 100")
    if isinstance(seed, (bool, np.bool_)):
        raise ValueError("seed must be an integer")
    try:
        seed_value = int(seed)
    except (TypeError, ValueError):
        raise ValueError("seed must be an integer") from None
    if seed_value != seed:
        raise ValueError("seed must be an integer")

    verified_coverage = _revalidate_coverage(fields, coverage_audit, minimum_completeness)
    rng = np.random.default_rng(seed_value)
    total_corrected_excess_draws = np.zeros(draws, dtype=float)
    total_science_exposure_sqdeg_days = 0.0
    included: list[dict[str, Any]] = []
    seen_field_ids: set[str] = set()

    for index, raw in enumerate(fields):
        row = dict(raw)
        field_id = str(row.get("field_id", "")).strip()
        if not field_id:
            raise ValueError(f"field {index} requires a non-empty field_id")
        if field_id in seen_field_ids:
            raise ValueError(
                f"duplicate field_id {field_id!r}; independent fields must appear only once"
            )
        seen_field_ids.add(field_id)

        required = (
            "observed_events", "null_events", "area_deg2",
            "baseline_days", "null_control_area_deg2",
            "null_control_baseline_days", "n_injected", "n_recovered",
            "null_control_to_science_exposure_ratio",
        )
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"field {field_id} missing {missing}")

        observed = _count(row["observed_events"], f"field {field_id} observed_events")
        null = _count(row["null_events"], f"field {field_id} null_events")
        injected = _count(row["n_injected"], f"field {field_id} n_injected")
        recovered = _count(row["n_recovered"], f"field {field_id} n_recovered")
        area = _positive_finite(row["area_deg2"], f"field {field_id} area_deg2")
        days = _positive_finite(row["baseline_days"], f"field {field_id} baseline_days")
        null_area = _positive_finite(
            row["null_control_area_deg2"], f"field {field_id} null_control_area_deg2"
        )
        null_days = _positive_finite(
            row["null_control_baseline_days"], f"field {field_id} null_control_baseline_days"
        )
        null_to_science_ratio = _positive_finite(
            row["null_control_to_science_exposure_ratio"],
            f"field {field_id} null_control_to_science_exposure_ratio",
        )
        derived_null_ratio = (area * days) / (null_area * null_days)
        if not math.isclose(null_to_science_ratio, derived_null_ratio, rel_tol=1e-6, abs_tol=1e-12):
            raise ValueError(f"field {field_id} null-control exposure ratio disagrees with its area-time denominators")
        if recovered > injected or injected <= 0:
            raise ValueError(f"field {field_id} has invalid injection/recovery counts")
        if not str(row.get("null_control_id", "")).strip():
            raise ValueError(f"field {field_id} has no null-control identifier")

        completeness = recovered / injected
        if completeness < minimum_completeness:
            # The full coverage audit should already have blocked this field.
            raise ValueError(f"field {field_id} fell below the rate completeness floor")

        completeness_draws = rng.beta(
            recovered + 0.5, injected - recovered + 0.5, size=draws
        )
        science_count_draws = rng.poisson(observed, size=draws)
        null_mean_science = rng.gamma(
            shape=null + 0.5,
            scale=null_to_science_ratio,
            size=draws,
        )
        null_count_draws = rng.poisson(null_mean_science)
        excess = np.maximum(science_count_draws - null_count_draws, 0)
        total_rate_draws += (
            excess / np.maximum(completeness_draws, 1e-6)
        )
        field_exposure = area * days
        total_science_exposure_sqdeg_days += field_exposure
        included.append({
            "field_id": field_id,
            "observed_events": observed,
            "null_events_in_control_exposure": null,
            "null_control_id": str(row["null_control_id"]),
            "null_control_to_science_exposure_ratio": null_to_science_ratio,
            "null_control_area_deg2": null_area,
            "null_control_baseline_days": null_days,
            "null_events_expected_in_science_exposure": null * null_to_science_ratio,
            "measured_completeness": completeness,
            "area_deg2": area,
            "baseline_days": days,
            "science_exposure_sqdeg_days": field_exposure,
        })

    if total_science_exposure_sqdeg_days <= 0:
        raise ValueError("total science area-time exposure must be positive")
    total_rate_draws = total_corrected_excess_draws / total_science_exposure_sqdeg_days
    q16, median, q84 = np.quantile(total_rate_draws, [0.16, 0.5, 0.84])
    q025, q975 = np.quantile(total_rate_draws, [0.025, 0.975])
    return {
        "included_fields": included,
        "skipped_fields": [],
        "field_count": len(included),
        "total_science_exposure_sqdeg_days": total_science_exposure_sqdeg_days,
        "event_rate_per_sqdeg_day": {
            "median": float(median),
            "lower_68": float(q16),
            "upper_68": float(q84),
            "lower_95": float(q025),
            "upper_95": float(q975),
        },
        "draws": draws,
        "seed": seed_value,
        "coverage_revalidated": True,
        "coverage_input_fields_sha256": verified_coverage["input_fields_sha256"],
        "method": (
            "pooled completeness-corrected non-negative Poisson excess counts divided by "
            "the sum of science-field solid-angle times time; Jeffreys Beta completeness "
            "draws and scaled Gamma-Poisson null-control predictive draws"
        ),
        "limitations": [
            "The estimator independently recomputes the coverage gate over the exact submitted records.",
            "Field independence and null-control matching remain operator-supplied scientific assumptions.",
            "Observed and null counts are treated as Poisson counts; spatial clustering and temporal dependence are not modelled.",
            "The null-control exposure ratio must accurately represent the science-to-control solid-angle times time ratio.",
            "The Beta completeness model assumes injections represent the target population and compresses the selection function to one scalar per field.",
            "No covariance between field counts, completeness estimates and control estimates is modelled.",
            "This rate is exploratory and is not a population result until selection, contamination and denominator assumptions are independently validated.",
        ],
    }
