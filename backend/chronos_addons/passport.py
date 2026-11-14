"""Content-addressed evidence passports. SHA-256 is not a digital signature."""
from __future__ import annotations
from typing import Any, Mapping
from datetime import datetime, timezone
import hashlib, json, os
SCHEMA="chronos-evidence-passport/1.0"
def canonical_json(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str).encode()
def sha256_bytes(x): return hashlib.sha256(x).hexdigest()
def hash_file(path):
    if not os.path.isfile(path): raise FileNotFoundError(path)
    h=hashlib.sha256(); size=0
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b); size+=len(b)
    return {"path_label":os.path.basename(path),"sha256":h.hexdigest(),"bytes":size}
def create_passport(*,project: str,candidate_id: str,creator: str,inputs: Mapping[str,Any],measurements: Mapping[str,Any],methods: Mapping[str,Any],software: Mapping[str,Any],source_hashes=None,external_references=None,limitations=None):
    if not all(x.strip() for x in (project,candidate_id,creator)): raise ValueError("project, candidate_id and creator are required")
    body={"schema":SCHEMA,"created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"project":project,"candidate_id":candidate_id,"creator":creator,
      "inputs":dict(inputs),"measurements":dict(measurements),"methods":dict(methods),"software":dict(software),"source_hashes":dict(source_hashes or {}),
      "external_references":[dict(x) for x in (external_references or [])],"limitations":list(limitations or []),
      "integrity_note":"SHA-256 detects content changes; it does not verify identity, authorship or scientific validity."}
    return {**body,"seal_sha256":sha256_bytes(canonical_json(body))}
def verify_passport(passport: Mapping[str,Any])->dict[str,Any]:
    if not isinstance(passport,Mapping): raise TypeError("passport must be a mapping")
    if passport.get("schema")!=SCHEMA:return {"valid":False,"reason":"unsupported schema"}
    supplied=passport.get("seal_sha256")
    if not isinstance(supplied,str) or len(supplied)!=64:return {"valid":False,"reason":"missing/malformed seal"}
    body={k:v for k,v in passport.items() if k!="seal_sha256"}
    try: actual=sha256_bytes(canonical_json(body))
    except (TypeError,ValueError) as e:return {"valid":False,"reason":str(e)}
    return {"valid":actual==supplied,"supplied_seal":supplied,"computed_seal":actual,"reason":"content matches seal" if actual==supplied else "content changed after sealing"}
def write_passport(passport,path):
    if not verify_passport(passport)["valid"]: raise ValueError("refusing to write invalid passport")
    os.makedirs(os.path.dirname(os.path.abspath(path)),exist_ok=True); tmp=path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(passport,f,ensure_ascii=False,indent=2,allow_nan=False); f.write("\n")
    os.replace(tmp,path); return os.path.abspath(path)
