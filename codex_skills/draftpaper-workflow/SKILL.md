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

1. `create-project` -> `search-literature` -> `resolve-journal-template` -> research feasibility -> `generate-plan`.
2. Resolve capabilities and plan feasibility; repair scope when required.
3. Acquire/inventory/assess data, record the data observation, then `collect-method-plan` and build the blueprint.
4. Assess plugin/method sufficiency; audit project code or rescue missing capabilities before blocking.
5. Plan/contract figures, generate stage-owned code, build traces, then `verify-methods`.
6. Resolve figure evidence -> `assess-result-validity` -> result support -> core evidence -> human checkpoint/resume.
7. `inventory-results`; complete accepted free writing and `write-results`, then discipline review.
8. Complete accepted free writing for `write-introduction`, Data, `write-methods`, and `write-discussion`.
9. Assess functional quality -> `assemble-latex` -> integrity -> final citation audit -> bibliography proof.
10. Freeze one anonymous manuscript, record two independent reviews, resolve findings, then `quality-check`.

Use `assemble-latex --compile-pdf` when the user wants a local review PDF. Use `compile-latex-pdf` after manual edits under `latex/`.

## Rerun Rules

Rerun from the earliest affected stage. If references change, rerun plan, evidence, Results, and writing. Journal changes affect plan, writing, and assembly; data affects method planning onward; code or method changes affect verification onward. If results change, rerun validity, core evidence, Results, and downstream writing. Template-only changes affect assembly and quality.

## Gates

Never plan before journal and research feasibility. Stop on `blocked_high_similarity` unless the user explicitly continues. Record visible data/method observations; never save hidden reasoning.

The loop is evidence-first. Figure contracts precede code generation; failed scientific figures route to data/method repair or plan revision, never substitute diagrams. Data code belongs under `data/scripts`; modelling, validation, and plotting belong under `methods/`; `code/` is compatibility-only.

Results require valid, human-confirmed evidence and contain no citations. Data/Methods use their context builders and code/formula traces. Discussion uses the comparison matrix and BibTeX evidence. Each section follows packet -> Codex free prose -> submission -> Scientific Editor -> local repair -> explicit acceptance -> writer. Fallback prose cannot reach release. Run integrity before final citation audit and `quality-check`.

For Zotero-backed references and append-only audit files, follow `references/commands.md`; do not edit CLI-owned ledgers or manifests manually.

For a scientific redesign of an existing project, use `plan-project-version` and create a clean `_vN` child. Keep the parent read-only and import only allowlisted assets. Do not copy passports, stage manifests, old figure metadata, sufficiency reports, audits, evidence snapshots, or reviewer reports as active state. Use `migrate-project` only when scientific content is unchanged and only the project schema needs upgrading.

## Review and Revision Loop

When a gate fails, follow `status`, `doctor`, or `run-pipeline` through diagnosis, recovery, statistical or analysis repair, reviewer-task reruns, and `generate-revision-plan`. Inspect the generated review plan, feasibility report, and confirmation requests before rerunning data or methods. `doctor` and `recover` are read-only and never confirm scientific evidence or modify claims. `apply-revision` only marks stages stale; use `re-review` after reruns.

## Skill Reuse

Reuse suitable skills or public research workflows before creating new analysis code. Record reusable work as a future skill candidate; use the configured paper-fetch skill for full text.

## Reporting

Report command status, important output paths, and the next actionable stage. If a command fails, summarize the error JSON and suggest the smallest upstream rerun instead of editing state files manually.
