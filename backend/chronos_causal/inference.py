"""Competing measurement-level explanations for an astronomical candidate.

Normalized BIC weights are relative model support under the stated Gaussian
likelihoods. They are not calibrated posterior probabilities.
"""
from __future__ import annotations
import math
import numpy as np
from .schema import normalize_observations
from .noise_model import fit_gaussian_linear, bic
from .coordinates import coordinate_diagnostics

def _transient_fit(rows):
    times = np.asarray([r["mjd"] for r in rows], dtype=float)
    unique = np.unique(times)
    if unique.size < 4:
        raise ValueError("transient search requires at least four distinct epochs")
    flux = np.asarray([r["flux"] for r in rows], dtype=float)
    sigma = np.asarray([r["sigma"] for r in rows], dtype=float)
    best = None
    trials = 0
    for start in range(unique.size):
        for stop in range(start, unique.size):
            event = (times >= unique[start]) & (times <= unique[stop])
            n_event = int(event.sum())
            n_base = int((~event).sum())
            if n_event < 1 or n_base < 2:
                continue
            design = np.column_stack([np.ones(times.size), event.astype(float)])
            try:
                fit = fit_gaussian_linear(flux, sigma, design)
            except ValueError:
                continue
            trials += 1
            if best is None or fit["log_likelihood"] > best["fit"]["log_likelihood"]:
                best = {
                    "fit": fit,
                    "start_mjd": float(unique[start]),
                    "end_mjd": float(unique[stop]),
                    "n_event": n_event,
                    "n_baseline": n_base,
                }
    if best is None:
        raise ValueError("no transient interval has enough baseline measurements")
    search_penalty = 2.0 * math.log(max(trials, 1))
    best["search_trials"] = trials
    best["search_penalty"] = search_penalty
    return best

def _designs(rows):
    t = np.asarray([r["mjd"] for r in rows], float)
    w = np.asarray([r["wavelength_um"] for r in rows], float)
    dt = (t - np.mean(t)) / max(float(np.ptp(t)), 1.0)
    dw = (w - np.mean(w)) / max(float(np.ptp(w)), 1e-8)
    template_values = [r.get("template_score") for r in rows]
    has_template = all(v is not None for v in template_values) and np.ptp(np.asarray(template_values, float)) > 1e-8
    template = np.asarray(template_values, float) if has_template else None
    designs = {
        "static_source": (np.ones((len(rows), 1)), "sky", "Stable flux and fixed sky position."),
        "achromatic_variable": (np.column_stack([np.ones(len(rows)), dt]), "sky", "Flux changes with time without a wavelength trend."),
        "chromatic_variable": (np.column_stack([np.ones(len(rows)), dt, dw, dt * dw]), "sky", "Flux evolution depends on time and sampled wavelength."),
        "moving_source": (np.ones((len(rows), 1)), "moving_sky", "A linear sky-position track with approximately constant measured flux."),
        "transient": (None, "sky", "A temporary flux change over a searched time interval."),
    }
    if template is not None:
        designs["instrumental_artifact"] = (np.column_stack([np.ones(len(rows)), template]), "detector", "Flux covaries with a supplied detector-template score and detector position is tested for persistence.")
        designs["mixed_sky_detector"] = (np.column_stack([np.ones(len(rows)), dt, template]), "sky", "A time-varying sky signal and a detector-template contribution coexist.")
    return designs, has_template

def investigate(observations, *, min_relative_support: float = 0.65, min_delta_bic: float = 6.0):
    rows = normalize_observations(observations)
    if not 0 < min_relative_support <= 1 or min_delta_bic < 0:
        raise ValueError("invalid abstention thresholds")
    times = np.asarray([r["mjd"] for r in rows], float)
    if np.unique(times).size < 2:
        raise ValueError("at least two distinct observation times are required")
    flux = np.asarray([r["flux"] for r in rows], float)
    sigma = np.asarray([r["sigma"] for r in rows], float)
    designs, has_template = _designs(rows)
    coordinates = coordinate_diagnostics(rows)
    models, rejected = [], []
    for name, (design, position_kind, description) in designs.items():
        try:
            transient = None
            if name == "transient":
                transient = _transient_fit(rows)
                flux_fit = transient["fit"]
                search_penalty = transient["search_penalty"]
            else:
                flux_fit = fit_gaussian_linear(flux, sigma, design)
                search_penalty = 0.0
            if position_kind == "moving_sky":
                pos = coordinates["sky_linear_motion"]
                if pos is None:
                    raise ValueError("at least three distinct epochs are required for a moving-position fit")
                pos_ll, pos_k = pos["log_likelihood"], pos["parameters"]
            elif position_kind == "detector":
                pos = coordinates["detector_fixed"]
                pos_ll, pos_k = pos["log_likelihood"], pos["parameters"]
            else:
                pos = coordinates["sky_fixed"]
                pos_ll, pos_k = pos["log_likelihood"], pos["parameters"]
            total_ll = flux_fit["log_likelihood"] + pos_ll
            total_k = flux_fit["k"] + pos_k
            total_n = 3 * len(rows)
            score = bic(total_ll, total_n, total_k) + search_penalty
            item = {
                "name": name, "description": description, "bic": score,
                "delta_bic": None, "log_likelihood": total_ll,
                "parameters": total_k, "flux_parameters": flux_fit["k"],
                "flux_chi2": flux_fit["chi2"], "flux_dof": flux_fit["dof"],
                "flux_prediction": flux_fit["prediction"],
                "flux_standardized_residual": flux_fit["standardized_residual"],
                "coordinate_model": pos["model"],
            }
            if transient is not None:
                item["transient_interval_mjd"] = [transient["start_mjd"], transient["end_mjd"]]
                item["transient_search_trials"] = transient["search_trials"]
                item["transient_search_penalty"] = transient["search_penalty"]
            models.append(item)
        except ValueError as exc:
            rejected.append({"model": name, "reason": str(exc)})
    if not models:
        raise ValueError("no hypothesis could be fit; inspect time, wavelength and uncertainty coverage")
    models.sort(key=lambda x: x["bic"])
    best_bic = models[0]["bic"]
    raw = np.asarray([math.exp(-0.5 * min(1400.0, m["bic"] - best_bic)) for m in models], float)
    weights = raw / raw.sum()
    for model, weight in zip(models, weights.tolist()):
        model["delta_bic"] = float(model["bic"] - best_bic)
        model["relative_support"] = weight
    gap = models[1]["bic"] - models[0]["bic"] if len(models) > 1 else 0.0
    best = models[0]
    reasons = []
    if len(rows) < 4:
        reasons.append("fewer than four valid observations")
    if float(np.ptp(times)) <= 0:
        reasons.append("no time baseline")
    if best["relative_support"] < min_relative_support:
        reasons.append("leading model has insufficient relative support")
    if gap < min_delta_bic:
        reasons.append("leading model is not separated from the next model by the configured BIC margin")
    if best["name"] == "chromatic_variable" and np.unique([round(r["wavelength_um"], 8) for r in rows]).size < 3:
        reasons.append("insufficient distinct wavelength samples")
    verdict = "unknown" if reasons else best["name"]
    return {
        "candidate_id": rows[0].get("candidate_id"),
        "verdict": verdict,
        "leading_model": best["name"],
        "relative_model_support": models,
        "delta_bic_to_runner_up": float(gap),
        "abstention_reasons": reasons,
        "coordinate_diagnostics": coordinates,
        "coverage": {
            "n_observations": len(rows),
            "n_epochs": int(np.unique(times).size),
            "time_span_days": float(np.ptp(times)),
            "n_wavelengths": int(np.unique([round(r["wavelength_um"], 8) for r in rows]).size),
            "n_detectors": int(len({r["detector_id"] for r in rows})),
            "template_score_available": has_template,
        },
        "interpretation_note": "Relative BIC weights are comparative model scores, not calibrated probabilities or proof of causation.",
        "limitations": [
            "This is a measurement-level model, not a pixel-level SPHEREx forward model.",
            "The transient search penalty approximates the interval search cost; it is not a substitute for independent calibration.",
            "Astrometric coordinate diagnostics do not replace a validated per-exposure detector-to-sky transform.",
            "The Gaussian likelihood assumes supplied uncertainties are meaningful and independent; covariance is not modelled.",
            "Wavelength and time sampling can be confounded. A chromatic model is not identifiable when the design matrix is rank deficient.",
            "No claim of real-data performance is made until blind, field-held-out tests are run on calibrated archive observations.",
        ],
        "rejected_models": rejected,
    }
