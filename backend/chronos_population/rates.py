"""Monte Carlo population-rate estimates with completeness and null controls."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import numpy as np

def estimate_event_rate(fields: Sequence[Mapping[str, Any]], *, minimum_completeness: float = 0.1,
                        draws: int = 10000, seed: int = 1) -> dict[str, Any]:
    if not fields:
        raise ValueError("at least one independent field is required")
    if not 0 < minimum_completeness <= 1 or draws < 100:
        raise ValueError("minimum_completeness must be in (0, 1] and draws must be at least 100")
    rng = np.random.default_rng(int(seed))
    total_rate_draws = np.zeros(draws, dtype=float)
    included, skipped = [], []
    for index, raw in enumerate(fields):
        row = dict(raw)
        required = ("field_id", "observed_events", "null_events", "area_deg2",
                    "baseline_days", "n_injected", "n_recovered")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"field {index} missing {missing}")
        observed, null = int(row["observed_events"]), int(row["null_events"])
        area, days = float(row["area_deg2"]), float(row["baseline_days"])
        injected, recovered = int(row["n_injected"]), int(row["n_recovered"])
        if min(observed, null, injected, recovered) < 0 or recovered > injected:
            raise ValueError(f"field {index} has invalid non-negative counts")
        if not np.isfinite(area) or not np.isfinite(days) or area <= 0 or days <= 0:
            raise ValueError(f"field {index} area and baseline must be finite and positive")
        if injected <= 0:
            skipped.append({"field_id": row["field_id"], "reason": "no injection denominator"})
            continue
        completeness = recovered / injected
        if completeness < minimum_completeness:
            skipped.append({"field_id": row["field_id"], "reason": "completeness below configured floor",
                            "measured_completeness": completeness})
            continue
        # Jeffreys-like Beta smoothing avoids a zero or one completeness estimate.
        comp_draw = rng.beta(recovered + 0.5, injected - recovered + 0.5, size=draws)
        # A non-negative difference of observed and null Poisson counts.
        sky_draw = rng.poisson(observed, size=draws)
        null_draw = rng.poisson(null, size=draws)
        excess = np.maximum(sky_draw - null_draw, 0)
        total_rate_draws += excess / np.maximum(comp_draw, 1e-6) / (area * days)
        included.append({"field_id": row["field_id"], "observed_events": observed,
                         "null_events": null, "measured_completeness": completeness,
                         "area_deg2": area, "baseline_days": days})
    if not included:
        raise ValueError("no fields passed the completeness and denominator checks")
    q16, median, q84 = np.quantile(total_rate_draws, [0.16, 0.5, 0.84])
    q025, q975 = np.quantile(total_rate_draws, [0.025, 0.975])
    return {
        "included_fields": included,
        "skipped_fields": skipped,
        "field_count": len(included),
        "event_rate_per_sqdeg_day": {
            "median": float(median), "lower_68": float(q16), "upper_68": float(q84),
            "lower_95": float(q025), "upper_95": float(q975),
        },
        "draws": draws,
        "seed": int(seed),
        "method": "sum of field-level non-negative Poisson excesses, divided by Beta-distributed completeness and area-time",
        "limitations": [
            "Field counts and null counts are treated as independent Poisson variables.",
            "The Beta completeness model assumes injected sources are representative of the target population within each field.",
            "Fields must be independent or their overlapping survey area must be accounted for before use.",
            "This rate is only as reliable as the supplied candidate counts, null controls, selection function, and area-time calculation.",
            "Do not use as a population result until field-level selection effects and uncertainty dependencies are validated.",
        ],
    }
