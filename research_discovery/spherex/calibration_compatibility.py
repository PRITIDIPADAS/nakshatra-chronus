"""Fail-closed science, spectral-WCS and pixel-area calibration compatibility."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


def _detector(value):
    if value is None:
        return None
    text = str(value).strip().upper()
    if text.startswith("DETECTOR"):
        text = text[len("DETECTOR"):]
    if text.startswith("D"):
        text = text[1:]
    return "D" + text if text in {"1","2","3","4","5","6"} else None


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def level2_filename_metadata(path):
    name = Path(path).name
    match = re.match(
        r"level2_(?P<obs>.+?)D(?P<det>[1-6])_spx_l2b-v(?P<version>[0-9.]+)-(?P<date>\d{4}-\d{3})\.fits$",
        name, re.I)
    return match.groupdict() if match else {}


def _audit_proof(science: Mapping[str, Any], calibration: Mapping[str, Any]):
    """Open and verify the audit JSON against the exact downloaded manifest products."""
    checks = {}
    path_value = calibration.get("wavelength_audit_path")
    expected_audit_sha = str(calibration.get("wavelength_audit_sha256", ""))
    if not path_value or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_audit_sha):
        return {"status": "review_required",
                "reason": "A local native-MEF audit JSON and its SHA-256 are required."}
    path = Path(str(path_value))
    if not path.is_file():
        return {"status": "review_required", "reason": f"Audit JSON is unavailable: {path}"}
    actual_audit_sha = _sha256(path)
    if actual_audit_sha.lower() != expected_audit_sha.lower():
        return {"status": "rejected", "reason": "Native-MEF audit JSON SHA-256 mismatch.",
                "actual_audit_sha256": actual_audit_sha}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "rejected", "reason": f"Native-MEF audit JSON cannot be parsed: {exc}"}

    pairs = (
        ("science_native_uri", science.get("native_uri"), report.get("science_native_uri")),
        ("science_sha256", science.get("sha256"), report.get("science_sha256")),
        ("spectral_wcs_native_uri", calibration.get("native_uri"), report.get("spectral_wcs_native_uri")),
        ("spectral_wcs_sha256", calibration.get("sha256"), report.get("spectral_wcs_sha256")),
    )
    for key, expected, actual in pairs:
        ok = bool(expected and actual and str(expected).lower() == str(actual).lower())
        checks[key] = {"status": "pass" if ok else "fail",
                       "expected": expected, "audit": actual}

    for label, local_path, expected_hash in (
        ("science_local_file", science.get("local_path"), science.get("sha256")),
        ("spectral_wcs_local_file", calibration.get("local_path"), calibration.get("sha256")),
        ("solid_angle_local_file", calibration.get("solid_angle_map_path"), calibration.get("solid_angle_map_sha256")),
    ):
        if not local_path or not expected_hash:
            checks[label] = {"status": "unknown", "reason": "local downloaded file path and manifest SHA-256 are required"}
        else:
            local = Path(str(local_path))
            if not local.is_file():
                checks[label] = {"status": "fail", "reason": f"local product file is missing: {local}"}
            else:
                actual_hash = _sha256(local)
                checks[label] = {"status": "pass" if actual_hash.lower() == str(expected_hash).lower() else "fail",
                                 "manifest_sha256": expected_hash, "local_sha256": actual_hash}
    
    science_meta = {
        "release": report.get("release"),
        "detector": report.get("science_detector"),
        "pipeline_version": report.get("science_pipeline_version"),
        "processing_date": report.get("science_processing_date"),
        "coordinate_frame": report.get("coordinate_frame"),
    }
    cal_meta = report.get("spectral_wcs_metadata") or {}
    for key in ("release", "detector", "pipeline_version", "processing_date", "coordinate_frame"):
        expected_science = science.get(key)
        actual_science = science_meta.get(key)
        if key == "detector":
            expected_science, actual_science = _detector(expected_science), _detector(actual_science)
        science_ok = bool(expected_science and actual_science and
                          str(expected_science).lower() == str(actual_science).lower())
        checks["science_" + key] = {"status": "pass" if science_ok else "fail",
                                    "manifest": expected_science, "audit": actual_science}

        expected_cal = calibration.get(key)
        actual_cal = cal_meta.get(key)
        if key == "detector":
            expected_cal, actual_cal = _detector(expected_cal), _detector(actual_cal)
        cal_ok = bool(expected_cal and actual_cal and
                      str(expected_cal).lower() == str(actual_cal).lower())
        checks["calibration_" + key] = {"status": "pass" if cal_ok else "fail",
                                        "manifest": expected_cal, "audit": actual_cal}

    audit_checks = report.get("checks") or {}
    required_audit_checks = (
        "required_hdus", "image_2d", "native_full_frame", "image_unit",
        "release_psf_family", "flags_integer_type", "celestial_wcs",
        "alternate_wcs_a", "cutout_parent_origin", "cwave_cband", "wavelength_units", "solid_angle",
        "variance_alignment", "zodi_alignment",
    )
    for key in required_audit_checks:
        item = audit_checks.get(key) or {}
        state = item.get("status")
        checks["audit_" + key] = {
            "status": "pass" if state == "pass" else "fail" if state == "fail" else "unknown",
            "audit_status": state,
        }

    flags = report.get("flags") or {}
    checks["audit_flags_dictionary"] = {
        "status": "pass" if flags.get("header_flag_dictionary_present") else "unknown",
        "present": bool(flags.get("header_flag_dictionary_present")),
    }
    wavelength = report.get("wavelength_summary") or {}
    checks["audit_wavelength_native_grid"] = {
        "status": "pass" if wavelength.get("cwave_native_shape") == [2040,2040]
                          and wavelength.get("cband_native_shape") == [2040,2040] else "fail",
        "cwave_native_shape": wavelength.get("cwave_native_shape"),
        "cband_native_shape": wavelength.get("cband_native_shape"),
    }

    area = report.get("solid_angle") or {}
    area_check = audit_checks.get("solid_angle") or {}
    checks["solid_angle_identity"] = {
        "status": "pass" if (
            area_check.get("status") == "pass" and
            area.get("status") == "pass" and
            area.get("uri") and calibration.get("solid_angle_map_uri") and
            area.get("uri") == calibration.get("solid_angle_map_uri") and
            area.get("sha256") and
            area.get("sha256") == calibration.get("solid_angle_map_sha256") and
            calibration.get("solid_angle_map_path") and
            Path(str(calibration.get("solid_angle_map_path"))).is_file() and
            _sha256(Path(str(calibration.get("solid_angle_map_path")))).lower() == str(area.get("sha256")).lower() and
            area.get("shape") == [2040,2040] and
            _detector(area.get("detector")) == _detector(science.get("detector")) and
            str(area.get("bunit","")).lower().replace(" ","") in {"sr","arcsec2","arcsec**2","arcsec^2"}
        ) else "fail",
        "audit_uri": area.get("uri"),
        "manifest_uri": calibration.get("solid_angle_map_uri"),
        "audit_sha256": area.get("sha256"),
        "manifest_sha256": calibration.get("solid_angle_map_sha256"),
    }

    state_values = [item["status"] for item in checks.values()]
    status = "rejected" if "fail" in state_values else (
        "compatible" if all(value == "pass" for value in state_values) else "review_required")
    return {
        "status": status,
        "audit_path": str(path),
        "audit_sha256": actual_audit_sha,
        "checks": checks,
        "science_audit_metadata": science_meta,
        "calibration_audit_metadata": cal_meta,
        "solid_angle_uri": area.get("uri"),
        "warning": "This is metadata and file-integrity compatibility, not proof of empirical detector performance.",
        "review_reasons": [
            {"check": name, "status": item.get("status"), "reason": item.get("reason")}
            for name, item in checks.items() if item.get("status") != "pass"
        ],
    }


def compatibility_decision(science: Mapping[str, Any], calibration: Mapping[str, Any],
                           *, required_frame="native_detector"):
    """Return compatible only from explicit metadata plus a checksum-verified real-file audit."""
    checks = {}
    pairs = (
        ("release", "release"),
        ("detector", "detector"),
        ("pipeline_version", "pipeline_version"),
        ("processing_date", "processing_date"),
        ("coordinate_frame", "coordinate_frame"),
    )
    for science_key, calibration_key in pairs:
        left = science.get(science_key)
        right = calibration.get(calibration_key)
        if science_key == "detector":
            left, right = _detector(left), _detector(right)
        if not left or not right:
            checks[science_key] = {"status": "unknown", "science": left, "calibration": right}
        else:
            checks[science_key] = {
                "status": "pass" if str(left).lower() == str(right).lower() else "fail",
                "science": left, "calibration": right,
            }
    if checks["coordinate_frame"]["status"] == "pass" and str(
        checks["coordinate_frame"]["science"]).lower() != required_frame.lower():
        checks["coordinate_frame"]["status"] = "fail"

    audit = _audit_proof(science, calibration)
    audit_state = "fail" if audit["status"] == "rejected" else audit["status"]
    checks["native_mef_audit"] = {"status": audit_state, "audit_status": audit["status"],
                                  "audit_sha256": audit.get("audit_sha256"),
                                  "reason": audit.get("reason")}
    checks["audit_details"] = audit.get("checks", {})
    states = [value["status"] for value in checks.values() if isinstance(value, dict) and "status" in value]
    audit_detail_states = [value["status"] for value in audit.get("checks", {}).values()]
    all_states = states + audit_detail_states
    status = "rejected" if "fail" in all_states else (
        "compatible" if audit["status"] == "compatible" and all(
            value == "pass" for value in all_states) else "review_required")
    return {
        "status": status,
        "checks": checks,
        "compatibility_group": (
            f"{science.get('release')}:{_detector(science.get('detector'))}:"
            f"{science.get('pipeline_version')}:{science.get('processing_date')}"
            if status == "compatible" else None),
        "solid_angle_uri": audit.get("solid_angle_uri"),
        "wavelength_source": "separate spectral-WCS calibration CWAVE/CBAND only",
        "audit": audit,
        "warning": "WCS-WAVE, filename similarity, array shape alone, or operator-entered hashes do not prove calibration compatibility.",
    }
