"""Write and execute the four notebooks in notebooks/. Run: python scripts/make_notebooks.py"""
import os

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB = os.path.join(ROOT, "notebooks")
os.makedirs(NB, exist_ok=True)

SETUP = """import os, sys, json, math, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.abspath("..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
for f in os.listdir(os.path.join(ROOT, "scripts", "fonts")):
    font_manager.fontManager.addfont(os.path.join(ROOT, "scripts", "fonts", f))
plt.rcParams.update({"font.family": "EB Garamond", "font.size": 12, "figure.facecolor": "#f5f0e6", "axes.facecolor": "#fbf8f2"})
import core, sky, pipeline as P"""


def md(s):
    return nbf.v4.new_markdown_cell(s)


def code(s):
    return nbf.v4.new_code_cell(s)


BOOKS = {
    "01_fair_pairs_and_false_change.ipynb": [
        md("# 1. Fair pairs: why you cannot blink SPHEREx\n\nEach pixel of a SPHEREx exposure sees its own color through a linear variable filter. "
           "This notebook shows how much a steady star seems to change when two exposures see different colors, and how CHRONOS picks fair pairs."),
        code(SETUP),
        md("## A practice field\n\nSix arrays, two colors per array in each visit, four visits half a year apart. Surveys 3 and 4 sit half a channel away."),
        code("""spec = sky.make_spec(3)
E, truth, cat = sky.render(spec)
print(len(E), "exposures;", sorted({e.det for e in E}), "arrays")
for e in E[:4]:
    print(e.id, "array", e.det, "lambda %.4f micron" % e.lam, "width %.4f" % e.bw, "frame", e.frame)"""),
        code("""fig, ax = plt.subplots(figsize=(8, 3.5))
col = {1: "#8f84c2", 2: "#7d9fd0", 3: "#6fb1ad", 4: "#9cb77a", 5: "#d3ad6a", 6: "#cf8a72"}
t0 = min(e.mjd for e in E)
for e in E:
    ax.scatter(e.mjd - t0, e.lam, color=col[e.det], s=18)
ax.set_yscale("log"); ax.set_xlabel("days"); ax.set_ylabel("micron"); ax.set_title("Coverage plane")
plt.show()"""),
        md("## How far apart are the colors?\n\nColor offset in channel widths for the same array and step, visit 1 against visits 2, 3 and 4."),
        code("""a = [e for e in E if e.det == 3 and e.id.endswith("s0")]
for b in a[1:]:
    print(a[0].id, "->", b.id, "offset %.2f channel" % (abs(a[0].lam - b.lam) / b.bw), "fair" if P.color_distance(a[0], b) <= 0.5 else "NOT fair")"""),
        md("## False change from color alone\n\nA steady star with a spectral slope seems to change brightness between two colors. "
           "The false change meter of CHRONOS predicts this change; the fair pair rule avoids it."),
        code("""for slope in (-0.6, 0.0, 0.6, 1.2):
    s = dict(mag=15.0, slope=slope)
    f1 = sky.flux_of(dict(s), a[0].lam, a[0].mjd, 0)
    f3 = sky.flux_of(dict(s), a[2].lam, a[2].mjd, 2)
    print(f"slope {slope:+.1f} mag per micron: apparent change {100 * (f3 / f1 - 1):+.2f} percent with no change in the sky")"""),
        md("## Fair co add pairs of a whole field"),
        code("""core.prepare(E)
ref, n, center = P.ref_wcs(E, spec["center"])
S = P.build(E, ref, n, cat)
pairs = P.fair_coadd_pairs(S)
print(sum(p["fair"] and p["release_same"] for p in pairs), "fair of", len(pairs), "visit pairs on the same array")
for p in pairs[:8]:
    print("visit", p["q1"] + 1, "and", p["q2"] + 1, "array", p["det"], "color %.2f" % p["color"], "fair" if p["fair"] else "", "" if p["release_same"] else "release differs")"""),
    ],
    "02_discovery_by_disagreement.ipynb": [
        md("# 2. Discovery by disagreement\n\nThree detectors read the same practice field: P (catalog), D (difference), A (anomaly ensemble). "
           "The agreement pattern of each candidate is kept and compared with the hidden truth."),
        code(SETUP + "\nimport investigate as I"),
        code("""spec = sky.make_spec(3)
E, truth, cat = sky.render(spec)
out = I.investigate(E, cat, center=spec["center"], truth=truth, spec=spec, meta=dict(mode="sim", key="demo"))
for c in out["candidates"]:
    p = c["post"]
    print(c["id"], c["methods"].ljust(3), "truth:", (c["truth_sub"] or c["truth"]).ljust(8), "verdict:", ("unknown" if p["unknown"] else p["verdict"]).ljust(9), "|", c["dossier"]["status"])"""),
        md("## Why they disagree\n\nEach pattern has a measured meaning and asks for a test."),
        code("""for c in out["candidates"]:
    d = c["dossier"]["disagreement"]
    print(c["id"], d["pattern"], "-", d["headline"])"""),
        md("## The crosstalk case: agreement is not proof"),
        code("""g = next(c for c in out["candidates"] if c["truth_sub"] == "ghost")
for t in g["dossier"]["tests"]:
    print(t["outcome"].ljust(11), t["question"], "|", t["result"])"""),
        md("## The difference microscope\n\nSpots above 5 sigma in each layer of correction for every fair pair."),
        code("""for L in out["field"]["microscope"]:
    print("visits", L["q1"], L["q2"], "array", L["det"], "fair" if L["fair"] else "NOT FAIR", [(x["key"], x["count"]) for x in L["layers"]])"""),
        md("## The report of the moving candidate\n\nEvery sentence carries evidence references."),
        code("""m = next(c for c in out["candidates"] if c["truth"] == "moving")
for s in m["dossier"]["report"]:
    print(s["text"], s["refs"])
print()
for e in m["dossier"]["evidence"]:
    print(e["id"], e["what"], ":", e["value"])"""),
    ],
    "03_validation_and_calibration.ipynb": [
        md("# 3. Validation and calibration\n\nScores of the five hypothesis engine on unseen practice fields, read from data/validation.json, "
           "then a fresh check on new fields that neither training nor testing used."),
        code(SETUP + "\nimport engine\nV = json.load(open(os.path.join(ROOT, 'data', 'validation.json')))"),
        code("""print("test fields", V["test_fields"], "candidates", V["test_candidates"])
print("accuracy when deciding %.3f, unknown %.3f, Brier %.3f, ECE %.4f" % (V["unknown"]["accuracy_when_decided"], V["unknown"]["fraction"], V["brier"], V["ece"]))
for k, a in V["per_class"].items():
    print(k.ljust(10), "precision %.2f recall %.2f n %d" % (a["precision"], a["recall"], a["n"]))"""),
        code("""r = V["reliability"]
fig, ax = plt.subplots(figsize=(4, 4))
ax.plot([0, 1], [0, 1], "--", color="#a7a19a")
ax.scatter([x["confidence"] for x in r], [x["accuracy"] for x in r], s=[10 + x["n"] / 3 for x in r], color="#937aa6")
ax.set_xlabel("stated confidence"); ax.set_ylabel("observed accuracy"); ax.set_title("Reliability")
plt.show()"""),
        code("""for k, a in sorted(V["agreement_by_count"].items()):
    print(k, "methods: real sky change in %.0f percent of %d (%.0f to %.0f)" % (100 * a["sky_fraction"], a["n"], 100 * a["lo"], 100 * a["hi"]))
print("A only:", V["agreement_patterns"].get("A"))"""),
        md("## A fresh check on new fields\n\nSix fields with seeds that no script used before. The engine is frozen."),
        code("""ok = tot = 0
for seed in range(90000, 90006):
    rng = np.random.default_rng(seed)
    spec = sky.make_spec(seed, center=(float(rng.uniform(0, 360)), float(rng.uniform(-60, 60))), events="random")
    E, truth, cat = sky.render(spec)
    core.prepare(E)
    S = P.run(E, cat, center=spec["center"])
    P.match_truth(S, truth)
    for c in S["cands"]:
        p = engine.posterior(c["f"])
        v = "null" if p["unknown"] else p["verdict"]
        tot += 1
        ok += v == c["truth"]
print(f"{ok} of {tot} candidates labelled as planted")"""),
        md("## Negative controls"),
        code("""print(json.dumps(V["controls"], indent=1)[:900])"""),
    ],
    "04_live_archive_walkthrough.ipynb": [
        md("# 4. The live SPHEREx archive path\n\nHow CHRONOS reads real SPHEREx Quick Release files from IRSA. The first cells build one file in the documented "
           "layout and read it with the same code. The last cell asks the real archive; it reports when the archive cannot be reached."),
        code(SETUP + "\nimport io\nfrom astropy.io import fits\nimport connectors as cn"),
        md("## One file in the IRSA layout\n\nExtensions IMAGE, FLAGS (bit names in MP keywords), VARIANCE, ZODI, and the alternate WCS A for detector pixels."),
        code("""spec = sky.make_spec(3)
E, truth, cat = sky.render(spec)
e = E[0]
hd = e.wcs.to_header()
hd["DETECTOR"], hd["OBSID"], hd["VERSION"] = e.det, e.id, "6.5.6"
hd["CRPIX1A"], hd["CRPIX2A"], hd["CRVAL1A"], hd["CRVAL2A"] = 1.0, 1.0, e.dxy[0], e.dxy[1]
fh = fits.Header()
for name, bit in core.FLAG_BITS.items():
    fh["MP_" + name[:5]] = bit
f = fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(e.img.astype("f4"), hd, name="IMAGE"), fits.ImageHDU(e.flags.astype("i4"), fh, name="FLAGS"),
                  fits.ImageHDU(e.var.astype("f4"), name="VARIANCE"), fits.ImageHDU(np.full(e.img.shape, e.zodi, "f4"), name="ZODI")])
f.info()
print("flag names read from the file:", cn.flag_bits(f))"""),
        md("## The search and cutout requests that live mode sends"),
        code("""ra, dec = 269.44850, 4.73942
print(cn.SIA + "?" + "&".join(f"{k}={v}" for k, v in dict(COLLECTION="spherex_qr3", POS=f"CIRCLE {ra} {dec} 0.12", MAXREC=2000).items()))
print("cutout: <access_url>?center=%.5f,%.5f&size=0.08" % (ra, dec))"""),
        md("## Ask the real archive\n\nThis cell needs internet access to irsa.ipac.caltech.edu."),
        code("""try:
    rows = cn.search(ra, dec, 0.05, "spherex_qr3")
    print(len(rows), "SPHEREx QR3 files cover Barnard's Star")
    for r in rows[:5]:
        print(r.get("obs_id"), r.get("energy_bandpassname"), r.get("t_min"))
except Exception as err:
    print("The archive could not be reached from this machine:", type(err).__name__, str(err)[:120])
    print("Run this notebook with internet access, or start the app and press Check the live archive.")"""),
    ],
}


def main():
    for name, cells in BOOKS.items():
        nb = nbf.v4.new_notebook()
        nb["cells"] = cells
        nb["metadata"]["kernelspec"] = dict(name="python3", display_name="Python 3", language="python")
        ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": NB}})
        nbf.write(nb, os.path.join(NB, name))
        print("wrote", name)


if __name__ == "__main__":
    main()
