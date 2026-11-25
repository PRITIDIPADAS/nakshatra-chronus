"""Residual checks for a fitted measurement-level model."""
from __future__ import annotations
import numpy as np

def residual_checks(observed, predicted, sigma):
    y = np.asarray(observed, float).reshape(-1)
    mu = np.asarray(predicted, float).reshape(-1)
    s = np.asarray(sigma, float).reshape(-1)
    if y.size == 0 or y.size != mu.size or y.size != s.size or np.any(~np.isfinite(y)) or np.any(~np.isfinite(mu)) or np.any(~np.isfinite(s)) or np.any(s <= 0):
        raise ValueError("observed, predicted and positive sigma arrays must be finite and equal length")
    z = (y - mu) / s
    return {
        "n": int(z.size),
        "mean_standardized_residual": float(np.mean(z)),
        "rms_standardized_residual": float(np.sqrt(np.mean(z ** 2))),
        "maximum_absolute_standardized_residual": float(np.max(np.abs(z))),
        "fraction_beyond_3_sigma": float(np.mean(np.abs(z) > 3)),
        "standardized_residuals": z.tolist(),
        "warning": "Descriptive residual diagnostics only; this is not a calibrated posterior predictive p-value.",
    }


"""Residual diagnostics and parametric-bootstrap predictive challenges."""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import numpy as np


def _validate_vectors(observed, predicted, sigma):
    y = np.asarray(observed, float).reshape(-1)
    mu = np.asarray(predicted, float).reshape(-1)
    s = np.asarray(sigma, float).reshape(-1)
    if (y.size == 0 or y.size != mu.size or y.size != s.size
            or np.any(~np.isfinite(y)) or np.any(~np.isfinite(mu))
            or np.any(~np.isfinite(s)) or np.any(s <= 0)):
        raise ValueError("observed, predicted and positive sigma arrays must be finite and equal length")
    return y, mu, s


def residual_checks(observed, predicted, sigma):
    y, mu, s = _validate_vectors(observed, predicted, sigma)
    z = (y - mu) / s
    return {
        "n": int(z.size),
        "mean_standardized_residual": float(np.mean(z)),
        "rms_standardized_residual": float(np.sqrt(np.mean(z ** 2))),
        "maximum_absolute_standardized_residual": float(np.max(np.abs(z))),
        "fraction_beyond_3_sigma": float(np.mean(np.abs(z) > 3)),
        "standardized_residuals": z.tolist(),
        "warning": "Descriptive residual diagnostics only; this is not a calibrated posterior predictive p-value.",
    }


def grouped_residual_checks(observed, predicted, sigma, groups: Mapping[str, Sequence[Any]]):
    y, mu, s = _validate_vectors(observed, predicted, sigma)
    output = {}
    z = (y - mu) / s
    for dimension, labels in groups.items():
        values = np.asarray(labels, dtype=object).reshape(-1)
        if values.size != y.size:
            raise ValueError(f"group labels for {dimension!r} must match observation count")
        rows = {}
        for label in sorted({str(x) for x in values}):
            selected = np.asarray([str(x) == label for x in values])
            local = z[selected]
            rows[label] = {
                "n": int(local.size),
                "mean_standardized_residual": float(np.mean(local)),
                "rms_standardized_residual": float(np.sqrt(np.mean(local ** 2))),
                "maximum_absolute_standardized_residual": float(np.max(np.abs(local))),
                "fraction_beyond_3_sigma": float(np.mean(np.abs(local) > 3)),
            }
        output[str(dimension)] = rows
    return {"dimensions": output, "warning": "Group summaries are descriptive; small groups are noisy."}


def _statistics(residual):
    z = np.asarray(residual, dtype=float)
    return {
        "mean_z": float(np.mean(z)),
        "rms_z": float(np.sqrt(np.mean(z ** 2))),
        "max_abs_z": float(np.max(np.abs(z))),
        "fraction_gt_3sigma": float(np.mean(np.abs(z) > 3.0)),
    }


def _tail_probability(simulated, observed, *, two_sided=False):
    values = np.asarray(simulated, dtype=float)
    if two_sided:
        return float((1 + np.count_nonzero(np.abs(values) >= abs(observed))) / (values.size + 1))
    return float((1 + np.count_nonzero(values >= observed)) / (values.size + 1))


def parametric_bootstrap_checks(observed, predicted, sigma, *, groups=None,
                                covariance=None, draws: int = 1000,
                                seed: int = 1) -> dict[str, Any]:
    """Check residual statistics under a specified parametric noise model.

    This is a bootstrap conditional on supplied point predictions. It is not a
    posterior predictive distribution unless a posterior has separately been
    sampled and propagated.
    """
    y, mu, s = _validate_vectors(observed, predicted, sigma)
    if int(draws) < 100:
        raise ValueError("draws must be at least 100")
    rng = np.random.default_rng(int(seed))
    if covariance is None:
        lower = None
        covariance_label = "independent Gaussian errors using supplied sigma"
    else:
        cov = np.asarray(covariance, dtype=float)
        if cov.shape != (y.size, y.size) or np.any(~np.isfinite(cov)):
            raise ValueError("covariance must be finite and square with one row per measurement")
        if not np.allclose(cov, cov.T, rtol=1e-10, atol=1e-12):
            raise ValueError("covariance must be symmetric")
        if not np.allclose(np.diag(cov), s ** 2, rtol=1e-5, atol=1e-10):
            raise ValueError("covariance diagonal must agree with sigma squared")
        try:
            lower = np.linalg.cholesky(cov)
        except np.linalg.LinAlgError as exc:
            raise ValueError("covariance must be positive definite") from exc
        covariance_label = "full supplied covariance"
    observed_z = (y - mu) / s
    observed_stats = _statistics(observed_z)
    replicates = {name: [] for name in observed_stats}
    group_arrays = {
        key: np.asarray(value, dtype=object).reshape(-1)
        for key, value in (groups or {}).items()
    }
    for key, values in group_arrays.items():
        if values.size != y.size:
            raise ValueError(f"group labels for {key!r} must match observation count")
    observed_group_stats = {}
    for key, values in group_arrays.items():
        observed_group_stats[key] = {}
        for label in sorted({str(x) for x in values}):
            select = np.asarray([str(x) == label for x in values])
            observed_group_stats[key][label] = _statistics(observed_z[select])
    group_replicates = {
        key: {label: {metric: [] for metric in stats}
              for label, stats in labels.items()}
        for key, labels in observed_group_stats.items()
    }
    for _ in range(int(draws)):
        if lower is None:
            simulated = mu + rng.normal(0.0, s)
        else:
            simulated = mu + lower @ rng.normal(size=y.size)
        z = (simulated - mu) / s
        stats = _statistics(z)
        for name, value in stats.items():
            replicates[name].append(value)
        for key, values in group_arrays.items():
            for label in observed_group_stats[key]:
                select = np.asarray([str(x) == label for x in values])
                group_stats = _statistics(z[select])
                for metric, value in group_stats.items():
                    group_replicates[key][label][metric].append(value)
    summaries = {}
    for name, observed_value in observed_stats.items():
        values = replicates[name]
        summaries[name] = {
            "observed": observed_value,
            "null_median": float(np.median(values)),
            "null_95_interval": [
                float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))
            ],
            "upper_tail_p_value": _tail_probability(values, observed_value, two_sided=(name == "mean_z")),
        }
    group_summaries = {}
    for key, labels in observed_group_stats.items():
        group_summaries[key] = {}
        for label, stats in labels.items():
            group_summaries[key][label] = {}
            for metric, observed_value in stats.items():
                values = group_replicates[key][label][metric]
                group_summaries[key][label][metric] = {
                    "observed": observed_value,
                    "null_95_interval": [
                        float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))
                    ],
                    "upper_tail_p_value": _tail_probability(values, observed_value, two_sided=(metric == "mean_z")),
                }
    return {
        "method": "parametric bootstrap conditional on supplied predictions",
        "draws": int(draws),
        "seed": int(seed),
        "noise_assumption": covariance_label,
        "observed_statistics": observed_stats,
        "global_checks": summaries,
        "group_checks": group_summaries,
        "warning": "These are not posterior probabilities or Bayesian posterior-predictive p-values. Validate the variance/covariance model and account for fitted-parameter uncertainty before confirmatory interpretation.",
    }


def _weighted_chi2(values, sigma, design, covariance=None):
    if covariance is None:
        root = 1.0 / sigma
        xw = design * root[:, None]
        yw = values * root
    else:
        lower = np.linalg.cholesky(covariance)
        xw = np.linalg.solve(lower, design)
        yw = np.linalg.solve(lower, values)
    beta, _, rank, _ = np.linalg.lstsq(xw, yw, rcond=None)
    if rank < design.shape[1]:
        return None, None
    prediction = design @ beta
    residual = values - prediction
    if covariance is None:
        residual = residual / sigma
    else:
        residual = np.linalg.solve(lower, residual)
    return float(residual @ residual), prediction


def _transient_scan_statistic(values, sigma, times, covariance=None):
    unique = np.unique(times)
    if unique.size < 4:
        return None, 0
    base_design = np.ones((values.size, 1))
    base_chi2, baseline_prediction = _weighted_chi2(values, sigma, base_design, covariance=covariance)
    if base_chi2 is None:
        return None, 0
    best = 0.0
    trials = 0
    for start in range(unique.size):
        for stop in range(start, unique.size):
            event = (times >= unique[start]) & (times <= unique[stop])
            if int(np.count_nonzero(~event)) < 2 or not np.any(event):
                continue
            design = np.column_stack([np.ones(values.size), event.astype(float)])
            chi2, _ = _weighted_chi2(values, sigma, design, covariance=covariance)
            if chi2 is None:
                continue
            trials += 1
            best = max(best, base_chi2 - chi2)
    return best, trials


def transient_scan_bootstrap(observed, null_prediction, sigma, times, *,
                             covariance=None, draws: int = 1000, seed: int = 1) -> dict[str, Any]:
    """Family-wise null calibration for the full scanned transient-window search."""
    y, mu, s = _validate_vectors(observed, null_prediction, sigma)
    t = np.asarray(times, dtype=float).reshape(-1)
    if t.size != y.size or np.any(~np.isfinite(t)):
        raise ValueError("times must be finite and match the observation count")
    if np.unique(t).size < 4:
        return {"status": "not_testable", "reason": "at least four distinct epochs are required"}
    if int(draws) < 100:
        raise ValueError("draws must be at least 100")
    lower = None
    if covariance is not None:
        cov = np.asarray(covariance, dtype=float)
        if cov.shape != (y.size, y.size) or np.any(~np.isfinite(cov)):
            raise ValueError("covariance must be finite and square with one row per measurement")
        if not np.allclose(cov, cov.T, rtol=1e-10, atol=1e-12):
            raise ValueError("covariance must be symmetric")
        if not np.allclose(np.diag(cov), s ** 2, rtol=1e-5, atol=1e-10):
            raise ValueError("covariance diagonal must agree with sigma squared")
        try:
            lower = np.linalg.cholesky(cov)
        except np.linalg.LinAlgError as exc:
            raise ValueError("covariance must be positive definite") from exc
    observed_stat, trials = _transient_scan_statistic(y, s, t, covariance=covariance)
    if observed_stat is None:
        return {"status": "not_testable", "reason": "transient scan is rank deficient"}
    rng = np.random.default_rng(int(seed))
    null_stats = []
    for _ in range(int(draws)):
        noise = rng.normal(0.0, s) if lower is None else lower @ rng.normal(size=y.size)
        sample = mu + noise
        value, _ = _transient_scan_statistic(sample, s, t, covariance=covariance)
        null_stats.append(float(value or 0.0))
    p_value = _tail_probability(null_stats, observed_stat)
    return {
        "status": "evaluated",
        "observed_max_delta_chi2": float(observed_stat),
        "searched_interval_count": int(trials),
        "bootstrap_draws": int(draws),
        "seed": int(seed),
        "noise_model": "independent Gaussian errors" if covariance is None else "full supplied covariance",
        "family_wise_false_alarm_probability": p_value,
        "null_95_interval": [
            float(np.percentile(null_stats, 2.5)), float(np.percentile(null_stats, 97.5))
        ],
        "interpretation": "Empirical family-wise null calibration for the complete interval scan under the supplied Gaussian null model.",
        "warning": "The null model, uncertainty values and event-search definition must be frozen before evaluation.",
    }
