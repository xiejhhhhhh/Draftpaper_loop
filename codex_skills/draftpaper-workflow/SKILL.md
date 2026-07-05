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
4. `generate-plan`
5. `prepare-data-acquisition`
6. `inventory-data`
7. `assess-data-quality`
8. `assess-data-feasibility`
9. `record-observation --stage data` after Codex has visibly summarized data source/content/processing
10. `collect-method-plan`
11. `prepare-method-blueprint`
12. `plan-figures`
13. `generate-analysis-code`
14. `classify-code-ownership`, `route-stage-code`, `build-code-provenance`, `extract-method-formulas`, and `trace-figures-to-code` when project-specific or legacy code exists under `code/`
15. `verify-methods`
16. `record-observation --stage methods` after Codex has visibly summarized method rationale/code intent
17. `assess-result-validity`
18. `assess-core-evidence`
19. `checkpoint --stage core_evidence` for human figure/evidence confirmation
20. `inventory-results`
21. `write-results`
22. `write-introduction`
23. `build-data-context`
24. `write-data`
25. `build-method-context`
26. `write-methods`
27. `prepare-discussion-comparison`
28. `write-discussion`
29. `assemble-latex`
30. `run-integrity-gate`
31. `quality-check`
32. reviewer/rescue commands when gates fail

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

If upstream artifacts change, rerun from the earliest affected stage through downstream writing, assembly, integrity, and quality. If references change, rerun plan, evidence generation, Results, then manuscript writing. Journal profile affects plan, all writing, and assembly; data affects method plan onward; code or method changes affect method verification onward. If results change, rerun result validity, core evidence, Results, then downstream writing. Template-only changes affect assembly, integrity, and quality.

## Gates

Never generate the research plan before `resolve-journal-template`. Stop on `blocked_high_similarity` unless the user explicitly continues with `--allow-high-similarity`. Do not save hidden reasoning; after Codex visibly summarizes data or method reasoning, preserve that summary with `record-observation`.

The main loop is evidence-first: literature and plan -> data acquisition/integration -> method/code -> figures/metadata/run manifest/result validity -> `assess-core-evidence` -> human confirmation -> Results -> Introduction/Data/Methods/Discussion. `plan-figures` must precede `generate-analysis-code`; generated code must follow the figure plan and produce scientific PNGs, metadata, and quality reports. Project-specific code must be stage-owned: data acquisition/processing belongs under `data/scripts`; modelling, statistics, validation, ablation, and plotting belong under `methods/scripts`, `methods/src`, or `methods/plotting`; `code/` is compatibility/shared workspace only.

Data writing must use `build-data-context` then `write-data`; Methods must use `build-method-context` then `write-methods`, both after core evidence and Results. Before those writing stages, use code provenance, method formula extraction, and figure-code trace artifacts. Results require passed/conditional result validity, passed `assess-core-evidence`, and `inventory-results`; Results contain no citations. Discussion citations must come from BibTeX and citation evidence, and `prepare-discussion-comparison` should create the comparison matrix before `write-discussion`. Always run `run-integrity-gate` before final `quality-check`.

For Zotero-backed references and append-only audit files, follow `references/commands.md`; do not edit CLI-owned ledgers or manifests manually.

## Review and Revision Loop

When any gate fails, use `status` or `run-pipeline` to follow: `diagnose-gate-failures`, `review-draft`, `assess-publication-readiness`, `discover-review-workflow-gaps`, `propose-review-engineering-plan`, `recommend-statistical-revision`, `prepare-analysis-revision`, reviewer-task reruns, then `generate-revision-plan`. Reviewer-task reruns use `plan-figures --use-review-tasks`, `generate-analysis-code --use-review-tasks`, `verify-methods`, and `assess-result-validity`. Review engineering runs geography, astronomy, machine_learning, or default. Use `review/review_engineering_plan.html`, `review/analysis_revision_feasibility.html`, and `review/user_confirmation_requests.json` before data cleaning or method reruns. `apply-revision` only marks stages stale. After reruns, use `re-review`.

## Skill Reuse

Before building new analysis/method workflows, search for reusable skills or GitHub skill repositories. Reuse suitable skills before creating new ones. If a reusable workflow is created, summarize it as a future skill candidate. For PDF/full-text literature fetching, prefer `Dictation354/paper-fetch-skill`.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
