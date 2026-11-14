/* Nakshatra CHRONOS: the citizen lab study, the whole sky tiles, cross matching with other surveys,
   the real data injection test and publishing to Hugging Face. Uses the helpers of app.js and charts.js. */

/* ------------------------------------------------------------ cross match (dossier) */
function crossCard(c) {
  const box = $("#dXm"); if (!box) return;
  const live = ST.D?.meta?.mode === "live";
  box.innerHTML = `<h3>Other surveys at this place</h3>
    <p class="small">Rubin alerts (Vera C. Rubin Observatory, through the ALeRCE broker) and known asteroids and comets (JPL). NEO Surveyor joins when its data is public: NASA plans its launch no earlier than September 2027.</p>
    ${live && !STATIC ? `<button class="btn ghost" id="xmGo">Check Rubin alerts and known bodies</button>` : `<p class="small muted">${STATIC ? "This hosted page is static. In the full app (python run.py), Live SPHEREx mode runs this check." : "The practice sky has no counterpart in other surveys. This check runs on real coordinates in Live SPHEREx mode."}</p>`}
    <div id="xmOut"></div>`;
  const go = $("#xmGo"); if (!go) return;
  go.onclick = async () => {
    $("#xmOut").textContent = "Asking ALeRCE and JPL…";
    const mjd = (ST.D.mjd_visits || []).reduce((a, b) => a + b, 0) / Math.max((ST.D.mjd_visits || []).length, 1);
    try {
      const r = await getJSON(`api/crossmatch?ra=${c.ra}&dec=${c.dec}&mjd=${mjd || 0}&mode=live`);
      const rub = r.rubin || [];
      $("#xmOut").innerHTML = `<p>${esc(r.summary || r.note || "")}</p>
        ${rub.length ? `<table><tr><th>Rubin object</th><th>Separation</th><th>Alerts</th><th>First and last (MJD)</th></tr>${rub.slice(0, 8).map((o) => `<tr><td>${esc(o.oid)}</td><td>${num(o.sep_arcsec, 1)} arcsec</td><td>${o.n ?? ""}</td><td>${num(o.first_mjd, 1)} to ${num(o.last_mjd, 1)}</td></tr>`).join("")}</table>` : ""}
        ${Object.keys(r.errors || {}).length ? `<p class="small muted">${Object.entries(r.errors).map(([k, v]) => esc(k + ": " + v)).join("; ")}</p>` : ""}`;
    } catch (e) { $("#xmOut").textContent = "The check failed: " + e.message; }
  };
}

/* ------------------------------------------------------------ real data injection (validation) */
async function realCard() {
  const box = $("#vReal"); if (!box) return;
  let R = null;
  try { R = await getJSON("data/real_injection.json"); } catch (e) { R = null; }
  if (!R || !R.real_rows) {
    box.innerHTML = `<h3>On real noise: injection into SPHEREx QR3</h3>
      <p>The scores above come from the practice sky. The next test plants known movers, variables and transients into real QR3 exposures, runs CHRONOS, and measures completeness and the engine on real noise. It can also retrain the engine with these rows; the new engine is scored on fields it did not see.</p>
      <p class="small"><b>Status:</b> ${R ? esc(R.status) : "not run yet"}. The tool is ready and tested offline on files in the IRSA layout. It needs network access to IRSA and Gaia: <code>python scripts/inject_real.py --retrain</code></p>`;
    return;
  }
  const f = R.fields.filter((x) => x.score);
  box.innerHTML = `<h3>On real noise: injection into SPHEREx ${esc(R.collection)}</h3>
    <p>${R.planted_all} planted sources in ${f.length} real fields: ${pct(R.completeness_all, 0)} became candidates.${R.before ? ` Engine right when it decides: ${pct(R.before.right_when_decided, 0)} before retraining, ${pct(R.after.right_when_decided, 0)} after (held out fields, unknown ${pct(R.after.unknown_fraction, 0)}).` : ""}</p>
    <table><tr><th>Field</th><th>Exposures</th><th>Own candidates</th><th>Planted found</th><th>New false per trial</th></tr>${f.map((x) => `<tr><td>${esc(x.name)}</td><td>${x.usable}</td><td>${x.base_candidates}</td><td>${x.score.found} of ${x.score.planted}</td><td>${num(x.score.new_unplanted_per_trial, 2)}</td></tr>`).join("")}</table>
    <p class="small muted">${esc(R.note)}</p>`;
}

/* ------------------------------------------------------------ Hugging Face (black box) */
function hfButton() {
  const b = $("#bxHf"); if (!b) return;
  b.onclick = async () => {
    const out = $("#bxHfOut");
    if (STATIC) { out.textContent = "This hosted page is static. In the full app, set HF_TOKEN on the server and press this button: the sealed package goes to a Hugging Face dataset, where anyone can download it and rerun it."; return; }
    const repo = prompt("Hugging Face dataset repository (owner/name):", localStorage.getItem("chronos_hf_repo") || "");
    if (!repo) return;
    try { localStorage.setItem("chronos_hf_repo", repo); } catch (e) { }
    out.textContent = "Uploading…";
    const D = ST.D, slim = { ...D, field: { ...D.field, maps: "omitted: rebuilt by the code from the inputs" } };
    try {
      const r = await getJSON("api/publish_hf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repo, package: { record: D.record, investigation: slim } }) });
      out.innerHTML = `Published: <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.repo)}/${esc(r.path)}</a>`;
    } catch (e) { out.textContent = e.message; }
  };
}

/* ------------------------------------------------------------ the citizen lab study */
const STUDY_KEY = "chronos_study_v2";
const SD = { S: null, st: null, timer: null };
function sdLoad() { try { return JSON.parse(localStorage.getItem(STUDY_KEY) || "null"); } catch (e) { return null; } }
function sdSave() { try { localStorage.setItem(STUDY_KEY, JSON.stringify(SD.st)); } catch (e) { } }
async function renderStudy() {
  const box = $("#study"); if (!box) return;
  if (!SD.S) { try { SD.S = await getJSON("data/study.json"); } catch (e) { box.innerHTML = "<h3>The citizen study</h3><p class=\"small muted\">The study file is missing. Run scripts/build_static.py.</p>"; return; } }
  SD.st = SD.st || sdLoad();
  const S = SD.S, st = SD.st;
  if (!st) {
    box.innerHTML = `<h3>Join the citizen study</h3><p>${S.training.length} practice cases with feedback, then ${S.sequence.length} study cases. Everyone sees the same cases in the same order, and some come back, so answers can be pooled and consistency measured. About eight minutes.</p>
      <ol class="small">${S.instructions.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>
      <button class="btn" id="sdStart">Start the study</button> <span class="small muted">Nothing leaves your browser unless you download your answers.</span>`;
    $("#sdStart").onclick = () => { SD.st = { protocol: S.protocol, participant: Math.random().toString(36).slice(2, 10), step: 0, answers: [] }; sdSave(); renderStudy(); };
    return;
  }
  const items = [...S.training.map((c, i) => ({ c, training: true, i })), ...S.sequence.map((q) => ({ c: S.cases[q.case], case: q.case, repeat: q.repeat }))];
  if (st.step >= items.length) return studyResults();
  const it = items[st.step], c = it.c, n0 = S.training.length;
  box.innerHTML = `<h3>${it.training ? `Practice case ${st.step + 1} of ${n0}` : `Study case ${st.step - n0 + 1} of ${S.sequence.length}`}</h3>
    <div class="two-col"><div><canvas id="sdCv" width="220" height="220"></canvas><p class="small muted" id="sdLbl"></p></div>
    <div><p>What happened to the spot in the middle?</p><div class="cit-q" id="sdA">${S.answers.map((a) => `<button data-v="${a.key}">${esc(a.label)}</button>`).join("")}</div>
    <p>How sure are you?</p><div class="cit-q" id="sdC">${S.confidence.map((k) => `<button data-v="${k}">${esc(k)}</button>`).join("")}</div>
    <button class="btn" id="sdGo" disabled>Record and continue</button> <button class="btn ghost" id="sdQuit">Stop and clear</button><div id="sdOut"></div></div></div>`;
  const pick = { a: null, c: null }, t0 = performance.now();
  const wire = (id, k) => box.querySelectorAll(`#${id} button`).forEach((b) => b.onclick = () => { pick[k] = b.dataset.v; b.parentNode.querySelectorAll("button").forEach((x) => x.classList.toggle("btn", x === b)); $("#sdGo").disabled = !(pick.a && pick.c); });
  wire("sdA", "a"); wire("sdC", "c");
  let k = 0; clearTimeout(SD.timer);
  const tick = () => { const cv = $("#sdCv"); if (!cv) return; const v = c.visits[k % c.visits.length]; drawImage(cv, v.img, "plate"); $("#sdLbl").textContent = `visit ${v.visit}`; k++; SD.timer = setTimeout(tick, 650); };
  tick();
  $("#sdQuit").onclick = () => { if (confirm("Clear your study answers in this browser?")) { SD.st = null; try { localStorage.removeItem(STUDY_KEY); } catch (e) { } renderStudy(); } };
  $("#sdGo").onclick = () => {
    st.answers.push({ step: st.step, case: it.training ? null : it.case, training: !!it.training, repeat: !!it.repeat, answer: pick.a, confidence: pick.c, ms: Math.round(performance.now() - t0) });
    st.step++; sdSave();
    if (it.training) {
      $("#sdOut").innerHTML = `<p>${pick.a === c.truth ? "Right." : "Not this time."} The planted change here is <b>${esc(c.truth)}</b>${c.truth_sub ? ` (${esc(c.truth_sub)})` : ""}.</p><button class="btn ghost" id="sdNext">Next</button>`;
      $("#sdGo").disabled = true; $("#sdNext").onclick = renderStudy;
    } else renderStudy();
  };
}
function studyResults() {
  const S = SD.S, st = SD.st, box = $("#study"), ans = st.answers.filter((a) => !a.training);
  const first = {}; ans.filter((a) => !a.repeat).forEach((a) => first[a.case] = a.answer);
  const rep = ans.filter((a) => a.repeat && first[a.case] !== undefined), same = rep.filter((a) => a.answer === first[a.case]).length;
  const firsts = ans.filter((a) => !a.repeat), right = firsts.filter((a) => a.answer === S.cases[a.case].truth).length;
  const eng = S.cases.filter((c) => c.engine === c.truth).length, agree = firsts.filter((a) => a.answer === S.cases[a.case].engine).length;
  const byc = {}; firsts.forEach((a) => { const q = byc[a.confidence] ||= [0, 0]; q[0]++; q[1] += a.answer === S.cases[a.case].truth; });
  box.innerHTML = `<h3>Your study results</h3>
    <div class="two-col"><div><p>You matched the practice truth in <b>${right} of ${firsts.length}</b> cases. The engine matched it in <b>${eng} of ${S.cases.length}</b>. You agreed with the engine in ${agree} of ${firsts.length}.</p>
    <p>Repeated cases: you answered <b>${same} of ${rep.length}</b> the same way twice.</p>
    <p class="small">By confidence: ${Object.entries(byc).map(([k, v]) => `${esc(k)} ${v[1]} of ${v[0]}`).join(", ")}.</p></div>
    <div><table><tr><th>Case</th><th>You</th><th>Engine</th><th>Truth</th></tr>${firsts.map((a) => { const c = S.cases[a.case]; return `<tr><td>${esc(c.id)}</td><td>${esc(a.answer)}</td><td>${esc(c.engine)}</td><td>${esc(c.truth)}</td></tr>`; }).join("")}</table></div></div>
    <p><button class="btn" id="sdDl">Download my answers</button> <button class="btn ghost" id="sdAgain">Start again</button></p>
    <p class="small muted">To pool many participants: collect the downloaded files and run python scripts/analyse_citizen_study.py answers/*.json. It gives Fleiss kappa, test retest consistency, and crowd against engine against truth. One person is not a study.</p>`;
  $("#sdDl").onclick = () => download(`chronos_study_${st.participant}.json`, JSON.stringify({ protocol: st.protocol, participant: st.participant, answers: st.answers }, null, 1));
  $("#sdAgain").onclick = () => { SD.st = null; try { localStorage.removeItem(STUDY_KEY); } catch (e) { } renderStudy(); };
}

/* ------------------------------------------------------------ the whole sky in tiles */
const TL = { T: null, layer: "corrected_rate" };
function moll(raDeg, decDeg) {
  let lon = ((180 - raDeg + 540) % 360) - 180; // RA grows to the left, RA 180 in the middle, RA 0 at the edge
  lon *= Math.PI / 180; const phi = decDeg * Math.PI / 180;
  let th = phi; for (let i = 0; i < 30; i++) { const f = 2 * th + Math.sin(2 * th) - Math.PI * Math.sin(phi), d = 2 + 2 * Math.cos(2 * th); if (Math.abs(d) < 1e-9) break; th -= f / d; }
  return [2 * Math.SQRT2 / Math.PI * lon * Math.cos(th), Math.SQRT2 * Math.sin(th)];
}
async function renderTiles() {
  const box = $("#tiles"); if (!box) return;
  if (!TL.T) { try { TL.T = await getJSON("data/sky_tiles.json"); } catch (e) { box.innerHTML = '<p class="small muted">The tile file is missing. Run python scripts/make_sky_tiles.py.</p>'; return; } }
  const T = TL.T, S = T.summary;
  const L = { corrected_rate: "Corrected rate (per square degree)", raw_rate: "Raw rate (per square degree)", true_rate: "Planted rate, the practice truth", visits: "Visits (depth of the scan)", completeness: "Completeness of its kind of tile", null_called: "False alarms in the null twin" };
  box.innerHTML = `<div class="two-col"><div><label>Layer <select id="tlL">${Object.entries(L).map(([k, v]) => `<option value="${k}" ${k === TL.layer ? "selected" : ""}>${v}</option>`).join("")}</select></label>
    <canvas id="tlCv" width="760" height="400" style="width:100%;max-width:760px"></canvas><p class="small muted" id="tlHover">Point at a tile.</p></div>
    <div><p>Summed over ${S.tiles} tiles, the raw count gives <b>${pct(S.raw_over_true, 0)}</b> of the planted changes; after the correction, <b>${pct(S.corrected_over_true, 0)}</b>. ${pct(S.within_two_errors, 0)} of the tiles agree with the truth within two errors.</p>
    <table><tr><th>Kind of tile</th><th>Tiles</th><th>Completeness</th><th>Raw / truth</th><th>Corrected / truth</th></tr>${Object.entries(S.by_class || {}).map(([k, q]) => `<tr><td>${esc(k.replace("_", ", "))}</td><td>${q.tiles}</td><td>${pct(q.completeness, 0)}</td><td>${q.raw_over_true == null ? "" : pct(q.raw_over_true, 0)}</td><td>${q.corrected_over_true == null ? "" : pct(q.corrected_over_true, 0)}</td></tr>`).join("")}</table>
    <p class="small">Why correct? A tile with more visits finds more, and a crowded tile finds less. Without the correction, a map of changes is a map of the survey. On the real sky, the completeness comes from injection into real exposures and the false alarms from fields with no expected change.</p>
    <p class="small muted">${esc(S.note)}</p></div></div>`;
  $("#tlL").onchange = (e) => { TL.layer = e.target.value; drawTiles(); };
  drawTiles();
  const cv = $("#tlCv");
  cv.onmousemove = (ev) => {
    const r = cv.getBoundingClientRect(), x = (ev.clientX - r.left) * cv.width / r.width, y = (ev.clientY - r.top) * cv.height / r.height;
    const hit = (TL.paths || []).find((p) => cv.getContext("2d").isPointInPath(p.path, x, y));
    $("#tlHover").textContent = hit ? `Tile ${hit.t.id} at RA ${num(hit.t.ra, 1)}, Dec ${num(hit.t.dec, 1)} (ecliptic latitude ${num(hit.t.elat, 0)}, galactic ${num(hit.t.glat, 0)}): ${hit.t.visits} visits, ${hit.t.n_stars} stars, ${hit.t.planted} planted, ${hit.t.called} called, null twin ${hit.t.null_called}, completeness of its kind (${esc((hit.t.class || "").replace("_", ", "))}) ${pct(hit.t.completeness ?? 0, 0)}.` : "Point at a tile.";
  };
}
function drawTiles() {
  const cv = $("#tlCv"), g = cv.getContext("2d"), T = TL.T.tiles, key = TL.layer, W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const sx = (W - 20) / (4 * Math.SQRT2), sy = (H - 20) / (2 * Math.SQRT2), X = (p) => W / 2 + p[0] * sx, Y = (p) => H / 2 - p[1] * sy;
  const vals = T.map((t) => t[key] ?? 0), hi = Math.max(...vals, 1e-9);
  const ramp = (v) => { const a = Math.max(0, Math.min(1, v / hi)); const c0 = [251, 248, 242], c1 = key === "visits" ? [93, 87, 99] : [110, 86, 131]; return `rgb(${c0.map((c, i) => Math.round(c + (c1[i] - c) * a)).join(",")})`; };
  TL.paths = [];
  T.forEach((t) => {
    let pts = t.outline.map(([ra, dec]) => moll(ra, dec));
    const xs = pts.map((p) => p[0]);
    if (Math.max(...xs) - Math.min(...xs) > 2 * Math.SQRT2) { const s = moll(t.ra, t.dec)[0] >= 0 ? 1 : -1; pts = pts.map((p) => [s * Math.abs(p[0]), p[1]]); }
    const path = new Path2D(); pts.forEach((p, i) => i ? path.lineTo(X(p), Y(p)) : path.moveTo(X(p), Y(p))); path.closePath();
    g.fillStyle = ramp(t[key] ?? 0); g.fill(path); g.strokeStyle = "#d8cfbf"; g.lineWidth = 0.8; g.stroke(path);
    TL.paths.push({ path, t });
  });
  g.beginPath(); g.ellipse(W / 2, H / 2, 2 * Math.SQRT2 * sx, Math.SQRT2 * sy, 0, 0, 2 * Math.PI);
  g.strokeStyle = "#5d5763"; g.lineWidth = 1; g.stroke();
  g.fillStyle = "#5d5763"; g.font = "13px 'EB Garamond', serif"; g.fillText(`${key.replace(/_/g, " ")}: 0 to ${num(hi, key === "completeness" ? 2 : 0)}`, 12, H - 8);
}

document.addEventListener("DOMContentLoaded", () => { renderStudy(); renderTiles(); });
