# SPHEREx DR1 D2 absolute-gain to electron conversion — independent calibration review packet

**Review state: PENDING — NOT INDEPENDENTLY APPROVED**  
**Prepared:** 25 November 2026  
**Purpose:** provide an instrument/calibration reviewer with the exact files, unit convention, code calculation, and empirical records requiring review. This packet is not a calibration certificate and does not sign for a reviewer.

## Question requiring independent review

CHRONOS uses the SPHEREx DR1 D2 absolute-gain matrix to derive a detector-pixel conversion for *added source-Poisson noise* in an already calibrated Level-2 IMAGE plane. The code does **not** apply the gain matrix a second time to the Level-2 science image. The derivation is recorded as \`derived_pending_independent_review\` in every machine-readable field report.

The official SPHEREx Explanatory Supplement v2.1 (10 November 2026) now provides the published product definitions used in the unit derivation below. It documents the gain matrix in (MJy/sr)/(e⁻/s), the Level-2 variance as the propagated combination of Poisson and electronic noise, and the delivered VARIANCE layer in (MJy/sr)². The review question is therefore narrower than an unknown-unit problem: independently verify the exposure-time and pixel-level bookkeeping in this implementation, and confirm that it adds only the synthetic source photons that were not present in the native exposure without re-adding noise already represented by that exposure's VARIANCE.

## Product and provenance record

M101 reference exposure:

| Item | Value |
|---|---|
| Science observation | \`2025W19_2B_0346_1\` |
| Release / detector | SPHEREx DR1 / D2 |
| Observation time | 2025-05-10 17:04:37.741 UTC |
| Exposure time | 113.5826 s |
| Science product | Native Level-2 MEF, 2040 × 2040, IMAGE BUNIT \`MJy / sr\` |
| Pipeline | 7.0.5 |
| Science SHA-256 | \`fba39ecd1930274aea655a744287908d6d677daeec59c8efe1ebbcffb844be90\` |
| Spectral-WCS SHA-256 | \`0eb4e27f351e6161e21372818f9e811480a7ab8bab9295722f180791e151a463\` |
| Absolute-gain SHA-256 | \`d0a4c3352da99326c307e4e0115285faa8cba2769ea6b57cf340d4e6fc271b37\` |
| Solid-angle map SHA-256 | \`231bcdab0aa31d0ee9c9349b10e6c871070bf3ed860b7dc799745c0f9d1c8bc0\` |

The absolute-gain FITS BUNIT retained by the audit is \`MJy s / (electron sr)\`. Its archive MD5 is recorded and verified in the field reports. The invalid/non-positive gain pixels are retained as invalid and masked; they are never interpolated or filled. The D2 map contains 4,161,600 pixels, of which 175 are invalid/non-positive in the audited product.

For M101, IRSA's \`spherex.provenance_input\` relation returned 14 input relationships for the science plane. The spectral-WCS and absolute-gain products have exact direct input links. The solid-angle map is a detector-matched supplemental product from the same calibration processing date; the reports do **not** represent it as a direct \`provenance_input\` child. The latest completed M101 audit is [workflow 45657439621](https://github.com/PRITIDIPADAS/nakshatra-chronus/actions/runs/45657439621), artifact 15044246564, SHA-256 \`9dfdb529b62f131864f9b7db5712896459edb3fa9f68eddf6cb917b190a18db2\`.

The same DR1 D2 absolute-gain and spectral-WCS calibration products were used for the six-region exploratory run. The six science observation IDs and native SHA-256 values are retained in the [six-region revalidation report](SPHEREX_MULTIFIELD_JY_REVALIDATION_2026-11-25.md).

## Official product-definition cross-check — SPHEREx Explanatory Supplement v2.1

The following points are documented by the SPHEREx Science Data Center / IPAC specification, *SSDC-DP-017, SPHEREx Explanatory Supplement*, version 2.1 dated 10 November 2026:

1. **Variance construction (§3.2.3, pp. 29–30):** the pipeline builds the per-pixel variance from Level-1 ramp/flux data and a per-pixel electronic-noise map. The specification describes the initial variance as the combined Poisson and electronic-noise estimate. It explicitly says the final calibrated 2040 × 2040 variance product delivered in the Level-2 MEF is in `(MJy/sr)^2`, after the variance has been updated along the Level-2 flux-processing steps.
2. **Noise terms (§3.2.3):** the electronic-noise model includes correlated-double-sampling and excess readout noise. The document says dark-current shot noise is excluded from the electronic-noise estimate because it is represented separately in the image at the variance-construction stage. The variance is based on the measured slope and integration time, with both electronic and Poisson contributions.
3. **Absolute-gain correction (§3.2.7, p. 35):** the Level-1 dark-subtracted detector image in `e-/s` is multiplied by the absolute-gain matrix to produce the Level-2 image in `MJy/sr`.
4. **Gain product (§4.1.1, p. 52; Appendix B, p. 80):** the gain matrix is `(MJy/sr)/(e-/s)`; the FITS example gives BUNIT `MJy s / (electron sr)`.
5. **Pixel solid angle (§4.2.1, pp. 54–55):** the absolute-gain calibration derivation explicitly uses the local pixel solid angle when converting point-source flux to equivalent surface brightness. In this injection implementation, the supplied Jy point-source flux is first converted to an IMAGE surface-brightness signal with the detector-aligned solid-angle map; the gain-derived electron conversion is then applied to that IMAGE signal. Do not introduce another solid-angle factor into the gain conversion itself.
6. **Photometry uncertainty (§3.3, pp. 43–44):** the supplement notes an additional 3% irreducible photometric scatter applied to reported catalog flux uncertainties; it states that this catalog uncertainty correction does not modify the image VARIANCE layer. That catalog-level correction is not silently folded into this pixel-level injection variance.

**Official reference:** [SPHEREx Explanatory Supplement, SSDC-DP-017, v2.1 (10 November 2026)](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf). Relevant headings are §3.2.3, §3.2.7, §4.1.1, §4.2.1, Appendix B. The [IRSA SPHEREx Data Products guide](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/) also lists the absolute-gain matrix as one 2040 × 2040 FITS image per detector with the same units.

### Consequence for the implemented source-Poisson addition

The native Level-2 VARIANCE already represents the noise of the *observed exposure*, including the Poisson contribution of its measured scene and electronic noise after propagation into IMAGE units. The simulated source is added after that exposure was observed, so its photons are not already present in the native ramp or the native variance estimate. Adding a Poisson realization for those additional photons and adding the corresponding `lambda_i / C_i^2` variance term is consistent with that separation, provided the injection is performed once and no later processing step adds the same synthetic-source variance again.

For a Jy injection with unit-integral ePSF (p_i), the implementation forms the pixel surface-brightness increment
[
\Delta I_i = \frac{10^{-6} F_{\mathrm{Jy}} p_i}{\Omega_i},
]
then uses
[
C_i = \frac{t_{\mathrm{exp}}}{G_{\mathrm{abs},i}},
\qquad
\lambda_i = \Delta I_i C_i,
\qquad
\Delta V_i = \frac{\lambda_i}{C_i^2}.
]
The source signal's `1/\Omega_i` factor is the Jy-to-MJy/sr pixel conversion; (C_i) is the gain/time conversion. These are distinct operations. This dimensional check is supported by the published units, but the mission team or an independent instrument-calibration reviewer must still reproduce the exact per-pixel noise bookkeeping for the released Level-2 product and the selected exposure.

## Implemented conversion — reviewer must independently verify

The code interprets the absolute-gain map as

\[
G_{\mathrm{abs},i}
\quad\left[
\frac{\mathrm{MJy/sr}}{\mathrm{electron/s}}
\right]
\]

and records a per-pixel conversion

\[
C_i = \frac{t_{\mathrm{exp}}}{G_{\mathrm{abs},i}}
\quad
\left[
\frac{\mathrm{electron}}{\mathrm{MJy/sr}}
\right].
\]

For an added source signal \(\Delta I_i\) in the Level-2 IMAGE units, the implementation computes

\[
\lambda_i = \Delta I_i C_i,
\qquad
N_i \sim \operatorname{Poisson}(\lambda_i),
\]

then represents the added realization in IMAGE units as \(N_i/C_i\), with the corresponding added variance

\[
\Delta V_i = \frac{\lambda_i}{C_i^2}.
\]

This is the implemented code path and dimensional interpretation—not an independently confirmed instrument calibration. The reviewer must check it against the authoritative product-definition documentation and the Level-2 pipeline's actual noise accounting. In particular, determine whether the delivered VARIANCE already contains any relevant source shot-noise term and whether the added term should be conditional on a source model, pixel solid angle, or another unit convention.

The science IMAGE itself remains in the delivered calibrated surface-brightness domain. The absolute-gain product is not multiplied into or divided out of the science IMAGE a second time. The solid-angle map is separately used by the Jy-domain source-flux and position-dependent matched-filter calculations.

## Exploratory injection evidence — not a calibration validation

The M101 pilot used 20 injections at each of 54.198, 108.396 and 216.792 µJy and recovered 5/20, 14/20 and 17/20, respectively. It is one exposure and one local detector region, with visible injection positions and seed. It is not blind, survey-wide, or a four-method comparison.

The six-region D2 pilot also ran with source-Poisson noise enabled. Its field-specific recoveries are:

| Region | Observation ID | Local 5σ reference | Low / nominal / high injected flux (µJy) | Recovered |
|---|---|---:|---:|---:|
| Taurus / Auriga | \`2025W35_1A_0331_1\` | 178.374 | 89.187 / 178.374 / 356.747 | 3/20 / 3/20 / 8/20 |
| Perseus / NGC 1333 | \`2025W34_1B_0227_1\` | 161.588 | 80.794 / 161.588 / 323.176 | 3/20 / 5/20 / 12/20 |
| Orion A | \`2025W37_1A_0365_1\` | 159.317 | 79.658 / 159.317 / 318.633 | 3/20 / 5/20 / 11/20 |
| Rho Ophiuchi | \`2025W31_2A_0170_1\` | 204.960 | 102.480 / 204.960 / 409.921 | 2/20 / 4/20 / 9/20 |
| Lupus III | \`2025W32_1A_0663_1\` | 211.158 | 105.579 / 211.158 / 422.317 | 0/20 / 0/20 / 0/20 |
| High-latitude control | \`2025W20_1C_0491_1\` | 114.063 | 57.032 / 114.063 / 228.126 | 6/20 / 13/20 / 17/20 |

The six-region run is exploratory and non-blind. The Lupus III zero-recovery result is retained in full and requires separate investigation; it must not be removed from or averaged away in the field summary.

## Specific review checklist

Please independently assess each item and cite the authoritative source, equation, or reproduction supporting the decision.

1. **Product definition and units:** confirm the exact meaning of the absolute-gain BUNIT and whether the archived map values have the interpreted numerator/denominator ordering.
2. **Exposure convention:** confirm which exposure time applies to the Level-2 plane, whether 113.5826 s is the appropriate multiplicative interval, and whether any time normalization is already embedded in the archived gain product.
3. **Pixel geometry:** confirm whether pixel solid angle belongs in the electron conversion itself or only in the conversion between integrated Jy and MJy/sr per pixel; ensure no missing or double-applied solid-angle factor.
4. **Existing variance:** identify exactly which shot-noise, read-noise, background, calibration and processing terms are already represented in the delivered VARIANCE plane. Confirm whether adding source Poisson variance is appropriate and not double counting.
5. **Poisson approximation:** assess electron-count discreteness, expected counts, detector response and any regimes where the stated Poisson draw is not valid.
6. **Invalid pixels and masks:** review the handling of 175 invalid gain pixels, photometry flags, source masks and invalid variance samples. Confirm no interpolation/filling or accidental re-entry into the likelihood occurs.
7. **PSF/solid-angle operation:** verify the 11 × 11 ePSF representation, Jy injection morphology and position-dependent ePSF/solid-angle matched-filter template in the Level-2 unit convention.
8. **Cross-field applicability:** confirm that the same D2 gain product is applicable to each listed science plane, given each field's release, pipeline, processing batch and exact provenance relation.
9. **Independent reproduction:** rerun at least M101 from the original archive bytes and the frozen repository revision; report any discrepancy in electron expectations, variance increments, recovery counts or provenance.

## Reviewer disposition — intentionally unsigned

| Field | Reviewer to complete |
|---|---|
| Reviewer name / role / affiliation | |
| Independent of CHRONOS developer? | |
| Date and UTC time | |
| Product-definition document / version | |
| Unit derivation accepted? | |
| Level-2 variance and double-counting review | |
| Pixel solid-angle convention accepted? | |
| Invalid-pixel and mask handling accepted? | |
| Independent reproduction artifact / checksum | |
| Discrepancies and required corrections | |
| Disposition | Pending / Approved with conditions / Not approved |
| Signature or institutional review record | |

**Current status remains \`derived_pending_independent_review\`.** No reviewer identity, signature, timestamp or approval is pre-populated. CI success, file hashes, provenance queries and a developer-authored derivation are not a substitute for this independent review.
