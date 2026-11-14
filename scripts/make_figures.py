"""Figures for the documents and the deck, from a fresh run of the practice fields and from data/validation.json.

Run: python scripts/make_figures.py   Output: docs/figures/*.png
"""
import base64
import json
import math
import os
import sys
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
warnings.filterwarnings("ignore")
os.chdir(ROOT)
OUT = os.path.join(ROOT, "docs", "figures")
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(os.path.join(ROOT, "scripts", "fonts")):
    font_manager.fontManager.addfont(os.path.join(ROOT, "scripts", "fonts", f))
plt.rcParams.update({"font.family": "EB Garamond", "font.size": 13, "axes.edgecolor": "#cfc5b3", "axes.labelcolor": "#2e2a33", "xtick.color": "#5d5763",
                     "ytick.color": "#5d5763", "axes.facecolor": "#fbf8f2", "figure.facecolor": "#f5f0e6", "savefig.facecolor": "#f5f0e6",
                     "axes.grid": True, "grid.color": "#e6dfd1", "grid.linewidth": 0.8, "axes.titleweight": 600, "axes.titlesize": 15})
H = dict(moving="#7489ad", variable="#c4a061", transient="#937aa6", artefact="#b56f5e", null="#a7a19a")
BAND = {1: "#8f84c2", 2: "#7d9fd0", 3: "#6fb1ad", 4: "#9cb77a", 5: "#d3ad6a", 6: "#cf8a72"}
PLATE = LinearSegmentedColormap.from_list("plate", ["#f5f0e6", "#2e2a33"])
DIV = LinearSegmentedColormap.from_list("div", ["#546a96", "#f5f0e6", "#a8524a"])


def dec(img):
    a = np.frombuffer(base64.b64decode(img["b64"]), np.uint8).reshape(img["h"], img["w"]).astype(float)
    v = np.where(a == 0, np.nan, img["lo"] + (a - 1) / 254 * (img["hi"] - img["lo"]))
    return np.flipud(v)


def noise(img):
    v = dec(img)
    return np.arcsinh(np.clip(v, 0, None) / 1.5) / np.arcsinh(20)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(name)


def field(key):
    p = os.path.join(ROOT, "site", "data", "fields", f"{key}.json")
    if os.path.exists(p):
        return json.load(open(p))
    import app  # noqa: F401
    import observatory as O
    return json.loads(json.dumps(O.run_field(key, "sim"), default=O.I_json))


def fair_plane(D):
    ex = D["field"]["exposures"]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    g = {}
    for e in ex:
        g.setdefault((e["visit"], e["det"]), []).append(e)
    for p in D["field"]["pairs"]:
        a, b = g.get((p["q1"] + 1, p["det"])), g.get((p["q2"] + 1, p["det"]))
        if a and b and p["fair"] and p["release_same"]:
            ax.plot([np.mean([e["day"] for e in a]), np.mean([e["day"] for e in b])], [np.exp(np.mean([math.log(e["lam"]) for e in a])),
                    np.exp(np.mean([math.log(e["lam"]) for e in b]))], color="#7d9a8a", lw=1.2, alpha=0.8, zorder=1)
    for e in ex:
        ax.scatter(e["day"], e["lam"], s=26, color=BAND[e["det"]], edgecolor="#b56f5e" if e["rel"] == "QR2" else "none", lw=1.5, zorder=2)
    ax.set_yscale("log")
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_yticks([0.75, 1, 1.5, 2, 3, 5])
    ax.set_yticklabels(["0.75", "1", "1.5", "2", "3", "5"])
    ax.set_xlabel("days since the first exposure")
    ax.set_ylabel("wavelength (micron)")
    ax.set_title("Coverage plane: each dot one exposure, lines join fair pairs")
    save(fig, "fair_plane.png")


def microscope(D):
    L = next(x for x in D["field"]["microscope"] if x["fair"] and x["det"] == 2) if any(x["fair"] and x["det"] == 2 for x in D["field"]["microscope"]) else D["field"]["microscope"][0]
    ex = D["field"]["exposures"]
    ia = next(i for i, e in enumerate(ex) if e["id"] == L["a"])
    ib = next(i for i, e in enumerate(ex) if e["id"] == L["b"])
    lay = {x["key"]: x for x in L["layers"]}
    panels = [("Exposure A, visit %d" % L["q1"], noise(D["field"]["maps"]["cube"][ia]), PLATE, (0, 1)),
              ("Exposure B, visit %d" % L["q2"], noise(D["field"]["maps"]["cube"][ib]), PLATE, (0, 1))]
    for k, t in (("raw", "Raw difference"), ("anchor", "Aligned on stars"), ("coadd", "Fair co add, honest noise")):
        if k in lay:
            panels.append((f"{t}: {lay[k]['count']} spot{'' if lay[k]['count'] == 1 else 's'}", dec(lay[k]["img"]), DIV, (-10, 10)))
    fig, axs = plt.subplots(1, len(panels), figsize=(3.0 * len(panels), 3.3))
    for ax, (t, a, cm, (lo, hi)) in zip(axs, panels):
        ax.imshow(a, cmap=cm, vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(t, fontsize=13)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
    for c in D["candidates"]:
        for ax in axs[2:]:
            ax.add_patch(plt.Circle((c["x"], D["n"] - 1 - c["y"]), 2.6, fill=False, color="#2e2a33", lw=0.8))
    fig.suptitle(f"The difference microscope: array {L['det']}, the same pair with more corrections", y=1.03, fontsize=15)
    save(fig, "microscope.png")


def disagreement(V):
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw=dict(width_ratios=[1, 1.6]))
    bn = V["agreement_by_count"]
    ks = ["1", "2", "3"]
    f = [bn[k]["sky_fraction"] for k in ks]
    lo = [bn[k]["sky_fraction"] - bn[k]["lo"] for k in ks]
    hi = [bn[k]["hi"] - bn[k]["sky_fraction"] for k in ks]
    axs[0].bar(["one\nmethod", "two\nmethods", "three\nmethods"], f, yerr=[lo, hi], color=["#c9bcd3", "#ad97c0", "#937aa6"], capsize=4)
    for i, k in enumerate(ks):
        axs[0].text(i, f[i] + hi[i] + 0.03, f"{100 * f[i]:.0f}%\nof {bn[k]['n']}", ha="center", fontsize=12)
    axs[0].set_ylim(0, 1.15)
    axs[0].set_ylabel("share that are real sky changes")
    axs[0].set_title("More agreement, higher odds")
    ap = sorted(((k, a) for k, a in V["agreement_patterns"].items() if a["n"] >= 8), key=lambda t: t[1]["sky_fraction"])
    y = np.arange(len(ap))
    axs[1].barh(y, [a["sky_fraction"] for _, a in ap], xerr=[[a["sky_fraction"] - a["lo"] for _, a in ap], [a["hi"] - a["sky_fraction"] for _, a in ap]],
                color=["#b56f5e" if k == "A" else "#937aa6" for k, _ in ap], capsize=3)
    axs[1].set_yticks(y)
    axs[1].set_yticklabels([f"{k}  ({a['n']})" for k, a in ap])
    axs[1].set_xlim(0, 1.05)
    axs[1].set_xlabel("share that are real sky changes")
    axs[1].set_title("Which methods disagree matters: A alone is the camera")
    fig.suptitle("Discovery by disagreement, on held out practice fields (95 percent intervals)", y=1.04, fontsize=15)
    save(fig, "disagreement.png")


def calibration(V):
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    r = V["reliability"]
    axs[0].plot([0, 1], [0, 1], ls="--", color="#a7a19a")
    axs[0].scatter([x["confidence"] for x in r], [x["accuracy"] for x in r], s=[20 + 2 * math.sqrt(x["n"]) * 6 for x in r], color="#937aa6", edgecolor="#2e2a33")
    axs[0].set_xlabel("stated confidence")
    axs[0].set_ylabel("observed accuracy")
    axs[0].set_title(f"Honest probabilities: ECE {V['ece']:.3f}, Brier {V['brier']:.3f}")
    names = ["H1", "H2", "H3", "H4", "H5"]
    C = np.array(V["confusion"])
    axs[1].imshow(C / C.sum(1, keepdims=True), cmap=LinearSegmentedColormap.from_list("s", ["#f5f0e6", "#d6c4e2", "#5c4678"]), vmin=0, vmax=1)
    for i in range(5):
        for j in range(5):
            axs[1].text(j, i, C[i, j], ha="center", va="center", color="#fbf8f2" if C[i, j] / max(C[i].sum(), 1) > 0.5 else "#2e2a33")
    axs[1].set_xticks(range(5))
    axs[1].set_xticklabels(names)
    axs[1].set_yticks(range(5))
    axs[1].set_yticklabels(names)
    axs[1].set_xlabel("engine answer")
    axs[1].set_ylabel("planted truth")
    axs[1].grid(False)
    axs[1].set_title(f"{V['test_candidates']} candidates, {V['test_fields']} unseen fields")
    save(fig, "calibration.png")


def completeness(V):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for k in ("moving", "variable", "transient"):
        d = V["completeness"].get(k, {})
        ms = sorted(int(m) for m in d if m.isdigit())
        ms = [m for m in ms if d[str(m)]["n"] >= 3]
        f = [d[str(m)]["fraction"] for m in ms]
        ax.errorbar(ms, f, yerr=[[d[str(m)]["fraction"] - d[str(m)]["lo"] for m in ms], [d[str(m)]["hi"] - d[str(m)]["fraction"] for m in ms]], color=H[k],
                    marker="o", capsize=3, label={"moving": "H1 moving", "variable": "H2 variable", "transient": "H3 transient"}[k])
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("AB magnitude at 4.5 micron (fainter to the right)")
    ax.set_ylabel("planted changes found")
    ax.legend(frameon=False)
    ax.set_title("Completeness on unseen practice fields")
    save(fig, "completeness.png")


def mover(D):
    c = next(c for c in D["candidates"] if c["post"]["verdict"] == "moving" and c["dossier"]["cutouts"].get("motion_stack"))
    cu = c["dossier"]["cutouts"]
    m = c["dossier"]["motion"]
    fig, axs = plt.subplots(1, 3, figsize=(10, 3.4))
    for ax, k, t in ((axs[0], "plain_stack", f"Plain stack, peak {cu['peak_plain']}"), (axs[1], "motion_stack", f"Following the motion, peak {cu['peak_motion']}")):
        ax.imshow(dec(cu[k]), cmap=PLATE, interpolation="nearest")
        ax.set_title(t, fontsize=13)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
    t = m["track"]
    mx, my = np.mean([p["x"] for p in t]), np.mean([p["y"] for p in t])
    for p in t:
        axs[2].add_patch(matplotlib.patches.Ellipse((p["x"] - mx, p["y"] - my), 2 * p["ex"], 2 * p["ey"], fill=False, color="#7489ad"))
        axs[2].plot(p["x"] - mx, p["y"] - my, "o", color="#7489ad")
        axs[2].text(p["x"] - mx + 0.01, p["y"] - my + 0.01, f"visit {p['visit']}", fontsize=11)
    s = max(0.2, max(max(abs(p["x"] - mx) + 2 * p["ex"], abs(p["y"] - my) + 2 * p["ey"]) for p in t)) * 1.2
    axs[2].set_xlim(-s, s)
    axs[2].set_ylim(-s, s)
    axs[2].set_aspect("equal")
    axs[2].set_xlabel("pixel offset (east left)")
    axs[2].set_title(f"{m['pm_arcsec_yr']:.2f} arcsec per year, {m['sig']:.0f} sigma", fontsize=13)
    fig.suptitle(f"Invisible motion: {c['id']} moves {m['pm_px_yr'] * 1.5:.2f} pixel in 548 days", y=1.04, fontsize=15)
    save(fig, "invisible_motion.png")


def ghost(D):
    c = next(c for c in D["candidates"] if c.get("truth_sub") == "ghost")
    v = c["dossier"]["cutouts"]["visits"]
    fig, axs = plt.subplots(1, len(v) + 1, figsize=(2.4 * (len(v) + 1) + 2.4, 2.9), gridspec_kw=dict(width_ratios=[1] * len(v) + [2.2]))
    for ax, x in zip(axs, v):
        ax.imshow(dec(x["img"]), cmap=PLATE, interpolation="nearest")
        ax.set_title(f"visit {x['visit']}", fontsize=13)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
    tests = [t for t in c["dossier"]["tests"] if t["outcome"] == "supports"][:3]
    axs[-1].axis("off")
    txt = f"{c['id']}: flagged by {c['methods']}\nVerdict: {c['dossier']['status']}\n\n" + "\n".join("• " + t["result"] for t in tests)
    axs[-1].text(0, 0.95, txt, va="top", fontsize=12, wrap=True)
    fig.suptitle(f"All three methods agreed, and they were wrong together: a crosstalk copy of a bright star ({c['dossier']['cutouts']['source']})", y=1.06, fontsize=15)
    save(fig, "crosstalk_case.png")


def planetx():
    d = np.logspace(2, 3.3, 200)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for mass, al, col in ((6, 0.4, "#7489ad"), (10, 0.75, "#937aa6"), (3, 0.1, "#a7a19a")):
        R = mass ** 0.55
        Hm = 5 * np.log10(1329 / (2 * R * 6371 * math.sqrt(al)))
        ax.plot(d, Hm + 10 * np.log10(d), color=col, label=f"{mass} Earth masses, albedo {al}")
    ax.axhline(19, color="#7d9a8a", ls="--", lw=1.2)
    ax.text(110, 18.7, "assumed one visit limit, 19 AB", color="#7d9a8a")
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel("distance from the Sun (AU)")
    ax.set_ylabel("AB magnitude (brighter up)")
    ax.legend(frameon=False, fontsize=11)
    ax.set_title("Planet X lab: reflected sunlight falls with the fourth power of distance")
    save(fig, "planetx.png")


if __name__ == "__main__":
    V = json.load(open(os.path.join(ROOT, "data", "validation.json")))
    D = field("demo")
    fair_plane(D)
    microscope(D)
    disagreement(V)
    calibration(V)
    completeness(V)
    mover(D)
    ghost(D)
    planetx()
