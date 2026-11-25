"""Auditable, non-extrapolating multidimensional injection selection function.

The model is deliberately stratified rather than silently smoothing across
unobserved covariate space. Bin edges and detector-zone levels must be frozen
before outcomes are inspected. A cell is usable only when it contains enough
independent real-field injection trials; unsupported cells remain unsupported.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

SCHEMA = "chronos-multidimensional-selection-function/1.0"
NUMERIC_DIMENSIONS = (
    "flux_jy",
    "wavelength_um",
    "crowding_index",
    "background_rms",
    "epoch_count",
)
REQUIRED_TRIAL_METADATA = (
    "method_id",
    "processing_config_sha256",
    "injection_protocol_sha256",
    "calibration_manifest_sha256",
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False, default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: Any, label: str) -> str:
    text = str(value or "").lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{label} must be a 64-character SHA-256 digest")
    return text


def validate_bin_spec(bin_spec: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete, predeclared joint covariate partition."""
    if not isinstance(bin_spec, Mapping):
        raise ValueError("selection_bin_spec must be an object")
    edges = bin_spec.get("edges")
    zones = bin_spec.get("detector_zone_levels")
    if not isinstance(edges, Mapping):
        raise ValueError("selection bin specification requires numeric edges")
    normalized_edges: dict[str, list[float]] = {}
    for dimension in NUMERIC_DIMENSIONS:
        raw = edges.get(dimension)
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            raise ValueError(f"{dimension} requires at least two predeclared bin edges")
        try:
            values = [float(item) for item in raw]
        except (TypeError, ValueError):
            raise ValueError(f"{dimension} bin edges must be finite numbers") from None
        if any(not math.isfinite(item) for item in values) or any(
            right <= left for left, right in zip(values, values[1:])
        ):
            raise ValueError(f"{dimension} bin edges must be finite and strictly increasing")
        normalized_edges[dimension] = values
    if not isinstance(zones, (list, tuple)) or not zones:
        raise ValueError("detector_zone_levels must be a non-empty predeclared list")
    normalized_zones = [str(value).strip() for value in zones]
    if any(not value for value in normalized_zones) or len(set(normalized_zones)) != len(normalized_zones):
        raise ValueError("detector_zone_levels must contain unique non-empty labels")
    return {
        "schema": "chronos-selection-bin-spec/1.0",
        "edges": normalized_edges,
        "detector_zone_levels": normalized_zones,
        "binning_policy": "fixed joint bins; no interpolation or extrapolation",
    }


def _numeric_bin(value: Any, edges: Sequence[float], dimension: str) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < edges[0] or number > edges[-1]:
        return None
    index = int(np.searchsorted(np.asarray(edges, dtype=float), number, side="right") - 1)
    return min(index, len(edges) - 2)


def _cell_key(covariates: Mapping[str, Any], spec: Mapping[str, Any]) -> tuple[int, ...] | None:
    key: list[int] = []
    for dimension in NUMERIC_DIMENSIONS:
        index = _numeric_bin(covariates.get(dimension), spec["edges"][dimension], dimension)
        if index is None:
            return None
        key.append(index)
    zone = str(covariates.get("detector_zone", "")).strip()
    try:
        key.append(spec["detector_zone_levels"].index(zone))
    except ValueError:
        return None
    return tuple(key)


def _cell_id(key: Sequence[int]) -> str:
    return hashlib.sha256(
        json.dumps(list(key), separators=(",", ":")).encode("ascii")
    ).hexdigest()[:20]


def fit_selection_function(
    injection_trials: Sequence[Mapping[str, Any]],
    bin_spec: Mapping[str, Any],
    *,
    field_records: Sequence[Mapping[str, Any]],
    minimum_trials_per_cell: int = 20,
    minimum_independent_fields: int = 5,
    minimum_fields_per_cell: int = 5,
    minimum_detection_probability: float = 0.05,
) -> dict[str, Any]:
    """Fit a Jeffreys beta-binomial detection probability in fixed joint bins.

    Every trial must come from an identified real DR1/QR3 field and the same
    detection method, frozen configuration, injection protocol and calibration
    manifest. Independence groups are read from field_records and never
    inferred from field names.
    """
    if not isinstance(injection_trials, (list, tuple)) or not injection_trials:
        raise ValueError("real-field injection_trials are required for a selection function")
    if isinstance(minimum_trials_per_cell, bool) or int(minimum_trials_per_cell) != minimum_trials_per_cell or minimum_trials_per_cell < 1:
        raise ValueError("minimum_trials_per_cell must be a positive integer")
    if isinstance(minimum_independent_fields, bool) or int(minimum_independent_fields) != minimum_independent_fields or minimum_independent_fields < 2:
        raise ValueError("minimum_independent_fields must be an integer of at least two")
    if isinstance(minimum_fields_per_cell, bool) or int(minimum_fields_per_cell) != minimum_fields_per_cell or minimum_fields_per_cell < 2:
        raise ValueError("minimum_fields_per_cell must be an integer of at least two")
    if not math.isfinite(float(minimum_detection_probability)) or not 0 < minimum_detection_probability < 1:
        raise ValueError("minimum_detection_probability must be in (0, 1)")
    spec = validate_bin_spec(bin_spec)

    field_by_id: dict[str, Mapping[str, Any]] = {}
    groups: set[str] = set()
    for field in field_records:
        field_id = str(field.get("field_id", "")).strip()
        if not field_id or field_id in field_by_id:
            raise ValueError("field_records must have unique non-empty field_id values")
        field_by_id[field_id] = field
        if str(field.get("dataset_class", field.get("data_class", "unverified"))).lower() != "real":
            continue
        if field.get("independent_field") is True:
            group = str(field.get("independence_group_id") or field_id).strip()
            if group:
                groups.add(group)
    if len(groups) < int(minimum_independent_fields):
        raise ValueError(
            f"selection calibration requires at least {minimum_independent_fields} independently attested real fields; found {len(groups)}"
        )

    metadata_values: dict[str, set[str]] = {name: set() for name in REQUIRED_TRIAL_METADATA}
    cells: dict[tuple[int, ...], dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "recovered": 0, "field_ids": set(), "trial_ids": set()}
    )
    trial_ids: set[str] = set()
    trial_fields: set[str] = set()
    for index, raw in enumerate(injection_trials):
        if not isinstance(raw, Mapping):
            raise ValueError(f"injection trial {index} must be an object")
        trial_id = str(raw.get("trial_id", "")).strip()
        field_id = str(raw.get("field_id", "")).strip()
        if not trial_id or trial_id in trial_ids:
            raise ValueError("injection trial_id values must be non-empty and unique")
        trial_ids.add(trial_id)
        if field_id not in field_by_id:
            raise ValueError(f"injection trial {trial_id} references an unknown field_id")
        field = field_by_id[field_id]
        if str(field.get("dataset_class", field.get("data_class", "unverified"))).lower() != "real":
            raise ValueError(f"injection trial {trial_id} is not attached to a real field")
        if field.get("independent_field") is not True:
            raise ValueError(f"injection trial {trial_id} is not attached to an independently attested field")
        if str(raw.get("dataset_class", "")).lower() != "real":
            raise ValueError(f"injection trial {trial_id} must be labelled dataset_class='real'")
        if str(raw.get("release", "")).upper() not in {"DR1", "QR3"}:
            raise ValueError(f"injection trial {trial_id} must use DR1 or QR3")
        if not isinstance(raw.get("recovered"), bool):
            raise ValueError(f"injection trial {trial_id} recovered must be a boolean")
        for name in REQUIRED_TRIAL_METADATA:
            value = str(raw.get(name, "")).strip()
            if not value:
                raise ValueError(f"injection trial {trial_id} is missing {name}")
            metadata_values[name].add(value)
        for name in ("processing_config_sha256", "injection_protocol_sha256", "calibration_manifest_sha256"):
            _sha256(raw.get(name), name)
        if raw.get("independence_group_id") is not None:
            declared_group = str(raw["independence_group_id"]).strip()
            actual_group = str(field.get("independence_group_id") or field_id).strip()
            if declared_group != actual_group:
                raise ValueError(f"injection trial {trial_id} independence_group_id mismatch")
        covariates = raw.get("covariates")
        if not isinstance(covariates, Mapping):
            raise ValueError(f"injection trial {trial_id} needs a covariates object")
        key = _cell_key(covariates, spec)
        if key is None:
            raise ValueError(f"injection trial {trial_id} falls outside the predeclared selection bins")
        cell = cells[key]
        cell["n"] += 1
        cell["recovered"] += int(raw["recovered"])
        cell["field_ids"].add(field_id)
        cell["trial_ids"].add(trial_id)
        trial_fields.add(field_id)

    inconsistent = [name for name, values in metadata_values.items() if len(values) != 1]
    if inconsistent:
        raise ValueError("selection trials mix frozen provenance fields: " + ", ".join(inconsistent))
    if not trial_fields:
        raise ValueError("selection trials do not cover any real field")
    groups_covered = {
        str(field_by_id[field_id].get("independence_group_id") or field_id)
        for field_id in trial_fields
    }
    if len(groups_covered) < int(minimum_independent_fields):
        raise ValueError(
            f"selection injections cover only {len(groups_covered)} independent fields; require {minimum_independent_fields}"
        )

    try:
        from scipy.stats import beta as beta_distribution
    except ImportError as exc:
        raise RuntimeError("SciPy is required for Jeffreys beta-binomial intervals") from exc

    cell_rows = []
    for key, counts in sorted(cells.items()):
        n = int(counts["n"])
        k = int(counts["recovered"])
        alpha, beta = k + 0.5, n - k + 0.5
        mean = alpha / (alpha + beta)
        independent_cell_fields = len(counts["field_ids"])
        supported = (
            n >= int(minimum_trials_per_cell)
            and independent_cell_fields >= int(minimum_fields_per_cell)
            and mean >= float(minimum_detection_probability)
        )
        cell_rows.append({
            "cell_id": _cell_id(key),
            "bin_indices": list(key),
            "injected": n,
            "recovered": k,
            "posterior": {
                "distribution": "Beta(recovered+0.5, missed+0.5)",
                "alpha": alpha,
                "beta": beta,
                "mean_detection_probability": mean,
                "lower_95": float(beta_distribution.ppf(0.025, alpha, beta)),
                "upper_95": float(beta_distribution.ppf(0.975, alpha, beta)),
            },
            "field_ids": sorted(counts["field_ids"]),
            "independent_field_count": independent_cell_fields,
            "supported": bool(supported),
            "unsupported_reason": None if supported else (
                "too_few_trials_in_joint_cell" if n < int(minimum_trials_per_cell)
                else "too_few_independent_fields_in_joint_cell" if independent_cell_fields < int(minimum_fields_per_cell)
                else "posterior_mean_below_minimum_detection_probability"
            ),
        })
    supported_cells = sum(row["supported"] for row in cell_rows)
    return {
        "schema": SCHEMA,
        "status": "supported" if supported_cells else "unsupported",
        "supported": bool(supported_cells),
        "bin_spec": spec,
        "minimum_trials_per_cell": int(minimum_trials_per_cell),
        "minimum_independent_fields": int(minimum_independent_fields),
        "minimum_fields_per_cell": int(minimum_fields_per_cell),
        "minimum_detection_probability": float(minimum_detection_probability),
        "independent_field_count": len(groups_covered),
        "trial_count": len(trial_ids),
        "field_ids": sorted(trial_fields),
        "frozen_provenance": {name: next(iter(values)) for name, values in metadata_values.items()},
        "cells": cell_rows,
        "supported_cell_count": supported_cells,
        "unsupported_cell_count": len(cell_rows) - supported_cells,
        "injection_trials_sha256": _canonical_sha256(list(injection_trials)),
        "bin_spec_sha256": _canonical_sha256(spec),
        "limitations": [
            "The model estimates detection probability only inside observed, sufficiently populated joint bins.",
            "No interpolation, extrapolation, smoothing, or substitution from a neighbouring detector zone is performed.",
            "Injection trials must represent the scientific target population and the exact frozen detector pipeline.",
            "The beta-binomial intervals condition on fixed bins and do not model cross-field or shared calibration covariance.",
            "A supported selection function is necessary but not sufficient for a population claim.",
        ],
    }


def predict_selection_probability(
    selection_function: Mapping[str, Any],
    covariates: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a cell posterior or an explicit unsupported result; never extrapolate."""
    if selection_function.get("schema") != SCHEMA or not isinstance(selection_function.get("bin_spec"), Mapping):
        raise ValueError("selection_function has an unsupported schema or missing bin_spec")
    spec = validate_bin_spec(selection_function["bin_spec"])
    key = _cell_key(covariates, spec)
    if key is None:
        return {
            "status": "outside_predeclared_support",
            "selection_probability": None,
            "selection_weight": None,
            "cell_id": None,
        }
    wanted = _cell_id(key)
    cell = next((row for row in selection_function.get("cells", []) if row.get("cell_id") == wanted), None)
    if cell is None:
        return {
            "status": "unobserved_joint_cell",
            "selection_probability": None,
            "selection_weight": None,
            "cell_id": wanted,
        }
    if cell.get("supported") is not True:
        return {
            "status": "insufficient_joint_cell_support",
            "selection_probability": None,
            "selection_weight": None,
            "cell_id": wanted,
            "injected": cell.get("injected"),
            "unsupported_reason": cell.get("unsupported_reason"),
        }
    posterior = cell.get("posterior") or {}
    probability = float(posterior.get("mean_detection_probability"))
    if not math.isfinite(probability) or probability <= 0:
        raise ValueError("selection cell posterior contains an invalid detection probability")
    return {
        "status": "supported",
        "selection_probability": probability,
        "selection_probability_95": [
            float(posterior["lower_95"]), float(posterior["upper_95"])
        ],
        "selection_weight": 1.0 / probability,
        "cell_id": wanted,
        "injected": int(cell["injected"]),
        "recovered": int(cell["recovered"]),
    }
