"""Build a transparent matrix of science-exposure/calibration candidate decisions."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from research_discovery.spherex.calibration_compatibility import compatibility_decision

def build_matrix(payload):
 science=payload.get("science_exposures",[])
 calibrations=payload.get("calibration_candidates",[])
 rows=[]
 for exp in science:
  candidates=[c for c in calibrations if str(c.get("product_type",""))=="spectral_wcs"]
  for cal in candidates:
   decision=compatibility_decision(exp.get("metadata",{}),cal.get("metadata",{}))
   rows.append({"science_id":exp.get("id"),"science_uri":exp.get("uri"),
     "calibration_id":cal.get("id"),"calibration_uri":cal.get("uri"),
     "decision":decision["status"],"compatibility_group":decision["compatibility_group"],
     "checks":decision["checks"]})
 return {"schema_version":"1.0","pair_count":len(rows),
   "compatible_pairs":[r for r in rows if r["decision"]=="compatible"],
   "failed_matches":[r for r in rows if r["decision"]=="rejected"],
   "unresolved_pairs":[r for r in rows if r["decision"]=="review_required"],
   "matrix":rows,
   "warning":"The tool does not infer matches. Missing provenance remains unresolved; filename similarity is not compatibility."}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("input",type=Path);p.add_argument("--out",type=Path,default=Path("calibration_compatibility_matrix.json"))
 a=p.parse_args();result=build_matrix(json.loads(a.input.read_text()));a.out.write_text(json.dumps(result,indent=2,default=str))
 print(f"pairs={result['pair_count']} compatible={len(result['compatible_pairs'])} rejected={len(result['failed_matches'])} unresolved={len(result['unresolved_pairs'])}")
if __name__=="__main__":main()
