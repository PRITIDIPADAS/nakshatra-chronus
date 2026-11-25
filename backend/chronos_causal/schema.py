"""Validated observation rows for the measurement-level Causal Sky Twin."""
from __future__ import annotations
import math
from typing import Any, Mapping, Sequence

_REQUIRED = (
    "mjd", "wavelength_um", "flux", "sigma",
    "sky_x", "sky_y", "sky_sigma",
    "detector_x", "detector_y", "detector_sigma", "detector_id",
)

def normalize_observations(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, (list, tuple)) or len(rows) < 3:
        raise ValueError("observations must contain at least three rows")
    result = []
    seen = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ValueError(f"observation {index} must be an object")
        if raw.get("valid", True) is False:
            continue
        missing = [key for key in _REQUIRED if key not in raw]
        if missing:
            raise ValueError(f"observation {index} is missing fields: {missing}")
        row = dict(raw)
        for key in _REQUIRED[:-1]:
            try:
                value = float(row[key])
            except (TypeError, ValueError):
                raise ValueError(f"observation {index}: {key} must be numeric") from None
            if not math.isfinite(value):
                raise ValueError(f"observation {index}: {key} must be finite")
            row[key] = value
        if row["wavelength_um"] <= 0:
            raise ValueError(f"observation {index}: wavelength_um must be positive")
        if row["sigma"] <= 0 or row["sky_sigma"] <= 0 or row["detector_sigma"] <= 0:
            raise ValueError(f"observation {index}: all supplied uncertainties must be positive")
        row["detector_id"] = str(row["detector_id"])
        row["observation_id"] = str(row.get("observation_id", index))
        if row["observation_id"] in seen:
            raise ValueError(f"duplicate observation_id: {row['observation_id']}")
        seen.add(row["observation_id"])
        score = row.get("template_score")
        if score is not None:
            score = float(score)
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError(f"observation {index}: template_score must be in [0, 1]")
            row["template_score"] = score
        result.append(row)
    if len(result) < 3:
        raise ValueError("fewer than three valid observations remain")
    return result
