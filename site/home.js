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
