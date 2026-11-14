/* Nakshatra CHRONOS observatory page. Works with the full app (python run.py) or as a static site with prepared fields. */
const STATIC = window.CHRONOS_STATIC === true;
const $ = (s) => document.querySelector(s);
const el = (tag, attrs = {}, html = "") => { const e = document.createElement(tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); e.innerHTML = html; return e; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ST = { D: null, V: null, fields: [], sel: null, t: 0, timer: null, view: { zoom: 1 }, pick: null, micro: { p: 0, l: 0 }, prior: null };
const ARR = { 1: "0.75 to 1.11", 2: "1.11 to 1.64", 3: "1.64 to 2.42", 4: "2.42 to 3.82", 5: "3.82 to 4.42", 6: "4.42 to 5.00" };

async function getJSON(u, opt) {
  const r = await fetch(u, opt);
  if (!r.ok) { let t = await r.text(); try { t = JSON.parse(t).detail || t; } catch (e) { } throw new Error(String(t).slice(0, 400)); }
  return r.json();
}
function status(t, busy) { $("#status").textContent = t; document.body.classList.toggle("loading", !!busy); }

/* ------------------------------------------------------------ URL state */
function readHash() { const h = new URLSearchParams(location.hash.slice(1)); return Object.fromEntries(h.entries()); }
function writeHash(extra = {}) {
  const D = ST.D; if (!D) return;
  const p = new URLSearchParams();
  const m = D.meta || {};
  if (m.key && !(m.ra != null && !ST.fields.find((f) => f.key === m.key))) p.set("field", m.key);
  if (m.ra != null) { p.set("ra", (+m.ra).toFixed(5)); p.set("dec", (+m.dec).toFixed(5)); }
  p.set("mode", m.mode || "sim"); p.set("fov", m.size || 49);
  if (ST.sel) p.set("cand", ST.sel);
  Object.entries(extra).forEach(([k, v]) => p.set(k, v));
  history.replaceState(null, "", "#" + p.toString());
}

/* ------------------------------------------------------------ start */
async function boot() {
  try { ST.fields = await getJSON(STATIC ? "data/fields/index.json" : "api/fields"); } catch (e) { ST.fields = []; }
  const sel = $("#field");
  ST.fields.forEach((f) => sel.append(el("option", { value: f.key }, esc(f.name + (f.kind === "field" ? "" : "  ·  " + (f.traits || []).join(", "))))));
  if (STATIC) {
    $("#mode").innerHTML = '<option value="sim">Practice sky (prepared)</option>';
    $("#fov").innerHTML = '<option value="49">5.0 arcmin (prepared)</option>';
    $("#goNote").textContent = "This hosted page holds prepared practice fields. Run the full app (python run.py) for any coordinate, any field of view, and live SPHEREx data.";
  }
  try { ST.V = await getJSON("data/validation.json"); } catch (e) { ST.V = null; }
  const h = readHash();
  if (h.field) sel.value = h.field;
  if (h.mode && !STATIC) $("#mode").value = h.mode;
  if (h.fov && !STATIC) $("#fov").value = h.fov;
  wire();
  renderPlanet();
  renderMethods();
  await investigate(h.ra ? { ra: +h.ra, dec: +h.dec } : null, h.cand);
}

function wire() {
  $("#go").onclick = () => {
    const q = $("#coord").value.trim();
    if (q) { const c = parseCoords(q); if (!c) return status("Could not read that position. Try 269.448 4.739 or 17h57m48s +04d44m36s."); if (c.key) { $("#field").value = c.key; return investigate(); } return investigate(c); }
    investigate();
  };
  $("#coord").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#go").click(); });
  $("#askForm").onsubmit = (e) => { e.preventDefault(); ask($("#ask").value); };
  ["#layer", "#tslider", "#ovCand", "#ovCat", "#ovWise", "#zoom"].forEach((s) => $(s).addEventListener("input", () => { if (s === "#layer") setupSlider(); if (s === "#zoom") ST.view.zoom = +$("#zoom").value; drawSky(); }));
  $("#play").onclick = () => togglePlay();
  $("#sky").addEventListener("click", skyClick);
  $("#cubeTurn").addEventListener("input", drawCube3);
  $("#exag").addEventListener("input", drawMotionMap);
  $("#pairSel").addEventListener("change", () => { ST.micro.p = +$("#pairSel").value; ST.micro.l = 0; renderMicro(); });
  const links = [...document.querySelectorAll(".rail a")];
  const io = new IntersectionObserver((es) => es.forEach((en) => { if (en.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + en.target.id)); }), { rootMargin: "-40% 0px -55% 0px" });
  document.querySelectorAll(".chapter").forEach((c) => io.observe(c));
}

async function investigate(coords, cand) {
  const key = $("#field").value || (ST.fields[0] || {}).key || "demo", mode = $("#mode").value, size = +$("#fov").value;
  stopPlay();
  status(mode === "live" ? "Asking the IRSA archive for every SPHEREx exposure here, then running the investigation. This can take minutes." :
    "Rendering the practice sky, then running three detectors, the engine, every challenge and every counterfactual.", true);
  try {
    let D;
    if (STATIC) {
      if (coords) {
        const near = ST.fields.find((f) => f.ra != null && Math.hypot((f.ra - coords.ra) * Math.cos(f.dec * Math.PI / 180), f.dec - coords.dec) < 0.2);
        if (!near) { status(`This hosted page holds prepared fields only. Position ${coords.ra.toFixed(4)}, ${coords.dec.toFixed(4)} needs the full app: python run.py. The practice sky can be made for any position there, and live mode reads the real archive.`); return; }
        $("#field").value = near.key;
      }
      D = await getJSON(`data/fields/${$("#field").value}.json`);
    } else {
      const q = new URLSearchParams({ key, mode, size, fov: (size * 6.15 / 3600).toFixed(3) });
      if (coords) { q.set("ra", coords.ra); q.set("dec", coords.dec); q.set("key", "coords"); }
      D = await getJSON("api/investigate?" + q.toString());
    }
    ST.D = D; ST.sel = null; ST.pick = null; ST.view = { zoom: +$("#zoom").value || 1 };
    render();
    const want = cand && D.candidates.find((c) => c.id === cand) ? cand : (D.candidates[0] || {}).id;
    if (want) selectCand(want, false);
    else { $("#dossier").innerHTML = '<div class="card s6">No candidate in this field. Every method looked and found no change above its threshold.</div>'; $("#dosId").textContent = ""; $("#dosStatus").textContent = "No candidate."; }
    status(`${D.meta.name}. ${D.field.exposures.length} exposures in ${D.visits} visits on ${D.arrays.length} arrays. ${D.candidates.length} candidates. ${D.meta.label === "SIMULATION" ? "Practice sky: the truth is known and hidden until you ask." : "Real SPHEREx data."}`);
    writeHash();
  } catch (e) {
    status("The investigation stopped: " + e.message, false);
  } finally { document.body.classList.remove("loading"); }
}

function render() {
  const D = ST.D;
  $("#stamp").textContent = D.meta.label || "SIMULATION";
  $("#stamp").classList.toggle("real", D.meta.label !== "SIMULATION");
  $("#railnote").innerHTML = `<b>${esc(D.meta.name)}</b><br>${D.candidates.length} candidates<br>centre ${num(D.center[0], 4)}, ${num(D.center[1], 4)}`;
  setupSlider(); drawSky(); renderMeta(); renderPlane(); renderGuardian(); renderMicroSel(); renderCands(); drawPop(); drawMotionMap(); renderValidation(); renderQuestions(); renderCitizen(); renderArchive(); renderBox();
}

/* ------------------------------------------------------------ I. sky and time */
function frames() {
  const D = ST.D, L = $("#layer").value;
  if (L === "white") return Object.keys(D.field.maps.white).sort((a, b) => a - b).map((k) => ({ img: D.field.maps.white[k], cmap: "plate", visit: +k }));
  if (/^a\d$/.test(L)) { const d = +L[1]; return Array.from({ length: D.visits }, (_, q) => ({ img: D.field.maps.coadd[`${q + 1}_${d}`], cmap: "plate", visit: q + 1, det: d })).filter((f) => f.img); }
  if (L === "cube") return D.field.exposures.map((e, i) => ({ ...e, i, img: D.field.maps.cube[i], cmap: "noise" })).sort((a, b) => a.day - b.day);
  const one = { deep: ["deep", "plate"], anomaly: ["anomaly", "seq"], coverage: ["coverage", "sage"], depth: ["depth", "seq"], pos: ["pos_err", "seq"] }[L];
  return [{ img: D.field.maps[one[0]], cmap: one[1], still: L }];
}
function setupSlider() { const f = frames(); const s = $("#tslider"); s.max = Math.max(0, f.length - 1); s.value = Math.min(+s.value, f.length - 1); s.disabled = f.length < 2; }
function drawSky() {
  const D = ST.D; if (!D) return;
  const fr = frames(), f = fr[+$("#tslider").value] || fr[0];
  if (!f || !f.img) return;
  const cv = $("#sky"), map = drawImage(cv, f.img, f.cmap, ST.view), g = cv.getContext("2d");
  ST.map = map;
  const t0 = D.mjd_visits[0];
  let txt = "";
  if (f.visit) txt = `visit ${f.visit} · day ${num(D.mjd_visits[f.visit - 1] - t0, 0)}` + (f.det ? ` · array ${f.det}` : "");
  else if (f.i !== undefined) txt = `exposure ${f.i + 1} · array ${f.det} · ${num(f.lam, 3)} micron · day ${num(f.day, 1)}`;
  else txt = $("#layer").selectedOptions[0].textContent;
  $("#elapsed").textContent = txt;
  if ($("#ovCat").checked) for (const s of D.field.catalog) { const [x, y] = map(s.x, s.y); g.strokeStyle = s.moving ? "#c4a061" : "rgba(125,154,138,.9)"; g.lineWidth = 1; g.beginPath(); g.moveTo(x - 6, y); g.lineTo(x - 3, y); g.moveTo(x + 3, y); g.lineTo(x + 6, y); g.moveTo(x, y - 6); g.lineTo(x, y - 3); g.moveTo(x, y + 3); g.lineTo(x, y + 6); g.stroke(); }
  if ($("#ovWise").checked) for (const s of D.field.overlay || []) { const [x, y] = map(s.x ?? 0, s.y ?? 0); g.strokeStyle = "#7489ad"; g.strokeRect(x - 5, y - 5, 10, 10); }
  if ($("#ovCand").checked) for (const c of D.candidates) {
    const [x, y] = map(c.x, c.y), col = PAL.H[c.post.verdict || "null"];
    g.strokeStyle = col; g.lineWidth = c.id === ST.sel ? 2.6 : 1.6; g.beginPath(); g.arc(x, y, 3.2 * map.s / 2 + 4, 0, 2 * Math.PI); g.stroke();
    label(g, c.id, x + 3.2 * map.s / 2 + 5, y - 4, col, 14);
  }
  if (ST.pick) { const [x, y] = map(ST.pick[0], ST.pick[1]); g.strokeStyle = "#2e2a33"; g.setLineDash([3, 3]); g.strokeRect(x - 7, y - 7, 14, 14); g.setLineDash([]); }
  drawKymo(); drawCube3();
}
function togglePlay() { if (ST.timer) return stopPlay(); const s = $("#tslider"); $("#play").setAttribute("aria-pressed", "true"); $("#play").textContent = "Stop"; ST.timer = setInterval(() => { s.value = (+s.value + 1) % (+s.max + 1); drawSky(); }, $("#layer").value === "cube" ? 260 : 700); }
function stopPlay() { clearInterval(ST.timer); ST.timer = null; $("#play").setAttribute("aria-pressed", "false"); $("#play").textContent = "Blink"; }
function valAt(img, x, y) { if (!img) return null; const D = img.d ? img : (img._dec ||= decode(img)), v = D.d[Math.round(y) * D.w + Math.round(x)]; return v ? D.lo + (v - 1) / 254 * (D.hi - D.lo) : null; }
function skyToRaDec(x, y) { const D = ST.D, c0 = (D.n - 1) / 2, s = D.pixel_arcsec / 3600; return [D.center[0] - (x - c0) * s / Math.cos(D.center[1] * Math.PI / 180), D.center[1] + (y - c0) * s]; }
function skyClick(ev) {
  const D = ST.D; if (!D || !ST.map) return;
  const r = ev.target.getBoundingClientRect(), [x, y] = ST.map.inv((ev.clientX - r.left) * ev.target.width / r.width, (ev.clientY - r.top) * ev.target.height / r.height);
  if (x < 0 || y < 0 || x > D.n - 1 || y > D.n - 1) return;
  ST.pick = [x, y];
  const near = D.candidates.map((c) => [Math.hypot(c.x - x, c.y - y), c]).sort((a, b) => a[0] - b[0])[0];
  const cat = D.field.catalog.map((s) => [Math.hypot(s.x - x, s.y - y), s]).sort((a, b) => a[0] - b[0])[0];
  const [ra, dec] = skyToRaDec(x, y), M = D.field.maps;
  const depth = valAt(M.depth, x, y), cov = valAt(M.coverage, x, y), pe = valAt(M.pos_err, x, y), an = valAt(M.anomaly, x, y);
  $("#pix").innerHTML = `<h3>Pixel reading</h3><table>
    <tr><td>Grid position</td><td>x ${num(x, 1)}, y ${num(y, 1)}</td></tr><tr><td>Sky position</td><td>RA ${num(ra, 5)}, Dec ${num(dec, 5)}</td></tr>
    <tr><td>Exposures covering</td><td>${cov == null ? "none" : Math.round(cov)} of ${D.field.exposures.length}</td></tr>
    <tr><td>Depth, one visit</td><td>${depth == null ? "n/a" : num(Math.pow(10, depth), 0) + " microJy at 5 sigma"}</td></tr>
    <tr><td>Position error for 300 microJy</td><td>${pe == null ? "n/a" : num(pe, 3) + " pixel"}</td></tr>
    <tr><td>Anomaly rank</td><td>${an == null ? "n/a" : num(an, 3)}</td></tr>
    <tr><td>Nearest catalog source</td><td>${cat && cat[0] < 3 ? esc(cat[1].name || "catalog") + ", " + num(cat[0], 2) + " pixel" : "none within 3 pixels"}</td></tr>
    <tr><td>Nearest candidate</td><td>${near ? `<a href="#ch-dossier" data-c="${near[1].id}">${near[1].id}</a>, ${num(near[0], 1)} pixel` : "none"}</td></tr></table>`;
  $("#pix").querySelector("a[data-c]")?.addEventListener("click", (e) => selectCand(e.target.dataset.c));
  if (near && near[0] < 2.5) selectCand(near[1].id, false); else drawSky();
}
function kymoPoint() { if (ST.pick) return ST.pick; const c = cand(); return c ? [c.x, c.y] : null; }
function drawKymo() {
  const D = ST.D, cv = $("#kymo"), g = cv.getContext("2d"); g.clearRect(0, 0, cv.width, cv.height);
  const p = kymoPoint(); if (!p) return;
  const ex = D.field.exposures.map((e, i) => ({ ...e, i })).sort((a, b) => a.day - b.day), half = 10, yy = Math.round(p[1]), x0 = Math.round(p[0]) - half;
  const W = 2 * half + 1, H = ex.length, c = document.createElement("canvas"); c.width = W; c.height = H;
  const cg = c.getContext("2d"), id = cg.createImageData(W, H);
  ex.forEach((e, r) => {
    const im = D.field.maps.cube[e.i], dd = im._dec ||= decode(im);
    for (let k = 0; k < W; k++) {
      const x = x0 + k, v = (x >= 0 && x < dd.w && yy >= 0 && yy < dd.h) ? dd.d[yy * dd.w + x] : 0, o = (r * W + k) * 4;
      const val = v ? dd.lo + (v - 1) / 254 * (dd.hi - dd.lo) : 0, t = Math.max(0, Math.min(1, Math.asinh(Math.max(val, 0) / 2) / Math.asinh(15)));
      const rgb = v ? CMAP.plate(t) : [236, 229, 214]; id.data[o] = rgb[0]; id.data[o + 1] = rgb[1]; id.data[o + 2] = rgb[2]; id.data[o + 3] = 255;
    }
  });
  cg.putImageData(id, 0, 0);
  g.imageSmoothingEnabled = false; const L = 40; g.drawImage(c, L, 6, cv.width - L - 6, cv.height - 30);
  let prev = null; g.font = `13px ${FONT}`;
  ex.forEach((e, r) => { if (e.visit !== prev) { const y = 6 + r * (cv.height - 30) / H; g.strokeStyle = "#937aa6"; g.beginPath(); g.moveTo(L, y); g.lineTo(cv.width - 6, y); g.stroke(); label(g, "visit " + e.visit, 0, y + 12, "#5d5763", 13); prev = e.visit; } });
  label(g, "time runs down · x from " + x0 + " to " + (x0 + W - 1) + " at y " + yy, L, cv.height - 8, "#5d5763", 13, true);
}
function drawCube3() {
  const D = ST.D, cv = $("#cube3"), g = cv.getContext("2d"); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height);
  if (!D) return;
  const keys = Object.keys(D.field.maps.white).sort((a, b) => a - b), turn = +$("#cubeTurn").value / 100, n = D.n, s = 150 / n, dz = (cv.height - 120) / Math.max(1, keys.length - 1);
  const c = cand();
  keys.slice().reverse().forEach((k, jr) => {
    const j = keys.length - 1 - jr, b = bitmap(D.field.maps.white[k], "plate");
    g.setTransform(s, s * 0.32 * turn, -s * 0.9 * turn, s * 0.5, 40 + 60 * turn, cv.height - 95 - j * dz);
    g.globalAlpha = 0.92; g.drawImage(b, 0, 0); g.globalAlpha = 1; g.strokeStyle = "#937aa6"; g.lineWidth = 1 / s; g.strokeRect(0, 0, n, n);
    g.setTransform(1, 0, 0, 1, 0, 0); label(g, `visit ${k} · day ${num(D.mjd_visits[k - 1] - D.mjd_visits[0], 0)}`, 218, cv.height - 72 - j * dz, "#5d5763", 13);
  });
  if (c) {
    const pts = keys.map((k, j) => {
      const tr = (c.dossier.motion.track || []).find((t) => t.visit === +k) || { x: c.x, y: c.y }, X = tr.x + 0.5, Y = n - tr.y - 0.5;
      return [40 + 60 * turn + s * X - s * 0.9 * turn * Y, cv.height - 95 - j * dz + s * 0.32 * turn * X + s * 0.5 * Y];
    });
    polyline(g, pts, PAL.H[c.post.verdict || "null"], 2); pts.forEach(([x, y]) => dot(g, x, y, 3, PAL.H[c.post.verdict || "null"]));
  }
  g.setTransform(1, 0, 0, 1, 0, 0); label(g, "time rises · each layer is one visit", 8, 16, "#5d5763", 13, true);
}
function renderMeta() {
  const D = ST.D, rows = D.field.exposures.map((e) => `<tr><td>${e.i + 1}</td><td>${esc(e.id)}</td><td>${e.visit}</td><td>${num(e.day, 2)}</td><td>${e.det}</td><td>${num(e.lam, 4)}</td><td>${num(e.bw, 4)}</td><td>${esc(e.rel)}</td><td>${num(e.noise_k, 2)}</td><td>${e.anchors}</td><td>${num(e.gain, 3)}</td><td>${Object.entries(e.flags).map(([k, v]) => `${esc(k)} ${v}`).join(", ") || "none"}</td><td>${num(100 * e.coverage, 0)}</td><td>${esc((e.notes || []).join("; "))}</td></tr>`).join("");
  $("#metaTable").innerHTML = `<table><tr><th>#</th><th>Exposure</th><th>Visit</th><th>Day</th><th>Array</th><th>Micron</th><th>Width</th><th>Release</th><th>Noise factor</th><th>Anchors</th><th>Star gain</th><th>Flags in cutout</th><th>Coverage %</th><th>Notes</th></tr>${rows}</table>
  <p class="small muted">MJD of each exposure is in the black box record. Noise factor: measured noise over the VARIANCE plane. Anchors: catalog stars used to fix the position. Star gain: brightness of the catalog stars against their fair partners.</p>`;
}

/* ------------------------------------------------------------ II. fair pairs */
function renderPlane() {
  const D = ST.D, cv = $("#plane"), ex = D.field.exposures;
  const days = ex.map((e) => e.day), A = axes(cv, [Math.min(...days) - 10, Math.max(...days) + 10], [0.72, 5.2], { logy: true, xl: "days since the first exposure", yl: "wavelength (micron)", fy: (v) => num(v, 1), ny: 6 });
  const g = A.g, groups = {};
  ex.forEach((e) => { const k = `${e.visit}_${e.det}`; (groups[k] ||= []).push(e); });
  const mid = (k) => { const v = groups[k]; return v ? [v.reduce((s, e) => s + e.day, 0) / v.length, Math.exp(v.reduce((s, e) => s + Math.log(e.lam), 0) / v.length)] : null; };
  let fair = 0, all = 0;
  for (const p of D.field.pairs) {
    all++; const a = mid(`${p.q1 + 1}_${p.det}`), b = mid(`${p.q2 + 1}_${p.det}`); if (!a || !b) continue;
    if (p.fair && p.release_same) { fair++; polyline(g, [[A.X(a[0]), A.Y(a[1])], [A.X(b[0]), A.Y(b[1])]], "rgba(125,154,138,.75)", 1.4); }
  }
  ex.forEach((e) => dot(g, A.X(e.day), A.Y(e.lam), 3.4, PAL.band[e.det], e.rel !== D.field.guardian.common_release ? "#b56f5e" : null));
  $("#planeNote").innerHTML = `${ex.length} exposures. ${all} visit pairs on the same array, of which <b>${fair}</b> are fair (mean color offset at most ${D.thresholds.fair_coadd} of a channel, one release). Red rings: exposures from another release. Surveys 3 and 4 sit half a channel away from 1 and 2, so visits 1 and 3 can not be compared directly.`;
}
function renderGuardian() {
  const G = ST.D.field.guardian;
  $("#guardian").innerHTML = `<table><tr><th>Visit</th><th>Array</th><th>Release</th><th>Star gain</th><th>z</th><th>Verdict</th></tr>${G.rows.map((r) => `<tr class="${r.warn ? "warn" : ""}"><td>${r.visit}</td><td>${r.det}</td><td>${esc(r.release)}</td><td>${num(r.gain, 3)} ± ${num(r.gain_err, 3)}</td><td>${num(r.z, 1)}</td><td>${esc(r.verdict)}</td></tr>`).join("")}</table>`;
}

/* ------------------------------------------------------------ III. microscope */
function renderMicroSel() {
  const M = ST.D.field.microscope, s = $("#pairSel");
  s.innerHTML = M.map((L, i) => `<option value="${i}">Visit ${L.q1} and ${L.q2}, array ${L.det}, ${L.fair ? "fair" : "NOT fair, color offset " + num(L.color, 2)}</option>`).join("");
  ST.micro = { p: 0, l: 0 }; renderMicro();
}
function renderMicro() {
  const D = ST.D, L = D.field.microscope[ST.micro.p]; if (!L) { $("#microNote").textContent = "No pair to show."; return; }
  const ia = D.field.exposures.findIndex((e) => e.id === L.a), ib = D.field.exposures.findIndex((e) => e.id === L.b);
  if (ia >= 0) drawImage($("#mA"), D.field.maps.cube[ia], "noise");
  if (ib >= 0) drawImage($("#mB"), D.field.maps.cube[ib], "noise");
  $("#layerBtns").innerHTML = L.layers.map((x, i) => `<button role="tab" aria-selected="${i === ST.micro.l}" data-i="${i}">${i + 1}. ${esc(x.key)}</button>`).join("");
  $("#layerBtns").querySelectorAll("button").forEach((b) => b.onclick = () => { ST.micro.l = +b.dataset.i; renderMicro(); });
  const ly = L.layers[ST.micro.l], map = drawImage($("#mZ"), ly.img, "div");
  const g = $("#mZ").getContext("2d");
  for (const c of D.candidates) { const [x, y] = map(c.x, c.y); g.strokeStyle = "#2e2a33"; g.lineWidth = 1; g.beginPath(); g.arc(x, y, 8, 0, 2 * Math.PI); g.stroke(); }
  $("#mZcap").textContent = `Layer ${ST.micro.l + 1}: significance, slate fainter, rose brighter`;
  hbars($("#funnel"), L.layers.map((x, i) => ({ label: `${i + 1}. ${x.key}`, v: x.count, color: i === ST.micro.l ? "#937aa6" : "#c9bcd3", text: String(x.count) })), { left: 120 });
  $("#microNote").innerHTML = `<b>${esc(ly.label)}</b> ${ly.count} spots above 5 sigma. ${L.fair ? "" : "This pair is not fair: the two exposures see different colors, so stars change brightness with no change in the sky. CHRONOS shows it as a warning and never uses it for detection."} Exposure A ${esc(L.a)}, exposure B ${esc(L.b)}, color offset ${num(L.color, 2)} of a channel.`;
}

/* ------------------------------------------------------------ IV. candidates */
function hb(p) { return `<span class="hbar" title="${Object.entries(p || {}).map(([k, v]) => HNAME[k] + " " + Math.round(100 * v) + " percent").join(", ")}">${["moving", "variable", "transient", "artefact", "null"].map((k) => `<span style="width:${100 * (p?.[k] || 0)}%;background:${PAL.H[k]}"></span>`).join("")}</span>`; }
function badges(m) { return ["P", "D", "A"].map((k) => `<span class="badge ${m.includes(k) ? k : "off"}" title="${{ P: "catalog", D: "difference", A: "anomaly" }[k]} method">${k}</span>`).join(""); }
function verdictName(c) { return c.post.unknown ? "H5 Unknown" : HNAME[c.post.verdict || "null"]; }
function cand(id) { return ST.D?.candidates.find((c) => c.id === (id || ST.sel)); }
function renderCands(filter) {
  const D = ST.D, list = D.candidates.slice().sort((a, b) => (b.dossier.oracle.priority || 0) - (a.dossier.oracle.priority || 0)).filter(filter || (() => true));
  $("#candTable").innerHTML = `<table><tr><th>ID</th><th>RA, Dec</th><th>Methods</th><th>Five hypotheses</th><th>Verdict</th><th>Robust</th><th>Status</th></tr>${list.map((c) => `<tr class="click ${c.id === ST.sel ? "sel" : ""}" data-c="${c.id}"><td><b>${c.id}</b></td><td>${num(c.ra, 5)}<br>${num(c.dec, 5)}</td><td>${badges(c.methods)}</td><td>${hb(c.post.probs)}</td><td style="color:${PAL.H[c.post.verdict || "null"]}">${verdictName(c)}</td><td>${c.dossier.robustness.survived}/${c.dossier.robustness.total}</td><td class="small">${esc(c.dossier.status)}</td></tr>`).join("")}</table>
  <p class="legend small"><span><i style="background:${PAL.H.moving}"></i>H1 moving</span><span><i style="background:${PAL.H.variable}"></i>H2 variable</span><span><i style="background:${PAL.H.transient}"></i>H3 transient</span><span><i style="background:${PAL.H.artefact}"></i>H4 artefact</span><span><i style="background:${PAL.H.null}"></i>H5 no change or unknown</span></p>`;
  $("#candTable").querySelectorAll("tr[data-c]").forEach((r) => r.onclick = () => selectCand(r.dataset.c));
}
function drawPop() {
  const D = ST.D, cv = $("#popmap"), map = drawImage(cv, D.field.maps.deep, "plate"), g = cv.getContext("2d");
  g.globalAlpha = 0.25; g.drawImage(bitmap(D.field.maps.coverage, "sage"), 0, 0, cv.width, cv.height); g.globalAlpha = 1;
  const counts = {};
  for (const c of D.candidates) {
    const v = c.post.unknown ? "null" : c.post.verdict || "null"; counts[v] = (counts[v] || 0) + 1;
    const [x, y] = map(c.x, c.y); g.fillStyle = PAL.H[v]; g.strokeStyle = "#2e2a33";
    g.beginPath(); if (v === "artefact") { g.rect(x - 6, y - 6, 12, 12); } else if (v === "moving") { g.moveTo(x, y - 8); g.lineTo(x + 7, y + 6); g.lineTo(x - 7, y + 6); g.closePath(); } else g.arc(x, y, 6, 0, 2 * Math.PI); g.fill(); g.stroke();
  }
  const cov = D.field.maps.coverage, dd = cov._dec ||= decode(cov); let good = 0; for (const v of dd.d) if (v && (dd.lo + (v - 1) / 254 * (dd.hi - dd.lo)) >= 0.5 * D.field.exposures.length) good++;
  const area = D.field.area_deg2 * good / dd.d.length, nullRate = ST.V?.controls?.null_candidates_per_deg2;
  $("#popNote").innerHTML = `Well covered area ${num(area * 3600, 1)} square arcmin (at least half of the exposures). ${Object.entries(counts).map(([k, v]) => `${HNAME[k]}: ${v}`).join(" · ")}.<br>Density of sky changes: ${num(((counts.moving || 0) + (counts.variable || 0) + (counts.transient || 0)) / Math.max(area, 1e-9), 0)} per square degree of good coverage. ${nullRate != null ? `Empty practice fields give ${num(nullRate, 0)} false candidates per square degree.` : ""} Shapes: triangle moving, square artefact, circle other. Green wash: coverage.`;
}

/* ------------------------------------------------------------ V. dossier */
function selectCand(id, scroll = true) {
  ST.sel = id; const c = cand(); if (!c) return;
  renderCands(); renderDossier(c); drawSky(); drawMotionMap(); writeHash();
  if (scroll) document.getElementById("ch-dossier").scrollIntoView();
}
function chip(o) { return `<span class="chip ${o.replace(" ", "")}">${{ supports: "supports", challenges: "argues against", neutral: "neutral", "not run": "not run" }[o] || o}</span>`; }
function renderDossier(c) {
  const D = ST.D, d = c.dossier, p = c.post;
  $("#dosId").textContent = c.id;
  $("#dosStatus").innerHTML = `<span class="verdict">${esc(d.status)}</span> · ${verdictName(c)} · RA ${num(c.ra, 5)}, Dec ${num(c.dec, 5)}`;
  const hasStack = !!d.cutouts.motion_stack;
  $("#dossier").innerHTML = `
  <div class="card s3"><h3>What the visits show</h3><p class="small muted">${esc(d.cutouts.source || "")}</p><div class="strip" id="dStrip"></div><button class="btn ghost" id="dBlink">Blink first and strongest visit</button>
    ${hasStack ? `<div class="strip" style="margin-top:8px"><figure><canvas id="dPlain" width="120" height="120"></canvas><figcaption>Plain stack (peak ${num(d.cutouts.peak_plain, 1)})</figcaption></figure><figure><canvas id="dMoved" width="120" height="120"></canvas><figcaption>Stack that follows the motion (peak ${num(d.cutouts.peak_motion, 1)})</figcaption></figure></div><p class="small">If the motion is real, following it makes the source sharper and brighter.</p>` : ""}</div>
  <div class="card s3"><h3>The memory of this place</h3><ul class="chain">${d.chain.map((s) => `<li class="${s.seen ? "" : "off"}"><b>Visit ${s.visit}</b>, day ${num(s.day, 0)}: ${esc(s.event)} <span class="muted small">(signal to noise ${num(s.snr, 1)})</span></li>`).join("")}</ul></div>
  <div class="card s2"><h3>Five hypotheses</h3><div id="dHyp"></div><details><summary class="small">Change the priors</summary><div id="dPrior"></div><p class="small muted">The engine uses equal priors. Move a slider to see how belief depends on what you expect.</p></details></div>
  <div class="card s2"><h3>Discovery by disagreement</h3><p>${badges(c.methods)} <span class="small">P ${num(c.scores.P, 1)} · D ${num(c.scores.D, 1)} · A ${num(c.scores.A, 3)} (model spread ${num(c.scores.A_spread, 3)})</span></p><p><b>${esc(d.disagreement.headline)}</b></p><p class="small">${esc(d.disagreement.meaning)}</p>${disagreementStat(c.methods)}</div>
  <div class="card s2"><h3>Next observation oracle</h3><p>${esc(d.oracle.next_measurement)}</p>${d.oracle.motion_error_now ? `<p class="small">Motion error now ${num(d.oracle.motion_error_now, 4)} pixel per year. After one more visit near day ${num(d.oracle.next_visit_day, 0)}: ${num(d.oracle.motion_error_after_next_visit, 4)} (${num(d.oracle.gain, 2)} times better).</p>` : ""}<p class="small muted">Undecided between ${HNAME[d.oracle.top]} and ${HNAME[d.oracle.second]}. Entropy ${num(d.oracle.entropy, 2)}. Priority ${num(d.oracle.priority, 2)}. Simulated follow up only: no telescope schedule is used.</p></div>
  <div class="card s3"><h3>The self questioning machine</h3><p class="small muted">Tests that try to break the leading explanation. None of them feeds the engine.</p><ul class="qlist">${d.tests.map((t) => `<li>${chip(t.outcome)} <b>${esc(t.question)}</b><br><span class="small">${esc(t.method)} ${esc(t.result)}</span></li>`).join("")}</ul></div>
  <div class="card s3"><h3>The artefact court</h3><table>${d.court.map((r) => `<tr><td><b>${esc(r.exam)}</b><br><span class="small muted">${esc(r.q)}</span></td><td class="small">${esc(r.a)}</td><td>${r.ok === true ? chip("supports") : r.ok === false ? chip("challenges") : ""}</td></tr>`).join("")}</table></div>
  <div class="card s3"><h3>The counterfactual universe</h3><p class="small muted">The ${esc(d.robustness.statistic)} under other reasonable analysis choices. Dashed line: the threshold.</p><canvas id="dRob" width="560" height="${30 + 26 * d.robustness.rows.length}"></canvas><p class="small">Survives ${d.robustness.survived} of ${d.robustness.total}.</p></div>
  <div class="card s3"><h3>Debate</h3><div class="analysts">${d.debate.analysts.map((a) => `<div class="analyst"><h4>${esc(a.who)}</h4><p><b>${esc(a.claim)}</b> <span class="small muted">${esc(a.strength)}</span></p><p class="small">${a.evidence.map(esc).join("; ")}</p></div>`).join("")}</div><p><i>${esc(d.debate.synthesis)}</i></p></div>
  <div class="card s2"><h3>Track</h3><canvas id="dTrack" width="300" height="260"></canvas><p class="small">${d.motion.n >= 2 ? `μ = ${num(d.motion.pm_arcsec_yr, 3)} arcsec per year (${num(d.motion.pm_px_yr, 4)} ± ${num(d.motion.err, 4)} pixel), ${num(d.motion.sig, 1)} sigma, position angle ${num(d.motion.pa_deg, 0)} degrees, delta BIC ${num(d.motion.dbic, 1)}.` : "Measured in fewer than two visits."}</p></div>
  <div class="card s2"><h3>Light curve</h3><canvas id="dLight" width="300" height="260"></canvas><p class="small muted">Forced PSF photometry of each visit co add, per array.</p></div>
  <div class="card s2"><h3>Spectral fingerprint F(λ, t)</h3><canvas id="dSpec" width="300" height="260"></canvas><p class="small">Every exposure at its own color. Shape test across visits: chi square ${num(d.spectral.shape_chi2, 1)} for ${d.spectral.shape_dof} degrees of freedom. No composition or temperature is inferred.</p></div>
  <div class="card s3"><h3>Temporal fingerprint</h3><canvas id="dFp" width="420" height="300"></canvas><p class="small muted">Motion, brightness, duration and spectral behaviour of this change, with its instrument signs, each scaled from 0 to 1.</p></div>
  <div class="card s3"><h3>Identity network</h3><canvas id="dGraph" width="420" height="300"></canvas><p class="small muted">Links weighted by association probability from positions and errors.</p></div>
  <div class="card s6"><h3>Investigation report</h3><div class="report">${d.report.map((s) => `<p>${esc(s.text)}${s.refs.map((r) => `<span class="ref" data-r="${r}">${r}</span>`).join("")}</p>`).join("")}</div>
    <table id="dEv"><tr><th>Ref</th><th>Measurement</th><th>Value</th><th>Source</th></tr>${d.evidence.map((e) => `<tr data-r="${e.id}"><td>${e.id}</td><td>${esc(e.what)}</td><td>${esc(e.value)}</td><td class="small">${esc(e.source)}</td></tr>`).join("")}</table></div>
  <div class="card s6" id="dXm"></div>
  ${c.truth !== undefined && c.truth !== null ? `<div class="card s6"><button class="btn ghost" id="dTruth">Reveal the practice truth</button> <span id="dTruthOut"></span></div>` : ""}`;
  if (window.crossCard) crossCard(c);
  const strip = $("#dStrip");
  d.cutouts.visits.forEach((v) => { const f = el("figure", {}, `<canvas width="88" height="88"></canvas><figcaption>visit ${v.visit}</figcaption>`); strip.append(f); drawImage(f.querySelector("canvas"), v.img, "plate"); });
  if (hasStack) { drawImage($("#dPlain"), d.cutouts.plain_stack, "plate"); drawImage($("#dMoved"), d.cutouts.motion_stack, "plate"); }
  let bl = null; $("#dBlink").onclick = () => {
    if (bl) { clearInterval(bl); bl = null; return; }
    const cvs = [...strip.querySelectorAll("canvas")], best = d.chain.reduce((a, s, i) => (s.snr ?? -1) > (d.chain[a].snr ?? -1) ? i : a, 0); let k = 0;
    bl = setInterval(() => { k ^= 1; cvs.forEach((cv, i) => cv.style.opacity = (i === 0 || i === best) ? ((k ? i === best : i === 0) ? 1 : 0.15) : 0.15); }, 600);
  };
  ST.prior = { moving: 1, variable: 1, transient: 1, artefact: 1, null: 1 };
  $("#dPrior").innerHTML = Object.keys(ST.prior).map((k) => `<div class="prior"><span>${HNAME[k]}</span><input type="range" min="0.1" max="5" step="0.1" value="1" data-k="${k}"><span id="pv_${k}">1.0</span></div>`).join("");
  $("#dPrior").querySelectorAll("input").forEach((i) => i.oninput = () => { ST.prior[i.dataset.k] = +i.value; $("#pv_" + i.dataset.k).textContent = (+i.value).toFixed(1); drawHyp(c); });
  drawHyp(c);
  hbars($("#dRob"), d.robustness.rows.map((r) => ({ label: r.label.length > 26 ? r.label.slice(0, 25) + "…" : r.label, v: Math.max(0, Math.min(r.value ?? 0, 60)), color: r.survives ? "#7d9a8a" : "#b56f5e", text: num(r.value, 1) })), { left: 210, line: 5 });
  drawTrack(c); drawLight(c); drawSpec(c); drawGraph(c); drawFingerprint(c);
  document.querySelectorAll(".ref").forEach((r) => { r.onmouseenter = () => document.querySelectorAll(`#dEv tr[data-r="${r.dataset.r}"]`).forEach((t) => t.classList.add("ev-hi")); r.onmouseleave = () => document.querySelectorAll("#dEv tr").forEach((t) => t.classList.remove("ev-hi")); r.onclick = r.onmouseenter; });
  const tb = $("#dTruth"); if (tb) tb.onclick = () => { $("#dTruthOut").innerHTML = c.truth === "null" ? "No planted change here. This candidate is a false alarm of the practice sky." : `Planted: <b>${esc(c.truth)}</b>${c.truth_sub ? " (" + esc(c.truth_sub) + ")" : ""}. Engine verdict: ${verdictName(c)}. ${(c.post.unknown ? c.truth === "null" : c.post.verdict === c.truth) ? "Correct." : "Not correct: see the tests and the debate for the reason."}`; };
}
function disagreementStat(m) {
  const ap = ST.V?.agreement_patterns?.[m]; if (!ap) return "";
  return `<p class="small">On held out practice fields, candidates flagged by exactly ${esc(m)} were real sky changes in ${Math.round(100 * ap.sky_fraction)} percent of ${ap.n} cases (95 percent interval ${Math.round(100 * ap.lo)} to ${Math.round(100 * ap.hi)}).</p>`;
}
function drawHyp(c) {
  const p = c.post.probs || {}, pr = ST.prior || {}; let tot = 0; const q = {};
  Object.keys(p).forEach((k) => { q[k] = p[k] * (pr[k] ?? 1); tot += q[k]; }); Object.keys(q).forEach((k) => q[k] /= tot || 1);
  const box = $("#dHyp"), dr = c.post.drivers || {}, top = Object.keys(q).sort((a, b) => q[b] - q[a])[0];
  box.innerHTML = `<canvas id="dHypC" width="300" height="150"></canvas>${c.post.unknown ? `<p><b>Unknown.</b> ${c.post.why_unknown.map(esc).join(" ")}</p>` : `<p>Most plausible: <b>${HNAME[top]}</b>.</p>`}
   <p class="small">For ${HNAME[top]}: ${(dr[top] || []).map((d) => `${esc(d.feature)} ${d.push > 0 ? "raises" : "lowers"} it`).join(", ")}.</p>
   <p class="small muted">Distance from the training set ${num(c.post.ood_distance2, 1)} (limit ${num(c.post.ood_limit, 1)}).</p>`;
  hbars($("#dHypC"), Object.keys(q).map((k) => ({ label: HNAME[k].split(" ")[0] + " " + HNAME[k].split(" ")[1], v: q[k], color: PAL.H[k], text: Math.round(100 * q[k]) + "%" })), { left: 110, max: 1 });
}
function drawTrack(c) {
  const t = c.dossier.motion.track, cv = $("#dTrack"); if (!t || t.length < 2) { const g = cv.getContext("2d"); g.clearRect(0, 0, cv.width, cv.height); label(g, "No track: seen in fewer than two visits.", 10, 40, "#5d5763"); return; }
  const mx = t.reduce((s, p) => s + p.x, 0) / t.length, my = t.reduce((s, p) => s + p.y, 0) / t.length;
  const span = Math.max(0.15, ...t.map((p) => Math.max(Math.abs(p.x - mx) + 3 * p.ex, Math.abs(p.y - my) + 3 * p.ey))) * 1.1;
  const A = axes(cv, [-span, span], [-span, span], { xl: "pixel offset, east left, west right", yl: "north offset (pixel)", fx: (v) => num(v, 2), fy: (v) => num(v, 2), nx: 4, ny: 4 }), g = A.g;
  const m = c.dossier.motion, tt = t.map((p) => p.day / 365.25), tm = tt.reduce((a, b) => a + b, 0) / tt.length;
  if (m.n >= 3) polyline(g, [[A.X(m.pm_x * (tt[0] - tm)), A.Y(m.pm_y * (tt[0] - tm))], [A.X(m.pm_x * (tt[tt.length - 1] - tm)), A.Y(m.pm_y * (tt[tt.length - 1] - tm))]], "#937aa6", 1.5, [4, 3]);
  t.forEach((p, i) => { const x = A.X(p.x - mx), y = A.Y(p.y - my); ellipse(g, x, y, Math.abs(A.X(p.ex) - A.X(0)), Math.abs(A.Y(p.ey) - A.Y(0)), "#7489ad"); dot(g, x, y, 3, "#7489ad"); label(g, "v" + p.visit, x + 5, y - 5, "#2e2a33", 13); });
}
function drawLight(c) {
  const L = c.dossier.light.filter((r) => r.f != null), cv = $("#dLight"); if (!L.length) return;
  const ys = L.flatMap((r) => [r.f - r.e, r.f + r.e]), A = axes(cv, [Math.min(...L.map((r) => r.day)) - 15, Math.max(...L.map((r) => r.day)) + 15], [Math.min(0, ...ys), Math.max(...ys) * 1.08], { xl: "day", yl: "flux (microJy)", nx: 4 });
  const by = {}; L.forEach((r) => (by[r.det] ||= []).push(r));
  Object.entries(by).forEach(([d, rs]) => { polyline(A.g, rs.map((r) => [A.X(r.day), A.Y(r.f)]), PAL.band[d], 1.2); rs.forEach((r) => { errbar(A.g, A.X(r.day), A.Y(r.f - r.e), A.Y(r.f + r.e), PAL.band[d]); dot(A.g, A.X(r.day), A.Y(r.f), 3, PAL.band[d]); }); });
  Object.keys(by).forEach((d, i) => label(A.g, "array " + d, 60 + (i % 3) * 70, 16 + Math.floor(i / 3) * 14, PAL.band[d], 13));
}
function drawSpec(c) {
  const R = c.dossier.spectral.rows.filter((r) => r.f != null), cv = $("#dSpec"); if (!R.length) return;
  const ys = R.map((r) => r.f), A = axes(cv, [0.72, 5.2], [Math.min(0, ...ys), Math.max(...ys) * 1.1], { logx: true, xl: "wavelength (micron)", yl: "flux (microJy)", fx: (v) => num(v, 0), nx: 4 });
  const vcol = ["#7489ad", "#c4a061", "#937aa6", "#7d9a8a", "#b56f5e", "#5d5763"];
  R.forEach((r) => { errbar(A.g, A.X(r.lam), A.Y(r.f - r.e), A.Y(r.f + r.e), vcol[(r.visit - 1) % 6]); dot(A.g, A.X(r.lam), A.Y(r.f), 3, vcol[(r.visit - 1) % 6]); });
  [...new Set(R.map((r) => r.visit))].forEach((v, i) => label(A.g, "visit " + v, 60 + i * 56, 16, vcol[(v - 1) % 6], 13));
}
function fingerprint(c) {
  const f = c.features, d = c.dossier, cl = (v) => Math.max(0, Math.min(1, v)), ex = (v) => Math.expm1(Math.abs(v || 0));
  const dof = d.spectral.shape_dof || 0, chi = d.spectral.shape_chi2 || 0;
  return [["motion", cl(ex(f.mot_sig) / 20)], ["brightness", cl(ex(f.var_z) / 30)], ["duration", cl((f.n_on || 0) / Math.max(1, ST.D.visits))], ["contrast", cl(ex(f.presence) / 30)],
    ["spectral change", dof ? cl(chi / dof / 10) : 0], ["one exposure", cl(f.a4)], ["one array", cl(f.a5)], ["shape off PSF", cl(Math.abs(1 - (f.sharp ?? 1)) / 0.7)], ["flags", cl((f.flagfrac || 0) * 5)]];
}
function drawFingerprint(c) {
  const cv = $("#dFp"), g = cv.getContext("2d"), F = fingerprint(c), n = F.length, cx = cv.width / 2, cy = cv.height / 2 + 6, R = 105, col = PAL.H[c.post.verdict || "null"];
  g.clearRect(0, 0, cv.width, cv.height); g.font = `13px ${FONT}`;
  for (const r of [0.33, 0.66, 1]) { g.strokeStyle = "#e3dccd"; g.beginPath(); F.forEach((_, i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / n; const x = cx + R * r * Math.cos(a), y = cy + R * r * Math.sin(a); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath(); g.stroke(); }
  F.forEach(([l], i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / n, x = cx + (R + 14) * Math.cos(a), y = cy + (R + 14) * Math.sin(a); g.fillStyle = i >= 5 ? "#b56f5e" : "#5d5763"; g.fillText(l, x - g.measureText(l).width / 2 * (1 - Math.cos(a)), y + 4); });
  g.beginPath(); F.forEach(([, v], i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / n, x = cx + R * v * Math.cos(a), y = cy + R * v * Math.sin(a); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath();
  g.fillStyle = col + "55"; g.fill(); g.strokeStyle = col; g.lineWidth = 2; g.stroke();
}
function drawGraph(c) {
  const G = c.dossier.graph, cv = $("#dGraph"), g = cv.getContext("2d"); g.clearRect(0, 0, cv.width, cv.height);
  const cx = cv.width / 2, cy = cv.height / 2, others = G.nodes.filter((n) => n.id !== "C"), pos = { C: [cx, cy] };
  others.forEach((n, i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / others.length; pos[n.id] = [cx + 95 * Math.cos(a), cy + 92 * Math.sin(a)]; });
  G.edges.forEach((e) => { const a = pos[e.a], b = pos[e.b]; if (!a || !b) return; g.strokeStyle = `rgba(147,122,166,${0.25 + 0.75 * (e.w || 0)})`; g.lineWidth = 1 + 3 * (e.w || 0); g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke(); });
  const col = { candidate: "#937aa6", visit: "#7489ad", absent: "#d8d0c4", catalog: "#7d9a8a", neighbor: "#c4a061" };
  G.nodes.forEach((n) => { const [x, y] = pos[n.id]; dot(g, x, y, n.id === "C" ? 15 : 10, col[n.kind] || "#999", "#2e2a33"); label(g, n.label, x - g.measureText(n.label).width / 2, y + (n.id === "C" ? 30 : 24), "#2e2a33", 13); });
}

/* ------------------------------------------------------------ VI. motion map */
function drawMotionMap() {
  const D = ST.D; if (!D) return;
  const cv = $("#mmap"), map = drawImage(cv, D.field.maps.deep, "plate"), g = cv.getContext("2d"), k = +$("#exag").value;
  const rows = [];
  for (const c of D.candidates) {
    const m = c.dossier.motion; if (!m || m.n < 2) continue;
    const t = m.track, mx = t.reduce((s, p) => s + p.x, 0) / t.length, my = t.reduce((s, p) => s + p.y, 0) / t.length, col = PAL.H[c.post.verdict || "null"];
    const pts = t.map((p) => map(mx + (p.x - mx) * k, my + (p.y - my) * k));
    polyline(g, pts, col, c.id === ST.sel ? 2.6 : 1.6);
    t.forEach((p, i) => { ellipse(g, pts[i][0], pts[i][1], p.ex * k * map.s, p.ey * k * map.s, col); dot(g, pts[i][0], pts[i][1], 2.5, col); });
    label(g, c.id, pts[pts.length - 1][0] + 5, pts[pts.length - 1][1], col, 13);
    rows.push(c);
  }
  label(g, `tracks drawn ${k} times larger than life`, 8, cv.height - 8, "#5d5763", 13, true);
  $("#motionList").innerHTML = `<table><tr><th>ID</th><th>μ (arcsec per year)</th><th>Sigma</th><th>Delta BIC</th><th>Position angle</th><th>Visits</th><th>Verdict</th></tr>${rows.map((c) => { const m = c.dossier.motion; return `<tr class="click ${c.id === ST.sel ? "sel" : ""}" data-c="${c.id}"><td>${c.id}</td><td>${num(m.pm_arcsec_yr, 3)}</td><td>${num(m.sig, 1)}</td><td>${num(m.dbic, 1)}</td><td>${num(m.pa_deg, 0)}</td><td>${m.n}</td><td>${verdictName(c)}</td></tr>`; }).join("")}</table><p class="small">A track needs at least two visits. Position errors include the astrometric floor measured from the catalog stars of this field (${num(D.astro_floor, 3)} pixel).</p>`;
  $("#motionList").querySelectorAll("tr[data-c]").forEach((r) => r.onclick = () => selectCand(r.dataset.c));
}

/* ------------------------------------------------------------ VII. validation */
function renderValidation() {
  const V = ST.V, box = $("#valid"), D = ST.D;
  if (!V) { box.innerHTML = '<div class="card">The validation file is missing. Run scripts/calibrate_engine.py.</div>'; return; }
  const C = V.controls, U = V.unknown;
  box.innerHTML = `
  <div class="card"><div class="big">${pct(U.accuracy_when_decided, 0).replace(" percent", "%")}</div><div class="bignote">engine accuracy when it decides, on ${V.test_candidates} candidates from ${V.test_fields} unseen fields. It says unknown for ${pct(U.fraction, 0)}. Accuracy over all: ${pct(U.accuracy_all, 0)}.</div></div>
  <div class="card"><div class="big">${num(C.null_candidates_mean, 2)}</div><div class="bignote">false candidates per empty field (${C.null_fields} fields with nothing planted), about ${num(C.null_candidates_per_deg2, 0)} per square degree.</div></div>
  <div class="card"><div class="big">${pct(C.static_false_motion_rate, 1).replace(" percent", "%")}</div><div class="bignote">of ${C.static_stars} stars that do not move were called moving (interval ${pct(C.static_lo_hi[0], 1)} to ${pct(C.static_lo_hi[1], 1)}).</div></div>
  <div class="card"><h3>Are the probabilities honest?</h3><canvas id="vRel" width="300" height="260"></canvas><p class="small">Brier score ${num(V.brier, 3)}, expected calibration error ${num(V.ece, 3)}. Points on the line mean a stated 80 percent is right 80 percent of the time.</p></div>
  <div class="card"><h3>Confusion on unseen fields</h3><canvas id="vConf" width="320" height="260"></canvas><p class="small">Rows: planted truth. Columns: engine answer.</p></div>
  <div class="card"><h3>Discovery by disagreement</h3><canvas id="vAgree" width="320" height="260"></canvas><p class="small">Share of candidates that are real sky changes, by the methods that flagged them. Disagreement carries information: it changes the odds.</p></div>
  <div class="card s2"><h3>Completeness: planted changes that became candidates</h3><canvas id="vComp" width="620" height="260"></canvas></div>
  <div class="card"><h3>Adversarial artefacts</h3><table><tr><th>Camera effect</th><th>Rejected</th><th>Cases</th></tr>${Object.entries(V.adversarial).map(([k, a]) => `<tr><td>${esc(k)}</td><td>${pct(a.rejected, 0)} (${pct(a.lo, 0)} to ${pct(a.hi, 0)})</td><td>${a.n}</td></tr>`).join("")}</table><p class="small">Rejected means called artefact or unknown, never a sky change.</p></div>
  <div class="card"><h3>Anti discovery controls in this field</h3>${fieldControls(D)}</div>
  <div class="card"><h3>Measured floors</h3><p class="small">Astrometric floor (median over fields) ${num(C.astrometric_floor_px, 3)} pixel. Photometric floor by array: ${Object.entries(C.photometric_floor).map(([d, v]) => `${d}: ${pct(v, 1)}`).join(", ")}. Both are measured on catalog stars of each field, never assumed.</p></div>
  <div class="card s2" id="vReal"></div>
  <div class="card"><h3>What drives each hypothesis</h3>${Object.entries(V.coefficients).map(([k, co]) => `<p class="small"><b style="color:${PAL.H[k]}">${HNAME[k]}</b>: ${Object.entries(co).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 4).map(([f, v]) => `${esc(f)} ${v > 0 ? "+" : "−"}`).join(", ")}</p>`).join("")}</div>`;
  if (window.realCard) realCard();
  const rel = V.reliability, A = axes($("#vRel"), [0, 1], [0, 1], { xl: "stated confidence", yl: "observed accuracy", fx: (v) => num(v, 1), fy: (v) => num(v, 1) });
  polyline(A.g, [[A.X(0), A.Y(0)], [A.X(1), A.Y(1)]], "#a7a19a", 1, [4, 3]);
  rel.forEach((r) => dot(A.g, A.X(r.confidence), A.Y(r.accuracy), 2 + Math.sqrt(r.n) / 2, "rgba(147,122,166,.7)", "#2e2a33"));
  const cls = V.classes.map((k) => HNAME[k].split(" ")[0]);
  heat($("#vConf"), V.confusion, cls, cls, { left: 50 });
  const pats = Object.entries(V.agreement_patterns).filter(([, a]) => a.n >= 5).sort((a, b) => b[1].sky_fraction - a[1].sky_fraction);
  hbars($("#vAgree"), pats.map(([k, a]) => ({ label: k + " (" + a.n + ")", v: a.sky_fraction, lo: a.lo, hi: a.hi, color: "#937aa6", text: Math.round(100 * a.sky_fraction) + "%" })), { left: 80, max: 1 });
  const comp = V.completeness, kinds = Object.keys(comp).filter((k) => k !== "artefact"), mags = [...new Set(kinds.flatMap((k) => Object.keys(comp[k])))].map(Number).filter((m) => !isNaN(m)).sort((a, b) => a - b);
  if (mags.length) {
    const A2 = axes($("#vComp"), [mags[0] - 0.5, mags[mags.length - 1] + 0.5], [0, 1.05], { xl: "AB magnitude at 4.5 micron (fainter to the right)", yl: "fraction found", fy: (v) => num(v, 1), fx: (v) => num(v, 0) });
    kinds.forEach((k) => { const pts = mags.filter((m) => comp[k][m]).map((m) => [A2.X(m), A2.Y(comp[k][m].fraction), comp[k][m]]); polyline(A2.g, pts.map((p) => [p[0], p[1]]), PAL.H[k], 2); pts.forEach(([x, y, q]) => { errbar(A2.g, x, A2.Y(q.lo), A2.Y(q.hi), PAL.H[k]); dot(A2.g, x, y, 3, PAL.H[k]); }); });
    kinds.forEach((k, i) => label(A2.g, HNAME[k], 70 + i * 140, 26, PAL.H[k], 15));
  }
}
function fieldControls(D) {
  const c = D?.field?.controls; if (!c) return '<p class="small">Not run for this field.</p>';
  const ts = c.time_shuffle?.rows || [];
  return `<p class="small"><b>Null twin:</b> ${c.null_twin ? `${c.null_twin.candidates} candidates when every planted change is removed.` : "only for the practice sky."}</p>
  <p class="small"><b>Static stars:</b> ${c.static_stars?.called_moving ?? "n/a"} of ${c.static_stars?.tested ?? "n/a"} catalog stars called moving.</p>
  <p class="small"><b>Alignment stress:</b> ${c.alignment_stress ? `${c.alignment_stress.wcs_only} spots with the file WCS only, ${c.alignment_stress.anchored} after the star anchors, ${c.alignment_stress.final} in the final fair co adds.` : "n/a"}</p>
  <p class="small"><b>Time shuffle:</b> ${ts.length ? ts.map((r) => `track at ${r.x}, ${r.y}: ${r.as_strong} of ${r.shuffles} shuffles fit as well (p ${num(r.p, 3)})`).join("; ") : "no moving track to shuffle."}</p>`;
}

/* ------------------------------------------------------------ VIII. questions */
function renderQuestions() {
  const Q = ST.D.research || [];
  $("#questions").innerHTML = Q.length ? Q.map((q, i) => `<div class="card"><p class="small muted">Suggestion ${i + 1}, not a finding</p><p><b>${esc(q.q)}</b></p><p class="small">${esc(q.numbers)}</p><p class="small"><b>Test:</b> ${esc(q.test)}</p><p class="small"><b>Falsified if:</b> ${esc(q.falsified_if)}</p></div>`).join("") : '<div class="card">No open question from this field.</div>';
}

/* ------------------------------------------------------------ IX. Planet X lab */
function planetlab(o) {
  const radius = Math.pow(o.mass, 0.55), D = 2 * radius * 6371, H = 5 * Math.log10(1329 / (D * Math.sqrt(o.albedo)));
  const refl = (d) => H + 10 * Math.log10(d);
  const therm = (T, d) => { const h = 6.626e-34, c = 2.998e8, k = 1.381e-23, lam = 4.5e-6, nu = c / lam, x = h * nu / (k * T); if (x > 700) return Infinity; const B = 2 * h * nu ** 3 / c ** 2 / Math.expm1(x), om = Math.PI * (radius * 6371e3 / (d * 1.496e11)) ** 2; return -2.5 * Math.log10(B * om / 3631e-26); };
  const lim = o.limit - (Math.abs(o.lat) < 10 ? 0.5 : 0);
  let tneed = null; for (let T = 20; T < 2000; T += 5) if (therm(T, o.d) < lim) { tneed = T; break; }
  return { radius, H, refl, therm, lim, reach: Math.pow(10, (lim - H) / 10), par: 206265 / o.d, orbit: 29.78 / Math.sqrt(o.d) * 3.156e7 / (o.d * 1.496e8) * 206265, tneed };
}
function renderPlanet() {
  const S = [["d", "Distance (AU)", 100, 2000, 10, 500], ["mass", "Mass (Earth masses)", 1, 20, 0.5, 6], ["albedo", "Albedo", 0.05, 0.8, 0.01, 0.4], ["temp", "Temperature (K)", 10, 300, 5, 40], ["limit", "Depth limit (AB)", 17, 21, 0.1, 19], ["lat", "Galactic latitude (deg)", 0, 90, 1, 30]];
  $("#pxControls").innerHTML = `<h3>Assume a planet</h3>${S.map(([k, l, a, b, s, v]) => `<div class="slider"><label for="px_${k}">${l}</label><input id="px_${k}" type="range" min="${a}" max="${b}" step="${s}" value="${v}"><output id="pxo_${k}">${v}</output></div>`).join("")}
  <p class="small muted">Assumptions: radius from mass as R = M to the power 0.55; reflected sunlight at opposition with AB equal to V; blackbody glow at 4.5 micron; the depth limit is your choice, minus 0.5 magnitude near the galactic plane. These are teaching estimates, not SPHEREx sensitivity claims.</p>`;
  S.forEach(([k]) => $("#px_" + k).oninput = drawPlanet);
  $("#ladder").innerHTML = [["Theoretical prediction", "Orbits of distant objects suggest an unseen mass. No light is seen.", false], ["Observational candidate", "A source that moves the right way in some images. CHRONOS can reach this rung, and no further.", true], ["Statistically supported detection", "Motion measured, artefacts excluded, false alarm rate shown to be small, on more data.", false], ["Confirmed discovery", "Independent telescopes recover it on a predicted orbit.", false]].map(([h, t, here], i) => `<div class="rung ${here ? "here" : ""}"><small>Rung ${i + 1}</small><h4>${h}</h4><p class="small">${t}</p></div>`).join("");
  drawPlanet();
}
function drawPlanet() {
  const o = {}; ["d", "mass", "albedo", "temp", "limit", "lat"].forEach((k) => { o[k] = +$("#px_" + k).value; $("#pxo_" + k).textContent = o[k]; });
  const P = planetlab(o), cv = $("#pxChart"), ds = [];
  for (let d = 100; d <= 2000; d += 25) ds.push(d);
  const A = axes(cv, [100, 2000], [26, 14], { logx: true, left: 66, xl: "distance (AU)", yl: "AB magnitude, brighter up", fx: (v) => num(v, 0), fy: (v) => num(v, 0) });
  polyline(A.g, ds.map((d) => [A.X(d), A.Y(Math.min(26, P.refl(d)))]), "#7489ad", 2);
  polyline(A.g, ds.map((d) => [A.X(d), A.Y(Math.max(14, Math.min(26, P.therm(o.temp, d))))]), "#b56f5e", 1.5, [5, 3]);
  polyline(A.g, [[A.X(100), A.Y(P.lim)], [A.X(2000), A.Y(P.lim)]], "#7d9a8a", 1.5, [2, 3]);
  dot(A.g, A.X(o.d), A.Y(Math.min(26, P.refl(o.d))), 5, "#937aa6", "#2e2a33");
  label(A.g, "reflected sunlight", 70, 34, "#7489ad"); label(A.g, `heat glow at ${o.temp} K`, 200, 34, "#b56f5e"); label(A.g, "depth limit", 340, 34, "#7d9a8a");
  const m = P.refl(o.d), seen = m < P.lim;
  $("#pxOut").innerHTML = `<p>Radius about ${num(P.radius, 1)} Earth radii. Brightness from reflected sunlight: <b>${num(m, 1)} AB</b>, ${seen ? "brighter than the limit" : "fainter than the limit"}.</p>
   <p>${seen ? "In this model SPHEREx could record it in one visit." : `In this model SPHEREx could not record it in one visit. Reach for this planet: ${num(P.reach, 0)} AU.`} The heat glow at ${o.temp} K is ${isFinite(P.therm(o.temp, o.d)) ? num(P.therm(o.temp, o.d), 1) + " AB" : "far too faint to compute"}; it would need about ${P.tneed ?? "more than 2000"} K to pass the limit, so a cold distant planet shows only by reflected sunlight.</p>
   <p>Apparent motion: parallax up to ${num(P.par, 0)} arcsec (${num(P.par / 6.15, 0)} pixels) over half a year, orbital drift ${num(P.orbit, 1)} arcsec per year. Between two visits half a year apart it would jump far outside a small cutout, so CHRONOS would see it as a transient pair, not a slow mover. The Planet X search tool in the full app stacks many exposures along trial distances for this reason.</p>`;
}

/* ------------------------------------------------------------ X. citizen lab */
const CIT_KEY = "chronos_citizen_v1";
function citLoad() { try { return JSON.parse(localStorage.getItem(CIT_KEY) || "[]"); } catch (e) { return []; } }
function citSave(a) { try { localStorage.setItem(CIT_KEY, JSON.stringify(a)); } catch (e) { } }
function renderCitizen() {
  const D = ST.D, box = $("#citizen"), done = citLoad(), mine = done.filter((r) => r.field === D.meta.key);
  if (!D.candidates.length) { box.innerHTML = "<h3>No candidate in this field</h3><p>Nothing changed here, so there is nothing to judge. That is a result too.</p>"; return; }
  const repeat = mine.length >= 2 && Math.random() < 0.2, pool = D.candidates.filter((c) => repeat || !mine.find((r) => r.cand === c.id));
  if (!pool.length) { box.innerHTML = `<h3>All cases of this field judged</h3><p>Try another field, or <button class="btn ghost" id="citReset">clear my answers</button>.</p>`; $("#citReset").onclick = () => { citSave(done.filter((r) => r.field !== D.meta.key)); renderCitizen(); renderArchive(); }; return; }
  const c = pool[Math.floor(Math.random() * pool.length)], ch = c.dossier.chain, a = 0, b = ch.reduce((k, s, i) => Math.abs((s.snr ?? 0) - (ch[0].snr ?? 0)) > Math.abs((ch[k].snr ?? 0) - (ch[0].snr ?? 0)) ? i : k, ch.length - 1);
  box.innerHTML = `<h3>Case ${esc(c.id)}${repeat ? " (shown again, to test consistency)" : ""}</h3><p class="small">Instructions: watch the blink of two visits. Answer from the images only. If you are unsure, say so: that is useful data.</p>
   <canvas id="citCv" width="200" height="200"></canvas><p class="small muted" id="citLbl"></p>
   <div class="cit-q">Did it move? <button data-q="move" data-v="yes">Yes</button><button data-q="move" data-v="no">No</button><button data-q="move" data-v="unsure">Can not tell</button></div>
   <div class="cit-q">Brightness? <button data-q="bright" data-v="brighter">Brighter</button><button data-q="bright" data-v="fainter">Fainter</button><button data-q="bright" data-v="same">Same</button></div>
   <div class="cit-q">Did it appear or disappear? <button data-q="appear" data-v="yes">Yes</button><button data-q="appear" data-v="no">No</button></div>
   <div class="cit-q">Is it a camera effect? <button data-q="art" data-v="yes">Yes</button><button data-q="art" data-v="no">No</button><button data-q="art" data-v="unsure">Can not tell</button></div>
   <button class="btn" id="citGo">Record my answer</button><div id="citOut"></div>`;
  const ans = {}; box.querySelectorAll(".cit-q button").forEach((bt) => bt.onclick = () => { ans[bt.dataset.q] = bt.dataset.v; bt.parentNode.querySelectorAll("button").forEach((x) => x.classList.toggle("btn", x === bt)); });
  let k = 0; const imgs = [c.dossier.cutouts.visits[a], c.dossier.cutouts.visits[b]];
  const tick = () => { if (!document.body.contains($("#citCv"))) return; drawImage($("#citCv"), imgs[k].img, "plate"); $("#citLbl").textContent = `visit ${imgs[k].visit}`; k ^= 1; ST.citT = setTimeout(tick, 700); };
  clearTimeout(ST.citT); tick();
  $("#citGo").onclick = () => {
    const human = ans.art === "yes" ? "artefact" : ans.move === "yes" ? "moving" : ans.appear === "yes" ? "transient" : (ans.bright && ans.bright !== "same") ? "variable" : (ans.move === "unsure" || ans.art === "unsure") ? "unknown" : "null";
    const machine = c.post.unknown ? "unknown" : c.post.verdict;
    const rec = { field: D.meta.key, cand: c.id, answers: ans, human, machine, truth: c.truth ?? null, instructions: "v1 blink two visits", n: done.length + 1, repeat };
    done.push(rec); citSave(done);
    $("#citOut").innerHTML = `<p>You said <b>${esc(human)}</b>. The engine said <b>${esc(machine)}</b>${c.truth ? `; the practice truth is <b>${esc(c.truth)}</b>` : ""}. ${human === machine ? "You agree." : "You disagree: this case goes to the disagreement archive."}</p><button class="btn ghost" id="citNext">Next case</button>`;
    $("#citNext").onclick = renderCitizen; renderArchive();
  };
}
function kappa(rows) {
  const labs = [...new Set(rows.flatMap((r) => [r.human, r.machine]))], n = rows.length; if (!n) return null;
  const po = rows.filter((r) => r.human === r.machine).length / n; let pe = 0;
  labs.forEach((l) => { pe += (rows.filter((r) => r.human === l).length / n) * (rows.filter((r) => r.machine === l).length / n); });
  return pe === 1 ? 1 : (po - pe) / (1 - pe);
}
function renderArchive() {
  const all = citLoad(), dis = all.filter((r) => r.human !== r.machine), k = kappa(all);
  const reps = {}; all.forEach((r) => (reps[r.field + r.cand] ||= []).push(r.human)); const rp = Object.values(reps).filter((v) => v.length > 1), same = rp.filter((v) => v.every((x) => x === v[0])).length;
  $("#archive").innerHTML = `<h3>Human and machine disagreement archive</h3><p>${all.length} judgements in this browser. Agreement ${all.length ? Math.round(100 * (all.length - dis.length) / all.length) : 0} percent, Cohen kappa ${k == null ? "n/a" : num(k, 2)}. ${rp.length ? `Repeated cases: ${same} of ${rp.length} answered the same way twice.` : ""}</p>
   <table><tr><th>#</th><th>Field</th><th>Case</th><th>Human</th><th>Machine</th><th>Truth</th></tr>${dis.slice(-12).reverse().map((r) => `<tr><td>${r.n}</td><td>${esc(r.field)}</td><td>${esc(r.cand)}</td><td>${esc(r.human)}</td><td>${esc(r.machine)}</td><td>${esc(r.truth ?? "unknown")}</td></tr>`).join("")}</table>
   <p class="small muted">A click is not a measurement. The archive keeps the instructions, repeats and uncertainty so that agreement can be studied, not claimed.</p><button class="btn ghost" id="citExport">Download the archive</button>`;
  $("#citExport").onclick = () => download("chronos_citizen_archive.json", JSON.stringify(all, null, 1));
}

/* ------------------------------------------------------------ XI. black box */
function download(name, text) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "application/json" })); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function renderBox() {
  const R = ST.D.record;
  $("#box").innerHTML = `<p><b>Seal</b> <code>${esc(R.seal)}</code><br><b>Output digest</b> <code>${esc(R.output_digest)}</code></p>
   <p class="small">${esc(R.rule)}</p>
   <p><button class="btn" id="bxRun">Reproduce this investigation</button> <button class="btn ghost" id="bxDl">Download the reproducibility package</button> <span id="bxOut"></span></p>
   <div class="two-col"><div><h3>Inputs and versions</h3><pre>${esc(JSON.stringify({ inputs: R.inputs.meta, releases: R.inputs.releases, exposures: R.inputs.exposures.length + " exposures (ids in the package)", versions: R.versions, code: R.code }, null, 1))}</pre></div>
   <div><h3>Thresholds and outputs</h3><pre>${esc(JSON.stringify({ thresholds: R.thresholds, outputs: R.outputs }, null, 1))}</pre></div></div>
   <p><button class="btn ghost" id="bxHf">Publish the package to Hugging Face</button> <span id="bxHfOut" class="small"></span></p>
   <p class="small muted">Human decisions: the citizen lab archive is kept apart in your browser.</p>`;
  if (window.hfButton) hfButton();
  $("#bxDl").onclick = () => { const D = ST.D, slim = { ...D, field: { ...D.field, maps: "omitted: rebuilt by the code from the inputs" } }; download(`chronos_${D.meta.key}_package.json`, JSON.stringify({ record: D.record, investigation: slim }, null, 1)); };
  $("#bxRun").onclick = async () => {
    if (STATIC) { $("#bxOut").textContent = "This hosted page is static. Run python run.py and press this button there: it reruns the analysis from the recorded inputs and compares the digest."; return; }
    $("#bxOut").textContent = "Running again from the recorded inputs…";
    try { const r = await getJSON("api/reproduce", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(R) }); $("#bxOut").textContent = r.note + (r.ok === null ? "" : ` Digest then ${r.old?.slice(0, 12)}, now ${r.new?.slice(0, 12)}.`); }
    catch (e) { $("#bxOut").textContent = "Reproduction failed: " + e.message; }
  };
}

/* ------------------------------------------------------------ XII. methods */
function renderMethods() {
  const M = [["Fair pairs", "Two exposures are compared only on the same array and within a fraction of a channel in color. Visits are co added only when every color has a partner. The difference image Z = (I₂ − k I₁) / √(σ₁² + k² σ₂² + (f s)²) adds the resampling error f s measured on catalog stars, where s is the local brightness."],
  ["Three detectors", "P: matched filter detection in each visit, PSF centroids, linking across visits, then motion, brightness and presence tests. D: fair co add differences summed over arrays. A: the time behaviour of every pixel against its fair partners, ranked by an isolation forest, a local outlier factor and a robust covariance model."],
  ["Five hypotheses", "A multinomial logistic model on 22 fingerprint features, trained on practice fields with a known truth, gives P(H | D) with equal priors and a temperature fitted on the training fields. It says unknown when the top probability is under 55 percent, when the fingerprint is far from the training set (Mahalanobis distance), or when fewer than two visits measured the place."],
  ["Self questioning", "For the leading hypothesis CHRONOS runs tests that it did not use to decide: star drift between visits, leave one visit out, catalog motion, the simultaneous array behind the dichroic, detector position, crosstalk geometry, and shape. A test that argues against the explanation changes the status to contested."],
  ["Counterfactuals", "The whole analysis runs again with flagged pixels kept, a local background, the worst measured noise, star anchors moved by their error, a wider PSF, each visit left out, and a stricter threshold. The robustness profile counts the choices under which the claim survives."],
  ["Floors and honesty", "Noise is checked against the VARIANCE plane on empty sky. The astrometric and photometric floors are measured on catalog stars in every field. Nothing in the practice sky is called a discovery, and in real data CHRONOS uses candidate language only."]];
  $("#methods").innerHTML = M.map(([h, t]) => `<div class="card"><h3>${h}</h3><p>${t}</p></div>`).join("");
}

/* ------------------------------------------------------------ ask the sky */
function parseCoords(q) {
  const low = q.toLowerCase().trim();
  const f = ST.fields.find((f) => low && (f.key === low || f.name.toLowerCase().includes(low)));
  if (f) return { key: f.key };
  const n = (q.replace(/−/g, "-").match(/[-+]?\d+(?:\.\d+)?/g) || []).map(Number);
  if (/\d+\s*[h:]\s*\d+/.test(q) && n.length >= 6) { const s = /-\s*\d/.test(q.split(/[h:]/).slice(1).join(" ").replace(/^[^ ]*\s/, "")) || q.replace(/^[^+-]*/, "").startsWith("-") ? -1 : 1; return { ra: 15 * (n[0] + n[1] / 60 + n[2] / 3600), dec: s * (Math.abs(n[3]) + n[4] / 60 + n[5] / 3600) }; }
  if (n.length >= 2 && n[0] >= 0 && n[0] < 360 && Math.abs(n[1]) <= 90) return { ra: n[0], dec: n[1] };
  return null;
}
function ask(q) {
  const D = ST.D, out = $("#askOut"), low = q.toLowerCase(); out.hidden = false;
  const id = (q.match(/\bc\s?0?(\d{1,2})\b/i) || [])[1], cid = id ? "C" + String(+id).padStart(2, "0") : null;
  const show = (intent, text, filt) => { out.innerHTML = `<b>Understood as</b> <code>${esc(JSON.stringify(intent))}</code><br>${text}`; };
  if (!D) return show({ intent: "none" }, "Load a field first.");
  const pnum = (low.match(/(\d+(?:\.\d+)?)\s*(?:percent|%)/) || [])[1];
  if (/planet\s*(x|nine|9)/.test(low)) { document.getElementById("ch-planet").scrollIntoView(); return show({ intent: "open", chapter: "Planet X lab" }, "Opened the Planet X laboratory. NASA states that Planet X has not been discovered."); }
  if (cid && /against|disprove|wrong|contra/.test(low)) { const c = cand(cid); if (!c) return show({ intent: "evidence_against", id: cid }, `There is no ${cid} in this field.`); selectCand(cid); const neg = c.dossier.tests.filter((t) => t.outcome === "challenges"); return show({ intent: "evidence_against", id: cid, hypothesis: c.post.top }, neg.length ? neg.map((t) => `${esc(t.question)} ${esc(t.result)}`).join("<br>") : `No test argues against the leading explanation of ${cid}. Weakest point: ${esc(c.dossier.robustness.rows.filter((r) => !r.survives).map((r) => r.label).join(", ") || "none")}.`); }
  if (cid && /catalog|gaia|wise|known/.test(low)) { const c = cand(cid); if (!c) return show({ intent: "catalog", id: cid }, `There is no ${cid}.`); selectCand(cid); const k = c.dossier.graph.nodes.find((n) => n.kind === "catalog"); return show({ intent: "catalog", id: cid }, k ? `${esc(k.label)} sits ${k.sep_px} pixel away after motion.` : `No catalog source within 3 pixels of ${cid}.`); }
  if (cid) { const c = cand(cid); if (!c) return show({ intent: "explain", id: cid }, `There is no ${cid} in this field. Candidates: ${D.candidates.map((c) => c.id).join(", ")}.`); selectCand(cid); return show({ intent: "explain", id: cid }, c.dossier.report.map((s) => esc(s.text)).join(" ")); }
  const filters = [[/mov|motion|shift|position/, "moving"], [/bright|faint|dim|variab|brightness/, "variable"], [/appear|vanish|transient|new |disappear|flare/, "transient"], [/artefact|artifact|glitch|camera|detector|instrument|ghost|hot pixel/, "artefact"], [/unknown|unexplained|uncertain|disagree/, "unknown"]];
  if (/poor|bad|quality|flag|contamin|noisy/.test(low)) { document.getElementById("ch-sky").querySelector("details").open = true; const bad = D.field.exposures.filter((e) => e.noise_k > 1.15 || Object.keys(e.flags).some((k) => !["COLD", "HOT"].includes(k)) || e.rel !== D.field.guardian.common_release); document.getElementById("ch-sky").scrollIntoView(); return show({ intent: "quality", rule: "noise factor above 1.15, or flags other than single cold or hot pixels, or another release" }, bad.length ? `${bad.length} exposures: ${bad.slice(0, 10).map((e) => `${e.id} (array ${e.det}${e.noise_k > 1.15 ? ", noise " + num(e.noise_k, 2) : ""}${e.rel !== D.field.guardian.common_release ? ", release " + e.rel : ""})`).join(", ")}${bad.length > 10 ? " …" : ""}.` : "No exposure breaks these rules."); }
  const vis = low.match(/visit\s*(\d)\D+(\d)/); if (vis && /compar/.test(low)) { const i = D.field.microscope.findIndex((L) => (L.q1 == vis[1] && L.q2 == vis[2]) || (L.q1 == vis[2] && L.q2 == vis[1])); if (i < 0) return show({ intent: "compare", visits: [+vis[1], +vis[2]] }, "These visits have no fair pair on any array, so CHRONOS will not compare their brightness directly. This is the SPHEREx color rule, not a missing feature."); $("#pairSel").value = i; ST.micro = { p: i, l: ST.D.field.microscope[i].layers.length - 1 }; renderMicro(); document.getElementById("ch-micro").scrollIntoView(); return show({ intent: "compare", visits: [+vis[1], +vis[2]], array: D.field.microscope[i].det }, "Opened the difference microscope on that pair."); }
  for (const [re, h] of filters) if (re.test(low)) {
    let f = (c) => h === "unknown" ? c.post.unknown || c.dossier.debate.unresolved : (!c.post.unknown && c.post.verdict === h) || (c.post.probs?.[h] || 0) > 0.3;
    if (h === "variable" && pnum) f = ((g) => (c) => g(c) && (c.features.amp || 0) >= pnum / 100)(f);
    const hits = D.candidates.filter(f); renderCands(f); document.getElementById("ch-cands").scrollIntoView();
    return show({ intent: "filter", hypothesis: h, min_change: pnum ? +pnum / 100 : undefined }, hits.length ? `${hits.length} candidates: ${hits.map((c) => `${c.id} (${verdictName(c)})`).join(", ")}. The table is filtered. <a href="#" id="clrF">Show all</a>` : "No candidate matches. That is an answer, not an error.");
  }
  const c = parseCoords(q); if (c && !c.key) { $("#coord").value = q; investigate(c); return show({ intent: "go_to", ra: c.ra, dec: c.dec }, "Investigating that position."); }
  if (c && c.key) { $("#field").value = c.key; investigate(); return show({ intent: "load", field: c.key }, "Loading that field."); }
  show({ intent: "unknown" }, "I could not map this to a measurement. Try: show moving candidates · brightness changed more than 20 percent · explain C02 · evidence against C01 · compare visit 1 and 2 · poor quality exposures · 269.45 4.74 · Planet X.");
}
document.addEventListener("click", (e) => { if (e.target.id === "clrF") { e.preventDefault(); renderCands(); } });
boot();
