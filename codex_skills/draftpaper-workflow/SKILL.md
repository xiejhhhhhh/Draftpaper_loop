---
name: draftpaper-workflow
description: Use when a user wants Codex to operate Draftpaper-loop projects, staged research-paper workflows, LaTeX drafts, citation evidence, results manifests, quality gates, or local review PDFs.
---

# Draftpaper-loop Workflow

Use this skill as a thin Codex calling layer for the active Draftpaper-loop repository. The core capability is the Python package, CLI, and local project directory model. Codex must translate user intent into CLI calls and explain results; it must not reimplement workflow logic.

## Boundary

Do not directly edit project.json. Do not directly edit stage_manifest files. Do not generate paper sections by bypassing the CLI. Do not patch references, status, or LaTeX assembly metadata by hand unless the user explicitly asks for manual repair after a failed command.

Use:

```powershell
python -m draftpaper_cli.cli <command>
```

For real paper projects, prefer plotting support:

```powershell
python -m pip install -e .[plotting]
```

Use the minimal install only for CLI smoke tests. Generated empirical Results figures must not degrade to workflow diagrams.

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
26. `write-results`
27. `write-introduction`
28. `build-data-context`
29. `write-data`
30. `build-method-context`
31. `write-methods`
32. `prepare-discussion-comparison`
33. `write-discussion`
34. `assemble-latex`
35. `run-integrity-gate`
36. `quality-check`
37. reviewer/rescue commands when gates fail

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

If upstream artifacts change, rerun from the earliest affected stage through downstream writing, assembly, integrity, and quality. If references change, rerun plan, evidence generation, Results, then manuscript writing. Journal profile affects plan, all writing, and assembly; data affects method plan onward; code or method changes affect method verification onward. If results change, rerun result validity, core evidence, Results, then downstream writing. Template-only changes affect assembly, integrity, and quality.

## Gates

Never generate the research plan before `resolve-journal-template` and `preflight-research-feasibility`. Stop on `blocked_high_similarity` unless the user explicitly continues with `--allow-high-similarity`. Do not save hidden reasoning; after Codex visibly summarizes data or method reasoning, preserve that summary with `record-observation`.

The main loop is evidence-first: literature and feasibility -> research plan/storyboard -> plan feasibility and repair -> data acquisition/integration -> method blueprint/feasibility -> figure contracts -> method/code -> figures/metadata/run manifest/result validity -> `assess-core-evidence` -> human confirmation -> Results -> Introduction/Data/Methods/Discussion. `plan-figures` must precede `assess-figure-contracts`, and `assess-figure-contracts` must pass or conditionally pass before `generate-analysis-code`. Generated code must follow the strict main-figure contracts and produce scientific PNGs, metadata, and quality reports. Failed main figures trigger data repair, method repair, or `revise-research-plan`; they must not be silently replaced with validation or workflow diagrams. Project-specific code must be stage-owned: data acquisition/processing belongs under `data/scripts`; modelling, statistics, validation, ablation, and plotting belong under `methods/scripts`, `methods/src`, or `methods/plotting`; `code/` is compatibility/shared workspace only.

Data writing must use `build-data-context` then `write-data`; Methods must use `build-method-context` then `write-methods`, both after core evidence and Results. Before those writing stages, use code provenance, method formula extraction, and figure-code trace artifacts. Results require passed/conditional result validity, passed `assess-core-evidence`, and `inventory-results`; Results contain no citations. Discussion citations must come from BibTeX and citation evidence, and `prepare-discussion-comparison` should create the comparison matrix before `write-discussion`. Always run `run-integrity-gate` before final `quality-check`.

For Zotero-backed references and append-only audit files, follow `references/commands.md`; do not edit CLI-owned ledgers or manifests manually.

## Review and Revision Loop

When any gate fails, use `status` or `run-pipeline` to follow: `diagnose-gate-failures`, `review-draft`, `assess-publication-readiness`, `discover-review-workflow-gaps`, `propose-review-engineering-plan`, `recommend-statistical-revision`, `prepare-analysis-revision`, reviewer-task reruns, then `generate-revision-plan`. Reviewer-task reruns use `plan-figures --use-review-tasks`, `generate-analysis-code --use-review-tasks`, `verify-methods`, and `assess-result-validity`. Review engineering runs geography, astronomy, machine_learning, or default. Use `review/review_engineering_plan.html`, `review/analysis_revision_feasibility.html`, and `review/user_confirmation_requests.json` before data cleaning or method reruns. `apply-revision` only marks stages stale. After reruns, use `re-review`.

## Skill Reuse

Before building new analysis/method workflows, search for reusable skills or GitHub skill repositories. Reuse suitable skills before creating new ones. If a reusable workflow is created, summarize it as a future skill candidate. For PDF/full-text literature fetching, prefer `Dictation354/paper-fetch-skill`.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
