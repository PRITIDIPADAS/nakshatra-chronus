/* Small drawing kit for CHRONOS: images from bytes, axes, points, bars, heat maps. */
const PAL = {
  paper: [245, 240, 230], ink: [46, 42, 51], plum: [147, 122, 166], slate: [116, 137, 173], rose: [192, 138, 134], sage: [125, 154, 138],
  ochre: [196, 160, 97], brick: [181, 111, 94], mist: [167, 161, 154],
  H: { moving: "#7489ad", variable: "#c4a061", transient: "#937aa6", artefact: "#b56f5e", null: "#a7a19a" },
  M: { P: "#7d9a8a", D: "#7489ad", A: "#937aa6" },
  band: { 1: "#8f84c2", 2: "#7d9fd0", 3: "#6fb1ad", 4: "#9cb77a", 5: "#d3ad6a", 6: "#cf8a72" },
};
const HNAME = { moving: "H1 Moving", variable: "H2 Variable", transient: "H3 Transient", artefact: "H4 Artefact", null: "H5 No change or unknown" };
const FONT = '"EB Garamond", Garamond, Georgia, serif';

function lerp(a, b, t) { return a.map((v, i) => Math.round(v + (b[i] - v) * t)); }
const CMAP = {
  plate: (t) => lerp(PAL.paper, PAL.ink, Math.pow(t, 0.9)),
  seq: (t) => t < 0.5 ? lerp(PAL.paper, [214, 196, 226], t * 2) : lerp([214, 196, 226], [92, 70, 120], (t - 0.5) * 2),
  sage: (t) => lerp(PAL.paper, [70, 110, 92], t),
  noise: (t) => { const v = -3 + 33 * t; return lerp(PAL.paper, PAL.ink, Math.max(0, Math.min(1, Math.asinh(Math.max(v, 0) / 1.5) / Math.asinh(20)))); },
  div: (t) => t < 0.5 ? lerp([84, 106, 150], PAL.paper, Math.pow(t * 2, 1.6)) : lerp(PAL.paper, [168, 82, 74], Math.pow((t - 0.5) * 2, 0.6)),
};

function decode(img) {
  const s = atob(img.b64), a = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) a[i] = s.charCodeAt(i);
  return { w: img.w, h: img.h, d: a, lo: img.lo, hi: img.hi };
}

const _imgCache = new WeakMap();
/* Render bytes to a small canvas, north up (row 0 of the array at the bottom). */
function bitmap(img, cmap = "plate") {
  let per = _imgCache.get(img);
  if (per && per[cmap]) return per[cmap];
  const D = img.d ? img : decode(img), c = document.createElement("canvas");
  c.width = D.w; c.height = D.h;
  const g = c.getContext("2d"), id = g.createImageData(D.w, D.h), f = CMAP[cmap];
  for (let y = 0; y < D.h; y++) for (let x = 0; x < D.w; x++) {
    const v = D.d[y * D.w + x], o = ((D.h - 1 - y) * D.w + x) * 4;
    if (v === 0) { id.data[o] = 236; id.data[o + 1] = 229; id.data[o + 2] = 214; id.data[o + 3] = 255; continue; }
    const rgb = f((v - 1) / 254);
    id.data[o] = rgb[0]; id.data[o + 1] = rgb[1]; id.data[o + 2] = rgb[2]; id.data[o + 3] = 255;
  }
  g.putImageData(id, 0, 0);
  if (!per) { per = {}; _imgCache.set(img, per); }
  per[cmap] = c;
  return c;
}

/* Draw an image into a canvas. view = {zoom, cx, cy} in array pixels. Returns a mapper from array x, y to canvas. */
function drawImage(cv, img, cmap = "plate", view = {}) {
  const g = cv.getContext("2d"), b = bitmap(img, cmap), z = view.zoom || 1, n = img.w;
  const span = n / z, cx = view.cx ?? (n - 1) / 2, cy = view.cy ?? (n - 1) / 2;
  let x0 = Math.min(Math.max(cx - span / 2 + 0.5, 0), n - span), y0 = Math.min(Math.max(cy - span / 2 + 0.5, 0), n - span);
  const s = cv.width / span;
  g.imageSmoothingEnabled = false;
  g.clearRect(0, 0, cv.width, cv.height);
  g.drawImage(b, x0, (n - y0 - span), span, span, 0, 0, cv.width, cv.height);
  const map = (x, y) => [(x + 0.5 - x0) * s, (n - (y + 0.5) - (n - y0 - span)) * s];
  map.inv = (px, py) => [px / s + x0 - 0.5, n - (py / s + (n - y0 - span)) - 0.5];
  map.s = s;
  return map;
}

function num(v, k = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  if (typeof v !== "number") return String(v);
  const a = Math.abs(v);
  const t = a >= 1000 ? v.toFixed(0) : a >= 100 ? v.toFixed(Math.max(0, k - 2)) : v.toFixed(k);
  return t;
}
function trim(t) { return t.includes(".") ? t.replace(/\.?0+$/, "") : t; }
function pct(v, k = 0) { return v === null || v === undefined ? "n/a" : (100 * v).toFixed(k) + " percent"; }

/* Axes. box = [left, top, width, height]. Returns {x, y} scale functions. */
function axes(cv, xr, yr, o = {}) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height;
  const L = o.left ?? 52, T = o.top ?? 14, R = o.right ?? 14, B = o.bottom ?? 40;
  if (!o.keep) g.clearRect(0, 0, W, H);
  const lx = o.logx, ly = o.logy;
  const tx = (v) => lx ? Math.log10(v) : v, ty = (v) => ly ? Math.log10(v) : v;
  const [x0, x1] = xr.map(tx), [y0, y1] = yr.map(ty);
  const X = (v) => L + (tx(v) - x0) / (x1 - x0 || 1) * (W - L - R);
  const Y = (v) => H - B - (ty(v) - y0) / (y1 - y0 || 1) * (H - T - B);
  g.strokeStyle = "#ddd3c2"; g.fillStyle = "#5d5763"; g.lineWidth = 1; g.font = `14px ${FONT}`;
  const ticks = (a0, b0, n, log) => {
    const a = Math.min(a0, b0), b = Math.max(a0, b0);
    if (log) { const out = []; for (let e = Math.floor(a); e <= Math.ceil(b); e++) out.push(Math.pow(10, e)); return out.filter((v) => Math.log10(v) >= a - 1e-9 && Math.log10(v) <= b + 1e-9); }
    const step = Math.pow(10, Math.floor(Math.log10((b - a) / n || 1))), m = [1, 2, 5, 10].find((k) => (b - a) / (k * step) <= n) * step;
    const out = []; for (let v = Math.ceil(a / m) * m; v <= b + 1e-9; v += m) out.push(+v.toFixed(10)); return out;
  };
  g.beginPath();
  for (const v of ticks(x0, x1, o.nx || 6, lx)) { const p = X(v); g.moveTo(p, T); g.lineTo(p, H - B); g.fillText(o.fx ? o.fx(v) : trim(num(v, Math.abs(v) < 10 ? 2 : 0)) || "0", p - 8, H - B + 16); }
  for (const v of ticks(y0, y1, o.ny || 5, ly)) { const p = Y(v); g.moveTo(L, p); g.lineTo(W - R, p); g.fillText(o.fy ? o.fy(v) : trim(num(v, Math.abs(v) < 10 ? 2 : 0)) || "0", 4, p + 4); }
  g.stroke();
  g.fillStyle = "#2e2a33"; g.font = `italic 15px ${FONT}`;
  if (o.xl) g.fillText(o.xl, L + (W - L - R) / 2 - g.measureText(o.xl).width / 2, H - 6);
  if (o.yl) { g.save(); g.translate(14, T + (H - T - B) / 2 + g.measureText(o.yl).width / 2); g.rotate(-Math.PI / 2); g.fillText(o.yl, 0, 0); g.restore(); }
  return { X, Y, g, L, T, R, B, W, H };
}

function dot(g, x, y, r, fill, stroke) { g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); if (fill) { g.fillStyle = fill; g.fill(); } if (stroke) { g.strokeStyle = stroke; g.lineWidth = 1.2; g.stroke(); } }
function errbar(g, x, y0, y1, color) { g.strokeStyle = color; g.lineWidth = 1.2; g.beginPath(); g.moveTo(x, y0); g.lineTo(x, y1); g.stroke(); }
function polyline(g, pts, color, w = 1.5, dash) { g.strokeStyle = color; g.lineWidth = w; g.setLineDash(dash || []); g.beginPath(); pts.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.stroke(); g.setLineDash([]); }
function label(g, text, x, y, color = "#2e2a33", size = 14, italic = false) { g.fillStyle = color; g.font = `${italic ? "italic " : ""}${size}px ${FONT}`; g.fillText(text, x, y); }
function ellipse(g, x, y, rx, ry, color) { g.strokeStyle = color; g.lineWidth = 1.2; g.beginPath(); g.ellipse(x, y, Math.max(rx, 0.5), Math.max(ry, 0.5), 0, 0, 2 * Math.PI); g.stroke(); }

/* Horizontal bars with optional intervals. rows = [{label, v, lo, hi, color}] */
function hbars(cv, rows, o = {}) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, L = o.left ?? 150, R = 50, n = rows.length;
  g.clearRect(0, 0, W, H);
  const max = o.max ?? Math.max(...rows.map((r) => r.hi ?? r.v), 1e-9), bh = Math.min(26, (H - 20) / n - 6);
  g.font = `15px ${FONT}`;
  rows.forEach((r, i) => {
    const y = 10 + i * (bh + 6), w = (W - L - R) * Math.max(r.v, 0) / max;
    g.fillStyle = "#2e2a33"; g.fillText(r.label, 4, y + bh * 0.72);
    g.fillStyle = r.color || "#937aa6"; g.globalAlpha = 0.85; g.fillRect(L, y, w, bh); g.globalAlpha = 1;
    if (r.lo !== undefined) { const a = L + (W - L - R) * r.lo / max, b = L + (W - L - R) * r.hi / max; g.strokeStyle = "#2e2a33"; g.beginPath(); g.moveTo(a, y + bh / 2); g.lineTo(b, y + bh / 2); g.moveTo(a, y + 3); g.lineTo(a, y + bh - 3); g.moveTo(b, y + 3); g.lineTo(b, y + bh - 3); g.stroke(); }
    g.fillStyle = "#5d5763"; g.fillText(r.text ?? num(r.v), L + w + 6, y + bh * 0.72);
  });
  if (o.line !== undefined) { const x = L + (W - L - R) * o.line / max; g.strokeStyle = "#b56f5e"; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(x, 4); g.lineTo(x, H - 4); g.stroke(); g.setLineDash([]); }
}

/* Heat map of a matrix with row and column labels. */
function heat(cv, M, rows, cols, o = {}) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, L = o.left ?? 110, T = o.top ?? 26, cw = (W - L - 6) / cols.length, ch = (H - T - 6) / rows.length;
  g.clearRect(0, 0, W, H);
  const max = o.max ?? Math.max(...M.flat(), 1e-9);
  g.font = `14px ${FONT}`;
  cols.forEach((c, j) => { g.fillStyle = "#5d5763"; g.fillText(c, L + j * cw + 4, T - 8); });
  rows.forEach((r, i) => {
    g.fillStyle = "#2e2a33"; g.fillText(r, 4, T + i * ch + ch * 0.62);
    cols.forEach((c, j) => {
      const v = M[i][j], t = Math.min(1, v / max), rgb = CMAP.seq(t);
      g.fillStyle = `rgb(${rgb})`; g.fillRect(L + j * cw + 1, T + i * ch + 1, cw - 2, ch - 2);
      g.fillStyle = t > 0.55 ? "#fbf8f2" : "#2e2a33"; g.fillText(o.fmt ? o.fmt(v, i, j) : String(v), L + j * cw + cw / 2 - 10, T + i * ch + ch * 0.62);
    });
  });
}
