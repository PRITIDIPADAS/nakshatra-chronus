"""Apply only unambiguous, fully passing calibration-pair decisions to a merged archive manifest."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from collections import defaultdict
from research_discovery.spherex.archive_manifest import build_manifest,validate_manifest

def apply_matrix(manifest,matrix):
 products=[dict(p) for p in manifest.get("products",[])]
 by_uri={p.get("native_uri"):p for p in products}
 compatible=defaultdict(list)
 for row in matrix.get("compatible_pairs",[]):
  compatible[row.get("science_uri")].append(row)
 applied=[];unresolved=[];used_cal={}
 for science_uri,rows in compatible.items():
  # Multiple compatible calibration files for one exposure are ambiguous; do not choose.
  unique={r.get("calibration_uri") for r in rows}
  if len(unique)!=1 or science_uri not in by_uri or next(iter(unique)) not in by_uri:
   unresolved.append({"science_uri":science_uri,"reason":"ambiguous or missing manifest product row"})
   continue
  row=rows[0];cal_uri=row["calibration_uri"]
  group=row.get("compatibility_group")
  if not group:
   group="SPX:"+hashlib.sha256((science_uri+"\n"+cal_uri).encode()).hexdigest()[:16]
  sci=by_uri[science_uri];cal=by_uri[cal_uri]
  sci["compatibility_status"]="compatible";cal["compatibility_status"]="compatible"
  sci["compatibility_group"]=group;cal["compatibility_group"]=group
  sci["notes"]=(str(sci.get("notes") or "")+" | Pair verified by compatibility matrix.").strip(" |")
  cal["notes"]=(str(cal.get("notes") or "")+" | Pair verified by compatibility matrix.").strip(" |")
  used_cal.setdefault(cal_uri,set()).add(group)
  applied.append({"science_uri":science_uri,"calibration_uri":cal_uri,"compatibility_group":group})
 for uri,groups in used_cal.items():
  if len(groups)>1:
   unresolved.append({"calibration_uri":uri,"reason":"calibration candidate maps to multiple compatibility groups"})
   by_uri[uri]["compatibility_status"]="review_required";by_uri[uri]["compatibility_group"]=None
 updated=build_manifest(archive="NASA/IPAC IRSA SPHEREx merged product inventory",
   query={"source_manifest_sha256":manifest.get("manifest_sha256"),"compatibility_matrix_sha256":hashlib.sha256(
     json.dumps(matrix,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()},
   products=products,processing_config={"operation":"apply verified compatibility matrix",
     "compatible_pair_count":len(applied),"unresolved_pair_count":len(unresolved)})
 return updated,{"applied_pairs":applied,"unresolved":unresolved}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("manifest",type=Path);p.add_argument("matrix",type=Path)
 p.add_argument("--out",type=Path,default=Path("data/spherex_compatible_manifest.json"))
 a=p.parse_args();data=json.loads(a.manifest.read_text());matrix=json.loads(a.matrix.read_text())
 updated,report=apply_matrix(data,matrix);valid=validate_manifest(updated)
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(updated,indent=2,default=str))
 (a.out.parent/(a.out.stem+".pairing.json")).write_text(json.dumps(report,indent=2))
 print(json.dumps({"manifest_valid":valid["valid"],"paired":len(report["applied_pairs"]),"unresolved":len(report["unresolved"])},indent=2))
 if not valid["valid"]:raise SystemExit(2)
if __name__=="__main__":main()
