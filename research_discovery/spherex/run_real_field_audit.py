#!/usr/bin/env python3
"""Retrieve one real SPHEREx field and audit detector-matched public calibrations.

This is a retrieval and structural audit, not a claim of complete scientific
calibration compatibility. Product identity, archive URIs, byte counts and
SHA-256 values are retained for every downloaded file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from astropy.io import fits
from astroquery.ipac.irsa import Irsa

from research_discovery.spherex.fetch_native_mefs import Field, run as fetch_native, download_native_mef
from research_discovery.spherex.discover_calibrations import find_products
from research_discovery.spherex.fetch_calibration import download_calibration
from research_discovery.spherex.native_mef_audit import audit as audit_native_mef
from research_discovery.spherex.extract_epsf_stamp import extract as extract_epsf
from research_discovery.spherex.flag_policy import policy_mask
from research_discovery.validation.injection_recovery import run_injection_recovery


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"none", "nan", "masked"} else None


def normal_detector(value):
    value = clean(value)
    if not value:
        return None
    value = value.upper().replace("DETECTOR", "").strip()
    if value.startswith("D"):
        value = value[1:]
    return f"D{value}" if value in {"1", "2", "3", "4", "5", "6"} else None


def path_tokens(uri: str):
    path = urlparse(uri).path
    version = re.search(r"(?:cal-[a-z]+-)?v([0-9]+(?:\.[0-9]+)*)", path, re.I)
    date = re.search(r"(20\d{2}-\d{3})", path)
    return {
        "archive_product_version": version.group(1) if version else None,
        "archive_processing_date": date.group(1) if date else None,
    }


def header_record(path: Path, family: str, uri: str):
    with fits.open(path, memmap=True, checksum=True) as hdul:
        names = [str(h.name).upper() for h in hdul]
        if family == "spectral_wcs":
            chosen = [hdul[n] for n in ("CWAVE", "CBAND") if n in names]
            shape = list(chosen[0].data.shape) if chosen and chosen[0].data is not None else None
            units = {h.name: clean(h.header.get("BUNIT")) for h in chosen}
            detector_values = [clean(h.header.get("DETECTOR")) for h in chosen]
        else:
            chosen = next((h for h in hdul if h.data is not None and np.asarray(h.data).ndim == 2), None)
            shape = list(chosen.data.shape) if chosen is not None else None
            units = {chosen.name: clean(chosen.header.get("BUNIT"))} if chosen is not None else {}
            detector_values = [clean(chosen.header.get("DETECTOR"))] if chosen is not None else []
        primary = hdul[0].header
        first_header = chosen[0].header if isinstance(chosen, list) and chosen else (
            chosen.header if chosen is not None else primary)
        det = next((normal_detector(x) for x in detector_values if normal_detector(x)), None)
        det = det or normal_detector(first_header.get("DETECTOR")) or normal_detector(primary.get("DETECTOR"))
        return {
            "family": family,
            "uri": uri,
            "local_path": str(path),
            "sha256": sha256(path),
            "byte_count": path.stat().st_size,
            "hdus": [{"name": h.name, "shape": list(h.data.shape) if h.data is not None else None,
                      "bunit": clean(h.header.get("BUNIT"))} for h in hdul],
            "detector": det,
            "release_from_uri": "dr1" if "/dr1/" in urlparse(uri).path.lower() else "qr3",
            "header_version": clean(first_header.get("VERSION", primary.get("VERSION"))),
            "header_processing_date": clean(first_header.get("PROCDATE", primary.get("PROCDATE"))),
            "bunit_by_hdu": units,
            **path_tokens(uri),
        }


def science_record(path: Path, uri: str):
    with fits.open(path, memmap=True, checksum=True) as hdul:
        names = [str(h.name).upper() for h in hdul]
        image = hdul[names.index("IMAGE")]
        primary = hdul[0].header
        h = image.header
        return {
            "family": "science_mef",
            "uri": uri,
            "local_path": str(path),
            "sha256": sha256(path),
            "byte_count": path.stat().st_size,
            "release": "dr1" if "/dr1/" in urlparse(uri).path.lower() else "qr3",
            "detector": normal_detector(h.get("DETECTOR", primary.get("DETECTOR"))),
            "pipeline_version": clean(h.get("VERSION", primary.get("VERSION"))),
            "processing_date": clean(h.get("PROCDATE", primary.get("PROCDATE"))),
            "observation_id": clean(h.get("OBSID", primary.get("OBSID"))),
            "date_obs": clean(h.get("DATE-OBS", primary.get("DATE-OBS"))),
            "mjd_obs": clean(h.get("MJD-OBS", primary.get("MJD-OBS"))),
            "exposure_time_s": clean(h.get("EXPTIME", h.get("TEXPTIME", primary.get("EXPTIME")))),
            "image_shape": list(image.data.shape) if image.data is not None else None,
            "image_bunit": clean(h.get("BUNIT")),
            "science_hdus": names,
        }


def normalise_irsa_uri(value: str) -> str:
    value = str(value).strip()
    if value.startswith("https://"):
        return value
    return "https://irsa.ipac.caltech.edu/" + value.lstrip("/")


def tap_rows(query: str) -> list[dict]:
    result = Irsa.query_tap(query)
    table = result.to_table() if hasattr(result, "to_table") else result
    rows = []
    for row in table:
        item = {}
        for name in table.colnames:
            value = row[name]
            if getattr(value, "mask", False):
                value = None
            elif hasattr(value, "item"):
                try:
                    value = value.item()
                except Exception:
                    value = str(value)
            else:
                value = str(value)
            item[name] = value
        rows.append(item)
    return rows


def resolve_archive_provenance(science_uri: str) -> dict:
    """Resolve exact input calibration artifacts through IRSA's foreign-key table."""
    uri_value = urlparse(science_uri).path.lstrip("/").replace("'", "''")
    q1 = (
        "SELECT a.uri, a.planeid, a.producttype, a.contentlength, a.contentchecksum, "
        "p.provenance_version, p.provenance_name, p.time_exposure, "
        "p.energy_bandpassname, p.position_dimension_naxis1, p.position_dimension_naxis2 "
        "FROM spherex.artifact a JOIN spherex.plane p ON p.planeid = a.planeid "
        f"WHERE a.uri = '{uri_value}'"
    )
    science_rows = tap_rows(q1)
    if len(science_rows) != 1:
        raise RuntimeError(
            f"Expected exactly one science artifact metadata row for {science_uri}; got {len(science_rows)}"
        )
    science_row = science_rows[0]
    science_planeid = str(science_row["planeid"])
    q2 = (
        "SELECT inputid, outputid FROM spherex.provenance_input "
        f"WHERE outputid = '{science_planeid}'"
    )
    relations = tap_rows(q2)
    artifacts = []
    queries = [{"query": q1, "rows": science_rows}, {"query": q2, "rows": relations}]
    for relation in relations:
        input_id = str(relation["inputid"])
        q3 = (
            "SELECT planeid, artifactid, uri, producttype, releasetype, "
            "contenttype, contentlength, contentchecksum "
            "FROM spherex.artifact "
            f"WHERE planeid = '{input_id}'"
        )
        rows = tap_rows(q3)
        queries.append({"query": q3, "rows": rows})
        artifacts.extend(rows)
    query_digest = hashlib.sha256(
        json.dumps(queries, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "science": science_row,
        "science_planeid": science_planeid,
        "input_relations": relations,
        "calibration_artifacts": artifacts,
        "query_records": queries,
        "query_sha256": query_digest,
        "source": "NASA/IPAC IRSA TAP: spherex.provenance_input",
        "status": "resolved" if relations and artifacts else "no_linked_calibration_inputs",
    }


def provenance_link_for_uri(provenance: dict, science_uri: str, calibration_uri: str,
                           local_path: Path | None = None) -> dict | None:
    target = normalise_irsa_uri(calibration_uri)
    matches = [
        item for item in provenance.get("calibration_artifacts", [])
        if normalise_irsa_uri(item.get("uri", "")) == target
        and str(item.get("producttype", "")).lower() == "calibration"
    ]
    if len(matches) != 1:
        return None
    artifact = matches[0]
    archive_checksum = str(artifact.get("contentchecksum") or "").strip().lower()
    md5_expected = archive_checksum.split(":", 1)[1] if archive_checksum.startswith("md5:") else None
    md5_actual = md5_file(local_path) if local_path and Path(local_path).is_file() else None
    md5_status = (
        "pass" if md5_expected and md5_actual and md5_expected == md5_actual.lower()
        else "not_checked" if not local_path or not md5_expected
        else "fail"
    )
    if md5_status == "fail":
        return None
    plane_id = str(artifact.get("planeid") or "")
    relations = [
        row for row in provenance.get("input_relations", [])
        if str(row.get("inputid")) == plane_id
        and str(row.get("outputid")) == str(provenance.get("science_planeid"))
    ]
    if len(relations) != 1:
        return None
    relation = relations[0]
    return {
        "input_table": "spherex.provenance_input",
        "science_planeid": str(provenance["science_planeid"]),
        "calibration_planeid": plane_id,
        "inputid": str(relation["inputid"]),
        "outputid": str(relation["outputid"]),
        "artifact_planeid": str(artifact.get("planeid")),
        "science_native_uri": science_uri,
        "calibration_native_uri": normalise_irsa_uri(calibration_uri),
        "calibration_producttype": artifact.get("producttype"),
        "calibration_contentchecksum": artifact.get("contentchecksum"),
        "artifact_md5_expected": md5_expected,
        "artifact_md5_actual": md5_actual,
        "artifact_md5_status": md5_status,
        "calibration_sha256": sha256(local_path) if local_path and Path(local_path).is_file() else None,
        "query_sha256": provenance["query_sha256"],
        "status": "verified_from_live_irsa_foreign_key_query",
    }


def run_calibrated_jy_injection(science_path: Path, science_uri: str,
                                area_path: Path, area_uri: str,
                                science_sha: str, area_sha: str,
                                out_dir: Path) -> dict:
    """Run deterministic Jy injections on one real DR1 MEF using native ePSF and pixel solid angle."""
    x_ref, y_ref = 1020.25, 1019.75
    stamp_path = out_dir / "native_epsf_stamp.fits"
    epsf_meta = extract_epsf(
        science_path, x=x_ref, y=y_ref, out=stamp_path, stamp_size=11
    )
    with fits.open(science_path, memmap=True) as science, fits.open(stamp_path) as psf_file, fits.open(area_path, memmap=True) as area_file:
        image = np.asarray(science["IMAGE"].data, dtype=float)
        variance = np.asarray(science["VARIANCE"].data, dtype=float)
        flags = np.asarray(science["FLAGS"].data)
        background = np.asarray(science["ZODI"].data, dtype=float)
        psf = np.asarray(psf_file[0].data, dtype=float)
        area_hdu = next(h for h in area_file if h.data is not None and np.asarray(h.data).ndim == 2)
        area_values = np.asarray(area_hdu.data, dtype=float)
        area_unit = str(area_hdu.header.get("BUNIT", "")).strip().lower().replace(" ", "")
        if area_unit in {"arcsec2", "arcsec**2", "arcsec^2"}:
            # 1 arcsec = pi/(180*3600) radians; square for pixel solid angle.
            omega_sr = area_values * (np.pi / (180.0 * 3600.0)) ** 2
        elif area_unit in {"sr", "steradian", "steradians"}:
            omega_sr = area_values
        else:
            raise ValueError(
                f"Solid-angle calibration must be in arcsec^2 or sr; received {area_hdu.header.get('BUNIT')!r}"
            )
        if image.shape != variance.shape or image.shape != flags.shape or image.shape != omega_sr.shape:
            raise ValueError("IMAGE, VARIANCE, FLAGS and solid-angle map must be pixel-aligned")

    flag_bits, flag_names = policy_mask("conservative-photometry")
    half = psf.shape[0] // 2
    x0, y0 = int(np.floor(x_ref)) - half, int(np.floor(y_ref)) - half
    sl = (slice(y0, y0 + psf.shape[0]), slice(x0, x0 + psf.shape[1]))
    local_var = variance[sl]
    local_omega = omega_sr[sl]
    local_flags = flags[sl].astype(np.uint64)
    good = (
        np.isfinite(local_var) & (local_var > 0)
        & np.isfinite(local_omega) & (local_omega > 0)
        & ((local_flags & np.uint64(flag_bits)) == 0)
    )
    if not good.all():
        raise ValueError("Reference PSF footprint touches invalid variance, solid-angle or flagged pixels")
    # In MJy/sr pixels the point-source template is ePSF / pixel-solid-angle.
    # Use that same template both for the local inverse-variance depth estimate
    # and for the SNR filter, rather than filtering surface brightness with a
    # flux-normalized ePSF alone.
    detection_template = psf / local_omega
    matched_filter_information = float(np.sum((detection_template ** 2) / local_var))
    if not np.isfinite(matched_filter_information) or matched_filter_information <= 0:
        raise ValueError("Could not derive local matched-filter flux sensitivity from the calibrated maps")
    five_sigma_jy = 5.0 / (1e-6 * np.sqrt(matched_filter_information))
    levels_jy = [0.5 * five_sigma_jy, five_sigma_jy, 2.0 * five_sigma_jy]
    result = run_injection_recovery(
        image, variance, flags, psf,
        flux_levels=levels_jy, n_per_level=20, snr_threshold=5.0,
        excluded_flag_bits=flag_bits, seed=20261125,
        min_injection_separation=16, source_exclusion_radius=7,
        solid_angle_sr_map=omega_sr, flux_unit="Jy",
        psf_reference_xy=(x_ref, y_ref), psf_region_radius=100.0,
        background=background, detection_psf=detection_template,
    )
    result["evaluation_type"] = "calibration-compatible real-data single-exposure injection recovery"
    result["calibrated_flux_definition"] = "Integrated source flux density in Jy; IMAGE is MJy/sr and pixel solid angle is converted from arcsec^2 to sr."
    result["local_reference_5sigma_sensitivity_jy"] = five_sigma_jy
    result["local_reference_1sigma_flux_uncertainty_jy"] = five_sigma_jy / 5.0
    result["local_matched_filter_information_jy_inverse2"] = matched_filter_information / (1.0e-12)
    result["local_psf_footprint_solid_angle_fractional_range"] = float(
        (np.max(local_omega) - np.min(local_omega)) / np.median(local_omega)
    )
    result["injection_flux_levels_jy"] = levels_jy
    result["science_provenance"] = {
        "science_native_uri": science_uri, "science_sha256": science_sha,
        "solid_angle_native_uri": area_uri, "solid_angle_sha256": area_sha,
        "epsf_extraction": epsf_meta,
    }
    result["flag_policy"] = {"name": "conservative-photometry", "excluded_flag_names": list(flag_names), "excluded_flag_mask": int(flag_bits)}
    result["limits"] = [
        "One real M101 D2 DR1 exposure; this is not a multi-field or time-domain benchmark.",
        "Deterministic injected source signals are added to the measured real image; source Poisson noise is not added because an independently signed electron-conversion record is absent.",
        "The injected sources are visible to this evaluation and the seed is not held by an independent custodian; this is not a blind benchmark.",
        "Sensitivity is computed locally from the observed VARIANCE, native ePSF and detector pixel solid-angle map.",
        "This run evaluates the matched-filter SNR baseline only, not the complete four-baseline CHRONOS comparison.",
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "calibrated_jy_injection_recovery.json"
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return {
        "status": "completed", "output": str(output),
        "five_sigma_sensitivity_jy": five_sigma_jy,
        "flux_levels_jy": levels_jy,
        "flux_summary": result.get("flux_summary"),
        "new_unmatched_peak_summary": result.get("new_unmatched_peak_summary"),
        "n_baseline_detections": result.get("n_baseline_detections"),
        "psf_sha256": epsf_meta.get("output_sha256"),
        "limitations": result["limits"],
    }


def candidate_sort_key(uri: str, wanted_date: str | None):
    tokens = path_tokens(uri)
    date = tokens["archive_processing_date"] or ""
    exact = bool(wanted_date and date == wanted_date)
    return (exact, date, tokens["archive_product_version"] or "")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--field", default="M101,210.80227,54.34895")
    p.add_argument("--science-uri", default=None,
                   help="Optional exact native DR1/QR3 Level-2 URI; bypasses field-level science selection")
    p.add_argument("--bandpass", default="SPHEREx-D2")
    p.add_argument("--release", choices=("dr1", "qr3"), default="dr1")
    p.add_argument("--limit-per-family", type=int, default=5)
    p.add_argument("--out", type=Path, default=Path("data/spherex_m101_audit"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    field_parts = args.field.split(",")
    if len(field_parts) != 3:
        p.error("--field must be NAME,RA_DEG,DEC_DEG")
    field = Field(field_parts[0].strip(), float(field_parts[1]), float(field_parts[2]))

    if args.science_uri:
        science_uri = normalise_irsa_uri(args.science_uri)
        science_name = Path(urlparse(science_uri).path).name
        science_path = args.out / "science" / science_name
        science_download = download_native_mef(science_uri, science_path)
        if science_download.get("status") != "downloaded":
            raise RuntimeError(f"Exact native science MEF download failed: {science_download}")
        inventory = {
            "field_results": [{
                "query": "Exact science URI selected by explicit --science-uri; TAP provenance metadata follows.",
                "tap_row_count": 1,
                "downloads": [science_download],
            }]
        }
    else:
        inventory = fetch_native([field], args.bandpass, args.out / "science",
                                 limit_per_field=1, download=True, release=args.release)
        downloads = [x for f in inventory["field_results"] for x in f["downloads"]
                     if x.get("status") == "downloaded"]
        if not downloads:
            raise RuntimeError("IRSA TAP returned no downloadable native science MEF for this field/bandpass")
        science_dl = downloads[0]
        science_path = Path(science_dl["local_path"])
        science_uri = science_dl.get("source_url") or science_dl.get("artifact_uri")
    science = science_record(science_path, science_uri)
    if science["detector"] is None:
        raise RuntimeError("Downloaded science IMAGE HDU has no usable DETECTOR identity")
    provenance = resolve_archive_provenance(science_uri)
    expected_science_md5 = str(provenance["science"].get("contentchecksum") or "").lower()
    actual_science_md5 = md5_file(science_path)
    if not expected_science_md5.startswith("md5:") or actual_science_md5 != expected_science_md5.split(":", 1)[1]:
        raise RuntimeError("Science MEF MD5 does not match the exact IRSA artifact checksum")
    if provenance["science"].get("contentlength") and science_path.stat().st_size != int(provenance["science"]["contentlength"]):
        raise RuntimeError("Science MEF byte count does not match the exact IRSA artifact record")
    science["archive_planeid"] = provenance["science_planeid"]
    science["processing_date"] = science["processing_date"] or (
        re.search(r"-v[0-9.]+-(20[0-9]{2}-[0-9]{3})\.fits$", science_path.name, re.I).group(1)
        if re.search(r"-v[0-9.]+-(20[0-9]{2}-[0-9]{3})\\.fits$", science_path.name, re.I) else None
    )
    science["exposure_time_s"] = provenance["science"].get("time_exposure")
    detector_number = int(science["detector"][1:])

    families = {
        "spectral_wcs": ("spectral_wcs", "spectral_wcs"),
        "solid_angle": ("solid_angle", "solid_angle"),
        "absolute_gain": ("gain", "abs_gain_matrix"),
    }
    calibration_records = []
    candidate_lists = {}
    for family, (discovery_name, download_name) in families.items():
        urls = find_products(discovery_name, detector_number, release=args.release)
        urls = [u for u in urls if f"/{detector_number}/" in urlparse(u).path]
        urls = sorted(urls, key=lambda u: candidate_sort_key(u, science.get("processing_date")), reverse=True)
        candidate_lists[family] = urls
        selected = urls[:max(1, args.limit_per_family)]
        family_dir = args.out / "calibrations" / family
        for index, uri in enumerate(selected, start=1):
            basename = Path(urlparse(uri).path).name
            destination = family_dir / basename
            record = download_calibration(uri, release=args.release, product=download_name,
                                          detector=detector_number, out=destination)
            if record["status"] == "downloaded":
                probe = header_record(destination, family, uri)
                probe["retrieval_status"] = "downloaded"
                probe["candidate_rank"] = index
                probe["same_processing_date_as_science_filename"] = (
                    bool(science.get("processing_date")) and
                    path_tokens(uri)["archive_processing_date"] == science.get("processing_date"))
                calibration_records.append(probe)
            else:
                calibration_records.append({
                    "family": family, "uri": uri, "retrieval_status": record["status"],
                    "error": record.get("error"), "candidate_rank": index,
                })

    def valid_candidate(family):
        valid = []
        for row in calibration_records:
            if row.get("family") != family or row.get("retrieval_status") != "downloaded":
                continue
            if row.get("detector") != science.get("detector"):
                continue
            if family == "spectral_wcs":
                hdus = {x["name"].upper(): x for x in row.get("hdus", [])}
                if not all(k in hdus and hdus[k].get("shape") == [2040, 2040] for k in ("CWAVE", "CBAND")):
                    continue
            else:
                if row.get("hdus") is None or not any(x.get("shape") == [2040, 2040] for x in row["hdus"]):
                    continue
            valid.append(row)
        valid.sort(key=lambda r: (r.get("same_processing_date_as_science_filename", False),
                                  r.get("archive_processing_date") or ""), reverse=True)
        return valid

    wcs_candidates = valid_candidate("spectral_wcs")
    area_candidates = valid_candidate("solid_angle")
    gain_candidates = valid_candidate("absolute_gain")
    chosen_wcs = wcs_candidates[0] if wcs_candidates else None
    chosen_area = area_candidates[0] if area_candidates else None
    chosen_gain = gain_candidates[0] if gain_candidates else None

    audit_report = None
    provenance_links = {}
    if chosen_wcs:
        provenance_links["spectral_wcs"] = provenance_link_for_uri(provenance, science_uri, chosen_wcs["uri"], Path(chosen_wcs["local_path"]))
    if chosen_gain:
        provenance_links["absolute_gain"] = provenance_link_for_uri(provenance, science_uri, chosen_gain["uri"], Path(chosen_gain["local_path"]))
    # The native MEF embeds the position-dependent EPSF table. Record the
    # archive input link for its calibration family as an independent check.
    epsf_artifacts = [
        x for x in provenance.get("calibration_artifacts", [])
        if "/epsf/" in str(x.get("uri", "")).lower()
    ]
    provenance_links["epsf"] = (
        provenance_link_for_uri(provenance, science_uri, normalise_irsa_uri(epsf_artifacts[0]["uri"]))
        if len(epsf_artifacts) == 1 else None
    )

    if chosen_wcs and chosen_area:
        # First write a base audit without a compatibility verdict. The
        # compatibility checker then verifies this exact audit file/hash,
        # the exact FITS files, and the live IRSA provenance foreign key.
        base_audit = audit_native_mef(
            science_path, Path(chosen_wcs["local_path"]),
            solid_angle_path=Path(chosen_area["local_path"]),
            solid_angle_uri=chosen_area["uri"],
            science_uri=science_uri, spectral_wcs_uri=chosen_wcs["uri"])
        base_audit_path = args.out / "native_mef_audit_precompat.json"
        base_audit_path.write_text(json.dumps(base_audit, indent=2, default=str), encoding="utf-8")
        audit_path = args.out / "native_mef_audit.json"
        wcs_link = provenance_links.get("spectral_wcs")
        if wcs_link:
            science_evidence = {
                "native_uri": science_uri, "sha256": science["sha256"],
                "local_path": str(science_path), "release": base_audit.get("release"),
                "detector": science["detector"],
                "pipeline_version": base_audit.get("science_pipeline_version"),
                "processing_date": base_audit.get("science_processing_date"),
                "coordinate_frame": base_audit.get("coordinate_frame"),
            }
            cal_meta = base_audit.get("spectral_wcs_metadata") or {}
            calibration_evidence = {
                "native_uri": chosen_wcs["uri"], "sha256": chosen_wcs["sha256"],
                "local_path": chosen_wcs["local_path"], "release": cal_meta.get("release"),
                "detector": cal_meta.get("detector"),
                "pipeline_version": cal_meta.get("pipeline_version"),
                "processing_date": cal_meta.get("processing_date"),
                "coordinate_frame": cal_meta.get("coordinate_frame"),
                "wavelength_audit_path": str(base_audit_path),
                "wavelength_audit_sha256": sha256(base_audit_path),
                "solid_angle_map_uri": chosen_area["uri"],
                "solid_angle_map_sha256": chosen_area["sha256"],
                "solid_angle_map_path": chosen_area["local_path"],
                "archive_provenance_link": wcs_link,
            }
            audit_report = audit_native_mef(
                science_path, Path(chosen_wcs["local_path"]),
                solid_angle_path=Path(chosen_area["local_path"]),
                solid_angle_uri=chosen_area["uri"],
                science_uri=science_uri, spectral_wcs_uri=chosen_wcs["uri"],
                compatibility_evidence={
                    "science": science_evidence,
                    "calibration": calibration_evidence,
                })
        else:
            audit_report = {
                **base_audit,
                "calibration_compatibility": {
                    "status": "review_required",
                    "reason": "No exact IRSA provenance_input foreign-key link was found for the selected spectral-WCS artifact.",
                },
            }
        audit_path.write_text(json.dumps(audit_report, indent=2, default=str), encoding="utf-8")
    else:
        audit_report = {
            "status": "REVIEW_REQUIRED",
            "reason": "No detector-matched, full-native-grid spectral-WCS plus solid-angle pair was found.",
            "science": science,
            "calibration_compatibility": {"status": "review_required"},
        }
        audit_path = args.out / "native_mef_audit.json"
        audit_path.write_text(json.dumps(audit_report, indent=2, default=str), encoding="utf-8")

    gain_validation = {"status": "not_available"}
    if chosen_gain:
        with fits.open(chosen_gain["local_path"], memmap=True, checksum=True) as hdul:
            hdu = next((h for h in hdul if h.data is not None and np.asarray(h.data).ndim == 2), None)
            if hdu is not None:
                values = np.asarray(hdu.data, dtype=float)
                unit = str(hdu.header.get("BUNIT", "")).lower()
                finite_positive = np.isfinite(values) & (values > 0)
                gain_structure_ok = (
                    values.shape == (2040, 2040)
                    and ("mjy" in unit and "sr" in unit and ("electron" in unit or "e-" in unit) and "s" in unit)
                    and normal_detector(hdu.header.get("DETECTOR", hdul[0].header.get("DETECTOR")))==science["detector"]
                )
                gain_validation = {
                    "status": (
                        "structure_units_pass_with_invalid_pixels_explicitly_masked"
                        if gain_structure_ok and finite_positive.mean() > 0.999
                        else "structure_and_units_pass"
                        if gain_structure_ok and finite_positive.all()
                        else "review_required"
                    ),
                    "shape": list(values.shape), "bunit": hdu.header.get("BUNIT"),
                    "detector": normal_detector(hdu.header.get("DETECTOR", hdul[0].header.get("DETECTOR"))),
                    "finite_positive_fraction": float(finite_positive.mean()),
                    "invalid_pixel_count": int((~finite_positive).sum()),
                    "invalid_pixels_are_not_interpolated": True,
                    "uri": chosen_gain["uri"], "sha256": chosen_gain["sha256"],
                }

    calibrated_injection = {"status": "not_run"}
    if (
        chosen_area and
        (audit_report.get("calibration_compatibility") or {}).get("status") == "compatible"
    ):
        try:
            calibrated_injection = run_calibrated_jy_injection(
                science_path, science_uri,
                Path(chosen_area["local_path"]), chosen_area["uri"],
                science["sha256"], chosen_area["sha256"],
                args.out / "calibrated_injection",
            )
        except Exception as exc:
            calibrated_injection = {
                "status": "failed", "error": f"{type(exc).__name__}: {exc}"
            }

    summary = {
        "schema_version": "1.0",
        "created_utc": started,
        "field": {"name": field.name, "ra_deg": field.ra_deg, "dec_deg": field.dec_deg},
        "archive": "NASA/IPAC IRSA SPHEREx",
        "release": args.release.upper(),
        "bandpass_requested": args.bandpass,
        "science": science,
        "calibration_candidates": calibration_records,
        "candidate_counts": {k: len(v) for k, v in candidate_lists.items()},
        "selected_products": {
            "spectral_wcs": chosen_wcs,
            "solid_angle": chosen_area,
            "absolute_gain": chosen_gain,
        },
        "native_mef_audit": audit_report,
        "absolute_gain_validation": gain_validation,
        "archive_provenance": {
            "science_planeid": provenance.get("science_planeid"),
            "science_metadata": provenance.get("science"),
            "input_relation_count": len(provenance.get("input_relations", [])),
            "linked_calibration_artifact_count": len(provenance.get("calibration_artifacts", [])),
            "query_sha256": provenance.get("query_sha256"),
            "exact_product_links": provenance_links,
        },
        "calibrated_jy_injection_evaluation": calibrated_injection,
        "matching_boundary": (
            "Selected candidates are detector-matched and native-grid checked. They are not labelled fully compatible "
            "unless the science/calibration processing provenance is explicitly reconciled. A shared detector, "
            "matching filename date, or matching dimensions alone is not proof of scientific compatibility."
        ),
        "source_query": inventory["field_results"][0].get("query"),
        "science_tap_row_count": inventory["field_results"][0].get("tap_row_count"),
    }
    (args.out / "real_field_audit_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (args.out / "candidate_urls.json").write_text(
        json.dumps({k: v for k, v in candidate_lists.items()}, indent=2), encoding="utf-8")
    print(json.dumps({
        "field": field.name, "science_uri": science_uri, "science_sha256": science["sha256"],
        "science_detector": science["detector"],
        "candidate_counts": summary["candidate_counts"],
        "selected_uris": {k: v.get("uri") if v else None for k, v in summary["selected_products"].items()},
        "native_mef_audit_status": audit_report.get("status"),
        "absolute_gain_status": gain_validation.get("status"),
        "archive_input_relation_count": len(provenance.get("input_relations", [])),
        "wavelength_calibration_provenance_linked": bool(provenance_links.get("spectral_wcs")),
        "calibration_compatibility_status": (audit_report.get("calibration_compatibility") or {}).get("status"),
        "calibrated_injection_evaluation": calibrated_injection.get("status"),
        "summary": str(args.out / "real_field_audit_summary.json"),
    }, indent=2))
    # Exit non-zero only if the science file or all calibration families were unavailable.
    # A REVIEW_REQUIRED scientific pairing is retained as an explicit, auditable outcome.
    if not chosen_wcs or not chosen_area or not chosen_gain:
        raise SystemExit("One or more required detector calibration families were not retrieved; see artifact manifest.")


if __name__ == "__main__":
    main()
