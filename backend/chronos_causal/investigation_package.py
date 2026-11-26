"""Create and verify reproducible CHRONOS investigation ZIP packages.

The package seals exported bytes and records source URIs/checksums. It does not
prove authorship, archive authenticity or scientific truth.
"""
from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
import hashlib
import json
import os
import platform
import re
import zipfile

PACKAGE_SCHEMA = "chronos-investigation-package/1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_MEMBERS = {
    "investigation.json",
    "analysis.json",
    "evidence_graph.json",
    "sources.json",
    "environment.json",
    "REPRODUCE.txt",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture_environment(*, git_commit: str | None = None) -> dict[str, Any]:
    packages = {}
    for name in (
        "astropy", "astroquery", "numpy", "scipy", "pandas",
        "photutils", "reproject", "fastapi", "pydantic",
    ):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
        "git_commit": git_commit or os.environ.get("CHRONOS_GIT_COMMIT"),
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=False,
            allow_nan=False, default=str,
        ) + "\n"
    ).encode("utf-8")


def _safe_member_name(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe package member path: {value!r}")
    if any(part in {"", "."} for part in path.parts):
        raise ValueError(f"unsafe package member path: {value!r}")
    return str(path)


def _normalize_sources(
    source_files: Sequence[Mapping[str, Any]],
    *,
    include_source_bytes: bool,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    rows: list[dict[str, Any]] = []
    members: dict[str, bytes] = {}
    used_names: set[str] = set()

    for index, raw in enumerate(source_files):
        row = dict(raw)
        role = str(row.get("role", "")).strip()
        native_uri = row.get("native_uri")
        digest = str(row.get("sha256", "")).lower()
        if not role:
            raise ValueError(f"source file {index} requires a non-empty role")
        if not isinstance(native_uri, str) or not native_uri.startswith("https://"):
            raise ValueError(f"source file {index} requires its exact HTTPS native_uri")
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"source file {index} requires a 64-character SHA-256")
        if not row.get("product_type") or not row.get("release") or not row.get("detector"):
            raise ValueError(f"source file {index} requires product_type, release and detector")

        local_path = row.get("local_path")
        include_name = None
        local_status = "not_available_locally"
        actual_byte_count = row.get("byte_count")
        if local_path:
            path = Path(str(local_path))
            if not path.is_file():
                raise FileNotFoundError(f"source file {index} is unavailable: {path}")
            actual_hash = sha256_file(path)
            if actual_hash != digest:
                raise ValueError(f"source file {index} SHA-256 does not match the supplied manifest")
            actual_byte_count = path.stat().st_size
            if row.get("byte_count") is not None and int(row["byte_count"]) != actual_byte_count:
                raise ValueError(f"source file {index} byte_count does not match its local bytes")
            local_status = "local_bytes_verified"
            if include_source_bytes:
                safe_role = re.sub(r"[^A-Za-z0-9_.-]+", "_", role).strip("._") or "source"
                suffix = path.suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", path.suffix or "") else ".bin"
                include_name = _safe_member_name(
                    f"sources/{index:04d}_{safe_role}_{digest[:12]}{suffix}"
                )
                if include_name in used_names:
                    raise ValueError(f"duplicate package source member {include_name}")
                members[include_name] = path.read_bytes()
                used_names.add(include_name)
        elif include_source_bytes:
            raise ValueError(
                f"source file {index} cannot be embedded because no local_path was supplied"
            )

        rows.append({
            "role": role,
            "archive_id": row.get("archive_id"),
            "product_type": row["product_type"],
            "release": row["release"],
            "detector": str(row["detector"]),
            "observation_time": row.get("observation_time"),
            "pipeline_version": row.get("pipeline_version"),
            "processing_date": row.get("processing_date"),
            "native_uri": native_uri,
            "sha256": digest,
            "byte_count": actual_byte_count,
            "local_bytes_status": local_status,
            "package_member": include_name,
            "compatibility_group": row.get("compatibility_group"),
            "compatibility_status": row.get("compatibility_status", "unassigned"),
        })
    return rows, members


def create_investigation_package(
    destination: str | Path,
    *,
    candidate_id: str,
    analysis: Mapping[str, Any],
    evidence_graph: Mapping[str, Any],
    source_files: Sequence[Mapping[str, Any]],
    reproduction_command: str,
    code_commit: str | None = None,
    environment: Mapping[str, Any] | None = None,
    processing_configuration: Mapping[str, Any] | None = None,
    failed_checks: Sequence[Mapping[str, Any]] | None = None,
    include_source_bytes: bool = False,
) -> dict[str, Any]:
    """Write an investigation ZIP and an adjacent SHA-256 sidecar."""
    if not str(candidate_id).strip():
        raise ValueError("candidate_id is required")
    if not isinstance(analysis, Mapping) or "verdict" not in analysis:
        raise ValueError("analysis must contain a verdict")
    if not isinstance(evidence_graph, Mapping) or "graph_sha256" not in evidence_graph:
        raise ValueError("evidence_graph must contain graph_sha256")
    if not isinstance(reproduction_command, str) or not reproduction_command.strip():
        raise ValueError("a reproduction command is required")
    if not source_files:
        raise ValueError("at least one exact source-file record is required")

    normalized_sources, source_members = _normalize_sources(
        source_files, include_source_bytes=include_source_bytes
    )
    env = dict(environment or capture_environment(git_commit=code_commit))
    if code_commit is not None:
        env["git_commit"] = code_commit
    config = dict(processing_configuration or {})
    checks = [dict(item) for item in (failed_checks or [])]
    created = utc_now()
    complete = all(row["package_member"] for row in normalized_sources)

    investigation = {
        "schema": PACKAGE_SCHEMA,
        "candidate_id": str(candidate_id),
        "created_utc": created,
        "code_commit": code_commit or env.get("git_commit"),
        "processing_configuration": config,
        "reproduction_command": reproduction_command,
        "source_file_count": len(normalized_sources),
        "all_source_bytes_embedded": bool(complete),
        "failed_or_unknown_checks_preserved": checks,
        "claim_boundary": (
            "Hashes verify exported byte integrity only. They do not prove authorship, "
            "archive authenticity, calibration compatibility or scientific truth."
        ),
    }
    files: dict[str, bytes] = {
        "investigation.json": _json_bytes(investigation),
        "analysis.json": _json_bytes(dict(analysis)),
        "evidence_graph.json": _json_bytes(dict(evidence_graph)),
        "sources.json": _json_bytes(normalized_sources),
        "environment.json": _json_bytes(env),
        "REPRODUCE.txt": (reproduction_command.rstrip() + "\n").encode("utf-8"),
    }
    files.update(source_members)

    manifest_rows = [
        {"path": name, "byte_count": len(data), "sha256": sha256_bytes(data)}
        for name, data in sorted(files.items())
    ]
    package_manifest = {
        "schema": "chronos-package-integrity-manifest/1.0",
        "created_utc": created,
        "files": manifest_rows,
        "source_bytes_embedded": bool(complete),
        "source_file_count": len(normalized_sources),
    }

    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(
        temporary, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(_safe_member_name(name), data)
        archive.writestr("package_manifest.json", _json_bytes(package_manifest))
    temporary.replace(output)

    archive_sha = sha256_file(output)
    sidecar = output.with_name(output.name + ".sha256")
    sidecar.write_text(f"{archive_sha}  {output.name}\n", encoding="utf-8")
    return {
        "path": str(output),
        "sha256": archive_sha,
        "sidecar": str(sidecar),
        "member_count": len(files) + 1,
        "source_bytes_embedded": bool(complete),
        "source_file_count": len(normalized_sources),
        "claim_boundary": "Integrity checksum only; not proof of authorship or scientific truth.",
    }


def verify_investigation_package(path: str | Path) -> dict[str, Any]:
    """Verify the archive sidecar, ZIP member set, lengths and member SHA-256s."""
    archive_path = Path(path)
    if not archive_path.is_file() or not zipfile.is_zipfile(archive_path):
        return {"valid": False, "status": "invalid", "reason": "not a readable ZIP package"}

    actual_archive_sha = sha256_file(archive_path)
    sidecar = archive_path.with_name(archive_path.name + ".sha256")
    if sidecar.is_file():
        supplied = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
        if not SHA256_RE.fullmatch(supplied) or supplied != actual_archive_sha:
            return {
                "valid": False, "status": "invalid",
                "reason": "ZIP SHA-256 sidecar does not match the package bytes",
                "actual_sha256": actual_archive_sha,
            }

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                return {"valid": False, "status": "invalid", "reason": "duplicate ZIP member names"}
            for name in names:
                try:
                    _safe_member_name(name)
                except ValueError as exc:
                    return {"valid": False, "status": "invalid", "reason": str(exc)}
            if "package_manifest.json" not in names:
                return {"valid": False, "status": "invalid", "reason": "package_manifest.json is missing"}
            missing_core = sorted(CORE_MEMBERS - set(names))
            if missing_core:
                return {"valid": False, "status": "invalid", "reason": f"missing core members: {missing_core}"}
            manifest = json.loads(archive.read("package_manifest.json").decode("utf-8"))
            if manifest.get("schema") != "chronos-package-integrity-manifest/1.0":
                return {"valid": False, "status": "invalid", "reason": "unsupported package manifest schema"}
            expected = {
                row["path"]: row for row in manifest.get("files", [])
                if isinstance(row, Mapping) and isinstance(row.get("path"), str)
            }
            actual_names = set(names) - {"package_manifest.json"}
            if actual_names != set(expected):
                return {
                    "valid": False, "status": "invalid",
                    "reason": "package member set differs from the integrity manifest",
                    "unlisted_members": sorted(actual_names - set(expected)),
                    "missing_members": sorted(set(expected) - actual_names),
                }
            failures = []
            for name, row in expected.items():
                raw = archive.read(name)
                digest = sha256_bytes(raw)
                if len(raw) != row.get("byte_count") or digest != row.get("sha256"):
                    failures.append({
                        "path": name,
                        "expected_sha256": row.get("sha256"),
                        "actual_sha256": digest,
                        "expected_byte_count": row.get("byte_count"),
                        "actual_byte_count": len(raw),
                    })
            if failures:
                return {
                    "valid": False, "status": "invalid",
                    "reason": "one or more package members failed integrity verification",
                    "failures": failures,
                }
            investigation = json.loads(archive.read("investigation.json").decode("utf-8"))
            return {
                "valid": True,
                "status": "valid",
                "candidate_id": investigation.get("candidate_id"),
                "package_sha256": actual_archive_sha,
                "member_count": len(names),
                "source_bytes_embedded": manifest.get("source_bytes_embedded"),
                "claim_boundary": "Checks verify package byte integrity only, not scientific truth or authorship.",
            }
    except Exception as exc:
        return {"valid": False, "status": "invalid", "reason": f"{type(exc).__name__}: {exc}"}
