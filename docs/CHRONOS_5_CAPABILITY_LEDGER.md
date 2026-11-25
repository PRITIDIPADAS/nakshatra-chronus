# CHRONOS 5.0 capability ledger — 25 November 2026

**Branch:** \`chronos-5-causal-sky-twin\`  
**Purpose:** single evidence-aware index of the 20-session workflow.  
**Rule:** software implementation, synthetic/contract tests, real-data execution and independent scientific acceptance are different states. A green CI run cannot promote an empirical or external gate.

## Status vocabulary

- **Implemented:** code or documented workflow exists.
- **Tested:** automated tests exercise the behaviour, usually with synthetic or contract fixtures.
- **Real-data pilot:** archive bytes were retrieved and a bounded exploratory run was performed.
- **Independent gate open:** an independent person, custodian, calibration review, preregistration service or reproduction is still required.
- **Not established:** no empirical evidence supports the claim yet.

## Twenty-session ledger

| Session | Capability / deliverable | Software status | Evidence status | Open condition |
|---|---|---|---|---|
| 01 | Research question, scope, assumptions, evidence rules | Research specification exists; this ledger closes the missing capability-index deliverable | Specification is documentation, not an empirical result | Reconcile project-wide README claims during release preparation |
| 02 | Versioned archive manifest, retrieval provenance, hashes | Committed four-product M101 metadata/checksum snapshot at [data/spherex_archive_manifest.M101_DR1_D2.json](../data/spherex_archive_manifest.M101_DR1_D2.json); retrieval/validation code in \`research_discovery/spherex/archive_manifest.py\`, schema and CLI | M101 native science and calibration products have archived URIs, byte counts and SHA-256; latest M101 evidence is linked below | Broaden immutable manifests to each planned field and retain all retrieval failures |
| 03 | Native FITS/MEF structural audit | Implemented in \`native_mef_audit.py\` and real-field runner | M101 DR1 D2 native MEF structure, aligned IMAGE/VARIANCE/FLAGS/ZODI and compatibility checks passed | Repeat on the intended full blind sample; one detector exposure is not general validation |
| 04 | Calibration compatibility and authoritative wavelength provenance | Implemented in compatibility matrix, archive lineage and CWAVE/CBAND wavelength gate | M101 spectral-WCS and absolute-gain exact provenance relations were checked; compatibility reported \`compatible\` | Independent instrument review of the gain-to-electron derivation is pending; never infer calibration from filename or detector alone |
| 05 | Sky-to-detector coordinate transform and landmark residuals | Transform code and unit/contract tests exist | No accepted independent real detector-landmark residual report is recorded in this tranche | Run against independently selected detector landmarks and publish residuals/covariance |
| 06 | Source-photon-noise model and Jy injection | Provenance-bound per-pixel electron conversion and Poisson injection implemented | M101 pilot and six-region D2 exploratory Jy pilot completed; strict six-field job is run #19 below | Gain-derived electron conversion is still \`derived_pending_independent_review\`; Lupus III 0/20 in every bin needs investigation |
| 07 | Common-input comparison: SNR-only, CHRONOS P/D/A, forensics, Sky–Detector Twin | Adapters, common-input signatures, metrics, matched operating points and field-group bootstrap implemented | Synthetic/contract tests only; no four-method result on common real held-out fields | Execute all four methods on identical exposures, masks, WCS, truth and frozen thresholds |
| 08 | Whole-field blind split, sealed truth, config freeze and unblinding | Encrypted truth store, opaque tokens, frozen config and Ed25519 custodian attestation checks implemented; runbook exists | No external custodian, immutable external preregistration receipt or actual blinded real-field run recorded | Independent custodian must prepare/sign and hold truth outside the analysis team before blind processing |
| 09 | Pixel-level Sky–Detector forward model | Controlled spectral exposure simulator with inspectable components, provenance and finite-exposure source-motion quadrature | Synthetic controlled-model tests; not calibrated SPHEREx raw readout | Obtain and model validated mission-specific PSF/response, readout, nonlinear, saturation, covariance and detector terms before calibration claims |
| 10 | Joint inference and identifiability | Finite-difference Jacobian, covariance whitening, SVD/rank/condition/nullspace and additional-measurement suggestions implemented | Synthetic and contract tests; local model/covariance assumptions supplied by operator | Validate likelihood/covariance from real data; local rank does not prove global identifiability |
| 11 | Falsification and predictive checks | Grouped residual, conditional parametric bootstrap, transient interval/family scan and counterfactual workflows implemented | Software tests only for the full suite | Full joint Bayesian posterior predictive over sky/detector/calibration is not implemented; candidate-family completeness needs independent custody/log attestation |
| 12 | Covariance-aware \(F(\lambda,t)\) reconstruction | Local GLS smoother, covariance propagation, shared calibration term, row provenance, null unsupported cells implemented | Synthetic/software tests only; no validated real source-level SPHEREx \(F(\lambda,t)\) result | Supply genuine source spectra/epochs and validated correlated calibration covariance; avoid wavelength/time confounding |
| 13 | Resolution-aware feature evolution | Equivalent-width/continuum uncertainty, LSF sampling diagnostics, blend screen and optional resolution-matched lab comparison implemented | Synthetic/software tests; no molecular identification | Need compatible real detector/release LSF, real spectra and independent feature review; no species claim by wavelength resemblance |
| 14 | Probabilistic source identity graph | Proper-motion/parallax propagation, local density/chance-coincidence model, alternatives and no-match probability implemented | Synthetic/software tests; no confirmed counterpart identity | Validate real catalogue covariance, epochs, selection, crowding and independent identity |
| 15 | Candidate-specific next observation | Expected information gain, prior sensitivity and externally sourced feasibility-record checks implemented | No telescope visibility or archive-availability result authenticated in this record | Supply fitted physical forecasts and a verified external calculator record; no telescope command/scheduling claim |
| 16 | Evidence graph and reproducible investigation package | Claim graph, provenance manifest, ZIP export, member hash and ZIP verification implemented | Software tests; no second-person reproduction from original real archive files recorded | Independent researcher must reproduce exact result from original files and environment |
| 17 | Four linked scientific workspaces and visualisation | Causal Investigation, Spectral Evolution, Cosmic Identity Network and Experimental Observatory exist in site/frontend; API routes and interaction tests exist | Front-end syntax and static/contract tests; no independent browser-accessibility/e2e acceptance report | Browser e2e, keyboard/accessibility and researcher usability review; scientific values must remain API-sourced |
| 18 | Real-data blind four-baseline evaluation | Evaluator and blind handoff infrastructure implemented | **Not satisfied** | Real held-out fields, all four executed detector outputs, external registration/custodian, frozen config, negative controls, ablations and paired group bootstrap required |
| 19 | One population-level YSO physics study | SPLICES/DR1/QR3 reconnaissance, SIAv2 spherical source-to-product association, exact per-source archive-product manifest, same-epoch feature/continuum coverage gates, calibration-group checks, exposure-ratio validation and digest-bound rate API implemented; rates pool signed completeness-corrected science-minus-control counts over summed area×time before applying the non-negative boundary | Archive metadata association is implemented; no validated source photometry, usable temporal series, selection-corrected YSO population estimate or discovery | Extracted/calibrated source flux, spectral quality, usable epochs, independent classifications, multidimensional selection/completeness, external preregistration and independent review required |
| 20 | Independent reproduction, paper and scientific release | Reproduction package and release documentation scaffolding exist | **Not satisfied; release gate remains closed** | External researcher review/reproduction, passed blind benchmark, resolved calibration review, validated population study and paper based only on measured results |

## Current verified real-data evidence

### M101 DR1 D2

The committed [four-product archive manifest](../data/spherex_archive_manifest.M101_DR1_D2.json) records the science MEF, exact spectral-WCS and absolute-gain provenance inputs, and the supplemental solid-angle map. It contains source URIs, archive plane IDs, byte counts, SHA-256 and archive MD5s where available. The four FITS binaries remain in the retained GitHub Actions artifact rather than being duplicated in Git. The manifest does not claim a direct provenance foreign key for the solid-angle map.

- Latest completed combined test/M101 workflow: [push run #967 / 45657439621](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45657439621), commit f5fe73471c83d1e9639ebf204abbf139ae01da77; the matching [PR run #968 / 45657453959](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45657453959) also passed.
- Test job: **334 passed, 7 warnings**; node --check frontend/causal-lab.js and node --check site/causal-lab.js both passed.
- M101 job: native archive retrieval, FITS compilation, file-backed MEF/calibration audit, provenance/hash validator and artifact upload all passed. Artifact 15044246564 is 91,213,914 bytes with SHA-256 9dfdb529b62f131864f9b7db5712896459edb3fa9f68eddf6cb917b190a18db2.
- Artifact 15041901578: 91,213,914 bytes; ZIP SHA-256 \`7f0451a82e979d1abd3c77e9a433f44fefd3e51a09470fd18a99a8f0e7b20e4f\`.
- Science exposure: M101, SPHEREx DR1 D2, observation \`2025W19_2B_0346_1\`, 113.5826 s, 2040 × 2040, pipeline 7.0.5.
- Exact Spectral-WCS and absolute-gain provenance links were verified; the solid-angle map is supplemental, not mislabelled as a direct pipeline input. Invalid gain pixels remain masked.
- Source-Poisson Jy recoveries: 5/20, 14/20 and 17/20 at 54.198, 108.396 and 216.792 µJy. One exposure and a local injection zone only.
- Gain-to-electron conversion is still \`derived_pending_independent_review\`; automated file/compatibility checks are not instrument-calibration sign-off.

### Six-region D2 calibrated-Jy pilot

- Strict six-region workflow: [run 45639895735](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45639895735), workflow run #19.
- Six predeclared fields returned and completed, zero incomplete; exact field manifest/roles and unique science observations/hashes validated.
- Final aggregate gate: \`valid=true\`, no errors, all six named fields verified and aggregate report SHA-256 \`26e237fec2b0e1f5571dd5e527c009a5a2d3de44186c4a240bf63ac4b9bb64e6\`.
- Artifact 15036382990: ZIP SHA-256 \`09978b42c6d626f65fe385d7d004c4a5d120ac7302ae06d8831f231e3dc65a35\`.
- Lupus III recovered 0/20 at all three flux bins. Retain it as an adverse anomaly; do not average it away or claim validated sensitivity.
- Exploratory, non-blind, one D2 exposure per region, not a four-method comparison. Gain review remains pending.

### SPLICES / DR1 / QR3 reconnaissance

- [Run 45648715196](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45648715196) completed the six-region archive/candidate reconnaissance.
- 16,663 catalogue rows, 2,421 candidate rows, 6,214 DR1/QR3 Level-2 SIAv2 products, 924,443 geometric candidate–product polygon matches, and 32 All-Sky Cube metadata records for the six predeclared cones.
- The SIAv2 polygon match establishes coordinate-in-footprint overlap only. It is not extracted source flux, spectral quality, usable epochs, cadence, light curves or a YSO discovery.
- The six-cone cube query is not a full-sky inventory; no native cube data were downloaded.

## Current scientific gates

| Gate | Status |
|---|---|
| M101 one-exposure calibration compatibility and source-Poisson Jy pilot | Completed exploratory real-data pilot; independent gain-conversion review pending |
| Six-region calibrated-Jy injection/recovery | Completed exploratory run with strict final manifest/hash/check gate; Lupus III anomaly open |
| Sessions 07–11 software infrastructure | Implemented and contract-tested; real blind benchmark not done |
| Sessions 12–16 software infrastructure | Implemented and synthetic/contract-tested; real source-specific results and independent reproduction not done |
| Four-baseline blind benchmark on genuine held-out SPHEREx fields | Not satisfied |
| Population-level YSO discovery / selection-corrected estimate | Not satisfied |
| Independent astronomical reproduction / researcher review | Not satisfied |
| Validated CHRONOS scientific release | Not satisfied; keep release gate closed |

## Required independent actions

The following cannot be truthfully completed by repository code or by the developer acting alone:

1. An instrument/calibration expert must review and sign the gain-to-electron conversion and Level-2 noise conventions.
2. A genuinely independent custodian must externally register the protocol before inspecting/releasing holdout truth, keep the keys/truth separate, sign the attestation and supervise unblinding.
3. An astronomer/instrument researcher must reproduce the M101 and multi-field evidence from original archive data and review the methods.
4. Only after those steps may the real blind four-method comparison, population analysis and validated release gates be reconsidered.

**Never upgrade an empirical gate from a test passing, an archive checksum, a generated signature, a source-footprint match, or a developer-written status document alone.**


## Source/product manifest update — 25 November 2026

The current implementation writes an exact `candidate_source_product_matches.csv` manifest per region and an all-region aggregate. Schema-1.1 source/product overlap is keyed by source ID plus archive product ID, not by a Level-2 plane ID inferred from SIAv2 metadata. Missing pair manifests fail closed as unavailable. This is still positional archive-product metadata: it does not establish source flux, spectral quality, independent temporal epochs or YSO identity.

Latest branch head at this edit: `fc64357658bc042fc27623b743ae7c7e08226116`. Full test/M101 and refreshed six-region YSO workflows were pending, so this is a code-state update only.


## Current-head verification — 25 November 2026

Current branch head at the time of this refresh: `84300c5ed225dc5ba190e8dac8b32650d37eafeb`.

- [Push workflow 45663142338](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663142338) completed successfully. The Python suite passed **338 tests with 7 warnings**; both JavaScript syntax checks passed. Its M101 DR1 D2 archive retrieval, native FITS/calibration compatibility audit, strict machine-readable evidence validator and artifact upload all passed.
- Companion [PR workflow 45663158946](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663158946) passed **338 tests with 12 warnings** and both JavaScript syntax checks.
- Current M101 artifact 15046223269 is 91,213,911 bytes; the locally downloaded ZIP SHA-256 exactly matched GitHub's digest: `5e7aeeeb79ff4f9b2ae8d97e9b56a0c3e47ee01c234dffd84c97ed29541747b0`. It contains the native science MEF, spectral-WCS, absolute-gain and solid-angle FITS products, audit records, archive manifest and calibrated-Jy injection report.
- The exact source-coordinate ambiguity fix is included in the 338-test run: invalid ICRS coordinates and duplicate source IDs with conflicting sky positions block source/product matching rather than silently selecting the first coordinate.
- Fresh SPLICES/DR1/QR3 source-to-product manifest workflow [45663142077](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663142077) is still in progress. The exact-roster six-field rerun [45663010413](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663010413) is also still in progress. They must not be described as completed until their reports/artifacts are available.

The previous six-region exploratory run [45639895735](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45639895735) remains complete and strict-gate verified. The current rerun adds exact roster acceptance. Both are non-blind one-exposure-per-region injection/recovery studies, not a four-method benchmark.


## Superseding current-head evidence — 25 November 2026

Current branch head: `3fdfd81ddd6e5d3dc2a7a58929a58eec2c2a41f3`.

- Push workflow [45670644445](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670644445): **342 tests passed, 12 warnings**, both JavaScript syntax checks passed, and M101 archive retrieval, native MEF/calibration audit, strict evidence validator and artifact upload passed.
- Companion PR workflow [45670657450](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670657450): **342 tests passed, 2 warnings**, both JavaScript syntax checks.
- M101 artifact 15050046463: 91,220,621 bytes; ZIP SHA-256 `032094d4a817960dc1780502166c9f380bb11f02251af1a7dd5acc923a55f6da`.
- SIAv2 reconnaissance workflow [45670644451](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670644451) completed successfully at the same head. Artifact 15049153600: 70,934,662 bytes; ZIP SHA-256 `1c517cc377bb0f4ae12191c9daf8cb7221dbf09053285cbc25dc98cfce488f4c`. Recon report SHA-256 `ee8909f6481a0467e2ecb250fc737d834975e16f139f8d0744bcb96d1723314f`; source/product inventory audit SHA-256 `2642ae27354ec72953f6438c1e8649112769ee807574567e8eb6eb33026da2ca`.
- Recon findings: 2,421 candidate rows and 2,421 unique source IDs; 6,214 SIAv2 spectral-image products (4,432 DR1 + 1,782 QR3); 32 cube metadata rows within six predeclared cones; 924,443 source/product pairs across the five star-forming-region cones. All six regional pair manifests passed exact inventory/provenance-integrity checks: zero duplicate pairs, unknown product IDs, pair metadata errors, per-source count mismatches or product-ID-set digest mismatches. Every pair is metadata-only with no extracted flux. The high-latitude comparison cone had zero candidate-source pairs, not a matched physical control sample.
- Per-region pair counts: Taurus/Auriga 84,669; Perseus/NGC 1333 68,086; Orion A 519,120; Rho Ophiuchi 186,980; Lupus III 65,588; high-latitude comparison 0.
- The source/product manifest is a spherical SIAv2 `s_region` positional association only. It does not establish calibrated source flux, spectrum quality, valid epoch cadence, variability or YSO identity.
- M101's new local-response diagnostic is described in [the peak-selection diagnostic note](SPHEREX_LOCAL_SNR_PEAK_SELECTION_DIAGNOSTICS_2026-11-25.md). It reports local maximum SNR samples, not detector-selected local maxima; it does not change production recovery.
- The earlier exact-roster six-field run [45663010413](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45663010413) completed with six requested/returned/completed fields, zero incomplete, exact manifest/roles and unique native observations/hashes. A newer per-injection SNR diagnostic rerun [45670018299](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45670018299) was still in progress at the time of this update; no outcome is claimed for that rerun.

No blind four-method result, independently approved gain-to-electron calibration, selection-corrected YSO population finding, independent astronomical reproduction or validated scientific release is established.


## Evidence refresh — 26 November 2026

**Code revision when this addendum was prepared:** `02e0d36445c0549f6473531cd01ed4fc78e443ec`. The branch continued to receive changes after the last fully validated SPHEREx commit; do not transfer an older test result to a newer revision without its own completed workflow.

### Verified current scientific evidence

- Full tests and real M101 audit on source-only diagnostic revision `44a96b3ae38e3a93d71687f50cb7accff5dbbeea`: [workflow 45685593266](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593266) completed successfully; **357 tests passed, 2 warnings**, and both JavaScript syntax checks passed. The M101 retrieval, native MEF/calibration audit and artifact upload passed. Artifact 15054464829 is 91,222,025 bytes; ZIP SHA-256 `64895b24b2ed030070b0474b9b000f8afa8d92d43599b90cbd1017ec3ccba46f`.
- M101 source-only component diagnostic: the formal combined-image recovery remains **5/20, 14/20, 17/20** at 0.5×, 1× and 2× local 5σ. Applying the production peak extractor separately to the injected-component image (`post-injection IMAGE − original IMAGE`) gives diagnostic counts **0/20, 8/20, 20/20**. The median source-only local maximum SNR values are 2.465, 4.906 and 9.056; corresponding combined-image local maximum SNR medians are 5.959, 8.140 and 11.150. The source-only image is evaluated with the original pre-injection VARIANCE map and is not the primary detection/completeness metric.
- Refreshed six-region archive-manifest validation: [workflow 45677731011](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45677731011) passed. Artifact 15052808730 is 70,934,685 bytes; ZIP SHA-256 `9fb16d20ff2a621a4882a61275efc3591921f942f3521404bbd9e5fd0a3af08b`. It contains 2,421 candidate sources, 924,443 exact source/product pairs and 6,214 SIAv2 product metadata rows. All six regional source/product manifest integrity audits report `available=true`, `valid=true`, and no errors. Per-region pair counts: Taurus/Auriga 84,669; Perseus/NGC 1333 68,086; Orion A 519,120; Rho Ophiuchi 186,980; Lupus III 65,588; high-latitude comparison 0. This validates metadata manifest integrity, not extracted source flux or cadence.
- The six-field primary calibrated-Jy exploratory pilot remains a completed result from [workflow 45674421060](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45674421060): 6/6 fields, 360 injections, 360 local-SNR rows, and the Lupus III zero-recovery flag retained. That artifact predates the source-only per-injection diagnostic and must not be treated as satisfying the new source-only aggregate gate.

### Current outstanding runs and scientific gates

The source-only six-field pilot on the newer aggregate-gated revision was queued as [workflow 45685593223](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685593223); no completed result or artifact was available when this addendum was written. An earlier source-only run on revision `930885e89c5ecf802a00fee7d740f747b1633337`, workflow [45685127482](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45685127482), remained in progress and does not substitute for the newer aggregate-gated run. Full tests/M101 on the latest branch head `02e0d36445c0549f6473531cd01ed4fc78e443ec` were also in progress; the 357-test result above belongs to `44a96b3`, not to `02e0d`.

Still not established: independent instrument approval of the gain-to-electron/variance convention; an externally preregistered custodian-held blind truth set; a four-method comparison on identical genuinely held-out real SPHEREx exposures; pixel-level source flux extraction and validated repeated temporal measurements; a YSO selection function with independent class review, completeness and contamination modelling; an independent astronomical reproduction; and a validated scientific release. No source-product metadata association or CI pass can substitute for these gates.
