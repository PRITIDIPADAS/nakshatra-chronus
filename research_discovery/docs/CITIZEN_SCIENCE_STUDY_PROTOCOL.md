# CHRONOS citizen-science pilot protocol

**Status: designed, not launched.** No human participants or responses were generated in this work.

## Objective

Test whether trained volunteers can reliably triage two-epoch SPHEREx candidate cutouts into `moving_source`, `stationary_source`, `artifact` or `uncertain`, and determine whether a consensus label improves candidate prioritization over a single review.

This is a candidate-triage task, not a request for volunteers to declare Planet Nine. The overwhelming majority of objects should be mundane sources, known solar-system objects, or instrumental/background artifacts.

## Why there is a precedent

NASA's Backyard Worlds: Planet 9 project demonstrates that volunteer review of time-separated WISE imagery can contribute to genuine astrophysics. NASA reports thousands of brown-dwarf discoveries and dozens of papers from the broader project, with volunteers included as co-authors in some studies. It is a methodological precedent, not a claim that CHRONOS already has a running or equivalent project.

## Dataset assembly

1. Build cutout pairs from actual Level-2 MEFs with distinct, recorded timestamps. Prefer comparable detector/band observations after astrometric alignment.
2. Use the science MEF WCS and the documented cutout-to-detector mapping. Never use an All-Sky Cube mosaic as a time-separated image pair.
3. Generate three panel images per case where available: epoch A, epoch B and an aligned difference or blink product. Retain original FITS files, WCS, variance and flags privately for the science team.
4. Remove filenames, observation identifiers and any metadata that may reveal the expected label. Use opaque case IDs.
5. Include balanced hidden controls: stationary known sources, known moving solar-system objects where appropriate, injected moving point sources, known detector/atmospheric artifacts, and blank/ambiguous controls. Truth labels must be independently verified by an expert and not inferred from the model under evaluation.

## Participant workflow

- Explain the task, expected uncertainty, time commitment and data use before the first classification.
- Require explicit consent. Do not collect names, emails, birth dates, exact locations or other unnecessary personal data.
- Participants see randomized cases and choose one of four labels plus confidence. An optional note field must not solicit personal information.
- Each case receives a pre-registered number of independent reviews, with adaptive extra reviews only under a stated rule (e.g. high disagreement).
- Preserve raw annotations. Do not overwrite them with consensus labels.

The included `review.html` is an offline prototype. It does not include identity management, server-side storage, authentication, an IRB approval, publication terms or participant recruitment. It is not a production Zooniverse deployment.

## Analysis

- Inter-rater reliability: Fleiss' kappa for balanced complete cases; report its assumptions and uncertainty.
- Consensus: majority label with explicit tie/uncertain category; do not force an answer when reviewers disagree.
- Accuracy: measured only on held-out, expert-adjudicated controls with an independent truth source.
- Per-reviewer calibration: accuracy vs confidence on controls; do not rank volunteers solely by raw speed.
- Machine comparison: compare the human consensus and the frozen algorithm on the same blinded cases.
- Report case and participant counts, missingness, completion bias, disagreement, time-to-review and per-category confusion matrices.

## Ethics and governance

Before recruiting participants or publishing any responses, the project owner must complete the required institutional review/ethics assessment, consent language, data-management plan, retention policy and platform review. The presence of a checkbox in the prototype is not itself adequate consent. If minors may participate, additional safeguards and guardian consent may be required; the recommended pilot should restrict initial participation to adults unless an institution approves another approach.

## Proposed pilot stages

1. Internal expert calibration set and interface usability test.
2. Small adult-only volunteer pilot, with no scientific discovery claim.
3. Revise the task using error analysis and freeze the workflow.
4. Larger blinded run with preregistered controls and held-out fields.
5. Expert follow-up for the highest-ranked candidates, plus publication of negative results and false-alarm rates.

## Success criterion

The citizen component is useful only if it improves the number of real, independently confirmed candidates reviewed per unit of expert time, without raising false-discovery risk beyond the project's predeclared tolerance. A large classification count alone is not a scientific result.
