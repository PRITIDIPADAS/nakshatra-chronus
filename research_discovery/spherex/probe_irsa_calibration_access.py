#!/usr/bin/env python3
"""Probe the documented IRSA DR1 calibration TAP collection and directory endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from astroquery.ipac.irsa import Irsa


def scalar(value):
    if value is None:
        return None
    try:
        return value.item()
    except Exception:
        return str(value)


def table_rows(query):
    result = Irsa.query_tap(query)
    table = result.to_table() if hasattr(result, "to_table") else result
    return {
        "query": query,
        "columns": list(table.colnames),
        "row_count": len(table),
        "rows": [
            {name: scalar(row[name]) for name in table.colnames}
            for row in table
        ],
    }


def main():
    out = Path("data/irsa_calibration_probe")
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    report = {"started_utc": started, "directory_probes": [], "tap": {}, "errors": []}
    urls = [
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/spectral_wcs/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/solid_angle_pixel_map/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/abs_gain_matrix/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/spectral_wcs/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/solid_angle_pixel_map/",
        "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr3/abs_gain_matrix/",
    ]
    session = requests.Session()
    for url in urls:
        item = {"url": url}
        try:
            response = session.get(url, timeout=45, allow_redirects=True)
            item.update({
                "status_code": response.status_code,
                "final_url": response.url,
                "content_type": response.headers.get("Content-Type"),
                "sample": response.text[:1000] if response.headers.get("Content-Type", "").startswith("text/") else None,
            })
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        report["directory_probes"].append(item)

    queries = {
        "tables": "SELECT schema_name, table_name, description FROM TAP_SCHEMA.tables",
        "spherex_columns": (
            "SELECT table_name, column_name, datatype, description "
            "FROM TAP_SCHEMA.columns WHERE schema_name = 'spherex'"
        ),
        "all_collection_columns": (
            "SELECT table_name, column_name, datatype, description "
            "FROM TAP_SCHEMA.columns WHERE LOWER(table_name) LIKE '%cal%' "
            "OR LOWER(table_name) LIKE '%artifact%'"
        ),
    }
    for key, query in queries.items():
        try:
            report["tap"][key] = table_rows(query)
        except Exception as exc:
            report["errors"].append({
                "stage": key, "query": query,
                "error": f"{type(exc).__name__}: {exc}",
            })

    names = []
    for row in report.get("tap", {}).get("tables", {}).get("rows", []):
        full = f"{row.get('schema_name')}.{row.get('table_name')}"
        text = full.lower()
        if "spherex" in text or "cal" in text:
            names.append(full)
    report["candidate_tables"] = names

    candidates = ["spherex_dr1_cal", "spherex.dr1_cal", "spherex.artifact"]
    candidates.extend(name for name in names if name not in candidates)
    report["tap_table_probes"] = []
    seen = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        query = f"SELECT TOP 5 * FROM {name}"
        try:
            report["tap_table_probes"].append(table_rows(query))
        except Exception as exc:
            report["tap_table_probes"].append({
                "query": query,
                "error": f"{type(exc).__name__}: {exc}",
            })

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "irsa_calibration_probe.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({
        "directory_probes": [
            {k: item.get(k) for k in ("url", "status_code", "final_url", "error")}
            for item in report["directory_probes"]
        ],
        "tap_table_count": report.get("tap", {}).get("tables", {}).get("row_count"),
        "candidate_tables": names,
        "tap_probe_results": [
            {"query": item.get("query"), "row_count": item.get("row_count"),
             "columns": item.get("columns"), "error": item.get("error")}
            for item in report["tap_table_probes"]
        ],
        "errors": report["errors"],
        "output": str(out / "irsa_calibration_probe.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
