"""Adapters that put four CHRONOS baselines onto one field and mask contract."""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import math

import numpy as np
from scipy.ndimage import map_coordinates

from chronos_addons.forensics import diagnose_candidate
from .baselines import REQUIRED_METHODS


def _signature(value: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "field_id", "dataset_class", "exposure_ids", "mask_sha256",
        "truth_catalogue_sha256", "coordinate_frame", "coordinate_unit",
    )
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError("input_signature is missing: " + ", ".join(missing))
    return dict(value)


def _detection(identifier, x, y, score, provenance):
    values = [float(x), float(y), float(score)]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("adapter produced a non-finite detection")
    return {
        "detection_id": str(identifier),
        "x": values[0],
        "y": values[1],
        "score": values[2],
        "provenance": dict(provenance),
    }


def _flagged_footprint_fraction(state, x, y, radius=1):
    masks = np.asarray(state.get("RB"), dtype=bool)
    if masks.ndim != 3:
        return None
    xi, yi = int(round(float(x))), int(round(float(y)))
    height, width = masks.shape[1:]
    x0, x1 = max(0, xi - radius), min(width, xi + radius + 1)
    y0, y1 = max(0, yi - radius), min(height, yi + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return None
    patch = masks[:, y0:y1, x0:x1]
    return float(np.mean(patch)) if patch.size else None


def _detector_position_scatter(state, x, y):
    exposures = state.get("exps") or []
    maps = state.get("MAP") or []
    if len(exposures) != len(maps):
        return None
    positions = {}
    for exposure, mapping in zip(exposures, maps):
        if not isinstance(mapping, (list, tuple)) or len(mapping) != 2:
            continue
        try:
            dx = float(map_coordinates(np.asarray(mapping[0], float), [[float(y)], [float(x)]], order=1)[0])
            dy = float(map_coordinates(np.asarray(mapping[1], float), [[float(y)], [float(x)]], order=1)[0])
        except (ValueError, IndexError, TypeError):
            continue
        if math.isfinite(dx) and math.isfinite(dy):
            positions.setdefault(str(getattr(exposure, "det", "unknown")), []).append((dx, dy))
    scatters = []
    for samples in positions.values():
        if len(samples) >= 2:
            values = np.asarray(samples, dtype=float)
            center = np.median(values, axis=0)
            scatters.append(float(np.median(np.linalg.norm(values - center, axis=1))))
    return min(scatters) if scatters else None


def build_four_baseline_records(state: Mapping[str, Any], input_signature: Mapping[str, Any], *,
                                sky_detector_twin_detections: Sequence[Mapping[str, Any]] | None,
                                score_thresholds: Mapping[str, Sequence[float]],
                                snr_threshold: float = 5.0,
                                forensics_thresholds: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Build common-input records from one prepared CHRONOS field state.

    State must be the output of pipeline.run. Twin detections are supplied by
    the causal inference runner using the same field manifest.
    """
    import pipeline

    signature = _signature(input_signature)
    if not isinstance(state, Mapping) or not state.get("exps"):
        raise ValueError("state must contain the exposure list from one pipeline.run result")
    if "cands" not in state:
        raise ValueError("state must contain cands; call pipeline.run before building baselines")
    if float(snr_threshold) <= 0 or not math.isfinite(float(snr_threshold)):
        raise ValueError("snr_threshold must be finite and positive")
    if not isinstance(score_thresholds, Mapping) or any(name not in score_thresholds for name in REQUIRED_METHODS):
        raise ValueError("score_thresholds must define every required baseline")
    for method in REQUIRED_METHODS:
        values = [float(value) for value in score_thresholds[method]]
        if not values or any(not math.isfinite(value) for value in values):
            raise ValueError(f"{method} needs finite score thresholds")

    snr_map = state.get("DEEPS")
    if snr_map is None:
        raise ValueError("pipeline state has no DEEPS matched-filter S/N map")
    snr_detections = [
        _detection(
            f"snr-{index:06d}", x, y, score,
            {"method": "snr_only", "map": "DEEPS", "score_definition": "matched-filter S/N"},
        )
        for index, (x, y, score) in enumerate(
            pipeline.peaks(snr_map, float(snr_threshold), pipeline.TH["edge"])
        )
    ]

    pda_detections = []
    for index, candidate in enumerate(state["cands"]):
        sources = {}
        scores = []
        for key in ("P", "D", "A"):
            members = list(candidate.get(key) or [])
            sources[key] = [
                {"score": float(item.get("s", 0.0)), "why": list(item.get("why") or [])}
                for item in members
            ]
            scores.extend(abs(float(item.get("s", 0.0))) for item in members)
        score = max(scores, default=0.0)
        pda_detections.append(_detection(
            f"pda-{index:06d}", candidate["x"], candidate["y"], score,
            {
                "method": "chronos_pda",
                "detector_agreement": str(candidate.get("methods", "")),
                "component_detections": sources,
                "score_definition": "maximum absolute contributing P, D or A significance",
            },
        ))

    # Instrument forensics is a triage system, not a standalone source finder.
    # Apply its transparent rules to the same P/D/A candidates. A strong veto
    # is used only when a measurable warning input is actually present.
    forensics_detections = []
    for index, candidate in enumerate(state["cands"]):
        sources = []
        for key in ("P", "D", "A"):
            sources.extend(candidate.get(key) or [])
        base_score = max((abs(float(item.get("s", 0.0))) for item in sources), default=0.0)
        flagged_fraction = _flagged_footprint_fraction(state, candidate["x"], candidate["y"])
        detector_scatter = _detector_position_scatter(state, candidate["x"], candidate["y"])
        evidence = {
            "candidate_id": f"pda-{index:06d}",
            "candidate_snr": base_score,
            "flagged_fraction": flagged_fraction,
            "same_detector_position_scatter_pixels": detector_scatter,
        }
        diagnosis = diagnose_candidate(evidence, forensics_thresholds)
        hard_veto = any(item["severity"] == "strong" for item in diagnosis["findings"])
        forensics_detections.append(_detection(
            f"forensics-{index:06d}",
            candidate["x"], candidate["y"],
            -1.0e12 if hard_veto else base_score,
            {
                "method": "instrument_forensics",
                "gate": "existing forensics strong-finding veto",
                "accepted": not hard_veto,
                "inherited_score": base_score,
                "diagnostic_status": diagnosis["status"],
                "findings": diagnosis["findings"],
                "thresholds": diagnosis["thresholds"],
                "evidence": evidence,
            },
        ))

    twin_detections = []
    for index, row in enumerate(sky_detector_twin_detections or []):
        if not isinstance(row, Mapping):
            raise ValueError("Sky–Detector Twin detections must be objects")
        provenance = row.get("provenance")
        if not isinstance(provenance, Mapping) or not provenance:
            raise ValueError("each Sky–Detector Twin detection requires provenance")
        twin_detections.append(_detection(
            row.get("detection_id", f"twin-{index:06d}"),
            row["x"], row["y"], row["score"],
            {"method": "sky_detector_twin", **dict(provenance)},
        ))

    rows = {
        "snr_only": snr_detections,
        "chronos_pda": pda_detections,
        "instrument_forensics": forensics_detections,
        "sky_detector_twin": twin_detections,
    }
    return {
        "input_signature": signature,
        "methods": {
            name: {"input_signature": signature, "detections": rows[name]}
            for name in REQUIRED_METHODS
        },
        "score_thresholds": {
            name: [float(value) for value in score_thresholds[name]]
            for name in REQUIRED_METHODS
        },
        "baseline_contract": {
            "same_pipeline_state": True,
            "same_exposure_set": list(signature["exposure_ids"]),
            "same_mask_checksum": signature["mask_sha256"],
            "same_coordinate_frame": signature["coordinate_frame"],
            "snr_only_map": "DEEPS",
            "pda_source": "pipeline.run -> state.cands",
            "instrument_forensics_policy": "P/D/A candidates plus measured flag/detector-position diagnostics",
            "sky_detector_twin_source": "supplied detections from causal inference on this field",
        },
    }
