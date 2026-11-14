"""The citizen lab study: a fixed set of cases, written instructions, training cases with feedback, and blind repeats.

Every participant sees the same cases in the same order, so that answers can be pooled (Fleiss kappa), repeats can be
compared (test retest consistency) and the crowd can be compared with the engine and with the practice truth.
scripts/analyse_citizen_study.py pools the exported answers.
"""
import numpy as np

PROTOCOL = "CHRONOS citizen study v2"
ANSWERS = [("moving", "It moved"), ("variable", "It got brighter or fainter"), ("transient", "It appeared or disappeared"),
           ("artefact", "A camera effect, not the sky"), ("null", "Nothing changed"), ("unsure", "I can not tell")]
INSTRUCTIONS = [
    "You will see a small patch of the infrared sky at several visits, months apart. The pictures play in a loop.",
    "Look only at the spot in the middle. Ignore the other stars.",
    "It moved: the spot shifts from visit to visit. It got brighter or fainter: same place, different brightness.",
    "It appeared or disappeared: the spot is there in some visits and missing in others.",
    "A camera effect: a very sharp dot, or a spot that shows in one picture only and looks unlike a star.",
    "Answer from the pictures only. If you are unsure, say so: an honest 'I can not tell' is useful data.",
    "Some cases come back later. Answer them again as if new. This measures consistency, not memory.",
    "The first three cases are practice. After each one you see the answer. After that, you see nothing until the end.",
]
TARGET = dict(moving=3, variable=3, transient=2, artefact=3, null=1)


def case(fid, fname, c):
    post = c.get("post") or {}
    return dict(id=f"{fid}:{c['id']}", field=fid, field_name=fname, cand=c["id"], methods=c.get("methods"),
                visits=[dict(visit=v["visit"], img=v["img"]) for v in c["dossier"]["cutouts"]["visits"]],
                engine=("unknown" if post.get("unknown") else post.get("verdict")), truth=c.get("truth"), truth_sub=c.get("truth_sub"))


def make(fields, seed=15, n_repeat=4, gap=4):
    """fields: list of (key, name, investigation output). Returns the study definition."""
    rng = np.random.default_rng(seed)
    pool = {}
    for fid, fname, out in fields:
        for c in out.get("candidates", []):
            if c.get("truth") and c["dossier"]["cutouts"]["visits"]:
                pool.setdefault(c["truth"], []).append(case(fid, fname, c))
    for v in pool.values():
        rng.shuffle(v)
    training = [pool[k].pop() for k in ("moving", "variable", "artefact") if pool.get(k)]
    chosen = []
    for k, n in TARGET.items():
        chosen += pool.get(k, [])[:n]
        pool[k] = pool.get(k, [])[n:]
    spare = [c for v in pool.values() for c in v]
    while len(chosen) < sum(TARGET.values()) and spare:
        chosen.append(spare.pop())
    order = list(rng.permutation(len(chosen)))
    seq = [dict(case=int(i), repeat=False) for i in order]
    rep = [int(i) for i in rng.choice(order[: max(1, len(order) - gap)], size=min(n_repeat, max(1, len(order) - gap)), replace=False)]
    for i in rep:
        first = next(k for k, s in enumerate(seq) if s["case"] == i)
        at = int(rng.integers(min(first + gap + 1, len(seq)), len(seq) + 1))
        seq.insert(at, dict(case=i, repeat=True))
    return dict(protocol=PROTOCOL, instructions=INSTRUCTIONS, answers=[dict(key=k, label=l) for k, l in ANSWERS],
                confidence=["sure", "fairly sure", "guess"], training=training, cases=chosen, sequence=seq,
                note="Practice sky cases with a known truth. The engine verdict and the truth are shown only at the end.")


def fleiss(table):
    """Fleiss kappa. table: one row per case, one column per answer, counts of raters."""
    t = np.asarray(table, float)
    t = t[t.sum(1) >= 2]
    if not len(t):
        return None
    n = t.sum(1)
    p_j = t.sum(0) / n.sum()
    P_i = ((t * t).sum(1) - n) / (n * (n - 1))
    pe = float((p_j ** 2).sum())
    return None if pe >= 1 else float((P_i.mean() - pe) / (1 - pe))


def analyse(study, exports):
    """Pool exported answers of several participants."""
    keys = [a["key"] for a in study["answers"]]
    n_case = len(study["cases"])
    table = np.zeros((n_case, len(keys)), int)
    retest, per = [], []
    for ex in exports:
        first, ok, right, conf_right = {}, 0, 0, {}
        for r in ex.get("answers", []):
            if r.get("training"):
                continue
            i = r["case"]
            if not r.get("repeat"):
                first[i] = r["answer"]
                table[i, keys.index(r["answer"])] += 1
                truth = study["cases"][i]["truth"]
                ok += 1
                right += r["answer"] == truth
                q = conf_right.setdefault(r.get("confidence", "?"), [0, 0])
                q[0] += 1
                q[1] += r["answer"] == truth
        for r in ex.get("answers", []):
            if r.get("repeat") and r["case"] in first:
                retest.append(r["answer"] == first[r["case"]])
        per.append(dict(participant=ex.get("participant"), answered=ok, right=right / max(ok, 1),
                        by_confidence={k: v[1] / max(v[0], 1) for k, v in conf_right.items()}))
    majority = [keys[int(np.argmax(row))] if row.sum() else None for row in table]
    truth = [c["truth"] for c in study["cases"]]
    eng = [c["engine"] for c in study["cases"]]
    answered = [i for i in range(n_case) if majority[i]]
    return dict(protocol=study["protocol"], participants=len(exports), fleiss_kappa=fleiss(table),
                retest_consistency=(sum(retest) / len(retest)) if retest else None, retest_pairs=len(retest),
                crowd_majority_right=sum(majority[i] == truth[i] for i in answered) / max(len(answered), 1),
                engine_right=sum(e == t for e, t in zip(eng, truth)) / max(n_case, 1),
                crowd_engine_agree=sum(majority[i] == eng[i] for i in answered) / max(len(answered), 1),
                per_participant=per, table=table.tolist(), answer_keys=keys)
