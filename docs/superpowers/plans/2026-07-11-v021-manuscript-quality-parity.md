# v0.21 Manuscript and Figure Quality Parity Plan

## Goal

Raise full Draftpaper-loop output to at least 95% of an expert reference draft without copying project-specific prose or hard-coding one discipline. The score is contract-based: scientific evidence fidelity, figure-story coverage, comparison and mechanism reasoning, uncertainty and claim boundaries, and prose quality.

## Architecture

1. Build `results/results_narrative_contract.json` from the research claims, figure contracts, plugin/run trace, result manifest, verified metrics, cohort records, and appendix links.
2. Assign every main figure an evidence role such as study boundary, pre-model signal, model comparison, component attribution, or error/uncertainty boundary. Roles come from structured contracts, not permanent discipline-specific branches.
3. Add the narrative contract to the Codex section packet. Codex writes freely from evidence packets; deterministic prose remains a draft fallback, never the quality target.
4. Score Results on evidence fidelity, narrative coverage, scientific reasoning, claim calibration, and prose diversity. A candidate passes at 0.95 or above. When an expert reference is supplied locally, require candidate score to reach at least 95% of the reference score as well.
5. Extend figure quality scoring with semantic contract fulfillment, panel completeness, verified method outputs, scientific annotations, resolution/legibility, and caption/evidence alignment. Pixel existence alone cannot pass.
6. Run post-Results discipline rules only for figures with complete data-plugin, method-plugin, and project-run traces. Findings repair claims and interpretation before downstream writing.

## Non-Overfitting Boundary

- The repository stores generic role and score logic, not astronomy sample values, project filenames, or reference prose.
- Astronomy, geography/ML, and bioinformatics/medicine are regression projects, not special-case branches.
- The 95% target is measured by evidence and narrative functions, not lexical similarity to one manuscript.

## Delivery Order

1. Results Narrative Contract and quality scorer.
2. Codex writing packet integration and candidate quality gate.
3. Results semantic repair loop with hash-aware re-review.
4. Scientific figure quality scorer and regeneration loop.
5. Full-paper section contracts and cross-section consistency.
6. Full astronomy regression, followed by geography/ML and bioinformatics/medicine regressions.
