"""Exploratory event-rate estimates with completeness and scaled null controls.

The null-count model requires an explicit ratio converting the control
solid-angle times time exposure to the science-field exposure. It never
silently subtracts raw control counts from science counts with different
denominators.
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


def estimate_event_rate(
    fields: Sequence[Mapping[str, Any]],
    *,
    minimum_completeness: float = 0.1,
    draws: int = 10000,
    seed: int = 1,
) -> dict[str, Any]:
    """Estimate a conditional event rate per square-degree-day.

    null_control_to_science_exposure_ratio equals the science field solid-angle
    times time divided by the null control solid-angle times time. A
    Gamma-Poisson posterior-predictive draw scales the null count onto the
    science exposure before it is subtracted from the observed count.

    This is an approximate exploratory model. Fields must genuinely be
    independent, the scalar injection completeness must represent the target
    population, and null controls must be appropriately matched.
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

    rng = np.random.default_rng(seed_value)
    total_rate_draws = np.zeros(draws, dtype=float)
    included: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
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

        if str(row.get("dataset_class", row.get("data_class", "unverified"))).lower() != "real":
            skipped.append({"field_id": field_id, "reason": "field_not_labelled_real"})
            continue
        if row.get("independent_field") is not True:
            skipped.append({"field_id": field_id, "reason": "independence_not_attested"})
            continue
        if not str(row.get("null_control_id", "")).strip():
            skipped.append({"field_id": field_id, "reason": "null_control_not_identified"})
            continue

        try:
            null_to_science_ratio = _positive_finite(
                row.get("null_control_to_science_exposure_ratio"),
                f"field {field_id} null_control_to_science_exposure_ratio",
            )
        except ValueError:
            skipped.append({
                "field_id": field_id,
                "reason": "null_control_exposure_ratio_missing_or_invalid",
            })
            continue

        required = ("observed_events", "null_events", "area_deg2",
                    "baseline_days", "n_injected", "n_recovered")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"field {field_id} missing {missing}")

        observed = _count(row["observed_events"], f"field {field_id} observed_events")
        null = _count(row["null_events"], f"field {field_id} null_events")
        injected = _count(row["n_injected"], f"field {field_id} n_injected")
        recovered = _count(row["n_recovered"], f"field {field_id} n_recovered")
        area = _positive_finite(row["area_deg2"], f"field {field_id} area_deg2")
        days = _positive_finite(row["baseline_days"], f"field {field_id} baseline_days")
        if recovered > injected:
            raise ValueError(f"field {field_id} recovered count cannot exceed injected count")
        if injected <= 0:
            skipped.append({"field_id": field_id, "reason": "no injection denominator"})
            continue

        completeness = recovered / injected
        if completeness < minimum_completeness:
            skipped.append({
                "field_id": field_id,
                "reason": "completeness below configured floor",
                "measured_completeness": completeness,
            })
            continue

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
            excess / np.maximum(completeness_draws, 1e-6) / (area * days)
        )
        included.append({
            "field_id": field_id,
            "observed_events": observed,
            "null_events_in_control_exposure": null,
            "null_control_id": str(row["null_control_id"]),
            "null_control_to_science_exposure_ratio": null_to_science_ratio,
            "null_events_expected_in_science_exposure": null * null_to_science_ratio,
            "measured_completeness": completeness,
            "area_deg2": area,
            "baseline_days": days,
        })

    if not included:
        raise ValueError("no real, independent fields passed the completeness and null-control checks")

    q16, median, q84 = np.quantile(total_rate_draws, [0.16, 0.5, 0.84])
    q025, q975 = np.quantile(total_rate_draws, [0.025, 0.975])
    return {
        "included_fields": included,
        "skipped_fields": skipped,
        "field_count": len(included),
        "event_rate_per_sqdeg_day": {
            "median": float(median),
            "lower_68": float(q16),
            "upper_68": float(q84),
            "lower_95": float(q025),
            "upper_95": float(q975),
        },
        "draws": draws,
        "seed": seed_value,
        "method": (
            "sum of field-level non-negative Poisson excesses, with Jeffreys Beta "
            "completeness draws and scaled Gamma-Poisson null-control predictive draws"
        ),
        "limitations": [
            "Field independence is an operator-supplied assertion; overlapping areas or repeated sources must be removed before analysis.",
            "Observed and null counts are treated as Poisson counts; spatial clustering and temporal dependence are not modelled.",
            "The null-control exposure ratio must accurately represent the science-to-control solid-angle times time ratio.",
            "The Beta completeness model assumes injections represent the target population and compresses the selection function to one scalar per field.",
            "No covariance between field counts, completeness estimates and control estimates is modelled.",
            "This rate is exploratory and is not a population result until selection, contamination, null-control and denominator assumptions are independently validated.",
        ],
    }
