/* Replays the guided story on the hosted page. Every answer was recorded from the full app by scripts/record_story.py. */
(function () {
  const M = {}; let cur = "*";
  const ready = fetch("story/manifest.json").then((r) => r.json()).then((j) => Object.assign(M, j)).catch(() => {});
  const of = window.fetch.bind(window);
  const keyOf = (method, u, body) => {
    const url = new URL(u, location.href), pq = url.pathname.slice(url.pathname.indexOf("/api/")) + url.search;
    if (pq.startsWith("/api/load")) cur = url.searchParams.get("t") || cur;
    if (pq.startsWith("/api/targets")) return "*|GET|" + pq;
    if (method === "POST" && pq.startsWith("/api/explain")) { let l = "en"; try { l = JSON.parse(body).lang || "en"; } catch (e) { } return cur + "|POST|/api/explain|" + l; }
    return cur + "|" + method + "|" + pq;
  };
  const miss = "This step needs the full app (python run.py). The hosted page replays the guided story of each star: press Play the full story.";
  window.fetch = async (u, o = {}) => {
    const s = String(u);
    if (!s.includes("/api/")) return of(u, o);
    await ready;
    const f = M[keyOf((o.method || "GET").toUpperCase(), s, o.body)];
    if (!f) return new Response(JSON.stringify({ detail: miss }), { status: 404, headers: { "Content-Type": "application/json" } });
    return of("story/" + f);
  };
  const d = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");
  Object.defineProperty(HTMLImageElement.prototype, "src", {
    get() { return d.get.call(this); },
    set(v) {
      const s = String(v);
      if (!s.includes("/api/")) return d.set.call(this, v);
      const f = M[keyOf("GET", s)];
      d.set.call(this, f ? "story/" + f : "data:image/gif;base64,R0lGODlhAQABAAAAACw=");
    },
  });
  document.addEventListener("DOMContentLoaded", () => {
    const m = document.getElementById("mode");
    if (m) [...m.options].forEach((o) => { if (o.value !== "sim") o.remove(); });
  });
})();
