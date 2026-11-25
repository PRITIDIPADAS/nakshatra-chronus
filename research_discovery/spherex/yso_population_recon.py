#!/usr/bin/env python3
"""Predeclared SPLICES/DR1 field reconnaissance for a future YSO population study.

This script does not claim a YSO discovery. It separates published catalogue
labels from SPLICES machine-learning classes, retains comparison classes, and
measures SPHEREx DR1 Level-2 archive coverage for the same predeclared fields.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astroquery.ipac.irsa import Irsa

REGIONS = (
    {"name": "Taurus_Auriga", "ra_deg": 65.7, "dec_deg": 26.0, "radius_deg": 2.0, "role": "star_forming_region"},
    {"name": "Perseus_NGC1333", "ra_deg": 52.30, "dec_deg": 31.30, "radius_deg": 0.85, "role": "star_forming_region"},
    {"name": "Orion_A", "ra_deg": 83.80, "dec_deg": -5.40, "radius_deg": 1.50, "role": "star_forming_region"},
    {"name": "Rho_Ophiuchi", "ra_deg": 246.75, "dec_deg": -24.60, "radius_deg": 0.90, "role": "star_forming_region"},
    {"name": "Lupus_III", "ra_deg": 242.10, "dec_deg": -39.10, "radius_deg": 0.90, "role": "star_forming_region"},
    {"name": "HighLatitude_Control", "ra_deg": 180.0, "dec_deg": 60.0, "radius_deg": 1.50, "role": "control"},
)
OUTPUT = Path("data/yso_population_recon")
CANDIDATE_LIMIT = 5000
DR1_BANDS = tuple(f"SPHEREx-D{i}" for i in range(1, 7))


def scalar(value: Any) -> Any:
    if value is None or getattr(value, "mask", False):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return str(value)


def query_rows(query: str) -> dict:
    result = Irsa.query_tap(query)
    table = result.to_table() if hasattr(result, "to_table") else result
    rows = [
        {str(name): scalar(row[name]) for name in table.colnames}
        for row in table
    ]
    return {
        "query": query,
        "columns": list(table.colnames),
        "row_count": len(rows),
        "rows": rows,
    }


def digest_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def region_predicate(region: dict, ra_col: str = "ra", dec_col: str = "dec") -> str:
    return (
        "1 = CONTAINS("
        f"POINT('ICRS', {ra_col}, {dec_col}), "
        f"CIRCLE('ICRS', {region['ra_deg']:.8f}, {region['dec_deg']:.8f}, {region['radius_deg']:.5f})"
        ")"
    )


def inspect_region(region: dict) -> dict:
    where = region_predicate(region)
    total_sql = f"SELECT COUNT(*) AS n FROM spherex.splices WHERE {where}"
    published_sql = (
        f"SELECT COUNT(*) AS n FROM spherex.splices WHERE {where} "
        "AND yso_pub IS NOT NULL"
    )
    class1_yso_sql = (
        f"SELECT COUNT(*) AS n FROM spherex.splices WHERE {where} "
        "AND UPPER(class_1) LIKE '%YSO%'"
    )
    ml_yso_sql = (
        f"SELECT COUNT(*) AS n FROM spherex.splices WHERE {where} "
        "AND UPPER(stype_ml) LIKE '%YSO%'"
    )
    class_distribution_sql = (
        "SELECT class_1, yso_pub, stype_ml, COUNT(*) AS n "
        f"FROM spherex.splices WHERE {where} "
        "GROUP BY class_1, yso_pub, stype_ml ORDER BY COUNT(*) DESC"
    )
    candidate_sql = (
        "SELECT TOP 5000 source_id, designation, ra, dec, sel_type, class_1, yso_pub, "
        "stype_ml, stype_ml_prob1, stype_ml_prob2, mc, mc_los, mc_dist, av, "
        "plx, e_plx, gaiadist, e_dist_upper, e_dist_lower, "
        "w1, w1err, w2, w2err, w3, w3err, w4, w4err, "
        "w1var, w1var_class, w2var, w2var_class, "
        "numgaianb, mingaiadist, numiracnbors, mindistirac "
        f"FROM spherex.splices WHERE {where} "
        "AND (yso_pub IS NOT NULL OR UPPER(class_1) LIKE '%YSO%' "
        "OR UPPER(stype_ml) LIKE '%YSO%') ORDER BY source_id"
    )
    query_results = {}
    for name, sql in (
        ("total", total_sql),
        ("published_yso_label", published_sql),
        ("class_1_yso", class1_yso_sql),
        ("ml_yso", ml_yso_sql),
        ("class_distribution", class_distribution_sql),
        ("candidate_sources", candidate_sql),
    ):
        query_results[name] = query_rows(sql)

    # Query real Level-2 archive coverage by detector band at the same sky region.
    exposure_sql = (
        "SELECT p.energy_bandpassname, COUNT(*) AS n_exposures, "
        "MIN(p.time_bounds_lower) AS first_time, MAX(p.time_bounds_upper) AS last_time "
        "FROM spherex.artifact a JOIN spherex.plane p ON p.planeid = a.planeid "
        "WHERE 1 = CONTAINS("
        f"POINT('ICRS', {region['ra_deg']:.8f}, {region['dec_deg']:.8f}), p.poly) "
        "AND LOWER(a.uri) LIKE '%/dr1/level2/%' "
        "AND p.energy_bandpassname IN ("
        + ", ".join(f"'{band}'" for band in DR1_BANDS)
        + ") GROUP BY p.energy_bandpassname ORDER BY p.energy_bandpassname"
    )
    try:
        query_results["dr1_level2_coverage_by_band"] = query_rows(exposure_sql)
    except Exception as exc:
        query_results["dr1_level2_coverage_by_band"] = {
            "query": exposure_sql,
            "error": f"{type(exc).__name__}: {exc}",
            "row_count": 0,
            "rows": [],
        }

    counts = {}
    for name in ("total", "published_yso_label", "class_1_yso", "ml_yso"):
        rows = query_results[name]["rows"]
        counts[name] = int(rows[0]["n"]) if rows else 0
    counts["candidate_rows_returned"] = query_results["candidate_sources"]["row_count"]
    counts["candidate_query_limit"] = CANDIDATE_LIMIT
    coverage_rows = query_results["dr1_level2_coverage_by_band"].get("rows", [])
    counts["dr1_level2_exposure_rows_by_band"] = {
        str(row["energy_bandpassname"]): int(row["n_exposures"])
        for row in coverage_rows
    }
    counts["dr1_level2_exposure_total"] = sum(counts["dr1_level2_exposure_rows_by_band"].values())
    return {
        "region": region,
        "counts": counts,
        "queries": query_results,
        "query_sha256": digest_json({k: v.get("query") for k, v in query_results.items()}),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    summaries = []
    all_candidates = []
    all_classes = []
    errors = []
    for region in REGIONS:
        print(f"Querying SPLICES and DR1 coverage: {region['name']}", flush=True)
        try:
            result = inspect_region(region)
            summaries.append({
                "region": region,
                "counts": result["counts"],
                "query_sha256": result["query_sha256"],
                "query_errors": {
                    key: value.get("error")
                    for key, value in result["queries"].items()
                    if value.get("error")
                },
            })
            for row in result["queries"]["candidate_sources"]["rows"]:
                all_candidates.append({**row, "recon_region": region["name"], "region_role": region["role"]})
            for row in result["queries"]["class_distribution"]["rows"]:
                all_classes.append({**row, "recon_region": region["name"], "region_role": region["role"]})
            region_dir = OUTPUT / region["name"]
            for name, query_result in result["queries"].items():
                if "rows" in query_result and name in {"candidate_sources", "class_distribution", "dr1_level2_coverage_by_band"}:
                    write_csv(region_dir / f"{name}.csv", query_result["rows"])
            (region_dir / "query_record.json").write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:
            errors.append({
                "region": region,
                "error": f"{type(exc).__name__}: {exc}",
            })
    write_csv(OUTPUT / "candidate_sources_all_regions.csv", all_candidates)
    write_csv(OUTPUT / "class_distribution_all_regions.csv", all_classes)
    report = {
        "schema": "chronos-spllices-yso-recon/1.0",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "catalogue": "IRSA spherex.splices",
        "catalogue_release": "SPLICES v8.6 according to IRSA release notes; actual TAP response is retained",
        "predeclared_regions": list(REGIONS),
        "region_results": summaries,
        "candidate_record_count": len(all_candidates),
        "class_distribution_record_count": len(all_classes),
        "errors": errors,
        "scientific_boundary": [
            "SPLICES is a broad ice-source target compilation, not a census of confirmed YSOs.",
            "Published YSO labels (CLASS_1/YSO_PUB) and ML labels (STYPE_ML/STYPE_ML_PROB*) are retained separately.",
            "Machine-learning classification is not treated as independent confirmation.",
            "The regional counts are not a population rate; selection functions and contamination must be modelled.",
            "This reconnaissance does not establish a new YSO discovery.",
            "L2 exposure coverage counts are not source-level extracted spectra or epoch completeness.",
        ],
        "report_sha256": None,
    }
    report["report_sha256"] = digest_json({k: v for k, v in report.items() if k != "report_sha256"})
    (OUTPUT / "yso_population_recon.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({
        "regions": summaries,
        "candidate_record_count": len(all_candidates),
        "errors": errors,
        "report": str(OUTPUT / "yso_population_recon.json"),
        "report_sha256": report["report_sha256"],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
