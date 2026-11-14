"""Aggregate multi-reviewer study responses with explicit incomplete-case handling."""
from __future__ import annotations
from typing import Any,Mapping,Sequence
from collections import defaultdict,Counter

def analyze_reviews(responses:Sequence[Mapping[str,Any]],answer_key:Mapping[str,str],machine_labels:Mapping[str,str]|None=None)->dict[str,Any]:
    by_case=defaultdict(list); by_person=defaultdict(list)
    for r in responses:
        if not all(k in r for k in ("participant_id","case_id","label")):raise ValueError("each row needs participant_id, case_id, label")
        p,c,l=str(r["participant_id"]),str(r["case_id"]),str(r["label"]);by_case[c].append(l);by_person[p].append(dict(r))
    cats=sorted({x for v in by_case.values() for x in v}); counts={c:Counter(v) for c,v in by_case.items()}; sizes={len(v) for v in by_case.values()}
    kappa=pbar=pe=None; included=[]
    if len(sizes)==1 and sizes and next(iter(sizes))>=2 and len(cats)>=2:
        n=next(iter(sizes)); N=len(counts); Pi=[]; totals=Counter()
        for c,co in counts.items():included.append(c);Pi.append((sum(v*v for v in co.values())-n)/(n*(n-1)));totals.update(co)
        pbar=sum(Pi)/N; probs=[totals[x]/(N*n) for x in cats];pe=sum(x*x for x in probs);kappa=(pbar-pe)/(1-pe) if pe<1 else None
    majority={};ties=[]
    for c,co in counts.items():
        m=max(co.values()); winners=[x for x,v in co.items() if v==m]
        majority[c]=winners[0] if len(winners)==1 else None
        if len(winners)>1:ties.append(c)
    scored=[c for c in answer_key if c in majority and majority[c] is not None]; acc=sum(majority[c]==str(answer_key[c]) for c in scored)/len(scored) if scored else None
    compar=[c for c in majority if majority[c] is not None and machine_labels and c in machine_labels]
    machine=sum(majority[c]==str(machine_labels[c]) for c in compar)/len(compar) if compar else None
    summaries={}
    for p,rows in by_person.items():
        known=[r for r in rows if str(r["case_id"]) in answer_key]; conf=[float(r["confidence"]) for r in rows if r.get("confidence") is not None]
        summaries[p]={"responses":len(rows),"scored_responses":len(known),"accuracy_on_keyed_cases":sum(str(r["label"])==str(answer_key[str(r["case_id"])]) for r in known)/len(known) if known else None,"mean_confidence":sum(conf)/len(conf) if conf else None}
    return {"response_count":len(responses),"participant_count":len(by_person),"case_count":len(by_case),"categories":cats,"fleiss_kappa":kappa,"fleiss_p_bar":pbar,"fleiss_p_e":pe,
      "fleiss_complete_case_ids":included,"equal_rater_count_per_case":len(sizes)==1,"majority_labels":majority,"majority_tie_cases":ties,
      "crowd_majority_accuracy_on_answer_key":acc,"human_machine_agreement":machine,"reviewer_summaries":summaries,
      "limitations":["Fleiss kappa requires equal reviewer counts per included case.","Answer key validity must be independently established.","Volunteer labels are not scientific ground truth without validation.","Anonymize participant identifiers before publication."]}
