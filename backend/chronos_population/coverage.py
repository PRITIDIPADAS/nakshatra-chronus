"""Fail-closed coverage audit before a single population investigation."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math
from chronos_causal.wavelength_gate import validate_science_wavelength


def assess_population_coverage(fields: Sequence[Mapping[str, Any]], *,
    target_class: str = "young_stellar_object",
    feature_interval_um: Sequence[float], blue_continuum_um: Sequence[float],
    red_continuum_um: Sequence[float], minimum_independent_fields: int = 5,
    minimum_epochs_per_source: int = 3, minimum_feature_samples: int = 3,
    minimum_continuum_samples: int = 4, minimum_median_snr: float = 5.0,
    minimum_completeness: float = 0.5) -> dict[str, Any]:
    if not fields:
        raise ValueError("at least one field is required")
    intervals=[feature_interval_um,blue_continuum_um,red_continuum_um]
    if any(len(x)!=2 for x in intervals):
        raise ValueError("feature and continuum intervals require lower and upper wavelengths")
    feature,blue,red=[tuple(map(float,x)) for x in intervals]
    if not (0 < blue[0] < blue[1] < feature[0] < feature[1] < red[0] < red[1]):
        raise ValueError("continuum and feature intervals must be positive, ordered and non-overlapping")
    field_reports=[];eligible_sources=[];seen=set();failure_counts={}
    for field in fields:
        fid=str(field.get("field_id","")).strip(); reasons=[]
        if not fid: reasons.append("field_id_missing")
        if fid in seen: reasons.append("duplicate_field_id")
        seen.add(fid)
        if str(field.get("dataset_class",field.get("data_class","unverified"))).lower()!="real":
            reasons.append("field_not_labelled_real")
        if field.get("independent_field") is not True: reasons.append("independence_not_attested")
        if not field.get("null_control_id"): reasons.append("null_control_not_identified")
        injected=int(field.get("n_injected",0) or 0); recovered=int(field.get("n_recovered",0) or 0)
        completeness=recovered/injected if injected>0 and 0<=recovered<=injected else None
        if completeness is None: reasons.append("injection_completeness_missing")
        elif completeness<minimum_completeness: reasons.append("completeness_below_threshold")
        source_reports=[]
        for source in field.get("sources") or []:
            sid=str(source.get("source_id","")).strip(); sr=[]
            if not sid: sr.append("source_id_missing")
            if str(source.get("sample_class","")).lower()!=target_class: sr.append("sample_class_mismatch")
            if not source.get("classification_reference"): sr.append("independent_classification_reference_missing")
            valid=[]
            for index,row in enumerate(source.get("observations") or []):
                if row.get("valid",True) is False: continue
                try:
                    validate_science_wavelength(row,index=index)
                    mjd=float(row["mjd"]); wave=float(row["wavelength_um"])
                    flux=float(row["flux"]); sigma=float(row["sigma"])
                    if not all(map(math.isfinite,(mjd,wave,flux,sigma))) or sigma<=0:
                        raise ValueError("invalid measurement")
                    valid.append((mjd,wave,abs(flux)/sigma,str(row["calibration_group"])))
                except (ValueError,TypeError,KeyError):
                    sr.append("invalid_or_unverified_measurement")
            epochs={x[0] for x in valid}
            feat=sum(feature[0]<=x[1]<=feature[1] for x in valid)
            bc=sum(blue[0]<=x[1]<=blue[1] for x in valid)
            rc=sum(red[0]<=x[1]<=red[1] for x in valid)
            snrs=sorted(x[2] for x in valid); median=snrs[len(snrs)//2] if snrs else 0.0
            if len(epochs)<minimum_epochs_per_source: sr.append("insufficient_independent_epochs")
            if feat<minimum_feature_samples: sr.append("insufficient_feature_sampling")
            if bc+rc<minimum_continuum_samples: sr.append("insufficient_continuum_sampling")
            if median<minimum_median_snr: sr.append("median_snr_below_threshold")
            report={"source_id":sid,"epoch_count":len(epochs),"feature_samples":feat,
                "blue_continuum_samples":bc,"red_continuum_samples":rc,"median_snr":median,
                "calibration_groups":sorted({x[3] for x in valid}),
                "eligible":not sr,"reasons":sorted(set(sr))}
            source_reports.append(report)
            if report["eligible"]:
                eligible_sources.append({"field_id":fid,"source_id":sid,"epoch_count":len(epochs),
                    "calibration_groups":report["calibration_groups"]})
        if not any(x["eligible"] for x in source_reports):
            reasons.append("no_source_passed_coverage_gates")
        for reason in reasons: failure_counts[reason]=failure_counts.get(reason,0)+1
        field_reports.append({"field_id":fid,"dataset_class":field.get("dataset_class",field.get("data_class","unverified")),
            "eligible":not reasons,"reasons":sorted(set(reasons)),"injection_completeness":completeness,
            "null_control_id":field.get("null_control_id"),"sources":source_reports})
    eligible_fields=sum(x["eligible"] for x in field_reports)
    if eligible_fields<minimum_independent_fields: failure_counts["too_few_independent_fields"]=1
    passed=eligible_fields>=minimum_independent_fields and all(x["eligible"] for x in field_reports)
    return {"status":"coverage_passed_preregistration_required" if passed else "not_ready_or_infeasible",
        "eligible_for_predeclared_population_protocol":passed,"target_class":target_class,
        "predeclared_intervals_um":{"feature":list(feature),"blue_continuum":list(blue),"red_continuum":list(red)},
        "thresholds":{"minimum_independent_fields":minimum_independent_fields,"minimum_epochs_per_source":minimum_epochs_per_source,
            "minimum_feature_samples":minimum_feature_samples,"minimum_continuum_samples":minimum_continuum_samples,
            "minimum_median_snr":minimum_median_snr,"minimum_completeness":minimum_completeness},
        "field_count":len(field_reports),"eligible_field_count":eligible_fields,"eligible_sources":eligible_sources,
        "fields":field_reports,"failure_counts":failure_counts,
        "next_step":"Freeze the inclusion, exclusion, null-control, selection and analysis protocol before measuring outcomes." if passed else "Do not calculate a population result; improve or document infeasible archive coverage.",
        "limitations":["Checks supplied records only; it does not query the archive or independently validate source classification.",
            "CWAVE/CBAND provenance is required for every valid real measurement.",
            "A coverage pass is not evidence for a physical population trend."]}
