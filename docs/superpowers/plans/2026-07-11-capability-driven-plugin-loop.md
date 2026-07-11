# Capability-Driven Plugin Loop Implementation Plan

> **For Codex:** Execute this plan on `codex/capability-driven-plugin-loop` with test-first changes. Do not silently fabricate data, methods, or figures when a required capability is missing.

**Goal:** Make research plans resolve to explicit, composite-discipline capabilities so every main figure has an auditable claim -> data plugin -> method plugin -> run output -> review-rule chain.

**Architecture:** Add a contract and sufficiency layer immediately after research planning, then bind selected plugin manifests into data/method execution ledgers. Extend figure contracts with the resulting provenance and run a result-stage composite review gate after Results. Rescue produces reviewable AcademicForge/GitHub candidate tasks; it never auto-promotes unknown third-party code.

## 1. v0.18.9: Contracts

**Files:** `draftpaper_cli/research_capabilities.py`, `draftpaper_cli/cli.py`, `tests/test_research_capabilities.py`

1. Create `discipline_contract.json` from the final project profile, declaring primary/secondary disciplines, their data/method/review roles, evidence, and cross-discipline interfaces.
2. Create `research_capability_contract.json` from claim contracts, storyboard, method plan, and data inventory. Use stable requirement IDs for data, method, figure, review, and runtime needs.
3. Add `resolve-research-capabilities` CLI command and tests for geography+ML, astronomy+ML, and bioinformatics+medicine.

## 2. v0.19.0: Sufficiency and structured selection

**Files:** `draftpaper_cli/research_capabilities.py`, `draftpaper_cli/cli.py`, `draftpaper_cli/orchestrator.py`, `tests/test_research_capabilities.py`

1. Match requirements against registered plugin specs using discipline, plugin type, input/output role, format, runtime class, validation level, and aliases.
2. Write `plugin_sufficiency_report.json/html`, `plugin_binding_plan.json`, and `plugin_gap_plan.json`.
3. Block core main-figure requirements unless data and methods are executable; mock/plan-only external contracts do not satisfy live execution.
4. Surface capability gaps in status/run-pipeline.

## 3. v0.19.1: Rescue

**Files:** `draftpaper_cli/plugin_rescue.py`, `draftpaper_cli/cli.py`, `draftpaper_cli/orchestrator.py`, `tests/test_plugin_rescue.py`

1. Convert each gap into a scoped rescue task.
2. Route in order: existing plugins, AcademicForge source processing, GitHub research repository discovery/inspection, candidate validation, explicit promotion confirmation.
3. Keep non-generalizable or license-uncertain code project-local and return user confirmation requirements.

## 4. v0.19.2: Binding and ledger

**Files:** `draftpaper_cli/plugin_execution.py`, `draftpaper_cli/cli.py`, `draftpaper_cli/data_acquisition.py`, `draftpaper_cli/method_blueprint.py`, `draftpaper_cli/analysis_code.py`, `tests/test_plugin_execution.py`

1. Bind each selected data/method plugin to a named requirement and resolve its manifest/template.
2. Write immutable-style execution events to `plugin_execution_ledger.jsonl`, including manifest/input/output hashes, parameters, runtime, status, and destination stage.
3. Execute standard runnable templates when their task contract permits it; otherwise prepare explicit project-code generation tasks without falsely claiming execution.
4. Keep data artifacts in `data/` and method artifacts in `methods/`.

## 5. v0.19.3: Figure provenance contract

**Files:** `draftpaper_cli/figure_plugin_trace.py`, `draftpaper_cli/figure_contract_gate.py`, `draftpaper_cli/analysis_code.py`, `tests/test_figure_plugin_trace.py`

1. Bind each main figure to its claim, data plugin(s), method plugin(s), method outputs, run evidence, and applicable review rules.
2. Write `results/figure_plugin_trace_report.json` and reject any incomplete main-figure chain before analysis-code generation.
3. Extend figure contracts/metadata with the trace IDs.

## 6. v0.19.4: Results review

**Files:** `draftpaper_cli/result_discipline_review.py`, `draftpaper_cli/cli.py`, `draftpaper_cli/orchestrator.py`, `tests/test_result_discipline_review.py`

1. Add `review-results-with-discipline-rules` after `write-results`.
2. Assess composite discipline review rules using current Results, figure evidence, bindings, and execution ledger.
3. Route failures to data/method rescue, result downgrade, results rewrite, or an explicit human checkpoint. Only mature/promoted evidence-bound rules can block scientifically.

## 7. v0.20.0: Regression and documentation

**Files:** fixture tests, `README.md`, `README.zh-CN.md`

1. Add three cross-discipline fixture regressions: geography+ML, astronomy+ML, bioinformatics+medicine.
2. Verify missing claim/plugin/run/review links block the pipeline; confirm complete chains pass and are traceable.
3. Document commands, artifact locations, rescue behavior, external runtime limits, and the no-silent-fallback policy.

## Verification

Run targeted suites after each phase, then `python -m pytest -q`, `python -m compileall -q draftpaper_cli tests`, `git diff --check`, and repository plugin registry checks. Review the full branch diff before integration.
