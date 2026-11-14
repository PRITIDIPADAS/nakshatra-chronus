"""Train and test the five hypothesis engine on practice fields with a known truth.

Writes data/engine.json (the frozen model) and data/validation.json (all scores). Run: python scripts/calibrate_engine.py
Every number in the validation file comes from fields that the model did not see in training.
"""
import json
import math
import os
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
warnings.filterwarnings("ignore")

import core  # noqa: E402
import pipeline as P  # noqa: E402
import sky  # noqa: E402

N_FIELDS = int(os.environ.get("N_FIELDS", "360"))
N_NULL = int(os.environ.get("N_NULL", "40"))


def one(args):
    seed, kind = args
    rng = np.random.default_rng(seed)
    center = (float(rng.uniform(0, 360)), float(rng.uniform(-70, 70)))
    hard = float(rng.uniform(0.8, 2.2))
    spec = sky.make_spec(seed, center=center, events="none" if kind == "null" else "random", hard=hard)
    E, truth, cat = sky.render(spec)
    core.prepare(E)
    S = P.run(E, cat, center=spec["center"])
    lab, found, missed = P.match_truth(S, truth)
    static, moving_static = static_stars(S, spec, truth)
    rows = [dict(f=c["f"], y=c["truth"], sub=c["truth_sub"], methods=c["methods"]) for c in S["cands"]]
    ev = []
    for t in found + missed:
        ev.append(dict(kind=t["kind"], sub=t.get("sub"), mag=t.get("mag"), amp=t.get("amp"), pm=math.hypot(*t.get("pm", [0, 0])) if t.get("pm") else 0.0,
                       level=t.get("level"), found=t in found))
    return dict(seed=seed, kind=kind, hard=hard, rows=rows, events=ev, static_groups=static, static_moving=moving_static,
                floor=S["floor"], pfloor=S["pfloor"])


def static_stars(S, spec, truth):
    """Catalog stars with no motion, far from every planted change: how many does the motion court call moving?"""
    stars = [s for s in spec["sources"] if s.get("kind") == "star" and not s.get("pm_ra") and not s.get("pm_dec")]
    ev = []
    for t in truth:
        x, y = core.to_pix(S["ref"], t["ra"], t["dec"])
        ev.append((float(x[0]), float(y[0])))
    pos = []
    for s in stars:
        x, y = core.to_pix(S["ref"], s["ra"], s["dec"])
        if all(math.hypot(x[0] - a, y[0] - b) > 4 for a, b in ev):
            pos.append((float(x[0]), float(y[0])))
    n = k = 0
    for g in S["groups"]:
        if len(g) == S["E"] and min(d["snr"] for d in g) > 10:
            gx, gy = np.mean([d["x"] for d in g]), np.mean([d["y"] for d in g])
            if any(math.hypot(gx - a, gy - b) < 1.0 for a, b in pos):
                mo = P.motion(g, S["mjd_ep"], S["floor"])
                n += 1
                k += int(mo["dbic"] > P.TH["motion_dbic"] and mo["sig"] > P.TH["motion_sig"])
    return n, k


def controls_only(n=60):
    """Recompute the static star control and update data/validation.json."""
    with Pool(max(1, os.cpu_count() or 1)) as pool:
        res = pool.map(one, [(10000 + k, "random") for k in range(n)], chunksize=3)
    st, sm = sum(r["static_groups"] for r in res), sum(r["static_moving"] for r in res)
    p = os.path.join(ROOT, "data", "validation.json")
    v = json.load(open(p))
    v["controls"].update(static_stars=st, static_called_moving=sm, static_false_motion_rate=sm / max(st, 1), static_lo_hi=core.wilson(sm, max(st, 1)))
    json.dump(v, open(p, "w"), indent=1)
    print(st, sm)


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def main():
    t0 = time.time()
    jobs = [(10000 + k, "random") for k in range(N_FIELDS)] + [(50000 + k, "null") for k in range(N_NULL)]
    with Pool(max(1, os.cpu_count() or 1)) as pool:
        res = pool.map(one, jobs, chunksize=4)
    print(f"{len(res)} fields in {time.time() - t0:.0f} s")
    rnd = [r for r in res if r["kind"] == "random"]
    nul = [r for r in res if r["kind"] == "null"]
    split = int(0.7 * len(rnd))
    train, test = rnd[:split], rnd[split:]
    names, classes = list(P.FEATURES), list(sky.CLASSES)

    def XY(fields):
        rows = [row for r in fields for row in r["rows"]]
        X = np.array([[row["f"][k] for k in names] for row in rows], float)
        y = np.array([classes.index(row["y"]) for row in rows])
        return X, y, rows

    Xtr, ytr, _ = XY(train)
    Xte, yte, rte = XY(test)
    from sklearn.covariance import LedoitWolf
    from sklearn.linear_model import LogisticRegression
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd
    w = np.bincount(ytr, minlength=len(classes)).astype(float)
    cw = {k: len(ytr) / (len(classes) * max(w[k], 1)) for k in range(len(classes))}
    lr = LogisticRegression(C=0.5, max_iter=4000, class_weight=cw).fit(Ztr, ytr)
    # Temperature on the training fields only: the scale that makes the probabilities honest.
    def nll(T):
        p = softmax((Ztr @ lr.coef_.T + lr.intercept_) / T)
        return -np.mean(np.log(p[np.arange(len(ytr)), ytr] + 1e-12))
    Ts = np.linspace(0.5, 3.0, 51)
    T = float(Ts[int(np.argmin([nll(t) for t in Ts]))])
    lw = LedoitWolf().fit(Ztr)
    prec = np.linalg.inv(lw.covariance_)
    d2tr = np.einsum("ij,jk,ik->i", Ztr, prec, Ztr)
    ood = float(np.quantile(d2tr, 0.995))
    engine = dict(features=names, classes=classes, mean=mu.tolist(), scale=sd.tolist(), coef=lr.coef_.tolist(), intercept=lr.intercept_.tolist(),
                  temperature=T, ood_mean=lw.location_.tolist(), ood_precision=prec.tolist(), ood_threshold=ood, unknown_p=0.55,
                  trained_on=dict(fields=len(train), candidates=int(len(ytr)), per_class={c: int((ytr == k).sum()) for k, c in enumerate(classes)}),
                  note="Multinomial logistic model on practice field candidates. Equal priors. Probabilities hold for the practice sky only.")
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    json.dump(engine, open(os.path.join(ROOT, "data", "engine.json"), "w"), indent=1)

    # ------------------------------------------------------------ scores on the test fields
    p = softmax((Zte @ lr.coef_.T + lr.intercept_) / T)
    pred = p.argmax(1)
    d2 = np.einsum("ij,jk,ik->i", (Zte - lw.location_), prec, (Zte - lw.location_))
    unknown = (p.max(1) < engine["unknown_p"]) | (d2 > ood)
    K = len(classes)
    conf = np.zeros((K, K), int)
    for a, b in zip(yte, pred):
        conf[a, b] += 1
    onehot = np.eye(K)[yte]
    brier = float(np.mean(np.sum((p - onehot) ** 2, 1)))
    conf_top = p.max(1)
    bins = np.linspace(0, 1, 11)
    rel, ece = [], 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (conf_top >= lo) & (conf_top < hi + (1e-9 if hi == 1 else 0))
        if m.sum():
            acc = float(np.mean(pred[m] == yte[m]))
            rel.append(dict(lo=float(lo), hi=float(hi), n=int(m.sum()), confidence=float(conf_top[m].mean()), accuracy=acc))
            ece += m.sum() / len(yte) * abs(acc - conf_top[m].mean())
    per = {}
    for k, c in enumerate(classes):
        tp, fp, fn = conf[k, k], conf[:, k].sum() - conf[k, k], conf[k, :].sum() - conf[k, k]
        per[c] = dict(precision=float(tp / max(tp + fp, 1)), recall=float(tp / max(tp + fn, 1)), n=int(conf[k, :].sum()))
    # Agreement patterns: how often a candidate with each method pattern is a real sky change.
    pat = {}
    for row in rte:
        q = pat.setdefault(row["methods"], dict(n=0, sky=0, artefact=0, null=0))
        q["n"] += 1
        q["sky" if row["y"] in ("moving", "variable", "transient") else row["y"]] += 1
    for q in pat.values():
        q["sky_fraction"] = q["sky"] / q["n"]
        lo, hi = core.wilson(q["sky"], q["n"])
        q["lo"], q["hi"] = lo, hi
    by_n = {}
    for row in rte:
        q = by_n.setdefault(str(len(row["methods"])), dict(n=0, sky=0))
        q["n"] += 1
        q["sky"] += row["y"] in ("moving", "variable", "transient")
    for q in by_n.values():
        q["sky_fraction"] = q["sky"] / q["n"]
        q["lo"], q["hi"] = core.wilson(q["sky"], q["n"])
    # Camera effects: how many does the engine call artefact or unknown, by kind.
    adv = {}
    for row, k, u in zip(rte, pred, unknown):
        if row["y"] != "artefact":
            continue
        q = adv.setdefault(row["sub"], dict(n=0, artefact=0, unknown=0, called_sky=0))
        q["n"] += 1
        if u:
            q["unknown"] += 1
        elif classes[k] == "artefact":
            q["artefact"] += 1
        elif classes[k] in ("moving", "variable", "transient"):
            q["called_sky"] += 1
    for q in adv.values():
        q["rejected"] = (q["artefact"] + q["unknown"]) / q["n"]
        q["lo"], q["hi"] = core.wilson(q["artefact"] + q["unknown"], q["n"])
    # Completeness: planted sky changes and camera effects that became a candidate, by kind and brightness.
    comp = {}
    for r in test:
        for e in r["events"]:
            key = e["kind"] if e["kind"] != "artefact" else "artefact"
            if e["kind"] == "artefact":
                b = "strong" if (e.get("level") or 0) >= 30 else "weak"
            else:
                b = f"{int(math.floor(e['mag']))}" if e.get("mag") is not None else "?"
            q = comp.setdefault(key, {}).setdefault(b, dict(n=0, found=0))
            q["n"] += 1
            q["found"] += int(e["found"])
    for d in comp.values():
        for q in d.values():
            q["fraction"] = q["found"] / q["n"]
            q["lo"], q["hi"] = core.wilson(q["found"], q["n"])
    # Negative controls: fields with no planted change, and stars that do not move.
    null_c = [len(r["rows"]) for r in nul]
    area = (49 * core.PIX / 3600) ** 2
    st = sum(r["static_groups"] for r in res)
    sm = sum(r["static_moving"] for r in res)
    controls = dict(null_fields=len(nul), null_candidates_mean=float(np.mean(null_c)), null_candidates_max=int(max(null_c)),
                    null_candidates_per_deg2=float(np.mean(null_c) / area), null_patterns={k: sum(row["methods"] == k for r in nul for row in r["rows"]) for k in
                                                                                         sorted({row["methods"] for r in nul for row in r["rows"]})},
                    static_stars=st, static_called_moving=sm, static_false_motion_rate=sm / max(st, 1), static_lo_hi=core.wilson(sm, max(st, 1)),
                    astrometric_floor_px=float(np.median([r["floor"] for r in res])),
                    photometric_floor={str(d): float(np.median([r["pfloor"].get(d, np.nan) for r in res])) for d in range(1, 7)})
    unk = dict(fraction=float(unknown.mean()), accuracy_when_decided=float(np.mean(pred[~unknown] == yte[~unknown])) if (~unknown).any() else None,
               accuracy_all=float(np.mean(pred == yte)))
    # Research questions use these tables: method pattern by truth and by artefact kind.
    val = dict(classes=classes, test_fields=len(test), test_candidates=int(len(yte)), confusion=conf.tolist(), per_class=per, brier=brier, ece=float(ece),
               reliability=rel, unknown=unk, agreement_patterns=pat, agreement_by_count=by_n, adversarial=adv, completeness=comp, controls=controls,
               temperature=T, coefficients={c: dict(zip(names, np.round(lr.coef_[k], 3).tolist())) for k, c in enumerate(classes)},
               note="Practice sky only. Fields 70 percent train, 30 percent test, split by field.")
    json.dump(val, open(os.path.join(ROOT, "data", "validation.json"), "w"), indent=1)
    print(json.dumps(dict(acc=unk, brier=brier, ece=ece, per=per, by_n=by_n, controls=controls), indent=1)[:3000])


if __name__ == "__main__":
    if "--controls" in sys.argv:
        controls_only()
    else:
        main()
