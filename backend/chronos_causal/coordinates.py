"""Sky- and detector-coordinate persistence diagnostics."""
from __future__ import annotations
import numpy as np
from .noise_model import fit_gaussian_linear, bic

def _fit_xy(rows, prefix: str, moving: bool):
    time = np.asarray([r["mjd"] for r in rows], float)
    time_scale = max(float(np.ptp(time)), 1.0)
    dt = (time - float(np.mean(time))) / time_scale
    design = np.column_stack([np.ones(len(rows)), dt]) if moving else np.ones((len(rows), 1))
    outputs = []
    total_ll = 0.0
    total_k = 0
    total_chi2 = 0.0
    for axis in ("x", "y"):
        values = [r[f"{prefix}_{axis}"] for r in rows]
        sigma = [r[f"{prefix}_sigma"] for r in rows]
        fit = fit_gaussian_linear(values, sigma, design)
        outputs.append(fit)
        total_ll += fit["log_likelihood"]
        total_k += fit["k"]
        total_chi2 += fit["chi2"]
    return {
        "log_likelihood": total_ll,
        "parameters": total_k,
        "bic": bic(total_ll, 2 * len(rows), total_k),
        "chi2": total_chi2,
        "dof": sum(x["dof"] for x in outputs),
        "reduced_chi2": total_chi2 / max(sum(x["dof"] for x in outputs), 1),
        "x_coefficients": outputs[0]["coefficients"],
        "y_coefficients": outputs[1]["coefficients"],
        "time_center_mjd": float(np.mean(time)),
        "time_scale_days": time_scale,
        "model": "linear-in-time" if moving else "fixed-coordinate",
    }

def coordinate_diagnostics(rows):
    sky_fixed = _fit_xy(rows, "sky", False)
    sky_moving = _fit_xy(rows, "sky", True) if len(rows) >= 4 and np.unique([r["mjd"] for r in rows]).size >= 3 else None
    detector_fixed = _fit_xy(rows, "detector", False)
    return {
        "sky_fixed": sky_fixed,
        "sky_linear_motion": sky_moving,
        "detector_fixed": detector_fixed,
        "sky_motion_delta_bic": None if sky_moving is None else sky_fixed["bic"] - sky_moving["bic"],
        "interpretation": (
            "Coordinate residuals are diagnostic evidence only. Detector-to-sky transforms, pointing history and calibration "
            "must be verified before treating persistence as a causal identification."
        ),
    }
