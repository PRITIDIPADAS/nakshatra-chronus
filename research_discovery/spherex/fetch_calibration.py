"""Download one explicitly selected calibration URI without claiming it matches science data."""
from __future__ import annotations
import argparse,hashlib,json,os,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

HOST="irsa.ipac.caltech.edu"
ALLOWED={"spectral_wcs","epsf","solid_angle_pixel_map","solid_angle","gain","dark","readnoise_pars","nonlinear_pars"}
def sha256_file(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def download_calibration(uri,*,release,product,detector,out,timeout=180):
 u=urlparse(uri)
 if u.scheme!="https" or u.hostname!=HOST:raise ValueError("calibration URI must be an HTTPS IRSA archive URI")
 if release not in {"dr1","qr3"}:raise ValueError("release must be dr1 or qr3; do not mix QR2 into the DR1/QR3 calibrated set")
 if product not in ALLOWED:raise ValueError(f"unsupported calibration product {product}")
 if detector not in range(1,7):raise ValueError("detector must be 1..6")
 path=u.path.lower()
 if f"/spherex/{release}/" not in path:raise ValueError("URI release path does not match the selected release")
 if product not in path and not (product=="solid_angle" and "solid_angle_pixel_map" in path):
  raise ValueError("URI product directory does not match the selected product")
 if not re.search(rf"/{detector}/",path) and product not in {"solid_angle"}:
  raise ValueError("URI does not contain the requested numeric detector directory")
 dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_suffix(dest.suffix+".part")
 digest=hashlib.sha256();count=0;status="failed";error=None
 try:
  with requests.get(uri,stream=True,timeout=(30,timeout)) as response:
   response.raise_for_status()
   expected=response.headers.get("Content-Length")
   with tmp.open("wb") as f:
    for block in response.iter_content(1024*1024):
     if block:f.write(block);digest.update(block);count+=len(block)
    f.flush();os.fsync(f.fileno())
   if expected is not None and int(expected)!=count:raise IOError(f"Content-Length mismatch: expected {expected}, received {count}")
   with tmp.open("rb") as f:signature=f.read(8)
   if signature!=b"SIMPLE  ":raise IOError(f"Not a primary FITS file (signature {signature!r})")
   tmp.replace(dest);status="downloaded"
 except Exception as exc:
  error=f"{type(exc).__name__}: {exc}"
  if tmp.exists() and tmp.stat().st_size:status="partial"
  else:tmp.unlink(missing_ok=True)
 record={"schema_version":"1.0.0","product_type":product,"release":release.upper(),"detector":f"D{detector}",
  "native_uri":uri,"local_path":str(dest) if status=="downloaded" else str(tmp) if status=="partial" else None,
  "status":status,"byte_count":count if count else None,"sha256":digest.hexdigest() if status=="downloaded" else None,
  "retrieved_utc":datetime.now(timezone.utc).isoformat(),"etag":response.headers.get("ETag") if "response" in locals() else None,
  "last_modified":response.headers.get("Last-Modified") if "response" in locals() else None,
  "compatibility_status":"candidate_only","compatibility_group":None,"error":error,
  "warning":"Downloading an exact calibration URI does not establish compatibility with any science exposure."}
 return record
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("uri");p.add_argument("--release",choices=("dr1","qr3"),required=True)
 p.add_argument("--product",choices=sorted(ALLOWED),required=True);p.add_argument("--detector",type=int,choices=range(1,7),required=True)
 p.add_argument("--out",type=Path,required=True);p.add_argument("--manifest",type=Path,default=Path("calibration_archive_manifest.json"))
 p.add_argument("--download-record",type=Path,default=Path("calibration_download_record.json"))
 a=p.parse_args();r=download_calibration(a.uri,release=a.release,product=a.product,detector=a.detector,out=a.out)
 from research_discovery.spherex.archive_manifest import build_manifest,product_record,validate_manifest
 product=product_record(product_type=r["product_type"],native_uri=r["native_uri"],status=r["status"],
   archive_id=None,release=r["release"],detector=r["detector"],observation_time=None,
   pipeline_version=None,processing_date=None,local_path=r["local_path"],byte_count=r["byte_count"],
   sha256=r["sha256"],compatibility_group=None,compatibility_status="candidate_only",
   notes=r.get("error") or "Downloaded candidate only; no science exposure match has been established.")
 manifest=build_manifest(archive="NASA/IPAC IRSA SPHEREx calibration archive",
   query={"native_uri":a.uri,"release":a.release,"product":a.product,"detector":a.detector},
   products=[product],processing_config={"retrieval":"exact URI only","compatibility":"candidate_only"})
 a.download_record.parent.mkdir(parents=True,exist_ok=True)
 a.download_record.write_text(json.dumps(r,indent=2))
 a.manifest.parent.mkdir(parents=True,exist_ok=True)
 a.manifest.write_text(json.dumps(manifest,indent=2))
 validation=validate_manifest(manifest,verify_local=(r["status"]=="downloaded"),base_dir=Path.cwd())
 print(json.dumps({"record":r,"validation":validation},indent=2))
 if r["status"]!="downloaded" or not validation["valid"]:raise SystemExit(2)
if __name__=="__main__":main()
