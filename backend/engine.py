"""Five hypothesis engine. Reads the frozen model in data/engine.json.

H1 moving, H2 variable, H3 transient, H4 instrumental artefact, H5 no established change or not enough evidence.
The model gives P(H | D) with equal priors. The engine says unknown (H5) when the top probability is low, when the
fingerprint lies outside everything the model saw in training, or when the source was measured in fewer than two visits.
"""
import json
import math
import os

import numpy as np

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "engine.json")
NAMES = dict(moving="H1 Moving object", variable="H2 Variable source", transient="H3 Transient", artefact="H4 Instrumental artefact",
             null="H5 No established change")
_M = {}


def model():
    if "m" not in _M:
        if not os.path.exists(PATH):
            return None
        m = json.load(open(PATH))
        for k in ("mean", "scale", "coef", "intercept", "ood_mean", "ood_precision"):
            m[k] = np.array(m[k])
        _M["m"] = m
    return _M["m"]


def posterior(f, prior=None):
    m = model()
    if m is None:
        return dict(ready=False, why="The engine file is missing. Run scripts/calibrate_engine.py.")
    x = np.array([f[k] for k in m["features"]], float)
    z = (x - m["mean"]) / m["scale"]
    logit = (m["coef"] @ z + m["intercept"]) / m["temperature"]
    if prior:
        logit = logit + np.log(np.array([max(prior.get(c, 1.0), 1e-9) for c in m["classes"]]))
    p = np.exp(logit - logit.max())
    p /= p.sum()
    d = z - m["ood_mean"]
    d2 = float(d @ m["ood_precision"] @ d)
    contrib = {c: sorted(((k, float(m["coef"][i][j] * z[j])) for j, k in enumerate(m["features"])), key=lambda t: -abs(t[1]))[:4]
               for i, c in enumerate(m["classes"])}
    probs = {c: float(p[i]) for i, c in enumerate(m["classes"])}
    top = max(probs, key=probs.get)
    why = []
    if probs[top] < m["unknown_p"]:
        why.append(f"The top explanation has only {100 * probs[top]:.0f} percent. The limit is {100 * m['unknown_p']:.0f} percent.")
    if d2 > m["ood_threshold"]:
        why.append("This fingerprint is unlike every case the engine was trained on.")
    if f.get("n_on", 0) + f.get("n_off", 0) < 2:
        why.append("The place was measured in fewer than two visits.")
    verdict = "null" if why else top
    ent = -sum(v * math.log(v) for v in probs.values() if v > 0) / math.log(len(probs))
    return dict(ready=True, probs=probs, top=top, verdict=verdict, unknown=bool(why), why_unknown=why, ood_distance2=d2,
                ood_limit=m["ood_threshold"], entropy=ent, drivers={c: [dict(feature=k, push=v) for k, v in contrib[c]] for c in contrib},
                names=NAMES)
