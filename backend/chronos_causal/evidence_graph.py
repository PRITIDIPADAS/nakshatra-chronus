"""Evidence graph linking archive inputs, calibration, measurements, tests and conclusions."""
from __future__ import annotations
from typing import Any,Mapping,Sequence
import hashlib,json


def _seal(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str).encode()).hexdigest()


def build_evidence_graph(*,candidate_id:str,observations:Sequence[Mapping[str,Any]],
    analysis:Mapping[str,Any],manifest:Mapping[str,Any]|None=None,
    model_runs:Sequence[Mapping[str,Any]]=(),counterfactuals:Sequence[Mapping[str,Any]]=(),
    failed_tests:Sequence[Mapping[str,Any]]=(),environment:Mapping[str,Any]|None=None,
    code_commit:str|None=None):
    if not candidate_id.strip() or not observations: raise ValueError("candidate_id and observations are required")
    if not isinstance(analysis,Mapping) or "verdict" not in analysis: raise ValueError("analysis must contain verdict")
    root=f"candidate:{candidate_id}";nodes=[{"id":root,"type":"candidate","label":candidate_id}];edges=[];archive={}
    if manifest:
        for i,file in enumerate(manifest.get("files",[])):
            aid=str(file.get("archive_id",i));nid=f"archive:{aid}";archive[aid]=nid
            nodes.append({"id":nid,"type":"archive_product","label":aid,"product_type":file.get("product_type"),
                "release":file.get("release"),"detector":file.get("detector"),"native_uri":file.get("native_uri"),
                "sha256":file.get("sha256"),"calibration_group":file.get("calibration_group")})
            edges.append({"source":nid,"target":root,"relation":"input_product_for"})
            if "cal" in str(file.get("product_type","")).lower():
                cid=f"calibration:{aid}";nodes.append({"id":cid,"type":"calibration_product","label":aid,"sha256":file.get("sha256")})
                edges.append({"source":cid,"target":nid,"relation":"calibrates_or_supports"})
    for i,row in enumerate(observations):
        oid=str(row.get("observation_id",row.get("measurement_id",i)));nid=f"measurement:{oid}"
        nodes.append({"id":nid,"type":"measurement","label":oid,"record_sha256":_seal(dict(row)),
            "mjd":row.get("mjd"),"wavelength_um":row.get("wavelength_um"),"flux":row.get("flux"),
            "sigma":row.get("sigma"),"detector_id":row.get("detector_id",row.get("detector")),
            "calibration_group":row.get("calibration_group"),"calibration_product_id":row.get("calibration_product_id")})
        edges.append({"source":nid,"target":root,"relation":"measures_candidate"})
        cal=row.get("calibration_product_id")
        if cal and str(cal) in archive: edges.append({"source":archive[str(cal)],"target":nid,"relation":"calibration_for_measurement"})
    for i,run in enumerate(model_runs):
        rid=str(run.get("run_id",i));nid=f"model_run:{rid}"
        nodes.append({"id":nid,"type":"model_run","label":rid,"record_sha256":_seal(dict(run)),
            "model":run.get("model"),"score":run.get("score"),"score_type":run.get("score_type")})
        edges.append({"source":root,"target":nid,"relation":"evaluated_by_model"})
    analysis_id="analysis:"+_seal(dict(analysis))
    nodes.append({"id":analysis_id,"type":"analysis","label":str(analysis.get("verdict")),
        "record_sha256":_seal(dict(analysis)),"leading_model":analysis.get("leading_model"),
        "relative_model_support":analysis.get("relative_model_support")})
    edges.append({"source":root,"target":analysis_id,"relation":"conclusion_recorded_as"})
    for i,cf in enumerate(counterfactuals):
        nid=f"counterfactual:{cf.get('id',i)}";nodes.append({"id":nid,"type":"counterfactual","label":str(cf.get("id",i)),
            "intervention":cf.get("intervention"),"record_sha256":_seal(dict(cf))})
        edges.append({"source":analysis_id,"target":nid,"relation":"challenged_by"})
    for i,test in enumerate(failed_tests):
        nid=f"failed_test:{test.get('test_id',test.get('name',i))}"
        nodes.append({"id":nid,"type":"failed_or_null_test","label":str(test.get("name",i)),
            "status":test.get("status","failed_or_unresolved"),"reason":test.get("reason"),
            "record_sha256":_seal(dict(test))})
        edges.append({"source":nid,"target":analysis_id,"relation":"qualifies_or_contradicts"})
    manifest_id=None
    if manifest:
        manifest_id="manifest:"+_seal(dict(manifest))
        nodes.append({"id":manifest_id,"type":"provenance_manifest","label":"Archive/calibration manifest",
            "record_sha256":_seal(dict(manifest)),"manifest_sha256":manifest.get("manifest_sha256")})
        edges.append({"source":manifest_id,"target":root,"relation":"documents_inputs_for"})
    if environment:
        env_id="environment:"+_seal(dict(environment));nodes.append({"id":env_id,"type":"software_environment","label":"Software environment",
            "environment":dict(environment),"record_sha256":_seal(dict(environment))})
        edges.append({"source":env_id,"target":analysis_id,"relation":"executed_in"})
    if code_commit:
        commit_id=f"commit:{code_commit}";nodes.append({"id":commit_id,"type":"code_commit","label":code_commit})
        edges.append({"source":commit_id,"target":analysis_id,"relation":"implemented_by"})
    return {"schema":"chronos-evidence-graph/2.0","candidate_id":candidate_id,"nodes":nodes,"edges":edges,
        "claim":{"verdict":analysis.get("verdict"),"leading_model":analysis.get("leading_model"),
            "abstention_reasons":analysis.get("abstention_reasons",[]),
            "status":"unresolved" if analysis.get("verdict")=="unknown" else "model_selected_not_confirmed",
            "support_type":"relative model support, not calibrated posterior probability"},
        "graph_sha256":_seal({"nodes":nodes,"edges":edges}),
        "limitations":["Hashes detect changes but do not prove authorship, identity or source authenticity.",
            "A selected model is not a confirmed astronomical discovery.",
            "The graph does not independently validate calibration or physical identity."]}
