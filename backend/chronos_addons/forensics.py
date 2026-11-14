"""Transparent, deterministic detector/contamination triage; not a classifier."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import numpy as np

DEFAULT_THRESHOLDS={"flagged_fraction_warning":.10,"flagged_fraction_strong":.50,"psf_reduced_chi2_warning":3.0,
 "noise_scale_warning":1.5,"template_overlap_warning":.35,"partner_non_detection_snr":2.0,
 "candidate_detection_snr":5.0,"position_scatter_warning_pixels":.75}

def template_overlap_score(template: np.ndarray, candidate_mask: np.ndarray)->float:
    t=np.asarray(template,float); m=np.asarray(candidate_mask,bool)
    if t.shape!=m.shape: raise ValueError("template and candidate mask shapes differ")
    weights=np.clip(np.nan_to_num(t,nan=0),0,None); total=float(weights.sum())
    return 0.0 if total<=0 else float(weights[m].sum()/total)

def diagnose_candidate(evidence: Mapping[str,Any], thresholds: Mapping[str,float]|None=None)->dict[str,Any]:
    th=dict(DEFAULT_THRESHOLDS)
    if thresholds:
        for k,v in thresholds.items():
            if k not in th or not np.isfinite(float(v)) or float(v)<0: raise ValueError(f"invalid threshold {k}={v}")
            th[k]=float(v)
    findings=[]
    def add(code,severity,value,limit,note): findings.append({"code":code,"severity":severity,"measured_value":value,"threshold":limit,"note":note})
    if evidence.get("candidate_snr") is not None and float(evidence["candidate_snr"])<th["candidate_detection_snr"]:
        add("LOW_CANDIDATE_SNR","warning",float(evidence["candidate_snr"]),th["candidate_detection_snr"],"Candidate below configured detection threshold.")
    if evidence.get("flagged_fraction") is not None:
        x=float(evidence["flagged_fraction"])
        if not 0<=x<=1: raise ValueError("flagged_fraction must be in [0,1]")
        if x>=th["flagged_fraction_strong"]: add("FLAG_DOMINATED","strong",x,th["flagged_fraction_strong"],"Large fraction of footprint is flagged; inspect official bit definitions.")
        elif x>=th["flagged_fraction_warning"]: add("FLAG_OVERLAP","warning",x,th["flagged_fraction_warning"],"Candidate overlaps flagged pixels.")
    checks=[("psf_reduced_chi2","PSF_MISMATCH","psf_reduced_chi2_warning","Profile differs from supplied detector-zone PSF/ePSF."),
      ("noise_scale","NOISE_UNDERMODEL_RISK","noise_scale_warning","Empirical noise exceeds nominal scale."),
      ("partner_snr","PARTNER_ARRAY_NONDETECTION","partner_non_detection_snr","Simultaneous partner-array signal is weak."),
      ("same_detector_position_scatter_pixels","FIXED_DETECTOR_POSITION","position_scatter_warning_pixels","Residual remains near a fixed detector coordinate.")]
    for key,code,tkey,note in checks:
        if evidence.get(key) is not None:
            x=float(evidence[key]); trigger=x>=th[tkey] if key!="partner_snr" and key!="same_detector_position_scatter_pixels" else (x<th[tkey] if key=="partner_snr" else x<=th[tkey])
            if trigger: add(code,"warning",x,th[tkey],note)
    if evidence.get("release_mismatch") is True: add("RELEASE_MISMATCH","strong",True,True,"Incompatible release/calibration inputs were combined.")
    if evidence.get("one_detector_fraction") is not None and float(evidence["one_detector_fraction"])>=.9:
        add("SINGLE_DETECTOR_DOMINANCE","warning",float(evidence["one_detector_fraction"]),.9,"Signal concentrated in one detector.")
    templates=evidence.get("template_overlap_scores") or {}
    if not isinstance(templates,Mapping): raise ValueError("template_overlap_scores must be a mapping")
    for name,score in templates.items():
        x=float(score)
        if not 0<=x<=1: raise ValueError(f"template overlap {name} must be in [0,1]")
        if x>=th["template_overlap_warning"]: add("TEMPLATE_OVERLAP:"+str(name),"warning",x,th["template_overlap_warning"],"Candidate overlaps supplied instrument template; verify provenance and detector applicability.")
    nstrong=sum(x["severity"]=="strong" for x in findings)
    status="instrumental-review-priority" if nstrong else ("review-required" if findings else "no-configured-instrument-warning")
    return {"candidate_id":evidence.get("candidate_id"),"status":status,"finding_count":len(findings),"findings":findings,
      "conflicts_to_reconcile":[x for x in ["Independent astrophysical support is also reported." if evidence.get("astrophysical_independent_support") else None,
      "Multi-epoch consistency is also reported; verify independence." if evidence.get("multi_epoch_consistent") else None] if x],
      "raw_detector_flags":list(evidence.get("detector_flags") or []),"thresholds":th,
      "limitations":["Triage findings are not probabilities or artefact verdicts.","Use official flag definitions and matching detector/version templates.","A weak partner array alone does not disprove an astrophysical source."]}

def calibration_ablation(baseline_positions: Sequence[Sequence[float]], variant_positions: Mapping[str,Sequence[Sequence[float]]], match_radius_pixels: float=2.0)->dict[str,Any]:
    base=np.asarray(baseline_positions,float).reshape((-1,2)) if len(baseline_positions) else np.empty((0,2))
    if match_radius_pixels<=0: raise ValueError("match radius must be positive")
    rows=[]
    for name,positions in variant_positions.items():
        var=np.asarray(positions,float).reshape((-1,2)) if len(positions) else np.empty((0,2)); used=set(); matches=0
        for p in base:
            if not len(var): break
            ds=np.linalg.norm(var-p,axis=1)
            j=next((int(i) for i in np.argsort(ds) if int(i) not in used and ds[i]<=match_radius_pixels),None)
            if j is not None: used.add(j); matches+=1
        rows.append({"variant":name,"candidate_count":len(var),"baseline_count":len(base),"matched_to_baseline":matches,
          "baseline_unmatched":len(base)-matches,"variant_unmatched":len(var)-matches,"match_radius_pixels":match_radius_pixels})
    return {"baseline_count":len(base),"variants":rows,"warning":"Counts/overlap are descriptive; test completeness and false alarms before calling a correction beneficial."}
