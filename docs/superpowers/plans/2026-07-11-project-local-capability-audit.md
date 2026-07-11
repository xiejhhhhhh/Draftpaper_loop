# Project-Local Capability Audit Implementation Plan

**Goal:** Audit apparent plugin gaps against project-local data and method assets before blocking a main figure, while keeping reusable-plugin promotion separate.

**Architecture:** The sufficiency report exposes audit-required requirements. A new audit command scans stage-owned data/method/code manifests and source files for role evidence, output contracts, and hashes. It writes constrained `project_local_binding` entries into the binding plan only when traceable local evidence exists. Figure gates accept those bindings but label them project-local; promotion remains candidate-only.

## Tasks

1. Add failing tests for local data and method capability discovery, unresolved gaps, and binding-plan updates.
2. Implement `project_capability_audit.py` with role-to-evidence matching, Python source inspection, artifact hashes, privacy-safe summaries, and JSON/HTML reports.
3. Upgrade sufficiency states from immediate `missing` to `audit_required` and add `audit-project-capabilities` CLI/status routing.
4. Allow project-local data/method bindings in figure trace and execution ledgers, but never treat them as globally promoted plugins.
5. Extend Results discipline review with semantic checks for numeric claims, figure references, evidence conflicts, internal artifact language, and unsupported conclusions.
6. Extend Data/Methods writing contexts with sanitized plugin/local-binding evidence.
7. Audit the current astronomy project, run only the legal next stages, compare the resulting Results artifact with the existing PDF Results, and write an optimization report.
8. Run focused and full tests, update README, commit, and retry GitHub push when connectivity permits.
