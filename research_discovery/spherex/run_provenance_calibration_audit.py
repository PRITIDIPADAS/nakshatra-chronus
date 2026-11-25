#!/usr/bin/env python3
"""Retrieve the exact calibration inputs linked to a SPHEREx Level-2 MEF.

The science-to-calibration relationship comes from the IRSA
spherex.provenance_input table. Calibration candidates discovered by filename
or by detector alone are never promoted to exact inputs by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

IRSA_ROOT = "https://irsa.ipac.caltech.edu/"
DEFAULT_SCIENCE_URI = (
    "ibe/data/spherex/dr1/level2/2025W19_2B/"
    "l2b-v27-2026-198/2/"
    "level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits"
)
SCHEMA = "chronos-spherex-provenance-calibration/1.0"


def plain(value):
    if value is None:
        return None
    if getattr(value, "mask", False):
        return None
    if hasattr(value, "item"):
        try:
            return plain(value.item())
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def query_rows(sql):
    from astroquery.ipac.irsa import Irsa

    response = Irsa.query_tap(sql)
    table = response.to_table() if callable(getattr(response, "to_table", None)) else response
    if not hasattr(table, "colnames"):
        raise TypeError(f"IRSA TAP response is not table-like: {type(table).__name__}")
    return {
        "query": sql,
        "columns": list(table.colnames),
        "row_count": len(table),
        "rows": [
            {str(name): plain(row[name]) for name in table.colnames}
            for row in table
        ],
    }


def safe_sql_string(value):
    return str(value).replace("'", "''")


def normalize_archive_uri(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("archive URI is empty")
    if raw.startswith("https://"):
        parsed = urlparse(raw)
        if parsed.hostname != "irsa.ipac.caltech.edu":
            raise ValueError("only native IRSA HTTPS archive URIs are accepted")
        return raw
    if raw.startswith("http://"):
        raise ValueError("plain HTTP archive URIs are not accepted")
    return urljoin(IRSA_ROOT, raw.lstrip("/"))


def normalize_release(uri):
    path = urlparse(uri).path.lower()
    for release in ("dr1", "qr3"):
        if f"/spherex/{release}/" in path or f"/{release}/" in path:
            return release.upper()
    return None


def calibration_family_from_uri(uri):
    path = urlparse(uri).path.lower()
    families = (
        ("spectral_wcs", "spectral_wcs"),
        ("solid_angle_pixel_map", "solid_angle_pixel_map"),
        ("abs_gain_matrix", "absolute_gain"),
        ("gain_factors", "electronic_gain_factors"),
        ("nonlinear_pars", "nonlinearity"),
        ("readnoise_pars", "read_noise"),
        ("nonfunc_v2", "nonfunctional_pixel_map"),
        ("dark", "dark_current"),
        ("epsf", "effective_psf"),
        ("dichroic", "dichroic"),
        ("he_template", "helium_template"),
        ("shuttle_glow_template", "shuttle_glow_template"),
        ("aurora_template", "aurora_template"),
        ("sip", "sip"),
        ("zodi_scaling_v2", "zodiacal_scaling"),
        ("xtalk_class1", "crosstalk_class_1"),
        ("xtalk_class2", "crosstalk_class_2"),
        ("xtalk_class3", "crosstalk_class_3"),
    )
    for marker, label in families:
        if f"/{marker}/" in path:
            return label
    return "unclassified_calibration"


def verify_archive_checksum(path, checksum):
    if not checksum:
        return {"status": "not_supplied", "algorithm": None, "expected": None, "actual": None}
    token = str(checksum).strip().lower()
    if ":" not in token:
        return {"status": "unsupported_format", "algorithm": None,
                "expected": token, "actual": None}
    algorithm, expected = token.split(":", 1)
    algorithm = algorithm.strip()
    expected = expected.strip()
    if algorithm not in {"md5", "sha256"}:
        return {"status": "unsupported_algorithm", "algorithm": algorithm,
                "expected": expected, "actual": None}
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest().lower()
    return {
        "status": "pass" if actual == expected else "fail",
        "algorithm": algorithm,
        "expected": expected,
        "actual": actual,
    }


def file_hashes(path):
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    count = 0
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
            count += len(block)
    return {"byte_count": count, "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def download_exact_product(uri, destination, *, expected_bytes, expected_checksum,
                           remaining_budget, timeout=240):
    url = normalize_archive_uri(uri)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    received = 0
    try:
        with requests.get(url, stream=True, timeout=(30, timeout)) as response:
            response.raise_for_status()
            declared_length = response.headers.get("Content-Length")
            with temporary.open("wb") as output:
                for block in response.iter_content(1024 * 1024):
                    if not block:
                        continue
                    received += len(block)
                    if received > remaining_budget:
                        raise IOError("download exceeded the remaining total-byte budget")
                    output.write(block)
                    sha.update(block)
                    md5.update(block)
                output.flush()
                os.fsync(output.fileno())
            if expected_bytes is not None and received != int(expected_bytes):
                raise IOError(f"archive byte count mismatch: expected {expected_bytes}, got {received}")
            if declared_length is not None and received != int(declared_length):
                raise IOError(f"HTTP Content-Length mismatch: expected {declared_length}, got {received}")
            digest = {
                "byte_count": received,
                "sha256": sha.hexdigest(),
                "md5": md5.hexdigest(),
            }
            checksum = None
            if expected_checksum:
                token = str(expected_checksum).lower()
                if token.startswith("md5:"):
                    checksum = {
                        "algorithm": "md5",
                        "expected": token.split(":", 1)[1],
                        "actual": digest["md5"],
                        "status": "pass" if digest["md5"] == token.split(":", 1)[1] else "fail",
                    }
                elif token.startswith("sha256:"):
                    checksum = {
                        "algorithm": "sha256",
                        "expected": token.split(":", 1)[1],
                        "actual": digest["sha256"],
                        "status": "pass" if digest["sha256"] == token.split(":", 1)[1] else "fail",
                    }
                else:
                    checksum = {"status": "unsupported_format", "expected": expected_checksum}
                if checksum["status"] != "pass":
                    raise IOError(f"archive checksum verification failed: {checksum}")
            temporary.replace(destination)
            return {
                "status": "downloaded",
                "source_uri": uri,
                "source_url": url,
                "local_path": str(destination),
                **digest,
                "archive_checksum": checksum or {"status": "not_supplied"},
                "http_status": response.status_code,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_type": response.headers.get("Content-Type"),
            }
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        return {
            "status": "failed",
            "source_uri": uri,
            "source_url": url,
            "local_path": None,
            "byte_count": received if received else None,
            "sha256": None,
            "archive_checksum": {"status": "failed"},
            "error": f"{type(exc).__name__}: {exc}",
        }


def inspect_download(path, content_type):
    path = Path(path)
    report = {"format": "unknown", "status": "not_inspected"}
    if content_type == "application/fits" or path.suffix.lower() in {".fits", ".fit", ".fts"}:
        try:
            import numpy as np
            from astropy.io import fits
            hdus = []
            with fits.open(path, memmap=True, checksum=True) as hdul:
                for hdu in hdul:
                    item = {
                        "name": str(hdu.name),
                        "shape": list(hdu.data.shape) if hdu.data is not None else None,
                        "bunit": hdu.header.get("BUNIT"),
                        "detector": hdu.header.get("DETECTOR"),
                        "version": hdu.header.get("VERSION"),
                        "processing_date": hdu.header.get("PROCDATE"),
                    }
                    if hdu.data is not None and str(hdu.name).upper() == "IMAGE":
                        values = np.asarray(hdu.data)
                        item["finite_fraction"] = float(np.isfinite(values).mean())
                    if hdu.data is not None and str(hdu.name).upper() == "VARIANCE":
                        values = np.asarray(hdu.data, dtype=float)
                        finite = np.isfinite(values)
                        item["finite_fraction"] = float(finite.mean())
                        item["negative_finite_pixels"] = int(np.sum(values[finite] < 0))
                    if "CHECKSUM" in hdu.header:
                        item["fits_checksum_status"] = hdu.verify_checksum()
                    if "DATASUM" in hdu.header:
                        item["fits_datasum_status"] = hdu.verify_datasum()
                    hdus.append(item)
                primary = hdul[0].header
            report = {
                "format": "FITS",
                "status": "opened",
                "hdus": hdus,
                "primary_header": {
                    key: primary.get(key)
                    for key in ("SIMPLE", "BITPIX", "NAXIS", "DETECTOR", "VERSION",
                                "PROCDATE", "RELEASE", "DATE-OBS", "MJD-OBS")
                    if key in primary
                },
            }
        except Exception as exc:
            report = {"format": "FITS", "status": "failed",
                      "error": f"{type(exc).__name__}: {exc}"}
    else:
        try:
            data = path.read_bytes()
            text = data[:65536].decode("utf-8", errors="replace")
            report = {
                "format": "text",
                "status": "opened",
                "text_prefix": text[:1200],
                "line_count": text.count("\n") + 1,
            }
        except Exception as exc:
            report = {"format": "text", "status": "failed",
                      "error": f"{type(exc).__name__}: {exc}"}
    return report


def package_versions():
    names = ("astropy", "astroquery", "numpy", "requests", "scipy", "photutils")
    found = {}
    for name in names:
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = None
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": found,
        "git_commit": os.getenv("CHRONOS_GIT_COMMIT"),
    }


def build_sql(science_uri):
    escaped = safe_sql_string(science_uri)
    return f"""
    SELECT a.artifactid AS science_artifactid, a.uri AS science_uri,
      a.planeid AS science_planeid, a.producttype AS science_producttype,
      a.contenttype AS science_contenttype, a.contentlength AS science_contentlength,
      a.contentchecksum AS science_contentchecksum, p.obsid AS science_obsid,
      p.productid AS science_productid, p.provenance_name AS science_provenance_name,
      p.provenance_reference AS science_provenance_reference,
      p.provenance_version AS science_provenance_version,
      p.provenance_project AS science_provenance_project,
      p.provenance_producer AS science_provenance_producer,
      p.provenance_runid AS science_provenance_runid,
      p.provenance_lastexecuted AS science_provenance_lastexecuted,
      p.provenance_keywords AS science_provenance_keywords,
      p.time_bounds_lower AS time_bounds_lower, p.time_bounds_upper AS time_bounds_upper,
      p.time_exposure AS time_exposure, p.energy_bandpassname AS energy_bandpassname,
      p.position_dimension_naxis1 AS naxis1, p.position_dimension_naxis2 AS naxis2,
      p.datarelease AS datarelease, o.collection AS collection,
      o.observationid AS observationid, o.intent AS intent, o.target_name AS target_name
    FROM spherex.artifact a
    JOIN spherex.plane p ON p.planeid = a.planeid
    JOIN spherex.observation o ON o.obsid = p.obsid
    WHERE a.uri = '{escaped}'
    """


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--science-uri", default=DEFAULT_SCIENCE_URI)
    parser.add_argument("--field-label", default="M101")
    parser.add_argument("--out", type=Path, default=Path("data/spherex_provenance_audit"))
    parser.add_argument("--max-total-bytes", type=int, default=450_000_000)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if args.max_total_bytes <= 0:
        parser.error("--max-total-bytes must be positive")

    started = datetime.now(timezone.utc).isoformat()
    args.out.mkdir(parents=True, exist_ok=True)
    sql_science = build_sql(args.science_uri)
    science_query = query_rows(sql_science)
    if science_query["row_count"] != 1:
        raise RuntimeError(
            f"Expected exactly one science artifact for the URI; got {science_query['row_count']}"
        )
    science = science_query["rows"][0]
    science_uri = str(science["science_uri"])
    science_plane_id = str(science["science_planeid"])
    science_detector = str(science.get("science_productid") or "")
    science_release = normalize_release(science_uri)
    if science_release not in {"DR1", "QR3"}:
        raise RuntimeError(f"Science release could not be identified from the native URI: {science_uri}")

    sql_inputs = (
        "SELECT inputid, outputid FROM spherex.provenance_input "
        f"WHERE outputid = '{safe_sql_string(science_plane_id)}'"
    )
    input_query = query_rows(sql_inputs)
    relations = input_query["rows"]
    if not relations:
        raise RuntimeError("IRSA returned no provenance_input rows for the selected science plane")

    provenance_records = []
    all_artifacts = []
    errors = []
    for relation in relations:
        input_id = str(relation.get("inputid") or "")
        output_id = str(relation.get("outputid") or "")
        if not input_id or output_id != science_plane_id:
            errors.append({"stage": "relation_validation", "relation": relation})
            continue
        sql_plane = (
            "SELECT planeid, obsid, productid, provenance_name, provenance_reference, "
            "provenance_version, provenance_project, provenance_producer, provenance_runid, "
            "provenance_lastexecuted, provenance_keywords, datarelease, calibrationlevel, "
            "dataproducttype, position_dimension_naxis1, position_dimension_naxis2 "
            "FROM spherex.plane "
            f"WHERE planeid = '{safe_sql_string(input_id)}'"
        )
        plane_query = query_rows(sql_plane)
        plane_rows = plane_query["rows"]
        if len(plane_rows) != 1:
            errors.append({
                "stage": "input_plane_lookup", "inputid": input_id,
                "row_count": len(plane_rows), "query": plane_query["query"],
            })
            continue
        plane = plane_rows[0]
        sql_artifact = (
            "SELECT planeid, artifactid, uri, producttype, releasetype, contenttype, "
            "contentlength, contentchecksum FROM spherex.artifact "
            f"WHERE planeid = '{safe_sql_string(input_id)}'"
        )
        artifact_query = query_rows(sql_artifact)
        artifacts = artifact_query["rows"]
        if not artifacts:
            errors.append({
                "stage": "input_artifact_lookup", "inputid": input_id,
                "row_count": 0, "query": artifact_query["query"],
            })
        provenance_records.append({
            "relation": relation,
            "input_plane": plane,
            "artifact_query": artifact_query,
        })
        for artifact in artifacts:
            product = {
                **artifact,
                "inputid": input_id,
                "outputid": output_id,
                "input_plane": plane,
                "family": calibration_family_from_uri(artifact.get("uri", "")),
                "release": normalize_release(str(artifact.get("uri") or "")),
                "detector": str(plane.get("productid") or ""),
                "provenance_relation_verified": output_id == science_plane_id,
            }
            all_artifacts.append(product)

    if errors:
        raise RuntimeError(
            "One or more provenance input planes or artifacts could not be resolved: "
            + json.dumps(errors[:10], default=str)
        )
    if not all_artifacts:
        raise RuntimeError("No archive artifacts were returned for the exact calibration input planes")

    # The Level-2 science MEF is itself part of the manifest and is retrieved
    # from its exact native URI, not a guessed directory listing.
    science_record = {
        "archive_id": science.get("science_artifactid"),
        "plane_id": science_plane_id,
        "observation_id": science.get("science_observationid") or science.get("observationid"),
        "uri": science_uri,
        "product_type": science.get("science_producttype"),
        "content_type": science.get("science_contenttype"),
        "content_length": science.get("science_contentlength"),
        "content_checksum": science.get("science_contentchecksum"),
        "release": science_release,
        "detector": science_detector,
        "pipeline_version": science.get("science_provenance_version"),
        "pipeline_name": science.get("science_provenance_name"),
        "processing_time": science.get("science_provenance_lastexecuted"),
        "observation_time": {
            "start_mjd": science.get("time_bounds_lower"),
            "end_mjd": science.get("time_bounds_upper"),
            "exposure_s": science.get("time_exposure"),
        },
    }
    science_name = Path(urlparse(normalize_archive_uri(science_uri)).path).name
    science_local = args.out / "science" / science_name
    remaining = int(args.max_total_bytes)
    downloaded_science = download_exact_product(
        science_uri, science_local,
        expected_bytes=science_record["content_length"],
        expected_checksum=science_record["content_checksum"],
        remaining_budget=remaining, timeout=args.timeout,
    )
    if downloaded_science["status"] != "downloaded":
        raise RuntimeError(f"Science MEF download failed: {downloaded_science}")
    remaining -= downloaded_science["byte_count"]
    downloaded_science["inspection"] = inspect_download(science_local, science_record["content_type"])
    science_record["download"] = downloaded_science

    calibration_products = []
    seen_uris = set()
    for index, product in enumerate(all_artifacts, start=1):
        uri = str(product.get("uri") or "")
        if not uri or uri in seen_uris:
            continue
        seen_uris.add(uri)
        if product.get("producttype") != "calibration":
            errors.append({"stage": "product_type", "uri": uri, "producttype": product.get("producttype")})
            continue
        if product.get("release") != science_release:
            errors.append({"stage": "release_mismatch", "uri": uri, "release": product.get("release")})
            continue
        if product.get("detector") not in {science_detector, "All"}:
            errors.append({"stage": "detector_mismatch", "uri": uri,
                           "detector": product.get("detector"), "science_detector": science_detector})
            continue
        basename = Path(urlparse(normalize_archive_uri(uri)).path).name
        family = product["family"]
        destination = args.out / "calibrations" / family / basename
        result = download_exact_product(
            uri, destination,
            expected_bytes=product.get("contentlength"),
            expected_checksum=product.get("contentchecksum"),
            remaining_budget=remaining, timeout=args.timeout,
        )
        if result["status"] == "downloaded":
            remaining -= result["byte_count"]
            result["inspection"] = inspect_download(destination, product.get("contenttype"))
        product.update({
            "download": result,
            "sha256": result.get("sha256"),
            "byte_count": result.get("byte_count"),
            "local_path": result.get("local_path"),
            "archive_checksum_status": (result.get("archive_checksum") or {}).get("status"),
        })
        calibration_products.append(product)

    direct_count = len(all_artifacts)
    downloaded_count = sum(
        row.get("download", {}).get("status") == "downloaded"
        for row in calibration_products
    )
    exact_relation_count = sum(
        bool(row.get("provenance_relation_verified"))
        for row in all_artifacts
    )
    detector_rows = [
        row for row in calibration_products
        if row.get("detector") not in {science_detector, "All"}
    ]
    failed_downloads = [
        row for row in calibration_products
        if row.get("download", {}).get("status") != "downloaded"
    ]

    from research_discovery.spherex.archive_manifest import (
        build_manifest, product_record, validate_manifest,
    )
    manifest_products = []
    science_manifest = product_record(
        product_type="level2_science_mef",
        native_uri=science_uri,
        archive_id=str(science_record["archive_id"]) if science_record["archive_id"] else None,
        release=science_release,
        detector=science_detector,
        observation_time=science_record["observation_time"],
        pipeline_version=science_record["pipeline_version"],
        processing_date=None,
        local_path=str(science_local),
        byte_count=downloaded_science["byte_count"],
        sha256=downloaded_science["sha256"],
        status="downloaded",
        compatibility_group=science_plane_id,
        compatibility_status="unassigned",
        notes="Exact SPHEREx science artifact selected by native URI and matched to TAP science plane metadata.",
    )
    science_manifest.update({
        "plane_id": science_plane_id,
        "artifact_content_checksum": science_record["content_checksum"],
        "pipeline_name": science_record["pipeline_name"],
        "pipeline_processing_time": science_record["processing_time"],
        "pipeline_version_exact": science_record["pipeline_version"],
        "archive_artifact_id": science_record["archive_id"],
    })
    manifest_products.append(science_manifest)

    for product in calibration_products:
        result = product.get("download") or {}
        if result.get("status") == "downloaded":
            manifest_status = "downloaded"
        elif result.get("status") == "failed":
            manifest_status = "failed"
        else:
            manifest_status = "discovered_not_downloaded"
        row = product_record(
            product_type=str(product.get("family") or "calibration"),
            native_uri=str(product.get("uri")),
            archive_id=str(product.get("artifactid")) if product.get("artifactid") else None,
            release=product.get("release"),
            detector=product.get("detector"),
            observation_time=None,
            pipeline_version=(product.get("input_plane") or {}).get("provenance_version"),
            processing_date=None,
            local_path=result.get("local_path"),
            byte_count=result.get("byte_count"),
            sha256=result.get("sha256"),
            status=manifest_status,
            compatibility_group=science_plane_id,
            compatibility_status="candidate_only",
            notes="Exact spherex.provenance_input relation to this science plane is recorded; independent reprocessing compatibility is not claimed.",
        )
        row.update({
            "plane_id": product.get("planeid"),
            "artifact_id": product.get("artifactid"),
            "content_type": product.get("contenttype"),
            "archive_content_length": product.get("contentlength"),
            "archive_content_checksum": product.get("contentchecksum"),
            "pipeline_input_id": product.get("inputid"),
            "pipeline_output_id": product.get("outputid"),
            "provenance_relation_verified": bool(product.get("provenance_relation_verified")),
            "pipeline_name": (product.get("input_plane") or {}).get("provenance_name"),
            "pipeline_version": (product.get("input_plane") or {}).get("provenance_version"),
            "pipeline_processing_time": (product.get("input_plane") or {}).get("provenance_lastexecuted"),
            "calibration_level": (product.get("input_plane") or {}).get("calibrationlevel"),
            "inspection": (result.get("inspection") or {}),
            "archive_checksum_status": (result.get("archive_checksum") or {}).get("status"),
        })
        manifest_products.append(row)

    manifest = build_manifest(
        archive="NASA/IPAC IRSA SPHEREx TAP and native IBE archive",
        query={
            "science_uri": science_uri,
            "science_plane_id": science_plane_id,
            "science_artifact_query": sql_science,
            "provenance_input_query": input_query["query"],
            "provenance_input_row_count": len(relations),
            "field_label": args.field_label,
        },
        products=manifest_products,
        processing_config={
            "method": "exact science plane -> provenance_input -> calibration plane -> artifact URI",
            "downloaded_bytes_limit": int(args.max_total_bytes),
            "checksum_policy": "verify archive MD5 or SHA256 when the TAP artifact checksum is supplied; record SHA256 for each downloaded local file",
            "calibration_compatibility": "direct pipeline input lineage is preserved; candidate_only remains until independent reprocessing audit",
            "level2_policy": "do not reapply Level-1 dark, read-noise, nonlinearity or gain corrections to already calibrated Level-2 IMAGE/VARIANCE products",
        },
        software=package_versions(),
        retrieved_utc=started,
    )
    manifest_path = args.out / "science_calibration_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    validation = validate_manifest(manifest, verify_local=True, base_dir=Path.cwd())
    validation_path = args.out / "science_calibration_manifest.validation.json"
    validation_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")

    # Query the separate D2 solid-angle map inventory. This is intentionally
    # reported as a related candidate unless the provenance table links it.
    solid_angle_sql = f"""
    SELECT a.artifactid, a.planeid, a.uri, a.producttype, a.releasetype,
      a.contenttype, a.contentlength, a.contentchecksum, p.productid
    FROM spherex.artifact a
    JOIN spherex.plane p ON p.planeid = a.planeid
    WHERE a.producttype = 'calibration'
      AND LOWER(a.uri) LIKE '%/{science_release.lower()}/solid_angle_pixel_map/%'
      AND LOWER(a.uri) LIKE '%/{science_detector[1:]}/%'
    """
    try:
        solid_angle_query = query_rows(solid_angle_sql)
    except Exception as exc:
        solid_angle_query = {"query": solid_angle_sql, "row_count": 0, "rows": [],
                             "error": f"{type(exc).__name__}: {exc}"}

    report = {
        "schema": SCHEMA,
        "created_utc": started,
        "field_label": args.field_label,
        "science": science_record,
        "science_download_inspection": downloaded_science.get("inspection"),
        "provenance": {
            "science_plane_id": science_plane_id,
            "direct_input_relation_count": len(relations),
            "verified_output_id_count": exact_relation_count,
            "input_planes_resolved": len(provenance_records),
            "input_artifacts_resolved": direct_count,
            "calibration_artifacts_downloaded": downloaded_count,
            "calibration_artifacts_failed": len(failed_downloads),
            "relation_semantics": "Each calibration plane was returned by spherex.provenance_input.inputid for this exact science planeid, and each file was then selected by that calibration planeid in spherex.artifact.",
        },
        "pipeline_versions": {
            "science_processing_pipeline": science_record["pipeline_version"],
            "calibration_input_pipeline_versions": sorted({
                str((row.get("input_plane") or {}).get("provenance_version"))
                for row in calibration_products
            }),
        },
        "calibration_products": calibration_products,
        "related_solid_angle_candidates": solid_angle_query,
        "manifest": {
            "path": str(manifest_path),
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "validation": validation,
        },
        "status": (
            "PROVENANCE_AND_BYTE_INTEGRITY_VALIDATED"
            if validation["valid"] and not failed_downloads and exact_relation_count == direct_count
            else "PARTIAL_OR_REVIEW_REQUIRED"
        ),
        "limitations": [
            "Direct provenance membership proves the listed calibration planes were recorded as inputs to this science plane's processing chain. It is not an independent reimplementation of the SPHEREx pipeline.",
            "The Level-2 science image and variance are already calibrated products. Level-1 detector correction maps must not be applied again to these Level-2 pixels.",
            "The separate solid-angle query is a related detector/release candidate unless the exact science provenance relation includes it.",
            "No Sky-Detector Twin performance result or blind benchmark is produced by this retrieval and audit.",
        ],
        "retrieval_errors": errors + failed_downloads,
    }
    report_path = args.out / "calibration_provenance_audit.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "science_plane_id": science_plane_id,
        "science_detector": science_detector,
        "direct_input_relations": len(relations),
        "resolved_calibration_artifacts": direct_count,
        "downloaded_calibration_artifacts": downloaded_count,
        "failed_calibration_artifacts": len(failed_downloads),
        "solid_angle_candidate_rows": solid_angle_query.get("row_count", 0),
        "manifest_validation": validation,
        "report": str(report_path),
    }, indent=2, default=str))
    if not validation["valid"] or failed_downloads or exact_relation_count != direct_count:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
