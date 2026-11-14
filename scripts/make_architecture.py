"""Write frontend/architecture.svg: the CHRONOS data flow, from archive files to the evidence report."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1200, 860
C = dict(paper="#f5f0e6", card="#fbf8f2", ink="#2e2a33", ink2="#5d5763", line="#ddd3c2", sage="#7d9a8a", slate="#7489ad", plum="#937aa6",
         ochre="#c4a061", brick="#b56f5e", rose="#c08a86")
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="EB Garamond, Garamond, Georgia, serif">',
       f'<rect width="{W}" height="{H}" fill="{C["paper"]}"/>',
       '<style>@font-face{font-family:"EB Garamond";src:url(fonts/eb-garamond-latin-400-normal.woff2) format("woff2");font-weight:400}'
       '@font-face{font-family:"EB Garamond";src:url(fonts/eb-garamond-latin-600-normal.woff2) format("woff2");font-weight:600}</style>',
       '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#5d5763"/></marker></defs>']


def box(x, y, w, h, title, lines=(), col="slate", fill=None):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill or C["card"]}" stroke="{C[col]}" stroke-width="1.6"/>')
    out.append(f'<text x="{x + 12}" y="{y + 24}" font-size="18" font-weight="600" fill="{C["ink"]}">{title}</text>')
    for i, t in enumerate(lines):
        out.append(f'<text x="{x + 12}" y="{y + 46 + 19 * i}" font-size="15" fill="{C["ink2"]}">{t}</text>')


def arrow(x1, y1, x2, y2, dash=False):
    out.append(f'<path d="M{x1} {y1}L{x2} {y2}" stroke="#5d5763" stroke-width="1.4" fill="none" marker-end="url(#ar)"{" stroke-dasharray=\"5 4\"" if dash else ""}/>')


def band(y, h, label):
    out.append(f'<text x="18" y="{y + h / 2}" font-size="15" font-style="italic" fill="{C["plum"]}" transform="rotate(-90 18 {y + h / 2})" text-anchor="middle">{label}</text>')
    out.append(f'<line x1="34" y1="{y}" x2="34" y2="{y + h}" stroke="{C["line"]}" stroke-width="2"/>')


out.append(f'<text x="44" y="38" font-size="28" fill="{C["ink"]}">Nakshatra CHRONOS: from archive files to an evidence report</text>')
band(60, 120, "inputs")
box(44, 60, 330, 120, "SPHEREx QR2 and QR3 at IRSA", ["SIA2 search, cutout service", "IMAGE · FLAGS · VARIANCE · ZODI", "PSF · WCS-WAVE · WCS A detector map", "six arrays, 102 channels, 0.75 to 5 micron"], "slate")
box(390, 60, 230, 120, "Gaia DR3", ["positions, motions, parallaxes", "star anchors and gains", "catalog cross match"], "sage")
box(636, 60, 230, 120, "AllWISE and JPL", ["AllWISE overlay (IRSA TAP)", "known small bodies", "(JPL sb_ident) in live mode"], "sage")
box(882, 60, 290, 120, "Practice sky with a hidden truth", ["same SPHEREx rules, planted movers,", "variables, transients and camera", "effects: glitch, hot pixel, crosstalk"], "plum")
band(200, 120, "prepare")
steps = [("Noise check", ["VARIANCE against", "empty sky"]), ("Star anchors", ["Gaia shift of", "every exposure"]), ("One grid", ["resample all", "exposures"]),
         ("Star gain", ["ensemble ratio", "per exposure"]), ("Guardian", ["release and", "gain steps"]), ("Fair pairs", ["same array, color", "within 0.35 channel"])]
for i, (t, ls) in enumerate(steps):
    x = 44 + i * 189
    box(x, 200, 175, 100, t, ls, "ochre")
    if i:
        arrow(x - 14, 250, x - 2, 250)
for x in (209, 505, 751, 1027):
    arrow(x, 182, min(max(x, 130), 1100), 198)
band(340, 150, "detect")
box(44, 340, 360, 150, "P · catalog method", ["matched filter in each visit", "PSF centroids, link across visits", "motion court, brightness, presence", "astrometric and photometric floors"], "sage")
box(420, 340, 360, 150, "D · difference method", ["fair co adds of two visits", "Z = (I2 − I1) / √(σ1² + σ2² + (f s)²)", "f measured on stars, summed over arrays", "dipoles mark small motions"], "slate")
box(796, 340, 376, 150, "A · anomaly ensemble", ["each exposure against fair partners", "eight time features per pixel", "isolation forest, local outlier factor,", "robust covariance; spread kept"], "plum")
for x in (224, 600, 984):
    arrow(x, 302, x, 338)
band(510, 170, "reason")
box(44, 510, 250, 170, "Candidates", ["union of P, D and A", "agreement pattern kept", "fingerprint of 22 features"], "ink")
box(310, 510, 250, 170, "Five hypotheses", ["H1 moving · H2 variable", "H3 transient · H4 artefact", "H5 no change or unknown", "calibrated on 400 fields"], "plum")
box(576, 510, 290, 170, "Self questioning", ["tests not used to decide:", "star drift, leave one visit out,", "catalog motion, dichroic partner,", "detector position, crosstalk"], "brick")
box(882, 510, 290, 170, "Counterfactuals and debate", ["rerun with other choices:", "flags, background, noise, anchors,", "PSF, each visit out, threshold", "three analysts with their own data"], "rose")
for x in (224, 600, 984):
    arrow(x, 492, 169 if x == 224 else x, 508)
arrow(296, 595, 308, 595)
arrow(562, 595, 574, 595)
arrow(868, 595, 880, 595)
band(700, 140, "deliver")
box(44, 700, 560, 140, "Evidence report and observatory", ["every sentence points to a measurement", "sky and time explorer, temporal cube, difference microscope,", "dossier, motion map, population map, Planet X lab, citizen lab"], "slate")
box(620, 700, 552, 140, "Validation and black box", ["completeness, confusion, calibration, adversarial artefacts,", "empty fields, static stars, time shuffle, alignment stress", "SHA 256 seal of inputs, thresholds, versions, outputs"], "sage")
arrow(169, 682, 169, 698)
arrow(1027, 682, 1027, 698)
out.append('<path d="M1172 120 C1195 300 1195 560 1172 610" stroke="#937aa6" stroke-width="1.4" fill="none" stroke-dasharray="5 4" marker-end="url(#ar)"/>')
out.append(f'<text x="1180" y="380" font-size="14" fill="{C["plum"]}" transform="rotate(90 1180 380)">trains and scores</text>')
out.append("</svg>")
open(os.path.join(ROOT, "frontend", "architecture.svg"), "w").write("\n".join(out))
print("ok")
