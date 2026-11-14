"""Build the static observatory in site/ for GitHub Pages: the full page with prepared practice fields.

Run: python scripts/build_static.py   (about three minutes). Then serve site/ with any static web server.
"""
import json
import os
import shutil
import sys
import time
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
warnings.filterwarnings("ignore")
os.chdir(ROOT)

import app  # noqa: E402,F401  (fills the target table)
import core  # noqa: E402
import observatory as O  # noqa: E402
import study  # noqa: E402

SITE = os.path.join(ROOT, "site")
FRONT = os.path.join(ROOT, "frontend")
KEEP = ("story", "media", "figures", "deck.html")
LINKS = ('<a href="media/chronos_demo.mp4">Watch the 30 second demo</a> · <a href="deck.html">Read the 7 slides</a> · '
         '<a href="https://github.com/PRITIDIPADAS/nakshatra-chronus">Source code</a>')


def static_story():
    """Make site/story.html replay the answers that scripts/record_story.py saved in site/story/."""
    s = open(os.path.join(FRONT, "story.html")).read()
    s = s.replace('<script src="/extras.js"></script>', '<script src="extras.js"></script>')
    s = s.replace("<script>", '<script src="story_static.js"></script><script>', 1)
    open(os.path.join(SITE, "story.html"), "w").write(s)


def main():
    t0 = time.time()
    keep = os.path.join(ROOT, ".site_keep")
    if os.path.exists(keep):
        shutil.rmtree(keep)
    os.makedirs(keep)
    for k in KEEP:  # recorded story, media, figures and deck are built by other scripts
        if os.path.exists(os.path.join(SITE, k)):
            shutil.move(os.path.join(SITE, k), os.path.join(keep, k))
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    shutil.copytree(FRONT, SITE)
    for k in os.listdir(keep):
        shutil.move(os.path.join(keep, k), os.path.join(SITE, k))
    shutil.rmtree(keep)
    open(os.path.join(SITE, "mode.js"), "w").write("window.CHRONOS_STATIC = true;\n")
    open(os.path.join(SITE, ".nojekyll"), "w").write("")
    os.makedirs(os.path.join(SITE, "data", "fields"), exist_ok=True)
    for f in ("validation.json", "engine.json"):
        shutil.copy(os.path.join(ROOT, "data", f), os.path.join(SITE, "data", f))
    index, outs = [], []
    keys = ["demo"] + list(O.TARGETS) + ["quiet"]
    for k in keys:
        t = time.time()
        out = json.loads(json.dumps(O.run_field(k, "sim"), default=O.I_json))
        json.dump(out, open(os.path.join(SITE, "data", "fields", f"{k}.json"), "w"), separators=(",", ":"))
        name = out["meta"]["name"]
        outs.append((k, name, out))
        kind = "target" if k in O.TARGETS else "field"
        index.append(dict(key=k, name=name, kind=kind, traits=O.TARGETS.get(k, {}).get("traits", []), ra=out["center"][0], dec=out["center"][1],
                          note=O.FIELDS.get(k, {}).get("note")))
        print(f"{k}: {len(out['candidates'])} candidates, {time.time() - t:.0f} s")
    json.dump(index, open(os.path.join(SITE, "data", "fields", "index.json"), "w"), indent=1)
    st = study.make(outs)
    for d in (os.path.join(ROOT, "data"), os.path.join(SITE, "data")):
        json.dump(st, open(os.path.join(d, "study.json"), "w"), separators=(",", ":"))
    for f in ("sky_tiles.json", "real_injection.json"):  # made by scripts/make_sky_tiles.py and scripts/inject_real.py
        if os.path.exists(os.path.join(ROOT, "data", f)):
            shutil.copy(os.path.join(ROOT, "data", f), os.path.join(SITE, "data", f))
    s = open(os.path.join(SITE, "index.html")).read()
    link = '<a class="storylink" href="story.html" id="storyLink">The five minute story of one star, in English and Bangla →</a>'
    if os.path.exists(os.path.join(SITE, "story", "manifest.json")):
        s = s.replace(link, '<span class="storylink">' + link.replace(' class="storylink"', "") + "<br>" + LINKS + "</span>")
        static_story()
    else:
        s = s.replace(link, '<span class="storylink">' + LINKS + "<br>Run python scripts/record_story.py to add the story to this page.</span>")
        for f in ("story.html", "extras.js", "story_static.js"):
            os.remove(os.path.join(SITE, f))
    open(os.path.join(SITE, "index.html"), "w").write(s)
    print(f"site built in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

# CHRONOS 4D laboratories: python scripts/build_lab.py (run after this script)
