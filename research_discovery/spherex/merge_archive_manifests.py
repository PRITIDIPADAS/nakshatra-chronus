"""Merge science and calibration manifests without deduplicating away conflicts."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from research_discovery.spherex.archive_manifest import build_manifest,validate_manifest,sha256_file

def merge(paths):
 products=[];source=[]
 for raw in paths:
  path=Path(raw);data=json.loads(path.read_text(encoding="utf-8"))
  report=validate_manifest(data)
  if not report["valid"]:
   raise ValueError(f"Input manifest failed validation: {path}; {report['issues'][:5]}")
  products.extend(data["products"])
  source.append({"path":str(path),"sha256":sha256_file(path),"schema_version":data["schema_version"],
                 "product_count":len(data["products"])})
 return build_manifest(archive="NASA/IPAC IRSA SPHEREx merged product inventory",
   query={"source_manifests":source,"merged_utc":datetime.now(timezone.utc).isoformat()},
   products=products,processing_config={"operation":"lossless product-row merge",
    "duplicate_policy":"preserve duplicate rows and let the validator flag conflicting identities",
    "calibration_pairing":"not performed by merge"})
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("manifests",nargs="+",type=Path)
 p.add_argument("--out",type=Path,default=Path("data/spherex_merged_manifest.json"));p.add_argument("--verify-local",action="store_true")
 a=p.parse_args();data=merge(a.manifests);a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(data,indent=2,default=str))
 report=validate_manifest(data,verify_local=a.verify_local,base_dir=Path.cwd())
 (a.out.parent/(a.out.stem+".validation.json")).write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
 if not report["valid"]:raise SystemExit(2)
if __name__=="__main__":main()
