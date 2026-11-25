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

    # IRSA catalogue registry: the guide calls this a TAP "collection",
    # which may not be the physical ADQL table name.
    try:
        catalogues = Irsa.list_catalogs(filter="spherex")
        report["irsa_catalogues_spherex"] = [str(x) for x in catalogues]
    except Exception as exc:
        report["irsa_catalogues_spherex_error"] = f"{type(exc).__name__}: {exc}"
    try:
        columns = Irsa.list_columns("spherex_dr1_cal")
        report["spherex_dr1_cal_columns"] = [
            {"name": str(getattr(row, "name", "")),
             "type": str(getattr(row, "type", "")),
             "description": str(getattr(row, "description", ""))}
            for row in columns
        ]
    except Exception as exc:
        report["spherex_dr1_cal_columns_error"] = f"{type(exc).__name__}: {exc}"

    # Resolve a real M101 DR1 science artifact to its CAOM plane, then join
    # the exact calibration input planes through provenance_input.
    science_filename = "level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits"
    science_identity_query = (
        "SELECT TOP 5 planeid, artifactid, uri, producttype, releasetype "
        "FROM spherex.artifact "
        f"WHERE LOWER(uri) LIKE '%{science_filename.lower()}%' "
        "AND producttype = 'science' AND releasetype = 'data'"
    )
    try:
        science_identity = table_rows(science_identity_query)
        report["m101_science_identity"] = science_identity
        plane_ids = [
            str(row.get("planeid")) for row in science_identity.get("rows", [])
            if row.get("planeid")
        ]
        report["m101_calibration_provenance"] = []
        for plane_id in plane_ids:
            safe_id = plane_id.replace("'", "''")
            provenance_query = (
                "SELECT pi.outputid, pi.inputid, "
                "ip.provenance_name, ip.provenance_version, ip.provenance_runid, "
                "ip.provenance_lastexecuted, "
                "ia.artifactid AS input_artifactid, ia.uri AS input_uri, "
                "ia.producttype AS input_producttype, ia.releasetype AS input_releasetype, "
                "ia.contenttype AS input_contenttype, ia.contentlength AS input_contentlength, "
                "ia.contentchecksum AS input_contentchecksum "
                "FROM spherex.provenance_input pi "
                "LEFT JOIN spherex.plane ip ON ip.planeid = pi.inputid "
                "LEFT JOIN spherex.artifact ia ON ia.planeid = pi.inputid "
                f"WHERE pi.outputid = '{safe_id}'"
            )
            try:
                joined = table_rows(provenance_query)
                joined["output_planeid"] = plane_id
                report["m101_calibration_provenance"].append(joined)
            except Exception as exc:
                report["m101_calibration_provenance"].append({
                    "output_planeid": plane_id,
                    "query": provenance_query,
                    "error": f"{type(exc).__name__}: {exc}",
                })
    except Exception as exc:
        report["m101_science_identity"] = {
            "query": science_identity_query,
            "error": f"{type(exc).__name__}: {exc}",
        }
        report["m101_calibration_provenance"] = []

    # Inspect all artifact classes and the calibration URI families directly.
    # This detects whether calibrations are exposed by the standard artifact
    # table even when the separate collection label is not an ADQL table.
    artifact_queries = {
        "artifact_product_release_counts": (
            "SELECT producttype, releasetype, COUNT(*) AS n "
            "FROM spherex.artifact GROUP BY producttype, releasetype"
        ),
        "artifact_spectral_wcs": (
            "SELECT TOP 20 artifactid, uri, producttype, releasetype, contenttype, "
            "contentlength, contentchecksum FROM spherex.artifact "
            "WHERE LOWER(uri) LIKE '%spectral_wcs%'"
        ),
        "artifact_solid_angle": (
            "SELECT TOP 20 artifactid, uri, producttype, releasetype, contenttype, "
            "contentlength, contentchecksum FROM spherex.artifact "
            "WHERE LOWER(uri) LIKE '%solid_angle%'"
        ),
        "artifact_absolute_gain": (
            "SELECT TOP 20 artifactid, uri, producttype, releasetype, contenttype, "
            "contentlength, contentchecksum FROM spherex.artifact "
            "WHERE LOWER(uri) LIKE '%abs_gain_matrix%'"
        ),
        "artifact_calibration_type": (
            "SELECT TOP 50 artifactid, uri, producttype, releasetype, contenttype, "
            "contentlength, contentchecksum FROM spherex.artifact "
            "WHERE LOWER(producttype) LIKE '%cal%' OR LOWER(releasetype) LIKE '%cal%'"
        ),
    }
    report["artifact_queries"] = {}
    for key, query in artifact_queries.items():
        try:
            report["artifact_queries"][key] = table_rows(query)
        except Exception as exc:
            report["artifact_queries"][key] = {
                "query": query, "error": f"{type(exc).__name__}: {exc}"
            }

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
        "irsa_catalogues_spherex": report.get("irsa_catalogues_spherex"),
        "irsa_catalogues_spherex_error": report.get("irsa_catalogues_spherex_error"),
        "spherex_dr1_cal_columns": report.get("spherex_dr1_cal_columns"),
        "spherex_dr1_cal_columns_error": report.get("spherex_dr1_cal_columns_error"),
        "artifact_query_results": {
            key: {"row_count": value.get("row_count"),
                  "columns": value.get("columns"),
                  "rows": value.get("rows", [])[:3],
                  "error": value.get("error")}
            for key, value in report.get("artifact_queries", {}).items()
        },
        "errors": report["errors"],
        "output": str(out / "irsa_calibration_probe.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
