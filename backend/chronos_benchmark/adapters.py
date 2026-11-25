"""Adapters that put four CHRONOS baselines onto one field and mask contract."""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import hashlib
import json
import math

import numpy as np
from scipy.ndimage import map_coordinates

from chronos_addons.forensics import diagnose_candidate
from .runner import REQUIRED_METHODS, truth_catalogue_digest



def reference_wcs_sha256(reference_wcs) -> str:
    """Hash the canonical FITS header of the registered field WCS."""
    if reference_wcs is None or not hasattr(reference_wcs, "to_header"):
        raise ValueError("a reference WCS with to_header() is required for sky-pixel matching")
    header = reference_wcs.to_header(relax=True)
    serialized = header.tostring(sep="\\n", endcard=True, padding=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def field_mask_sha256(state: Mapping[str, Any]) -> str:
    """Hash the per-exposure union of bad flags, out-of-footprint and invalid image pixels.

    Exposure masks are sorted by immutable exposure ID before hashing, making
    the result independent of input list order while retaining exposure identity.
    """
    exposures = list(state.get("exps") or [])
    if not exposures:
        raise ValueError("state needs exposures to compute its mask checksum")
    ids = [str(getattr(exposure, "id", "")) for exposure in exposures]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("every exposure needs a unique non-empty id for mask hashing")
    flags = np.asarray(state.get("RB"), dtype=bool)
    inside = np.asarray(state.get("IN"), dtype=bool)
    image = np.asarray(state.get("R"), dtype=float)
    if flags.ndim != 3 or inside.shape != flags.shape or image.shape != flags.shape:
        raise ValueError("RB, IN and R must have equal (exposure, y, x) shapes")
    if flags.shape[0] != len(exposures):
        raise ValueError("exposure count does not match prepared mask arrays")
    digest = hashlib.sha256()
    digest.update(b"chronos-field-mask/1\\0")
    for index in sorted(range(len(ids)), key=lambda item: ids[item]):
        mask = flags[index] | ~inside[index] | ~np.isfinite(image[index])
        digest.update(ids[index].encode("utf-8") + b"\\0")
        digest.update(np.asarray(mask.shape, dtype=np.int64).tobytes())
        digest.update(np.packbits(mask.reshape(-1), bitorder="little").tobytes())
    return digest.hexdigest()


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
                                snr_threshold: float | None = None,
                                forensics_thresholds: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Build common-input records from one prepared CHRONOS field state.

    State must be the output of pipeline.run. Twin detections are supplied by
    the causal inference runner using the same field manifest.
    """
    import pipeline

    if not isinstance(state, Mapping) or not state.get("exps"):
        raise ValueError("state must contain the exposure list from one pipeline.run result")
    signature = _signature(input_signature)
    state_exposure_ids = sorted(str(getattr(exposure, "id", "")) for exposure in state["exps"])
    if any(not value for value in state_exposure_ids) or len(set(state_exposure_ids)) != len(state_exposure_ids):
        raise ValueError("prepared exposures need unique, non-empty IDs")
    if sorted(signature["exposure_ids"]) != state_exposure_ids:
        raise ValueError("input_signature exposure_ids do not match the prepared pipeline state")
    actual_mask_digest = field_mask_sha256(state)
    if actual_mask_digest != str(signature["mask_sha256"]).lower():
        raise ValueError("input_signature mask_sha256 does not match the prepared pipeline masks")
    if signature.get("coordinate_frame") == "sky" and signature.get("coordinate_unit") == "pixel":
        actual_wcs_digest = reference_wcs_sha256(state.get("ref"))
        if actual_wcs_digest != str(signature.get("pixel_wcs_sha256", "")).lower():
            raise ValueError("input_signature pixel_wcs_sha256 does not match the registered field WCS")
    if "cands" not in state:
        raise ValueError("state must contain cands; call pipeline.run before building baselines")
    if not isinstance(score_thresholds, Mapping) or any(name not in score_thresholds for name in REQUIRED_METHODS):
        raise ValueError("score_thresholds must define every required baseline")
    normalized_thresholds = {}
    for method in REQUIRED_METHODS:
        values = [float(value) for value in score_thresholds[method]]
        if not values or any(not math.isfinite(value) for value in values):
            raise ValueError(f"{method} needs finite score thresholds")
        normalized_thresholds[method] = values
    minimum_snr_score = min(normalized_thresholds["snr_only"])
    detection_floor = minimum_snr_score if snr_threshold is None else float(snr_threshold)
    if not math.isfinite(detection_floor) or detection_floor <= 0:
        raise ValueError("snr_threshold must be finite and positive")
    if detection_floor > minimum_snr_score:
        raise ValueError("snr_threshold cannot exceed the lowest requested SNR curve threshold")

    snr_map = state.get("DEEPS")
    if snr_map is None:
        raise ValueError("pipeline state has no DEEPS matched-filter S/N map")
    snr_detections = [
        _detection(
            f"snr-{index:06d}", x, y, score,
            {"method": "snr_only", "map": "DEEPS", "score_definition": "matched-filter S/N",
             "collection_floor": detection_floor},
        )
        for index, (x, y, score) in enumerate(
            pipeline.peaks(snr_map, detection_floor, pipeline.TH["edge"])
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
            name: normalized_thresholds[name]
            for name in REQUIRED_METHODS
        },
        "baseline_contract": {
            "same_pipeline_state": True,
            "same_exposure_set": list(signature["exposure_ids"]),
            "same_mask_checksum": signature["mask_sha256"],
            "same_coordinate_frame": signature["coordinate_frame"],
            "verified_exposure_ids": state_exposure_ids,
            "verified_mask_sha256": actual_mask_digest,
            "verified_pixel_wcs_sha256": (
                reference_wcs_sha256(state.get("ref"))
                if signature.get("coordinate_frame") == "sky" and signature.get("coordinate_unit") == "pixel"
                else None
            ),
            "snr_only_map": "DEEPS",
            "snr_detection_floor": detection_floor,
            "pda_source": "pipeline.run -> state.cands",
            "instrument_forensics_policy": "P/D/A candidates plus measured flag/detector-position diagnostics",
            "sky_detector_twin_source": "supplied detections from causal inference on this field",
        },
    }



def build_benchmark_field_record(state: Mapping[str, Any], input_signature: Mapping[str, Any],
                                 truth_catalogue: Sequence[Mapping[str, Any]], *,
                                 split: str, match_radius: float,
                                 score_thresholds: Mapping[str, Sequence[float]],
                                 sky_detector_twin_detections: Sequence[Mapping[str, Any]] | None,
                                 field_area_deg2: float | None = None,
                                 independence_group_id: str | None = None,
                                 snr_threshold: float | None = None,
                                 forensics_thresholds: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Build one complete field record ready to append to a benchmark package."""
    signature = _signature(input_signature)
    if truth_catalogue_digest(truth_catalogue) != str(signature["truth_catalogue_sha256"]).lower():
        raise ValueError("truth catalogue does not match input_signature truth_catalogue_sha256")
    if split not in {"development", "blind_test", "held_out", "not_split"}:
        raise ValueError("split must be development, blind_test, held_out or not_split")
    radius = float(match_radius)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("match_radius must be finite and positive")
    if field_area_deg2 is not None and (
        not math.isfinite(float(field_area_deg2)) or float(field_area_deg2) <= 0
    ):
        raise ValueError("field_area_deg2 must be finite and positive when supplied")
    group_id = str(independence_group_id or signature["field_id"])
    if not group_id:
        raise ValueError("independence_group_id cannot be blank")

    records = build_four_baseline_records(
        state,
        signature,
        sky_detector_twin_detections=sky_detector_twin_detections,
        score_thresholds=score_thresholds,
        snr_threshold=snr_threshold,
        forensics_thresholds=forensics_thresholds,
    )
    return {
        "split": split,
        "input_signature": signature,
        "truth_catalogue": [dict(row) for row in truth_catalogue],
        "independence_group_id": group_id,
        "match_radius": radius,
        "field_area_deg2": float(field_area_deg2) if field_area_deg2 is not None else None,
        "methods": records["methods"],
        "baseline_contract": records["baseline_contract"],
    }
