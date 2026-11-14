"""Injection/recovery and held-out-field validation metrics."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
import math, random
import numpy as np

def wilson_interval(k:int,n:int,z:float=1.959963984540054):
    if n<0 or k<0 or k>n: raise ValueError("require 0 <= successes <= trials")
    if n==0:return (float("nan"),float("nan"))
    p=k/n; den=1+z*z/n; c=(p+z*z/(2*n))/den; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,c-h),min(1,c+h)
def _match(t,d,radius):
    if not len(t) or not len(d): return []
    # Solve a minimum-cost assignment with one private dummy column per truth
    # row. A real in-radius match is always cheaper than a dummy, so this first
    # maximizes the number of matches and then minimizes total separation.
    try:
        from scipy.optimize import linear_sum_assignment
        dist=np.linalg.norm(t[:,None,:]-d[None,:,:],axis=2)
        dummy=radius+max(1e-9,radius*1e-9)
        cost=np.full((len(t),len(d)+len(t)),dummy*10.0)
        cost[:,:len(d)]=np.where(dist<=radius,dist,dummy*10.0)
        for i in range(len(t)): cost[i,len(d)+i]=dummy
        rows,cols=linear_sum_assignment(cost)
        return [(int(i),int(j),float(dist[i,j])) for i,j in zip(rows,cols) if j<len(d) and dist[i,j]<=radius]
    except ImportError:
        pairs=sorted((float(np.linalg.norm(a-b)),i,j) for i,a in enumerate(t) for j,b in enumerate(d) if np.linalg.norm(a-b)<=radius)
        used_t=set();used_d=set();out=[]
        for sep,i,j in pairs:
            if i not in used_t and j not in used_d:used_t.add(i);used_d.add(j);out.append((i,j,sep))
        return out

def score_recovery(truth_positions,detection_positions,match_radius:float=2.0,field_area_deg2:float|None=None):
    if match_radius<=0: raise ValueError("match_radius must be positive")
    t=np.asarray(truth_positions,float).reshape((-1,2)) if len(truth_positions) else np.empty((0,2))
    d=np.asarray(detection_positions,float).reshape((-1,2)) if len(detection_positions) else np.empty((0,2))
    if np.any(~np.isfinite(t)) or np.any(~np.isfinite(d)): raise ValueError("positions must be finite")
    m=_match(t,d,match_radius); tp=len(m); fp=len(d)-tp; fn=len(t)-tp
    return {"truth_count":len(t),"detection_count":len(d),"true_positive":tp,"false_positive":fp,"false_negative":fn,
      "precision":tp/(tp+fp) if tp+fp else None,"recall_completeness":tp/(tp+fn) if tp+fn else None,
      "precision_wilson_95":wilson_interval(tp,tp+fp) if tp+fp else None,"recall_wilson_95":wilson_interval(tp,tp+fn) if tp+fn else None,
      "false_candidates_per_field":fp,"false_candidates_per_square_degree":fp/field_area_deg2 if field_area_deg2 and field_area_deg2>0 else None,
      "match_radius":match_radius,"matched_pairs":[{"truth_index":i,"detection_index":j,"separation":dist} for i,j,dist in m]}

def stratified_recovery(rows:Sequence[Mapping[str,Any]],match_radius:float=2.0)->dict[str,Any]:
    """Aggregate recovery by user-supplied scientific strata, keeping fields independent.

    Each input row must carry field_id, truth_positions and detection_positions;
    optional `stratum` is a mapping such as magnitude_bin, detector, visit_count
    or crowding_bin. Matching is performed separately per field before pooling.
    """
    groups={}
    for row in rows:
        if "field_id" not in row:raise ValueError("each stratified row needs field_id")
        stratum=row.get("stratum") or {"all":"all"}
        key="|".join(f"{k}={v}" for k,v in sorted(stratum.items()))
        groups.setdefault(key,[]).append(row)
    output={}
    for key,items in groups.items():
        scored=[score_recovery(x.get("truth_positions") or [],x.get("detection_positions") or [],match_radius) for x in items]
        tp=sum(x["true_positive"] for x in scored);fp=sum(x["false_positive"] for x in scored);fn=sum(x["false_negative"] for x in scored)
        output[key]={"fields":len(items),"truth":sum(x["truth_count"] for x in scored),"detections":sum(x["detection_count"] for x in scored),
          "true_positive":tp,"false_positive":fp,"false_negative":fn,"precision":tp/(tp+fp) if tp+fp else None,
          "completeness":tp/(tp+fn) if tp+fn else None,"false_candidates_per_field":fp/len(items) if items else None}
    return {"strata":output,"match_radius":match_radius,"warning":"Do not split or pool multiple exposures from the same field across train/test."}

def probability_metrics(true_labels:Sequence[str],probability_rows:Sequence[Mapping[str,float]|None],classes:Sequence[str],bins:int=10):
    if len(true_labels)!=len(probability_rows) or not true_labels: raise ValueError("labels and probabilities must have equal non-zero length")
    if bins<2: raise ValueError("bins must be >=2")
    cls=list(classes)
    if len(cls)<2 or any(x not in cls for x in true_labels): raise ValueError("classes must include all labels and at least two classes")
    ps=[]; truths=[]
    for truth,row in zip(true_labels,probability_rows):
        if row is None: continue
        p=np.array([float(row.get(c,0)) for c in cls])
        if np.any(~np.isfinite(p)) or np.any(p<0) or p.sum()<=0: raise ValueError("invalid probabilities")
        ps.append(p/p.sum()); truths.append(truth)
    coverage=len(ps)/len(true_labels)
    if not ps:return {"n":len(true_labels),"n_covered":0,"coverage":0.0,"classes":cls,"brier_score":None,"top_label_expected_calibration_error":None,"reliability_bins":[]}
    P=np.vstack(ps); Y=np.zeros_like(P)
    for i,label in enumerate(truths):Y[i,cls.index(label)]=1
    brier=float(np.mean(np.sum((P-Y)**2,axis=1))); idx=P.argmax(axis=1); conf=P[np.arange(len(P)),idx]
    correct=np.array([cls[j]==truths[i] for i,j in enumerate(idx)],float); edges=np.linspace(0,1,bins+1); ece=0.; bins_out=[]
    for i in range(bins):
        mask=(conf>=edges[i])&(conf<(edges[i+1]) if i<bins-1 else conf<=edges[i+1])
        if np.any(mask):
            c=float(conf[mask].mean()); a=float(correct[mask].mean()); ece+=float(mask.mean())*abs(a-c)
            bins_out.append({"lower":edges[i],"upper":edges[i+1],"count":int(mask.sum()),"mean_confidence":c,"accuracy":a})
    return {"n":len(true_labels),"n_covered":len(ps),"coverage":coverage,"classes":cls,"brier_score":brier,
      "top_label_expected_calibration_error":ece,"top_label_accuracy":float(correct.mean()),"reliability_bins":bins_out,
      "warning":"Evaluate on held-out sky fields, not randomly split pixels/candidates from the same field."}
def split_fields(field_ids:Sequence[str],test_fraction:float=.3,seed:int=17):
    ids=sorted(set(map(str,field_ids)))
    if len(ids)<2 or not 0<test_fraction<1: raise ValueError("need >=2 fields and 0<test_fraction<1")
    random.Random(seed).shuffle(ids); n=min(len(ids)-1,max(1,round(len(ids)*test_fraction)))
    return {"train_fields":sorted(ids[n:]),"test_fields":sorted(ids[:n]),"seed":seed,"field_level_split":True}
