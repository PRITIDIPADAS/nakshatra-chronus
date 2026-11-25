#!/usr/bin/env python3
"""Pre-registered SPHEREx DR1 real-field calibration and injection/recovery preflight.

This is a deliberately limited real-image evaluation, not the four-method
CHRONOS benchmark, not a custodian-controlled blind run, and not a YSO discovery.
It retrieves one native D2 MEF per predeclared field, seeks an exact CWAVE/CBAND
and solid-angle calibration match, and only then runs a local SNR injection test.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from astropy.io import fits

from research_discovery.spherex.fetch_native_mefs import (
    Field, tap_query, download_native_mef, _safe_basename,
)
from research_discovery.spherex.discover_calibrations import find_products
from research_discovery.spherex.fetch_calibration import (
    download_calibration, archive_path_metadata,
)
from research_discovery.spherex.native_mef_audit import audit as audit_native
from research_discovery.spherex.calibration_compatibility import (
    compatibility_decision, level2_filename_metadata,
)
from research_discovery.spherex.archive_manifest import (
    build_manifest, product_record, validate_manifest,
)
from research_discovery.spherex.extract_epsf_stamp import extract as extract_epsf
from research_discovery.spherex.flag_policy import policy_mask
from research_discovery.validation.injection_recovery import run_injection_recovery

# Coordinates were fixed before this workflow runs. Each field is spatially
# separate and represents a known star-forming region / YSO research field.
FIELDS = (
    Field("RW_Aur_Taurus", 76.95625, 30.40139),
    Field("NGC_1333_Perseus", 52.29708, 31.31000),
    Field("OMC_1_Orion", 83.80833, -5.37333),
    Field("Rho_Oph", 246.77679, -24.69630),
    Field("Lupus_3", 242.12933, -39.08481),
)
RELEASE = "dr1"
BANDPASS = "SPHEREx-D2"
FLUX_LEVELS_IMAGE_SUM = (0.005, 0.015, 0.04)
N_INJECTIONS_PER_LEVEL = 20
SNR_THRESHOLD = 5.0
PSF_POSITION = (1020.25, 1019.75)
PSF_LOCAL_RADIUS = 100.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def jwrite(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")


def header_info(science_path: Path, table_row: dict) -> dict:
    filename = level2_filename_metadata(science_path)
    with fits.open(science_path, memmap=True) as hdul:
        image = hdul["IMAGE"]
        h = image.header
        primary = hdul[0].header
        detector = str(h.get("DETECTOR", filename.get("det", ""))).strip()
        version = str(h.get("VERSION", primary.get("VERSION", filename.get("version", ""))) or "").strip()
        process_date = str(h.get("PROCDATE", primary.get("PROCDATE", filename.get("date", ""))) or "").strip()
        obs_id = str(h.get("OBSID", primary.get("OBSID", ""))).strip() or None
        bunit = str(h.get("BUNIT", "")).strip()
        return {
            "detector": detector,
            "pipeline_version": version or None,
            "processing_date": process_date or None,
            "observation_id": obs_id,
            "image_unit": bunit,
            "shape": list(image.data.shape) if image.data is not None else None,
            "filename_metadata": filename,
            "archive_time_lower": table_row.get("time_bounds_lower"),
            "archive_time_upper": table_row.get("time_bounds_upper"),
        }


def download_pair_product(uri: str, *, kind: str, detector_number: int,
                          local_dir: Path, cache: dict) -> dict:
    if uri in cache:
        return cache[uri]
    filename = Path(urlparse(uri).path).name
    path = local_dir / kind / f"D{detector_number}" / filename
    result = download_calibration(
        uri, release=RELEASE, product=kind, detector=detector_number, out=path
    )
    if result.get("status") != "downloaded":
        raise RuntimeError(f"{kind} download failed: {result.get('error')}")
    cache[uri] = result
    return result


def enrich_audit_with_archive_identity(report: dict, science_info: dict,
                                       science_uri: str, wcs_uri: str,
                                       area_uri: str) -> dict:
    """Use only explicit SIA collection, native filename and archive-path tokens."""
    science_info_fields = report.get("spectral_wcs_metadata") or {}
    if not report.get("release") and f"/{RELEASE}/" in science_uri.lower():
        report["release"] = RELEASE
        report["science_release_basis"] = "SIA collection and exact native archive URI"
    if not report.get("science_detector"):
        report["science_detector"] = science_info.get("detector")
    if not report.get("science_pipeline_version"):
        report["science_pipeline_version"] = science_info.get("pipeline_version")
    if not report.get("science_processing_date"):
        report["science_processing_date"] = science_info.get("processing_date")

    path_meta = archive_path_metadata(wcs_uri)
    if not science_info_fields.get("release") and f"/{RELEASE}/" in wcs_uri.lower():
        science_info_fields["release"] = RELEASE
        science_info_fields["release_basis"] = "exact native calibration archive URI"
    if not science_info_fields.get("detector"):
        detector_match = re.search(r"/([1-6])/", urlparse(wcs_uri).path)
        if detector_match:
            science_info_fields["detector"] = f"D{detector_match.group(1)}"
            science_info_fields["detector_basis"] = "numeric detector directory in exact native calibration URI"
    if not science_info_fields.get("pipeline_version") and path_meta.get("product_version"):
        science_info_fields["pipeline_version"] = path_meta["product_version"]
        science_info_fields["pipeline_version_basis"] = "literal calibration product version token in archive path"
    if not science_info_fields.get("processing_date") and path_meta.get("processing_date"):
        science_info_fields["processing_date"] = path_meta["processing_date"]
        science_info_fields["processing_date_basis"] = "literal processing-date token in archive path"
    if science_info_fields.get("coordinate_frame") is None:
        science_info_fields["coordinate_frame"] = "native_detector" if (
            "CWAVE" in {x["name"].upper() for x in report.get("spectral_wcs_hdus", [])}
            and "CBAND" in {x["name"].upper() for x in report.get("spectral_wcs_hdus", [])}
            and report.get("wavelength_summary", {}).get("cwave_native_shape") == [2040, 2040]
            and report.get("wavelength_summary", {}).get("cband_native_shape") == [2040, 2040]
        ) else None
    report["spectral_wcs_metadata"] = science_info_fields
    report["archive_identity_basis"] = {
        "science": "native SIA/TAP URI plus parsed official Level-2 filename fields",
        "spectral_wcs": "native IRSA calibration URI plus FITS header and literal archive-path tokens",
        "solid_angle": "native IRSA calibration URI plus file SHA-256 and FITS header",
        "solid_angle_uri": area_uri,
    }
    return report


def try_compatible_pair(science_path: Path, science_uri: str, science_sha: str,
                        science_info: dict, root: Path, cache: dict,
                        field_name: str) -> dict:
    detector_number = int(str(science_info["detector"]).upper().replace("D", ""))
    processing_date = science_info.get("processing_date")
    if not processing_date:
        return {"status": "blocked", "reason": "Science MEF has no processing date in header or documented filename."}
    wcs_uris = find_products("spectral_wcs", detector_number, release=RELEASE,
                             processing_date=processing_date)
    area_uris = find_products("solid_angle", detector_number, release=RELEASE,
                              processing_date=processing_date)
    attempts = []
    if not wcs_uris or not area_uris:
        return {
            "status": "blocked",
            "reason": "No date-matched spectral-WCS and/or solid-angle calibration candidate was found.",
            "processing_date": processing_date,
            "spectral_wcs_candidates": len(wcs_uris),
            "solid_angle_candidates": len(area_uris),
        }

    for wi, wcs_uri in enumerate(wcs_uris[:3]):
        try:
            wcs = download_pair_product(wcs_uri, kind="spectral_wcs",
                                         detector_number=detector_number,
                                         local_dir=root / "calibration", cache=cache)
        except Exception as exc:
            attempts.append({"wcs_uri": wcs_uri, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for ai, area_uri in enumerate(area_uris[:3]):
            try:
                area = download_pair_product(area_uri, kind="solid_angle",
                                             detector_number=detector_number,
                                             local_dir=root / "calibration", cache=cache)
                audit_path = root / "reports" / field_name / f"native_audit_wcs{wi}_area{ai}.json"
                report = audit_native(
                    science_path, Path(wcs["local_path"]),
                    solid_angle_path=Path(area["local_path"]),
                    solid_angle_uri=area_uri,
                    science_uri=science_uri,
                    spectral_wcs_uri=wcs_uri,
                )
                report = enrich_audit_with_archive_identity(
                    report, science_info, science_uri, wcs_uri, area_uri
                )
                jwrite(audit_path, report)
                cal_info = report.get("spectral_wcs_metadata") or {}
                area_sha = area["sha256"]
                science_meta = {
                    "native_uri": science_uri, "sha256": science_sha,
                    "local_path": str(science_path), "release": report.get("release"),
                    "detector": report.get("science_detector"),
                    "pipeline_version": report.get("science_pipeline_version"),
                    "processing_date": report.get("science_processing_date"),
                    "coordinate_frame": report.get("coordinate_frame"),
                }
                calibration_meta = {
                    "native_uri": wcs_uri, "sha256": wcs["sha256"],
                    "local_path": wcs["local_path"], "release": cal_info.get("release"),
                    "detector": cal_info.get("detector"),
                    "pipeline_version": cal_info.get("pipeline_version"),
                    "processing_date": cal_info.get("processing_date"),
                    "coordinate_frame": cal_info.get("coordinate_frame"),
                    "wavelength_audit_path": str(audit_path),
                    "wavelength_audit_sha256": sha256(audit_path),
                    "solid_angle_map_uri": area_uri,
                    "solid_angle_map_sha256": area_sha,
                    "solid_angle_map_path": area["local_path"],
                }
                decision = compatibility_decision(science_meta, calibration_meta)
                attempt = {
                    "spectral_wcs_uri": wcs_uri, "solid_angle_uri": area_uri,
                    "decision": decision["status"],
                    "review_reasons": decision.get("audit", {}).get("review_reasons", [])[:12],
                    "direct_checks": decision.get("checks", {}),
                }
                attempts.append(attempt)
                if decision["status"] == "compatible":
                    return {
                        "status": "compatible", "science": science_meta,
                        "spectral_wcs": calibration_meta, "solid_angle": area,
                        "decision": decision, "audit_path": str(audit_path),
                    }
            except Exception as exc:
                attempts.append({
                    "wcs_uri": wcs_uri, "solid_angle_uri": area_uri,
                    "error": f"{type(exc).__name__}: {exc}",
                })
    return {
        "status": "not_compatible_or_review_required",
        "processing_date": processing_date,
        "spectral_wcs_candidates": len(wcs_uris),
        "solid_angle_candidates": len(area_uris),
        "attempts": attempts,
    }


def run_injection(science_path: Path, science_uri: str, science_sha: str,
                  compatible_pair: dict, root: Path, field_name: str,
                  field_index: int) -> dict:
    stamp_path = root / "reports" / field_name / "native_epsf_stamp.fits"
    epsf_meta = extract_epsf(
        science_path, x=PSF_POSITION[0], y=PSF_POSITION[1], out=stamp_path,
        stamp_size=11,
    )
    with fits.open(science_path, memmap=True) as science, fits.open(stamp_path) as stamp:
        image = np.asarray(science["IMAGE"].data, dtype=float)
        variance = np.asarray(science["VARIANCE"].data, dtype=float)
        flags = np.asarray(science["FLAGS"].data)
        background = np.asarray(science["ZODI"].data, dtype=float)
        psf = np.asarray(stamp[0].data, dtype=float)
    flag_bits, flag_names = policy_mask("conservative-photometry")
    result = run_injection_recovery(
        image, variance, flags, psf,
        flux_levels=list(FLUX_LEVELS_IMAGE_SUM),
        n_per_level=N_INJECTIONS_PER_LEVEL,
        snr_threshold=SNR_THRESHOLD,
        excluded_flag_bits=flag_bits,
        seed=20261125 + field_index,
        source_exclusion_radius=7,
        flux_unit="image_sum",
        psf_reference_xy=PSF_POSITION,
        psf_region_radius=PSF_LOCAL_RADIUS,
        background=background,
    )
    result["science_provenance"] = {
        "native_uri": science_uri, "sha256": science_sha,
        "calibration_compatibility": "compatible",
        "compatibility_group": compatible_pair["decision"].get("compatibility_group"),
        "native_audit_path": compatible_pair["audit_path"],
        "epsf_stamp_sha256": epsf_meta["output_sha256"],
    }
    result["flag_policy"] = {
        "name": "conservative-photometry",
        "excluded_flag_names": list(flag_names),
        "excluded_flag_mask": int(flag_bits),
    }
    result["limits"] = [
        "One native MEF per field: this is not a time-domain or all-sky performance estimate.",
        "This is one matched-filter SNR baseline, not the four-way CHRONOS benchmark.",
        "Injected flux is IMAGE-unit sum, not integrated Jy; no detector solid-angle conversion is claimed.",
        "Source Poisson noise is not simulated because no verified absolute-gain conversion was supplied.",
        "Completeness is conditional on the selected detector position, local ePSF, mask, ZODI model, flux levels and SNR threshold.",
        "Injections are visible to this workflow and are not a blind benchmark.",
    ]
    output = root / "reports" / field_name / "injection_recovery.json"
    jwrite(output, result)
    return {
        "status": "completed",
        "summary": result["flux_summary"],
        "new_unmatched_peak_summary": result["new_unmatched_peak_summary"],
        "n_baseline_detections": result["n_baseline_detections"],
        "output": str(output),
        "limits": result["limits"],
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/chronos5_real_preflight"))
    args = parser.parse_args()
    root = args.out.resolve()
    raw = root / "raw"
    reports = root / "reports"
    raw.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    product_records = []
    field_reports = []
    calibration_cache = {}
    seen_science_uris = set()

    for index, field in enumerate(FIELDS):
        item = {
            "field": {"name": field.name, "ra_deg": field.ra_deg, "dec_deg": field.dec_deg},
            "release": RELEASE, "bandpass": BANDPASS,
        }
        try:
            sql, table = tap_query(field, BANDPASS, release=RELEASE)
            qdir = raw / RELEASE / field.name
            qdir.mkdir(parents=True, exist_ok=True)
            table.write(qdir / "tap_results.csv", format="ascii.csv", overwrite=True)
            item["tap_row_count"] = len(table)
            item["tap_query"] = sql
            if len(table) == 0:
                item["status"] = "no_archive_rows"
                field_reports.append(item)
                continue
            selected = table[len(table) // 2]
            row = {str(k): str(selected[k]) for k in table.colnames}
            uri = str(selected["artifact_uri"])
            filename = _safe_basename(uri)
            science_path = qdir / filename
            if uri in seen_science_uris:
                item["status"] = "duplicate_science_uri"
                item["native_uri"] = uri
                field_reports.append(item)
                continue
            seen_science_uris.add(uri)
            downloaded = download_native_mef(uri, science_path)
            if downloaded.get("status") != "downloaded":
                item.update({"status": "science_download_failed", "download": downloaded})
                field_reports.append(item)
                continue
            info = header_info(science_path, row)
            item.update({
                "status": "science_downloaded",
                "native_uri": uri,
                "science_sha256": downloaded["sha256"],
                "science_bytes": downloaded["bytes"],
                "science_local_path": str(science_path),
                "science_metadata": info,
            })
            det_text = str(info.get("detector", "")).upper().replace("D", "")
            if det_text not in {"1", "2", "3", "4", "5", "6"}:
                item["calibration"] = {"status": "blocked", "reason": "Detector identity is absent or invalid."}
                field_reports.append(item)
                product_records.append(product_record(
                    product_type="level2_mef", native_uri=uri, status="downloaded",
                    release="DR1", detector=None, observation_time={
                        "start": row.get("time_bounds_lower"), "end": row.get("time_bounds_upper")},
                    pipeline_version=info.get("pipeline_version"), processing_date=info.get("processing_date"),
                    local_path=str(science_path), byte_count=downloaded["bytes"], sha256=downloaded["sha256"],
                    compatibility_status="review_required", notes="Science product retrieved; detector metadata unresolved."
                ))
                continue

            science_product = product_record(
                product_type="level2_mef", native_uri=uri, status="downloaded",
                release="DR1", detector=f"D{det_text}", observation_time={
                    "start": row.get("time_bounds_lower"), "end": row.get("time_bounds_upper")},
                pipeline_version=info.get("pipeline_version"), processing_date=info.get("processing_date"),
                local_path=str(science_path), byte_count=downloaded["bytes"], sha256=downloaded["sha256"],
                compatibility_status="candidate_only", notes="Native DR1 MEF; calibration match pending."
            )
            product_records.append(science_product)

            pair = try_compatible_pair(
                science_path, uri, downloaded["sha256"], info,
                root, calibration_cache, field.name,
            )
            item["calibration"] = {
                "status": pair["status"],
                "compatibility_group": pair.get("decision", {}).get("compatibility_group"),
                "audit_path": pair.get("audit_path"),
                "attempts": pair.get("attempts", []),
                "reason": pair.get("reason"),
            }
            if pair["status"] == "compatible":
                science_product["compatibility_status"] = "compatible"
                science_product["compatibility_group"] = pair["decision"].get("compatibility_group")
                for kind, cal_result in (
                    ("spectral_wcs", pair["spectral_wcs"]),
                    ("solid_angle", pair["solid_angle"]),
                ):
                    cal_uri = cal_result["native_uri"]
                    if not any(p.get("native_uri") == cal_uri for p in product_records):
                        product_records.append(product_record(
                            product_type=kind, native_uri=cal_uri, status="downloaded",
                            release="DR1", detector=f"D{det_text}",
                            pipeline_version=archive_path_metadata(cal_uri).get("product_version"),
                            processing_date=archive_path_metadata(cal_uri).get("processing_date"),
                            local_path=cal_result["local_path"], byte_count=cal_result["byte_count"],
                            sha256=cal_result["sha256"], compatibility_group=pair["decision"].get("compatibility_group"),
                            compatibility_status="compatible",
                            notes="Exact native calibration URI; compatibility decision passed file-backed audit."
                        ))
                try:
                    item["injection_recovery"] = run_injection(
                        science_path, uri, downloaded["sha256"], pair, root, field.name, index
                    )
                except Exception as exc:
                    item["injection_recovery"] = {
                        "status": "failed", "error": f"{type(exc).__name__}: {exc}"
                    }
            field_reports.append(item)
        except Exception as exc:
            item.update({"status": "field_query_or_processing_failed",
                         "error": f"{type(exc).__name__}: {exc}"})
            field_reports.append(item)

    manifest = build_manifest(
        archive="NASA/IPAC IRSA SPHEREx DR1",
        query={
            "retrieval": "IRSA TAP spherex.artifact JOIN spherex.plane",
            "release": RELEASE, "bandpass": BANDPASS,
            "fields_predeclared": [f.__dict__ for f in FIELDS],
        },
        products=product_records,
        processing_config={
            "workflow": "CHRONOS 5 calibration-compatible real-data preflight",
            "selection": "one median-time native MEF per predeclared field",
            "flux_levels_image_sum": list(FLUX_LEVELS_IMAGE_SUM),
            "n_injections_per_level": N_INJECTIONS_PER_LEVEL,
            "snr_threshold": SNR_THRESHOLD,
            "blind": False,
        },
    )
    manifest_path = reports / "archive_manifest.json"
    jwrite(manifest_path, manifest)
    manifest_validation = validate_manifest(
        manifest, verify_local=True, base_dir=Path.cwd()
    )
    jwrite(reports / "archive_manifest_validation.json", manifest_validation)

    compatible_fields = sum(
        x.get("calibration", {}).get("status") == "compatible" for x in field_reports
    )
    completed_injections = sum(
        x.get("injection_recovery", {}).get("status") == "completed" for x in field_reports
    )
    downloaded_fields = sum(x.get("status") == "science_downloaded" for x in field_reports)
    result = {
        "schema_version": "1.0",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": __import__("os").environ.get("GITHUB_SHA"),
        "data_release": RELEASE.upper(),
        "instrument_bandpass": BANDPASS,
        "predeclared_fields": [f.__dict__ for f in FIELDS],
        "counts": {
            "fields_queried": len(FIELDS),
            "fields_with_downloaded_science_mef": downloaded_fields,
            "fields_with_file_backed_compatible_calibration": compatible_fields,
            "fields_with_injection_recovery": completed_injections,
        },
        "field_results": field_reports,
        "archive_manifest": str(manifest_path),
        "archive_manifest_sha256": sha256(manifest_path),
        "archive_manifest_validation": manifest_validation,
        "acceptance_gates": {
            "calibration_compatible_real_data_pilot": "preliminary_pilot_completed_not_acceptance" if compatible_fields >= 1 and completed_injections >= 1 else "not_satisfied",
            "full_calibration_compatible_real_data_acceptance_gate": "not_satisfied: this pilot selects one exposure per field and runs a single-band matched-filter check; multi-epoch, multi-field selection-function and four-baseline validation remain required",
            "four_baseline_benchmark": "not_satisfied: this run evaluates the matched-filter SNR baseline only",
            "independently_controlled_blind_benchmark": "not_satisfied: external independent custody of the sealed truth catalogue is absent",
            "population_level_yso_discovery": "not_satisfied: this field preflight does not provide a complete selection function, population denominator, contamination audit or independent catalogue validation",
            "independent_astronomical_reproduction_or_researcher_review": "not_satisfied: no independent researcher has reviewed or reproduced these measurements",
            "validated_scientific_release": "not_satisfied: the empirical and independent-review gates above remain open",
        },
        "scientific_limits": [
            "A field with no archive product or no exact file-backed calibration pair is reported as blocked, not dropped silently.",
            "No QR2 products are mixed into this DR1 run.",
            "Scientific wavelengths are accepted only from the separate CWAVE/CBAND product, never WCS-WAVE.",
            "The injection test is a conditional single-band matched-filter evaluation, not the full four-baseline CHRONOS benchmark.",
            "Visible injection truth is not a blind benchmark, even if the injection seed is fixed.",
            "No YSO discovery is claimed from field locations or archive coverage alone.",
        ],
    }
    jwrite(reports / "run_report.json", result)
    print(json.dumps({
        "counts": result["counts"],
        "gates": result["acceptance_gates"],
        "manifest_valid": manifest_validation.get("valid"),
        "report": str(reports / "run_report.json"),
    }, indent=2))
    if not manifest_validation.get("valid"):
        raise SystemExit("Retrieved product manifest failed integrity validation; inspect report artifacts.")


if __name__ == "__main__":
    main()
