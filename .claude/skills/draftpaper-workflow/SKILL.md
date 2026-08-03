---
name: draftpaper-workflow
version: 0.37.0
description: Use when Claude Code, Codex, or another supported coding agent operates Draftpaper-loop projects through the authoritative CLI workflow and evidence gates.
---

# Draftpaper-loop Workflow

Treat the installed `draftpaper_cli` package as the workflow authority. Do not
reimplement stage ordering, write project state directly, or infer stale stages
from memory.

Do not directly edit project.json. Do not directly edit stage_manifest files.

## Authoritative artifacts and transactions

- Manuscript sections are authoritative in their stage directories, such as
  `methods/methods.tex`; `latex/sections/*.tex` is rebuildable output. Apply a
  user revision only with `apply-section-revision`, then inspect its transaction
  receipt and the computed stale artifacts.
- Project metadata, YAML mirrors, stage manifests, passports, evidence
  snapshots, and revision candidates must change through CLI transactions. If
  a command reports `rollback_incomplete`, stop and run `doctor`/`recover`.
- Use artifact IDs, paths, hashes, schema families, and producer/consumer edges
  from the artifact DAG. Stage labels are a summary, not a second truth source.

## Plugin and execution truth

- Read the normalized plugin manifest and execution contract. A plan-only,
  mock-only, contract-only, or candidate plugin cannot be reported as a live
  project execution.
- Fixture execution proves a plugin contract, not a paper result. Core evidence
  requires a project run event and matching output hashes.
- Data and method capability bindings gate executable analysis. Discipline
  review rules evaluate the generated Results and their evidence after Results
  exist; they do not fabricate or silently replace figures.

## Required control loop

Before changing a paper project:

```powershell
python -m draftpaper_cli.cli session-preflight --project <project>
python -m draftpaper_cli.cli status --project <project>
python -m draftpaper_cli.cli verify-next-action --project <project>
```

Use the recommended command only when verification passes. For ordinary
progression, call:

```powershell
python -m draftpaper_cli.cli continue --project <project>
```

When `status` reports an explicit human checkpoint, show the evidence or
decision request to the user and stop. Never confirm a research plan, accept
core evidence, promote a plugin, downgrade a claim, confirm the final
manuscript, or accept a manuscript revision on the user's behalf.

Every human checkpoint must first produce a portable Chinese summary package:
`review/checkpoints/<checkpoint_id>/stage_summary.zh-CN.html`,
`stage_summary.json`, `artifact_manifest.json`, and
`confirmation_request.json`. The Agent response must show both the project
relative path and the current machine's absolute path, list primary artifacts
and unresolved issues, and state what the confirmation means. Open the HTML
before asking the user to confirm. A missing summary or path is a blocker, not
a reason to fall back to a vague "please confirm" message. Use
`show-checkpoint-summary` for a read-only copy of the exact paths.

## Scientific boundaries

- Preserve the evidence-first order: literature and research plan, data and
  methods, executable figures, human core-evidence confirmation, manuscript,
  final citation audit, then independent reviews.
- New paper projects use the configured central projects root; large datasets
  remain read-only through private locators and public data contracts.
- The Chinese-first research-plan and feasibility packet is a human scientific
  checkpoint. Key-figure code may execute only against the current confirmed
  plan hash. Implementation repair may not change claims, data roles, methods,
  statistics, main figures, or panels; reopen the plan for human correction if
  any scientific contract must change.
- A project-local method may satisfy a research capability only after the
  capability audit records its inputs, outputs, hashes, and execution scope.
- A scientific failure is not a command failure. Follow the structured rescue
  route instead of fabricating a substitute figure or weakening a gate.
- Result Support v3 is a hash-bound whole-checkpoint decision: resolve current
  evidence first, use one downgrade or supplement route, and reopen the same
  checkpoint for evidence findings.
- Citation repair narrows or rewrites claims while retaining curated
  references. It must run after the final assembled manuscript.
- Literature search may enrich retained, anchor, and user-selected works with
  metadata-only GitHub and Zenodo code-source leads. Use
  `enrich-literature-code-leads` or `discover-research-code`; these commands
  do not download, extract, install, or execute third-party code. A Zenodo
  version DOI, GitHub release, stars, forks, or paper citation count is a
  provenance/adoption signal, not proof of scientific validity.
- Default code-source mode is `knowledge_base`: prefer the latest stable
  release while retaining paper-era lineage. Use `reproduction` only when the
  user explicitly requests paper-version reproduction; never substitute the
  latest release for an unavailable exact version.
- Downloading an archive requires the guarded
  `fetch-research-code-archive --confirm-download` action, checksum and
  license inspection, and a later fixture-based human promotion. Never run
  archive code during metadata enrichment.
- Use `doctor` and `recover` for diagnosis. Do not edit `project.json`, stage
  manifests, passports, evidence snapshots, or append-only ledgers by hand.

## Stage order

The CLI owns the exact next action. Its scientific order is `create-project`,
`search-literature`, `resolve-journal-template`, `generate-plan`, task-aware
statistics and pre-execution support, human research-plan confirmation, data
and `collect-method-plan`, confirmed-storyboard figure planning and method
execution, `verify-methods`, `assess-result-validity`, result support,
key-results/core-evidence
confirmation, `inventory-results`, `write-results`, post-Results discipline
review and semantic repair, `write-introduction`, Data and `write-methods`,
`write-discussion`, `assemble-latex`, integrity, final citation audit, two
independent reviews, `quality-check`, and final manuscript confirmation.

## Rerun rules

When references change, regenerate the plan and affected evidence/writing.
When results change, reopen core evidence and regenerate Results and downstream
sections. Let `status` and `verify-next-action` compute the precise stale scope.
