"""Immutable manifests for archive inputs and calibration choices."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import hashlib
import json

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=str).encode("utf-8")

def create_manifest(*, project: str, calibration_group: str, files: Sequence[Mapping[str, Any]],
                    software: Mapping[str, Any], processing_choices: Mapping[str, Any] | None = None):
    if not project.strip() or not calibration_group.strip():
        raise ValueError("project and calibration_group are required")
    if not files:
        raise ValueError("at least one input file is required")
    normalized = []
    seen = set()
    for index, raw in enumerate(files):
        row = dict(raw)
        required = ("archive_id", "product_type", "release", "detector", "sha256", "bytes")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(f"file {index} is missing required provenance fields: {missing}")
        digest = str(row["sha256"]).lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"file {index} has an invalid SHA-256 digest")
        size = int(row["bytes"])
        if size < 0:
            raise ValueError(f"file {index} bytes must be non-negative")
        key = (str(row["archive_id"]), digest)
        if key in seen:
            raise ValueError(f"duplicate archive file: {row['archive_id']}")
        seen.add(key)
        row["sha256"] = digest
        row["bytes"] = size
        row["detector"] = str(row["detector"])
        normalized.append(row)
    body = {
        "schema": "chronos-archive-manifest/1.0",
        "project": project,
        "calibration_group": calibration_group,
        "files": normalized,
        "software": dict(software),
        "processing_choices": dict(processing_choices or {}),
        "immutability_note": "This record seals supplied provenance metadata. It does not verify that the metadata are true or that the files are scientifically compatible.",
    }
    return {**body, "manifest_sha256": hashlib.sha256(_canonical(body)).hexdigest()}

def verify_manifest(manifest: Mapping[str, Any]):
    if manifest.get("schema") != "chronos-archive-manifest/1.0":
        return {"valid": False, "reason": "unsupported manifest schema"}
    supplied = manifest.get("manifest_sha256")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    try:
        actual = hashlib.sha256(_canonical(body)).hexdigest()
    except (TypeError, ValueError) as exc:
        return {"valid": False, "reason": str(exc)}
    return {"valid": supplied == actual, "supplied_sha256": supplied, "computed_sha256": actual}
