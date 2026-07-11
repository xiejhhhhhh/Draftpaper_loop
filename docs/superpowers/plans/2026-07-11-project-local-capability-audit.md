# Project-Local Capability Audit Implementation Plan

**Goal:** Audit apparent plugin gaps against project-local data and method assets before blocking a main figure, while keeping reusable-plugin promotion separate.

**Architecture:** The sufficiency report exposes audit-required requirements. A new audit command scans stage-owned data/method/code manifests and source files for role evidence, output contracts, and hashes. It writes constrained `project_local_binding` entries into the binding plan only when traceable local evidence exists. Figure gates accept those bindings but label them project-local; promotion remains candidate-only.

## Tasks

1. Add failing tests for local data and method capability discovery, unresolved gaps, and binding-plan updates.
2. Implement `project_capability_audit.py` with role-to-evidence matching, Python source inspection, artifact hashes, privacy-safe summaries, and JSON/HTML reports.
3. Upgrade sufficiency states from immediate blocking to `rescue_required` and add `audit-project-capabilities` CLI/status routing.
4. Allow project-local data/method bindings in figure trace and execution ledgers, but never treat them as globally promoted plugins. Missing review-rule bindings must not block code generation.
5. Move discipline-rule activation to `review-results-with-discipline-rules`. Select rules only from the data/method plugins that actually produced a figure, and classify prose findings as repair work rather than figure-generation failure.
6. Extend Data/Methods writing contexts with sanitized plugin/local-binding evidence.
7. Audit the current astronomy project, run only the legal next stages, compare the resulting Results artifact with the existing PDF Results, and write an optimization report.
8. Run focused and full tests, update README, commit, and retry GitHub push when connectivity permits.

## Final Blocking Boundary

`record-plugin-rescue-outcome` is the only path from a temporary capability gap to `blocked_unavailable`. It requires auditable attempts against project-local assets, the existing registry, AcademicForge, and GitHub research code. Scientific prose or review-rule findings can require Results repair, but cannot retroactively declare figure generation impossible.
