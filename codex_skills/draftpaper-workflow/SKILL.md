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
5. `write-introduction`
6. `inventory-data`
7. `assess-data-quality`
8. `assess-data-feasibility`
9. `record-observation --stage data` after Codex has visibly summarized data source/content/processing
10. `build-data-context`
11. `write-data`
12. `collect-method-plan`
13. `plan-figures`
14. `generate-analysis-code`
15. `verify-methods`
16. `record-observation --stage methods` after Codex has visibly summarized method rationale/code intent
17. `build-method-context`
18. `write-methods`
19. `assess-result-validity`
20. `inventory-results`
21. `write-results`
22. `write-discussion`
23. `assemble-latex`
24. `run-integrity-gate`
25. `quality-check`
26. `diagnose-gate-failures`
27. `review-draft`
28. `assess-publication-readiness`
29. `recommend-statistical-revision`
30. `generate-revision-plan`
31. `apply-revision` when the user accepts a revision route
32. `re-review`

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

If upstream artifacts change, rerun from the earliest affected stage through downstream writing, assembly, integrity, and quality. If references change, rerun plan, Introduction, Discussion, assembly, integrity, and quality. Journal profile affects all writing and assembly; data affects method plan onward; code or method changes affect method verification onward. If results change, rerun result validity onward. Template-only changes affect assembly, integrity, and quality.

## Gates

Never generate the research plan or writing stages before `resolve-journal-template`. Stop on `blocked_high_similarity` unless the user explicitly continues with `--allow-high-similarity`. Do not save hidden reasoning; after Codex visibly summarizes data or method reasoning, preserve that summary with `record-observation`. Data writing must use `build-data-context` then `write-data`; Methods must use `build-method-context` then `write-methods`. Never verify/write Methods before data feasibility is `pass` or `conditional_pass` and method requirements exist. Run `plan-figures` before `generate-analysis-code`; generated code must follow `results/figure_plan.json`, produce `results/figure_metadata.json` and `results/figure_quality_report.json`, and avoid workflow-diagram fallbacks for empirical Results. If raw data are remote/private/too large, use local processed/results artifacts and limit claims. Results require passed/conditional result validity and `inventory-results`; Results contain no citations and should interpret figure metadata rather than filenames. Discussion citations must come from BibTeX and citation evidence. Always run `run-integrity-gate` before final `quality-check`. Quality fails if Data/Methods contain local filenames, paths, commands, manifest dumps, or generated empirical figures without scientific metadata.

For Zotero-backed references, first call `list-zotero-collections` after confirming `ZOTERO_LIBRARY_ID`, `ZOTERO_LIBRARY_TYPE`, and `ZOTERO_API_KEY` are configured in the local environment. Then call `search-literature --zotero-collection "<collection name>"`; do not fall back to the full Zotero library. Treat imported Zotero records as user-curated references: they are preserved outside external-search ranking, recency, abstract/PDF filtering, and the external 30-reference cap, but must still appear in `literature_summaries/index.html` together with searched references and remain distinguishable by their Zotero source/origin metadata. Use `--zotero-context all` only when the user intends the selected collection to support Introduction, Data, and Methods evidence.

Every project has `project_passport.yaml`, `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`. Treat these files as append-only audit state owned by the core CLI. Do not edit them manually; use `status`, `checkpoint`, `resume`, or stage commands.

## Review and Revision Loop

When any gate fails, run `diagnose-gate-failures` before broad advice. After an assembled draft exists, run `review-draft`, `assess-publication-readiness`, `recommend-statistical-revision`, then `generate-revision-plan`. Do not let `apply-revision` rewrite scientific content; it only marks affected stages stale. If revisions require data, methods, statistical processing, or weaker claims, ask the user to confirm. After reruns, use `re-review`.

## Skill Reuse

Before building new analysis/method workflows, search for reusable skills or GitHub skill repositories. Reuse suitable skills before creating new ones. If a reusable workflow is created, summarize it as a future skill candidate. For PDF/full-text literature fetching, prefer `Dictation354/paper-fetch-skill`.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
