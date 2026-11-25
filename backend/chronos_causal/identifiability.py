"""Forward-model Jacobian and nuisance-parameter identifiability auditing."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence
import numpy as np


def finite_difference_jacobian(model: Callable[[np.ndarray], Any], parameters: Sequence[float], *,
                               relative_step: float = 1e-5) -> np.ndarray:
    """Central finite-difference Jacobian of a deterministic forward model."""
    theta = np.asarray(parameters, dtype=float).reshape(-1)
    if theta.size == 0 or np.any(~np.isfinite(theta)):
        raise ValueError("parameters must be a non-empty finite vector")
    if not np.isfinite(relative_step) or relative_step <= 0:
        raise ValueError("relative_step must be finite and positive")
    baseline = np.asarray(model(theta.copy()), dtype=float).reshape(-1)
    if baseline.size == 0 or np.any(~np.isfinite(baseline)):
        raise ValueError("forward model must return a non-empty finite vector")
    jacobian = np.empty((baseline.size, theta.size), dtype=float)
    for column in range(theta.size):
        step = relative_step * max(abs(float(theta[column])), 1.0)
        plus, minus = theta.copy(), theta.copy()
        plus[column] += step
        minus[column] -= step
        y_plus = np.asarray(model(plus), dtype=float).reshape(-1)
        y_minus = np.asarray(model(minus), dtype=float).reshape(-1)
        if y_plus.shape != baseline.shape or y_minus.shape != baseline.shape:
            raise ValueError("forward model output shape changed during finite differences")
        if np.any(~np.isfinite(y_plus)) or np.any(~np.isfinite(y_minus)):
            raise ValueError("forward model returned non-finite values during finite differences")
        jacobian[:, column] = (y_plus - y_minus) / (2.0 * step)
    return jacobian


def _whiten_jacobian(jacobian: np.ndarray, covariance: Any):
    n = jacobian.shape[0]
    if covariance is None:
        return jacobian.copy(), "identity covariance assumed", False
    cov = np.asarray(covariance, dtype=float)
    if cov.ndim == 1:
        if cov.size != n or np.any(~np.isfinite(cov)) or np.any(cov <= 0):
            raise ValueError("variance vector must be finite, positive and match measurement count")
        return jacobian / np.sqrt(cov)[:, None], "diagonal variance supplied", True
    if cov.shape != (n, n) or np.any(~np.isfinite(cov)):
        raise ValueError("measurement covariance must be a finite square matrix matching the Jacobian")
    try:
        lower = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as exc:
        raise ValueError("measurement covariance must be positive definite") from exc
    return np.linalg.solve(lower, jacobian), "full covariance supplied", True


def audit_forward_model_identifiability(jacobian, parameter_names: Sequence[str], *,
                                        covariance=None,
                                        parameter_roles: Mapping[str, str] | None = None,
                                        measurement_options: Sequence[Mapping[str, Any]] | None = None,
                                        weak_condition_number: float = 1e3,
                                        severe_condition_number: float = 1e6,
                                        near_collinearity: float = 0.98,
                                        covariance_verified: bool = False) -> dict[str, Any]:
    """Inspect a whitened forward-model Jacobian and proposed extra measurements."""
    j = np.asarray(jacobian, dtype=float)
    names = [str(name) for name in parameter_names]
    if j.ndim != 2 or j.shape[1] != len(names) or j.shape[0] < 1 or not names:
        raise ValueError("jacobian must be (measurements, parameters) and match parameter_names")
    if len(set(names)) != len(names) or any(not name for name in names):
        raise ValueError("parameter_names must be unique and non-empty")
    if np.any(~np.isfinite(j)):
        raise ValueError("jacobian must be finite")
    if weak_condition_number <= 1 or severe_condition_number <= weak_condition_number:
        raise ValueError("condition-number thresholds are invalid")
    if not 0 < near_collinearity < 1:
        raise ValueError("near_collinearity must be between zero and one")
    if covariance_verified and covariance is None:
        raise ValueError("covariance_verified cannot be true when no covariance was supplied")
    weighted, covariance_description, covariance_was_supplied = _whiten_jacobian(j, covariance)
    column_norms = np.linalg.norm(weighted, axis=0)
    zero_columns = [names[i] for i, value in enumerate(column_norms) if value <= np.finfo(float).tiny]
    scales = column_norms.copy()
    scales[scales <= np.finfo(float).tiny] = 1.0
    normalized = weighted / scales
    _, singular, vt = np.linalg.svd(normalized, full_matrices=True)
    tolerance = (
        np.finfo(float).eps * max(normalized.shape) * (singular[0] if singular.size else 1.0)
    )
    rank = int(np.sum(singular > tolerance))
    smallest = float(singular[-1]) if singular.size else 0.0
    condition = float(singular[0] / smallest) if smallest > tolerance else float("inf")
    fisher = weighted.T @ weighted
    parameter_covariance = np.linalg.pinv(fisher, rcond=1e-12)
    full_rank = rank == len(names)
    if full_rank:
        errors = np.sqrt(np.clip(np.diag(parameter_covariance), 0.0, None))
        denom = np.outer(errors, errors)
        correlations = np.divide(
            parameter_covariance, denom,
            out=np.zeros_like(parameter_covariance), where=denom > 0,
        )
        np.fill_diagonal(correlations, 1.0)
    else:
        errors = None
        correlations = None

    # Cosine similarity of whitened, unit-norm Jacobian columns directly
    # exposes local sensitivity degeneracy even when Fisher inversion fails.
    design_correlations = normalized.T @ normalized
    pairs = []
    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            value = float(design_correlations[left, right])
            if abs(value) >= 0.5:
                pairs.append({
                    "parameter_a": names[left],
                    "parameter_b": names[right],
                    "design_column_cosine": value,
                    "absolute_cosine": abs(value),
                    "near_collinear": abs(value) >= near_collinearity,
                })
    nuisance_pairs = []
    roles = dict(parameter_roles or {})
    for item in pairs:
        role_a = roles.get(item["parameter_a"], "unspecified")
        role_b = roles.get(item["parameter_b"], "unspecified")
        if role_a != role_b and ("nuisance" in role_a or "nuisance" in role_b or
                                 role_a in {"sky", "instrument"} and role_b in {"sky", "instrument"}):
            nuisance_pairs.append({**item, "role_a": role_a, "role_b": role_b})

    near_pairs = [item for item in pairs if item["near_collinear"]]
    if rank < len(names):
        status = "not_identifiable"
    elif near_pairs:
        status = "degenerate"
    elif condition >= severe_condition_number:
        status = "degenerate"
    elif condition >= weak_condition_number:
        status = "weakly_identifiable"
    else:
        status = "identifiable"

    null_vectors = []
    if rank < len(names):
        for vector in vt[rank:]:
            order = np.argsort(np.abs(vector))[::-1]
            null_vectors.append({
                "dominant_parameter_loadings": [
                    {"parameter": names[int(index)], "loading": float(vector[index])}
                    for index in order[:min(5, len(names))]
                ],
                "interpretation": "This parameter combination has no independently constrained direction in the local linearized model.",
            })

    recommendations = []
    option_results = []
    for option in measurement_options or []:
        label = str(option.get("name", "unnamed measurement"))
        extra = np.asarray(option.get("jacobian_rows"), dtype=float)
        noise = np.asarray(option.get("sigma", 1.0), dtype=float)
        if extra.ndim == 1:
            extra = extra.reshape(1, -1)
        if extra.ndim != 2 or extra.shape[1] != len(names) or extra.shape[0] < 1:
            raise ValueError(f"measurement option {label!r} jacobian_rows must have one column per parameter")
        if np.any(~np.isfinite(extra)) or np.any(~np.isfinite(noise)) or np.any(noise <= 0):
            raise ValueError(f"measurement option {label!r} has invalid derivatives or sigma")
        if noise.ndim == 0:
            noise = np.full(extra.shape[0], float(noise))
        if noise.shape != (extra.shape[0],):
            raise ValueError(f"measurement option {label!r} sigma must be scalar or one value per row")
        candidate = np.vstack([weighted, extra / noise[:, None]])
        candidate_scales = np.linalg.norm(candidate, axis=0)
        candidate_scales[candidate_scales <= np.finfo(float).tiny] = 1.0
        candidate_normalized = candidate / candidate_scales
        svals = np.linalg.svd(candidate_normalized, compute_uv=False)
        candidate_tol = np.finfo(float).eps * max(candidate_normalized.shape) * svals[0]
        candidate_rank = int(np.sum(svals > candidate_tol))
        candidate_condition = (
            float(svals[0] / svals[-1])
            if svals.size and svals[-1] > candidate_tol else float("inf")
        )
        improves = candidate_rank > rank or candidate_rank == rank and candidate_condition < condition
        option_results.append({
            "name": label,
            "rank_after_measurement": candidate_rank,
            "condition_number_after_measurement": candidate_condition,
            "improves_local_identifiability": bool(improves),
        })
        if improves:
            recommendations.append(label)
    if not recommendations and status != "identifiable":
        recommendations.append(
            "Add a measurement whose sky, detector, time and wavelength sensitivity differs from the existing design."
        )

    return {
        "status": status,
        "decision_status": "quantitative_covariance_unverified" if not covariance_verified else "covariance_verified_for_this_run",
        "n_measurements": int(j.shape[0]),
        "n_parameters": len(names),
        "parameter_names": names,
        "parameter_roles": roles,
        "rank": rank,
        "singular_values": singular.tolist(),
        "condition_number": condition,
        "zero_sensitivity_parameters": zero_columns,
        "parameter_standard_errors_local": (
            {name: float(errors[i]) for i, name in enumerate(names)}
            if full_rank else {name: None for name in names}
        ),
        "parameter_uncertainty_available": bool(full_rank),
        "parameter_correlations": correlations.tolist() if full_rank else None,
        "correlated_parameter_pairs": pairs,
        "sky_instrument_or_nuisance_degeneracies": nuisance_pairs,
        "null_space_directions": null_vectors,
        "covariance": {
            "description": covariance_description,
            "was_supplied": covariance_was_supplied,
            "verified_by_operator": bool(covariance_verified),
        },
        "additional_measurement_options": option_results,
        "recommended_additional_measurements": recommendations,
        "interpretation": (
            "Local Jacobian analysis only. It does not establish global identifiability or validate the forward model. "
            "Parameter standard errors and correlations are withheld when the Fisher matrix is rank deficient. "
            "A BIC difference remains a relative model score, not a posterior probability."
        ),
    }
