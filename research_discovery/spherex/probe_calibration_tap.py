#!/usr/bin/env python3
"""Inspect IRSA TAP_SCHEMA for the live SPHEREx calibration inventory.

The archive guide refers to spherex_dr1_cal as a calibration collection, but
that label is not necessarily an ADQL table name. This script first enumerates
TAP_SCHEMA and then records all matching table definitions and column schemas.
It does not infer calibration compatibility.
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
    if not hasattr(table, "colnames") or not hasattr(table, "write"):
        table = Table(table)
    return table


def _rows(table):
    return [
        {str(name): _plain(row[name]) for name in table.colnames}
        for row in table
    ]


def inspect_calibration_collection(sample_rows: int = 50) -> dict[str, Any]:
    from astroquery.ipac.irsa import Irsa

    tables_query = (
        "SELECT TOP 500 * FROM TAP_SCHEMA.tables "
        "WHERE LOWER(table_name) LIKE '%spherex%' "
        "OR LOWER(schema_name) LIKE '%spherex%'"
    )
    tables = normalize_tap_results(Irsa.query_tap(tables_query))
    table_rows = _rows(tables)

    columns_query = (
        "SELECT TOP 2000 * FROM TAP_SCHEMA.columns "
        "WHERE LOWER(table_name) LIKE '%spherex%'"
    )
    columns = normalize_tap_results(Irsa.query_tap(columns_query))
    column_rows = _rows(columns)

    started = datetime.now(timezone.utc).isoformat()
    return {
        "schema": "spherex-dr1-cal-tap-inspection/1.1",
        "started_utc": started,
        "intended_calibration_collection": "spherex_dr1_cal",
        "tables_query": tables_query,
        "table_count": len(tables),
        "table_columns": [str(x) for x in tables.colnames],
        "matching_tables": table_rows,
        "columns_query": columns_query,
        "column_count": len(columns),
        "columns_schema": [str(x) for x in columns.colnames],
        "matching_columns": column_rows,
        "interpretation": (
            "TAP_SCHEMA records show the actual searchable ADQL tables and columns. "
            "The collection label spherex_dr1_cal must not be treated as a table name "
            "unless it appears in this registry."
        ),
        "warning": (
            "This is a live TAP metadata inspection only. No calibration file is "
            "selected or deemed compatible. Match release, detector, product version, "
            "processing provenance, FITS content and the Level-2 science pipeline."
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
        "table_count": report["table_count"],
        "matching_tables": report["matching_tables"],
        "column_count": report["column_count"],
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
