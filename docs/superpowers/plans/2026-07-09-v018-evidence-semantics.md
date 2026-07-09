# Evidence-Semantic Paper Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the permissive v0.17.0 manuscript path with a versioned, run-aware evidence loop that rejects contradictory facts and scientifically invalid figures while preserving Codex freedom at sentence level.

**Architecture:** The implementation separates presentation changes from scientific-semantic changes, records project-specific evidence through a domain-neutral registry, resolves metrics from verified method runs, and validates figures against executable scientific contracts. Human-approved core evidence is frozen by snapshot; writers consume only one current snapshot and are followed by section-specific gates and a post-writing citation audit.

**Tech Stack:** Python 3.11+, dataclasses, JSON/YAML/CSV project artifacts, pytest, existing Draftpaper-loop CLI and stage manifests.

## Global Constraints

- Preserve Git history; do not reset or force-push `main`.
- Results contain no citations.
- Citation audit repairs claims and placement without deleting retained references.
- Scientific figure changes invalidate result validity, core evidence, all manuscript sections, citation audit, LaTeX, integrity, and quality.
- Cosmetic-only figure changes are allowed only when data, method run, metric, variable-role, and claim fingerprints are unchanged.
- No writer may consume stale or mixed-snapshot evidence.
- Do not hard-code astronomy metrics, source classes, file paths, or project-specific facts in reusable modules.
- Correct astronomy regression values are `0.8667`, `0.8486`, `0.8053`, and `0.8205`.
- `source_id` versus `obs_id` and mixed count/performance metric charts must fail semantic figure validation.

---

### Task 1: v0.17.1 Emergency Stabilization

**Files:**
- Modify: `draftpaper_cli/analysis_code.py`
- Modify: `draftpaper_cli/results.py`
- Modify: `draftpaper_cli/methods.py`
- Modify: `draftpaper_cli/quality_gate.py`
- Test: `tests/test_analysis_code_generation.py`
- Test: `tests/test_results.py`
- Test: `tests/test_methods.py`

**Interfaces:**
- Consumes: current figure plan, method source status, run manifests, result manifest.
- Produces: strict main-figure execution refusal, approved-figure preservation, deterministic metric-source provenance.

- [ ] Add failing tests proving missing method-source evidence blocks a main figure, approved figures are not overwritten, and generic `metrics.csv` cannot replace verified run metrics.
- [ ] Run focused tests and confirm failures represent the existing regression.
- [ ] Tighten role aliases, restore strict method-source checks, and make generated-code execution preserve approved figure hashes.
- [ ] Remove current Scientific Fact Ledger text injection and make its old quality check non-authoritative.
- [ ] Run focused tests and the complete existing suite.

### Task 2: v0.17.2 Change Classification and Precise Stale Propagation

**Files:**
- Create: `draftpaper_cli/change_impact.py`
- Modify: `draftpaper_cli/artifact_freshness.py`
- Modify: `draftpaper_cli/project_state.py`
- Modify: `draftpaper_cli/cli.py`
- Test: `tests/test_change_impact.py`
- Test: `tests/test_artifact_freshness.py`

**Interfaces:**
- Produces: `classify_change(before, after, artifact_role) -> ChangeClassification`.
- Produces: `affected_stages(change, dependency_graph) -> list[str]`.
- Change classes: `presentation_only`, `citation_local`, `prose_semantic`, `scientific_result`, `method_semantic`, `data_semantic`, `research_design`.

- [ ] Add failing tests for local citation repair, cosmetic figure replacement, scientific figure replacement, result metric change, method change, and research-plan change.
- [ ] Verify local citation repair does not stale evidence-generation stages.
- [ ] Implement content, presentation, and scientific-semantic fingerprints.
- [ ] Implement dependency propagation with conservative scientific fallback for unknown changes.
- [ ] Integrate propagation into `sync-artifact-stale` and `apply-revision`.
- [ ] Run focused and full tests.

### Task 3: v0.17.3 Scientific Evidence Registry

**Files:**
- Create: `draftpaper_cli/evidence_registry.py`
- Create: `draftpaper_cli/evidence_conflicts.py`
- Modify: `draftpaper_cli/writing_brief.py`
- Modify: `draftpaper_cli/data_writing.py`
- Modify: `draftpaper_cli/methods.py`
- Modify: `draftpaper_cli/quality_gate.py`
- Test: `tests/test_evidence_registry.py`
- Test: `tests/test_evidence_conflicts.py`

**Interfaces:**
- Produces: `writing/scientific_evidence_registry.json`.
- Evidence records include `entity_role`, `value`, `unit`, `cohort`, `sample_unit`, `split`, `run_id`, `source_artifact`, `source_hash`, `confidence`, and `target_sections`.
- Conflict detection distinguishes different cohorts from contradictory values within the same cohort.

- [ ] Add failing tests for `1 source` versus `5 AGN + 5 XRB` in one cohort, valid smoke-test/main-cohort separation, and domain-neutral geography/medicine evidence roles.
- [ ] Implement registry schemas and source-priority rules.
- [ ] Implement conflict detection and make blocking conflicts stop manuscript writing.
- [ ] Replace literal “must preserve” prose injection with structured writer context.
- [ ] Run focused and full tests.

### Task 4: v0.17.4 Run-Aware Result Evidence Resolver

**Files:**
- Create: `draftpaper_cli/result_evidence.py`
- Modify: `draftpaper_cli/results.py`
- Modify: `draftpaper_cli/result_validity.py`
- Modify: `draftpaper_cli/methods.py`
- Test: `tests/test_result_evidence.py`
- Test: `tests/test_result_validity.py`

**Interfaces:**
- Produces: `results/resolved_result_evidence.json`.
- Resolves model, split, fold aggregation, metric name, value, uncertainty, run ID, and source table.
- Rejects unbound root-level metric files when verified run-linked metrics exist.

- [ ] Add a failing fixture containing generic F1 `0.5` and verified astronomy metrics `0.8667/0.8486/0.8053/0.8205`.
- [ ] Confirm current resolver selects the wrong value.
- [ ] Implement run-manifest and figure-code-trace ranking.
- [ ] Bind Results, Methods, validity checks, and figure metadata to resolved evidence IDs.
- [ ] Run focused and full tests.

### Task 5: v0.17.5 Semantic Figure Contract

**Files:**
- Create: `draftpaper_cli/figure_semantics.py`
- Modify: `draftpaper_cli/figure_contract_gate.py`
- Modify: `draftpaper_cli/figure_plan.py`
- Modify: `draftpaper_cli/analysis_code.py`
- Modify: `draftpaper_cli/core_evidence.py`
- Test: `tests/test_figure_semantics.py`
- Test: `tests/test_figure_contract_gate.py`

**Interfaces:**
- Produces: `results/figure_semantic_validation_report.json`.
- Contracts declare scientific question, required variable roles, forbidden roles, method outputs, plot grammar, panel requirements, metric dimensions, and expected claim.

- [ ] Add failing tests rejecting identifier-versus-identifier regression, mixed count/performance axes, missing ablation variants, and title-only contract matches.
- [ ] Add passing tests for workflow schematics, modality coverage panels, model comparison, ablation, and uncertainty figures.
- [ ] Implement variable-role, unit-family, panel, and method-output validation.
- [ ] Require semantic pass before core evidence or human confirmation.
- [ ] Run focused and full tests.

### Task 6: v0.17.6 Free Composition and Section Writing Contracts

**Files:**
- Create: `draftpaper_cli/section_contracts.py`
- Create: `draftpaper_cli/manuscript_composer.py`
- Modify: `draftpaper_cli/introduction.py`
- Modify: `draftpaper_cli/data_writing.py`
- Modify: `draftpaper_cli/methods.py`
- Modify: `draftpaper_cli/results.py`
- Modify: `draftpaper_cli/discussion.py`
- Modify: `draftpaper_cli/quality_gate.py`
- Test: `tests/test_section_contracts.py`
- Test: `tests/test_manuscript_composer.py`

**Interfaces:**
- Produces section evidence packets and section validation reports.
- Deterministic code controls evidence and prohibited content; prose composition remains open-ended.

- [ ] Add failing tests for repeated template sentences, workflow narration, irrelevant formulas, Results citations, unsupported metrics, and placeholder Abstract.
- [ ] Implement universal section intent and evidence rules with discipline extensions.
- [ ] Convert fixed paragraph writers into evidence-packet composers with deterministic fallback only for explicit offline mode.
- [ ] Add post-writing gates for evidence coverage, internal language, formula implementation, result leakage, and citation placement.
- [ ] Run focused and full tests.

### Task 7: v0.17.7 Evidence and Citation Snapshot Binding

**Files:**
- Create: `draftpaper_cli/evidence_snapshot.py`
- Modify: `draftpaper_cli/core_evidence.py`
- Modify: `draftpaper_cli/citation_audit.py`
- Modify: `draftpaper_cli/latex_assembly.py`
- Modify: `draftpaper_cli/quality_gate.py`
- Modify: `draftpaper_cli/cli.py`
- Test: `tests/test_evidence_snapshot.py`
- Test: `tests/test_citation_audit.py`

**Interfaces:**
- Produces: `results/promoted_evidence_snapshot.json`.
- Produces snapshot IDs in core-evidence, section, citation-audit, LaTeX, integrity, and quality reports.

- [ ] Add failing tests where PNGs change after core-evidence approval and where sections change after citation audit.
- [ ] Implement snapshot creation and explicit reopen semantics for scientific figure changes.
- [ ] Make writers and assembly reject mixed snapshot IDs.
- [ ] Require final citation audit timestamps and hashes to cover the final sections and BibTeX library.
- [ ] Run focused and full tests.

### Task 8: v0.18.0 Three-Project Regression and Release

**Files:**
- Create: `tests/fixtures/semantic_regression/`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `draftpaper_cli/__init__.py`
- Test: full `tests/` suite and three real project regressions.

**Interfaces:**
- Astronomy project verifies exact metric provenance and the approved six-figure story.
- Geography project verifies spatial/data roles without astronomy assumptions.
- Machine-learning project verifies baseline, ablation, split, and model-explanation evidence.

- [ ] Run astronomy regression from status through final quality without mixed snapshots.
- [ ] Run NDVI/geography regression and verify discipline-specific evidence contracts.
- [ ] Run machine-learning regression and verify run-aware metrics and semantic figures.
- [ ] Render and inspect all three PDFs.
- [ ] Update both READMEs with corrected v0.17.0 notes, v0.17.1-v0.17.7 changes, and v0.18.0 release behavior.
- [ ] Run the full test suite, inspect Git diff, commit, push the feature branch, and report remaining limitations.

