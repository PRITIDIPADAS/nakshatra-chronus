#!/usr/bin/env python3
"""Query IRSA's documented SPHEREx TAP tables and fetch native Level-2 MEFs.

This follows IRSA's public cutout tutorial query but deliberately retrieves the
underlying native MEF URI (a.uri), not a small image cutout. Full MEFs are about
70 MB each. Downloads are checksummed and written atomically. The script does
not choose calibration files or claim calibration compatibility.

Example:
  python -m research_discovery.spherex.fetch_native_mefs \
    --field M101,210.80227,54.34895 \
    --field M31,10.6847,41.2692 \
    --bandpass SPHEREx-D2 --limit-per-field 3 --out data/spherex_native

Requires: astroquery, astropy, requests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

IRSA_ROOT = "https://irsa.ipac.caltech.edu/"

@dataclass(frozen=True)
class Field:
    name: str
    ra_deg: float
    dec_deg: float


def parse_field(value: str) -> Field:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("field must be NAME,RA_DEG,DEC_DEG")
    name, ra, dec = parts
    try:
        f = Field(name=name, ra_deg=float(ra), dec_deg=float(dec))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("RA and Dec must be numeric degrees") from exc
    if not name or not 0 <= f.ra_deg < 360 or not -90 <= f.dec_deg <= 90:
        raise argparse.ArgumentTypeError("invalid field name or ICRS coordinate range")
    return f


def tap_query(field: Field, bandpass: str):
    if not re.fullmatch(r"SPHEREx-D[1-6]", bandpass):
        raise ValueError("bandpass must be SPHEREx-D1 through SPHEREx-D6")
    try:
        from astroquery.ipac.irsa import Irsa
    except ImportError as exc:
        raise RuntimeError("Install astroquery and astropy: pip install astroquery astropy") from exc
    # Same tables, point-in-polygon predicate and columns demonstrated by the
    # official IRSA SPHEREx cutout tutorial. We omit the cutout URL suffix so
    # the downloaded URI is the original native MEF.
    sql = f"""
    SELECT
        a.uri AS artifact_uri,
        p.time_bounds_lower AS time_bounds_lower,
        p.time_bounds_upper AS time_bounds_upper,
        p.energy_bandpassname AS energy_bandpassname
    FROM spherex.artifact a
    JOIN spherex.plane p ON a.planeid = p.planeid
    WHERE 1 = CONTAINS(POINT('ICRS', {field.ra_deg:.10f}, {field.dec_deg:.10f}), p.poly)
      AND p.energy_bandpassname = '{bandpass}'
    ORDER BY p.time_bounds_lower
    """
    table = Irsa.query_tap(sql)
    return sql, table


def _safe_basename(uri: str) -> str:
    name = Path(urlparse(uri).path).name
    if not name.lower().endswith(".fits") or not name.startswith("level2_"):
        raise ValueError(f"Unexpected MEF URI; refusing to save as FITS: {uri}")
    return name


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_native_mef(uri: str, destination: Path, timeout: int = 180,
                        retries: int = 3) -> dict[str, Any]:
    import requests
    url = uri if uri.startswith("https://") else urljoin(IRSA_ROOT, uri.lstrip("/"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=(30, timeout)) as response:
                response.raise_for_status()
                expected = response.headers.get("Content-Length")
                digest = hashlib.sha256()
                nbytes = 0
                with temporary.open("wb") as out:
                    for block in response.iter_content(1024 * 1024):
                        if not block:
                            continue
                        out.write(block)
                        digest.update(block)
                        nbytes += len(block)
                    out.flush()
                    os.fsync(out.fileno())
                if expected is not None and nbytes != int(expected):
                    raise IOError(f"Content-Length mismatch: expected {expected}, received {nbytes}")
                with temporary.open("rb") as check:
                    signature = check.read(8)
                if signature != b"SIMPLE  ":
                    raise IOError(f"Downloaded file does not start with FITS SIMPLE signature: {signature!r}")
                temporary.replace(destination)
                return {
                    "status": "downloaded", "source_url": url,
                    "local_path": str(destination), "bytes": nbytes,
                    "sha256": digest.hexdigest(),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "content_type": response.headers.get("Content-Type"),
                    "http_status": response.status_code,
                }
        except Exception as exc:  # preserve failure in the manifest and retry
            last_error = f"{type(exc).__name__}: {exc}"
            temporary.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    return {"status": "failed", "source_url": url, "error": last_error}


def run(fields: list[Field], bandpass: str, outdir: Path,
        limit_per_field: int, download: bool = True) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    inventory: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive": "IRSA SPHEREx TAP: spherex.artifact JOIN spherex.plane",
        "bandpass": bandpass,
        "retrieval_type": "native uncut Level-2 MEF via a.uri; not image cutouts",
        "field_results": [],
        "warning": "A successful HTTP download and FITS signature do not establish calibration compatibility or scientific validity.",
    }
    all_manifest_rows: list[dict[str, Any]] = []
    for field in fields:
        print(f"Querying {field.name}: RA={field.ra_deg}, Dec={field.dec_deg}, {bandpass}")
        sql, table = tap_query(field, bandpass)
        query_dir = outdir / field.name
        query_dir.mkdir(parents=True, exist_ok=True)
        table.write(query_dir / "tap_results.csv", format="ascii.csv", overwrite=True)
        rows = list(table[:limit_per_field]) if limit_per_field else list(table)
        field_info = {
            **asdict(field), "tap_row_count": len(table),
            "download_limit": limit_per_field,
            "query": sql, "downloads": [],
        }
        for i, row in enumerate(rows):
            raw_uri = str(row["artifact_uri"])
            if not raw_uri or raw_uri.lower() == "masked":
                continue
            uri = raw_uri if raw_uri.startswith("http") else urljoin(IRSA_ROOT, raw_uri.lstrip("/"))
            try:
                fname = _safe_basename(uri)
            except ValueError as exc:
                item = {"field": field.name, "status": "rejected", "artifact_uri": raw_uri, "error": str(exc)}
                field_info["downloads"].append(item); all_manifest_rows.append(item); continue
            destination = query_dir / fname
            record = {
                "field": field.name, "ra_deg": field.ra_deg, "dec_deg": field.dec_deg,
                "time_bounds_lower": str(row["time_bounds_lower"]),
                "time_bounds_upper": str(row["time_bounds_upper"]),
                "energy_bandpassname": str(row["energy_bandpassname"]),
                "artifact_uri": raw_uri,
            }
            if download:
                result = download_native_mef(uri, destination)
                record.update(result)
            else:
                record.update({"status": "discovered_not_downloaded", "source_url": uri})
            field_info["downloads"].append(record)
            all_manifest_rows.append(record)
            print(f"  [{i+1}/{len(rows)}] {fname}: {record['status']}")
        inventory["field_results"].append(field_info)
    (outdir / "native_mef_manifest.json").write_text(json.dumps(inventory, indent=2, default=str))
    with (outdir / "native_mef_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        if all_manifest_rows:
            keys = sorted({key for row in all_manifest_rows for key in row})
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader(); writer.writerows(all_manifest_rows)
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", action="append", type=parse_field,
        help="NAME,RA_DEG,DEC_DEG; repeat to include more independent sky fields")
    parser.add_argument("--bandpass", default="SPHEREx-D2",
        help="One IRSA energy_bandpassname, e.g. SPHEREx-D2")
    parser.add_argument("--limit-per-field", type=int, default=4,
        help="Maximum number of native MEFs to download for each field; 0 means all rows")
    parser.add_argument("--out", type=Path, default=Path("data/spherex_native"))
    parser.add_argument("--discover-only", action="store_true", help="Save TAP metadata without downloading MEFs")
    args = parser.parse_args()
    if args.limit_per_field < 0:
        parser.error("--limit-per-field must be >= 0")
    fields = args.field or [parse_field("M101,210.80227,54.34895")]
    result = run(fields, args.bandpass, args.out, args.limit_per_field, not args.discover_only)
    n = sum(len(x["downloads"]) for x in result["field_results"])
    print(f"Processed {n} candidate MEFs. Manifest: {args.out / 'native_mef_manifest.json'}")

if __name__ == "__main__":
    main()
