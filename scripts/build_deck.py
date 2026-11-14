"""Build the 7 slide deck as one HTML page and a PDF from docs/deck/slides. Run: python scripts/build_deck.py"""
import asyncio
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECK = os.path.join(ROOT, "docs", "deck")
ORDER = ["cover", "problem", "idea", "investigate", "evidence", "impact", "next"]
FILES = dict(micro="microscope.png", dis="disagreement.png", dossier="app_dossier.png", cal="calibration.png", px="planetx.png", arch="architecture.png",
             sky="app_sky.png", ghost="crosstalk_case.png", inv="invisible_motion.png", plane="fair_plane.png", comp="completeness.png", qr="qr_site.png", tiles="sky_tiles_pair.png")


def page(prefix_fig, prefix_font):
    blobs = json.load(open(os.path.join(DECK, "blobs.json")))
    body = []
    for k in ORDER:
        s = open(os.path.join(DECK, "slides", f"{k}.html")).read()
        for name, url in blobs.items():
            s = s.replace(url, prefix_fig + FILES[name])
        body.append(s)
    faces = "".join(f'@font-face{{font-family:"EB Garamond";src:url({prefix_font}eb-garamond-latin-{w}-{st}.woff2) format("woff2");font-weight:{w};font-style:{st}}}'
                    for w in (400, 500, 600, 700) for st in ("normal", "italic"))
    css = ("@page{size:1920px 1080px;margin:0}html,body{margin:0;padding:0;background:#2e2a33}"
           "section{width:1920px;height:1080px;position:relative;overflow:hidden;box-sizing:border-box;page-break-after:always;break-after:page}"
           "section *{box-sizing:border-box}x-shape{display:inline-block;clip-path:polygon(0 20%,60% 20%,60% 0,100% 50%,60% 100%,60% 80%,0 80%)}h1,h2,h3,p,ul,ol,li{margin:0}ul{padding-left:36px}aside{display:none}"
           "@media screen{section{margin:0 auto 24px;transform-origin:top center}}")
    return f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Nakshatra CHRONOS deck</title><style>{faces}{css}</style></head><body>{"".join(body)}</body></html>'


async def pdf(html_path, out):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1920, "height": 1080})
        await pg.goto("file://" + html_path)
        await pg.wait_for_timeout(1500)
        await pg.pdf(path=out, width="1920px", height="1080px", print_background=True)
        for i in range(len(ORDER)):
            el = (await pg.query_selector_all("section"))[i]
            await el.screenshot(path=os.path.join(DECK, f"slide_{i + 1}.png"))  # preview, removed after the build
        await b.close()


if __name__ == "__main__":
    h = os.path.join(DECK, "deck.html")
    open(h, "w").write(page("../figures/", "../../frontend/fonts/"))
    open(os.path.join(ROOT, "site", "deck.html"), "w").write(page("figures/", "fonts/"))
    os.makedirs(os.path.join(ROOT, "site", "figures"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "site", "media"), exist_ok=True)
    import shutil
    for f in set(FILES.values()):
        shutil.copy(os.path.join(ROOT, "docs", "figures", f), os.path.join(ROOT, "site", "figures", f))
    out = os.path.join(DECK, "CHRONOS_deck.pdf")
    asyncio.run(pdf(h, out))
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(out))
    w.metadata = None
    w.add_metadata({"/Title": "Nakshatra CHRONOS deck", "/CreationDate": "D:20261115160000Z", "/ModDate": "D:20261115160000Z"})
    w.write(out)
    shutil.copy(out, os.path.join(ROOT, "site", "media", "CHRONOS_deck.pdf"))
    for i in range(len(ORDER)):
        os.remove(os.path.join(DECK, f"slide_{i + 1}.png"))
    print("deck built")
