#!/usr/bin/env python3
"""Inspect the documented IRSA DR1 calibration TAP collection.

This diagnostic does not infer science/calibration compatibility. It records
the exact TAP query, returned column schema, sample rows and URL-like fields
so calibration discovery can be implemented against the live archive schema.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from astropy.table import Table


def _plain(value: Any):
    if value is None or np.ma.is_masked(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def normalize_tap_results(result):
    """Normalize Astroquery/PyVO results across property/method API variants."""
    converter = getattr(result, "to_table", None)
    if callable(converter):
        table = converter()
    elif converter is not None:
        table = converter
    elif hasattr(result, "colnames") and hasattr(result, "write"):
        table = result
    else:
        names = getattr(result, "fieldnames", None) or getattr(result, "colnames", None)
        getter = getattr(result, "getcolumn", None)
        if names and callable(getter):
            table = Table({str(name): getter(name) for name in names})
        else:
            votable = getattr(result, "votable", None)
            if votable is not None and hasattr(votable, "iter_tables"):
                elements = list(votable.iter_tables())
                if not elements:
                    raise TypeError("IRSA TAP response contains no VOTable table")
                table = elements[0].to_table(use_names_over_ids=True)
            else:
                raise TypeError(
                    "IRSA TAP result cannot be converted to Astropy Table; "
                    f"type={type(result).__name__}, fields={names!r}"
                )
    if not hasattr(table, "colnames"):
        table = Table(table)
    if not hasattr(table, "write"):
        table = Table(table)
    return table


def inspect_calibration_collection(sample_rows: int = 50) -> dict[str, Any]:
    from astroquery.ipac.irsa import Irsa

    query = f"SELECT TOP {int(sample_rows)} * FROM spherex_dr1_cal"
    started = datetime.now(timezone.utc).isoformat()
    result = Irsa.query_tap(query)
    table = normalize_tap_results(result)
    rows = []
    candidate_fields = set()
    for row in table:
        item = {str(name): _plain(row[name]) for name in table.colnames}
        rows.append(item)
        for name, value in item.items():
            if isinstance(value, str) and (
                ".fits" in value.lower() or ".yaml" in value.lower()
                or ".ecsv" in value.lower() or "ibe/data/spherex" in value.lower()
                or value.lower().startswith("s3://")
            ):
                candidate_fields.add(name)
    return {
        "schema": "spherex-dr1-cal-tap-inspection/1.0",
        "started_utc": started,
        "query": query,
        "table_name": "spherex_dr1_cal",
        "returned_rows": len(table),
        "columns": [
            {"name": str(name), "dtype": str(table[name].dtype)}
            for name in table.colnames
        ],
        "url_or_filename_columns": sorted(candidate_fields),
        "sample_rows": rows,
        "warning": (
            "This is a live TAP schema inspection only. Rows are not yet selected "
            "as compatible calibrations; release, detector, processing provenance, "
            "FITS content and science-pipeline compatibility must be verified."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("spherex_dr1_cal_tap_inspection.json"))
    args = parser.parse_args()
    if not 1 <= args.rows <= 1000:
        parser.error("--rows must be between 1 and 1000")
    report = inspect_calibration_collection(args.rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "table": report["table_name"],
        "rows": report["returned_rows"],
        "columns": [item["name"] for item in report["columns"]],
        "url_or_filename_columns": report["url_or_filename_columns"],
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
