#!/usr/bin/env python3
"""Compare predicted RA/Dec against an independently exported JPL Horizons table.

Input CSVs must each contain mjd, ra_deg and dec_deg columns. Download the
reference table independently from JPL Horizons and record its query settings.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd


def angular_separation_arcsec(ra1,dec1,ra2,dec2):
    r1,d1,r2,d2=np.deg2rad([ra1,dec1,ra2,dec2]);
    cosang=np.sin(d1)*np.sin(d2)+np.cos(d1)*np.cos(d2)*np.cos(r1-r2)
    return np.rad2deg(np.arccos(np.clip(cosang,-1,1)))*3600


def compare(pred_path:Path,ref_path:Path)->dict:
    p=pd.read_csv(pred_path);r=pd.read_csv(ref_path)
    required={"mjd","ra_deg","dec_deg"}
    if not required.issubset(p.columns) or not required.issubset(r.columns):raise ValueError(f"Both CSVs need columns {sorted(required)}")
    joined=p.merge(r,on="mjd",suffixes=("_pred","_ref"))
    if joined.empty:raise ValueError("No matching epochs. Align the MJD values exactly first.")
    sep=angular_separation_arcsec(joined.ra_deg_pred,joined.dec_deg_pred,joined.ra_deg_ref,joined.dec_deg_ref)
    return {"n_epochs":int(len(sep)),"median_separation_arcsec":float(np.median(sep)),"p95_separation_arcsec":float(np.percentile(sep,95)),
      "max_separation_arcsec":float(np.max(sep)),"per_epoch_arcsec":sep.tolist(),
      "interpretation":"A known-object test validates only the tested frame, time span, element source and propagator. It does not validate a hypothetical Planet Nine orbit."}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("predictions",type=Path);p.add_argument("horizons_reference",type=Path);p.add_argument("--out",type=Path,default=Path("horizons_comparison.json"));a=p.parse_args()
    r=compare(a.predictions,a.horizons_reference);a.out.write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
if __name__=="__main__":main()
