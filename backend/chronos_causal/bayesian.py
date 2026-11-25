"""Exact conjugate Bayesian inference for linear-Gaussian measurement models.

The posterior and marginal likelihood here are exact only for the stated model:
a linear design matrix, known positive-definite observation covariance, and
proper multivariate-Gaussian coefficient priors. They are not a replacement
for a posterior sampler over the complete CHRONOS detector/coordinate model.
"""
from __future__ import annotations

from typing import Any, Mapping
import math
import numpy as np


def _spd(matrix: Any, name: str, size: int) -> tuple[np.ndarray, np.ndarray, float]:
    value = np.asarray(matrix, dtype=float)
    if value.shape != (size, size) or np.any(~np.isfinite(value)):
        raise ValueError(f"{name} must be a finite {size}x{size} matrix")
    if not np.allclose(value, value.T, rtol=1e-10, atol=1e-12):
        raise ValueError(f"{name} must be symmetric")
    try:
        lower = np.linalg.cholesky(value)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{name} must be positive definite") from exc
    logdet = float(2.0 * np.sum(np.log(np.diag(lower))))
    return value, lower, logdet


def _inputs(observed, design_matrix, covariance, prior_mean, prior_covariance):
    y = np.asarray(observed, dtype=float).reshape(-1)
    x = np.asarray(design_matrix, dtype=float)
    if y.size < 2 or x.ndim != 2 or x.shape[0] != y.size or x.shape[1] < 1:
        raise ValueError("observed and design_matrix have incompatible or insufficient dimensions")
    if np.any(~np.isfinite(y)) or np.any(~np.isfinite(x)) or y.size <= x.shape[1]:
        raise ValueError("observations/design must be finite and observations must exceed coefficient count")
    c, lc, logdet_c = _spd(covariance, "measurement covariance", y.size)
    m0 = np.asarray(prior_mean, dtype=float).reshape(-1)
    if m0.size != x.shape[1] or np.any(~np.isfinite(m0)):
        raise ValueError("prior_mean must be finite and match the design columns")
    s0, ls0, logdet_s0 = _spd(prior_covariance, "prior covariance", x.shape[1])
    return y, x, c, lc, logdet_c, m0, s0, ls0, logdet_s0


def _posterior(y, x, lc, m0, ls0):
    whitened_x = np.linalg.solve(lc, x)
    whitened_y = np.linalg.solve(lc, y)
    prior_precision = np.linalg.solve(ls0.T, np.linalg.solve(ls0, np.eye(m0.size)))
    precision = prior_precision + whitened_x.T @ whitened_x
    try:
        lp = np.linalg.cholesky(precision)
    except np.linalg.LinAlgError as exc:
        raise ValueError("posterior precision is not positive definite") from exc
    covariance = np.linalg.solve(lp.T, np.linalg.solve(lp, np.eye(m0.size)))
    rhs = prior_precision @ m0 + whitened_x.T @ whitened_y
    mean = covariance @ rhs
    return mean, covariance, lp


def _log_marginal_likelihood(y, x, c, lc, logdet_c, m0, s0, logdet_s0):
    # Integrate beta analytically: y ~ N(X m0, C + X S0 X^T).
    marginal_cov = c + x @ s0 @ x.T
    _, lm, logdet_m = _spd(marginal_cov, "marginal covariance", y.size)
    residual = y - x @ m0
    whitened = np.linalg.solve(lm, residual)
    log_evidence = -0.5 * (
        y.size * math.log(2.0 * math.pi) + logdet_m + float(whitened @ whitened)
    )
    return float(log_evidence)


def gaussian_linear_posterior_predictive(
    observed,
    design_matrix,
    covariance,
    prior_mean,
    prior_covariance,
    *,
    draws: int = 4000,
    seed: int = 1,
) -> dict[str, Any]:
    """Sample the exact Gaussian coefficient posterior and its posterior predictive.

    The supplied covariance is treated as known, and coefficient priors are
    proper multivariate Gaussians. For each posterior parameter draw, a
    replicated data vector is drawn from N(X beta, C). Posterior-predictive
    tail areas are reported for the global whitened residual chi-square and
    maximum absolute whitened residual. These are Bayesian posterior-
    predictive checks for this conditional linear-Gaussian model, not for
    unmodelled detector physics or the full CHRONOS hypothesis family.
    """
    if int(draws) < 500:
        raise ValueError("draws must be at least 500 for a posterior-predictive run")
    y, x, c, lc, logdet_c, m0, s0, ls0, logdet_s0 = _inputs(
        observed, design_matrix, covariance, prior_mean, prior_covariance
    )
    mean, post_cov, _ = _posterior(y, x, lc, m0, ls0)
    log_evidence = _log_marginal_likelihood(y, x, c, lc, logdet_c, m0, s0, logdet_s0)
    rng = np.random.default_rng(int(seed))
    beta_draws = rng.multivariate_normal(mean, post_cov, size=int(draws))
    noise = rng.standard_normal((int(draws), y.size)) @ lc.T
    posterior_mean_prediction = x @ mean
    replicated = beta_draws @ x.T + noise

    observed_chi2 = np.empty(int(draws), dtype=float)
    replicated_chi2 = np.empty(int(draws), dtype=float)
    observed_max = np.empty(int(draws), dtype=float)
    replicated_max = np.empty(int(draws), dtype=float)
    for index, beta in enumerate(beta_draws):
        observed_z = np.linalg.solve(lc, y - x @ beta)
        replicated_z = np.linalg.solve(lc, replicated[index] - x @ beta)
        observed_chi2[index] = observed_z @ observed_z
        replicated_chi2[index] = replicated_z @ replicated_z
        observed_max[index] = np.max(np.abs(observed_z))
        replicated_max[index] = np.max(np.abs(replicated_z))

    lower = np.percentile(replicated, 2.5, axis=0)
    upper = np.percentile(replicated, 97.5, axis=0)
    posterior_predictive = {
        "draws": int(draws),
        "seed": int(seed),
        "replicated_observation_count": int(y.size),
        "pointwise_95_percent_interval": [
            {"lower": float(a), "upper": float(b)}
            for a, b in zip(lower, upper)
        ],
        "global_whitened_residual_chi_square": {
            "posterior_predictive_p_value": float(
                (1 + np.count_nonzero(replicated_chi2 >= observed_chi2))
                / (int(draws) + 1)
            ),
            "observed_statistic_posterior_median": float(np.median(observed_chi2)),
            "replicated_statistic_median": float(np.median(replicated_chi2)),
        },
        "maximum_absolute_whitened_residual": {
            "posterior_predictive_p_value": float(
                (1 + np.count_nonzero(replicated_max >= observed_max))
                / (int(draws) + 1)
            ),
            "observed_statistic_posterior_median": float(np.median(observed_max)),
            "replicated_statistic_median": float(np.median(replicated_max)),
        },
        "replicated_values": replicated.tolist(),
        "interpretation": (
            "Posterior-predictive checks conditional on the stated linear design, "
            "known covariance and proper Gaussian coefficient prior."
        ),
        "limitations": [
            "Measurement covariance is treated as known, not inferred.",
            "The coefficient prior and design matrix must be scientifically justified and frozen before holdout inspection.",
            "This does not integrate uncertainty in SPHEREx calibration products, detector response, source selection or coordinate models unless those are explicitly included in the design and prior.",
            "Posterior-predictive p-values are discrepancy checks, not probabilities that a hypothesis is true.",
        ],
    }
    return {
        "schema": "chronos-gaussian-linear-bayes/1.0",
        "model": "linear_gaussian_known_covariance",
        "prior": {"family": "multivariate_normal", "mean": m0.tolist(),
                  "covariance": s0.tolist(), "is_proper": True},
        "posterior": {
            "family": "multivariate_normal",
            "mean": mean.tolist(),
            "covariance": post_cov.tolist(),
            "coefficient_names": [f"beta_{i}" for i in range(x.shape[1])],
        },
        "log_marginal_likelihood": log_evidence,
        "posterior_mean_prediction": posterior_mean_prediction.tolist(),
        "posterior_predictive": posterior_predictive,
        "measurement_covariance": c.tolist(),
        "scientific_scope": "conditional linear-Gaussian measurement model only",
    }


def bayesian_linear_model_comparison(
    observed,
    covariance,
    models: Mapping[str, Any],
    coefficient_priors: Mapping[str, Mapping[str, Any]],
    model_priors: Mapping[str, float],
) -> dict[str, Any]:
    """Compute posterior model probabilities from proper marginal likelihoods.

    This uses exact Gaussian marginal likelihoods, not BIC. Every model must
    have an explicit proper Gaussian coefficient prior and a positive model
    prior. Model probabilities are conditional on this finite model set and
    these prior choices.
    """
    names = list(models)
    if len(names) < 2 or set(names) != set(coefficient_priors) or set(names) != set(model_priors):
        raise ValueError("models, coefficient_priors and model_priors must contain the same >=2 model names")
    prior_weights = np.asarray([float(model_priors[name]) for name in names], dtype=float)
    if np.any(~np.isfinite(prior_weights)) or np.any(prior_weights <= 0):
        raise ValueError("all model priors must be finite and positive")
    prior_weights /= prior_weights.sum()
    log_weights = []
    reports = []
    y = np.asarray(observed, dtype=float).reshape(-1)
    for name in names:
        spec = coefficient_priors[name]
        design = np.asarray(models[name], dtype=float)
        yv, xv, cv, lc, logdet_c, m0, s0, ls0, logdet_s0 = _inputs(
            y, design, covariance, spec["mean"], spec["covariance"]
        )
        log_evidence = _log_marginal_likelihood(
            yv, xv, cv, lc, logdet_c, m0, s0, logdet_s0
        )
        log_weight = math.log(float(prior_weights[names.index(name)])) + log_evidence
        log_weights.append(log_weight)
        reports.append({
            "model": name,
            "log_marginal_likelihood": log_evidence,
            "prior_model_probability": float(prior_weights[names.index(name)]),
        })
    log_weights = np.asarray(log_weights, dtype=float)
    shifted = np.exp(log_weights - float(np.max(log_weights)))
    posterior_probabilities = shifted / shifted.sum()
    for row, probability in zip(reports, posterior_probabilities):
        row["posterior_model_probability"] = float(probability)
    return {
        "schema": "chronos-bayesian-model-comparison/1.0",
        "method": "exact_gaussian_marginal_likelihood",
        "models": reports,
        "model_set_conditional": True,
        "interpretation": (
            "Posterior model probabilities use explicit model priors and exact "
            "marginal likelihoods under proper Gaussian coefficient priors. "
            "They are not BIC scores or BIC-derived probabilities."
        ),
        "limitations": [
            "Probabilities are conditional on the supplied finite model set and prior distributions.",
            "The known measurement covariance is treated as fixed.",
            "Omitted hypotheses, prior sensitivity and model misspecification remain possible.",
        ],
    }
