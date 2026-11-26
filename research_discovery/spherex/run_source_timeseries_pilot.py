"""Run a provenance-verified four-epoch native SPHEREx source-photometry pilot."""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,math
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping
from research_discovery.spherex.source_photometry import assemble_source_photometry_series,extract_source_photometry
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST=ROOT/"data"/"spherex_source_timeseries_pilot.orion_candidate.json"
SOURCE_CATALOGUE=ROOT/"data"/"spherex_orion_source_catalogue_snapshot.json"
REPOSITORY="PRITIDIPADAS/nakshatra-chronus"
SCHEMA="chronos-spherex-source-timeseries-pilot/1.0"
def sha256_file(path:Path)->str:
 d=hashlib.sha256()
 with path.open("rb") as h:
  for block in iter(lambda:h.read(1024*1024),b""): d.update(block)
 return d.hexdigest()
def validate_pilot_manifest(value:Mapping[str,Any])->dict[str,Any]:
 if not isinstance(value,Mapping) or value.get("schema")!=SCHEMA: raise ValueError(f"pilot manifest schema must be {SCHEMA}")
 source=value.get("source_catalogue")
 if not isinstance(source,Mapping) or not str(source.get("source_id") or "").strip(): raise ValueError("pilot requires one source catalogue record with a source_id")
 ra,dec=float(source.get("ra_deg")),float(source.get("dec_deg"))
 if not (0<=ra<360 and -90<=dec<=90): raise ValueError("source ICRS coordinates are invalid")
 if source.get("catalogue_labels_are_independent_confirmation") is not False: raise ValueError("catalogue labels must remain explicitly non-independent")
 policy=value.get("selection_policy") or {}
 if policy.get("release")!="DR1" or policy.get("detector")!="D2": raise ValueError("pilot is frozen to SPHEREx DR1 D2")
 minimum=policy.get("minimum_epochs")
 if isinstance(minimum,bool) or int(minimum)!=minimum or minimum<2: raise ValueError("minimum_epochs must be an integer of at least two")
 band_overlap=float(policy.get("minimum_band_overlap_fraction",float("nan")))
 if not math.isfinite(band_overlap) or not 0<band_overlap<=1: raise ValueError("minimum_band_overlap_fraction must be preregistered in (0, 1]")
 products=value.get("products")
 if not isinstance(products,list) or len(products)!=4: raise ValueError("pilot manifest must contain exactly four predeclared products")
 ids,obs,uris,times=set(),set(),set(),[]
 for i,row in enumerate(products):
  if not isinstance(row,Mapping): raise ValueError(f"product {i} must be an object")
  pid=str(row.get("archive_product_id") or "").strip(); oid=str(row.get("observation_id") or "").strip(); uri=str(row.get("native_uri") or "").strip()
  if not pid or pid in ids: raise ValueError("archive product IDs must be unique and non-empty")
  if not oid or oid in obs: raise ValueError("observation_id values must be unique and non-empty")
  if not uri.startswith("https://") or uri in uris: raise ValueError(f"product {pid} needs a unique HTTPS URI")
  if row.get("release")!="DR1" or row.get("detector")!="D2" or row.get("bandpass")!="SPHEREx-D2": raise ValueError(f"product {pid} is not a DR1 D2 spectral-image product")
  if "/dr1/level2/" not in uri.lower() or not uri.lower().endswith(".fits"): raise ValueError(f"product {pid} is not a native DR1 Level-2 FITS URI")
  lo,hi,mid=float(row["t_min_mjd"]),float(row["t_max_mjd"]),float(row["mjd_midpoint"])
  if not lo<hi or abs(mid-(lo+hi)/2)>1e-8: raise ValueError(f"product {pid} has invalid MJD bounds")
  ids.add(pid);obs.add(oid);uris.add(uri);times.append(mid)
 if times!=sorted(times) or len(set(times))!=len(times): raise ValueError("pilot products must be sorted by distinct increasing MJD")
 if len(obs)<int(minimum): raise ValueError("frozen roster is smaller than minimum_epochs")
 canonical=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
 return {"source_id":str(source["source_id"]),"product_count":len(products),"observation_ids":sorted(obs),"minimum_epochs":int(minimum),"minimum_band_overlap_fraction":band_overlap,"baseline_days":max(times)-min(times),"manifest_sha256":hashlib.sha256(canonical.encode()).hexdigest()}
def file_record(uri:str,path:Path)->dict[str,str]:
 if not path.is_file(): raise FileNotFoundError(path)
 return {"uri":uri,"local_path":str(path),"sha256":sha256_file(path)}

def validate_native_observation_time(science:Mapping[str,Any],product:Mapping[str,Any],*,tolerance_seconds:float=5.0)->dict[str,float]:
 start=float(science.get("mjd_obs"))
 exposure=float(science.get("exposure_time_s"))
 if not math.isfinite(start) or not math.isfinite(exposure) or exposure<=0:
  raise ValueError("native science MEF must provide finite MJD-OBS and positive exposure time")
 lower=float(product["t_min_mjd"]); upper=float(product["t_max_mjd"])
 midpoint=float(product["mjd_midpoint"])
 native_end=start+exposure/86400.0
 native_midpoint=start+exposure/(2.0*86400.0)
 offsets={
  "start_offset_seconds":abs(start-lower)*86400.0,
  "end_offset_seconds":abs(native_end-upper)*86400.0,
  "midpoint_offset_seconds":abs(native_midpoint-midpoint)*86400.0,
 }
 worst=max(offsets.values())
 if worst>float(tolerance_seconds):
  raise ValueError(
   "native FITS MJD-OBS/EXPTIME disagrees with frozen SIAv2 time bounds "
   f"(max offset {worst:.3f} s > {tolerance_seconds:.3f} s)"
  )
 return {
  "native_mjd_obs":start,
  "native_exposure_time_s":exposure,
  "native_midpoint_mjd":native_midpoint,
  "manifest_midpoint_mjd":midpoint,
  **offsets,
  "maximum_allowed_offset_seconds":float(tolerance_seconds),
 }


def write_json(path:Path,value:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,default=str),encoding="utf-8")
def run_pilot(manifest_path:Path,output_dir:Path,*,code_revision:str,skip_source_poisson_injection:bool=True)->dict[str,Any]:
 revision=str(code_revision).strip().lower()
 if len(revision)!=40 or any(c not in "0123456789abcdef" for c in revision): raise ValueError("code_revision must be a full 40-character Git commit SHA")
 manifest=json.loads(manifest_path.read_text(encoding="utf-8")); validation=validate_pilot_manifest(manifest)
 if not SOURCE_CATALOGUE.is_file(): raise FileNotFoundError(SOURCE_CATALOGUE)
 source=manifest["source_catalogue"]; output_dir.mkdir(parents=True,exist_ok=True)
 catalogue_uri=f"https://github.com/{REPOSITORY}/blob/{revision}/data/spherex_orion_source_catalogue_snapshot.json"
 catalogue_file=file_record(catalogue_uri,SOURCE_CATALOGUE)
 source_record={"source_id":str(source["source_id"]),"ra_deg":float(source["ra_deg"]),"dec_deg":float(source["dec_deg"]),"sample_class":"catalogue_candidate_only_not_independently_confirmed","classification_reference":catalogue_uri,"catalogue_labels":{"yso_pub":source.get("yso_pub"),"class_1":source.get("class_1"),"stype_ml":source.get("stype_ml"),"stype_ml_prob1":source.get("stype_ml_prob1")}}
 run_id=os.environ.get("GITHUB_RUN_ID")
 audit_uri=f"https://github.com/{REPOSITORY}/actions/runs/{run_id}" if run_id else f"https://github.com/{REPOSITORY}/commit/{revision}"
 started=datetime.now(timezone.utc).isoformat(); epoch_records=[]; extraction_results=[]
 for index,product in enumerate(manifest["products"],start=1):
  obsid=str(product["observation_id"]); epoch_dir=output_dir/"epochs"/obsid; audit_dir=epoch_dir/"audit"; audit_dir.mkdir(parents=True,exist_ok=True)
  log_path=epoch_dir/"native_audit_runner.log"
  command=[sys.executable,"-m","research_discovery.spherex.run_real_field_audit","--field",f"{source['region']},{source['ra_deg']},{source['dec_deg']}","--science-uri",str(product["native_uri"]),"--bandpass","SPHEREx-D2","--release","dr1","--out",str(audit_dir)]
  if skip_source_poisson_injection: command.append("--skip-calibrated-injection")
  record={"index":index,"archive_product_id":product["archive_product_id"],"observation_id":obsid,"native_uri":product["native_uri"],"mjd_midpoint":product["mjd_midpoint"],"status":"pending","runner_log":str(log_path.relative_to(output_dir))}
  try:
   completed=subprocess.run(command,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
   log_path.write_text(completed.stdout,encoding="utf-8"); record["audit_return_code"]=completed.returncode
   summary_path=audit_dir/"real_field_audit_summary.json"; audit_path=audit_dir/"native_mef_audit.json"
   if not summary_path.is_file() or not audit_path.is_file(): raise RuntimeError("native audit did not produce summary and native_mef_audit.json")
   summary=json.loads(summary_path.read_text(encoding="utf-8")); audit=json.loads(audit_path.read_text(encoding="utf-8"))
   if completed.returncode!=0: raise RuntimeError(f"native audit exited {completed.returncode}; see runner log")
   science=summary.get("science") or {}
   if science.get("uri")!=product["native_uri"]: raise ValueError("retrieved science URI differs from frozen URI")
   if science.get("observation_id")!=obsid: raise ValueError("native science OBSID differs from frozen observation ID")
   if science.get("detector")!="D2" or str(science.get("release","")).upper()!="DR1": raise ValueError("retrieved science file is not DR1 D2")
   timing=validate_native_observation_time(science,product,tolerance_seconds=5.0)
   decision=audit.get("calibration_compatibility") or {}
   if audit.get("status")!="STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS" or decision.get("status")!="compatible": raise ValueError("native MEF or calibration compatibility gate did not pass")
   selected=summary.get("selected_products") or {}; spectral=selected.get("spectral_wcs") or {}; area=selected.get("solid_angle") or {}
   if not spectral.get("local_path") or not area.get("local_path"): raise ValueError("native audit omitted spectral-WCS or solid-angle local file")
   audit_file=file_record(audit_uri,audit_path)
   result=extract_source_photometry(
    science_file={"uri":science["uri"],"local_path":science["local_path"],"sha256":science["sha256"]},
    spectral_wcs_file={"uri":spectral["uri"],"local_path":spectral["local_path"],"sha256":spectral["sha256"]},
    solid_angle_file={"uri":area["uri"],"local_path":area["local_path"],"sha256":area["sha256"]},
    product_record={"archive_product_id":product["archive_product_id"],"observation_id":obsid,"mjd":float(product["mjd_midpoint"]),"detector":"D2","release":"DR1","calibration_group":decision.get("compatibility_group")},
    source_record=source_record,source_catalogue_file=catalogue_file,native_mef_audit_file=audit_file,compatibility_decision=decision,
    code_commit=revision,output_dir=epoch_dir/"photometry",stamp_size=11)
   extraction_results.append(result); m=result["measurements"][0]
   record.update({"status":"photometry_extracted" if m.get("valid") else "fit_review_required","native_time_validation":timing,"native_mef_audit_status":audit.get("status"),"calibration_compatibility_status":decision.get("status"),"calibration_group":decision.get("compatibility_group"),"science_sha256":science.get("sha256"),"spectral_wcs_sha256":spectral.get("sha256"),"solid_angle_sha256":area.get("sha256"),"native_mef_audit_sha256":audit_file["sha256"],"measurement_id":m.get("measurement_id"),"flux_jy":m.get("flux_jy"),"sigma_jy":m.get("sigma_jy"),"snr":m.get("fit_diagnostics",{}).get("snr"),"wavelength_um":m.get("wavelength_um"),"bandwidth_um":m.get("bandwidth_um"),"fit_status":m.get("fit_status"),"photometry_output":result.get("output_path")})
  except Exception as exc: record.update({"status":"epoch_failed","error":f"{type(exc).__name__}: {exc}"})
  epoch_records.append(record); write_json(output_dir/"epoch_records.json",epoch_records)
  print(json.dumps({"epoch":index,"observation_id":obsid,"status":record["status"],"error":record.get("error")}),flush=True)
 series_result=None; series_error=None
 if extraction_results:
  try: series_result=assemble_source_photometry_series(extraction_results,minimum_epochs=int(manifest["selection_policy"]["minimum_epochs"]),verify_files=True,minimum_band_overlap_fraction=float(manifest["selection_policy"]["minimum_band_overlap_fraction"]),output_path=output_dir/"source_timeseries.json")
  except Exception as exc: series_error=f"{type(exc).__name__}: {exc}"
 nested=(series_result or {}).get("verified_source_timeseries") or {}; sources=nested.get("sources") or []
 time_summary=(sources[0].get("time_series_summary") or {}) if sources else {}
 usable=bool(time_summary.get("usable_multi_epoch_series")); extracted=sum(x.get("status")=="photometry_extracted" for x in epoch_records)
 status="verified_multi_epoch_source_series" if usable else "incomplete_no_verified_multi_epoch_source_series"
 report={"schema":SCHEMA,"status":status,"started_utc":started,"finished_utc":datetime.now(timezone.utc).isoformat(),"code_revision":revision,"pilot_manifest_sha256":validation["manifest_sha256"],"source_id":source["source_id"],"designation":source.get("designation"),"region":source.get("region"),"catalogue_label_boundary":"Catalogue YSO labels are not independent confirmation.","requested_epoch_count":len(manifest["products"]),"successful_photometry_epoch_count":extracted,"failed_or_review_required_epoch_count":len(epoch_records)-extracted,"epoch_records":epoch_records,"series_error":series_error,"series_status":series_result.get("series_status") if series_result else "not_assembled","time_series_summary":time_summary,"verified_source_timeseries_manifest_sha256":nested.get("source_timeseries_manifest_sha256") if nested else None,"scientific_boundary":["Only four verified distinct native observation epochs can be called a multi-epoch series.","Included photometry is bound to native science, spectral-WCS, solid-angle, audit and rendered ePSF bytes.","Review-required fits are not made valid; failed epochs are never imputed.","Flux uncertainty uses delivered Level-2 VARIANCE as a diagonal covariance; correlated noise, PSF systematics and deblending are not included.","Catalogue class labels are not independent YSO confirmation.","No population-level rate, variability discovery, blind benchmark or performance superiority is claimed."]}
 write_json(output_dir/"pilot_summary.json",report)
 print(json.dumps({"status":status,"source_id":source["source_id"],"successful_epochs":extracted,"requested_epochs":len(epoch_records),"series_error":series_error},indent=2))
 return report
def main():
 parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST); parser.add_argument("--out",type=Path,default=ROOT/"data"/"spherex_source_timeseries_pilot"); parser.add_argument("--code-revision",required=True); parser.add_argument("--allow-calibrated-source-poisson",action="store_true"); args=parser.parse_args()
 run_pilot(args.manifest,args.out,code_revision=args.code_revision,skip_source_poisson_injection=not args.allow_calibrated_source_poisson)
if __name__=="__main__": main()
