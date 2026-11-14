#!/usr/bin/env python3
"""Reproduce the angular-motion diagnostic for the published IRAS/AKARI pair.

This is a calculation from published catalogue coordinates, not a new object
identification and not an orbit fit. The IRAS epoch is an observing interval;
we therefore report a range instead of pretending that a single epoch is known.
"""
from __future__ import annotations
import argparse, json, math
from datetime import date
from pathlib import Path

IRAS = {"name": "IRAS F02211-4844", "ra_deg": 35.74075, "dec_deg": -48.5125}
AKARI = {"name": "AKARI-MUSL J0220440-491247", "ra_deg": 35.18379, "dec_deg": -49.2135}
IRAS_FIRST = date(1983, 6, 26)
IRAS_LAST = date(1983, 9, 1)
IRAS_MIDPOINT = date(1983, 7, 29)
AKARI_EPOCH = date(2006, 12, 26)
ARCSEC_PER_RAD = 206264.80624709636


def position_diagnostic(ra1_deg: float, dec1_deg: float,
                        ra2_deg: float, dec2_deg: float) -> dict:
    r1, d1, r2, d2 = map(math.radians, (ra1_deg, dec1_deg, ra2_deg, dec2_deg))
    dra = (r2 - r1 + math.pi) % (2 * math.pi) - math.pi
    hav = math.sin((d2-d1)/2)**2 + math.cos(d1)*math.cos(d2)*math.sin(dra/2)**2
    sep_rad = 2 * math.asin(math.sqrt(max(0.0, min(1.0, hav))))
    # Initial great-circle bearing, clockwise from celestial north.
    pa = math.atan2(math.sin(dra)*math.cos(d2),
        math.cos(d1)*math.sin(d2)-math.sin(d1)*math.cos(d2)*math.cos(dra))
    pa_deg = math.degrees(pa) % 360.0
    # Great-circle tangent-plane displacement components from source 1 to 2.
    east = math.atan2(math.sin(dra)*math.cos(d2),
        math.cos(d1)*math.cos(d2)*math.cos(dra)+math.sin(d1)*math.sin(d2))*ARCSEC_PER_RAD
    north = math.atan2(math.cos(d1)*math.sin(d2)-math.sin(d1)*math.cos(d2)*math.cos(dra),
        math.cos(d1)*math.cos(d2)*math.cos(dra)+math.sin(d1)*math.sin(d2))*ARCSEC_PER_RAD
    return {"separation_arcmin": math.degrees(sep_rad)*60.0,
            "position_angle_deg_from_north_eastward": pa_deg,
            "east_component_arcsec": east,
            "north_component_arcsec": north}


def compute() -> dict:
    geom = position_diagnostic(IRAS["ra_deg"], IRAS["dec_deg"], AKARI["ra_deg"], AKARI["dec_deg"])
    intervals = []
    for label, iras_epoch in (("earliest_IRAS_survey_date", IRAS_FIRST),
                              ("midpoint_approximation", IRAS_MIDPOINT),
                              ("latest_IRAS_survey_date", IRAS_LAST)):
        days = (AKARI_EPOCH - iras_epoch).days
        years = days / 365.25
        rate = geom["separation_arcmin"] * 60.0 / years
        # Re-express the paper's assumed scaling (42 arcmin in 23 yr at 700 AU).
        # This is a heuristic model inversion, not a distance measurement.
        heuristic_au = 700.0 * ((42.0 * (years / 23.0)) / geom["separation_arcmin"]) ** (2.0 / 3.0)
        intervals.append({"epoch_assumption": label, "iras_date_assumed": iras_epoch.isoformat(),
            "akari_date_assumed": AKARI_EPOCH.isoformat(), "baseline_days": days,
            "baseline_julian_years": years, "mean_angular_rate_arcsec_per_year": rate,
            "heuristic_distance_au_from_paper_scaling_NOT_A_FIT": heuristic_au})
    rates = [x["mean_angular_rate_arcsec_per_year"] for x in intervals]
    distances = [x["heuristic_distance_au_from_paper_scaling_NOT_A_FIT"] for x in intervals]
    return {
        "analysis_type": "reproducible angular separation and baseline sensitivity calculation from published IRAS/AKARI coordinates",
        "iras_source": IRAS, "akari_source": AKARI,
        "published_iras_scan_window": [IRAS_FIRST.isoformat(), IRAS_LAST.isoformat()],
        "akari_scan_date_used": AKARI_EPOCH.isoformat(),
        **geom,
        "east_rate_arcsec_per_year_midpoint": geom["east_component_arcsec"] / intervals[1]["baseline_julian_years"],
        "north_rate_arcsec_per_year_midpoint": geom["north_component_arcsec"] / intervals[1]["baseline_julian_years"],
        "baseline_sensitivity": intervals,
        "angular_rate_range_arcsec_per_year": [min(rates), max(rates)],
        "heuristic_distance_range_au_NOT_A_FIT": [min(distances), max(distances)],
        "scientific_interpretation": "The angular separation reproduces the published pair separation. The mean motion depends on the assumed IRAS epoch within its multi-week scan window. The distance range merely inverts a simplified assumed Planet Nine motion scaling; it is not astrometric parallax, a Keplerian orbit, a new discovery, or a validated ephemeris.",
        "why_no_orbit": ["Only two survey-era catalogue positions are available for this pair.",
            "The IRAS source was co-added across an observing interval rather than at a single documented instantaneous epoch.",
            "The paper flags uncertainty in an AKARI flux measurement and explicitly says the pair does not determine a full orbit.",
            "The authors call for follow-up and discuss nine detections for reliable linked-orbit evaluation."],
        "status": "PUBLISHED_CANDIDATE_PAIR_DIAGNOSTIC_ONLY_NOT_CONFIRMED_PLANET_NINE"
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/planet9_published_candidate_motion.json"))
    args = parser.parse_args()
    result = compute()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"Saved {args.out}")

if __name__ == "__main__":
    main()
