# SPHEREx M101 DR1 D2 real-data pilot

**Execution date:** 25 November 2026  
**Field:** M101 (RA 210.80227°, Dec +54.34895°)  
**Exposure:** 2025W19_2B_0346_1 · D2 · 2025-05-10 · 113.5826 s  
**Scope:** native calibration audit and exploratory, non-blind Jy injection/recovery on one detector exposure.

## Archive products and immutable identifiers

| Product | Archive URI | Bytes | SHA-256 |
|---|---|---:|---|
| Native Level-2 science MEF | https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_2B/l2b-v27-2026-198/2/level2_2025W19_2B_0346_1D2_spx_l2b-v27-2026-198.fits | 64,800,000 | `fba39ecd1930274aea655a744287908d6d677daeec59c8efe1ebbcffb844be90` |
| Spectral WCS | https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/spectral_wcs/cal-swcs-v5-2026-191/2/spectral_wcs_D2_spx_cal-swcs-v5-2026-191.fits | 33,312,960 | `0eb4e27f351e6161e21372818f9e811480a7ab8bab9295722f180791e151a463` |
| Solid-angle map | https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/solid_angle_pixel_map/cal-sapm-v3-2026-191/2/solid_angle_pixel_map_D2_spx_cal-sapm-v3-2026-191.fits | 16,652,160 | `231bcdab0aa31d0ee9c9349b10e6c871070bf3ed860b7dc799745c0f9d1c8bc0` |
| Absolute-gain map | https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/abs_gain_matrix/cal-agm-v8-2026-191/2/abs_gain_matrix_D2_spx_cal-agm-v8-2026-191.fits | 16,652,160 | `d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37` |

The science product is a native 2040 × 2040 Level-2 image in MJy/sr,
pipeline version 7.0.5, archive product version v27, processing batch
2026-198. Its IRSA science plane identifier is
`01a0cf8b-7b99-7cbb-bacf-f0572e021e16`.

The Spectral WCS and absolute-gain calibration products have exact foreign-key
links to this science plane in `spherex.provenance_input`. The TAP query
returned 14 input relations; its SHA-256 is
`6eba2bf33c5291940a61632eb297dcd940038aa5ac1d4c06a23f1124d78a41c0`.

The solid-angle map is a supplemental DR1/D2 product from the same calibration
processing date. It passed detector, grid, unit and integrity checks, but it
is **not** asserted to be a direct `provenance_input` child of the science
plane. Do not merge that auxiliary relationship with the exact provenance
links above.

## Native-MEF and calibration audit

The file-backed audit reported
`STRUCTURE_AND_COMPATIBILITY_CHECKS_PASS` and compatibility `compatible`.
The native MEF has aligned 2040 × 2040 IMAGE, FLAGS, VARIANCE and ZODI arrays.
Alternate WCS A and the science wavelength maps were inspected. CWAVE and
CBAND are native-grid 2040 × 2040 maps in micrometres; the wavelength audit
found no invalid pixels.

The absolute-gain map's archive MD5 and local SHA-256 were verified. A total
of 175 out of 4,161,600 pixels (0.00421%) were invalid or non-positive and
remain masked. They were not interpolated, and the gain map was not applied
again to the already calibrated Level-2 image.

## Position-dependent ePSF handling

The position-dependent ePSF was rendered as an 11 × 11 native-pixel stamp at
(x=1019.25, y=1020.75), preserving sub-pixel phase. The raw stamp is retained
unchanged; SHA-256:
`113cdbcc9387f94ce0987faf9fc093d88ec6139a741d244229fc1b3c84adf282`.

The raw stamp contained one small negative interpolation sample. Its
negative-to-positive peak fraction was 0.0001716175 (0.01716%), and its
integrated negative-to-positive flux fraction was 0.00008576184 (0.008576%).
Both are below the explicit 0.001 (0.1%) rejection limit. A separate
nonnegative, unit-sum stamp was written and hashed:
`6c4ef41635bcf5a6f5d105ba5ba8a82e8b41238e1e7bf5f010cc26d82882dafd`.
A non-finite stamp or material negative lobe still fails closed. No science,
variance, flag or calibration-map pixels are changed by this PSF-only
correction.

## Calibrated Jy injection/recovery

The experiment uses the measured VARIANCE, conservative photometry flag
policy, ZODI background model, the position-specific ePSF and the
detector-matched solid-angle map. Integrated source flux in Jy is converted
to the MJy/sr science-pixel domain using each pixel's solid angle. The
position-dependent detection template uses ePSF divided by pixel solid angle.

In the earlier deterministic baseline run (before the source-Poisson model was connected), the local nominal matched-filter 5-sigma reference sensitivity was
**0.000108396 Jy (108.396 microJy)**. Sixty deterministic source signals
were injected, 20 at each of three flux levels:

| Integrated flux | Recovered | Completeness | Wilson 95% interval |
|---:|---:|---:|---:|
| 54.198 microJy | 5 / 20 | 25% | 11.19%–46.87% |
| 108.396 microJy | 13 / 20 | 65% | 43.29%–81.88% |
| 216.792 microJy | 19 / 20 | 95% | 76.39%–99.11% |

Detection threshold was 5 sigma; the matching radius was 2.5 native pixels.
The injections were confined to a 100-pixel local region around the ePSF
reference position. Median astrometric offset was 0.7906 pixel; the
95th-percentile offset was 0.7906–1.0574 pixels across the flux bins.
There were 246 baseline detections in the full exposure and no unmatched new
peaks inside the evaluated local PSF region.

The machine-readable full injection report in the workflow artifact has
SHA-256
`78d102e4d54b1093c66fd6c863a435866d06b20668bd18c25ef0654caaede136`.
The native audit JSON has SHA-256
`e56c5601077e47c317aa01023b0866e608b7e0425e1dc4f801b48eb7ef417bf6`;
the overall field summary has SHA-256
`b2142a05ddb045a2560fec69f242c680261c55f87fd7ae27756b47bcf98d7f16`.

## Reproduction record for the earlier deterministic baseline

- Real-field audit and injection workflow: [GitHub Actions run 45614873760](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45614873760).
- Latest combined tests + real-field run: [GitHub Actions run 45614925600](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45614925600).
- The latter completed successfully on commit
  `91ac35a3799bfc8ed938e9aa0a99f6b5db27613c`; 248 tests passed with two
  warnings, and all real-field retrieval/audit steps passed.
- Workflow artifact ID: `15022161616`; artifact SHA-256:
  `cd56b93b0edc4e52d1220bd59636e827f7af6815914450e619c1cd31ef245d47`.
  The artifact contains original FITS inputs, ePSF stamps, and full JSON
  reports. GitHub Actions retains it for 30 days from upload.

## Scientific limits

This is one real exposure and one local detector zone. It is not a
multi-field or time-domain completeness estimate, and does not generalise to
the full detector or survey. The injected source signals are deterministic;
injection truth and seed were available to the evaluator, so this is **not**
a blind benchmark. Source Poisson variance was not added because a verified
exposure-specific electron-conversion record is not part of this evaluation.
The experiment is a standalone matched-filter pilot, not the Session 07
four-method CHRONOS benchmark and not evidence of comparative performance
advantage.

No population-level YSO result or astronomical discovery is claimed. A
predeclared SPLICES/DR1 coverage reconnaissance workflow is being developed
separately. An independent custodian-controlled blind benchmark, multi-field
calibration evaluation, preregistered YSO population analysis, and external
astronomical reproduction/review remain open. The validated scientific
release gate remains closed.


## Gain-derived source Poisson method — implementation record, superseded by the completed run below

The completeness numbers above belong to the earlier deterministic injection
run. They must not be reinterpreted as having included source Poisson noise.

A follow-on implementation now derives a detector-pixel conversion from the
same science exposure's exact provenance-linked absolute-gain product. For
an absolute-gain value
\(G_{abs,i}\) in \((\mathrm{MJy/sr})/(e^-/s)\), exposure time \(t\), and
Level-2 IMAGE surface brightness \(I_i\) in MJy/sr, the implementation uses

\[
C_i = t/G_{abs,i}
\]

in electrons per IMAGE unit. For an injected pixel signal \(s_i\), the
expected source electrons are \(\lambda_i=s_i C_i\). The added source
realization is a Poisson draw divided by \(C_i\), and the additional
variance in IMAGE units is \(\lambda_i/C_i^2\). The code retains invalid
or non-positive gain pixels as invalid and refuses to fill them.

The conversion record is bound to the native science and gain SHA-256 hashes,
the science OBSID, detector, exact FITS units, exposure time, archive URIs,
IRSA archive MD5 and the live \`spherex.provenance_input\` plane relation.
Because the derivation has not been signed off by an independent instrument
calibration reviewer, its status is
\`derived_pending_independent_review\`. The exploratory mode requires an
explicit opt-in and records \`independent_human_reviewed: false\`; it is
not allowed to masquerade as a verified calibration record.

At the time this implementation note was first added, the gain-derived source-
Poisson run had not yet completed. The runner and tests now record expected
electrons, realized electrons and the per-flux-bin variance increment. The
subsequent section, **Updated gain-derived source-Poisson run**, records the
completed real-data execution and supersedes that earlier pending status. The
60-source deterministic table above remains a separate historical baseline.

## Updated gain-derived source-Poisson run — 25 November 2026

The M101 real-field workflow was rerun after adding a provenance-bound per-pixel electron conversion and source shot noise. This newer run supersedes the deterministic injection counts above for the source-Poisson configuration; the earlier run is retained as a historical baseline, not merged with the new counts.

- Workflow: [GitHub Actions run 45622359188](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45622359188)
- Code revision: `1065d862877ef3fbea250d74f7a6f03f3c11eab8`
- Workflow conclusion: success; native MEF audit, direct calibration provenance, gain validation and Jy injection all completed.
- Companion full test suite: [run 45622372718](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45622372718), **269 passed, 12 warnings**.
- Artifact ID: `15026536639`; artifact SHA-256: `89e47150827c093dadd1fe8b8bcbb1273be15548b9a7f87c1eb1b8483eafce99` (GitHub Actions retention through 2026-12-25).
- Field summary SHA-256: `bbd7c33c73a98706dc673bb4183c59593ba679e8e30c98a87344fd185f01ae94`.
- Final native-MEF audit SHA-256: `58ab96630506cf3280569c60f50983ae6c3f5a1cca6e4306b8039a237979c8e4`.
- Full injection/recovery JSON SHA-256: `427d66e337b3840293fe2a913b1fb08c187a2db035c30b64c6311caca8552568`.

The native MEF/calibration compatibility result remained `compatible`. IRSA's live provenance query returned 14 input relations. The exact absolute-gain matrix link was verified with matching science and calibration plane IDs, matching native URIs, archive MD5 pass, calibration SHA-256 `d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37`, and provenance query SHA-256 `6eba2bf33c5291940a61632eb297dcd940038aa5ac1d4c06a23f1124d78a41c0`.

The conversion was calculated per detector pixel as exposure time divided by the absolute-gain matrix. Its valid fraction was 0.9999579489; 175 invalid/non-positive gain samples stayed masked. The existing Level-2 IMAGE data were not gain-corrected a second time. Source Poisson draws and their IMAGE-domain variance were added only to the injected sources. The conversion record is `derived_pending_independent_review`, with `review_status=pending`; no human reviewer or sign-off is claimed.

| Integrated injected flux | Recovered | Completeness | Wilson 95% interval |
|---:|---:|---:|---:|
| 54.198 microJy | 5 / 20 | 25% | 11.19%–46.87% |
| 108.396 microJy | 14 / 20 | 70% | 48.10%–85.45% |
| 216.792 microJy | 17 / 20 | 85% | 63.96%–94.76% |

The pre-injection local 5-sigma reference remains 108.396 microJy. This is a fixed-seed exploratory run of 60 simulated source signals in one local PSF region of one M101 D2 exposure. The source locations, input fluxes and random seed were available to the evaluator. It is **not blind**, not multi-field, not a four-method comparison, and not a survey-wide completeness curve. The ePSF's raw stamp is preserved; only the tiny below-threshold interpolation undershoot is clipped in a separate hashed stamp.

## Current scientific boundary

The gain-derived source-Poisson implementation has now passed its M101 real-data workflow and the full test suite at the revisions above. Its calibration derivation still requires independent human review before being labelled verified. The six-region multi-field Jy workflow is implemented, but its aggregate result must be checked before the multi-field gate is changed. The independent-custodian blind benchmark, YSO population analysis, independent astronomical reproduction/review and validated release gates remain unsatisfied.
