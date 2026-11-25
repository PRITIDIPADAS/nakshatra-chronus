"""Matched-threshold comparison for the four required detection baselines."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import numpy as np
from chronos_addons.validation import score_recovery

REQUIRED = ("snr_only", "chronos_pda", "instrument_forensics", "sky_detector_twin")

def compare_baselines(truth_positions: Sequence[Sequence[float]],
                      methods: Mapping[str, Sequence[Mapping[str, float]]],
                      score_thresholds: Sequence[float], *,
                      match_radius: float = 2.0,
                      field_area_deg2: float | None = None,
                      target_false_candidates_per_field: float | None = None,
                      target_completeness: float | None = None) -> dict[str, Any]:
    missing = [name for name in REQUIRED if name not in methods]
    if missing:
        raise ValueError("methods is missing required baselines: " + ", ".join(missing))
    thresholds = sorted({float(x) for x in score_thresholds}, reverse=True)
    if not thresholds or any(not np.isfinite(x) for x in thresholds):
        raise ValueError("score_thresholds must contain finite values")
    if (target_false_candidates_per_field is None) == (target_completeness is None):
        raise ValueError("supply exactly one matching target: false candidates per field or completeness")
    if target_false_candidates_per_field is not None and target_false_candidates_per_field < 0:
        raise ValueError("target false candidates per field must be non-negative")
    if target_completeness is not None and not 0 < target_completeness <= 1:
        raise ValueError("target completeness must be in (0, 1]")
    truth = np.asarray(truth_positions, dtype=float).reshape((-1, 2)) if len(truth_positions) else np.empty((0, 2))
    if np.any(~np.isfinite(truth)):
        raise ValueError("truth positions must be finite")
    curves = {}
    selected = {}
    for method in REQUIRED:
        rows = methods[method]
        points = []
        for threshold in thresholds:
            detections = []
            for item in rows:
                x, y, score = float(item["x"]), float(item["y"]), float(item["score"])
                if not np.all(np.isfinite([x, y, score])):
                    raise ValueError(f"{method} contains a non-finite detection")
                if score >= threshold:
                    detections.append([x, y])
            metric = score_recovery(truth, detections, match_radius=match_radius, field_area_deg2=field_area_deg2)
            points.append({
                "threshold": threshold,
                "detections": metric["detection_count"],
                "completeness": metric["recall_completeness"],
                "false_candidates_per_field": metric["false_candidates_per_field"],
                "precision": metric["precision"],
                "true_positive": metric["true_positive"],
                "false_positive": metric["false_positive"],
            })
        curves[method] = points
        if target_false_candidates_per_field is not None:
            key = lambda p: abs(p["false_candidates_per_field"] - target_false_candidates_per_field)
        else:
            key = lambda p: abs((p["completeness"] if p["completeness"] is not None else -1) - target_completeness)
        selected[method] = min(points, key=key)
    metric_key = "false_candidates_per_field" if target_false_candidates_per_field is not None else "completeness"
    return {
        "baselines": list(REQUIRED),
        "matching_rule": {
            "metric": metric_key,
            "target": target_false_candidates_per_field if target_false_candidates_per_field is not None else target_completeness,
            "selection": "nearest supplied threshold; exact equality is not guaranteed",
        },
        "curves": curves,
        "matched_comparison": selected,
        "limitations": [
            "All methods must be run on the same field, masks, truth set and measurement products.",
            "Threshold matching is approximate over the supplied threshold grid.",
            "This endpoint calculates comparison metrics; it does not run the four detection algorithms.",
            "Use independent fields and field-level uncertainty estimates for scientific claims.",
        ],
    }
