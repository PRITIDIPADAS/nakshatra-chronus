// CHRONOS 4D page. Reads data/lab/<field>.json (static site) or /api/lab (local server).
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));
const tbl = (head, rows) => "<table><tr>" + head.map(h => `<th>${h}</th>`).join("") + "</tr>" + rows.map(r => "<tr>" + r.map(c => `<td>${c}</td>`).join("") + "</tr>").join("") + "</table>";
let L = null, C = null, KEY = "demo";

async function get(key) {
  try { const r = await fetch(`data/lab/${key}.json`); if (r.ok) return r.json(); } catch (e) {}
  return (await fetch(`/api/lab?key=${key}`)).json();
}

function color(v) { // 0..1 to a plum ramp on paper
  const a = Math.max(0, Math.min(1, v)); return `rgb(${245 - 98 * a},${240 - 118 * a},${230 - 64 * a})`;
}
function diverge(z) { const a = Math.max(-1, Math.min(1, z / 5)); return a >= 0 ? `rgb(${245 - 64 * a},${240 - 129 * a},${230 - 136 * a})` : `rgb(${245 + 129 * a},${240 + 103 * a},${230 + 57 * a})`; }

function heat(cv, M, fn, state) {
  const nV = M[0].length, c = cv.getContext("2d"); cv.width = 102 * 6; cv.height = nV * 16;
  const fin = M.flat().filter(x => x != null), lo = Math.min(...fin), hi = Math.max(...fin);
  for (let ch = 0; ch < 102; ch++) for (let v = 0; v < nV; v++) {
    const x = M[ch][v], st = state ? state[ch][v] : "";
    c.fillStyle = st === "no data in DR1 cube" ? "#e9b9ae" : x == null ? "#e4ded3" : fn(x, lo, hi);
    c.fillRect(ch * 6, v * 16, 6, 16);
  }
  c.fillStyle = "#2e2a33"; for (let d = 1; d < 6; d++) c.fillRect(d * 17 * 6, 0, 1, cv.height);
}

function line(cv, xs, ys, es, zero) {
  const c = cv.getContext("2d"); cv.width = 612; cv.height = 160; c.clearRect(0, 0, 612, 160);
  const pts = xs.map((x, i) => [x, ys[i], es ? es[i] : 0]).filter(p => p[1] != null);
  if (!pts.length) { c.fillText("No measurements at this visit.", 10, 20); return; }
  const lo = Math.min(...pts.map(p => p[1] - p[2]), zero ? -5 : Infinity), hi = Math.max(...pts.map(p => p[1] + p[2]), zero ? 5 : -Infinity);
  const X = x => 30 + (x - 0.75) / 4.25 * 570, Y = y => 150 - (y - lo) / ((hi - lo) || 1) * 140;
  c.strokeStyle = "#ddd3c2"; if (zero) { c.beginPath(); c.moveTo(30, Y(0)); c.lineTo(600, Y(0)); c.stroke(); }
  c.fillStyle = "#937aa6"; c.strokeStyle = "#937aa6";
  pts.forEach(([x, y, e]) => { c.beginPath(); c.moveTo(X(x), Y(y - e)); c.lineTo(X(x), Y(y + e)); c.stroke(); c.fillRect(X(x) - 2, Y(y) - 2, 4, 4); });
  c.fillStyle = "#5d5763"; [1, 2, 3, 4, 5].forEach(t => c.fillText(t + " µm", X(t) - 8, 158));
}

function center(ch) { const B = {1: [0.75, 1.09], 2: [1.10, 1.62], 3: [1.63, 2.41], 4: [2.42, 3.82], 5: [3.83, 4.41], 6: [4.42, 5.00]}; const d = Math.floor((ch - 1) / 17) + 1, k = (ch - 1) % 17, [lo, hi] = B[d]; return lo * Math.pow(hi / lo, (k + 0.5) / 17); }

function drawSpec() {
  const s = C.spectral, v = +$("tslider").value; $("tlab").textContent = `visit ${s.visits[v] ?? "-"}`;
  const xs = [...Array(102).keys()].map(i => center(i + 1));
  line($("spec"), xs, s.flux.map(r => r[v]), s.sigma.map(r => r[v] ?? 0));
}

function show() {
  const s = C.spectral;
  heat($("heat"), s.flux, (x, lo, hi) => color((Math.log(Math.max(x, 1)) - Math.log(Math.max(lo, 1))) / ((Math.log(hi) - Math.log(Math.max(lo, 1))) || 1)), s.state);
  heat($("unc"), s.flux.map((r, i) => r.map((x, j) => x && s.sigma[i][j] ? s.sigma[i][j] / Math.abs(x) : null)), (x, lo, hi) => color((x - lo) / ((hi - lo) || 1)), s.state);
  $("tslider").max = Math.max(0, s.visits.length - 1); drawSpec();
  const xs = [...Array(102).keys()].map(i => center(i + 1)); line($("dz"), xs, s.difference_z_first_last || [], null, true);
  $("stab").innerHTML = `<p><b>Spectral stability score</b> ${s.stability.score ?? "–"} (reduced χ² ${s.stability.reduced_chi2 ?? "–"} on ${s.stability.dof} degrees of freedom). ${s.stability.meaning}
    Gray scale per visit: ${s.gray_scale.map(g => g ?? "–").join(", ")}. <b>Spectral residual court:</b> ${s.sampling_court.explained} of ${s.sampling_court.tested} channel differences are within what wavelength sampling and noise allow.</p>` +
    s.warnings.map(w => `<div class="warn">${esc(w)}</div>`).join("");
  $("feat").innerHTML = "<b>Emission and absorption explorer</b> " + s.features.map(f => `<span class="pill" title="${esc(f.kind)}">${f.um} µm ${esc(f.name)} · ${f.blank ? "falls in blank channel" : f.measured ? "sampled" : "not sampled"}</span>`).join("");
  const F = C.forensics;
  $("for").innerHTML = `<p><b>${esc(F.explanation)}</b></p>` + tbl(["Module", "Question", "Measured", "Verdict", "Official product to confirm"], F.modules.map(m =>
    [esc(m.module), esc(m.question), esc(m.measured), `<span class="v-${m.verdict.split(" ")[0]}">${esc(m.verdict)}</span>`, `<code>${esc(m.product)}</code>`]));
  const U = C.uncertainty; $("unc2").innerHTML = tbl(["Detection", "Position", "Motion", "Brightness", "Spectral", "Interpretation"], [[U.detection, U.position, U.motion, U.brightness, U.spectral, U.interpretation].map(esc)]);
  $("ice").innerHTML = tbl(["Feature", "µm", "τ", "±", "Blended with", "Note"], C.ice.map(i => [esc(i.feature), i.um, i.tau ?? "–", i.tau_err ?? "–", esc(i.blended_with.join(", ") || "–"), esc(i.note)]));
  const O = C.optimizer;
  $("opt").innerHTML = `<p>Prior entropy ${O.prior_entropy_bits} bits over ${O.hypotheses.join(", ")}. <b>Recommended: ${esc(O.recommended.option)}.</b> Why: ${esc(O.recommended.why)}</p>` +
    tbl(["Option", "Observable", "Expected information (bits)", "Why"], O.ranked.map(o => [esc(o.option), esc(o.observable), `${o.bits}<span class="bar" style="width:${Math.round(o.bits * 200)}px"></span>`, esc(o.why)])) +
    (O.visibility ? `<p>Ecliptic longitude ${O.visibility.ecliptic_lon}°, latitude ${O.visibility.ecliptic_lat}°. Approximate SPHEREx windows in 2027: ${O.visibility.next_windows_2027.join(" and ")}. ${esc(O.visibility.note)}</p>` : "");
  const P = C.passport;
  $("pass").innerHTML = `<p>Seal <code>${P.seal}</code></p><p>Sections: ${Object.entries(P.section_sha256).map(([k, v]) => `<span class="pill">${k} ${v.slice(0, 10)}…</span>`).join("")}</p>
    <p><button class="btn" id="dl">Download passport JSON</button> <button class="btn ghost" id="vf">Verify in this browser</button> <span id="vfo"></span></p>
    <p class="note">Command line: <code>sha256sum data/lab/passport_${KEY}_${C.id}.json</code> must print the seal. Or <code>python scripts/verify_passport.py file.json</code>.</p>`;
  $("dl").onclick = () => save(`passport_${KEY}_${C.id}.json`, JSON.stringify(P, null, 1), "application/json");
  $("vf").onclick = verify;
}

async function verify() {
  try {
    const t = await (await fetch(`data/lab/passport_${KEY}_${C.id}.json`)).arrayBuffer();
    const h = [...new Uint8Array(await crypto.subtle.digest("SHA-256", t))].map(b => b.toString(16).padStart(2, "0")).join("");
    $("vfo").innerHTML = h === C.passport.seal ? "✓ the bytes match the seal" : "✗ mismatch: " + h;
  } catch (e) { $("vfo").textContent = "Run the static site to verify the published bytes."; }
}

function save(name, text, type) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name; a.click(); }

function fieldWide() {
  $("identity").textContent = L.identity; $("stamp").textContent = L.label || "SIMULATION";
  const R = L.releases;
  $("rel").innerHTML = `<p>Releases in this investigation: <b>${R.releases.join(", ")}</b>. ${esc(R.verdict)} ${esc(R.rule)}</p>` +
    tbl(["Release", "SIA collections", "Searchable", "PSF", "Note"], Object.entries(L.release_table).map(([k, r]) => [k.toUpperCase(), (r.collections || []).join(", ") + (r.cube ? `, cube: ${r.cube}` : ""), r.searchable ? "yes" : "no", r.psf, esc(r.note)])) +
    `<p>Default live collections now: <code>${L.default_collections}</code>.</p>`;
  $("impact").innerHTML = tbl(["Processing stage", "Count"], L.calibration_impact.map(s => [esc(s.stage), s.count]));
  const X = L.planetx, pp = X.published_pair;
  $("px").innerHTML = `<p><b>Published IRAS–AKARI pair</b> (${pp.status}): separation ${pp.separation_arcmin} arcmin over ${pp.baseline_years} years, ${pp.rate_deg_per_yr}° per year. A circular orbit with that rate would be at about ${pp.circular_orbit_distance_au} au. ${esc(pp.falsification)}</p>` +
    tbl(["Distance (au)", "Parallax shift in 6 months (arcsec)", "Orbital motion (arcsec/yr)", "SPHEREx pixels in 6 months"], X.motion_sensitivity.map(r => [r.d_au, r.parallax_arcsec_6mo, r.orbit_arcsec_per_yr, r.spherex_pixels_6mo])) +
    `<p><b>Survey selection</b> under stated assumptions (${esc(X.selection.model)}): brighter than V 21 for ${Math.round(100 * X.selection.fraction_brighter_than_V21)} percent of orbit positions, V 24 for ${Math.round(100 * X.selection.fraction_brighter_than_V24)} percent. ${esc(X.selection.meaning)}</p><p>Ladder: ${X.ladder.join(" → ")}.</p>`;
  const V = L.validation, F = V.fdr;
  let v = `<p><b>False-discovery control</b> (Benjamini–Hochberg, q = ${F.q}): ${F.kept} of ${F.tested} candidates kept. Expected false candidates per empty field: ${V.expected_by_chance}. ${esc(V.chance_note)}</p>`;
  if (V.real_vs_simulated) { const r = V.real_vs_simulated; v += `<p><b>Real versus simulated.</b> Real QR3 injection: ${r.real.found} of ${r.real.planted} recovered (${Math.round(100 * r.real.fraction)} percent, 95 percent interval ${r.real.interval.join(" to ")}). Simulated test fields: ${Math.round(100 * r.simulated_test_accuracy)} percent right when deciding. ${esc(r.lesson)}</p>`; }
  if (V.sensitivity) v += "<b>Sensitivity (simulated sky)</b>" + tbl(["Kind", "AB mag", "n", "found", "95% interval"], Object.entries(V.sensitivity).flatMap(([k, d]) => Object.entries(d).map(([m, x]) => [k, m, x.n, x.fraction, x.interval.join("–")])));
  const nc = V.negative_controls || {}; v += `<p><b>Negative controls:</b> static stars called moving ${nc.static_stars?.called_moving ?? "–"} of ${nc.static_stars?.tested ?? "–"}; null twin false candidates ${nc.null_twin?.candidates ?? "–"}; alignment stress ${nc.alignment_stress ? `${nc.alignment_stress.wcs_only} → ${nc.alignment_stress.anchored} → ${nc.alignment_stress.final}` : "–"}.</p>`;
  $("val").innerHTML = v;
  $("cases").innerHTML = tbl(["Case", "Kind", "Data", "Tests", "Status"], (L.cases || []).map(c => [esc(c.name), esc(c.kind), esc(c.data), esc(c.tests.join("; ")), esc(c.status)]));
  $("gloss").innerHTML = tbl(["English", "বাংলা"], L.glossary.map(([e, b]) => [e, b]));
}

async function pick(key) {
  KEY = key; L = await get(key); fieldWide();
  $("cand").innerHTML = L.candidates.map((c, i) => `<option value="${i}">${c.id} · ${c.verdict || "unknown"}</option>`).join("");
  if (!L.candidates.length) { $("for").textContent = "This field has no candidates: a valid result."; return; }
  C = L.candidates[0]; show();
}

(async () => {
  let keys = ["demo", "barnard", "epsindib", "wise0855", "rwaur", "rdra", "quiet"];
  try { const r = await fetch("data/fields/index.json"); if (r.ok) keys = (await r.json()).map(x => x.key); } catch (e) {}
  $("field").innerHTML = keys.map(k => `<option>${k}</option>`).join("");
  $("field").onchange = e => pick(e.target.value);
  $("cand").onchange = e => { C = L.candidates[+e.target.value]; show(); };
  $("tslider").oninput = drawSpec;
  $("csv").onclick = () => {
    const s = C.spectral, rows = ["channel,center_um,visit,lam_um,flux_uJy,sigma_uJy,state"];
    for (let ch = 0; ch < 102; ch++) s.visits.forEach((v, j) => rows.push([ch + 1, center(ch + 1).toFixed(4), v, s.lam[ch][j] ?? "", s.flux[ch][j] ?? "", s.sigma[ch][j] ?? "", s.state[ch][j]].join(",")));
    save(`spectral_history_${KEY}_${C.id}.csv`, rows.join("\n"), "text/csv");
  };
  pick(keys[0]);
  try {
    const R = await (await fetch("data/real_data_run.json")).json(), S = R.steps, out = [];
    out.push(`<p>Run ${esc(R.started)}: ${Object.entries(R.summary).map(([k, v]) => `<span class="pill">${v ? "✓" : "✗"} ${k}</span>`).join("")}</p>`);
    if (S.sia_counts_by_release?.ok) out.push(tbl(["Place", "DR1", "DR1 deep", "QR3", "QR3 deep", "DR1 cube"], Object.entries(S.sia_counts_by_release.result).map(([k, v]) => [k, ...["spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep", "spherex_dr1_cube"].map(c => v[c]?.n ?? "–")])));
    const cu = S.dr1_cube_spectrum; if (cu?.ok) { const r = cu.result; out.push(`<p><b>DR1 All-Sky Cube at RW Aurigae</b> (${esc(r.access_url.split("/").pop())}, ${r.shape.join(" × ")}): ${r.finite_channels} of 102 channels hold a value at this pixel; BLANKCH = ${esc(r.BLANKCH)}. ${esc(r.note)} Plot: surface brightness by channel (gaps are missing, never filled).</p>`);
      line($("cube"), [...Array(102).keys()].map(i => center(i + 1)), r.flux_MJy_sr, null); }
    const sp = S.splices_near_rwaur; if (sp?.ok) out.push(`<p><b>SPLICES</b> table <code>${esc(sp.result.tables.join(", "))}</code>: ${sp.result.n} ice-target sources within 0.25° of RW Aurigae.</p>`);
    const ca = S.calibration_products_dr1_detector1; if (ca?.ok) out.push("<b>Official calibration products found</b>" + tbl(["Product", "Files", "Example"], Object.entries(ca.result).map(([k, v]) => [esc(k), v.n ?? esc(v.error), v.files?.[0] ? `<code>${esc(v.files[0].split("/").pop())}</code>` : "–"])));
    const he = S.helium_template_stats; if (he?.ok) out.push(`<p><b>Helium template, detector 1</b>: median ${he.result.IMAGE?.median}, 99th percentile ${he.result.IMAGE?.p99?.toFixed(3)}: the stripe pattern the Helium Emission test compares against.</p>`);
    const at = S["3i_atlas_spherex_coverage"]; if (at?.ok) out.push("<b>3I/ATLAS</b>, JPL Horizons positions and SPHEREx images within 0.02°" + tbl(["Date", "RA", "Dec", "Images"], at.result.map(x => [x.date, x.ra ?? "–", x.dec ?? "–", x.images_within_0p02deg ?? esc(x.error)])));
    $("realout").innerHTML = out.join("");
  } catch (e) { $("cube").style.display = "none"; }
})();
