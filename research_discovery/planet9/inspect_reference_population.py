#!/usr/bin/env python3
"""Download and fully inspect the public CaltechDATA Planet Nine v3 files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

DATA_URL="https://data.caltech.edu/records/8fjad-x7y61/files/reference_population.csv?download=1"
README_URL="https://data.caltech.edu/records/8fjad-x7y61/files/README.TXT?download=1"


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def download(outdir:Path)->dict:
    import requests
    outdir.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for url,name in ((DATA_URL,"reference_population.csv"),(README_URL,"README.TXT")):
        response=requests.get(url,timeout=180)
        response.raise_for_status()
        path=outdir/name
        path.write_bytes(response.content)
        manifest.append({"name":name,"source_url":url,"path":str(path),
                         "bytes":path.stat().st_size,"sha256":sha256(path)})
        print(f"Downloaded {name}: {path.stat().st_size:,} bytes sha256={manifest[-1]['sha256']}")
    (outdir/"download_manifest.json").write_text(json.dumps(manifest,indent=2))
    return {"files":manifest,"manifest_path":str(outdir/"download_manifest.json")}


def inspect(path:Path,readme_path:Path|None=None)->dict:
    # This is a 13 MB public CSV; read the complete file rather than extrapolating
    # whole-population statistics from the first few hundred rows.
    df=pd.read_csv(path)
    numeric={}
    for c in df.columns:
        s=pd.to_numeric(df[c],errors="coerce")
        if s.notna().any():
            numeric[c]={"min":float(s.min()),"median":float(s.median()),"max":float(s.max()),
                        "n_finite":int(s.notna().sum()),"n_missing_or_non_numeric":int(s.isna().sum())}
    readme_text=readme_path.read_text(errors="replace") if readme_path and readme_path.exists() else None
    return {"path":str(path),"bytes":path.stat().st_size,"sha256":sha256(path),
      "rows":int(len(df)),"columns":list(df.columns),"dtypes":{k:str(v) for k,v in df.dtypes.items()},
      "first_rows":df.head(5).astype(object).where(pd.notna(df.head(5)),None).to_dict(orient="records"),
      "numeric_summary_all_rows":numeric,"readme_path":str(readme_path) if readme_path else None,
      "readme_sha256":sha256(readme_path) if readme_path and readme_path.exists() else None,
      "readme_text":readme_text,
      "warning":"Inspect README units, element epoch, frame, anomaly type and distribution construction before creating a column map. This script does not infer their meaning."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv",type=Path,nargs="?")
    p.add_argument("--readme",type=Path)
    p.add_argument("--download-to",type=Path)
    p.add_argument("--out",type=Path,default=Path("planet9_population_inspection.json"))
    a=p.parse_args()
    if a.download_to:
        download_info=download(a.download_to)
        a.csv=a.download_to/"reference_population.csv"
        a.readme=a.download_to/"README.TXT"
    else:download_info=None
    if not a.csv:p.error("provide csv or --download-to")
    result=inspect(a.csv,a.readme)
    result["download_manifest"]=download_info
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,default=str))
    print(json.dumps({"rows":result["rows"],"columns":result["columns"],"sha256":result["sha256"],"out":str(a.out)},indent=2))
if __name__=="__main__":main()
