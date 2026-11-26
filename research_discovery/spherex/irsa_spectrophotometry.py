#!/usr/bin/env python3
"""Import IRSA SPHEREx Spectrophotometry Tool rows into the CHRONOS source-series schema.

The adapter does not infer archive product identity, coordinate origin, source
classification, quality thresholds, or calibration compatibility. Those must be
provided in a signed-off sidecar. Every imported row is subsequently checked by
assemble_source_timeseries against the exact native FITS products.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from research_discovery.spherex.flag_policy import FLAG_BITS, policy_mask
from research_discovery.spherex.source_timeseries import (
    assemble_source_timeseries,
    sha256_file,
)

SCHEMA = "chronos-irsa-spherex-photometry-import/1.0"
REPORT_SCHEMA = "chronos-irsa-spherex-import-report/1.0"
IRSA_HOST = "irsa.ipac.caltech.edu"
REQUIRED_COLUMNS = (
    "wavelength", "flux", "flux_err", "lambda_width", "flags", "fit_ql",
    "flux_bkg", "lvf_id", "det_id", "deep_flg", "mjd", "data_collection",
    "x_image", "y_image", "ra", "dec",
)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False, default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _scalar(value: Any) -> Any:
    try:
        import numpy as np
        if np.ma.is_masked(value):
            return None
        if isinstance(value, np.generic):
            value = value.item()
    except ImportError:
        pass
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return value


def load_irsa_rows(path: str | Path) -> list[dict[str, Any]]:
    """Load the downloaded IRSA VOTable/XML or CSV without discarding columns."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    elif suffix in {".vot", ".votable", ".xml"}:
        try:
            from astropy.table import Table
        except ImportError as exc:
            raise RuntimeError("Astropy is required to read IRSA VOTable exports") from exc
        table = Table.read(path, format="votable")
        rows = [
            {str(name): _scalar(row[name]) for name in table.colnames}
            for row in table
        ]
    else:
        raise ValueError("IRSA export must be .csv, .vot, .votable, or .xml")
    if not rows:
        raise ValueError("IRSA export contains no source-measurement rows")
    normalized = []
    for index, row in enumerate(rows):
        lookup = {_key(name): _scalar(value) for name, value in row.items()}
        missing = [name for name in REQUIRED_COLUMNS if _key(name) not in lookup]
        if missing:
            raise ValueError(f"IRSA row {index} is missing required columns: {missing}")
        normalized.append({name: lookup[_key(name)] for name in REQUIRED_COLUMNS})
    return normalized


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{label} must be finite" + (" and positive" if positive else ""))
    return result


def _integer(value: Any, label: str) -> int:
    number = _number(value, label)
    if not number.is_integer():
        raise ValueError(f"{label} must be an integer")
    return int(number)


def _boolean(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"{label} must be boolean-like")


def _release(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "qr2" in text:
        raise ValueError("QR2 rows are not admitted into the uniform DR1/QR3 series")
    if "dr1" in text:
        return "DR1"
    if "qr3" in text:
        return "QR3"
    raise ValueError(f"unsupported or ambiguous SPHEREx data_collection: {value!r}")


def _detector(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.fullmatch(r"(?:DETECTOR|DET|D)?0?([1-6])", text)
    if not match:
        raise ValueError(f"invalid SPHEREx det_id: {value!r}")
    return "D" + match.group(1)


def _separation_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    a1, d1, a2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    hav = (
        math.sin((d2 - d1) / 2) ** 2
        + math.cos(d1) * math.cos(d2) * math.sin((a2 - a1) / 2) ** 2
    )
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(max(0.0, hav))))) * 3600.0


def _flag_names(flags: int) -> list[str]:
    return sorted(name for name, bit in FLAG_BITS.items() if flags & (1 << bit))


def _validate_sidecar(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    if sidecar.get("schema") != SCHEMA:
        raise ValueError(f"sidecar schema must be {SCHEMA}")
    service = sidecar.get("service")
    sources = sidecar.get("sources")
    products = sidecar.get("products")
    catalogue = sidecar.get("source_catalogue")
    policy = sidecar.get("photometry_quality_policy")
    if not all(isinstance(item, Mapping) for item in (service, catalogue, policy)):
        raise ValueError("sidecar requires service, source_catalogue and photometry_quality_policy objects")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sidecar.sources must be a non-empty explicit source list")
    if len(sources) > 20:
        raise ValueError(
            "one IRSA Spectrophotometry Tool job supports at most 20 targets; submit explicit batches of 20 or fewer"
        )
    if not isinstance(products, list) or not products:
        raise ValueError("sidecar.products must contain exact LVF-to-archive-product mappings")

    tool_uri = str(service.get("tool_uri", "")).strip()
    parsed = urlparse(tool_uri)
    if parsed.scheme != "https" or parsed.hostname != IRSA_HOST:
        raise ValueError("service.tool_uri must be the official HTTPS IRSA host")
    for key in ("job_id", "version", "retrieved_utc"):
        if not str(service.get(key, "")).strip():
            raise ValueError(f"service.{key} is required")
    config_sha = str(service.get("configuration_sha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", config_sha):
        raise ValueError("service.configuration_sha256 must be a SHA-256 digest")

    policy_payload = {
        "policy_id": str(policy.get("policy_id", "")).strip(),
        "flag_policy": str(policy.get("flag_policy", "")).strip(),
        "fit_ql_max": _number(policy.get("fit_ql_max"), "fit_ql_max", positive=True),
        "max_abs_background_to_flux_ratio": _number(
            policy.get("max_abs_background_to_flux_ratio"),
            "max_abs_background_to_flux_ratio", positive=True,
        ),
        "background_fraction_definition": "abs(flux_bkg) / max(abs(flux), flux_err)",
    }
    if not policy_payload["policy_id"]:
        raise ValueError("photometry_quality_policy.policy_id is required")
    mask, names = policy_mask(policy_payload["flag_policy"])
    policy_sha = canonical_sha256(policy_payload)

    pixel_origin = sidecar.get("image_pixel_origin")
    if pixel_origin not in (0, 1):
        raise ValueError("image_pixel_origin must be explicitly declared as 0 or 1")
    position_tolerance = _number(
        sidecar.get("source_position_tolerance_arcsec"),
        "source_position_tolerance_arcsec", positive=True,
    )
    wcs_tolerance = _number(
        sidecar.get("image_wcs_tolerance_pixels", 0.5),
        "image_wcs_tolerance_pixels", positive=True,
    )
    if wcs_tolerance > 2:
        raise ValueError("image_wcs_tolerance_pixels must not exceed 2 pixels")
    flux_unit = str(service.get("flux_unit", "")).strip()
    if flux_unit not in {"uJy", "µJy"}:
        raise ValueError("IRSA flux_unit must explicitly be uJy/µJy; no unit guessing is allowed")

    source_index = {}
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ValueError(f"source row {index} must be an object")
        source_id = str(source.get("source_id", "")).strip()
        if not source_id or source_id in source_index:
            raise ValueError("source_id values must be unique and non-empty")
        ra = _number(source.get("ra_deg"), f"source {source_id} ra_deg")
        dec = _number(source.get("dec_deg"), f"source {source_id} dec_deg")
        if not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError(f"source {source_id} has invalid ICRS coordinates")
        if not str(source.get("classification_reference", "")).strip():
            raise ValueError(f"source {source_id} requires an external classification reference")
        source_index[source_id] = dict(source, source_id=source_id, ra_deg=ra, dec_deg=dec)

    product_index = {}
    normalized_products = []
    for index, product in enumerate(products):
        if not isinstance(product, Mapping):
            raise ValueError(f"product mapping {index} must be an object")
        lvf_id = str(product.get("lvf_id", "")).strip()
        detector = _detector(product.get("detector"))
        release = str(product.get("release", "")).upper().strip()
        product_id = str(product.get("archive_product_id", "")).strip()
        if not lvf_id or release not in {"DR1", "QR3"} or not product_id:
            raise ValueError(f"product mapping {index} requires lvf_id, DR1/QR3 release and archive_product_id")
        key = (lvf_id, detector, release)
        if key in product_index:
            raise ValueError(f"ambiguous duplicate LVF-to-product mapping for {key}")
        if product.get("detector") != detector or product.get("release") != release:
            raise ValueError(f"product {product_id} detector/release must be normalized as Dn and DR1/QR3")
        product_index[key] = dict(product)
        normalized_products.append(dict(product))

    return {
        "service": dict(service),
        "source_catalogue": dict(catalogue),
        "sources": list(source_index.values()),
        "products": normalized_products,
        "product_index": product_index,
        "quality_policy": policy_payload,
        "quality_policy_sha256": policy_sha,
        "flag_mask": mask,
        "flag_names": names,
        "image_pixel_origin": int(pixel_origin),
        "source_position_tolerance_arcsec": position_tolerance,
        "image_wcs_tolerance_pixels": wcs_tolerance,
    }


def build_source_photometry_manifest(
    rows: Sequence[Mapping[str, Any]],
    sidecar: Mapping[str, Any],
    *,
    export_sha256: str,
    sidecar_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert IRSA forced-photometry rows into the native-product assembler schema."""
    config = _validate_sidecar(sidecar)
    for label, digest in (("export_sha256", export_sha256), ("sidecar_sha256", sidecar_sha256)):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(digest)):
            raise ValueError(f"{label} must be a SHA-256 digest")

    accepted, excluded = [], []
    seen = set()
    service = config["service"]
    quality = config["quality_policy"]
    for index, raw in enumerate(rows):
        row = {_key(key): _scalar(value) for key, value in raw.items()}
        normalized = {name: row.get(_key(name)) for name in REQUIRED_COLUMNS}
        release = _release(normalized["data_collection"])
        detector = _detector(normalized["det_id"])
        lvf_id = str(normalized["lvf_id"] or "").strip()
        product_key = (lvf_id, detector, release)
        product = config["product_index"].get(product_key)
        if product is None:
            raise ValueError(f"IRSA row {index} has no exact LVF/detector/release product mapping: {product_key}")

        ra = _number(normalized["ra"], f"IRSA row {index} RA")
        dec = _number(normalized["dec"], f"IRSA row {index} Dec")
        if not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError(f"IRSA row {index} has invalid ICRS coordinates")
        candidates = []
        for source in config["sources"]:
            separation = _separation_arcsec(ra, dec, source["ra_deg"], source["dec_deg"])
            if separation <= config["source_position_tolerance_arcsec"]:
                candidates.append((separation, source))
        candidates.sort(key=lambda item: item[0])
        if not candidates:
            excluded.append({
                "row_index": index, "reason": "no_sidecar_source_within_position_tolerance",
                "ra_deg": ra, "dec_deg": dec,
            })
            continue
        if len(candidates) > 1:
            raise ValueError(
                f"IRSA row {index} lies within the matching tolerance of multiple catalogue sources"
            )
        source = candidates[0][1]
        separation = candidates[0][0]
        x_raw = _number(normalized["x_image"], f"IRSA row {index} x_image")
        y_raw = _number(normalized["y_image"], f"IRSA row {index} y_image")
        x, y = x_raw - config["image_pixel_origin"], y_raw - config["image_pixel_origin"]
        if x < 0 or y < 0:
            raise ValueError(f"IRSA row {index} image coordinates are outside the declared pixel convention")

        wavelength = _number(normalized["wavelength"], f"IRSA row {index} wavelength", positive=True)
        bandwidth = _number(normalized["lambda_width"], f"IRSA row {index} lambda_width", positive=True)
        flux_ujy = _number(normalized["flux"], f"IRSA row {index} flux")
        sigma_ujy = _number(normalized["flux_err"], f"IRSA row {index} flux_err", positive=True)
        try:
            flux_bkg_ujy = _number(normalized["flux_bkg"], f"IRSA row {index} flux_bkg")
        except ValueError:
            flux_bkg_ujy = None
        try:
            fit_ql = _number(normalized["fit_ql"], f"IRSA row {index} fit_ql")
        except ValueError:
            fit_ql = None
        flags = _integer(normalized["flags"], f"IRSA row {index} flags")
        if flags < 0:
            raise ValueError(f"IRSA row {index} flags must be non-negative")
        mjd = _number(normalized["mjd"], f"IRSA row {index} MJD", positive=True)
        deep = _boolean(normalized["deep_flg"], f"IRSA row {index} deep_flg")
        background_fraction = (
            abs(flux_bkg_ujy) / max(abs(flux_ujy), sigma_ujy)
            if flux_bkg_ujy is not None else None
        )
        known_flag_mask = sum(1 << bit for bit in FLAG_BITS.values())
        reasons = []
        if flags & config["flag_mask"]:
            reasons.append("excluded_by_predeclared_photometry_flag_policy")
        if flags & ~known_flag_mask:
            reasons.append("unrecognized_flag_bits_present")
        if fit_ql is None or fit_ql < 0 or fit_ql > quality["fit_ql_max"]:
            reasons.append("fit_ql_missing_or_outside_predeclared_quality_limit")
        if (
            background_fraction is None
            or background_fraction > quality["max_abs_background_to_flux_ratio"]
        ):
            reasons.append("background_fraction_missing_or_outside_predeclared_quality_limit")
        measurement_id = canonical_sha256({
            "export_sha256": export_sha256.lower(),
            "row_index": index,
            "source_id": source["source_id"],
            "archive_product_id": product["archive_product_id"],
            "mjd": mjd,
            "wavelength_um": wavelength,
        })
        if measurement_id in seen:
            raise ValueError(f"duplicate generated measurement id at IRSA row {index}")
        seen.add(measurement_id)
        quality_record = {
            "flags": flags,
            "flag_names": _flag_names(flags),
            "flag_policy": quality["flag_policy"],
            "fit_ql": fit_ql,
            "fit_ql_max": quality["fit_ql_max"],
            "flux_bkg_uJy": flux_bkg_ujy,
            "background_fraction": background_fraction,
            "background_fraction_max": quality["max_abs_background_to_flux_ratio"],
            "pass": not reasons,
        }
        if reasons:
            excluded.append({
                "row_index": index, "measurement_id": measurement_id,
                "source_id": source["source_id"],
                "archive_product_id": product["archive_product_id"],
                "mjd": mjd, "wavelength_um": wavelength,
                "quality": quality_record, "reasons": reasons,
            })
            continue
        accepted.append({
            "measurement_id": measurement_id,
            "source_id": source["source_id"],
            "archive_product_id": product["archive_product_id"],
            "mjd": mjd,
            "wavelength_um": wavelength,
            "bandwidth_um": bandwidth,
            "flux_jy": flux_ujy * 1e-6,
            "sigma_jy": sigma_ujy * 1e-6,
            "flux_unit": "Jy",
            "valid": True,
            "fit_status": "success",
            "photometry_method": "IRSA_SPHEREX_SPECTROPHOTOMETRY_TOOL",
            "quality_flags": quality_record["flag_names"],
            "photometry_flags": flags,
            "fit_ql": fit_ql,
            "flux_background": flux_bkg_ujy * 1e-6,
            "quality_policy_sha256": config["quality_policy_sha256"],
            "pixel_valid": True,
            "pixel_position": {
                "x": x, "y": y, "convention": "zero-based",
            },
            "ra_deg": ra,
            "dec_deg": dec,
            "image_wcs_tolerance_pixels": config["image_wcs_tolerance_pixels"],
            "requested_source_position_separation_arcsec": separation,
            "deep_flg": deep,
            "lvf_id": lvf_id,
            "det_id": detector,
            "data_collection": release,
        })

    if not accepted:
        raise ValueError("no IRSA rows passed the predeclared source matching and photometry quality rules")
    quality_policy = {
        **config["quality_policy"],
        "sha256": config["quality_policy_sha256"],
    }
    manifest = {
        "schema": "chronos-spherex-source-photometry/1.0",
        "dataset_class": "real",
        "extraction_method": {
            "kind": "hosted_service",
            "name": "IRSA SPHEREx Spectrophotometry Tool",
            "version": str(service["version"]),
            "service_uri": str(service["tool_uri"]),
            "job_id": str(service["job_id"]),
            "retrieved_utc": str(service["retrieved_utc"]),
            "configuration_sha256": str(service["configuration_sha256"]).lower(),
        },
        "photometry_quality_policy": quality_policy,
        "source_catalogue": config["source_catalogue"],
        "sources": config["sources"],
        "products": config["products"],
        "measurements": accepted,
        "import_provenance": {
            "schema": SCHEMA,
            "export_sha256": str(export_sha256).lower(),
            "sidecar_sha256": str(sidecar_sha256).lower(),
            "accepted_row_count": len(accepted),
            "excluded_row_count": len(excluded),
            "image_pixel_origin": config["image_pixel_origin"],
            "flux_input_unit": str(service["flux_unit"]),
            "flux_output_unit": "Jy",
            "quality_policy_sha256": config["quality_policy_sha256"],
        },
    }
    audit = {
        "schema": REPORT_SCHEMA,
        "status": "rows_imported_native_product_verification_required",
        "export_sha256": str(export_sha256).lower(),
        "sidecar_sha256": str(sidecar_sha256).lower(),
        "measurement_rows_seen": len(rows),
        "measurement_rows_accepted_for_native_verification": len(accepted),
        "measurement_rows_excluded": len(excluded),
        "excluded_rows": excluded,
        "scientific_boundaries": [
            "IRSA rows are targeted/forced source-photometry measurements; they are not an independent blind source detection.",
            "The sidecar must bind each LVF/detector/release tuple to the exact archive product ID and local native FITS products.",
            "The stated x_image/y_image pixel origin is applied explicitly; source sky coordinates are checked against the native IMAGE WCS by the assembler.",
            "Flux and uncertainty are converted from microjansky to jansky exactly once.",
            "Rows failing the frozen flag, fit_ql or background-fraction rules are retained in this audit and excluded from the analysis manifest.",
            "Native science, variance, CWAVE, CBAND, ePSF and solid-angle files still require local checksum and pixel-level verification.",
            "This import alone does not establish source classification, a population selection function, a YSO population result or independent reproduction.",
        ],
    }
    return manifest, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="IRSA Spectrophotometry Tool VOTable/XML or CSV export")
    parser.add_argument("--sidecar", type=Path, required=True, help="JSON sidecar with exact source and native-product mappings")
    parser.add_argument("--out", type=Path, default=Path("data/source_timeseries/irsa_source_timeseries.json"))
    parser.add_argument("--minimum-epochs", type=int, default=2)
    args = parser.parse_args()

    sidecar_bytes = args.sidecar.read_bytes()
    sidecar = json.loads(sidecar_bytes)
    rows = load_irsa_rows(args.export)
    manifest, audit = build_source_photometry_manifest(
        rows, sidecar,
        export_sha256=sha256_file(args.export),
        sidecar_sha256=hashlib.sha256(sidecar_bytes).hexdigest(),
    )
    assembled = assemble_source_timeseries(
        manifest, minimum_epochs=args.minimum_epochs, verify_files=True,
    )
    report = {
        "schema": REPORT_SCHEMA,
        "status": "native_source_timeseries_verified",
        "import_audit": audit,
        "assembled_source_timeseries": assembled,
        "boundaries": [
            "This verifies submitted extraction rows and native FITS provenance; it does not independently reproduce the hosted service's photometry algorithm.",
            "Population claims remain blocked until real-field injection/recovery selection calibration and the preregistered null-control gates pass.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "accepted_measurements": audit["measurement_rows_accepted_for_native_verification"],
        "excluded_measurements": audit["measurement_rows_excluded"],
        "verified_sources": assembled["usable_source_count"],
        "unusable_sources": assembled["unusable_source_count"],
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
