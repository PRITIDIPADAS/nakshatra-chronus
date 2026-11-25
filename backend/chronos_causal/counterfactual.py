"""Reproducible measurement-level counterfactuals; original rows are never mutated."""
from __future__ import annotations
import numpy as np
from .schema import normalize_observations

_ALLOWED = {"sky_variability", "detector_template", "moving_source", "mixed", "transient"}

def make_counterfactual(observations, intervention: str, *, amplitude: float = 1.0,
                        template_amplitude: float = 0.0, motion_x_per_day: float = 0.0,
                        motion_y_per_day: float = 0.0, added_noise_sigma: float = 0.0,
                        event_start_mjd: float | None = None, event_end_mjd: float | None = None,
                        seed: int = 1):
    if intervention not in _ALLOWED:
        raise ValueError(f"intervention must be one of {sorted(_ALLOWED)}")
    values = [amplitude, template_amplitude, motion_x_per_day, motion_y_per_day, added_noise_sigma]
    if any(not np.isfinite(float(v)) for v in values) or added_noise_sigma < 0:
        raise ValueError("counterfactual parameters must be finite and added_noise_sigma non-negative")
    rows = normalize_observations(observations)
    result = [dict(row) for row in rows]
    times = np.asarray([r["mjd"] for r in result])
    center = float(np.mean(times))
    span = max(float(np.ptp(times)), 1.0)
    if intervention == "transient":
        if event_start_mjd is None:
            event_start_mjd = float(np.quantile(times, 0.55))
        if event_end_mjd is None:
            event_end_mjd = float(np.quantile(times, 0.75))
        if not np.isfinite(event_start_mjd) or not np.isfinite(event_end_mjd) or event_end_mjd < event_start_mjd:
            raise ValueError("transient interval must be finite and event_end_mjd >= event_start_mjd")
    rng = np.random.default_rng(int(seed))
    for row in result:
        dt = (float(row["mjd"]) - center) / span
        score = float(row.get("template_score") or 0.0)
        shift = 0.0
        if intervention in {"sky_variability", "mixed"}:
            shift += float(amplitude) * dt
        if intervention in {"detector_template", "mixed"}:
            shift += float(template_amplitude if intervention == "mixed" else amplitude) * score
        if intervention in {"sky_variability", "detector_template", "mixed"}:
            row["flux"] = float(row["flux"]) + shift
        if intervention == "moving_source":
            row["sky_x"] = float(row["sky_x"]) + float(motion_x_per_day) * (float(row["mjd"]) - center)
            row["sky_y"] = float(row["sky_y"]) + float(motion_y_per_day) * (float(row["mjd"]) - center)
        if intervention == "transient" and float(event_start_mjd) <= float(row["mjd"]) <= float(event_end_mjd):
            row["flux"] = float(row["flux"]) + float(amplitude)
        if added_noise_sigma:
            row["flux"] = float(row["flux"]) + float(rng.normal(0.0, added_noise_sigma))
        row["counterfactual"] = intervention
    return {
        "intervention": intervention,
        "seed": int(seed),
        "event_interval_mjd": [event_start_mjd, event_end_mjd] if intervention == "transient" else None,
        "observations": result,
        "measurement_level_only": True,
        "warning": "This transforms supplied measurements. It does not simulate photons, PSFs, detector readout, calibration or raw FITS pixels.",
        "original_rows_mutated": False,
    }
