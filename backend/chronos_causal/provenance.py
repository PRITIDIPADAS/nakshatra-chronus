"""Archive provenance manifests with completeness and integrity checks."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from datetime import datetime
import hashlib, json


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str).encode("utf-8")


def create_manifest(*, project: str, calibration_group: str, files: Sequence[Mapping[str, Any]],
                    software: Mapping[str, Any], processing_choices: Mapping[str, Any] | None = None,
                    source_query: Mapping[str, Any] | str | None = None, retrieved_at: str | None = None):
    if not project.strip() or not calibration_group.strip() or not files:
        raise ValueError("project, calibration_group and files are required")
    issues=[]
    if not source_query: issues.append("source_query_not_recorded")
    if not retrieved_at: issues.append("retrieval_timestamp_not_recorded")
    else:
        try:
            dt=datetime.fromisoformat(str(retrieved_at).replace("Z","+00:00"))
            if dt.tzinfo is None: issues.append("retrieval_timestamp_timezone_missing")
        except ValueError: raise ValueError("retrieved_at must be ISO-8601") from None
    for key in ("python_version","project_version","pipeline_commit"):
        if not str(software.get(key,"")).strip(): issues.append("software_"+key+"_not_recorded")
    if not processing_choices: issues.append("processing_configuration_not_recorded")
    normalized=[]; seen=set()
    for i,raw in enumerate(files):
        row=dict(raw); required=("archive_id","product_type","release","detector","sha256","bytes")
        missing=[k for k in required if k not in row]
        if missing: raise ValueError(f"file {i} missing required provenance fields: {missing}")
        digest=str(row["sha256"]).lower()
        if len(digest)!=64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"file {i} invalid SHA-256")
        size=int(row["bytes"])
        if size<0: raise ValueError("file bytes must be non-negative")
        key=(str(row["archive_id"]),digest)
        if key in seen: raise ValueError("duplicate archive product")
        seen.add(key)
        for field in ("native_uri","processing_version","calibration_version"):
            if not str(row.get(field,"")).strip(): issues.append(f"file_{i}_{field}_not_recorded")
        if row.get("observation_time_mjd") is None and not row.get("observation_time"):
            issues.append(f"file_{i}_observation_time_not_recorded")
        row.update(sha256=digest,bytes=size,detector=str(row["detector"]))
        normalized.append(row)
    body={"schema":"chronos-archive-manifest/2.0","project":project,"calibration_group":calibration_group,
        "source_query":source_query,"retrieved_at":retrieved_at,"files":normalized,"software":dict(software),
        "processing_choices":dict(processing_choices or {}),"complete_for_reproduction":not issues,
        "completeness_issues":sorted(set(issues)),
        "integrity_note":"SHA-256 detects content changes; it does not establish authenticity, authorship or scientific truth."}
    return {**body,"manifest_sha256":hashlib.sha256(_canonical(body)).hexdigest()}


def verify_manifest(manifest: Mapping[str,Any]):
    if manifest.get("schema") not in {"chronos-archive-manifest/1.0","chronos-archive-manifest/2.0"}:
        return {"valid":False,"reason":"unsupported schema"}
    supplied=manifest.get("manifest_sha256")
    body={k:v for k,v in manifest.items() if k!="manifest_sha256"}
    try: actual=hashlib.sha256(_canonical(body)).hexdigest()
    except (TypeError,ValueError) as exc: return {"valid":False,"reason":str(exc)}
    return {"valid":supplied==actual,"supplied_sha256":supplied,"computed_sha256":actual,
        "complete_for_reproduction":bool(manifest.get("complete_for_reproduction",False)),
        "completeness_issues":list(manifest.get("completeness_issues",[])),
        "warning":"A valid hash proves only that the metadata match their seal. It does not prove metadata truth, source authenticity or scientific compatibility."}
