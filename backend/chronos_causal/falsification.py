"""Predeclared falsification challenges for the measurement-level Sky–Detector model."""
from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Sequence

import numpy as np

from .counterfactual import make_counterfactual
from .inference import investigate
from .posterior_predictive import (
    grouped_residual_checks,
    parametric_bootstrap_checks,
    transient_scan_bootstrap,
    transient_candidate_family_bootstrap,
)
from .schema import normalize_observations


def _groups(rows):
    times = np.asarray([row["mjd"] for row in rows], dtype=float)
    waves = np.asarray([row["wavelength_um"] for row in rows], dtype=float)
    flux = np.asarray([row["flux"] for row in rows], dtype=float)
    if flux.size >= 4:
        cuts = np.unique(np.quantile(flux, [0.0, 1 / 3, 2 / 3, 1.0]))
        brightness = np.digitize(flux, cuts[1:-1], right=True)
    else:
        brightness = np.zeros(flux.size, dtype=int)
    return {
        "epoch_mjd": [f"{value:.6f}" for value in times],
        "wavelength_um": [f"{value:.5f}" for value in waves],
        "detector_id": [str(row["detector_id"]) for row in rows],
        "source_brightness_bin": [str(int(value)) for value in brightness],
    }



def _residual_records(rows, prediction, sigma, groups):
    predicted = np.asarray(prediction, dtype=float)
    observed = np.asarray([row["flux"] for row in rows], dtype=float)
    errors = np.asarray(sigma, dtype=float)
    z = (observed - predicted) / errors
    brightness = groups["source_brightness_bin"]
    return [
        {
            "observation_id": str(row.get("observation_id", index)),
            "mjd": float(row["mjd"]),
            "wavelength_um": float(row["wavelength_um"]),
            "detector_id": str(row["detector_id"]),
            "observed_flux": float(observed[index]),
            "predicted_flux": float(predicted[index]),
            "sigma": float(errors[index]),
            "standardized_residual": float(z[index]),
            "source_brightness_bin": brightness[index],
        }
        for index, row in enumerate(rows)
    ]


def run_falsification_suite(observations: Sequence[Mapping[str, Any]], *,
                            challenge_specs: Sequence[Mapping[str, Any]] | None = None,
                            challenge_plan_sha256: str | None = None,
                            candidate_family: Sequence[Mapping[str, Any]] | None = None,
                            flux_covariance=None,
                            bootstrap_draws: int = 1000,
                            transient_draws: int = 500,
                            seed: int = 20261125,
                            maximum_predictive_p_value: float = 0.01,
                            min_relative_support: float = 0.65,
                            min_delta_bic: float = 6.0) -> dict[str, Any]:
    """Fit the same observations, inspect residual structure and run controls.

    Counterfactual interventions are measurement-level perturbations. They are
    challenge replays, not alternate raw-pixel reductions or physical claims.
    """
    rows = normalize_observations(observations)
    if not 0 < maximum_predictive_p_value < 1:
        raise ValueError("maximum_predictive_p_value must be between zero and one")
    if int(bootstrap_draws) < 100 or int(transient_draws) < 100:
        raise ValueError("bootstrap_draws and transient_draws must be at least 100")
    analysis = investigate(
        rows,
        min_relative_support=min_relative_support,
        min_delta_bic=min_delta_bic,
        flux_covariance=flux_covariance,
    )
    leading = analysis["leading_model"]
    model_rows = analysis["relative_model_support"]
    static = next((item for item in model_rows if item["name"] == "static_source"), None)
    best = next((item for item in model_rows if item["name"] == leading), model_rows[0])
    null_prediction = (
        static["flux_prediction"] if static is not None
        else best["flux_prediction"]
    )
    observed = [row["flux"] for row in rows]
    sigma = [row["sigma"] for row in rows]
    times = [row["mjd"] for row in rows]
    group_labels = _groups(rows)

    descriptive = grouped_residual_checks(
        observed, best["flux_prediction"], sigma, group_labels
    )
    residual_records = _residual_records(
        rows, best["flux_prediction"], sigma, group_labels
    )
    bootstrap = parametric_bootstrap_checks(
        observed, best["flux_prediction"], sigma,
        groups=group_labels, covariance=flux_covariance,
        draws=bootstrap_draws, seed=seed,
    )
    uncertainties_verified = all(
        row.get("uncertainty_status") in {"validated", "calibrated"}
        for row in rows
    )
    if uncertainties_verified:
        predictive_status = "evaluated_with_declared_uncertainties"
        p_values = [
            float(item["upper_tail_p_value"])
            for item in bootstrap["global_checks"].values()
        ]
        predictive_pass = all(value >= maximum_predictive_p_value for value in p_values)
    else:
        predictive_status = "exploratory_uncertainty_not_validated"
        predictive_pass = False
        p_values = [
            float(item["upper_tail_p_value"])
            for item in bootstrap["global_checks"].values()
        ]

    transient = transient_scan_bootstrap(
        observed, null_prediction, sigma, times,
        covariance=flux_covariance, draws=transient_draws, seed=seed + 1,
    )
    candidate_selection_correction = {
        "status": "not_required_for_non_transient_leading_model",
        "candidate_selection_adjusted": False,
        "family_wise_false_alarm_probability": None,
    }
    candidate_family_complete = False
    candidate_family_significant = False
    if candidate_family is not None:
        family_report = transient_candidate_family_bootstrap(
            candidate_family, draws=transient_draws, seed=seed + 2
        )
        current_candidate_id = analysis.get("candidate_id")
        included_ids = {str(item.get("candidate_id", "")) for item in candidate_family}
        candidate_family_complete = (
            current_candidate_id is not None and str(current_candidate_id) in included_ids
        )
        family_p = float(family_report["family_wise_false_alarm_probability"])
        candidate_family_significant = family_p <= maximum_predictive_p_value
        candidate_selection_correction = {
            **family_report,
            "current_candidate_in_supplied_family": candidate_family_complete,
            "significance_alpha": maximum_predictive_p_value,
            "family_wise_transient_claim_supported": (
                candidate_family_complete and candidate_family_significant
            ),
        }
    elif leading == "transient":
        candidate_selection_correction = {
            "status": "not_evaluated",
            "candidate_selection_adjusted": False,
            "family_wise_false_alarm_probability": None,
            "reason": "Complete searched candidate family was not supplied; post-hoc candidate selection has not been adjusted.",
        }
    plan = list(challenge_specs or [
        {"challenge_id": "sky_only", "intervention": "sky_variability", "amplitude": 1.0},
        {"challenge_id": "detector_only", "intervention": "detector_template", "amplitude": 1.0},
        {"challenge_id": "mixed", "intervention": "mixed", "amplitude": 1.0, "template_amplitude": 1.0},
    ])
    challenge_ids = [str(item.get("challenge_id", "")) for item in plan]
    if any(not value for value in challenge_ids) or len(set(challenge_ids)) != len(challenge_ids):
        raise ValueError("challenge specs need unique, non-empty challenge_id values")
    from chronos_benchmark.runner import canonical_json
    plan_digest = hashlib.sha256(canonical_json(plan)).hexdigest()
    plan_hash_matches = challenge_plan_sha256 == plan_digest if challenge_plan_sha256 else False

    challenges = []
    for item in plan:
        spec = dict(item)
        challenge_id = str(spec.pop("challenge_id"))
        intervention = str(spec.pop("intervention", ""))
        display_parameters = dict(spec)
        if intervention not in {"sky_variability", "detector_template", "mixed", "moving_source", "transient"}:
            raise ValueError(f"{challenge_id}: unsupported intervention {intervention!r}")
        altered = make_counterfactual(
            rows, intervention,
            amplitude=float(spec.pop("amplitude", 1.0)),
            template_amplitude=float(spec.pop("template_amplitude", 0.0)),
            motion_x_per_day=float(spec.pop("motion_x_per_day", 0.0)),
            motion_y_per_day=float(spec.pop("motion_y_per_day", 0.0)),
            added_noise_sigma=float(spec.pop("added_noise_sigma", 0.0)),
            event_start_mjd=spec.pop("event_start_mjd", None),
            event_end_mjd=spec.pop("event_end_mjd", None),
            seed=int(spec.pop("seed", seed)),
        )
        challenge_analysis = investigate(
            altered["observations"],
            min_relative_support=min_relative_support,
            min_delta_bic=min_delta_bic,
            flux_covariance=flux_covariance,
        )
        challenges.append({
            "challenge_id": challenge_id,
            "intervention": intervention,
            "parameters": display_parameters,
            "leading_model_after_intervention": challenge_analysis["leading_model"],
            "verdict_after_intervention": challenge_analysis["verdict"],
            "delta_bic_to_runner_up": challenge_analysis["delta_bic_to_runner_up"],
            "relative_model_support": challenge_analysis["relative_model_support"],
            "measurement_level_only": True,
            "original_observations_mutated": False,
        })

    transient_family_pass = (
        leading != "transient"
        or candidate_family_complete and candidate_family_significant
    )
    if analysis["verdict"] == "unknown" or not predictive_pass or not uncertainties_verified or not plan_hash_matches or not transient_family_pass:
        verdict = "unknown"
        decision_reasons = list(analysis["abstention_reasons"])
        if not uncertainties_verified:
            decision_reasons.append("supplied uncertainties are not marked validated or calibrated")
        if not predictive_pass:
            decision_reasons.append("predeclared predictive checks did not pass")
        if not plan_hash_matches:
            decision_reasons.append("challenge plan SHA-256 is missing or does not match the supplied plan")
        if not transient_family_pass:
            if candidate_family is None:
                decision_reasons.append("transient candidate-family selection correction was not run")
            elif not candidate_family_complete:
                decision_reasons.append("supplied candidate family does not include this candidate")
            else:
                decision_reasons.append("transient candidate family does not pass the predeclared family-wise false-alarm threshold")
        result_status = "model_not_established"
    else:
        verdict = "provisionally_survives_declared_checks"
        decision_reasons = []
        result_status = "provisional_only"

    return {
        "schema": "chronos-falsification-report/1.0",
        "candidate_id": analysis.get("candidate_id"),
        "verdict": verdict,
        "status": result_status,
        "leading_model": leading,
        "relative_model_support": analysis["relative_model_support"],
        "delta_bic_to_runner_up": analysis["delta_bic_to_runner_up"],
        "abstention_reasons": decision_reasons,
        "residual_checks": descriptive,
        "residual_records": residual_records,
        "parametric_bootstrap": {
            **bootstrap,
            "status": predictive_status,
            "uncertainties_marked_validated": uncertainties_verified,
            "acceptance_threshold": maximum_predictive_p_value,
            "all_global_checks_above_threshold": predictive_pass,
            "warning": (
                "Exploratory only because the supplied uncertainties are not marked validated or calibrated."
                if not uncertainties_verified else bootstrap["warning"]
            ),
        },
        "transient_search": transient,
        "candidate_selection_correction": candidate_selection_correction,
        "counterfactual_challenges": challenges,
        "challenge_plan": {
            "sha256": plan_digest,
            "provided_sha256_matches": plan_hash_matches,
            "external_timestamp_or_signature_verified": False,
            "predeclaration_verified": False,
            "note": (
                "The supplied hash confirms plan-content integrity only. It does not prove that the plan was registered before inspecting the data."
            ),
        },
        "evidence_to_preserve": {
            "failed_or_contradictory_checks": [
                name for name, item in bootstrap["global_checks"].items()
                if float(item["upper_tail_p_value"]) < maximum_predictive_p_value
            ],
            "all_challenge_results_preserved": True,
            "original_measurements_mutated": False,
            "observation_level_residuals_preserved": True,
            "conditional_predictive_intervals_preserved": True,
        },
        "interpretation": (
            "A surviving result is provisional and conditional on the declared measurements and noise model. "
            "The system returns unknown when uncertainty is unvalidated or predictive checks fail."
        ),
        "limitations": [
            "The current model comparison is measurement-level and uses relative BIC weights, not calibrated posterior probabilities.",
            "The parametric bootstrap is conditional on supplied point predictions; it is not a posterior predictive check with parameter uncertainty.",
            "Flux fits use a supplied full covariance matrix when present and require its diagonal to match sigma squared; coordinate fits remain independent per axis.",
            "The per-candidate transient scan corrects across searched intervals. A transient interpretation additionally requires a candidate-family maximum-statistic calibration across all supplied candidates.",
            "Candidate-family correction does not account for upstream image detection, field selection or candidates omitted from the declared searched family.",
            "The transient scan calibration assumes the supplied null prediction and Gaussian noise model.",
            "Counterfactual intervention replays alter measurement rows; they do not rerender raw FITS pixels or establish causal truth.",
            "Instrument and sky-coordinate evidence requires a validated detector-to-sky transformation.",
        ],
    }
