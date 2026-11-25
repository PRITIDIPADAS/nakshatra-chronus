#!/usr/bin/env python3
"""Resolve calibration inputs linked to an exact SPHEREx science artifact via IRSA TAP."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from astroquery.ipac.irsa import Irsa

DEFAULT_URI = (
    "ibe/data/spherex/dr1/level2/2025W19_2B/"
    "l2b-v27-2026-198/2/"
    "level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits"
)


def to_rows(query: str):
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
    return {"query": query, "columns": list(table.colnames), "row_count": len(rows), "rows": rows}


def safe_query(report, key, query):
    try:
        value = to_rows(query)
    except Exception as exc:
        value = {"query": query, "row_count": 0, "rows": [],
                 "error": f"{type(exc).__name__}: {exc}"}
        report["errors"].append({"stage": key, "error": value["error"], "query": query})
    report["queries"][key] = value
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--science-uri", default=DEFAULT_URI)
    p.add_argument("--out", type=Path, default=Path("data/irsa_provenance_inputs"))
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    uri = args.science_uri.strip().replace("'", "''")
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive": "NASA/IPAC IRSA SPHEREx TAP",
        "science_uri": args.science_uri,
        "queries": {},
        "errors": [],
        "matching_basis": "Explicit provenance_input.outputid foreign key to science planeid, followed by planeid-to-artifact lookup.",
    }

    q1 = f"""
    SELECT a.uri AS science_uri, a.planeid AS science_planeid,
      a.producttype AS science_producttype, a.contentlength AS science_contentlength,
      a.contentchecksum AS science_contentchecksum, p.obsid AS science_obsid,
      p.productid AS science_productid, p.provenance_name AS science_provenance_name,
      p.provenance_version AS science_provenance_version,
      p.provenance_runid AS science_provenance_runid,
      p.provenance_lastexecuted AS science_provenance_lastexecuted,
      p.provenance_keywords AS science_provenance_keywords,
      p.time_bounds_lower AS time_bounds_lower, p.time_bounds_upper AS time_bounds_upper,
      p.time_exposure AS time_exposure, p.energy_bandpassname AS energy_bandpassname,
      p.position_dimension_naxis1 AS naxis1, p.position_dimension_naxis2 AS naxis2,
      o.collection AS collection, o.observationid AS observationid,
      o.intent AS intent, o.target_name AS target_name
    FROM spherex.artifact a
    JOIN spherex.plane p ON p.planeid = a.planeid
    JOIN spherex.observation o ON o.obsid = p.obsid
    WHERE a.uri = '{uri}'
    """
    science = safe_query(report, "science_artifact", q1)
    science_rows = science.get("rows", [])
    report["queries"]["provenance_inputs"] = []
    report["queries"]["calibration_planes"] = []
    report["queries"]["calibration_artifacts"] = []

    for science_row in science_rows:
        plane_id = str(science_row.get("science_planeid") or "").replace("'", "''")
        if not plane_id:
            continue
        q2 = (
            "SELECT inputid, outputid FROM spherex.provenance_input "
            f"WHERE outputid = '{plane_id}'"
        )
        prov = safe_query(report, f"provenance_inputs_{plane_id}", q2)
        report["queries"]["provenance_inputs"].append(prov)
        for relation in prov.get("rows", []):
            input_id = str(relation.get("inputid") or "").replace("'", "''")
            if not input_id:
                continue
            q3 = (
                "SELECT planeid, obsid, productid, provenance_name, provenance_reference, "
                "provenance_version, provenance_project, provenance_producer, provenance_runid, "
                "provenance_lastexecuted, provenance_keywords, datarelease, calibrationlevel, "
                "dataproducttype, position_dimension_naxis1, position_dimension_naxis2 "
                "FROM spherex.plane "
                f"WHERE planeid = '{input_id}'"
            )
            cal_plane = safe_query(report, f"calibration_plane_{input_id}", q3)
            report["queries"]["calibration_planes"].append(cal_plane)
            q4 = (
                "SELECT planeid, artifactid, uri, producttype, releasetype, contenttype, "
                "contentlength, contentchecksum FROM spherex.artifact "
                f"WHERE planeid = '{input_id}'"
            )
            cal_artifact = safe_query(report, f"calibration_artifact_{input_id}", q4)
            report["queries"]["calibration_artifacts"].append(cal_artifact)

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    out = args.out / "provenance_input_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    provenance_rows = [x for q in report["queries"]["provenance_inputs"] for x in q.get("rows", [])]
    artifact_rows = [x for q in report["queries"]["calibration_artifacts"] for x in q.get("rows", [])]
    print(json.dumps({
        "science_uri": report["science_uri"],
        "science_artifact_rows": len(science_rows),
        "science_rows": science_rows,
        "provenance_input_rows": len(provenance_rows),
        "provenance_inputs": provenance_rows,
        "calibration_artifact_rows": len(artifact_rows),
        "calibration_artifacts": artifact_rows,
        "errors": report["errors"],
        "report": str(out),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
