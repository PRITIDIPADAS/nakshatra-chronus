# CHRONOS 5 independent astronomical reproduction protocol

**Status: NOT OBTAINED.** This document defines the external acceptance gate. It is not evidence that a researcher has reviewed or reproduced the project.

## Independence requirement

The reproducer must be an astronomy researcher who is not an author of the CHRONOS analysis being assessed and has no role in producing the claimed result. Their identity, affiliation, role, conflicts and review scope must be documented by that person. No name, institution, endorsement or result is to be invented or inferred from a GitHub account.

A software test, self-review, collaborator who authored the result, automated workflow, source-code inspection, or confirmation that an archive URL resolves is not an independent astronomical reproduction.

## Reproduction package to freeze

The authors must provide, under the applicable archive and catalogue licences:

- exact native science MEFs and calibration products, with archive IDs, URIs, byte counts, SHA-256 and MD5 where supplied;
- source catalogue, source positions and independently documented source-classification references;
- exact source-level measurements, per-row observation/MJD/LVF/detector/release identity and native pixel/WCS/CWAVE/CBAND verification reports;
- calibration compatibility decisions and calibration review record;
- full source-extraction method/version/configuration or the hosted-service job/version/configuration record;
- all exclusion rules, quality masks, fit-quality/background thresholds and frozen selection-function bins;
- injection input truth, detector output, production peak lists, one-to-one matching records and false-positive/null-control records;
- preregistration receipt and frozen configuration linked to the exact source commit and data digest;
- code commit, environment lock, commands, random seeds and all output artifacts;
- failures, warnings, excluded rows, negative results and known limitations.

The release archive must include a machine-readable manifest binding every file and report. Do not include private credentials or restricted archive material.

## Independent reproduction procedure

The external researcher should be given an immutable copy of the package and a written protocol. They should then:

1. verify the file hashes and archive/product identity independently;
2. retrieve or validate original archive products under their own account where licensing permits;
3. rebuild the source-level time series from the supplied original measurements and native FITS data;
4. reproduce a preselected subset of source measurements from original data, including flux, uncertainty, MJD, wavelength and quality decisions;
5. independently inspect CWAVE/CBAND and calibration compatibility for the reproduced subset;
6. rerun the frozen injection/recovery experiment, using the exact production detection/peak rule, and reproduce the selection function over claimed supported cells;
7. rerun the blinded four-method evaluation if the claim depends on performance superiority, including all baselines, matched operating points, negative controls and ablations;
8. independently inspect the YSO sample definition, classification references, contamination model, null controls, selection correction and uncertainty calculation;
9. compare outputs against the authors' reports with stated tolerances, and document every discrepancy or unreproduced claim;
10. provide a signed dated report stating the exact commit, input-manifest digest, commands, environment, reproduced results, deviations, limitations and whether the claim is supported.

The independent researcher must be able to report a negative result. The authors must not edit the frozen result or acceptance criteria after seeing the review.

## Acceptance record

Create a record only after the researcher supplies it. Required fields:

- researcher name and self-declared role/affiliation;
- independence/conflict statement;
- review date and report URI/hash;
- exact CHRONOS commit and input-manifest SHA-256;
- reproduced source IDs/products/epochs and measured tolerances;
- selection-function cells independently reproduced;
- blind benchmark and population outputs reproduced, where applicable;
- discrepancies, unresolved issues and negative findings;
- explicit reviewer conclusion and any conditions.

The repository's evidence graph should attach this record to the exact claims it supports. A reviewer need not endorse broader claims than those they actually reproduced.

## Current gate state

No independent astronomical reproduction was supplied in this implementation run. No researcher has been recruited or contacted by this automated code change, and no independent review is implied. Until a genuine external report is attached and its contents verified, Session 20 remains **NOT SATISFIED**, the scientific release remains closed, and no discovery or performance-superiority claim should be made.
