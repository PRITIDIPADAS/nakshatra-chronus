"""Record the guided story of every star from the full app, so that the hosted page can replay it without a server.

Run after scripts/build_static.py: python scripts/record_story.py
It starts the app, plays the guided story of each star in English and in Bangla, opens the Lab tools that work offline,
and saves every answer of the server under site/story/. site/story.html replays them with frontend/story_static.js.
"""
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(SITE, "story")
PORT = 8766
TARGETS = ["barnard", "epsindib", "wise0855", "rwaur", "rdra"]


def key_of(target, method, url, body=None):
    u = urlparse(url)
    pq = u.path[u.path.index("/api/"):] + (("?" + u.query) if u.query else "")
    if pq.startswith("/api/targets"):
        return "*|GET|" + pq
    if method == "POST" and pq.startswith("/api/explain"):
        lang = "en"
        try:
            lang = json.loads(body or "{}").get("lang", "en")
        except Exception:
            pass
        return f"{target}|POST|/api/explain|{lang}"
    return f"{target}|{method}|{pq}"


async def record():
    from playwright.async_api import async_playwright
    manifest, state, keys = {}, {"t": "*"}, {}
    os.makedirs(os.path.join(OUT, "d"), exist_ok=True)

    async def on_response(resp):
        req = resp.request
        if "/api/" not in req.url:
            return
        try:
            body = await resp.body()
        except Exception:
            return
        if resp.status != 200:
            return
        k = keys.get(req) or key_of(state["t"], req.method, req.url, req.post_data)
        ext = "png" if "image/png" in (resp.headers.get("content-type") or "") else "json"
        name = "d/" + hashlib.sha1(k.encode()).hexdigest()[:20] + "." + ext
        open(os.path.join(OUT, name), "wb").write(body)
        manifest[k] = name

    def on_request(req):
        if "/api/" not in req.url:
            return
        q = parse_qs(urlparse(req.url).query)
        if "/api/load" in req.url and q.get("t"):
            state["t"] = q["t"][0]
        keys[req] = key_of(state["t"], req.method, req.url, req.post_data)

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("request", on_request)
        pg.on("response", lambda r: asyncio.ensure_future(on_response(r)))
        for t in TARGETS:
            await pg.goto(f"http://127.0.0.1:{PORT}/story.html?t={t}")
            await pg.wait_for_function("typeof ex !== 'undefined' && ex.length > 0", timeout=180000)
            await pg.evaluate("window.__done = false; const g = window.go; window.go = (id) => { g(id); if (id === 's5') window.__done = true; }; true")
            await pg.click("#tour")
            await pg.wait_for_function("window.__done === true", timeout=300000)
            await pg.wait_for_timeout(3000)
            for lang in ("en", "bn"):
                await pg.select_option("#lang", lang)
                await pg.evaluate("verdict()")
                await pg.wait_for_timeout(1500)
            await pg.select_option("#lang", "en")
            for k in ("lapse", "px", "ps", "fz", "tm"):
                try:
                    await pg.evaluate(f"document.getElementById('lab_{k}').click()")
                    await pg.wait_for_timeout(6000 if k in ("ps", "lapse") else 1500)
                except Exception as err:
                    print(t, k, err)
            print(t, len(manifest))
        await pg.wait_for_timeout(2000)
        await b.close()
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=0)
    return manifest


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "run.py")], env=dict(os.environ, PORT=str(PORT)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(6)
        m = asyncio.run(record())
    finally:
        srv.terminate()
    import build_static
    build_static.static_story()
    for f in ("story_static.js", "extras.js"):
        shutil.copy(os.path.join(ROOT, "frontend", f), os.path.join(SITE, f))
    print(f"recorded {len(m)} answers")


if __name__ == "__main__":
    main()
