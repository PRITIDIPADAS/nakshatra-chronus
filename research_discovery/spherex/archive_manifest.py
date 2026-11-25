#!/usr/bin/env python3
"""Versioned SPHEREx archive manifest, retrieval provenance and integrity checks."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, os, platform, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Mapping, Sequence

SCHEMA_VERSION="1.0.0"
SHA256_RE=re.compile(r"^[0-9a-f]{64}$")
REQUIRED=("archive_id","identity_basis","product_type","release","detector","observation_time",
          "pipeline_version","processing_date","native_uri","local_path","byte_count","sha256",
          "status","compatibility_group","compatibility_status")
STATUSES={"downloaded","failed","partial","discovered_not_downloaded","rejected"}
COMPAT={"unassigned","candidate_only","compatible","rejected","review_required"}

def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def software_fingerprint():
    pkgs={}
    for name in ("astropy","astroquery","numpy","requests","scipy","photutils"):
        try: pkgs[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: pkgs[name]=None
    return {"python":platform.python_version(),"implementation":platform.python_implementation(),
            "platform":platform.platform(),"packages":pkgs,"git_commit":os.getenv("CHRONOS_GIT_COMMIT")}

def product_record(*,product_type,native_uri,status,archive_id=None,release=None,detector=None,
 observation_time=None,pipeline_version=None,processing_date=None,local_path=None,byte_count=None,
 sha256=None,compatibility_group=None,compatibility_status="unassigned",notes=None):
    return {"archive_id":archive_id,"identity_basis":"archive_id" if archive_id else "native_uri",
      "product_type":product_type,"release":release,"detector":detector,"observation_time":observation_time,
      "pipeline_version":pipeline_version,"processing_date":processing_date,"native_uri":native_uri,
      "local_path":local_path,"byte_count":byte_count,"sha256":sha256,"status":status,
      "compatibility_group":compatibility_group,"compatibility_status":compatibility_status,"notes":notes}

def _digest(m):
    return hashlib.sha256(json.dumps({k:v for k,v in m.items() if k not in {"manifest_sha256","download_validation"}},
      sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()).hexdigest()

def build_manifest(*,archive,query,products,processing_config,retrieved_utc=None,software=None):
    m={"schema_version":SCHEMA_VERSION,"archive":archive,"query":dict(query),
       "retrieved_utc":retrieved_utc or datetime.now(timezone.utc).isoformat(),
       "software":dict(software or software_fingerprint()),"processing_config":dict(processing_config),
       "products":[dict(p) for p in products],
       "status":"empty_unpopulated" if not products else "populated",
       "status_note":"An empty list is not evidence of retrieval; product records are emitted only from archive responses or downloaded bytes."}
    m["manifest_sha256"]=_digest(m)
    return m

def validate_manifest(m:Mapping[str,Any],*,verify_local=False,base_dir=None):
    issues=[]
    for k in ("schema_version","archive","query","retrieved_utc","software","processing_config","products"):
        if k not in m: issues.append({"code":"missing_top_level_field","field":k})
    if m.get("schema_version")!=SCHEMA_VERSION: issues.append({"code":"unsupported_schema_version"})
    if not isinstance(m.get("archive"),str) or not m.get("archive","").strip(): issues.append({"code":"invalid_archive"})
    if m.get("products") and not m.get("retrieved_utc"): issues.append({"code":"missing_retrieval_time"})
    for k in ("query","software","processing_config"):
        if not isinstance(m.get(k),Mapping): issues.append({"code":"invalid_top_level_object","field":k})
    products=m.get("products")
    if not isinstance(products,list): issues.append({"code":"products_not_list"}); products=[]
    seen_uri=set(); seen_ids=set(); root=Path(base_dir or Path.cwd())
    for i,p in enumerate(products):
        if not isinstance(p,Mapping): issues.append({"code":"product_not_object","index":i}); continue
        for k in REQUIRED:
            if k not in p: issues.append({"code":"missing_product_field","index":i,"field":k})
        uri=p.get("native_uri"); aid=p.get("archive_id"); status=p.get("status")
        if not isinstance(uri,str) or not uri.strip() or urlparse(uri).scheme not in {"https","http","irsa"}:
            issues.append({"code":"invalid_native_uri","index":i})
        elif uri in seen_uri: issues.append({"code":"duplicate_product_uri","index":i,"uri":uri})
        else: seen_uri.add(uri)
        if aid is not None:
            if not isinstance(aid,str) or not aid.strip(): issues.append({"code":"invalid_archive_id","index":i})
            elif aid in seen_ids: issues.append({"code":"duplicate_archive_id","index":i,"archive_id":aid})
            else: seen_ids.add(aid)
        if p.get("identity_basis") not in {"archive_id","native_uri"}: issues.append({"code":"invalid_identity_basis","index":i})
        if p.get("identity_basis")=="archive_id" and not aid: issues.append({"code":"missing_archive_id_for_identity","index":i})
        if p.get("identity_basis")=="native_uri" and not uri: issues.append({"code":"missing_uri_for_identity","index":i})
        if status not in STATUSES: issues.append({"code":"invalid_product_status","index":i})
        if p.get("compatibility_status") not in COMPAT: issues.append({"code":"invalid_compatibility_status","index":i})
        digest=p.get("sha256"); size=p.get("byte_count")
        if digest is not None and (not isinstance(digest,str) or not SHA256_RE.fullmatch(digest)):
            issues.append({"code":"malformed_sha256","index":i})
        if size is not None and (not isinstance(size,int) or isinstance(size,bool) or size<0):
            issues.append({"code":"invalid_byte_count","index":i})
        if status=="downloaded":
            local=p.get("local_path")
            if not isinstance(size,int) or isinstance(size,bool) or size<=0: issues.append({"code":"download_missing_byte_count","index":i})
            if not isinstance(digest,str) or not SHA256_RE.fullmatch(digest): issues.append({"code":"download_missing_sha256","index":i})
            if not isinstance(local,str) or not local.strip(): issues.append({"code":"download_missing_local_path","index":i})
            elif verify_local:
                f=Path(local); f=f if f.is_absolute() else root/f
                if not f.is_file(): issues.append({"code":"downloaded_file_missing","index":i,"path":str(f)})
                else:
                    if f.stat().st_size!=size: issues.append({"code":"byte_count_mismatch","index":i})
                    if SHA256_RE.fullmatch(str(digest)) and sha256_file(f)!=digest: issues.append({"code":"sha256_mismatch","index":i})
        elif status in {"failed","partial","rejected"} and digest is not None:
            issues.append({"code":"incomplete_download_has_final_hash","index":i})
        elif status=="discovered_not_downloaded" and (digest is not None or size is not None):
            issues.append({"code":"undownloaded_product_has_hash_or_size","index":i})
    got=m.get("manifest_sha256")
    if got is not None and (not isinstance(got,str) or not SHA256_RE.fullmatch(got) or got!=_digest(m)):
        issues.append({"code":"manifest_sha256_invalid_or_mismatch"})
    return {"valid":not issues,"issue_count":len(issues),"issues":issues,
      "product_count":len(products),"downloaded_count":sum(p.get("status")=="downloaded" for p in products if isinstance(p,Mapping))}

def _text(v):
    if v is None: return None
    s=str(v).strip()
    return None if not s or s.lower() in {"masked","none","nan","--"} else s

def manifest_from_sia(rows:Sequence[Mapping[str,Any]],*,query_url,query_metadata,downloads=(),retrieved_utc=None):
    by_uri={str(x.get("source_url")):x for x in downloads if x.get("source_url")}
    products=[]
    for row in rows:
        uri=_text(row.get("access_url"))
        if not uri: continue
        name=Path(urlparse(uri).path).name
        mt=re.match(r"level2_(?P<obs>.+?)D(?P<det>[1-6])_spx_l2b-v(?P<ver>[0-9.]+)-(?P<date>\d{4}-\d{3})\.fits$",name,re.I)
        dl=by_uri.get(uri,{})
        status=dl.get("status","discovered_not_downloaded")
        if status not in STATUSES: status="failed"
        products.append(product_record(
          archive_id=_text(row.get("obs_publisher_did")),product_type="level2_mef",
          release=_release(row.get("obs_collection"),uri),detector=f"D{mt.group('det')}" if mt else None,
          observation_time={"start_mjd":_text(row.get("t_min")),"end_mjd":_text(row.get("t_max")),"exposure_time_s":_text(row.get("t_exptime"))},
          pipeline_version=mt.group("ver") if mt else None,processing_date=mt.group("date") if mt else None,
          native_uri=uri,local_path=dl.get("local_path"),byte_count=dl.get("bytes"),sha256=dl.get("sha256"),
          status=status,compatibility_group=None,compatibility_status="unassigned",
          notes=("SIA2 obs_publisher_did retained." if _text(row.get("obs_publisher_did")) else "No publisher DID was provided; native URI retained as identity.")+
            (("; download error: "+str(dl.get("error"))) if dl.get("error") else "")))
    return build_manifest(archive="NASA/IPAC IRSA SPHEREx SIA2",query={"query_url":query_url,**dict(query_metadata)},
      products=products,processing_config={"method":"SIA2 access_url; SHA-256 of completed downloads",
      "calibration_pairing":"not performed during archive retrieval"},retrieved_utc=retrieved_utc)

def _release(collection,uri):
    s=(str(collection or "")+" "+urlparse(uri).path).lower()
    return next((x.upper() for x in ("dr1","qr3","qr2") if x in s),None)

def manifest_from_native_inventory(inv):
    products=[]; query_rows=[]
    for f in inv.get("field_results",[]):
        if f.get("query"): query_rows.append({"field":f.get("name"),"ra_deg":f.get("ra_deg"),"dec_deg":f.get("dec_deg"),"tap_sql":f.get("query")})
        for item in f.get("downloads",[]):
            uri=item.get("source_url") or item.get("artifact_uri")
            if not uri: continue
            name=Path(urlparse(uri).path).name
            mt=re.search(r"D([1-6]).*?-v(?P<ver>[0-9.]+)-(?P<date>\d{4}-\d{3})",name,re.I)
            products.append(product_record(product_type="level2_mef",native_uri=uri,
              archive_id=None,release=_release(None,uri),detector=f"D{mt.group(1)}" if mt else None,
              observation_time={"start":item.get("time_bounds_lower"),"end":item.get("time_bounds_upper")},
              pipeline_version=mt.group("ver") if mt else None,processing_date=mt.group("date") if mt else None,
              local_path=item.get("local_path"),byte_count=item.get("bytes"),sha256=item.get("sha256"),
              status=item.get("status","discovered_not_downloaded") if item.get("status") in STATUSES else "failed",
              compatibility_status="unassigned",notes=item.get("error")))
    return build_manifest(archive="NASA/IPAC IRSA SPHEREx TAP",query={"queries":query_rows,"archive":inv.get("archive")},
      products=products,processing_config={"method":"native MEF retrieval; TAP query and original URI preserved",
      "compatibility_pairing":"unassigned; no inferred calibration matches"},retrieved_utc=inv.get("created_utc"))

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("input",type=Path)
    p.add_argument("--out",type=Path,default=Path("data/spherex_archive_manifest.json"))
    p.add_argument("--verify-local",action="store_true"); a=p.parse_args()
    data=json.loads(a.input.read_text(encoding="utf-8"))
    m=data if data.get("schema_version")==SCHEMA_VERSION else manifest_from_native_inventory(data)
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(m,indent=2),encoding="utf-8")
    report=validate_manifest(m,verify_local=a.verify_local,base_dir=Path.cwd())
    print(json.dumps(report,indent=2))
    if not report["valid"]: raise SystemExit(2)
if __name__=="__main__": main()
