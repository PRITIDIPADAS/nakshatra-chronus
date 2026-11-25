"""Deterministic measurement-level challenge fixtures.

These cases test code paths and are not a substitute for blind injections into
actual calibrated SPHEREx exposures.
"""
from __future__ import annotations
import math
import numpy as np

SCENARIOS = (
    "static_source", "achromatic_variable", "chromatic_variable",
    "transient", "moving_source", "instrumental_artifact", "mixed_sky_detector",
)

def generate_scenario(scenario: str, *, seed: int = 1, n_observations: int = 12) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {list(SCENARIOS)}")
    if n_observations < 8:
        raise ValueError("n_observations must be at least eight")
    rng = np.random.default_rng(int(seed))
    times = np.linspace(60000.0, 60040.0, n_observations)
    wave = 1.4 + 0.35 * np.sin(np.arange(n_observations) * 1.17)
    template = 0.5 + 0.34 * np.sin(np.arange(n_observations) * 1.73) + 0.12 * np.cos(np.arange(n_observations) * 0.57)
    rows = []
    t0 = float(np.mean(times))
    span = float(np.ptp(times))
    event_lo = n_observations // 3
    event_hi = min(n_observations - 2, event_lo + 1)
    for i, (mjd, lam) in enumerate(zip(times, wave)):
        dt = (mjd - t0) / span
        detector_score = float(template[i])
        detector_x = 300.0 + 2.0 * math.sin(i * 0.8)
        detector_y = 510.0 + 2.0 * math.cos(i * 0.7)
        sky_x, sky_y = 0.05 * math.sin(i), 0.05 * math.cos(i)
        flux = 100.0
        if scenario in {"achromatic_variable", "mixed_sky_detector"}:
            flux += 16.0 * dt
        if scenario == "chromatic_variable":
            flux += 18.0 * dt * ((lam - float(np.mean(wave))) / float(np.ptp(wave)))
        if scenario in {"instrumental_artifact", "mixed_sky_detector"}:
            flux += (24.0 if scenario == "instrumental_artifact" else 9.0) * detector_score
        if scenario == "transient" and event_lo <= i <= event_hi:
            flux += 28.0
        if scenario == "moving_source":
            sky_x += 1.8 * dt
            sky_y -= 1.0 * dt
        if scenario == "instrumental_artifact":
            detector_x, detector_y = 320.0, 490.0
            sky_x += 0.8 * math.sin(i * 0.75)
            sky_y += 0.8 * math.cos(i * 0.7)
        sigma = 1.5
        flux += float(rng.normal(0.0, sigma))
        rows.append({
            "observation_id": f"SYN-{seed}-{i:03d}",
            "candidate_id": f"SYNTHETIC-{scenario}",
            "mjd": float(mjd),
            "wavelength_um": float(lam),
            "flux": float(flux),
            "sigma": sigma,
            "sky_x": float(sky_x),
            "sky_y": float(sky_y),
            "sky_sigma": 0.12,
            "detector_x": float(detector_x),
            "detector_y": float(detector_y),
            "detector_sigma": 0.15,
            "detector_id": "D2" if i % 2 == 0 else "D3",
            "template_score": detector_score,
            "calibration_group": "SYNTHETIC-FIXTURE",
            "valid": True,
        })
    return {
        "scenario": scenario,
        "seed": int(seed),
        "observations": rows,
        "truth_label": scenario,
        "data_class": "synthetic measurement-level fixture",
        "warning": "This deterministic fixture is for software tests, not scientific performance claims or an independent benchmark.",
    }
