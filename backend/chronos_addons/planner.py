"""Expected-information-gain planning with explicit feasibility provenance."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence
import math

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
    source_uri = supplied.get("source_uri")
    if not isinstance(source_uri, str) or not source_uri.startswith("https://"):
        raise ValueError("verified feasibility requires an exact HTTPS source_uri")
    checked = _utc_timestamp(supplied.get("checked_utc"), "checked_utc")
    feasible = supplied.get("feasible")
    if not isinstance(feasible, bool):
        raise ValueError("verified feasibility requires a boolean feasible field")
    window_start = supplied.get("window_start_utc")
    window_end = supplied.get("window_end_utc")
    if (window_start is None) != (window_end is None):
        raise ValueError("feasibility window_start_utc and window_end_utc must be supplied together")
    normalized_window = None
    if window_start is not None:
        start = _utc_timestamp(window_start, "window_start_utc")
        end = _utc_timestamp(window_end, "window_end_utc")
        if end <= start:
            raise ValueError("feasibility window end must be later than its start")
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
            "Visibility and archive availability are not calculated here; they must come from the recorded external feasibility source.",
            "An unverified candidate can be information-ranked but is not asserted to be observable or available.",
            "Inputs must be physical forecasts, not guessed values.",
            "Prior sensitivity is evaluated only for the alternative prior sets supplied by the caller.",
            "This does not schedule or command a telescope.",
        ],
    }
