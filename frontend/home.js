"use strict";

const H = 6.62607015e-34, C = 2.99792458e8, K = 1.380649e-23;
const BANDS = [[0.75, 1.09, 41], [1.10, 1.62, 41], [1.63, 2.41, 41], [2.42, 3.82, 35], [3.83, 4.41, 110], [4.42, 5.00, 130]];
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const planck = (T, um) => {
  const nu = C / (um * 1e-6);
  return nu ** 3 / Math.expm1(H * nu / (K * T));
};
const ICE = [[3.05, 0.15, 0.5], [4.27, 0.02, 0.6], [4.67, 0.015, 0.5]];
const iceT = um => ICE.reduce((t, [c, w, d]) => t * (1 - d * Math.exp(-0.5 * ((um - c) / w) ** 2)), 1);
const spectrum = (T, um, ice) => planck(T, um) * (ice ? iceT(um) : 1);

// colour of a wavelength on the page's spectral scale
const STOPS = [[0.75, [91, 60, 196]], [1.1, [47, 143, 216]], [1.6, [45, 179, 122]], [2.4, [226, 184, 48]], [3.8, [226, 96, 42]], [5.0, [163, 22, 46]]];
function lamColor(um) {
  for (let i = 1; i < STOPS.length; i++) {
    if (um <= STOPS[i][0]) {
      const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i];
      const f = Math.max(0, (Math.log(um) - Math.log(a)) / (Math.log(b) - Math.log(a)));
      return ca.map((v, j) => Math.round(v + (cb[j] - v) * f));
    }
  }
  return STOPS[STOPS.length - 1][1];
}

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
function gauss(r) {
  return Math.sqrt(-2 * Math.log(r() + 1e-12)) * Math.cos(2 * Math.PI * r());
}

/* ---------- the blink in the first screen ---------- */
const blink = (() => {
  const N = 80, SIG = 1.05, N0 = 0.00025, G = 2e-6, SHIFT = 14, [LMIN, LMAX] = BANDS[1];
  const lamAt = x => LMIN * (LMAX / LMIN) ** (Math.min(Math.max(x, 0), N) / N);
  const r = rng(11);
  const stars = [];
  for (let i = 0; i < 46; i++) {
    stars.push({ x: 4 + r() * (N - 8), y: 4 + r() * (N - 8), f: 0.03 * Math.exp(r() * 3.4), T: 2600 + r() ** 1.6 * 11000 });
  }
  const mover = { x: 22, y: 30, f: 0.3, T: 5200, dx: 3.4, dy: 1.8 };
  const varst = stars.reduce((a, s) => (s.f > 0.15 && s.f < 0.6 && s.x > 45 && !a ? s : a), null) || stars[0];
  const render = (mode, visit, seed) => {
    const img = new Float32Array(N * N), nr = rng(seed);
    const add = (x0, y0, f) => {
      for (let y = Math.max(0, Math.floor(y0 - 4)); y < Math.min(N, y0 + 5); y++)
        for (let x = Math.max(0, Math.floor(x0 - 4)); x < Math.min(N, x0 + 5); x++)
          img[y * N + x] += f / (2 * Math.PI * SIG * SIG) * Math.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * SIG * SIG));
    };
    for (const s of stars) {
      let f = s.f;
      if (visit === 2) {
        const l1 = lamAt(s.x), l2 = mode === "naive" ? lamAt(s.x + SHIFT) : l1;
        f *= planck(s.T, l2) / planck(s.T, l1);
        if (s === varst) f *= 1.6;
      }
      add(s.x, s.y, f);
    }
    const l1 = lamAt(mover.x);
    const m2 = mode === "naive" ? planck(mover.T, lamAt(mover.x + mover.dx + SHIFT)) / planck(mover.T, l1) : 1;
    if (visit === 1) add(mover.x, mover.y, mover.f);
    else add(mover.x + mover.dx, mover.y + mover.dy, mover.f * m2);
    for (let i = 0; i < img.length; i++) img[i] += Math.sqrt(N0 * N0 + G * Math.max(img[i], 0)) * gauss(nr);
    return img;
  };
  const cache = {};
  const frames = mode => cache[mode] || (cache[mode] = (() => {
    const a = render(mode, 1, 3), b = render(mode, 2, 7);
    const z = a.map((v, i) => (b[i] - v) / Math.sqrt(2 * (N0 * N0 + G * Math.max(v, 0))));
    // spots: local maxima of |Z| above 5, merged within 5 pixels
    const peaks = [];
    for (let y = 1; y < N - 1; y++) for (let x = 1; x < N - 1; x++) {
      const v = Math.abs(z[y * N + x]);
      if (v < 5) continue;
      let top = true;
      for (let dy = -1; dy <= 1 && top; dy++) for (let dx = -1; dx <= 1; dx++) if (Math.abs(z[(y + dy) * N + x + dx]) > v) { top = false; break; }
      if (top) peaks.push([x, y]);
    }
    const spots = [];
    for (const p of peaks) if (!spots.some(q => Math.hypot(q[0] - p[0], q[1] - p[1]) < 5)) spots.push(p);
    return { a, b, z, spots };
  })());

  const cA = $("#blinkA"), cD = $("#blinkD");
  if (!cA) return null;
  const off = document.createElement("canvas");
  off.width = off.height = N;
  const octx = off.getContext("2d");
  const draw = (canvas, fn) => {
    const im = octx.createImageData(N, N);
    for (let i = 0; i < N * N; i++) {
      const [r2, g, b] = fn(i);
      im.data.set([r2, g, b, 255], i * 4);
    }
    octx.putImageData(im, 0, 0);
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
    return ctx;
  };
  const plate = arr => i => {
    const v = Math.min(1, Math.asinh(Math.max(arr[i], 0) / 0.0015) / 5.2);
    return [238 - 220 * v, 241 - 214 * v, 240 - 197 * v];
  };
  const diverge = z => i => {
    const v = Math.max(-1, Math.min(1, z[i] / 9));
    return v > 0 ? [238 - 46 * v, 241 - 193 * v, 240 - 134 * v] : [238 + 195 * v, 241 + 148 * v, 240 + 84 * v];
  };
  let mode = "naive", visit = 1, timer = null, paused = reduced;
  const paint = () => {
    const F = frames(mode);
    draw(cA, plate(visit === 1 ? F.a : F.b));
    $("#blinkTag").textContent = visit === 1 ? "visit 1" : "visit 2";
    const ctx = draw(cD, diverge(F.z));
    ctx.strokeStyle = "#0f1b2d";
    ctx.lineWidth = 1.5;
    const s = cD.width / N;
    for (const [x, y] of F.spots) { ctx.beginPath(); ctx.arc((x + 0.5) * s, (y + 0.5) * s, 4.2 * s, 0, 2 * Math.PI); ctx.stroke(); }
    $("#blinkCount").textContent = F.spots.length;
    $("#blinkWords").textContent = F.spots.length === 1 ? "spot looks changed." : "spots look changed.";
    $("#blinkTruth").textContent = mode === "naive"
      ? "Each star landed on a different colour of the filter: hot stars look fainter, cool stars brighter. Only two things really changed."
      : "Same colour on both visits. What is left is real: one asteroid moved (the blue and pink pair) and one star brightened.";
  };
  const tick = () => { visit = visit === 1 ? 2 : 1; paint(); };
  const start = () => { clearInterval(timer); if (!paused) timer = setInterval(tick, 850); };
  $$(".seg button").forEach(b => b.addEventListener("click", () => {
    mode = b.dataset.mode;
    $$(".seg button").forEach(o => o.setAttribute("aria-checked", String(o === b)));
    paint();
  }));
  const pb = $("#blinkPause");
  const syncPause = () => { pb.textContent = paused ? "Play blink" : "Pause blink"; pb.setAttribute("aria-pressed", String(paused)); };
  pb.addEventListener("click", () => { paused = !paused; syncPause(); start(); if (paused) { visit = 2; paint(); } });
  syncPause();
  paint();
  start();
  let auto = setTimeout(() => {   // one orchestrated moment: after a few blinks, show the fair pair
    if (!paused && mode === "naive") $('.seg button[data-mode="fair"]').click();
  }, 7000);
  $$(".seg button").forEach(b => b.addEventListener("click", () => clearTimeout(auto), { once: true }));
  return { frames };
})();

/* ---------- the filter laboratory ---------- */
(() => {
  const strip = $("#labStrip"), spec = $("#labSpec");
  if (!strip) return;
  const st = { band: 1, T: 5800, ice: false, x1: 0.32, x2: 0.52 };
  const lamOf = x => { const [a, b] = BANDS[st.band]; return a * (b / a) ** x; };
  const measure = lam => {
    const R = BANDS[st.band][2], w = lam / R;
    let s = 0;
    for (let i = 0; i < 41; i++) s += spectrum(st.T, lam - w / 2 + (w * i) / 40, st.ice);
    return s / 41;
  };
  const dpr = () => Math.min(2, window.devicePixelRatio || 1);
  const fit = c => { const w = c.clientWidth, h = Math.round(w * c.height / c.width); c.width = w * dpr(); c.height = h * dpr(); };
  let sized = false;
  function drawStrip() {
    const ctx = strip.getContext("2d"), W = strip.width, Hh = strip.height, k = dpr();
    ctx.clearRect(0, 0, W, Hh);
    const top = 18 * k, h = 46 * k;
    for (let x = 0; x < W; x++) {
      const [r, g, b] = lamColor(lamOf(x / W));
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(x, top, 1, h);
    }
    ctx.fillStyle = "#9aa4bd";
    ctx.font = `${12 * k}px "IBM Plex Sans Condensed", sans-serif`;
    for (let i = 0; i <= 4; i++) {
      const x = (i / 4) * W, l = lamOf(i / 4);
      ctx.textAlign = i === 0 ? "left" : i === 4 ? "right" : "center";
      ctx.fillText(`${l.toFixed(2)} µm`, x, top + h + 18 * k);
    }
    ctx.textAlign = "left";
    ctx.fillText("detector column, where the star lands", 0, 12 * k);
    [[st.x1, "1"], [st.x2, "2"]].forEach(([x, lab]) => {
      const px = x * W;
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2 * k;
      ctx.beginPath(); ctx.moveTo(px, top - 4 * k); ctx.lineTo(px, top + h + 4 * k); ctx.stroke();
      ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(px, top + h / 2, 11 * k, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = "#101626"; ctx.textAlign = "center"; ctx.font = `600 ${13 * k}px "IBM Plex Sans Condensed", sans-serif`;
      ctx.fillText(lab, px, top + h / 2 + 4.5 * k);
      ctx.font = `${12 * k}px "IBM Plex Sans Condensed", sans-serif`; ctx.textAlign = "left"; ctx.fillStyle = "#9aa4bd";
    });
  }
  function drawSpec() {
    const ctx = spec.getContext("2d"), W = spec.width, Hh = spec.height, k = dpr();
    ctx.clearRect(0, 0, W, Hh);
    const [a, b] = BANDS[st.band], lo = a * 0.97, hi = b * 1.03;
    const pad = { l: 44 * k, r: 10 * k, t: 14 * k, b: 30 * k };
    const xs = l => pad.l + (Math.log(l / lo) / Math.log(hi / lo)) * (W - pad.l - pad.r);
    const pts = [];
    for (let i = 0; i <= 300; i++) { const l = lo * (hi / lo) ** (i / 300); pts.push([l, spectrum(st.T, l, st.ice)]); }
    const ymax = Math.max(...pts.map(p => p[1])) * 1.08;
    const ys = v => Hh - pad.b - (v / ymax) * (Hh - pad.t - pad.b);
    ctx.strokeStyle = "#2d375a"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, Hh - pad.b); ctx.lineTo(W - pad.r, Hh - pad.b); ctx.stroke();
    const R = BANDS[st.band][2];
    [[st.x1, "#e4e8f2"], [st.x2, "#e2b830"]].forEach(([x, col]) => {
      const l = lamOf(x), w = l / R;
      ctx.fillStyle = col + "33";
      ctx.fillRect(xs(l - w / 2), pad.t, xs(l + w / 2) - xs(l - w / 2), Hh - pad.t - pad.b);
      ctx.strokeStyle = col; ctx.lineWidth = 2 * k;
      const yv = ys(measure(l));
      ctx.beginPath(); ctx.moveTo(xs(l - w / 2), yv); ctx.lineTo(xs(l + w / 2), yv); ctx.stroke();
    });
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.6 * k; ctx.beginPath();
    pts.forEach(([l, v], i) => (i ? ctx.lineTo(xs(l), ys(v)) : ctx.moveTo(xs(l), ys(v))));
    ctx.stroke();
    ctx.fillStyle = "#9aa4bd"; ctx.font = `${12 * k}px "IBM Plex Sans Condensed", sans-serif`;
    ctx.textAlign = "center";
    [a, (a + b) / 2, b].forEach(l => ctx.fillText(`${l.toFixed(2)} µm`, xs(l), Hh - 9 * k));
    ctx.save(); ctx.translate(14 * k, Hh / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("brightness Fν", 0, 0); ctx.restore();
  }
  function update() {
    if (!sized) { fit(strip); fit(spec); sized = true; }
    const l1 = lamOf(st.x1), l2 = lamOf(st.x2), R = BANDS[st.band][2];
    const off = Math.abs(l2 - l1) / ((l1 + l2) / 2 / R);
    const chg = measure(l2) / measure(l1) - 1;
    $("#rd1").textContent = `${l1.toFixed(3)} µm`;
    $("#rd2").textContent = `${l2.toFixed(3)} µm`;
    $("#rdOff").textContent = `${off.toFixed(2)} channels`;
    $("#rdChg").textContent = `${chg >= 0 ? "+" : ""}${(100 * chg).toFixed(1)}%`;
    const v = $("#rdVerdict"), fair = off <= 0.5;
    v.className = "verdict " + (fair ? "fair" : "unfair");
    v.textContent = fair
      ? "Fair pair: the colours agree within half a channel. A change here is worth testing."
      : `Not a fair pair. The star did not change, but the camera reports ${(100 * chg).toFixed(1)} percent. That is the filter, not the sky.`;
    $("#labTout").textContent = `${st.T} K`;
    drawStrip(); drawSpec();
  }
  $("#labBand").addEventListener("change", e => { st.band = +e.target.value; update(); });
  $("#labT").addEventListener("input", e => { st.T = +e.target.value; update(); });
  $("#labIce").addEventListener("change", e => {
    st.ice = e.target.checked;
    if (st.ice && st.band < 3) { st.band = 3; $("#labBand").value = "3"; st.x1 = 0.36; st.x2 = 0.47; }
    update();
  });
  let drag = null;
  const pos = e => { const r = strip.getBoundingClientRect(); return Math.min(0.999, Math.max(0, (e.clientX - r.left) / r.width)); };
  strip.addEventListener("pointerdown", e => { const x = pos(e); drag = Math.abs(x - st.x1) < Math.abs(x - st.x2) ? "x1" : "x2"; st[drag] = x; strip.setPointerCapture(e.pointerId); update(); });
  strip.addEventListener("pointermove", e => { if (drag) { st[drag] = pos(e); update(); } });
  strip.addEventListener("pointerup", () => { drag = null; });
  strip.tabIndex = 0;
  strip.addEventListener("keydown", e => {
    const step = e.shiftKey ? 0.01 : 0.002;
    if (e.key === "ArrowRight") st.x2 = Math.min(0.999, st.x2 + step);
    else if (e.key === "ArrowLeft") st.x2 = Math.max(0, st.x2 - step);
    else return;
    e.preventDefault(); update();
  });
  window.addEventListener("resize", () => { sized = false; update(); });
  update();
})();

/* ---------- small SVG charts ---------- */
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function frame(host, { xlab, ylab, x0, x1, y0, y1, xticks, yticks, xfmt = v => v, yfmt = v => v, w = 560, h = 340, m = { l: 52, r: 14, t: 16, b: 46 } }) {
  host.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "xMidYMid meet" }, host);
  const X = v => m.l + ((v - x0) / (x1 - x0)) * (w - m.l - m.r);
  const Y = v => h - m.b - ((v - y0) / (y1 - y0)) * (h - m.t - m.b);
  const g = el("g", { class: "grid" }, svg), ax = el("g", { class: "axis" }, svg);
  (yticks || []).forEach(t => {
    el("line", { x1: m.l, x2: w - m.r, y1: Y(t), y2: Y(t) }, g);
    el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, ax).textContent = yfmt(t);
  });
  (xticks || []).forEach(t => { el("text", { x: X(t), y: h - m.b + 18, "text-anchor": "middle" }, ax).textContent = xfmt(t); });
  el("line", { x1: m.l, x2: w - m.r, y1: h - m.b, y2: h - m.b }, ax);
  if (xlab) el("text", { x: (m.l + w - m.r) / 2, y: h - 6, "text-anchor": "middle" }, ax).textContent = xlab;
  if (ylab) { const t = el("text", { x: 0, y: 0, "text-anchor": "middle", transform: `translate(14 ${(m.t + h - m.b) / 2}) rotate(-90)` }, ax); t.textContent = ylab; }
  return { svg, X, Y, w, h, m };
}
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function wilson(k, n, z = 1.96) {
  if (!n) return [0, 0];
  const p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, w = (z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d;
  return [Math.max(0, c - w), Math.min(1, c + w)];
}
function bars(host, items, { ymax = 1, ylab = "", pct = true, colors } = {}) {
  const n = items.length;
  const f = frame(host, { ylab, x0: 0, x1: n, y0: 0, y1: ymax, yticks: [0, ymax / 4, ymax / 2, (3 * ymax) / 4, ymax], yfmt: v => (pct ? Math.round(v * 100) + "%" : v), xticks: [] });
  items.forEach((it, i) => {
    const bw = (f.X(1) - f.X(0)) * 0.56, cx = f.X(i + 0.5);
    el("rect", { x: cx - bw / 2, y: f.Y(it.v), width: bw, height: f.Y(0) - f.Y(it.v), fill: (colors && colors[i]) || css("--ink"), rx: 2 }, f.svg);
    if (it.lo != null) {
      el("line", { x1: cx, x2: cx, y1: f.Y(it.lo), y2: f.Y(it.hi), stroke: css("--graphite"), "stroke-width": 1.5 }, f.svg);
      [it.lo, it.hi].forEach(v => el("line", { x1: cx - 6, x2: cx + 6, y1: f.Y(v), y2: f.Y(v), stroke: css("--graphite"), "stroke-width": 1.5 }, f.svg));
    }
    el("text", { x: cx, y: f.Y(Math.max(it.v, it.hi || 0)) - 8, "text-anchor": "middle", style: "font-weight:600;fill:" + css("--ink") }, f.svg).textContent = it.top;
    el("text", { x: cx, y: f.h - f.m.b + 18, "text-anchor": "middle" }, f.svg).textContent = it.label;
    if (it.sub) el("text", { x: cx, y: f.h - f.m.b + 33, "text-anchor": "middle" }, f.svg).textContent = it.sub;
  });
}

async function getJSON(p) {
  try { const r = await fetch(p); return r.ok ? r.json() : null; } catch { return null; }
}

(async () => {
  const [val, curves, fields, inj, tiles] = await Promise.all(
    ["data/validation.json", "data/lvf_curves.json", "data/real_fields.json", "data/real_injection.json", "data/sky_tiles.json"].map(getJSON));

  if (val) {
    const set = (k, v) => $$(`[data-stat="${k}"]`).forEach(e => (e.textContent = v));
    set("acc", (100 * val.unknown.accuracy_when_decided).toFixed(1) + "%");
    set("fields", val.test_fields);
    const adv = Object.values(val.adversarial);
    const rej = adv.reduce((s, a) => s + a.n - a.called_sky, 0), tot = adv.reduce((s, a) => s + a.n, 0);
    set("camera", `${rej} of ${tot}`);
    set("brier", val.brier.toFixed(3));
    set("ece", val.ece.toFixed(3));
    set("static", `${val.controls.static_called_moving} of ${val.controls.static_stars}`);
    set("nullmean", val.controls.null_candidates_mean.toFixed(3));

    const abc = val.agreement_by_count, A = val.agreement_patterns.A;
    const items = ["1", "2", "3"].map(k => ({ v: abc[k].sky_fraction, lo: abc[k].lo, hi: abc[k].hi, top: Math.round(100 * abc[k].sky_fraction) + "%", label: `${k} detector${k === "1" ? "" : "s"}`, sub: `n = ${abc[k].n}` }));
    if (A) items.push({ v: A.sky_fraction, lo: A.lo, hi: A.hi, top: Math.round(100 * A.sky_fraction) + "%", label: "anomaly only", sub: `n = ${A.n}` });
    bars($("#agreeChart"), items, { ylab: "share that is a real sky change", colors: [css("--graphite"), css("--cool"), css("--sky"), css("--instrument")] });

    const rel = val.reliability.filter(r => r.n);
    const f = frame($("#relChart"), { xlab: "engine confidence", ylab: "observed accuracy", x0: 0.5, x1: 1, y0: 0.3, y1: 1, xticks: [0.5, 0.75, 1], yticks: [0.4, 0.6, 0.8, 1], xfmt: v => Math.round(v * 100) + "%", yfmt: v => Math.round(v * 100) + "%" });
    el("line", { x1: f.X(0.5), y1: f.Y(0.5), x2: f.X(1), y2: f.Y(1), stroke: css("--rule"), "stroke-width": 2, "stroke-dasharray": "5 4" }, f.svg);
    rel.forEach(r => el("circle", { cx: f.X(r.confidence), cy: f.Y(r.accuracy), r: 4 + Math.sqrt(r.n), fill: css("--sky"), "fill-opacity": 0.75 }, f.svg));

    const names = { glitch: "glitches", hot: "hot pixels", ghost: "crosstalk" };
    bars($("#advChart"), Object.entries(val.adversarial).map(([k, a]) => ({ v: a.rejected, lo: a.lo, hi: a.hi, top: `${a.n - a.called_sky}/${a.n}`, label: names[k] || k })),
      { ylab: "rejected as artefact or unknown", colors: [css("--instrument"), css("--instrument"), css("--instrument")] });

    const mv = val.completeness.moving;
    const mags = Object.keys(mv).sort((a, b) => a - b);
    bars($("#compChart"), mags.map(m => ({ v: mv[m].fraction, lo: mv[m].lo, hi: mv[m].hi, top: `${mv[m].found}/${mv[m].n}`, label: `AB ${m}` })),
      { ylab: "moving sources found", colors: mags.map(() => css("--cool")) });
  }

  if (tiles && tiles.summary) $$('[data-stat="tiles"]').forEach(e => (e.textContent = Math.round(100 * tiles.summary.corrected_over_true) + "%"));

  if (curves) {
    const host = $("#matlabChart");
    const all = curves.curves.flatMap(c => c.change_percent);
    const lo = Math.floor(Math.min(...all) / 5) * 5, hi = Math.ceil(Math.max(...all) / 5) * 5;
    const yt = []; for (let v = lo; v <= hi; v += 5) yt.push(v);
    const f = frame(host, { xlab: "colour offset between the two visits (nm)", ylab: "apparent change (%)", x0: -80, x1: 80, y0: lo, y1: hi, xticks: [-80, -40, 0, 40, 80], yticks: yt, w: 760, h: 360 });
    const cols = ["#e2602a", "#e2b830", "#9cc7ff", "#2db37a"];
    curves.curves.forEach((c, i) => {
      const d = c.change_percent.map((v, j) => `${j ? "L" : "M"}${f.X(curves.dlam_nm[j]).toFixed(1)},${f.Y(v).toFixed(1)}`).join("");
      el("path", { d, fill: "none", stroke: cols[i % cols.length], "stroke-width": 2.6, "stroke-dasharray": i === 3 ? "7 5" : "" }, f.svg);
      el("rect", { x: f.X(8), y: f.m.t + 6 + i * 20, width: 14, height: 3, fill: cols[i % cols.length] }, f.svg);
      el("text", { x: f.X(8) + 20, y: f.m.t + 11 + i * 20 }, f.svg).textContent = c.label.replace(" um", " µm");
    });
    const chw = 1.6 / 41 * 1000;
    [-chw, chw].forEach(v => el("line", { x1: f.X(v), x2: f.X(v), y1: f.Y(lo), y2: f.Y(hi), stroke: "#56628a", "stroke-dasharray": "2 4" }, f.svg));
    el("text", { x: f.X(chw) + 4, y: f.Y(lo) - 8 }, f.svg).textContent = "one channel at 1.6 µm";
  }

  if (fields) {
    const host = $("#fieldChart"), rows = fields.fields, n = fields.n_per_level;
    const w = 560, h = 60 + rows.length * 44;
    const f = frame(host, { xlab: "injected sources recovered", x0: 0, x1: 1, y0: 0, y1: rows.length, xticks: [0, 0.25, 0.5, 0.75, 1], xfmt: v => Math.round(v * 100) + "%", w, h, m: { l: 150, r: 16, t: 26, b: 44 } });
    host.style.aspectRatio = `${w} / ${h}`;
    [0, 0.25, 0.5, 0.75, 1].forEach(t => el("line", { x1: f.X(t), x2: f.X(t), y1: f.m.t - 10, y2: h - f.m.b, stroke: css("--rule"), "stroke-dasharray": "2 3" }, f.svg));
    const cols = [css("--rule"), css("--graphite"), css("--ink")], labs = ["½ × 5σ", "1 × 5σ", "2 × 5σ"];
    labs.forEach((l, i) => {
      el("circle", { cx: f.m.l + 10 + i * 90, cy: 10, r: 5, fill: cols[i], stroke: css("--ink") }, f.svg);
      el("text", { x: f.m.l + 20 + i * 90, y: 14 }, f.svg).textContent = l;
    });
    rows.forEach((r, i) => {
      const y = f.m.t + 14 + i * 44;
      el("text", { x: f.m.l - 10, y: y + 4, "text-anchor": "end", style: r.recovered.every(v => !v) ? `fill:${css("--sky")};font-weight:600` : "" }, f.svg).textContent = r.name;
      r.recovered.forEach((k, j) => {
        const [a, b] = wilson(k, n), yy = y + (j - 1) * 9;
        el("line", { x1: f.X(a), x2: f.X(b), y1: yy, y2: yy, stroke: cols[j], "stroke-width": 2.5, "stroke-opacity": 0.8 }, f.svg);
        el("circle", { cx: f.X(k / n), cy: yy, r: 5, fill: cols[j], stroke: css("--ink"), "stroke-width": 1 }, f.svg);
      });
    });
  }

  if (inj && inj.fields) {
    const tot = {};
    inj.fields.forEach(fl => Object.values((fl.score || {}).by_kind || {}).forEach(bm => Object.entries(bm).forEach(([m, x]) => {
      const a = (tot[m] = tot[m] || [0, 0]); a[0] += x.found; a[1] += x.n;
    })));
    const mags = Object.keys(tot).sort((a, b) => a - b);
    bars($("#qr3Chart"), mags.map(m => { const [k, n] = tot[m], [lo, hi] = wilson(k, n); return { v: k / n, lo, hi, top: `${k}/${n}`, label: `AB ${m}` }; }),
      { ylab: "found in real QR3 images", colors: mags.map(() => css("--sky")) });
  }

  const diag = await getJSON("data/injection_diagnostics.json");
  if (diag && diag.fields && $("#skyChart")) {
    const names = { HighLatitude_Control: "control", Lupus_III: "Lupus III", Orion_A: "Orion A", Perseus_NGC1333: "Perseus", Rho_Ophiuchi: "Rho Oph", Taurus_Auriga: "Taurus" };
    const pts = diag.fields.map(f => ({ x: f.image.region_noise_excess, y: f.levels[2].recovered / f.levels[2].n, k: f.levels[2].recovered, n: f.levels[2].n, name: names[f.field] || f.field }));
    const f = frame($("#skyChart"), { xlab: "sky scatter ÷ pipeline noise in the injection region", ylab: "recovered at 2 × 5σ", x0: 1, x1: 6, y0: 0, y1: 1, xticks: [1, 2, 3, 4, 5, 6], yticks: [0, 0.25, 0.5, 0.75, 1], xfmt: v => v + "×", yfmt: v => Math.round(v * 100) + "%" });
    pts.forEach(p => {
      const [lo, hi] = wilson(p.k, p.n);
      el("line", { x1: f.X(p.x), x2: f.X(p.x), y1: f.Y(lo), y2: f.Y(hi), stroke: css("--rule"), "stroke-width": 3 }, f.svg);
      el("circle", { cx: f.X(p.x), cy: f.Y(p.y), r: 8, fill: p.name === "Lupus III" ? css("--sky") : css("--ink") }, f.svg);
      el("text", { x: f.X(p.x) + 12, y: f.Y(p.y) + (p.name === "Orion A" ? 16 : -8), style: "font-weight:600" }, f.svg).textContent = `${p.name} ${p.k}/${p.n}`;
    });
  }
})();

/* ---------- code tabs ---------- */
$$(".tabs [role=tab]").forEach(t => t.addEventListener("click", () => {
  $$(".tabs [role=tab]").forEach(o => {
    const on = o === t;
    o.setAttribute("aria-selected", String(on));
    document.getElementById(o.getAttribute("aria-controls")).hidden = !on;
  });
}));

/* ---------- film: the idea in forty seconds ---------- */
(() => {
  const cv = $("#filmCanvas");
  if (!cv) return;
  const ctx = cv.getContext("2d"), W = cv.width, Hh = cv.height;
  const SCENES = [
    [7, "SPHEREx circles Earth and maps the whole sky in 102 infrared colours."],
    [7, "A rainbow filter sits on each detector, so every column of pixels sees its own colour."],
    [7, "The same star lands on another column next visit. Another colour, another number: a change that never happened."],
    [7, "CHRONOS compares only fair pairs: same array, same colour. What survives is real."],
    [7, "Every change faces five explanations, with calibrated odds and the right to say unknown."],
    [7, "On real NASA data even the sky’s own glow is measured: in Lupus III it hid every planted star."],
  ];
  const total = SCENES.reduce((a, s) => a + s[0], 0);
  const r = rng(5), stars = Array.from({ length: 140 }, () => ({ x: r(), y: r(), b: r(), T: 2600 + r() ** 1.5 * 12000 }));
  let t0 = performance.now(), paused = reduced, offset = 0, shown = -1;
  const dots = $("#filmScenes");
  SCENES.forEach((_, i) => { const b = document.createElement("button"); b.setAttribute("role", "tab"); b.setAttribute("aria-label", `Scene ${i + 1}`); b.onclick = () => { offset = SCENES.slice(0, i).reduce((a, s) => a + s[0], 0); t0 = performance.now(); if (paused) draw(offset); }; dots.appendChild(b); });
  const ease = x => x < 0 ? 0 : x > 1 ? 1 : x * x * (3 - 2 * x);
  const lvf = (x0, y0, w, h, a = 1) => { for (let i = 0; i < w; i += 2) { const [rr, g, b] = lamColor(0.75 * (5 / 0.75) ** (i / w)); ctx.fillStyle = `rgba(${rr},${g},${b},${a})`; ctx.fillRect(x0 + i, y0, 2, h); } };
  const text = (s, x, y, size = 30, col = "#f1f3f8", align = "left", font = "Cormorant Garamond") => { ctx.font = `600 ${size}px "${font}", serif`; ctx.fillStyle = col; ctx.textAlign = align; ctx.fillText(s, x, y); };
  const starDot = (x, y, rad, col) => { const g = ctx.createRadialGradient(x, y, 0, x, y, rad); g.addColorStop(0, col); g.addColorStop(1, "rgba(0,0,0,0)"); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, rad, 0, 7); ctx.fill(); };
  function bg(p) {
    ctx.fillStyle = "#0b1020"; ctx.fillRect(0, 0, W, Hh);
    for (const s of stars) { ctx.fillStyle = `rgba(228,232,242,${0.25 + 0.6 * s.b})`; ctx.fillRect(((s.x + p * 0.01) % 1) * W, s.y * Hh, 1.6, 1.6); }
  }
  const scenes = [
    p => { // orbit
      const cx = W / 2, cy = Hh / 2 + 20;
      const g = ctx.createRadialGradient(cx - 40, cy - 40, 10, cx, cy, 150); g.addColorStop(0, "#5b8fd8"); g.addColorStop(1, "#14305e");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, 130, 0, 7); ctx.fill();
      ctx.strokeStyle = "rgba(255,134,180,.5)"; ctx.setLineDash([6, 8]); ctx.beginPath(); ctx.ellipse(cx, cy, 250, 80, -0.25, 0, 7); ctx.stroke(); ctx.setLineDash([]);
      const a = p * 7 * 1.6, sx = cx + 250 * Math.cos(a) * Math.cos(-0.25) - 80 * Math.sin(a) * Math.sin(-0.25), sy = cy + 250 * Math.cos(a) * Math.sin(-0.25) + 80 * Math.sin(a) * Math.cos(-0.25);
      ctx.fillStyle = "#e2b830"; ctx.fillRect(sx - 9, sy - 5, 18, 10); ctx.fillStyle = "#9cc7ff"; ctx.fillRect(sx - 26, sy - 3, 14, 6); ctx.fillRect(sx + 12, sy - 3, 14, 6);
      for (let k = 0; k < 6; k++) { ctx.strokeStyle = "rgba(226,184,48,.25)"; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx + Math.cos(a + 1.5) * 900, sy + Math.sin(a + 1.5) * 900); ctx.stroke(); }
      lvf(160, Hh - 70, W - 320, 14, ease(p * 2)); text("0.75 µm", 160, Hh - 82, 22, "#c3cbdd"); text("5.0 µm", W - 160, Hh - 82, 22, "#c3cbdd", "right");
    },
    p => { // detector with filter, stars sliding
      const x0 = 140, y0 = 120, w = W - 280, h = 420;
      lvf(x0, y0, w, h, 0.85);
      ctx.fillStyle = "rgba(11,16,32,.55)"; ctx.fillRect(x0, y0, w, h);
      for (let i = 0; i < 40; i++) { const s = stars[i], x = x0 + ((s.x + p * 0.35) % 1) * w, y = y0 + 20 + s.y * (h - 40); const [rr, g, b] = lamColor(0.75 * (5 / 0.75) ** ((x - x0) / w)); starDot(x, y, 10 + 10 * s.b, `rgb(${rr},${g},${b})`); }
      text("each column, its own colour", W / 2, y0 + h + 60, 34, "#f1f3f8", "center");
    },
    p => { // same star, two columns, two numbers
      const x0 = 140, y0 = 150, w = W - 280, h = 160;
      lvf(x0, y0, w, h, 0.9);
      const a = x0 + w * 0.3, b = x0 + w * (0.3 + 0.22 * ease(p * 1.6));
      starDot(a, y0 + h / 2, 30, "#ffffff"); starDot(b, y0 + h / 2, 30, "#ffffff");
      text("visit 1", a, y0 - 18, 26, "#c3cbdd", "center"); text("visit 2", b, y0 - 18, 26, "#c3cbdd", "center");
      const f1 = 1, f2 = 1 - 0.09 * ease(p * 1.6);
      ctx.fillStyle = "#9cc7ff"; ctx.fillRect(W / 2 - 220, 560 - 180 * f1, 120, 180 * f1);
      ctx.fillStyle = "#ff86b4"; ctx.fillRect(W / 2 + 100, 560 - 180 * f2, 120, 180 * f2);
      text("measured, visit 1", W / 2 - 160, 600, 24, "#c3cbdd", "center"); text("measured, visit 2", W / 2 + 160, 600, 24, "#c3cbdd", "center");
      text(`${(-9 * ease(p * 1.6)).toFixed(1)}%`, W / 2, 470, 64, "#ff86b4", "center");
      text("the star did not change", W / 2, 660, 30, "#f1f3f8", "center");
    },
    p => { // fair pair: difference shows only the mover
      const pan = (x, label, diff) => {
        ctx.fillStyle = "#e6ebea"; ctx.fillRect(x, 170, 300, 300);
        for (let i = 0; i < 26; i++) { const s = stars[i + 40]; const px = x + 20 + s.x * 260, py = 190 + s.y * 260; if (!diff) { ctx.fillStyle = "#0f1b2d"; ctx.beginPath(); ctx.arc(px, py, 3 + 5 * s.b, 0, 7); ctx.fill(); } }
        if (diff) { const k = ease(p * 2); ctx.fillStyle = `rgba(43,93,156,${k})`; ctx.beginPath(); ctx.arc(x + 120, 300, 12, 0, 7); ctx.fill(); ctx.fillStyle = `rgba(192,48,106,${k})`; ctx.beginPath(); ctx.arc(x + 150, 318, 12, 0, 7); ctx.fill(); ctx.strokeStyle = "#0f1b2d"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x + 135, 309, 34, 0, 7); ctx.stroke(); }
        text(label, x + 150, 510, 26, "#c3cbdd", "center");
      };
      pan(130, "visit 1, 1.31 µm", false); pan(490, "visit 2, 1.31 µm", false); pan(850, "difference", true);
      text("same colour on both visits: only the asteroid is left", W / 2, 600, 32, "#f1f3f8", "center");
    },
    p => { // five explanations
      const H = ["moving", "variable", "transient", "camera artefact", "nothing"], P = [0.86, 0.06, 0.03, 0.04, 0.01];
      H.forEach((h, i) => {
        const y = 170 + i * 82, k = ease(p * 2.2 - i * 0.15);
        ctx.fillStyle = "#1b2440"; ctx.fillRect(300, y, 680, 54);
        ctx.fillStyle = i === 0 ? "#c0306a" : "#2b5d9c"; ctx.fillRect(300, y, 680 * P[i] * k, 54);
        text(h, 280, y + 38, 30, "#f1f3f8", "right"); text(`${Math.round(100 * P[i] * k)}%`, 1000, y + 38, 30, "#f1f3f8");
      });
      text("or: unknown, when the evidence is thin", W / 2, 640, 30, "#e2b830", "center");
    },
    p => { // lumpy cloud hides a star
      const x0 = 340, y0 = 130, n = 60, cs = 10;
      const rr = rng(9);
      const blobs = Array.from({ length: 30 }, () => [rr() * n, rr() * n, 1.5 + rr() * 3, rr()]);
      for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
        let v = 0; for (const [bx, by, s, a] of blobs) v += a * Math.exp(-((i - bx) ** 2 + (j - by) ** 2) / (2 * s * s));
        v = Math.min(1, v * 0.8 * ease(p * 1.5) + 0.1 * rr());
        ctx.fillStyle = `rgb(${30 + 200 * v},${20 + 90 * v},${50 + 120 * v})`; ctx.fillRect(x0 + i * cs, y0 + j * cs, cs, cs);
      }
      ctx.strokeStyle = "#9cc7ff"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x0 + 300, y0 + 300, 26, 0, 7); ctx.stroke();
      text("planted star: here, but outshone", x0 + 345, y0 + 300, 24, "#9cc7ff");
      text("sky 5.5× noisier than the camera alone", W / 2, 700, 30, "#f1f3f8", "center");
    },
  ];
  function draw(tt) {
    let t = tt % total, i = 0;
    while (t > SCENES[i][0]) { t -= SCENES[i][0]; i++; }
    const p = t / SCENES[i][0];
    bg(tt / total);
    ctx.save(); ctx.globalAlpha = Math.min(1, t / 0.6, (SCENES[i][0] - t) / 0.6 + 0.15); scenes[i](p); ctx.restore();
    if (i !== shown) { shown = i; $("#filmCap").textContent = SCENES[i][1]; [...dots.children].forEach((d, k) => d.setAttribute("aria-selected", String(k === i))); }
  }
  let visible = false;
  new IntersectionObserver(es => es.forEach(e => (visible = e.isIntersecting)), { threshold: 0.2 }).observe(cv);
  const loop = now => { if (!paused && visible) draw(offset + (now - t0) / 1000); requestAnimationFrame(loop); };
  draw(0); requestAnimationFrame(loop);
  const pb = $("#filmPlay");
  pb.textContent = paused ? "Play" : "Pause";
  pb.onclick = () => { if (paused) { t0 = performance.now(); } else { offset += (performance.now() - t0) / 1000; } paused = !paused; pb.textContent = paused ? "Play" : "Pause"; };
})();

/* ---------- simulation: parallax against orbit ---------- */
(() => {
  const cv = $("#pxSky");
  if (!cv) return;
  const AS = 206264.8;
  function fit(t, X, Y, e, fx, fy) { // least squares for H0, H1, H2 with equal weights
    const n = t.length, tc = t.map(v => v - t.reduce((a, b) => a + b, 0) / n);
    const cols = { H0: [[1, 0], [0, 1]], H1: [[1, 0], [0, 1], ["t", 0], [0, "t"]], H2: [[1, 0], [0, 1], ["t", 0], [0, "t"], ["fx", "fy"]] };
    const out = {};
    for (const [k, cs] of Object.entries(cols)) {
      const A = [], y = [];
      for (let i = 0; i < n; i++) {
        A.push(cs.map(([a]) => (a === 1 ? 1 : a === "t" ? tc[i] : a === "fx" ? fx[i] : 0))); y.push(X[i]);
        A.push(cs.map(([, b]) => (b === 1 ? 1 : b === "t" ? tc[i] : b === "fy" ? fy[i] : 0))); y.push(Y[i]);
      }
      const m = cs.length, N = Array.from({ length: m }, () => Array(m + 1).fill(0));
      A.forEach((row, r) => { for (let a = 0; a < m; a++) { for (let b = 0; b < m; b++) N[a][b] += row[a] * row[b]; N[a][m] += row[a] * y[r]; } });
      for (let c = 0; c < m; c++) { let pv = c; for (let r = c + 1; r < m; r++) if (Math.abs(N[r][c]) > Math.abs(N[pv][c])) pv = r; [N[c], N[pv]] = [N[pv], N[c]]; for (let r = 0; r < m; r++) if (r !== c) { const f = N[r][c] / (N[c][c] || 1e-12); for (let q = c; q <= m; q++) N[r][q] -= f * N[c][q]; } }
      const par = N.map((row, i) => row[m] / (row[i] || 1e-12));
      const chi = A.reduce((s, row, r) => s + ((y[r] - row.reduce((a, v, i) => a + v * par[i], 0)) / e) ** 2, 0);
      out[k] = { chi, bic: chi + m * Math.log(2 * n), par };
    }
    return out;
  }
  function run() {
    const d = +$("#pxD").value, beta = (+$("#pxB").value * Math.PI) / 180, yrs = +$("#pxY").value, e = +$("#pxE").value;
    $("#pxDout").textContent = `${d} au`; $("#pxBout").textContent = `${$("#pxB").value}°`; $("#pxYout").textContent = yrs.toFixed(1); $("#pxEout").textContent = `${e}″`;
    const plx = AS / d, mu = ((2 * Math.PI) / d ** 1.5) * AS; // arcsec and arcsec per year
    const path = [], obs = [], r = rng(42);
    for (let i = 0; i <= 400; i++) { const t = (yrs * i) / 400; path.push([mu * t + plx * Math.sin(2 * Math.PI * t), plx * Math.sin(beta) * Math.cos(2 * Math.PI * t)]); }
    const t = [], X = [], Y = [], fx = [], fy = [];
    for (let k = 0; k < Math.round(yrs * 2) + 1; k++) for (const dt of [0, 0.02]) { const tt = k * 0.5 + 0.07 + dt; if (tt > yrs) continue; t.push(tt); fx.push(Math.sin(2 * Math.PI * tt)); fy.push(Math.sin(beta) * Math.cos(2 * Math.PI * tt)); X.push(mu * tt + plx * fx.at(-1) + e * gauss(r)); Y.push(plx * fy.at(-1) + e * gauss(r)); }
    const ctx = cv.getContext("2d"), Wc = cv.width, Hc = cv.height;
    ctx.fillStyle = "#101626"; ctx.fillRect(0, 0, Wc, Hc);
    const xs = path.map(p => p[0]), ys = path.map(p => p[1]);
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 4 * e) * 1.25;
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2, sc = Math.min(Wc, Hc) / span;
    const P = ([x, y]) => [Wc / 2 + (x - cx) * sc, Hc / 2 - (y - cy) * sc];
    ctx.strokeStyle = "#2d375a"; ctx.lineWidth = 1;
    ctx.strokeStyle = "#e2b830"; ctx.lineWidth = 2; ctx.beginPath(); path.forEach((p, i) => { const [a, b] = P(p); i ? ctx.lineTo(a, b) : ctx.moveTo(a, b); }); ctx.stroke();
    X.forEach((x, i) => { const [a, b] = P([x, Y[i]]); ctx.strokeStyle = "rgba(255,134,180,.6)"; ctx.beginPath(); ctx.arc(a, b, Math.max(3, e * sc), 0, 7); ctx.stroke(); ctx.fillStyle = "#ff86b4"; ctx.beginPath(); ctx.arc(a, b, 3, 0, 7); ctx.fill(); });
    ctx.fillStyle = "#9aa4bd"; ctx.font = '14px "IBM Plex Sans Condensed", sans-serif'; ctx.textAlign = "left";
    const unit = span > 120 ? `${(span / 60).toFixed(1)}′ across` : `${span.toFixed(1)}″ across`;
    ctx.fillText(`view ${unit}; yellow: true path; pink: SPHEREx visits every six months`, 12, Hc - 12);
    const F = fit(t, X, Y, e, fx, fy), best = F.H2.bic < F.H1.bic - 2 ? "motion plus parallax" : F.H1.bic < F.H0.bic - 10 ? "moving" : "fixed";
    const dB = F.H0.bic - Math.min(F.H1.bic, F.H2.bic);
    $("#pxOut").innerHTML = `Parallax amplitude <b>${plx > 120 ? (plx / 60).toFixed(1) + "′" : plx.toFixed(1) + "″"}</b>, orbital drift <b>${mu > 120 ? (mu / 60).toFixed(2) + "′" : mu.toFixed(1) + "″"} per year</b> (Kepler: P = ${(d ** 1.5).toFixed(0)} years). With ${t.length} positions the motion court says <b>${best}</b> (ΔBIC ${dB.toFixed(0)}).`;
  }
  ["#pxD", "#pxB", "#pxY", "#pxE"].forEach(id => $(id).addEventListener("input", run));
  run();
})();

/* ---------- simulation: a star hidden by a glowing cloud ---------- */
(() => {
  const cI = $("#nbImg");
  if (!cI) return;
  const N = 64, PS = 1.3;
  let seed = 3;
  const psf = []; let ps2 = 0;
  for (let y = -4; y <= 4; y++) for (let x = -4; x <= 4; x++) { const v = Math.exp(-(x * x + y * y) / (2 * PS * PS)); psf.push([x, y, v]); ps2 += v * v; }
  const psum = psf.reduce((a, p) => a + p[2], 0);
  function snrMap(img, sig) { // matched filter with per-pixel noise sig
    const out = new Float32Array(N * N);
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
      let s = 0, w = 0;
      for (const [dx, dy, v] of psf) { const x = i + dx, y = j + dy; if (x < 0 || y < 0 || x >= N || y >= N) continue; const k = y * N + x; s += v * img[k] / (sig[k] * sig[k]); w += v * v / (sig[k] * sig[k]); }
      out[j * N + i] = s / Math.sqrt(w || 1);
    }
    return out;
  }
  function mesh(img) { // 16 px cells: median background and robust scatter
    const C = 16, bg = new Float32Array(N * N), sc = new Float32Array(N * N);
    for (let cy = 0; cy < N; cy += C) for (let cx = 0; cx < N; cx += C) {
      const v = []; for (let y = cy; y < cy + C; y++) for (let x = cx; x < cx + C; x++) v.push(img[y * N + x]);
      v.sort((a, b) => a - b); const med = v[v.length >> 1];
      const dev = v.map(q => Math.abs(q - med)).sort((a, b) => a - b), mad = 1.4826 * dev[dev.length >> 1];
      for (let y = cy; y < cy + C; y++) for (let x = cx; x < cx + C; x++) { bg[y * N + x] = med; sc[y * N + x] = Math.max(1, mad); }
    }
    return { bg, sc };
  }
  function verdict(snr, sx, sy) { // brightest peak within 7 px must sit within 2.5 px of the source and pass 5
    let best = -1e9, bx = 0, by = 0;
    for (let y = sy - 7; y <= sy + 7; y++) for (let x = sx - 7; x <= sx + 7; x++) { const v = snr[y * N + x]; if (v > best) { best = v; bx = x; by = y; } }
    const ok = best >= 5 && Math.hypot(bx - sx, by - sy) <= 2.5;
    return { ok, best, near: Math.hypot(bx - sx, by - sy) };
  }
  const paint = (cv, arr, lo, hi, cmap) => {
    const ctx = cv.getContext("2d"), im = ctx.createImageData(N, N);
    for (let i = 0; i < N * N; i++) { const v = Math.max(0, Math.min(1, (arr[i] - lo) / (hi - lo))); im.data.set(cmap(v), i * 4); }
    const off = document.createElement("canvas"); off.width = off.height = N; off.getContext("2d").putImageData(im, 0, 0);
    ctx.imageSmoothingEnabled = false; ctx.drawImage(off, 0, 0, cv.width, cv.height);
  };
  const gray = v => [236 - 220 * v, 239 - 214 * v, 238 - 190 * v, 255];
  const heat = v => (v < 0.5 ? [16 + 60 * v, 22 + 80 * v, 38 + 200 * v, 255] : [60 + 380 * (v - 0.5), 62 + 230 * (v - 0.5), 138 - 160 * (v - 0.5), 255]);
  function run() {
    const A = +$("#nbA").value, K = +$("#nbK").value;
    $("#nbAout").textContent = A.toFixed(1); $("#nbKout").textContent = `${K.toFixed(2)} × 5σ`;
    const r = rng(seed), img = new Float32Array(N * N), sig = new Float32Array(N * N).fill(1);
    const blobs = Array.from({ length: 110 }, () => [r() * N, r() * N, 1.1 + r() * 1.4, r()]);
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) { let v = 0; for (const [bx, by, s, a] of blobs) v += a * Math.exp(-((i - bx) ** 2 + (j - by) ** 2) / (2 * s * s)); img[j * N + i] = A * v + gauss(r); }
    const flux = (K * 5 * Math.sqrt(ps2)) / (ps2 / psum) / psum * psum; // peak so the matched filter gives K x 5 in pure noise
    const sx = 32, sy = 32, amp = (K * 5) / Math.sqrt(ps2);
    for (const [dx, dy, v] of psf) img[(sy + dy) * N + sx + dx] += amp * v;
    const raw = snrMap(img, sig), m = mesh(img), fixed = new Float32Array(N * N);
    for (let i = 0; i < N * N; i++) fixed[i] = img[i] - m.bg[i];
    const honest = snrMap(fixed, m.sc);
    const v1 = verdict(raw, sx, sy), v2 = verdict(honest, sx, sy);
    const med = [...img].sort((a, b) => a - b)[N * N >> 1], ex = 1.4826 * [...img].map(v => Math.abs(v - med)).sort((a, b) => a - b)[N * N >> 1];
    paint(cI, img, -3, 4 + 2 * A, gray); paint($("#nbSnr"), raw, -2, 12, heat); paint($("#nbFix"), honest, -2, 12, heat);
    [cI, $("#nbSnr"), $("#nbFix")].forEach(cv => { const c = cv.getContext("2d"), s = cv.width / N; c.strokeStyle = "#9cc7ff"; c.lineWidth = 2; c.beginPath(); c.arc((sx + 0.5) * s, (sy + 0.5) * s, 5 * s, 0, 7); c.stroke(); });
    const say = v => (v.ok ? `<b class="ok">found</b> (SNR ${v.best.toFixed(1)})` : `<b class="miss">missed</b>, a ${v.near > 2.5 ? "brighter neighbour " + v.near.toFixed(1) + " px away won" : "peak below 5"}`);
    $("#nbOut").innerHTML = `Sky scatter is <b>${ex.toFixed(1)}×</b> the camera noise. Camera noise only: ${say(v1)}. Sky-aware noise: ${say(v2)}. <span class="note-s">The sky-aware rule needs a brighter star to claim a detection, and it stops counting bumps of glowing dust as stars.</span>`;
  }
  ["#nbA", "#nbK"].forEach(id => $(id).addEventListener("input", run));
  $("#nbNew").onclick = () => { seed++; run(); };
  run();
})();

/* ---------- where each step lives in the code ---------- */
(() => {
  const host = $("#pipe");
  if (!host) return;
  const GH = "https://github.com/PRITIDIPADAS/nakshatra-chronus/blob/main/";
  const steps = [
    ["Search the archive", "Finds every SPHEREx exposure over a place in NASA IRSA, with Gaia stars and known asteroids.", "backend/connectors.py", "tests/test_live.py"],
    ["Download and check", "Native 2040 × 2040 files with every extension, checked against IRSA’s MD5 and kept with SHA-256.", "research_discovery/spherex/run_real_field_audit.py", "research_discovery/tests/test_multifield_jy_pilot.py"],
    ["Colour of each pixel", "The spectral WCS gives the wavelength and bandwidth of every pixel.", "backend/chronos_causal/wavelength_gate.py", "tests/test_wavelength_provenance_gate.py"],
    ["Fair pairs", "Same array, colours within half a channel, one release.", "backend/core.py", "tests/test_core.py"],
    ["Three detectors", "Catalogue per visit, fair-pair difference, anomaly ensemble.", "backend/pipeline.py", "tests/test_observatory.py"],
    ["Artefact court", "Flags, crosstalk geometry, the twin array, counterfactual reanalysis.", "backend/investigate.py", "tests/test_core.py"],
    ["Five hypotheses", "Calibrated probabilities with the right to say unknown.", "backend/engine.py", "tests/test_core.py"],
    ["Motion court", "Fixed, moving, moving plus parallax; also written in MATLAB.", "matlab/motion_court.m", "tests/test_matlab_crosscheck.py"],
    ["Injection and recovery", "Plants sources in Jy with photon noise; records why each is missed.", "research_discovery/validation/injection_recovery.py", "research_discovery/tests/test_structured_background.py"],
    ["Evidence passport", "Every claim tied to its measurement, sealed with SHA-256.", "backend/chronos_causal/investigation_package.py", "tests/test_chronos_evidence_graph.py"],
  ];
  host.innerHTML = steps.map(([t], i) => `<button class="pnode" data-i="${i}" aria-pressed="false"><span class="pn">${i + 1}</span>${t}</button>`).join('<span class="parrow" aria-hidden="true"></span>');
  const show = i => {
    const [t, d, f, tf] = steps[i];
    $$(".pnode", host).forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.i === i)));
    $("#pipeDetail").innerHTML = `<h4>${i + 1}. ${t}</h4><p>${d}</p><p class="paths">Code: <a href="${GH}${f}">${f}</a><br>Tested in: <a href="${GH}${tf}">${tf}</a></p>`;
  };
  host.addEventListener("click", e => { const b = e.target.closest(".pnode"); if (b) show(+b.dataset.i); });
  show(0);
})();

/* ---------- gallery with a lightbox ---------- */
(() => {
  const g = $("#gal");
  if (!g) return;
  const figs = [["microscope", "Difference microscope: 27 false spots, then 10, then 1."], ["fair_plane", "Which exposures make fair pairs: wavelength against time."], ["disagreement", "How often each pattern of detector agreement is a real change."],
    ["calibration", "Reliability of the five-hypothesis engine."], ["completeness", "Moving sources found by brightness."], ["invisible_motion", "Motion smaller than a pixel, measured."], ["crosstalk_case", "A crosstalk copy that fooled all three detectors."],
    ["sky_tiles_pair", "Whole sky: raw and corrected change rates."], ["sky_tiles", "48 equal-area tiles with their twins."], ["planetx", "Planet X sandbox."], ["architecture", "How the parts connect."],
    ["app_hero", "The observatory’s first screen."], ["app_sky", "Sky and time: every exposure on one grid."], ["app_micro", "The difference microscope in the app."], ["app_candidates", "Candidates and their detectors."], ["app_dossier", "A candidate dossier."], ["app_validation", "Validation chapter."], ["app_planetx", "Planet X chapter."]];
  g.insertAdjacentHTML("beforeend", figs.map(([f, c]) => `<figure><button class="zoom" data-src="figures/${f}.png" data-cap="${c}"><img src="figures/${f}.png" alt="${c}" loading="lazy"></button><figcaption>${c}</figcaption></figure>`).join(""));
  const dlg = document.createElement("dialog"); dlg.className = "lightbox"; dlg.innerHTML = '<img alt=""><p></p><button class="btn small ghost light">Close</button>'; document.body.appendChild(dlg);
  g.addEventListener("click", e => { const b = e.target.closest(".zoom"); if (!b) return; dlg.querySelector("img").src = b.dataset.src; dlg.querySelector("img").alt = b.dataset.cap; dlg.querySelector("p").textContent = b.dataset.cap; dlg.showModal(); });
  dlg.addEventListener("click", e => { if (e.target === dlg || e.target.tagName === "BUTTON") dlg.close(); });
})();

/* ---------- repository map ---------- */
(async () => {
  const host = $("#repo");
  if (!host) return;
  const d = await getJSON("data/repo_map.json");
  if (!d) return;
  const GH = "https://github.com/PRITIDIPADAS/nakshatra-chronus/blob/main/";
  const max = d.folders[0].lines, tot = Object.values(d.lines_by_language).reduce((a, b) => a + b, 0);
  host.innerHTML = `<p class="repo-sum"><b>${d.files.length}</b> source files, <b>${tot.toLocaleString()}</b> lines: ${Object.entries(d.lines_by_language).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v.toLocaleString()}`).join(", ")}. <b>${d.workflows}</b> GitHub workflows, <b>${d.docs}</b> written documents.</p>` +
    d.folders.slice(0, 16).map(f => `<div class="rbar"><span class="rname">${f.folder}</span><span class="rtrack"><span style="width:${(100 * f.lines) / max}%"></span></span><span class="rnum">${f.lines.toLocaleString()} lines, ${f.files} files</span></div>`).join("");
  const list = $("#repoFiles"), q = $("#repoQ");
  const render = () => {
    const s = q.value.trim().toLowerCase();
    const rows = d.files.filter(f => !s || (f.path + " " + f.about).toLowerCase().includes(s)).slice(0, s ? 60 : 14);
    list.innerHTML = rows.map(f => `<li><a href="${GH}${f.path}">${f.path}</a><span>${f.lang}, ${f.lines} lines</span>${f.about ? `<em>${f.about.replace(/</g, "&lt;")}</em>` : ""}</li>`).join("") || "<li>No file matches.</li>";
  };
  q.addEventListener("input", render); render();
})();

/* ---------- held-out test result ---------- */
(async () => {
  const d = await getJSON("data/holdout_result.json");
  if (!d || !$("#holdoutResult")) return;
  $("#holdoutResult").innerHTML = d.html;
})();

/* ---------- chapter rail, index, reveals ---------- */
(() => {
  const secs = $$("main > section[id], main section[id]").filter((s, i, a) => a.indexOf(s) === i && s.querySelector("h2"));
  const rail = $("#rail");
  rail.innerHTML = secs.map(s => `<a href="#${s.id}" title="${s.querySelector("h2").textContent}"><span>${s.querySelector("h2").textContent}</span></a>`).join("");
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) $$("a", rail).forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id)); }), { rootMargin: "-45% 0px -50% 0px" });
  secs.forEach(s => io.observe(s));
  const atlas = $("#atlas"), body = $("#atlasBody"), q = $("#atlasQ");
  const GH = "https://github.com/PRITIDIPADAS/nakshatra-chronus/blob/main/";
  const items = [
    ["Sections", secs.map(s => [s.querySelector("h2").textContent, "#" + s.id])],
    ["Pages", [["The observatory, twelve chapters", "observatory.html"], ["Ten laboratories", "lab.html"], ["Causal sky twin", "causal-lab.html"], ["Research tools", "chronos-lab.html"], ["The story of one star, English and Bangla", "story.html"], ["Classroom kit", "classroom.html"], ["Slides", "deck.html"]]],
    ["Simulations", [["The blink", "#top"], ["Filter lab", "#physics"], ["Planet X parallax", "#sims"], ["A star hidden by a cloud", "#sims"], ["The forty second film", "#film"]]],
    ["Data", [["Practice-sky validation", "data/validation.json"], ["Seven real fields", "data/real_fields.json"], ["Per-injection diagnostics", "data/injection_diagnostics.json"], ["Whole sky tiles", "data/sky_tiles.json"], ["Real QR3 planting", "data/real_injection.json"], ["MATLAB filter curves", "data/lvf_curves.json"], ["Repository map", "data/repo_map.json"]]],
    ["Documents", [["README", GH + "README.md"], ["Methods", GH + "docs/METHODS.md"], ["Validation", GH + "docs/VALIDATION.md"], ["Limits", GH + "docs/LIMITS.md"], ["Reproduce every result", GH + "docs/REPRODUCE.md"], ["Preregistration", GH + "docs/PREREGISTRATION_SKY_AWARE_NOISE_2026-11-26.md"], ["Lupus III investigation", GH + "docs/SPHEREX_LUPUS_III_ZERO_RECOVERY_INVESTIGATION_2026-11-25.md"]]],
    ["Media", [["Demo video", "media/chronos_demo.mp4"], ["Slides as PDF", "media/CHRONOS_deck.pdf"], ["Slides as PowerPoint", "media/Nakshatra_CHRONOS.pptx"], ["All figures", "#gallery"]]],
    ["Code", [["Source on GitHub", "https://github.com/PRITIDIPADAS/nakshatra-chronus"], ["Real-data runs", "https://github.com/PRITIDIPADAS/nakshatra-chronus/actions"], ["MATLAB folder", "https://github.com/PRITIDIPADAS/nakshatra-chronus/tree/main/matlab"], ["Repository map", "#code"]]],
  ];
  const render = () => {
    const s = q.value.trim().toLowerCase();
    body.innerHTML = items.map(([h, list]) => { const l = list.filter(([t]) => !s || t.toLowerCase().includes(s)); return l.length ? `<div><h3>${h}</h3><ul>${l.map(([t, u]) => `<li><a href="${u}">${t}</a></li>`).join("")}</ul></div>` : ""; }).join("") || "<p>Nothing matches.</p>";
  };
  q.addEventListener("input", render); render();
  const open = () => { atlas.showModal(); q.focus(); };
  $("#atlasOpen").onclick = open; $("#atlasClose").onclick = () => atlas.close();
  body.addEventListener("click", e => { if (e.target.closest("a")) atlas.close(); });
  addEventListener("keydown", e => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); open(); } });
  if (!reduced) {
    const rv = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); rv.unobserve(e.target); } }), { threshold: 0.12 });
    $$("main section h2, .g, .sim, .eqs article, .flow li, figure, .callout").forEach(el => { el.classList.add("rv"); rv.observe(el); });
    $$(".hero-stats dt").forEach(dt => { const m = dt.textContent.match(/^([\d.]+)(.*)$/); if (!m) return; const end = +m[1], dec = (m[1].split(".")[1] || "").length, t0 = performance.now();
      const step = now => { const k = Math.min(1, (now - t0) / 1200); dt.textContent = (end * (1 - (1 - k) ** 3)).toFixed(dec) + m[2]; if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); });
  }
})();

/* ---------- every tool on this page ---------- */
(() => {
  const fr = $("#wbIframe");
  if (!fr) return;
  const tabs = $$(".wb-tabs [role=tab]");
  const pick = b => {
    tabs.forEach(t => t.setAttribute("aria-selected", String(t === b)));
    fr.src = b.dataset.src; fr.title = b.textContent;
    $("#wbNote").textContent = b.dataset.note; $("#wbOpen").href = b.dataset.src;
  };
  tabs.forEach(b => b.addEventListener("click", () => pick(b)));
  new IntersectionObserver((es, o) => es.forEach(e => { if (e.isIntersecting) { pick(tabs[0]); o.disconnect(); } }), { rootMargin: "300px" }).observe(fr);
  $("#wbFull").onclick = () => { const f = $("#wbFrame"); (document.fullscreenElement ? document.exitFullscreen() : f.requestFullscreen?.()); };
  addEventListener("hashchange", () => { const t = tabs.find(x => location.hash === "#tool-" + x.dataset.src.replace(".html", "")); if (t) { pick(t); $("#workbench").scrollIntoView(); } });
})();
