---
name: draftpaper-workflow
description: Use when a user wants Codex to operate Draftpaper-loop projects, staged research-paper workflows, LaTeX drafts, citation evidence, results manifests, quality gates, or local review PDFs.
---

# Draftpaper-loop Workflow

Use this skill as the thin Codex calling layer for Draftpaper-loop. Translate user intent into CLI calls and explain results; do not reimplement workflow logic.

## Boundary

Do not directly edit project.json. Do not directly edit stage_manifest files. Do not generate paper sections by bypassing the CLI. Do not patch references, status, or LaTeX assembly metadata by hand unless the user explicitly asks for manual repair after a failed command.

Use:

```powershell
python -m draftpaper_cli.cli <command>
```

Install plotting dependencies for real paper projects. Empirical Results figures must not degrade to workflow diagrams.

Read `references/commands.md` when exact command syntax is needed.

Before any stage command, call:

```powershell
python -m draftpaper_cli.cli status --project <project>
```

Use `run-pipeline` for the next safe action. Use `checkpoint` when human confirmation is required; if `status` reports `pipeline_state=awaiting_confirmation`, wait for user confirmation and `resume`.

If `status` reports `pipeline_state=drift_detected`, run `sync-artifact-stale`. Do not manually decide stale stages when the CLI can compute them.

## Stage Order

Run stages in this order unless the user asks for a focused rerun:

1. `create-project`
2. `search-literature`
3. `resolve-journal-template`
4. `preflight-research-feasibility`
5. `generate-plan`
6. `assess-research-plan-feasibility`
7. `revise-research-plan` if the plan feasibility report is blocked or needs scope repair
8. `prepare-data-acquisition`
9. `inventory-data`
10. `assess-data-quality`
11. `assess-data-feasibility`
12. `record-observation --stage data` after Codex has visibly summarized data source/content/processing
13. `collect-method-plan`
14. `prepare-method-blueprint`
15. `assess-method-feasibility`
16. `plan-figures`
17. `assess-figure-contracts`
18. `generate-analysis-code`
19. `classify-code-ownership`, `route-stage-code`, `build-code-provenance`, `extract-method-formulas`, and `trace-figures-to-code` when project-specific or legacy code exists under `code/`
20. `verify-methods`
21. `record-observation --stage methods` after Codex has visibly summarized method rationale/code intent
22. `assess-result-validity`
23. `assess-core-evidence`
24. `checkpoint --stage core_evidence` for human figure/evidence confirmation
25. `inventory-results`
26. For Results: `prepare-section-writing`, compose `writing/drafts/results.tex` freely from the packet, `submit-section-draft`, `prepare-scientific-editor`, apply only requested local repairs, `accept-section-draft`, then `write-results`
27. Repeat the same free-writing/editor/acceptance lifecycle for Introduction, then `write-introduction`
28. `build-data-context`, then repeat the lifecycle for Data before `write-data`
29. `build-method-context`, then repeat the lifecycle for Methods before `write-methods`
30. `prepare-discussion-comparison`, then repeat the lifecycle for Discussion before `write-discussion`
31. `assess-functional-quality-release`
32. `assemble-latex`
33. `run-integrity-gate`
34. `audit-citations --final`
35. `prepare-blind-quality-evaluation`, collect independent reviews, then `record-blind-quality-evaluation`
36. `assess-paper-quality-parity`
37. `quality-check`
38. reviewer/rescue commands when gates fail

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

Rerun from the earliest affected stage. If references change, rerun plan, evidence, Results, and writing. Journal changes affect plan, writing, and assembly; data affects method planning onward; code or method changes affect verification onward. If results change, rerun validity, core evidence, Results, and downstream writing. Template-only changes affect assembly and quality.

## Gates

Never generate the research plan before `resolve-journal-template` and `preflight-research-feasibility`. Stop on `blocked_high_similarity` unless the user explicitly continues with `--allow-high-similarity`. Do not save hidden reasoning; after Codex visibly summarizes data or method reasoning, preserve that summary with `record-observation`.

The main loop is evidence-first: literature and feasibility -> research plan/storyboard -> plan feasibility and repair -> data acquisition/integration -> method blueprint/feasibility -> figure contracts -> method/code -> figures/metadata/run manifest/result validity -> `assess-core-evidence` -> human confirmation -> Results -> Introduction/Data/Methods/Discussion. `plan-figures` must precede `assess-figure-contracts`, and `assess-figure-contracts` must pass or conditionally pass before `generate-analysis-code`. Generated code must follow the strict main-figure contracts and produce scientific PNGs, metadata, and quality reports. Failed main figures trigger data repair, method repair, or `revise-research-plan`; they must not be silently replaced with validation or workflow diagrams. Project-specific code must be stage-owned: data acquisition/processing belongs under `data/scripts`; modelling, statistics, validation, ablation, and plotting belong under `methods/scripts`, `methods/src`, or `methods/plotting`; `code/` is compatibility/shared workspace only.

Data writing must use `build-data-context` then `write-data`; Methods must use `build-method-context` then `write-methods`, both after core evidence and Results. Before those writing stages, use code provenance, method formula extraction, and figure-code trace artifacts. Results require passed/conditional result validity, passed `assess-core-evidence`, and `inventory-results`; Results contain no citations. Discussion citations must come from BibTeX and citation evidence, and `prepare-discussion-comparison` should create the comparison matrix before `write-discussion`. Always run `run-integrity-gate` before final `quality-check`.

Every formal manuscript section must follow the state machine exposed by `run-pipeline`: evidence-packet preparation -> Codex free composition -> candidate submission -> Scientific Editor -> paragraph-local repair when requested -> explicit section acceptance -> section writer. Deterministic fallback text is diagnostic-only and must never proceed to LaTeX assembly, citation audit, parity assessment, or formal release. Do not bypass an Agent action when `run-pipeline` returns `compose-section-with-agent` or `revise-section-with-agent`; write the requested draft path, then rerun `run-pipeline`.

For Zotero-backed references and append-only audit files, follow `references/commands.md`; do not edit CLI-owned ledgers or manifests manually.

## Review and Revision Loop

When a gate fails, follow `status` or `run-pipeline` through diagnosis, review, statistical or analysis repair, reviewer-task reruns, and `generate-revision-plan`. Inspect the generated review plan, feasibility report, and confirmation requests before rerunning data or methods. `apply-revision` only marks stages stale; use `re-review` after reruns.

## Skill Reuse

Reuse suitable skills or public research workflows before creating new analysis code. Record reusable work as a future skill candidate; use the configured paper-fetch skill for full text.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
