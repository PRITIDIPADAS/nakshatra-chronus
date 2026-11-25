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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--science-uri", default=DEFAULT_URI,
                   help="Exact artifact URI value from spherex.artifact.uri (not full hostname)")
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
        "matching_basis": "Explicit spherex.provenance_input.outputid foreign-key join from science plane to calibration input planes.",
    }
    q1 = f"""
    SELECT
      a.uri AS science_uri,
      a.planeid AS science_planeid,
      a.producttype AS science_producttype,
      a.contentlength AS science_contentlength,
      a.contentchecksum AS science_contentchecksum,
      p.obsid AS science_obsid,
      p.productid AS science_productid,
      p.provenance_name AS science_provenance_name,
      p.provenance_version AS science_provenance_version,
      p.provenance_runid AS science_provenance_runid,
      p.provenance_lastexecuted AS science_provenance_lastexecuted,
      p.provenance_keywords AS science_provenance_keywords,
      p.time_bounds_lower AS time_bounds_lower,
      p.time_bounds_upper AS time_bounds_upper,
      p.time_exposure AS time_exposure,
      p.energy_bandpassname AS energy_bandpassname,
      p.position_dimension_naxis1 AS naxis1,
      p.position_dimension_naxis2 AS naxis2,
      o.collection AS collection,
      o.observationid AS observationid,
      o.intent AS intent,
      o.target_name AS target_name
    FROM spherex.artifact a
    JOIN spherex.plane p ON p.planeid = a.planeid
    JOIN spherex.observation o ON o.obsid = p.obsid
    WHERE a.uri = '{uri}'
    """
    try:
        report["queries"]["science_artifact"] = to_rows(q1)
    except Exception as exc:
        report["errors"].append({"stage": "science_artifact", "error": f"{type(exc).__name__}: {exc}", "query": q1})
        report["queries"]["science_artifact"] = {"row_count": 0, "rows": []}

    science_rows = report["queries"]["science_artifact"].get("rows", [])
    if science_rows:
        plane_ids = sorted({str(x["science_planeid"]) for x in science_rows if x.get("science_planeid")})
        report["queries"]["provenance_inputs"] = []
        for plane_id in plane_ids:
            q2 = f"""
            SELECT
              pi.inputid AS calibration_planeid,
              pi.outputid AS science_planeid,
              ca.uri AS calibration_uri,
              ca.producttype AS calibration_producttype,
              ca.releasetype AS calibration_releasetype,
              ca.contenttype AS calibration_contenttype,
              ca.contentlength AS calibration_contentlength,
              ca.contentchecksum AS calibration_contentchecksum,
              cp.obsid AS calibration_obsid,
              cp.productid AS calibration_productid,
              cp.provenance_name AS calibration_provenance_name,
              cp.provenance_version AS calibration_provenance_version,
              cp.provenance_runid AS calibration_provenance_runid,
              cp.provenance_lastexecuted AS calibration_provenance_lastexecuted,
              cp.provenance_keywords AS calibration_provenance_keywords,
              co.collection AS calibration_collection,
              co.observationid AS calibration_observationid,
              co.intent AS calibration_intent
            FROM spherex.provenance_input pi
            JOIN spherex.plane cp ON cp.planeid = pi.inputid
            JOIN spherex.artifact ca ON ca.planeid = cp.planeid
            JOIN spherex.observation co ON co.obsid = cp.obsid
            WHERE pi.outputid = '{plane_id}'
            """
            try:
                report["queries"]["provenance_inputs"].append(to_rows(q2))
            except Exception as exc:
                report["errors"].append({"stage": "provenance_inputs", "science_planeid": plane_id,
                                         "error": f"{type(exc).__name__}: {exc}", "query": q2})
    else:
        # Preserve the raw join-table diagnostic, even when the science artifact
        # lookup failed to return an accessible row.
        q2 = "SELECT TOP 20 * FROM spherex.provenance_input"
        try:
            report["queries"]["provenance_table_sample"] = to_rows(q2)
        except Exception as exc:
            report["errors"].append({"stage": "provenance_table_sample", "error": f"{type(exc).__name__}: {exc}"})

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    out = args.out / "provenance_input_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "science_uri": report["science_uri"],
        "science_artifact_rows": report["queries"].get("science_artifact", {}).get("row_count"),
        "science_rows": report["queries"].get("science_artifact", {}).get("rows", []),
        "provenance_queries": [
            {"row_count": q.get("row_count"), "columns": q.get("columns"),
             "rows": q.get("rows", [])[:30], "query": q.get("query")}
            for q in report["queries"].get("provenance_inputs", [])
        ],
        "errors": report["errors"],
        "report": str(out),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
