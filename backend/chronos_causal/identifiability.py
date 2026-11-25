"""Audit whether the available measurements can separate proposed effects."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import numpy as np
from .schema import normalize_observations

def audit_identifiability(observations: Sequence[Mapping[str, Any]], *,
                          weak_condition_number: float = 1e3,
                          severe_condition_number: float = 1e6,
                          near_collinearity: float = 0.98) -> dict[str, Any]:
    rows = normalize_observations(observations)
    if weak_condition_number <= 1 or severe_condition_number <= weak_condition_number:
        raise ValueError("condition-number thresholds are invalid")
    if not 0 < near_collinearity < 1:
        raise ValueError("near_collinearity must be between zero and one")
    times = np.asarray([r["mjd"] for r in rows], dtype=float)
    waves = np.asarray([r["wavelength_um"] for r in rows], dtype=float)
    epochs = np.unique(times)
    unique_waves = np.unique(np.round(waves, 8))
    span_t = float(np.ptp(times))
    span_w = float(np.ptp(waves))
    dt = (times - np.mean(times)) / max(span_t, 1.0)
    dw = (waves - np.mean(waves)) / max(span_w, 1e-8)
    columns = [np.ones(len(rows)), dt, dw, dt * dw]
    names = ["constant", "time", "wavelength", "time_x_wavelength"]
    scores = [r.get("template_score") for r in rows]
    template_available = all(v is not None for v in scores)
    if template_available:
        template = np.asarray(scores, dtype=float)
        if np.ptp(template) > 1e-10:
            columns.append(template - np.mean(template))
            names.append("detector_template")
    design = np.column_stack(columns)
    scales = np.linalg.norm(design, axis=0)
    scales[scales == 0] = 1.0
    normalized = design / scales
    singular = np.linalg.svd(normalized, compute_uv=False)
    tolerance = np.finfo(float).eps * max(normalized.shape) * (singular[0] if singular.size else 1.0)
    rank = int(np.sum(singular > tolerance))
    condition = float(singular[0] / singular[-1]) if singular.size and singular[-1] > 0 else float("inf")
    correlations = {}
    if template_available and "detector_template" in names:
        template_column = normalized[:, names.index("detector_template")]
        for name in ("time", "wavelength", "time_x_wavelength"):
            col = normalized[:, names.index(name)]
            if np.std(col) > 0 and np.std(template_column) > 0:
                corr = float(np.corrcoef(col, template_column)[0, 1])
                correlations[name] = corr
    reasons = []
    recommendations = []
    if len(epochs) < 3:
        reasons.append("Fewer than three distinct epochs are available.")
        recommendations.append("Obtain at least one additional independent epoch.")
    if len(unique_waves) < 2:
        reasons.append("Only one distinct wavelength is sampled.")
        recommendations.append("Obtain a measurement at a different calibrated wavelength.")
    if not template_available:
        reasons.append("No detector-template score is supplied.")
        recommendations.append("Use a detector-matched calibration template before testing detector coupling.")
    if rank < len(names):
        reasons.append(f"The design matrix is rank deficient ({rank} of {len(names)} independent columns).")
        recommendations.append("Add observations that vary time, wavelength and detector coverage independently.")
    if any(abs(v) >= near_collinearity for v in correlations.values()):
        highly = [key for key, value in correlations.items() if abs(value) >= near_collinearity]
        reasons.append("Detector-template values are strongly correlated with " + ", ".join(highly) + ".")
        recommendations.append("Seek simultaneous partner-array measurements or a later visit with different detector coverage.")
    if len(rows) < 3 * len(names):
        reasons.append("The observation count is low relative to the number of fitted effects.")
        recommendations.append("Increase the number of independent measurements before fitting the full model.")
    if condition >= severe_condition_number or rank < len(names):
        status = "not_identifiable"
    elif condition >= weak_condition_number or reasons:
        status = "weakly_identifiable"
    else:
        status = "identifiable"
    if status == "identifiable":
        reasons = []
        recommendations = ["Proceed to model comparison, then verify the result with posterior-predictive and held-out tests."]
    return {
        "status": status,
        "rank": rank,
        "design_columns": names,
        "singular_values": singular.tolist(),
        "condition_number": condition,
        "epochs": int(len(epochs)),
        "wavelengths": int(len(unique_waves)),
        "detector_template_available": template_available,
        "template_correlations": correlations,
        "reasons": reasons,
        "recommended_additional_measurements": list(dict.fromkeys(recommendations)),
        "interpretation": (
            "This is a design-matrix identifiability screen, not a proof that the full physical parameters are identifiable. "
            "A full audit must include the calibrated forward-model Jacobian, nuisance parameters and covariance."
        ),
    }
