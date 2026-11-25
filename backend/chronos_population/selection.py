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
    "preregistration_sha256",
    "recovery_rule_sha256",
    "quality_policy_sha256",
)



def _validate_recovery_evidence(
    raw: Mapping[str, Any], trial_id: str
) -> dict[str, Any]:
    """Derive recovery from frozen production-selection and photometry evidence."""
    evidence = raw.get("recovery_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError(f"injection trial {trial_id} requires recovery_evidence")
    if evidence.get("rule_id") != RECOVERY_RULE_ID:
        raise ValueError(f"injection trial {trial_id} uses an unsupported recovery rule")
    if _sha256(raw.get("recovery_rule_sha256"), "recovery_rule_sha256") != RECOVERY_RULE_SHA256:
        raise ValueError(f"injection trial {trial_id} recovery-rule digest does not match this implementation")
    detector_sha = _sha256(evidence.get("detector_output_sha256"), "detector_output_sha256")
    truth_sha = _sha256(evidence.get("injection_truth_sha256"), "injection_truth_sha256")
    image_id = str(evidence.get("image_id") or "").strip()
    if not image_id:
        raise ValueError(f"injection trial {trial_id} requires an image_id")
    try:
        peak_snr = float(evidence.get("peak_snr"))
        threshold_sigma = float(evidence.get("threshold_sigma"))
        separation = float(evidence.get("separation_pixels"))
        match_radius = float(evidence.get("match_radius_pixels"))
        fit_ql = float(evidence.get("fit_ql"))
        fit_ql_max = float(evidence.get("fit_ql_max"))
        background_fraction = float(evidence.get("background_fraction"))
        background_fraction_max = float(evidence.get("background_fraction_max"))
    except (TypeError, ValueError):
        raise ValueError(f"injection trial {trial_id} has incomplete numeric recovery evidence") from None
    numeric = (
        peak_snr, threshold_sigma, separation, match_radius,
        fit_ql, fit_ql_max, background_fraction, background_fraction_max,
    )
    if not all(math.isfinite(value) for value in numeric):
        raise ValueError(f"injection trial {trial_id} recovery diagnostics must be finite")
    if (
        peak_snr < 0 or threshold_sigma <= 0 or separation < 0 or match_radius <= 0
        or fit_ql < 0 or fit_ql_max <= 0
        or background_fraction < 0 or background_fraction_max <= 0
    ):
        raise ValueError(f"injection trial {trial_id} recovery diagnostics are outside valid bounds")

    quality_policy = raw.get("quality_policy")
    if not isinstance(quality_policy, Mapping):
        raise ValueError(f"injection trial {trial_id} requires the frozen quality_policy object")
    quality_policy_payload = {
        "policy_id": str(quality_policy.get("policy_id", "")).strip(),
        "flag_policy": str(quality_policy.get("flag_policy", "")).strip(),
        "fit_ql_max": float(quality_policy.get("fit_ql_max", float("nan"))),
        "max_abs_background_to_flux_ratio": float(
            quality_policy.get("max_abs_background_to_flux_ratio", float("nan"))
        ),
    }
    if not quality_policy_payload["policy_id"]:
        raise ValueError(f"injection trial {trial_id} quality_policy.policy_id is required")
    if not math.isfinite(quality_policy_payload["fit_ql_max"]) or quality_policy_payload["fit_ql_max"] <= 0:
        raise ValueError(f"injection trial {trial_id} quality_policy.fit_ql_max must be positive")
    if (
        not math.isfinite(quality_policy_payload["max_abs_background_to_flux_ratio"])
        or quality_policy_payload["max_abs_background_to_flux_ratio"] <= 0
    ):
        raise ValueError(f"injection trial {trial_id} quality_policy background threshold must be positive")
    quality_sha = _sha256(raw.get("quality_policy_sha256"), "quality_policy_sha256")
    if quality_sha != _canonical_sha256(quality_policy_payload):
        raise ValueError(f"injection trial {trial_id} quality-policy digest does not match its policy object")
    if not math.isclose(fit_ql_max, quality_policy_payload["fit_ql_max"], rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"injection trial {trial_id} fit_ql_max differs from its frozen quality policy")
    if not math.isclose(
        background_fraction_max,
        quality_policy_payload["max_abs_background_to_flux_ratio"],
        rel_tol=0.0, abs_tol=1e-12,
    ):
        raise ValueError(f"injection trial {trial_id} background threshold differs from its frozen quality policy")

    try:
        flags = int(evidence.get("flags"))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"injection trial {trial_id} flags must be a non-negative integer") from None
    if isinstance(evidence.get("flags"), bool) or flags < 0 or flags != evidence.get("flags"):
        raise ValueError(f"injection trial {trial_id} flags must be a non-negative integer")
    try:
        from research_discovery.spherex.flag_policy import policy_mask
        mask, _ = policy_mask(quality_policy_payload["flag_policy"])
    except (ImportError, ValueError) as exc:
        raise ValueError(f"injection trial {trial_id} has an invalid photometry flag policy: {exc}") from exc
    flags_pass = (flags & mask) == 0

    predicates = {}
    for key in (
        "peak_is_local_maximum",
        "one_to_one_assignment",
        "primary_selection_rule_passed",
        "fit_quality_pass",
        "background_quality_pass",
    ):
        value = evidence.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"injection trial {trial_id} recovery_evidence.{key} must be boolean")
        predicates[key] = value
    if evidence.get("photometry_flags_pass") is not flags_pass:
        raise ValueError(f"injection trial {trial_id} photometry_flags_pass disagrees with the frozen flag mask")
    if evidence.get("fit_quality_pass") is not (fit_ql <= fit_ql_max):
        raise ValueError(f"injection trial {trial_id} fit_quality_pass disagrees with fit_ql")
    if evidence.get("background_quality_pass") is not (
        background_fraction <= background_fraction_max
    ):
        raise ValueError(f"injection trial {trial_id} background_quality_pass disagrees with its fraction")

    peak_id = str(evidence.get("peak_id") or "").strip()
    if peak_id:
        injected_xy = evidence.get("injected_xy")
        peak_xy = evidence.get("peak_xy")
        if (
            not isinstance(injected_xy, (list, tuple)) or len(injected_xy) != 2
            or not isinstance(peak_xy, (list, tuple)) or len(peak_xy) != 2
        ):
            raise ValueError(f"injection trial {trial_id} matched peak requires injected_xy and peak_xy")
        try:
            ix, iy = (float(value) for value in injected_xy)
            px, py = (float(value) for value in peak_xy)
        except (TypeError, ValueError):
            raise ValueError(f"injection trial {trial_id} peak coordinates must be numeric") from None
        if not all(math.isfinite(value) for value in (ix, iy, px, py)):
            raise ValueError(f"injection trial {trial_id} peak coordinates must be finite")
        measured_separation = math.hypot(px - ix, py - iy)
        if not math.isclose(measured_separation, separation, rel_tol=0.0, abs_tol=1e-3):
            raise ValueError(f"injection trial {trial_id} separation_pixels disagrees with the supplied peak coordinates")
    else:
        measured_separation = separation

    derived = bool(
        predicates["peak_is_local_maximum"]
        and predicates["one_to_one_assignment"]
        and predicates["primary_selection_rule_passed"]
        and flags_pass
        and predicates["fit_quality_pass"]
        and predicates["background_quality_pass"]
        and peak_snr >= threshold_sigma
        and measured_separation <= match_radius
        and fit_ql <= fit_ql_max
        and background_fraction <= background_fraction_max
        and peak_id
    )
    if raw.get("recovered") is not derived:
        raise ValueError(
            f"injection trial {trial_id} recovered disagrees with the full production peak/matching rule"
        )
    return {
        "rule_id": RECOVERY_RULE_ID,
        "detector_output_sha256": detector_sha,
        "injection_truth_sha256": truth_sha,
        "image_id": image_id,
        "peak_id": peak_id or None,
        "peak_snr": peak_snr,
        "threshold_sigma": threshold_sigma,
        "separation_pixels": measured_separation,
        "match_radius_pixels": match_radius,
        "fit_ql": fit_ql,
        "fit_ql_max": fit_ql_max,
        "background_fraction": background_fraction,
        "background_fraction_max": background_fraction_max,
        "photometry_flags_pass": flags_pass,
        **predicates,
        "derived_recovered": derived,
    }


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False, default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


RECOVERY_RULE_SPEC = {
    "id": "chronos-production-peak-match-fit-quality/1.0",
    "predicates": [
        "production-local-maximum",
        "production-primary-selection",
        "one-to-one-injection-to-peak-assignment",
        "peak-snr-at-or-above-frozen-threshold",
        "separation-within-frozen-match-radius",
        "predeclared-photometry-flag-mask-passes",
        "fit-ql-at-or-below-predeclared-maximum",
        "background-fraction-at-or-below-predeclared-maximum",
    ],
}
RECOVERY_RULE_ID = RECOVERY_RULE_SPEC["id"]
RECOVERY_RULE_SHA256 = _canonical_sha256(RECOVERY_RULE_SPEC)

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
    posterior_draws: int = 10000,
    seed: int = 0,
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
    if isinstance(posterior_draws, bool) or int(posterior_draws) != posterior_draws or posterior_draws < 1000:
        raise ValueError("posterior_draws must be an integer of at least 1000")
    if isinstance(seed, bool) or int(seed) != seed or seed < 0:
        raise ValueError("seed must be a non-negative integer")
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
        lambda: {
            "n": 0, "recovered": 0, "field_ids": set(),
            "independence_groups": set(), "group_counts": defaultdict(
                lambda: {"n": 0, "recovered": 0}
            ), "trial_ids": set(),
        }
    )
    trial_ids: set[str] = set()
    trial_fields: set[str] = set()
    field_trial_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"injected": 0, "recovered": 0}
    )
    assigned_peaks: set[tuple[str, str, str]] = set()
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
        for name in (
            "processing_config_sha256", "injection_protocol_sha256",
            "calibration_manifest_sha256", "preregistration_sha256",
            "recovery_rule_sha256", "quality_policy_sha256",
        ):
            _sha256(raw.get(name), name)
        recovery = _validate_recovery_evidence(raw, trial_id)
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
        group_id = str(field.get("independence_group_id") or field_id).strip()
        cell["n"] += 1
        cell["recovered"] += int(recovery["derived_recovered"])
        cell["field_ids"].add(field_id)
        cell["independence_groups"].add(group_id)
        cell["group_counts"][group_id]["n"] += 1
        cell["group_counts"][group_id]["recovered"] += int(recovery["derived_recovered"])
        cell["trial_ids"].add(trial_id)
        field_trial_counts[field_id]["injected"] += 1
        field_trial_counts[field_id]["recovered"] += int(recovery["derived_recovered"])
        if recovery["derived_recovered"]:
            assignment = (
                recovery["detector_output_sha256"],
                recovery["image_id"],
                str(recovery["peak_id"]),
            )
            if assignment in assigned_peaks:
                raise ValueError(
                    f"injection trial {trial_id} reuses a production peak already assigned to another injection"
                )
            assigned_peaks.add(assignment)
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

    cell_rows = []
    for key, counts in sorted(cells.items()):
        n = int(counts["n"])
        k = int(counts["recovered"])
        independent_cell_fields = len(counts["independence_groups"])
        group_ids = sorted(counts["group_counts"])
        rng_seed = int(_canonical_sha256({"seed": int(seed), "cell": list(key)})[:8], 16)
        rng = np.random.default_rng(rng_seed)
        group_alpha = np.asarray(
            [counts["group_counts"][group]["recovered"] + 0.5 for group in group_ids],
            dtype=float,
        )
        group_beta = np.asarray([
            counts["group_counts"][group]["n"] - counts["group_counts"][group]["recovered"] + 0.5
            for group in group_ids
        ], dtype=float)
        group_draws = rng.beta(
            group_alpha[None, :], group_beta[None, :],
            size=(int(posterior_draws), len(group_ids)),
        )
        resample_indices = rng.integers(
            0, len(group_ids), size=(int(posterior_draws), len(group_ids))
        )
        cluster_samples = np.take_along_axis(
            group_draws, resample_indices, axis=1
        ).mean(axis=1)
        mean = float(np.mean(cluster_samples))
        lower_95, upper_95 = np.quantile(cluster_samples, [0.025, 0.975])
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
                "distribution": "field-cluster bootstrap of per-group Jeffreys beta posteriors",
                "field_group_count": independent_cell_fields,
                "posterior_draws": int(posterior_draws),
                "mean_detection_probability": mean,
                "lower_95": float(lower_95),
                "upper_95": float(upper_95),
            },
            "field_ids": sorted(counts["field_ids"]),
            "independence_group_ids": group_ids,
            "independent_field_count": independent_cell_fields,
            "per_group_trials": {
                group: dict(counts["group_counts"][group]) for group in group_ids
            },
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
        "posterior_draws": int(posterior_draws),
        "seed": int(seed),
        "independent_field_count": len(groups_covered),
        "trial_count": len(trial_ids),
        "field_ids": sorted(trial_fields),
        "field_trial_counts": [
            {"field_id": field_id, **field_trial_counts[field_id]}
            for field_id in sorted(field_trial_counts)
        ],
        "frozen_provenance": {name: next(iter(values)) for name, values in metadata_values.items()},
        "cells": cell_rows,
        "supported_cell_count": supported_cells,
        "unsupported_cell_count": len(cell_rows) - supported_cells,
        "injection_trials_sha256": _canonical_sha256(list(injection_trials)),
        "bin_spec_sha256": _canonical_sha256(spec),
        "limitations": [
            "The model estimates detection probability only inside observed, sufficiently populated joint bins.",
            "No interpolation, extrapolation, smoothing, or substitution from a neighbouring detector zone is performed.",
            "Recovery is derived from explicit peak, match, flag-mask, fit-quality and background-quality evidence; inconsistent caller labels are rejected.",
            "A detected peak can be assigned to at most one injected source within an identical detector-output image.",
            "Uncertainty resamples independently attested field groups and then draws their Jeffreys beta posteriors; trials within a field are not treated as independent fields.",
            "The field-cluster bootstrap does not model shared calibration covariance or validate the scientific representativeness of the injection distribution.",
            "Detector-output and injection-truth hashes are provenance references; the service does not retrieve or independently inspect those external bytes.",
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
