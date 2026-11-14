#!/usr/bin/env python3
"""Build blinded human-review tasks from real, pre-prepared SPHEREx epoch cutouts.

Input CSV columns: case_id,epoch_a,epoch_b[,difference,answer_key,field_id].
The output task manifest deliberately omits answer_key and field_id.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,secrets
from pathlib import Path

ALLOWED_LABELS={"moving_source","stationary_source","artifact","uncertain"}
REQUIRED={"case_id","epoch_a","epoch_b"}


def build_tasks(input_csv:Path,outdir:Path,*,seed:int=20261114)->dict:
    import random
    rows=list(csv.DictReader(input_csv.open(newline="",encoding="utf-8-sig")))
    if not rows: raise ValueError("Input CSV contains no cases")
    missing=REQUIRED-set(rows[0])
    if missing: raise ValueError(f"Missing columns: {sorted(missing)}")
    ids=[r["case_id"].strip() for r in rows]
    if any(not x for x in ids) or len(set(ids))!=len(ids): raise ValueError("case_id values must be non-empty and unique")
    tasks=[];answer_key={};rng=random.Random(seed)
    for r in rows:
        case_id=r["case_id"].strip()
        # Opaque task ID prevents case IDs from carrying source labels.
        task_id=hashlib.sha256(f"{seed}:{case_id}".encode()).hexdigest()[:16]
        task={"task_id":task_id,"epoch_a":r["epoch_a"].strip(),"epoch_b":r["epoch_b"].strip(),
              "difference":r.get("difference","").strip(),
              "instruction":"Compare the same sky position at two distinct observation epochs. Classify the evidence, not the hypothesis."}
        tasks.append(task)
        label=r.get("answer_key","").strip()
        if label:
            if label not in ALLOWED_LABELS: raise ValueError(f"Invalid answer_key for {case_id}: {label}")
            answer_key[task_id]=label
    rng.shuffle(tasks)
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"tasks_public.json").write_text(json.dumps({"schema":"chronos-citizen-task-v1","tasks":tasks},indent=2))
    (outdir/"answer_key_private.json").write_text(json.dumps({"warning":"Do not publish with volunteer task file.","answer_key":answer_key},indent=2))
    return {"n_tasks":len(tasks),"n_keyed":len(answer_key),"task_file":str(outdir/"tasks_public.json"),
            "private_key_file":str(outdir/"answer_key_private.json"),
            "warning":"Answer keys are valid only when created from independently vetted controls or expert adjudication."}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("cases_csv",type=Path);p.add_argument("--out",type=Path,default=Path("citizen_tasks"));p.add_argument("--seed",type=int,default=20261114)
    a=p.parse_args();print(json.dumps(build_tasks(a.cases_csv,a.out,seed=a.seed),indent=2))
if __name__=="__main__":main()
