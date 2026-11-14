# Solo AI/researcher screening versus citizen science

A citizen-science study cannot be conducted by one AI assistant alone. The central scientific contribution of a citizen-science programme is the participation of actual members of the public and the ability to characterize genuine human labels, disagreement, learning, engagement, and reproducibility.

## What can be done solo

After genuine SPHEREx image pairs are downloaded, a single researcher can conduct an exploratory machine-assisted screening pass:

1. Create image pairs from two epochs using documented WCS alignment.
2. Randomize left/right order and remove dates, coordinates and filenames from the review view.
3. Run two or more distinct automated detectors or model configurations, retaining raw outputs separately.
4. Have one researcher review the resulting candidate list and label obvious artefacts, stationary sources and plausible movers.
5. Use held-out fields and untouched control images to measure the machine pipeline's false positives and sensitivity.
6. Publish it explicitly as a **single-analyst exploratory screening audit**, with no inter-rater or citizen-science claims.

This can be a useful development stage, but an AI system is not a recruited human volunteer, multiple model prompts are not independent participants, and repeated model calls do not provide independent human annotations.

## What cannot be fabricated

Do not manufacture participant identities, consent, human labels, inter-rater reliability, demographics, volunteer counts, or ethics approval. A Fleiss' kappa value computed from repeated copies or outputs of one model is not evidence of citizen agreement.

## Conditions before a public study

- Confirm institutional or local ethics requirements and obtain a formal determination where needed.
- Use a clear consent statement and withdrawal/data-retention policy.
- Recruit genuine adult volunteers and provide blinded, randomized tasks with known control examples.
- Keep raw annotations, timestamps, confidence scores and answer keys auditable.
- Preregister primary outcome measures and exclude training/control cases from confirmatory performance estimates.

The provided HTML interface and task manifest are infrastructure only. No participant study has been conducted and no participant responses are included in this repository.
