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

from research_discovery.spherex.fetch_native_mefs import Field, run as fetch_native
from research_discovery.spherex.discover_calibrations import find_products
from research_discovery.spherex.fetch_calibration import download_calibration
from research_discovery.spherex.native_mef_audit import audit as audit_native_mef


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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


def candidate_sort_key(uri: str, wanted_date: str | None):
    tokens = path_tokens(uri)
    date = tokens["archive_processing_date"] or ""
    exact = bool(wanted_date and date == wanted_date)
    return (exact, date, tokens["archive_product_version"] or "")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--field", default="M101,210.80227,54.34895")
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
    if chosen_wcs and chosen_area:
        audit_report = audit_native_mef(
            science_path, Path(chosen_wcs["local_path"]),
            solid_angle_path=Path(chosen_area["local_path"]),
            solid_angle_uri=chosen_area["uri"],
            science_uri=science_uri, spectral_wcs_uri=chosen_wcs["uri"])
        audit_path = args.out / "native_mef_audit.json"
        audit_path.write_text(json.dumps(audit_report, indent=2, default=str), encoding="utf-8")
    else:
        audit_report = {
            "status": "REVIEW_REQUIRED",
            "reason": "No detector-matched, full-native-grid spectral-WCS plus solid-angle pair was found among downloaded candidates.",
            "science": science,
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
                gain_validation = {
                    "status": "structure_and_units_pass" if (
                        values.shape == (2040, 2040) and finite_positive.all()
                        and ("mjy" in unit and "sr" in unit and ("electron" in unit or "e-" in unit) and "s" in unit)
                        and normal_detector(hdu.header.get("DETECTOR", hdul[0].header.get("DETECTOR")))==science["detector"]
                    ) else "review_required",
                    "shape": list(values.shape), "bunit": hdu.header.get("BUNIT"),
                    "detector": normal_detector(hdu.header.get("DETECTOR", hdul[0].header.get("DETECTOR"))),
                    "finite_positive_fraction": float(finite_positive.mean()),
                    "uri": chosen_gain["uri"], "sha256": chosen_gain["sha256"],
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
        "summary": str(args.out / "real_field_audit_summary.json"),
    }, indent=2))
    # Exit non-zero only if the science file or all calibration families were unavailable.
    # A REVIEW_REQUIRED scientific pairing is retained as an explicit, auditable outcome.
    if not chosen_wcs or not chosen_area or not chosen_gain:
        raise SystemExit("One or more required detector calibration families were not retrieved; see artifact manifest.")


if __name__ == "__main__":
    main()
