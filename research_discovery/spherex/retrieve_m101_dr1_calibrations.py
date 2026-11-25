#!/usr/bin/env python3
"""Download the original M101 DR1 D2 MEF and its release-specific D2 calibrations from IRSA's public S3 mirror.

The script verifies byte counts, FITS signatures, S3 ETags where they are single-part MD5
values, and SHA-256. It then runs the repository's native MEF structural/WCS audit and
tests the absolute-gain conversion path. It does not declare the calibration pair
scientifically compatible unless the repository's strict compatibility audit passes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import requests
from astropy.io import fits

from research_discovery.spherex.native_mef_audit import audit as audit_native_mef
from research_discovery.spherex.electron_conversion import derive_electrons_per_image_unit

BUCKET = "nasa-irsa-spherex"
REGION = "us-east-1"
S3_BASE = f"https://{BUCKET}.s3.{REGION}.amazonaws.com"
IRSA_BASE = "https://irsa.ipac.caltech.edu/ibe/data/spherex/"
OUT = Path("data/spherex_m101_dr1_d2_verified")

SCIENCE_KEY = (
    "dr1/level2/2025W19_2B/l2b-v27-2026-198/2/"
    "level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits"
)
CALIBRATIONS = {
    "spectral_wcs": "dr1/spectral_wcs/cal-swcs-v5-2026-191/2/",
    "solid_angle": "dr1/solid_angle_pixel_map/cal-sapm-v3-2026-191/2/",
    "absolute_gain": "dr1/abs_gain_matrix/cal-agm-v8-2026-191/2/",
}
SCIENCE_PLANE_ID = "01a0cf8b-7b99-7cbb-bacf-f0572e021e16"
SCIENCE_CONTENT_MD5 = "9fdc6dec669aad79cfdcc4d8dbc6306f"


def now():
    return datetime.now(timezone.utc).isoformat()


def md5_sha256(path: Path):
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            if not block:
                break
            size += len(block)
            md5.update(block)
            sha.update(block)
    return {"byte_count": size, "md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def list_prefix(session: requests.Session, prefix: str):
    params = {"list-type": "2", "prefix": prefix}
    url = S3_BASE + "/?" + urlencode(params)
    response = session.get(url, timeout=60)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    entries = []
    for node in root.findall("s3:Contents", ns):
        entries.append({
            "key": node.findtext("s3:Key", namespaces=ns),
            "size": int(node.findtext("s3:Size", namespaces=ns) or 0),
            "etag": (node.findtext("s3:ETag", namespaces=ns) or "").strip('"'),
            "last_modified": node.findtext("s3:LastModified", namespaces=ns),
        })
    if root.findtext("s3:IsTruncated", namespaces=ns) == "true":
        raise RuntimeError(f"S3 prefix listing was truncated; refusing incomplete selection: {prefix}")
    fits_entries = [x for x in entries if x["key"].lower().endswith((".fits", ".fits.gz"))]
    if len(fits_entries) != 1:
        raise RuntimeError(
            f"Expected exactly one FITS object under {prefix}, found {len(fits_entries)}: "
            f"{[x['key'] for x in fits_entries]}"
        )
    return url, fits_entries[0]


def download_object(session: requests.Session, key: str, metadata: dict, family: str):
    destination = OUT / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{S3_BASE}/{key}"
    expected_bytes = int(metadata["size"])
    expected_etag = str(metadata.get("etag") or "").lower()
    digest_md5 = hashlib.md5()
    digest_sha = hashlib.sha256()
    count = 0
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".part",
                                            dir=str(destination.parent))
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with session.get(url, stream=True, timeout=(30, 240)) as response:
            response.raise_for_status()
            response_length = response.headers.get("Content-Length")
            with temporary.open("wb") as handle:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        handle.write(block)
                        digest_md5.update(block)
                        digest_sha.update(block)
                        count += len(block)
                handle.flush()
                os.fsync(handle.fileno())
            if response_length and int(response_length) != count:
                raise IOError(f"HTTP Content-Length mismatch for {key}: {response_length} != {count}")
            http_headers = {
                "status_code": response.status_code,
                "content_length": response_length,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_type": response.headers.get("Content-Type"),
            }
        if count != expected_bytes:
            raise IOError(f"S3 byte count mismatch for {key}: {count} != {expected_bytes}")
        with temporary.open("rb") as handle:
            if handle.read(8) != b"SIMPLE  ":
                raise IOError(f"Downloaded object is not a primary FITS file: {key}")
        md5_value = digest_md5.hexdigest()
        sha_value = digest_sha.hexdigest()
        # Single-part S3 ETags are the MD5 of the object. Record a pass only
        # when the ETag has the expected 32-character form and matches bytes.
        etag_is_md5 = bool(re.fullmatch(r"[0-9a-f]{32}", expected_etag))
        etag_matches = bool(etag_is_md5 and md5_value == expected_etag)
        if etag_is_md5 and not etag_matches:
            raise IOError(f"S3 ETag/MD5 mismatch for {key}: {md5_value} != {expected_etag}")
        temporary.replace(destination)
        return {
            "family": family,
            "key": key,
            "s3_uri": url,
            "irsa_archive_uri": IRSA_BASE + key,
            "local_path": str(destination),
            "archive_size_bytes": expected_bytes,
            "downloaded_size_bytes": count,
            "s3_etag": expected_etag,
            "computed_md5": md5_value,
            "computed_sha256": sha_value,
            "etag_is_single_part_md5": etag_is_md5,
            "etag_md5_match": etag_matches if etag_is_md5 else None,
            "last_modified": metadata.get("last_modified"),
            "http": http_headers,
            "status": "downloaded_and_verified",
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def header_summary(path: Path):
    with fits.open(path, memmap=True, checksum=True) as hdul:
        result = {
            "hdu_count": len(hdul),
            "hdus": [],
            "primary_header": {},
        }
        keys = (
            "DETECTOR", "OBSID", "VERSION", "PROCDATE", "RELEASE",
            "DATE-OBS", "MJD-OBS", "EXPTIME", "TEXPTIME", "BUNIT",
            "WCSNAME", "WCSNAMEA", "CRPIX1A", "CRPIX2A",
            "CTYPE1", "CTYPE2", "CTYPE1A", "CTYPE2A",
        )
        result["primary_header"] = {k: hdul[0].header.get(k) for k in keys
                                    if hdul[0].header.get(k) is not None}
        for hdu in hdul:
            entry = {
                "name": str(hdu.name),
                "shape": list(hdu.data.shape) if hdu.data is not None else None,
                "bunit": hdu.header.get("BUNIT"),
                "detector": hdu.header.get("DETECTOR"),
                "version": hdu.header.get("VERSION"),
                "processing_date": hdu.header.get("PROCDATE"),
            }
            if "CHECKSUM" in hdu.header:
                entry["fits_checksum_result"] = hdu.verify_checksum()
            if "DATASUM" in hdu.header:
                entry["fits_datasum_result"] = hdu.verify_datasum()
            result["hdus"].append(entry)
        return result


def first_2d_hdu(path: Path):
    with fits.open(path, memmap=True, checksum=True) as hdul:
        for hdu in hdul:
            if hdu.data is not None and np.asarray(hdu.data).ndim == 2:
                return {
                    "name": str(hdu.name),
                    "shape": list(hdu.data.shape),
                    "bunit": hdu.header.get("BUNIT"),
                    "detector": hdu.header.get("DETECTOR", hdul[0].header.get("DETECTOR")),
                }
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Chronos-Sky-Twin/1.0 (reproducible archive audit)"})
    started = now()
    records = {}
    list_records = {}

    # The science object comes from the exact TAP-identified artifact and is
    # also revalidated against S3's independently exposed object metadata.
    science_prefix = SCIENCE_KEY
    science_list_url, science_object = list_prefix(session, science_prefix)
    if science_object["key"] != SCIENCE_KEY:
        raise RuntimeError(f"Exact science object mismatch: {science_object['key']}")
    if science_object["size"] != 64_800_000 or science_object["etag"].lower() != SCIENCE_CONTENT_MD5:
        raise RuntimeError("Science object metadata does not match the TAP-identified archive record")
    list_records["science"] = {"query_url": science_list_url, "object": science_object}
    records["science"] = download_object(session, SCIENCE_KEY, science_object, "science_mef")

    for family, prefix in CALIBRATIONS.items():
        listing_url, metadata = list_prefix(session, prefix)
        list_records[family] = {"query_url": listing_url, "prefix": prefix, "object": metadata}
        records[family] = download_object(session, metadata["key"], metadata, family)

    science_path = Path(records["science"]["local_path"])
    wcs_path = Path(records["spectral_wcs"]["local_path"])
    area_path = Path(records["solid_angle"]["local_path"])
    gain_path = Path(records["absolute_gain"]["local_path"])

    headers = {name: header_summary(Path(record["local_path"])) for name, record in records.items()}
    # Inspect the science/calibration files before invoking the strict native
    # MEF audit. This report distinguishes product identity from compatibility.
    audit = audit_native_mef(
        science_path, wcs_path,
        solid_angle_path=area_path,
        solid_angle_uri=records["solid_angle"]["irsa_archive_uri"],
        science_uri=records["science"]["irsa_archive_uri"],
        spectral_wcs_uri=records["spectral_wcs"]["irsa_archive_uri"],
    )
    audit_path = OUT / "native_mef_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest()

    # Absolute gain conversion is attempted only when the native MEF audit
    # confirms the science IMAGE and map are structurally valid.
    gain_validation = {
        "status": "not_attempted",
        "reason": "The native audit did not provide a usable science IMAGE footprint.",
    }
    if audit.get("image_shape") and audit.get("cutout_parent_origin_xy") is not None:
        science_hdu = next((x for x in headers["science"]["hdus"] if x["name"].upper() == "IMAGE"), None)
        gain_hdu = first_2d_hdu(gain_path)
        if science_hdu and gain_hdu:
            try:
                with fits.open(science_path, memmap=True) as hdul:
                    image_header = hdul["IMAGE"].header
                    exptime = image_header.get("EXPTIME", image_header.get("TEXPTIME"))
                    if exptime is None:
                        exptime = hdul[0].header.get("EXPTIME", hdul[0].header.get("TEXPTIME"))
                    science_unit = str(image_header.get("BUNIT", ""))
                gain_map = derive_electrons_per_image_unit(
                    calibration_path=gain_path,
                    expected_sha256=records["absolute_gain"]["computed_sha256"],
                    detector="D2",
                    calibration_bunit=str(gain_hdu.get("bunit") or ""),
                    exposure_time_s=float(exptime),
                    origin_xy=tuple(audit["cutout_parent_origin_xy"]),
                    image_shape=tuple(audit["image_shape"]),
                    science_image_unit=science_unit,
                )
                finite = np.isfinite(gain_map)
                gain_validation = {
                    "status": "conversion_map_derived",
                    "shape": list(gain_map.shape),
                    "finite_fraction": float(finite.mean()),
                    "positive_fraction": float((finite & (gain_map > 0)).mean()),
                    "minimum": float(np.nanmin(gain_map)) if finite.any() else None,
                    "maximum": float(np.nanmax(gain_map)) if finite.any() else None,
                    "units": "electrons per IMAGE unit per pixel",
                    "formula": "exposure_time_s / absolute_gain[(MJy/sr)/(e-/s)]",
                    "exposure_time_s": float(exptime),
                    "science_image_unit": science_unit,
                }
                np.save(OUT / "electrons_per_image_unit.npy", gain_map)
            except Exception as exc:
                gain_validation = {
                    "status": "review_required",
                    "error": f"{type(exc).__name__}: {exc}",
                    "gain_hdu": gain_hdu,
                }

    strict_metadata = {
        "science": {
            "release": "dr1",
            "archive_plane_id": SCIENCE_PLANE_ID,
            "detector": "D2",
            "filename_pipeline_version": "v27",
            "filename_processing_date": "2026-198",
        },
        "calibrations": {
            name: {
                "uri": record["irsa_archive_uri"],
                "s3_uri": record["s3_uri"],
                "sha256": record["computed_sha256"],
                "detector_from_hdu": first_2d_hdu(Path(record["local_path"])),
                "archive_release": "dr1",
            }
            for name, record in records.items() if name != "science"
        },
        "compatibility_status": "not_asserted",
        "reason": (
            "The audit verifies exact file bytes, FITS structure, native dimensions, "
            "CWAVE/CBAND, alternate WCS A and solid-angle identity. It does not infer "
            "pipeline compatibility solely from shared release, detector, or nearby "
            "processing dates. The archive's exact provenance-input relationship and "
            "the file-backed metadata checks remain the controlling evidence."
        ),
    }

    manifest = {
        "schema_version": "1.0",
        "created_utc": started,
        "finished_utc": now(),
        "archive": "NASA/IPAC IRSA SPHEREx DR1; official S3 mirror nasa-irsa-spherex, us-east-1",
        "field": {"name": "M101", "ra_deg": 210.80227, "dec_deg": 54.34895},
        "science_plane_id": SCIENCE_PLANE_ID,
        "bandpass": "SPHEREx-D2",
        "tap_query": (
            "SELECT a.uri, a.planeid, a.producttype, a.contentlength, a.contentchecksum, "
            "p.obsid, p.productid, p.time_bounds_lower, p.time_bounds_upper, p.time_exposure, "
            "p.energy_bandpassname FROM spherex.artifact a JOIN spherex.plane p "
            "ON p.planeid=a.planeid WHERE a.uri='<exact native Level-2 MEF URI>'"
        ),
        "s3_listing_method": "ListObjectsV2 prefix listing, detector directory, exactly one FITS object per product family",
        "directory_metadata": list_records,
        "products": records,
        "fits_headers": headers,
        "native_mef_audit": {
            "status": audit.get("status"),
            "report_path": str(audit_path),
            "report_sha256": audit_sha,
            "checks": audit.get("checks"),
            "calibration_compatibility": audit.get("calibration_compatibility"),
            "wavelength_authority": audit.get("wavelength_authority"),
            "science_claim_boundary": audit.get("science_claim_boundary"),
        },
        "absolute_gain_conversion": gain_validation,
        "strict_metadata_decision": strict_metadata,
        "scientific_boundary": (
            "This is an actual DR1 M101 D2 file-backed retrieval and native FITS audit. "
            "A detector-matched calibration release is not automatically an exposure-compatible "
            "calibration pair. Do not use this report to claim empirical performance, a blind "
            "benchmark, transient discovery or a YSO population result."
        ),
    }
    manifest_path = OUT / "real_field_calibration_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "products": {
            name: {
                "irsa_archive_uri": item["irsa_archive_uri"],
                "s3_uri": item["s3_uri"],
                "bytes": item["downloaded_size_bytes"],
                "md5": item["computed_md5"],
                "sha256": item["computed_sha256"],
                "etag_md5_match": item["etag_md5_match"],
            } for name, item in records.items()
        },
        "native_mef_audit_status": audit.get("status"),
        "native_mef_checks": audit.get("checks"),
        "gain_conversion_status": gain_validation.get("status"),
        "calibration_compatibility": "not_asserted",
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
