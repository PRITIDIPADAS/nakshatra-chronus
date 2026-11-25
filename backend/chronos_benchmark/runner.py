"""Common-input four-baseline benchmark and reproducible comparison reports.

This module evaluates detector outputs produced elsewhere. It does not silently
run a different field, mask, exposure set or truth catalogue for any baseline.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np

from chronos_addons.validation import score_recovery, wilson_interval

REQUIRED_METHODS = (
    "snr_only",
    "chronos_pda",
    "instrument_forensics",
    "sky_detector_twin",
)
SCHEMA = "chronos-four-baseline-package/1.0"
_SHA256 = set("0123456789abcdef")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _require_sha(value: Any, label: str) -> str:
    token = str(value).lower()
    if len(token) != 64 or not set(token) <= _SHA256:
        raise ValueError(f"{label} must be a 64-character SHA-256 hex digest")
    return token


def truth_catalogue_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    normal = []
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"truth row {index} must be an object")
        if "truth_id" not in row or "x" not in row or "y" not in row:
            raise ValueError(f"truth row {index} requires truth_id, x and y")
        truth_id = str(row["truth_id"])
        if not truth_id or truth_id in seen:
            raise ValueError("truth IDs must be non-empty and unique within a field")
        seen.add(truth_id)
        x, y = float(row["x"]), float(row["y"])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"truth row {index} coordinates must be finite")
        item = {k: v for k, v in row.items()}
        item["truth_id"] = truth_id
        item["x"], item["y"] = x, y
        normal.append(item)
    normal.sort(key=lambda item: item["truth_id"])
    return sha256_json(normal)


def _validate_signature(signature: Mapping[str, Any], truth_rows) -> dict[str, Any]:
    required = (
        "field_id", "dataset_class", "exposure_ids", "mask_sha256",
        "truth_catalogue_sha256", "coordinate_frame", "coordinate_unit",
    )
    missing = [key for key in required if key not in signature]
    if missing:
        raise ValueError("input_signature is missing: " + ", ".join(missing))
    out = dict(signature)
    out["field_id"] = str(out["field_id"])
    if not out["field_id"]:
        raise ValueError("field_id cannot be blank")
    if out["dataset_class"] not in {"real", "synthetic", "illustrative", "unverified"}:
        raise ValueError("dataset_class must be real, synthetic, illustrative or unverified")
    exposures = [str(x) for x in out["exposure_ids"]]
    if not exposures or any(not x for x in exposures) or len(set(exposures)) != len(exposures):
        raise ValueError("exposure_ids must be non-empty and unique")
    out["exposure_ids"] = sorted(exposures)
    out["mask_sha256"] = _require_sha(out["mask_sha256"], "mask_sha256")
    out["truth_catalogue_sha256"] = _require_sha(
        out["truth_catalogue_sha256"], "truth_catalogue_sha256"
    )
    actual_truth_digest = truth_catalogue_digest(truth_rows)
    if actual_truth_digest != out["truth_catalogue_sha256"]:
        raise ValueError("truth catalogue digest does not match input_signature")
    if out["coordinate_frame"] not in {"sky", "detector"}:
        raise ValueError("coordinate_frame must be sky or detector")
    if out["coordinate_unit"] not in {"pixel", "arcsec"}:
        raise ValueError("coordinate_unit must be pixel or arcsec")
    if out["coordinate_frame"] == "sky" and out["coordinate_unit"] == "pixel":
        if not out.get("pixel_wcs_sha256"):
            raise ValueError("sky-pixel matching requires pixel_wcs_sha256")
    if out.get("pipeline_input_sha256") is not None:
        out["pipeline_input_sha256"] = _require_sha(
            out["pipeline_input_sha256"], "pipeline_input_sha256"
        )
    return out


def _normalise_detections(method: str, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, (list, tuple)):
        raise ValueError(f"{method}.detections must be a list; use [] for no detections")
    out = []
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{method} detection {index} must be an object")
        missing = [k for k in ("detection_id", "x", "y", "score", "provenance") if k not in row]
        if missing:
            raise ValueError(f"{method} detection {index} is missing: {', '.join(missing)}")
        detection_id = str(row["detection_id"])
        if not detection_id or detection_id in seen:
            raise ValueError(f"{method} detection IDs must be non-empty and unique")
        seen.add(detection_id)
        x, y, score = float(row["x"]), float(row["y"]), float(row["score"])
        if not all(math.isfinite(v) for v in (x, y, score)):
            raise ValueError(f"{method} detection {index} has a non-finite coordinate or score")
        provenance = row["provenance"]
        if not isinstance(provenance, Mapping) or not provenance:
            raise ValueError(f"{method} detection {index} needs non-empty provenance")
        item = dict(row)
        item.update(detection_id=detection_id, x=x, y=y, score=score,
                    provenance=dict(provenance))
        out.append(item)
    return out


def _summarise_astrometry(matches: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["separation"]) for row in matches]
    if not values:
        return {"n": 0, "median": None, "p95": None, "rmse": None, "unit": "input coordinate unit"}
    arr = np.asarray(values, dtype=float)
    return {
        "n": len(values),
        "median": float(np.median(arr)),
        "p95": float(np.percentile(arr, 95)),
        "rmse": float(np.sqrt(np.mean(arr ** 2))),
        "unit": "input coordinate unit",
    }


def _evaluate_field_method(truth_rows, detections, thresholds, match_radius):
    truth_ids = [str(row["truth_id"]) for row in truth_rows]
    truth_xy = [[float(row["x"]), float(row["y"])] for row in truth_rows]
    curve = []
    for threshold in thresholds:
        selected = [row for row in detections if row["score"] >= threshold]
        found = [[row["x"], row["y"]] for row in selected]
        metric = score_recovery(truth_xy, found, match_radius=match_radius)
        pairs = metric["matched_pairs"]
        matched = []
        used_truth = set()
        used_detection = set()
        for pair in pairs:
            ti, di = int(pair["truth_index"]), int(pair["detection_index"])
            det = selected[di]
            truth = truth_rows[ti]
            used_truth.add(ti)
            used_detection.add(di)
            matched.append({
                "truth_id": truth_ids[ti],
                "detection_id": det["detection_id"],
                "separation": float(pair["separation"]),
                "score": det["score"],
                "provenance": det["provenance"],
            })
        unmatched = [
            {"detection_id": row["detection_id"], "x": row["x"], "y": row["y"],
             "score": row["score"], "provenance": row["provenance"]}
            for index, row in enumerate(selected) if index not in used_detection
        ]
        missed = [truth_ids[index] for index in range(len(truth_rows)) if index not in used_truth]
        residuals = _summarise_astrometry(matched)
        curve.append({
            "threshold": float(threshold),
            "detection_count": int(metric["detection_count"]),
            "true_positive": int(metric["true_positive"]),
            "false_positive": int(metric["false_positive"]),
            "false_negative": int(metric["false_negative"]),
            "precision": metric["precision"],
            "completeness": metric["recall_completeness"],
            "false_candidates_per_field": int(metric["false_candidates_per_field"]),
            "precision_wilson_95": metric["precision_wilson_95"],
            "completeness_wilson_95": metric["recall_wilson_95"],
            "astrometric_residuals": residuals,
            "matched": matched,
            "unmatched_detections": unmatched,
            "non_detections": missed,
        })
    return curve


def _aggregate_point(field_points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tp = sum(int(row["true_positive"]) for row in field_points)
    fp = sum(int(row["false_positive"]) for row in field_points)
    fn = sum(int(row["false_negative"]) for row in field_points)
    n_fields = len(field_points)
    residuals = [
        float(match["separation"])
        for field in field_points for match in field["matched"]
    ]
    residual_array = np.asarray(residuals, dtype=float)
    return {
        "field_count": n_fields,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "completeness": tp / (tp + fn) if tp + fn else None,
        "false_candidates_per_field": fp / n_fields if n_fields else None,
        "precision_wilson_95": wilson_interval(tp, tp + fp) if tp + fp else None,
        "completeness_wilson_95": wilson_interval(tp, tp + fn) if tp + fn else None,
        "astrometric_residuals": {
            "n": int(residual_array.size),
            "median": float(np.median(residual_array)) if residual_array.size else None,
            "p95": float(np.percentile(residual_array, 95)) if residual_array.size else None,
            "rmse": float(np.sqrt(np.mean(residual_array ** 2))) if residual_array.size else None,
        },
    }


def _field_bootstrap(field_points, *, draws: int, seed: int) -> dict[str, Any]:
    grouped = {}
    for index, row in enumerate(field_points):
        group_id = str(row.get("independence_group_id") or row.get("field_id") or f"field-{index}")
        grouped.setdefault(group_id, []).append(row)
    group_ids = sorted(grouped)
    if len(group_ids) < 2:
        return {
            "draws": 0,
            "seed": int(seed),
            "independent_group_count": len(group_ids),
            "intervals_95": None,
            "warning": "At least two independent sky-field groups are required for field-level bootstrap intervals.",
        }
    rng = np.random.default_rng(seed)
    names = ("precision", "completeness", "false_candidates_per_field")
    samples = {name: [] for name in names}
    n_groups = len(group_ids)
    for _ in range(int(draws)):
        picked = rng.integers(0, n_groups, size=n_groups)
        block = []
        for index in picked:
            block.extend(grouped[group_ids[int(index)]])
        point = _aggregate_point(block)
        for name in names:
            value = point[name]
            if value is not None and math.isfinite(float(value)):
                samples[name].append(float(value))
    return {
        "draws": int(draws),
        "seed": int(seed),
        "independent_group_count": n_groups,
        "intervals_95": {
            name: (
                [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]
                if values else None
            )
            for name, values in samples.items()
        },
        "resampling_unit": "independent sky-field group (related observing periods resampled together)",
    }


def _select_operating_point(curve, target_metric, target):
    if target_metric == "false_candidates_per_field":
        getter = lambda row: row["false_candidates_per_field"]
    else:
        getter = lambda row: row["completeness"]
    candidates = [row for row in curve if getter(row) is not None]
    if not candidates:
        return None
    chosen = min(
        candidates,
        key=lambda row: (abs(float(getter(row)) - float(target)), -float(row["threshold"])),
    )
    return {
        "threshold": chosen["threshold"],
        "observed_value": getter(chosen),
        "target_value": float(target),
        "absolute_target_difference": abs(float(getter(chosen)) - float(target)),
        "point": chosen,
        "selection_rule": "nearest observed operating point; no interpolated detections",
    }


def compare_benchmark_package(package: Mapping[str, Any], *, bootstrap_draws: int = 2000,
                              seed: int = 20261125) -> dict[str, Any]:
    """Compare the four methods only after validating identical field inputs."""
    if package.get("schema") != SCHEMA:
        raise ValueError(f"package schema must be {SCHEMA}")
    fields = package.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("package.fields must contain at least one field")
    if int(bootstrap_draws) < 100:
        raise ValueError("bootstrap_draws must be at least 100 for reported intervals")
    target = package.get("matched_target")
    if not isinstance(target, Mapping) or not target or len(target) > 2:
        raise ValueError("matched_target must contain false_candidates_per_field, completeness or both")
    allowed_targets = {"false_candidates_per_field", "completeness"}
    if not set(target).issubset(allowed_targets):
        raise ValueError("matched_target has an unsupported metric")
    target_values = {}
    for target_metric, raw_value in target.items():
        target_value = float(raw_value)
        if not math.isfinite(target_value) or target_value < 0 or (
            target_metric == "completeness" and not 0 < target_value <= 1
        ):
            raise ValueError(f"matched target {target_metric} is outside its valid range")
        target_values[target_metric] = target_value

    thresholds_by_method = package.get("score_thresholds")
    if not isinstance(thresholds_by_method, Mapping):
        raise ValueError("score_thresholds must define a threshold list for every baseline")
    missing = [name for name in REQUIRED_METHODS if name not in thresholds_by_method]
    if missing:
        raise ValueError("score_thresholds is missing: " + ", ".join(missing))
    threshold_map = {}
    for method in REQUIRED_METHODS:
        values = sorted({float(x) for x in thresholds_by_method[method]}, reverse=True)
        if not values or any(not math.isfinite(x) for x in values):
            raise ValueError(f"{method} needs at least one finite score threshold")
        threshold_map[method] = values

    field_ids = []
    per_field = []
    method_field_points = {name: [] for name in REQUIRED_METHODS}
    expected_signature = None
    dataset_classes = set()
    for index, field in enumerate(fields):
        signature = _validate_signature(field.get("input_signature") or {}, field.get("truth_catalogue") or [])
        field_id = signature["field_id"]
        if field_id in field_ids:
            raise ValueError(f"duplicate field_id: {field_id}")
        field_ids.append(field_id)
        dataset_classes.add(signature["dataset_class"])
        if field.get("split") not in {"development", "blind_test", "held_out", "not_split"}:
            raise ValueError(f"field {field_id} must declare split")
        methods = field.get("methods")
        if not isinstance(methods, Mapping):
            raise ValueError(f"field {field_id} is missing method records")
        missing_methods = [name for name in REQUIRED_METHODS if name not in methods]
        if missing_methods:
            raise ValueError(f"field {field_id} is missing methods: {', '.join(missing_methods)}")
        for method in REQUIRED_METHODS:
            record = methods[method]
            if not isinstance(record, Mapping):
                raise ValueError(f"{field_id}.{method} must be an object")
            method_signature = _validate_signature(
                record.get("input_signature") or {}, field.get("truth_catalogue") or []
            )
            if method_signature != signature:
                raise ValueError(
                    f"{field_id}.{method} input signature differs from the common field signature"
                )
            method_field_points[method].append(record)
        if expected_signature is None:
            expected_signature = {
                "coordinate_frame": signature["coordinate_frame"],
                "coordinate_unit": signature["coordinate_unit"],
            }
        elif (
            signature["coordinate_frame"] != expected_signature["coordinate_frame"]
            or signature["coordinate_unit"] != expected_signature["coordinate_unit"]
        ):
            raise ValueError("all fields in one benchmark must use the same coordinate frame and unit")

        radius = float(field.get("match_radius", 0))
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError(f"field {field_id} needs a positive match_radius")
        area = field.get("field_area_deg2")
        if area is not None and (not math.isfinite(float(area)) or float(area) <= 0):
            raise ValueError(f"field {field_id} has invalid field_area_deg2")
        truth = field["truth_catalogue"]
        method_curves = {}
        for method in REQUIRED_METHODS:
            detections = _normalise_detections(
                method, methods[method].get("detections", [])
            )
            curve = _evaluate_field_method(truth, detections, threshold_map[method], radius)
            method_curves[method] = curve
        independence_group_id = str(field.get("independence_group_id") or field_id)
        if not independence_group_id:
            raise ValueError(f"field {field_id}: independence_group_id cannot be blank")
        per_field.append({
            "field_id": field_id,
            "independence_group_id": independence_group_id,
            "dataset_class": signature["dataset_class"],
            "split": field["split"],
            "input_signature": signature,
            "match_radius": radius,
            "field_area_deg2": float(area) if area is not None else None,
            "truth_count": len(truth),
            "method_curves": method_curves,
        })

    aggregate = {}
    matched = {}
    for method in REQUIRED_METHODS:
        threshold_points = []
        for threshold in threshold_map[method]:
            selected_fields = []
            for field_report in per_field:
                field_curve = field_report["method_curves"][method]
                point = next(row for row in field_curve if row["threshold"] == threshold)
                selected_fields.append(point)
            point = _aggregate_point(selected_fields)
            point["threshold"] = threshold
            point["by_field"] = [
                {"field_id": field_report["field_id"], **next(
                    row for row in field_report["method_curves"][method]
                    if row["threshold"] == threshold
                )}
                for field_report in per_field
            ]
            threshold_points.append(point)
        bootstrap_by_threshold = {}
        for index, threshold in enumerate(threshold_map[method]):
            bootstrap_by_threshold[str(threshold)] = _field_bootstrap(
                [{
                    "field_id": report["field_id"],
                    "independence_group_id": report["independence_group_id"],
                    **next(row for row in report["method_curves"][method]
                           if row["threshold"] == threshold),
                } for report in per_field],
                draws=bootstrap_draws, seed=seed + index,
            )
        aggregate[method] = {
            "threshold_curve": threshold_points,
            "field_bootstrap_by_threshold": bootstrap_by_threshold,
        }
        matched[method] = {
            metric: _select_operating_point(threshold_points, metric, target_value)
            for metric, target_value in target_values.items()
        }

    scientifically_eligible = (
        dataset_classes == {"real"}
        and all(row["split"] in {"blind_test", "held_out"} for row in per_field)
    )
    return {
        "schema": "chronos-four-baseline-report/1.0",
        "benchmark_id": str(package.get("benchmark_id", "unnamed")),
        "methods": list(REQUIRED_METHODS),
        "fields": per_field,
        "aggregate": aggregate,
        "matched_operating_points": {
            "targets": target_values,
            "methods": matched,
            "interpretation": "Each target is matched independently using the nearest observed threshold for each method.",
        },
        "reproducibility": {
            "input_signature_fields": [
                "field_id", "dataset_class", "exposure_ids", "mask_sha256",
                "truth_catalogue_sha256", "coordinate_frame", "coordinate_unit",
            ],
            "score_thresholds": threshold_map,
            "matching_radii_by_field": {
                row["field_id"]: row["match_radius"] for row in per_field
            },
            "bootstrap_draws": int(bootstrap_draws),
            "bootstrap_seed": int(seed),
            "truth_catalogue_digests_verified": True,
            "same_input_enforced_for_all_methods": True,
        },
        "scientific_claim_eligible": scientifically_eligible,
        "interpretation": (
            "All four methods were evaluated on the same declared field inputs and truth catalogues. "
            "This report does not establish a performance advantage unless it is based on independent, "
            "real, held-out fields and a preregistered threshold policy."
        ),
        "limitations": [
            "This evaluator scores supplied detector records; method execution must be performed by the same frozen pipeline runner.",
            "Matched operating points select the nearest observed threshold and do not interpolate detections.",
            "Field bootstrap intervals require independent fields and do not correct selection bias.",
            "For sky-coordinate arcsecond comparisons, the same validated WCS transform and coordinate convention must be used for truth and detections.",
            "No winner is declared by this report.",
        ],
    }
