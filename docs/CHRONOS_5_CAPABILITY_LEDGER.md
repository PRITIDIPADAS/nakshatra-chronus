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
| 19 | One population-level YSO physics study | SPLICES/DR1/QR3 reconnaissance, SIAv2 footprint matching, same-epoch feature/continuum coverage gates, calibration-group checks, exposure-ratio validation and digest-bound rate API implemented; rates pool signed completeness-corrected science-minus-control counts over summed area×time before applying the non-negative boundary | Reconnaissance completed; no validated selection-corrected YSO population estimate or discovery | Source flux/spectral quality/usable epochs, independent classifications, multidimensional selection/completeness, external preregistration and independent review required |
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
