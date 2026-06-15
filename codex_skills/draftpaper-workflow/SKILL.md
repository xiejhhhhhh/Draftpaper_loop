---
name: draftpaper-workflow
description: Use when a user wants Codex to operate DraftPaper CLI projects, staged research-paper workflows, LaTeX drafts, citation evidence, results manifests, quality gates, or local review PDFs.
---

# DraftPaper Workflow

Use this skill as a thin Codex calling layer for `C:\DraftPaper_CLI`. The core capability is the Python package, CLI, and local project directory model. Codex must translate user intent into CLI calls and explain results; it must not reimplement workflow logic.

## Boundary

Do not directly edit project.json. Do not directly edit stage_manifest files. Do not generate paper sections by bypassing the CLI. Do not patch references, status, or LaTeX assembly metadata by hand unless the user explicitly asks for manual repair after a failed command.

Use:

```powershell
python -m draftpaper_cli.cli <command>
```

Read `references/commands.md` when exact command syntax is needed.

Before choosing a stage command, call:

```powershell
python -m draftpaper_cli.cli status --project <project>
```

Use `run-pipeline` to ask the orchestrator for the next safe CLI action. Use `checkpoint` whenever a stage requires explicit human confirmation; if `status` reports `pipeline_state=awaiting_confirmation`, do not continue into downstream stages until the user confirms and `resume` consumes the checkpoint hash.

If `status` reports `pipeline_state=drift_detected`, run `sync-artifact-stale` before continuing. This maps changed artifact hashes to downstream stale stages and refreshes the passport baseline. Do not manually decide stale stages when the CLI can compute them from the artifact ledger.

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
9. `collect-method-plan`
10. `plan-figures`
11. `generate-analysis-code`
12. `verify-methods`
13. `write-methods`
14. `assess-result-validity`
15. `inventory-results`
16. `write-results`
17. `write-discussion`
18. `assemble-latex`
19. `run-integrity-gate`
20. `quality-check`
21. `diagnose-gate-failures`
22. `review-draft`
23. `generate-revision-plan`
24. `apply-revision` when the user accepts a revision route
25. `re-review`

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

If upstream artifacts change, rerun from the earliest affected stage through downstream writing, `assemble-latex`, `run-integrity-gate`, and `quality-check`. If references change, rerun plan, Introduction, Discussion, assembly, integrity, and quality. Journal profile affects all writing and assembly; data affects method plan, code, methods, results, discussion, and assembly; code or method changes affect method verification onward. If results change, rerun result validity onward. If only LaTeX template files change, rerun assembly, integrity, and quality.

## Gates

Never generate the research plan or writing stages before `resolve-journal-template` has produced a current journal profile. Stop on `blocked_high_similarity` unless the user explicitly continues with `--allow-high-similarity`. Never verify/write Methods before data feasibility is `pass` or `conditional_pass` and method requirements exist. Run `plan-figures` before `generate-analysis-code`; generated code must follow `results/figure_plan.json` rather than a fixed plotting template. Run `generate-analysis-code` before `verify-methods` when generated code is used. If raw data are remote/private/too large and only processed tables or final figures are local, use those artifacts through `inventory-results`/`write-results` and keep claims limited to the supplied evidence. Never write Results before result validity passes or conditionally passes; always run `inventory-results` before `write-results`. Results must contain no citations. Discussion citations must come from BibTeX and citation evidence. Always run `run-integrity-gate` before final `quality-check`; route failures back to references, section citations, result manifest, or artifacts.

For Zotero-backed references, first call `list-zotero-collections` after confirming `ZOTERO_LIBRARY_ID`, `ZOTERO_LIBRARY_TYPE`, and `ZOTERO_API_KEY` are configured in the local environment. Then call `search-literature --zotero-collection "<collection name>"`; do not fall back to the full Zotero library. Use `--zotero-context all` only when the user intends the selected collection to support Introduction, Data, and Methods evidence.

Every project has `project_passport.yaml`, `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`. Treat these files as append-only audit state owned by the core CLI. Do not edit them manually; use `status`, `checkpoint`, `resume`, or stage commands.

## Review and Revision Loop

When any gate fails, run `diagnose-gate-failures` before giving broad advice. `status` and `run-pipeline` recommend it automatically when integrity or final quality reports failed. After an assembled draft exists, run `review-draft`, then `generate-revision-plan`. Do not let `apply-revision` rewrite scientific content; it only marks affected stages stale. If the plan requires adding data, changing methods, or lowering claims, ask the user to confirm the scientific choice. After reruns, use `re-review`.

## Skill Reuse

Before building new data-analysis or method-code workflows, search for existing reusable skills or GitHub skill repositories. Reuse or install a suitable skill before creating a new one. If a new reusable workflow is created during implementation, summarize it as a future skill candidate with inputs, commands, outputs, validation checks, and failure modes. For PDF or full-text literature fetching, prefer the GitHub skill `Dictation354/paper-fetch-skill` when that need arises; install it with the system `skill-installer` flow and tell the user to restart Codex.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
