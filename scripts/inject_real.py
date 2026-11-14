"""Inject known sources into real SPHEREx QR3 exposures, score CHRONOS on real noise, and retrain the engine.

Needs network access to NASA IRSA and the Gaia archive. Run:

    python scripts/inject_real.py                      # score only, the six target fields
    python scripts/inject_real.py --retrain            # also retrain the engine with the real noise rows
    python scripts/inject_real.py --retrain --install  # and make the retrained engine the one the app uses

Writes data/real_injection.json, and data/engine_real.json with --retrain. The scores of the retrained engine come
from fields that it did not see: each target field is held out in turn.
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
warnings.filterwarnings("ignore")

import connectors as cn  # noqa: E402
import core  # noqa: E402
import inject  # noqa: E402
import pipeline as P  # noqa: E402
import sky  # noqa: E402

DEFAULT = "barnard,epsindib,wise0855,rwaur,rdra"


def load_targets():
    import app  # noqa: F401  (fills the target table)
    import observatory as O
    return O.TARGETS


def practice_rows(n, seed0=10000):
    """Labelled rows from practice fields, made exactly as the main calibration makes them."""
    spec = importlib.util.spec_from_file_location("calibrate_engine", os.path.join(ROOT, "scripts", "calibrate_engine.py"))
    ce = importlib.util.module_from_spec(spec)
    sys.modules["calibrate_engine"] = ce  # the worker processes find the function by this name
    spec.loader.exec_module(ce)
    from multiprocessing import Pool
    with Pool(max(1, os.cpu_count() or 1)) as pool:
        res = pool.map(ce.one, [(seed0 + k, "random") for k in range(n)], chunksize=2)
    return [dict(f=r["f"], y=r["y"]) for x in res for r in x["rows"]]


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit(rows, names, classes, unknown_p=0.55):
    """The same model as scripts/calibrate_engine.py: standardized features, class weights, temperature, OOD limit."""
    from sklearn.covariance import LedoitWolf
    from sklearn.linear_model import LogisticRegression
    X = np.array([[r["f"][k] for k in names] for r in rows], float)
    y = np.array([classes.index(r["y"]) for r in rows])
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    w = np.bincount(y, minlength=len(classes)).astype(float)
    cw = {k: len(y) / (len(classes) * max(w[k], 1)) for k in range(len(classes))}
    lr = LogisticRegression(C=0.5, max_iter=4000, class_weight=cw).fit(Z, y)
    Ts = np.linspace(0.5, 3.0, 51)
    nll = [-np.mean(np.log(softmax((Z @ lr.coef_.T + lr.intercept_) / T)[np.arange(len(y)), y] + 1e-12)) for T in Ts]
    T = float(Ts[int(np.argmin(nll))])
    lw = LedoitWolf().fit(Z)
    prec = np.linalg.inv(lw.covariance_)
    d2 = np.einsum("ij,jk,ik->i", Z - lw.location_, prec, Z - lw.location_)
    return dict(features=names, classes=classes, mean=mu.tolist(), scale=sd.tolist(), coef=lr.coef_.tolist(), intercept=lr.intercept_.tolist(),
                temperature=T, ood_mean=lw.location_.tolist(), ood_precision=prec.tolist(), ood_threshold=float(np.quantile(d2, 0.995)),
                unknown_p=unknown_p)


def predict(m, rows):
    names, classes = m["features"], m["classes"]
    X = np.array([[r["f"][k] for k in names] for r in rows], float)
    Z = (X - np.array(m["mean"])) / np.array(m["scale"])
    p = softmax((Z @ np.array(m["coef"]).T + np.array(m["intercept"])) / m["temperature"])
    d = Z - np.array(m["ood_mean"])
    d2 = np.einsum("ij,jk,ik->i", d, np.array(m["ood_precision"]), d)
    unk = (p.max(1) < m["unknown_p"]) | (d2 > m["ood_threshold"])
    return ["unknown" if u else classes[k] for k, u in zip(p.argmax(1), unk)]


def held_out(real, practice, names, classes):
    """Retrain without one field, score on that field. Returns accuracy when decided and the unknown fraction."""
    right = decided = n = 0
    for key in sorted({r["field"] for r in real}):
        train = practice + [r for r in real if r["field"] != key]
        test = [r for r in real if r["field"] == key]
        if not test:
            continue
        m = fit(train, names, classes)
        for r, v in zip(test, predict(m, test)):
            n += 1
            if v != "unknown":
                decided += 1
                right += v == r["y"]
    return dict(rows=n, right_when_decided=right / max(decided, 1), unknown_fraction=1 - decided / max(n, 1))


def run_field(T, key, coll, n, fov, trials, per, seed):
    exps = cn.live_exposures(T, coll, n, size=fov, det=0)
    if len(exps) < 4:
        return dict(key=key, name=T["name"], usable=len(exps), skipped="fewer than four usable exposures", report=dict(cn.REPORT, gaia=None))
    cat = cn.gaia_catalog(cn.REPORT.get("gaia", []))
    size = int(round(fov * 3600 / core.PIX)) | 1
    res = inject.trials(exps, cat, core.catalog_at(T, core.SIM_T0), size, trials, per, seed)
    sc = inject.score(res)
    for r in res["rows"]:
        r["field"] = key
    return dict(key=key, name=T["name"], usable=len(exps), releases=sorted({e.rel for e in exps}), detectors=sorted({e.det for e in exps}),
                labels=sorted({e.label for e in exps}), base_candidates=res["base_candidates"], base_verdicts=res["base_verdicts"],
                n_epochs=res["n_epochs"], score=sc, rows=res["rows"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default=DEFAULT)
    ap.add_argument("--fields", default="", help="extra fields as name:ra:dec, comma separated (for example nep:270.0:66.56)")
    ap.add_argument("--coll", default="spherex_dr1+spherex_qr3")
    ap.add_argument("--n", type=int, default=96)
    ap.add_argument("--fov", type=float, default=0.08)
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--per", type=int, default=6)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--retrain", action="store_true")
    ap.add_argument("--practice", type=int, default=120, help="practice fields to mix with the real rows when retraining")
    ap.add_argument("--install", action="store_true", help="copy the retrained engine to data/engine.json")
    ap.add_argument("--out", default=os.path.join(ROOT, "data"))
    a = ap.parse_args(argv)
    t0 = time.time()
    TG = dict(load_targets())
    keys = [k for k in a.targets.split(",") if k]
    for f in [f for f in a.fields.split(",") if f]:
        name, ra, dec = f.split(":")
        TG[name] = dict(name=f"Field {name} (RA {float(ra):.2f}, Dec {float(dec):.2f})", ra=float(ra), dec=float(dec), epoch=2016.0, pmra=0.0, pmdec=0.0, plx=0.0)
        keys.append(name)
    fields = []
    for key in keys:
        try:
            fields.append(run_field(TG[key], key, a.coll, a.n, a.fov, a.trials, a.per, a.seed))
        except Exception as err:
            fields.append(dict(key=key, name=TG[key]["name"], error=f"{type(err).__name__}: {str(err)[:200]}"))
        print(key, {k: v for k, v in fields[-1].items() if k in ("usable", "error", "skipped")}, flush=True)
    real = [r for f in fields for r in f.get("rows", [])]
    ev_found = sum(f["score"]["found"] for f in fields if "score" in f)
    ev_all = sum(f["score"]["planted"] for f in fields if "score" in f)
    out = dict(status="done" if real else "no real rows", collection=a.coll, trials=a.trials, per_trial=a.per,
               fields=[{k: v for k, v in f.items() if k != "rows"} for f in fields], real_rows=len(real),
               completeness_all=ev_found / max(ev_all, 1), planted_all=ev_all,
               note="Known sources planted in real exposures. Completeness and engine scores hold for these fields and these brightnesses.")
    if a.retrain and real:
        names, classes = list(P.FEATURES), list(sky.CLASSES)
        prac = practice_rows(a.practice)
        engine_rows = [r for r in real if r.get("engine")]
        dec = [r for r in engine_rows if r["engine"] != "unknown"]
        out["before"] = dict(rows=len(engine_rows), right_when_decided=sum(r["engine"] == r["y"] for r in dec) / max(len(dec), 1),
                             unknown_fraction=1 - len(dec) / max(len(engine_rows), 1))
        out["after"] = held_out(real, prac, names, classes)
        m = fit(prac + real, names, classes)
        m.update(trained_on=dict(practice_fields=a.practice, practice_rows=len(prac), real_rows=len(real), collection=a.coll),
                 note="Practice rows and rows from sources planted in real SPHEREx exposures.")
        json.dump(m, open(os.path.join(a.out, "engine_real.json"), "w"), indent=1)
        if a.install:
            shutil.copy(os.path.join(a.out, "engine.json"), os.path.join(a.out, "engine_practice.json"))
            shutil.copy(os.path.join(a.out, "engine_real.json"), os.path.join(a.out, "engine.json"))
            out["installed"] = True
    out["seconds"] = round(time.time() - t0)
    json.dump(out, open(os.path.join(a.out, "real_injection.json"), "w"), indent=1, default=str)
    print(json.dumps({k: out[k] for k in ("status", "real_rows", "completeness_all") if k in out}))
    return out


if __name__ == "__main__":
    main()
