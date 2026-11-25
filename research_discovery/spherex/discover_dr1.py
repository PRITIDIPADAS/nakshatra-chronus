#!/usr/bin/env python3
"""Discover/download public SPHEREx DR1 and QR3 Level-2 MEFs through IRSA SIA2.

Calibration files are intentionally not fetched through SIA2: IRSA documents
those under the browsable calibration directories instead.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
DEFAULT_COLLECTIONS = ("spherex_dr1", "spherex_qr3")


def _table_from_votable(payload: bytes):
    try:
        from astropy.io.votable import parse_single_table
    except ImportError as exc:
        raise RuntimeError("Install astropy to parse IRSA SIA2 VOTable responses") from exc
    return parse_single_table(io.BytesIO(payload)).to_table()


def query_sia(*, ra_deg: float, dec_deg: float, radius_deg: float,
              collections: tuple[str, ...] = DEFAULT_COLLECTIONS,
              mjd_start: float | None = None, mjd_end: float | None = None,
              wavelength_min_um: float | None = None,
              wavelength_max_um: float | None = None,
              maxrec: int = 1000, timeout: int = 90):
    """Return the Astropy table from the documented IRSA SIA2 endpoint."""
    if not (-360 <= ra_deg <= 360 and -90 <= dec_deg <= 90):
        raise ValueError("RA/Dec are not in a valid degree range")
    if radius_deg <= 0 or radius_deg > 180:
        raise ValueError("radius_deg must be in (0, 180]")
    if not collections:
        raise ValueError("At least one SIA2 collection is required")
    params: list[tuple[str, str]] = [("COLLECTION", c) for c in collections]
    params += [("POS", f"CIRCLE {ra_deg} {dec_deg} {radius_deg}"),
               ("MAXREC", str(maxrec)), ("RESPONSEFORMAT", "VOTABLE")]
    if (mjd_start is None) != (mjd_end is None):
        raise ValueError("Supply both mjd_start and mjd_end, or neither")
    if mjd_start is not None:
        if mjd_end < mjd_start:
            raise ValueError("mjd_end must not precede mjd_start")
        params.append(("TIME", f"{mjd_start} {mjd_end}"))
    if (wavelength_min_um is None) != (wavelength_max_um is None):
        raise ValueError("Supply both wavelength limits, or neither")
    if wavelength_min_um is not None:
        if wavelength_min_um <= 0 or wavelength_max_um <= wavelength_min_um:
            raise ValueError("Wavelength limits must be positive and increasing")
        # SIA BAND values are metres, not microns.
        params.append(("BAND", f"{wavelength_min_um * 1e-6} {wavelength_max_um * 1e-6}"))
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("Install requests to query IRSA") from exc
    response = requests.get(SIA_URL, params=params, timeout=timeout)
    response.raise_for_status()
    table = _table_from_votable(response.content)
    return table, response.url


def _safe_filename(url: str, fallback: str) -> str:
    name = os.path.basename(urlparse(url).path)
    return name if name and "." in name else fallback


def download_manifest(table, outdir: Path, *, limit: int | None = None,
                      timeout: int = 180) -> list[dict[str, Any]]:
    """Download products atomically and retain failures/partials as explicit records."""
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("Install requests to download SPHEREx FITS files") from exc
    if "access_url" not in table.colnames:
        raise ValueError(f"SIA response has no access_url column: {table.colnames}")
    outdir.mkdir(parents=True, exist_ok=True)
    rows = table if limit is None else table[:limit]
    manifest: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        raw_url = str(row["access_url"]).strip()
        item = {str(k): (None if str(row[k]).lower() in {"masked", "none", "nan"} else str(row[k]))
                for k in table.colnames}
        if not raw_url or raw_url.lower() == "masked":
            item.update({"status": "rejected", "error": "SIA2 row has no access_url"})
            manifest.append(item)
            continue
        url = raw_url
        fname = _safe_filename(url, f"spherex_dr1_{i:05d}.fits")
        dest = outdir / f"{i:05d}_{fname}"
        tmp = dest.with_suffix(dest.suffix + ".part")
        digest = hashlib.sha256()
        nbytes = 0
        response = None
        try:
            response = requests.get(url, timeout=(30, timeout), stream=True)
            response.raise_for_status()
            expected = response.headers.get("Content-Length")
            with tmp.open("wb") as f:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        f.write(block)
                        digest.update(block)
                        nbytes += len(block)
                f.flush()
                os.fsync(f.fileno())
            if expected is not None and nbytes != int(expected):
                raise IOError(f"Content-Length mismatch: expected {expected}, received {nbytes}")
            with tmp.open("rb") as f:
                signature = f.read(8)
            if signature != b"SIMPLE  ":
                raise IOError(f"Downloaded payload is not a primary FITS file: {signature!r}")
            tmp.replace(dest)
            item.update({"status": "downloaded", "local_path": str(dest), "bytes": nbytes,
                         "sha256": digest.hexdigest(), "source_url": url})
        except Exception as exc:
            status = "partial" if tmp.exists() and tmp.stat().st_size else "failed"
            item.update({"status": status, "local_path": str(tmp) if status == "partial" else None,
                         "bytes": nbytes if nbytes else None, "sha256": None,
                         "source_url": url, "error": f"{type(exc).__name__}: {exc}"})
            if status == "failed":
                tmp.unlink(missing_ok=True)
        if response is not None:
            item.update({"http_status": response.status_code, "etag": response.headers.get("ETag"),
                         "last_modified": response.headers.get("Last-Modified"),
                         "content_type": response.headers.get("Content-Type")})
        manifest.append(item)
        print(f"[{len(manifest)}] {fname}: {item['status']}" +
              (f" ({nbytes:,} bytes)" if nbytes else ""))
    (outdir / "download_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ra", type=float, required=True, help="ICRS RA in degrees")
    p.add_argument("--dec", type=float, required=True, help="ICRS Dec in degrees")
    p.add_argument("--radius", type=float, default=0.2, help="Search radius in degrees")
    p.add_argument("--collections", nargs="+", default=list(DEFAULT_COLLECTIONS))
    p.add_argument("--mjd-start", type=float)
    p.add_argument("--mjd-end", type=float)
    p.add_argument("--min-um", type=float)
    p.add_argument("--max-um", type=float)
    p.add_argument("--maxrec", type=int, default=1000)
    p.add_argument("--download", action="store_true")
    p.add_argument("--limit", type=int, help="Maximum number of MEFs to download")
    p.add_argument("--out", type=Path, default=Path("data/spherex_dr1"))
    args = p.parse_args()
    table, query_url = query_sia(ra_deg=args.ra, dec_deg=args.dec,
        radius_deg=args.radius, collections=tuple(args.collections),
        mjd_start=args.mjd_start, mjd_end=args.mjd_end,
        wavelength_min_um=args.min_um, wavelength_max_um=args.max_um,
        maxrec=args.maxrec)
    args.out.mkdir(parents=True, exist_ok=True)
    table.write(args.out / "sia_results.csv", format="ascii.csv", overwrite=True)
    from datetime import datetime, timezone
    retrieved_utc = datetime.now(timezone.utc).isoformat()
    query_metadata = {
        "query_url": query_url, "collections": args.collections,
        "ra_deg": args.ra, "dec_deg": args.dec, "radius_deg": args.radius,
        "mjd_start": args.mjd_start, "mjd_end": args.mjd_end,
        "row_count": len(table), "maxrec": args.maxrec,
        "wavelength_min_um": args.min_um, "wavelength_max_um": args.max_um,
    }
    query_metadata["retrieved_utc"] = retrieved_utc
    query_metadata["download_scope"] = "all SIA2 rows" if args.download and args.limit is None else (f"first {args.limit} rows downloaded" if args.download else "discovery only; no files downloaded")
    (args.out / "query.json").write_text(json.dumps(query_metadata, indent=2))
    print(f"IRSA returned {len(table)} rows. Saved {args.out / 'sia_results.csv'}")
    downloads = download_manifest(table, args.out / "fits", limit=args.limit) if args.download else []
    from research_discovery.spherex.archive_manifest import manifest_from_sia, validate_manifest
    sia_rows = [{str(k): (None if str(row[k]).lower() in {"masked", "none", "nan"} else str(row[k]))
                 for k in table.colnames} for row in table]
    archive_manifest = manifest_from_sia(sia_rows, query_url=query_url,
        query_metadata=query_metadata, downloads=downloads, retrieved_utc=retrieved_utc)
    (args.out / "archive_manifest.json").write_text(json.dumps(archive_manifest, indent=2, default=str))
    validation = validate_manifest(archive_manifest, verify_local=args.download, base_dir=Path.cwd())
    (args.out / "archive_manifest_validation.json").write_text(json.dumps(validation, indent=2))
    print(f"Saved versioned archive manifest with {validation['product_count']} products; valid={validation['valid']}")
    if not validation["valid"]:
        raise SystemExit("Archive manifest has validation issues; inspect archive_manifest_validation.json")

if __name__ == "__main__":
    main()
