"""Expected-information-gain planning with explicit feasibility provenance."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence
import base64
import hashlib
import json
import math
import os

import numpy as np


def _entropy(probabilities):
    p = np.asarray(probabilities, dtype=float)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def _pdf(values, mean, sigma):
    z = (values - mean) / sigma
    return np.exp(-0.5 * z * z) / (math.sqrt(2.0 * math.pi) * sigma)


def _utc_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"feasibility {label} must be an ISO-8601 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"feasibility {label} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None:
        raise ValueError(f"feasibility {label} must include a timezone")
    return result


def canonical_feasibility_attestation_payload(record: Mapping[str, Any]) -> bytes:
    """Canonical bytes that an external visibility service must sign with Ed25519."""
    if not isinstance(record, Mapping):
        raise ValueError("feasibility record must be an object")
    payload = {str(key): value for key, value in record.items() if key != "attestation"}
    try:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("feasibility record must be strict JSON before attestation") from exc


def _verify_feasibility_attestation(record: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a detached Ed25519 signature against an out-of-band pinned key."""
    configured_key_id = os.environ.get("CHRONOS_FEASIBILITY_ATTESTATION_KEY_ID", "").strip()
    configured_public_key = os.environ.get(
        "CHRONOS_FEASIBILITY_ATTESTATION_PUBLIC_KEY_B64", ""
    ).strip()
    if not configured_key_id or not configured_public_key:
        return {
            "valid": False,
            "reason": "trusted_feasibility_public_key_not_configured",
        }
    attestation = record.get("attestation")
    if not isinstance(attestation, Mapping):
        return {"valid": False, "reason": "detached_attestation_missing"}
    if attestation.get("algorithm") != "Ed25519":
        return {"valid": False, "reason": "unsupported_attestation_algorithm"}
    if attestation.get("key_id") != configured_key_id:
        return {"valid": False, "reason": "attestation_key_id_does_not_match_pinned_key"}
    try:
        public_key_bytes = base64.b64decode(configured_public_key, validate=True)
        signature = base64.b64decode(
            str(attestation.get("signature_b64", "")), validate=True
        )
        if len(public_key_bytes) != 32 or len(signature) != 64:
            raise ValueError("invalid Ed25519 key or signature length")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        payload = canonical_feasibility_attestation_payload(record)
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload)
    except Exception as exc:
        return {
            "valid": False,
            "reason": f"detached_attestation_invalid:{type(exc).__name__}",
        }
    return {
        "valid": True,
        "algorithm": "Ed25519",
        "key_id": configured_key_id,
        "signed_payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _feasibility_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    record = candidate.get("feasibility")
    if record is None:
        return {
            "status": "unverified",
            "reason": "No external visibility or archive-availability evidence was supplied.",
        }
    if not isinstance(record, Mapping):
        raise ValueError("candidate feasibility must be an object")
    supplied = dict(record)
    if supplied.get("status") != "verified":
        return {
            "status": "unverified",
            "supplied_record": supplied,
            "reason": "The supplied feasibility record is not marked verified.",
        }

    # A caller-provided status string is not an attestation. Only a detached
    # signature under the deployment's out-of-band pinned Ed25519 key can
    # promote the record to verified.
    attestation_check = _verify_feasibility_attestation(supplied)
    if attestation_check.get("valid") is not True:
        return {
            "status": "unverified",
            "supplied_record": supplied,
            "attestation_verification": attestation_check,
            "reason": "External feasibility evidence is unsigned or its pinned-key signature did not verify.",
        }

    source_uri = supplied.get("source_uri")
    if not isinstance(source_uri, str) or not source_uri.startswith("https://"):
        raise ValueError("verified feasibility requires an exact HTTPS source_uri")
    checked = _utc_timestamp(supplied.get("checked_utc"), "checked_utc")
    feasible = supplied.get("feasible")
    if not isinstance(feasible, bool):
        raise ValueError("verified feasibility requires a boolean feasible field")
    window_start = supplied.get("window_start_utc")
    window_end = supplied.get("window_end_utc")
    if window_start is None or window_end is None:
        raise ValueError(
            "verified feasibility requires both window_start_utc and window_end_utc"
        )
    start = _utc_timestamp(window_start, "window_start_utc")
    end = _utc_timestamp(window_end, "window_end_utc")
    if end <= start:
        raise ValueError("feasibility window end must be later than its start")
    if not supplied.get("calculator") or not supplied.get("query_id"):
        raise ValueError("verified feasibility requires calculator and query_id")
    query_parameters = supplied.get("query_parameters")
    if not isinstance(query_parameters, Mapping) or not query_parameters:
        raise ValueError("verified feasibility requires exact query_parameters")
    digest = str(supplied.get("evidence_sha256", "")).lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("verified feasibility requires a valid evidence_sha256")
    normalized_window = {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
    }
    return {
        "status": "verified",
        "feasible": feasible,
        "source_uri": source_uri,
        "checked_utc": checked.isoformat(),
        "window": normalized_window,
        "constraints": dict(supplied.get("constraints") or {}),
        "result_detail": supplied.get("result_detail"),
        "calculator": supplied["calculator"],
        "query_id": supplied["query_id"],
        "query_parameters": dict(query_parameters),
        "evidence_sha256": digest,
        "attestation_verification": attestation_check,
    }


def expected_information_gain(
    predictions: Mapping[str, Mapping[str, float]],
    priors: Mapping[str, float] | None = None,
    measurement_sigma: float = 1.0,
    quadrature_points: int = 401,
) -> dict[str, Any]:
    names = list(predictions)
    if len(names) < 2:
        raise ValueError("at least two hypotheses are required")
    if (
        measurement_sigma <= 0 or not math.isfinite(measurement_sigma)
        or quadrature_points < 21
    ):
        raise ValueError("invalid measurement sigma or quadrature count")
    if priors is not None and set(priors) - set(names):
        raise ValueError("prior set contains hypotheses without forecasts")
    prior = np.array([float((priors or {}).get(name, 1.0)) for name in names])
    if np.any(~np.isfinite(prior)) or np.any(prior <= 0):
        raise ValueError("priors must be finite and positive")
    prior /= prior.sum()

    means, sigmas = [], []
    for name in names:
        forecast = predictions[name]
        mean = float(forecast["mean"])
        model_sigma = float(forecast.get("sigma", 0.0))
        if not math.isfinite(mean) or not math.isfinite(model_sigma) or model_sigma < 0:
            raise ValueError(f"invalid forecast for {name}")
        means.append(mean)
        sigmas.append(math.hypot(model_sigma, measurement_sigma))

    means = np.asarray(means)
    sigmas = np.asarray(sigmas)
    lower = float(np.min(means - 7.0 * sigmas))
    upper = float(np.max(means + 7.0 * sigmas))
    values = np.linspace(lower, upper, int(quadrature_points))
    step = float(values[1] - values[0])
    likelihood = np.vstack([
        _pdf(values, means[index], sigmas[index])
        for index in range(len(names))
    ])
    mixture = np.sum(prior[:, None] * likelihood, axis=0)
    posterior = prior[:, None] * likelihood / np.maximum(mixture[None, :], 1e-300)
    expected_entropy = float(
        np.sum(mixture * np.asarray([_entropy(posterior[:, j]) for j in range(values.size)])) * step
    )
    prior_entropy = _entropy(prior)
    information_gain = max(0.0, prior_entropy - expected_entropy)
    return {
        "hypotheses": names,
        "prior": dict(zip(names, prior.tolist())),
        "predictive_mean": dict(zip(names, means.tolist())),
        "predictive_model_sigma": dict(zip(names, [float(predictions[name].get("sigma", 0.0)) for name in names])),
        "measurement_sigma": float(measurement_sigma),
        "predictive_total_sigma": dict(zip(names, sigmas.tolist())),
        "prior_entropy_bits": prior_entropy,
        "expected_posterior_entropy_bits": expected_entropy,
        "expected_information_gain_bits": information_gain,
        "quadrature_points": int(quadrature_points),
        "note": "Gaussian predictive approximation; forecasts must come from physical models or measurements.",
    }


def plan_observations(
    candidates: Sequence[Mapping[str, Any]],
    priors: Mapping[str, float] | None = None,
    measurement_sigma: float = 1.0,
    alternative_priors: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("at least one candidate time is required")
    if not math.isfinite(float(measurement_sigma)) or measurement_sigma <= 0:
        raise ValueError("measurement_sigma must be finite and positive")

    ranked, rejected = [], []
    for index, candidate in enumerate(candidates):
        feasibility = _feasibility_record(candidate)
        if feasibility.get("status") == "verified" and feasibility.get("feasible") is True:
            requested_time = _utc_timestamp(candidate.get("time"), "candidate time")
            window = feasibility.get("window") or {}
            window_start = _utc_timestamp(window.get("start_utc"), "verified window start")
            window_end = _utc_timestamp(window.get("end_utc"), "verified window end")
            if not window_start <= requested_time <= window_end:
                raise ValueError(
                    "candidate time falls outside the externally verified feasibility window"
                )
        visible = candidate.get("visible", True)
        feasible_flag = candidate.get("feasible", True)
        if not isinstance(visible, bool) or not isinstance(feasible_flag, bool):
            raise ValueError(f"candidate {index} visible and feasible flags must be boolean")
        if visible is False or feasible_flag is False or (
            feasibility["status"] == "verified" and feasibility.get("feasible") is False
        ):
            rejected.append({
                "time": candidate.get("time"),
                "reason": candidate.get("reason", "not visible/feasible"),
                "feasibility": feasibility,
            })
            continue

        predictions = candidate.get("predictions") or {}
        candidate_sigma = float(candidate.get("measurement_sigma", measurement_sigma))
        score = expected_information_gain(predictions, priors, candidate_sigma)
        measurement = {
            key: candidate.get(key)
            for key in (
                "candidate_id", "time", "wavelength_um", "detector_id",
                "array_configuration", "measurement_type",
            )
            if key in candidate
        }
        ranked.append({
            "time": candidate.get("time"),
            "measurement": measurement,
            "information_gain": score["expected_information_gain_bits"],
            "score": score,
            "constraints": dict(candidate.get("constraints") or {}),
            "feasibility": feasibility,
            "interpretation": (
                "Candidate is ranked using the supplied hypothesis forecasts. "
                "External feasibility is verified separately."
            ),
        })

    ranked.sort(key=lambda item: item["information_gain"], reverse=True)
    if not ranked:
        raise ValueError("no candidate measurements passed the declared filters")

    sensitivity = {}
    for label, alternative in (alternative_priors or {}).items():
        if not str(label).strip():
            raise ValueError("alternative prior set labels must be non-empty")
        local = []
        for candidate in ranked:
            model_forecasts = {
                name: {
                    "mean": candidate["score"]["predictive_mean"][name],
                    "sigma": candidate["score"]["predictive_model_sigma"][name],
                }
                for name in candidate["score"]["hypotheses"]
            }
            local_score = expected_information_gain(
                model_forecasts,
                alternative,
                candidate["score"]["measurement_sigma"],
            )
            local.append({
                "time": candidate["time"],
                "information_gain_bits": local_score["expected_information_gain_bits"],
            })
        local.sort(key=lambda item: item["information_gain_bits"], reverse=True)
        sensitivity[str(label)] = {
            "top_ranked_time": local[0]["time"],
            "ranked_candidates": local,
        }

    recommended = ranked[0]
    result_status = (
        "forecast_ranked_feasibility_verified"
        if recommended["feasibility"]["status"] == "verified"
        and recommended["feasibility"].get("feasible") is True
        else "forecast_ranked_feasibility_unverified"
    )
    return {
        "recommended": recommended,
        "recommendation_status": result_status,
        "ranked": ranked,
        "rejected": rejected,
        "prior_sensitivity": sensitivity,
        "method": "expected reduction in Shannon entropy under Gaussian predictive distributions",
        "limitations": [
            "The planner validates that the requested candidate time lies within the supplied external feasibility window; it does not authenticate the external service or its data.",
            "An unverified candidate can be information-ranked but is not asserted to be observable or available.",
            "Inputs must be physical forecasts, not guessed values.",
            "Prior sensitivity is evaluated only for the alternative prior sets supplied by the caller.",
            "This does not schedule or command a telescope.",
        ],
    }


def plan_candidate_observations(candidates: Sequence[Mapping[str, Any]], *,
                                priors: Mapping[str, float] | None = None,
                                prior_sets: Mapping[str, Mapping[str, float]] | None = None,
                                measurement_sigma: float = 1.0) -> dict[str, Any]:
    if not candidates:
        raise ValueError("at least one candidate observation is required")
    normalized, provenance, raw_feasibility = [], {}, {}
    seen = set()
    for index, raw in enumerate(candidates):
        cid = str(raw.get("candidate_observation_id", raw.get("id", ""))).strip()
        if not cid or cid in seen:
            raise ValueError("candidate observation IDs must be present and unique")
        seen.add(cid)
        predictions = raw.get("predictions") or {}
        fp = raw.get("forecast_provenance") or {}
        missing = sorted(set(predictions) - set(fp))
        if missing:
            raise ValueError(f"{cid} forecast provenance missing models: {missing}")
        for name in predictions:
            item = fp[name]
            if not isinstance(item, Mapping) or not item.get("fit_id") or not item.get("input_observation_ids"):
                raise ValueError(f"{cid} model {name} requires fit_id and input_observation_ids")
        option = dict(raw.get("measurement_option") or {})
        feasibility = raw.get("feasibility")
        if feasibility is None:
            feasibility = raw.get("feasibility_evidence") or {}
        # A service response marked "available" is data, not a trusted
        # feasibility attestation. Do not silently upgrade it to "verified".
        # It can be retained in the report, but only an explicitly verified,
        # bounded record can make a candidate eligible for recommendation.
        normalized_feasibility = dict(feasibility) if isinstance(feasibility, Mapping) else None
        normalized.append({
            "candidate_id": cid, "time": raw.get("time"),
            "wavelength_um": option.get("wavelength_um", raw.get("wavelength_um")),
            "detector_id": option.get("detector_id", raw.get("detector_id")),
            "array_configuration": option.get("array_configuration", option.get("array")),
            "measurement_type": option.get("measurement_type"),
            "predictions": predictions,
            "measurement_sigma": raw.get("measurement_sigma", measurement_sigma),
            "feasibility": normalized_feasibility,
            "constraints": dict(raw.get("constraints") or option.get("constraints") or {}),
            "visible": raw.get("visible", True), "feasible": raw.get("feasible", True),
        })
        provenance[cid] = {"forecast_provenance": dict(fp), "measurement_option": option,
                            "purpose": raw.get("purpose")}
        raw_feasibility[cid] = dict(feasibility) if isinstance(feasibility, Mapping) else {}
    base = plan_observations(normalized, priors=priors, measurement_sigma=measurement_sigma,
                             alternative_priors=prior_sets)
    ranked = []
    for rank, item in enumerate(base["ranked"], start=1):
        measurement = dict(item.get("measurement") or {})
        cid = str(measurement.get("candidate_id", ""))
        extra = provenance.get(cid, {})
        ranked.append({**item, "rank": rank, "candidate_observation_id": cid,
            "forecast_provenance": extra.get("forecast_provenance", {}),
            "measurement_option": extra.get("measurement_option", {}),
            "data_class": str(next(
                (raw.get("dataset_class", raw.get("data_class",
                    "synthetic" if raw.get("synthetic_fixture") is True else "unverified"))
                 for raw in candidates
                 if str(raw.get("candidate_observation_id", raw.get("id", ""))) == cid),
                "unverified",
            )),
            "purpose": extra.get("purpose"), "feasibility_evidence": raw_feasibility.get(cid, {})})
    verified, blocked = [], []
    for item in ranked:
        f = item.get("feasibility") or {}
        raw_f = item.get("feasibility_evidence") or {}
        evidence_digest = str(raw_f.get("evidence_sha256", "")).lower()
        digest_valid = (len(evidence_digest) == 64
                        and set(evidence_digest) <= set("0123456789abcdef"))
        query_parameters = raw_f.get("query_parameters")
        good = (f.get("status") == "verified" and f.get("feasible") is True
                and (f.get("attestation_verification") or {}).get("valid") is True
                and str(f.get("source_uri", "")).startswith("https://")
                and bool(f.get("checked_utc")) and bool(raw_f.get("calculator"))
                and bool(raw_f.get("query_id")) and digest_valid
                and isinstance(query_parameters, Mapping) and bool(query_parameters))
        if good:
            verified.append(item)
        else:
            blocked.append({"candidate_observation_id": item["candidate_observation_id"],
                "reason": "external feasibility evidence is absent, incomplete or unverified",
                "feasibility": f})
    return {
        "status": "ranked_with_verified_feasibility" if verified else "science_ranked_but_feasibility_unverified",
        "recommended": verified[0] if verified else None,
        "feasible_ranked": verified, "science_only_ranked": ranked,
        "blocked_or_unverified": blocked,
        "prior_sensitivity": base.get("prior_sensitivity", {}),
        "feasibility_policy": "A candidate is recommended only when the external record has a detached Ed25519 signature verified against the deployment's out-of-band pinned public key, plus an HTTPS source, timezone-aware check time, calculator, query ID, exact query parameters and evidence SHA-256. Without the pinned key, the record remains unverified.",
        "limitations": base["limitations"] + ["Forecasts must come from fitted physical models.", "The planner does not schedule or command a telescope."],
    }
