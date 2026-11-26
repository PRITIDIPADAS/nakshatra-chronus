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
from research_discovery.spherex.psf_physicality import enforce_nonnegative_interpolation_psf
from research_discovery.spherex.run_provenance_calibration_audit import normalize_release
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


def normalize_release(value: str) -> str | None:
    """Return the exact SPHEREx archive release token from a native URI."""
    path = urlparse(str(value)).path.lower()
    for release in ("dr1", "qr3"):
        if f"/spherex/{release}/" in path or f"/{release}/" in path:
            return release.upper()
    return None


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




def query_related_solid_angle_candidates(release: str, detector_number: int) -> list[dict]:
    """Query the calibration artifact table for a same-release and detector area map."""
    detector = f"D{int(detector_number)}"
    release_token = str(release).lower()
    sql = f"""
    SELECT a.artifactid, a.planeid, a.uri, a.producttype, a.releasetype,
      a.contenttype, a.contentlength, a.contentchecksum, p.productid
    FROM spherex.artifact a
    JOIN spherex.plane p ON p.planeid = a.planeid
    WHERE a.producttype = 'calibration'
      AND LOWER(a.uri) LIKE '%/spherex/{release_token}/solid_angle_pixel_map/%'
      AND UPPER(p.productid) = '{detector}'
    """
    return tap_rows(sql)


def download_artifact_row(row: dict, *, family: str, product_name: str,
                          release: str, detector_number: int, out_dir: Path,
                          provenance: dict, science_uri: str,
                          direct_pipeline_input: bool) -> dict:
    """Download an exact artifact-table URI and verify its published MD5."""
    uri = normalise_irsa_uri(str(row["uri"]))
    destination = out_dir / family / Path(urlparse(uri).path).name
    record = download_calibration(
        uri, release=release.lower(), product=product_name,
        detector=detector_number, out=destination,
    )
    if record.get("status") != "downloaded":
        raise RuntimeError(f"{family} download failed: {record.get('error')}")
    expected = str(row.get("contentchecksum") or "").strip().lower()
    actual = md5_file(destination)
    if expected.startswith("md5:") and actual != expected.split(":", 1)[1]:
        raise RuntimeError(
            f"{family} MD5 differs from the IRSA artifact row: {actual} != {expected}"
        )
    link = (
        provenance_link_for_uri(provenance, science_uri, uri, destination)
        if direct_pipeline_input else None
    )
    if direct_pipeline_input and link is None:
        raise RuntimeError(
            f"{family} failed exact spherex.provenance_input linkage or archive MD5 verification"
        )
    probe = header_record(destination, family, uri)
    probe.update({
        "retrieval_status": "downloaded",
        "artifact_id": row.get("artifactid"),
        "archive_plane_id": row.get("planeid"),
        "archive_content_length": row.get("contentlength"),
        "archive_content_checksum": row.get("contentchecksum"),
        "archive_md5_actual": actual,
        "archive_md5_status": "pass" if expected.startswith("md5:") else "not_supplied",
        "provenance_relation": (
            "exact_input_to_this_science_plane" if direct_pipeline_input
            else "supplemental_same_release_detector_area_map"
        ),
        "provenance_link": link,
    })
    return probe


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


def run_calibrated_jy_injection(
    science_path: Path, science_uri: str,
    area_path: Path, area_uri: str,
    gain_path: Path, gain_uri: str,
    science_sha: str, area_sha: str, gain_sha: str,
    gain_provenance_link: dict, science_metadata: dict,
    out_dir: Path,
) -> dict:
    """Run real-data Jy injection with photon noise derived from the linked abs-gain map.

    The provenance-derived conversion is explicitly pending independent human
    review. This exploratory opt-in is never labelled human-verified.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    flag_bits, flag_names = policy_mask("conservative-photometry")
    stamp_size = 11
    with (
        fits.open(science_path, memmap=True) as science,
        fits.open(area_path, memmap=True) as area_file,
        fits.open(gain_path, memmap=True, checksum=True) as gain_file,
    ):
        image_hdu = science["IMAGE"]
        image = np.asarray(image_hdu.data, dtype=float)
        image_header = image_hdu.header.copy()
        variance = np.asarray(science["VARIANCE"].data, dtype=float)
        flags = np.asarray(science["FLAGS"].data)
        background = np.asarray(science["ZODI"].data, dtype=float)
        area_hdu = next(h for h in area_file if h.data is not None and np.asarray(h.data).ndim == 2)
        area_values = np.asarray(area_hdu.data, dtype=float)
        area_unit = str(area_hdu.header.get("BUNIT", "")).strip().lower().replace(" ", "")
        if area_unit in {"arcsec2", "arcsec**2", "arcsec^2"}:
            omega_sr = area_values * (np.pi / (180.0 * 3600.0)) ** 2
        elif area_unit in {"sr", "steradian", "steradians"}:
            omega_sr = area_values
        else:
            raise ValueError(
                f"Solid-angle calibration must be in arcsec^2 or sr; received {area_hdu.header.get('BUNIT')!r}"
            )
        if image.shape != variance.shape or image.shape != flags.shape or image.shape != omega_sr.shape:
            raise ValueError("IMAGE, VARIANCE, FLAGS and solid-angle map must be pixel-aligned")
        gain_hdu = next(
            h for h in gain_file
            if h.data is not None and np.asarray(h.data).ndim == 2
        )
        gain_bunit = str(gain_hdu.header.get("BUNIT", "")).strip()
        gain_detector = normal_detector(
            gain_hdu.header.get("DETECTOR", gain_file[0].header.get("DETECTOR"))
        )
        if gain_detector != science_metadata.get("detector"):
            raise ValueError("absolute-gain detector does not match the science detector")
        if not gain_bunit:
            raise ValueError("absolute-gain map does not declare BUNIT")
        if not gain_provenance_link:
            raise ValueError("source Poisson modelling requires an exact provenance_input link")

    exposure_time_s = float(science_metadata.get("exposure_time_s"))
    if not np.isfinite(exposure_time_s) or exposure_time_s <= 0:
        raise ValueError("science archive metadata does not provide a valid exposure time")
    if not science_metadata.get("observation_id"):
        raise ValueError("science MEF is missing OBSID required to bind the electron calibration")

    from research_discovery.spherex.coordinate_transform import detector_origin_offset
    from research_discovery.spherex.electron_conversion import derive_electrons_per_image_unit
    origin_xy = detector_origin_offset(image_header)
    electrons_per_image_unit = derive_electrons_per_image_unit(
        calibration_path=gain_path,
        expected_sha256=gain_sha,
        detector=science_metadata["detector"],
        calibration_bunit=gain_bunit,
        exposure_time_s=exposure_time_s,
        origin_xy=origin_xy,
        image_shape=image.shape,
        science_image_unit=str(image_header.get("BUNIT", "")),
    )
    electron_record = {
        "verification_status": "derived_pending_independent_review",
        "review_status": "pending",
        "derived_by": "CHRONOS provenance-aware automated evaluation",
        "derived_utc": datetime.now(timezone.utc).isoformat(),
        "calibration_product": "abs_gain_matrix",
        "calibration_bunit": gain_bunit,
        "exposure_time_s": exposure_time_s,
        "science_file_sha256": science_sha,
        "science_native_file_sha256": science_sha,
        "science_observation_id": str(science_metadata["observation_id"]),
        "science_source_uri": science_uri,
        "detector": str(science_metadata["detector"]),
        "image_unit": str(image_header.get("BUNIT", "")),
        "calibration_uri": gain_uri,
        "calibration_file_path": str(gain_path),
        "calibration_sha256": gain_sha,
        "conversion_method": (
            "G_abs has units (MJy/sr)/(electron/s). For each valid detector "
            "pixel, electrons per MJy/sr IMAGE unit = exposure_time_s / G_abs. "
            "Source Poisson draws are divided by this conversion map; variance "
            "is updated in IMAGE units. Non-positive or non-finite gain pixels "
            "remain invalid and are excluded, never interpolated."
        ),
        "provenance_link": gain_provenance_link,
    }

    # The first trial used a fixed geometric centre, which fell on a quality-mask
    # boundary. Select the nearest valid native-detector location instead.
    from scipy.ndimage import minimum_filter
    quality = (
        np.isfinite(variance) & (variance > 0)
        & np.isfinite(omega_sr) & (omega_sr > 0)
        & ((flags.astype(np.uint64) & np.uint64(flag_bits)) == 0)
        & np.isfinite(background)
        & np.isfinite(electrons_per_image_unit)
        & (electrons_per_image_unit > 0)
    )
    footprint_good = minimum_filter(
        quality.astype(np.uint8), size=(stamp_size, stamp_size),
        mode="constant", cval=0,
    ) > 0
    margin = stamp_size // 2 + 100 + 10
    height, width = image.shape
    y_grid, x_grid = np.indices(image.shape)
    safe_zone = (
        footprint_good
        & (x_grid >= margin) & (x_grid < width - margin)
        & (y_grid >= margin) & (y_grid < height - margin)
    )
    candidates = np.argwhere(safe_zone)
    if not len(candidates):
        raise ValueError("No full native ePSF footprint with valid image, area, flags and gain exists.")
    target_y, target_x = (height - 1) / 2.0, (width - 1) / 2.0
    distance2 = (
        (candidates[:, 0] - target_y) ** 2
        + (candidates[:, 1] - target_x) ** 2
    )
    selected = candidates[int(np.argmin(distance2))]
    y_ref, x_ref = float(selected[0]) + 0.75, float(selected[1]) + 0.25
    stamp_path = out_dir / "native_epsf_stamp.fits"
    epsf_meta = extract_epsf(
        science_path, x=x_ref, y=y_ref, out=stamp_path, stamp_size=stamp_size
    )
    with fits.open(stamp_path) as psf_file:
        raw_psf = np.asarray(psf_file[0].data, dtype=float)
        raw_psf_header = psf_file[0].header.copy()
    psf, psf_correction = enforce_nonnegative_interpolation_psf(raw_psf)
    physical_psf_path = out_dir / "native_epsf_stamp_nonnegative.fits"
    physical_header = raw_psf_header.copy()
    physical_header["PSFCLIP"] = (bool(psf_correction["correction_applied"]), "Tiny negative interpolation overshoot clipped")
    physical_header["PSFNCLIP"] = (int(psf_correction["clipped_pixel_count"]), "Number of clipped negative samples")
    physical_header["PSFNEGFR"] = (float(psf_correction["negative_to_positive_integrated_flux_fraction"]), "Clipped negative flux / positive flux")
    physical_header["PSFMETH"] = ("bounded_clip_renorm", "Audited bounded interpolation correction")
    fits.PrimaryHDU(data=psf.astype(np.float32), header=physical_header).writeto(
        physical_psf_path, overwrite=True
    )
    half = psf.shape[0] // 2
    x0, y0 = int(np.floor(x_ref)) - half, int(np.floor(y_ref)) - half
    sl = (slice(y0, y0 + psf.shape[0]), slice(x0, x0 + psf.shape[1]))
    local_var = variance[sl]
    local_omega = omega_sr[sl]
    local_flags = flags[sl].astype(np.uint64)
    local_conversion = electrons_per_image_unit[sl]
    good = (
        np.isfinite(local_var) & (local_var > 0)
        & np.isfinite(local_omega) & (local_omega > 0)
        & ((local_flags & np.uint64(flag_bits)) == 0)
        & np.isfinite(local_conversion) & (local_conversion > 0)
    )
    if not good.all():
        raise ValueError("Selected PSF reference footprint failed the strict calibration validity scan.")
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
        electrons_per_image_unit=electrons_per_image_unit,
        electron_calibration_record=electron_record,
        allow_unreviewed_electron_calibration=True,
    )
    # Secondary, reported beside the primary rule and never replacing it: model the structured sky
    # (mesh background plus empirical noise) and inject at the 5 sigma that this honest noise implies.
    from research_discovery.validation.injection_recovery import structured_background_model
    sb_valid = np.isfinite(image) & np.isfinite(variance) & (variance > 0) & ((flags.astype(np.uint64) & np.uint64(flag_bits)) == 0)
    _, sb_scale = structured_background_model(image - (background if background is not None else 0.0), variance, sb_valid)
    local_scale = sb_scale[sl]
    empirical_info = float(np.sum((detection_template ** 2) / (local_var * local_scale ** 2)))
    empirical_five_sigma_jy = 5.0 / (1e-6 * np.sqrt(empirical_info))
    sb_levels = [0.5 * empirical_five_sigma_jy, empirical_five_sigma_jy, 2.0 * empirical_five_sigma_jy]
    sb = run_injection_recovery(
        image, variance, flags, psf,
        flux_levels=sb_levels, n_per_level=20, snr_threshold=5.0,
        excluded_flag_bits=flag_bits, seed=20261126,
        min_injection_separation=16, source_exclusion_radius=7,
        solid_angle_sr_map=omega_sr, flux_unit="Jy",
        psf_reference_xy=(x_ref, y_ref), psf_region_radius=100.0,
        background=background, detection_psf=detection_template,
        electrons_per_image_unit=electrons_per_image_unit,
        electron_calibration_record=electron_record,
        allow_unreviewed_electron_calibration=True,
        structured_background=True,
    )
    result["structured_background_variant"] = {
        "role": "secondary diagnostic; the primary recovery rule above is unchanged",
        "empirical_five_sigma_jy": empirical_five_sigma_jy,
        "pipeline_five_sigma_jy": five_sigma_jy,
        "sensitivity_ratio": empirical_five_sigma_jy / five_sigma_jy,
        "local_noise_scale_median": float(np.median(local_scale)),
        "flux_levels_jy": sb_levels,
        "recovered": [int(sum(1 for r in sb["injections"] if r["flux_level"] == lv and r["recovered"])) for lv in sb_levels],
        "n_per_level": 20,
        "n_baseline_detections": sb.get("n_baseline_detections"),
        "structured_background": sb.get("structured_background"),
    }
    result["evaluation_type"] = (
        "real Level-2 single-exposure Jy injection/recovery with position-dependent ePSF, "
        "pixel solid angle and provenance-derived source Poisson noise"
    )
    result["calibrated_flux_definition"] = "Integrated source flux density in Jy; IMAGE is MJy/sr and pixel solid angle is converted from arcsec^2 to sr."
    result["local_reference_5sigma_sensitivity_jy"] = five_sigma_jy
    result["local_reference_1sigma_flux_uncertainty_jy"] = five_sigma_jy / 5.0
    result["local_matched_filter_information_jy_inverse2"] = matched_filter_information * 1.0e-12
    result["local_psf_footprint_solid_angle_fractional_range"] = float(
        (np.max(local_omega) - np.min(local_omega)) / np.median(local_omega)
    )
    result["injection_flux_levels_jy"] = levels_jy
    psf_correction.update({
        "raw_stamp_path": str(stamp_path),
        "raw_stamp_sha256": epsf_meta.get("output_sha256"),
        "corrected_stamp_path": str(physical_psf_path),
        "corrected_stamp_sha256": sha256(physical_psf_path),
    })
    result["psf_interpolation_correction"] = psf_correction
    result["electron_calibration_derivation"] = {
        "record": electron_record,
        "absolute_gain_uri": gain_uri,
        "absolute_gain_sha256": gain_sha,
        "gain_bunit": gain_bunit,
        "conversion_map_shape": list(electrons_per_image_unit.shape),
        "conversion_map_valid_fraction": float(np.mean(np.isfinite(electrons_per_image_unit) & (electrons_per_image_unit > 0))),
        "independent_review_status": "pending",
        "explicit_exploratory_opt_in": True,
    }
    result["psf_reference_selection"] = {
        "selection_method": "nearest-to-detector-centre position with fully valid native ePSF, area, gain and 100-pixel injection zone",
        "reference_x": x_ref, "reference_y": y_ref,
        "quality_valid_fraction_in_image": float(quality.mean()),
        "valid_reference_position_count": int(len(candidates)),
        "footprint_shape": [int(psf.shape[0]), int(psf.shape[1])],
    }
    result["science_provenance"] = {
        "science_native_uri": science_uri, "science_sha256": science_sha,
        "solid_angle_native_uri": area_uri, "solid_angle_sha256": area_sha,
        "solid_angle_provenance_status": "detector-matched auxiliary calibration product; not represented as a direct input-plane link",
        "absolute_gain_native_uri": gain_uri, "absolute_gain_sha256": gain_sha,
        "absolute_gain_provenance_link": gain_provenance_link,
        "epsf_extraction": epsf_meta,
    }
    result["flag_policy"] = {"name": "conservative-photometry", "excluded_flag_names": list(flag_names), "excluded_flag_mask": int(flag_bits)}
    result["limits"] = [
        "One real D2 DR1 exposure; this is not a multi-field or time-domain benchmark.",
        "Source Poisson noise is simulated from a per-pixel conversion derived from the exact provenance-linked absolute-gain map; the derivation remains pending independent human review.",
        "The injected sources are visible to this evaluation and the seed is not held by an independent custodian; this is not a blind benchmark.",
        "Sensitivity is computed locally from observed VARIANCE, the native ePSF and the detector pixel solid-angle map; it is a pre-injection nominal sensitivity.",
        "This is an exploratory standalone matched-filter test, not the Session 07 DEEPS SNR baseline and not the four-method CHRONOS comparison.",
        "The solid-angle map is a detector-matched archive calibration product; it is not asserted to be a direct spherex.provenance_input child of this science plane.",
        "Invalid absolute-gain pixels remain non-finite in the conversion map and are excluded; no calibration pixel is interpolated or filled.",
    ]
    output = out_dir / "calibrated_jy_injection_recovery.json"
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return {
        "status": "completed",
        "output": str(output),
        "five_sigma_sensitivity_jy": five_sigma_jy,
        "flux_levels_jy": levels_jy,
        "flux_summary": result.get("flux_summary"),
        "new_unmatched_peak_summary": result.get("new_unmatched_peak_summary"),
        "n_baseline_detections": result.get("n_baseline_detections"),
        "psf_sha256": epsf_meta.get("output_sha256"),
        "source_photon_noise": result.get("source_photon_noise"),
        "electron_calibration_derivation": result.get("electron_calibration_derivation"),
        "limitations": result["limits"],
    }



def candidate_sort_key(uri: str, wanted_date: str | None):
    tokens = path_tokens(uri)
    date = tokens["archive_processing_date"] or ""
    exact = bool(wanted_date and date == wanted_date)
    return (exact, date, tokens["archive_product_version"] or "")


def validate_calibrated_injection_exit(status: str, *, skipped_by_request: bool) -> None:
    """Allow a deliberate no-injection audit run without masking real injection failures."""
    if skipped_by_request and status == "skipped_by_request":
        return
    if status != "completed":
        raise SystemExit("Calibrated Jy injection/recovery did not complete; see field summary.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--field", default="M101,210.80227,54.34895")
    p.add_argument("--science-uri", default=None,
                   help="Optional exact native DR1/QR3 Level-2 URI; bypasses field-level science selection")
    p.add_argument("--bandpass", default="SPHEREx-D2")
    p.add_argument("--release", choices=("dr1", "qr3"), default="dr1")
    p.add_argument("--limit-per-family", type=int, default=5)
    p.add_argument("--out", type=Path, default=Path("data/spherex_m101_audit"))
    p.add_argument("--skip-calibrated-injection", action="store_true", help="Skip source-Poisson injection; source photometry uses delivered Level-2 VARIANCE")
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
    science["pipeline_version"] = (
        science.get("pipeline_version") or provenance["science"].get("provenance_version")
    )
    filename_processing = re.search(
        r"-v[0-9.]+-(20[0-9]{2}-[0-9]{3})\.fits$",
        science_path.name, re.I,
    )
    science["processing_date"] = science["processing_date"] or (
        filename_processing.group(1) if filename_processing else None
    )
    science["exposure_time_s"] = provenance["science"].get("time_exposure")
    detector_number = int(science["detector"][1:])

    # Wavelength and gain files must come from the exact provenance_input
    # graph for this science plane. The detector solid-angle map is queried
    # separately and remains explicitly supplemental if not directly linked.
    exact_artifacts = [
        row for row in provenance.get("calibration_artifacts", [])
        if str(row.get("producttype", "")).lower() == "calibration"
    ]
    wcs_rows = [
        row for row in exact_artifacts
        if "/spectral_wcs/" in str(row.get("uri", "")).lower()
        and normalize_release(normalise_irsa_uri(row["uri"])) == args.release.upper()
    ]
    gain_rows = [
        row for row in exact_artifacts
        if "/abs_gain_matrix/" in str(row.get("uri", "")).lower()
        and normalize_release(normalise_irsa_uri(row["uri"])) == args.release.upper()
    ]
    if len(wcs_rows) != 1:
        raise RuntimeError(
            "Expected exactly one provenance-linked spectral-WCS artifact for this "
            f"science plane; found {len(wcs_rows)}"
        )
    if len(gain_rows) != 1:
        raise RuntimeError(
            "Expected exactly one provenance-linked absolute-gain artifact for this "
            f"science plane; found {len(gain_rows)}"
        )

    wcs_date = path_tokens(normalise_irsa_uri(wcs_rows[0]["uri"]))["archive_processing_date"]
    area_rows = query_related_solid_angle_candidates(args.release, detector_number)
    area_rows = [
        row for row in area_rows
        if path_tokens(normalise_irsa_uri(str(row.get("uri") or "")))["archive_processing_date"] == wcs_date
    ]
    if len(area_rows) != 1:
        raise RuntimeError(
            "Expected exactly one same-release, same-detector, same-calibration-date "
            f"solid-angle artifact; found {len(area_rows)}"
        )

    selections = {
        "spectral_wcs": (wcs_rows[0], "spectral_wcs", True),
        "solid_angle": (area_rows[0], "solid_angle", False),
        "absolute_gain": (gain_rows[0], "abs_gain_matrix", True),
    }
    calibration_records = []
    candidate_lists = {}
    for family, (archive_row, product_name, direct_link) in selections.items():
        uri = normalise_irsa_uri(str(archive_row["uri"]))
        candidate_lists[family] = [uri]
        probe = download_artifact_row(
            archive_row, family=family, product_name=product_name,
            release=args.release, detector_number=detector_number,
            out_dir=args.out / "calibrations", provenance=provenance,
            science_uri=science_uri, direct_pipeline_input=direct_link,
        )
        calibration_records.append(probe)

    def valid_candidate(family):
        return [
            row for row in calibration_records
            if row.get("family") == family
            and row.get("retrieval_status") == "downloaded"
            and row.get("detector") == science.get("detector")
        ]

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
        # Fill only missing archive identity from the exact URI/TAP record.
        # These identifiers are distinct from the direct FITS header values.
        base_audit["release"] = science["release"].lower()
        base_audit["science_processing_date"] = science.get("processing_date")
        base_audit["science_detector"] = science["detector"]
        base_audit["science_pipeline_version"] = (
            base_audit.get("science_pipeline_version") or science.get("pipeline_version")
        )
        cal_meta_for_audit = base_audit.get("spectral_wcs_metadata") or {}
        cal_meta_for_audit["release"] = normalize_release(chosen_wcs["uri"]).lower()
        cal_meta_for_audit["detector"] = chosen_wcs.get("detector") or science["detector"]
        cal_meta_for_audit["pipeline_version"] = (
            cal_meta_for_audit.get("pipeline_version") or chosen_wcs.get("header_version")
        )
        cal_meta_for_audit["processing_date"] = (
            path_tokens(chosen_wcs["uri"]).get("archive_processing_date")
        )
        cal_meta_for_audit["coordinate_frame"] = "native_detector"
        base_audit["spectral_wcs_metadata"] = cal_meta_for_audit
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
                "solid_angle_provenance_status": "supplemental_not_listed_as_direct_pipeline_input",
                "solid_angle_archive_content_checksum": chosen_area.get("archive_content_checksum"),
                "solid_angle_archive_md5_status": chosen_area.get("archive_md5_status"),
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
    if args.skip_calibrated_injection:
        calibrated_injection = {"status": "skipped_by_request", "reason": "Source photometry uses delivered Level-2 VARIANCE; source-Poisson injection and the pending gain-to-electron derivation are not used."}
    elif (
        chosen_area and chosen_gain and provenance_links.get("absolute_gain")
        and (audit_report.get("calibration_compatibility") or {}).get("status") == "compatible"
    ):
        try:
            calibrated_injection = run_calibrated_jy_injection(
                science_path, science_uri,
                Path(chosen_area["local_path"]), chosen_area["uri"],
                Path(chosen_gain["local_path"]), chosen_gain["uri"],
                science["sha256"], chosen_area["sha256"], chosen_gain["sha256"],
                provenance_links["absolute_gain"], science,
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
            "solid_angle_map_pipeline_input": False,
            "solid_angle_map_selection_basis": (
                "same DR1 release, D2 detector and calibration processing date as the "
                "provenance-linked spectral-WCS artifact; separate artifact-table lookup"
            ),
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
    if (audit_report.get("calibration_compatibility") or {}).get("status") != "compatible":
        raise SystemExit("Native MEF calibration compatibility did not pass; see audit report.")
    validate_calibrated_injection_exit(
        str(calibrated_injection.get("status", "not_run")),
        skipped_by_request=bool(args.skip_calibrated_injection),
    )


if __name__ == "__main__":
    main()
