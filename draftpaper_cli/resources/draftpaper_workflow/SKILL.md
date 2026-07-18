---
name: draftpaper-workflow
version: 0.30.5
description: Use when Codex operates Draftpaper-loop projects through the authoritative CLI workflow and evidence gates.
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

## MCP and release boundaries

- MCP science or network execution requires the short-lived capability token
  issued for the exact project, command, arguments, and time window. A boolean
  confirmation is not authorization.
- Before a release, validate command contracts, plugin manifests, schema and
  third-party registries, the generated release manifest, secret scan,
  project-scoped dependency audit, wheel installation, and cross-discipline
  regressions. Synthetic fixtures validate contracts, not manuscript quality.

## Required control loop

Before changing a paper project:

```powershell
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

## Scientific boundaries

- Preserve the evidence-first order: literature and research plan, data and
  methods, executable figures, human core-evidence confirmation, manuscript,
  final citation audit, then independent reviews.
- New paper projects use the configured central projects root. Large source
  datasets remain read-only in place through private locators and public data
  contracts; do not create the paper project next to a large dataset merely
  because the data live there.
- The Chinese-first research-plan and feasibility packet is a human scientific
  checkpoint. Key-figure code may execute only against the current confirmed
  plan hash. Implementation repair may not change claims, data roles, methods,
  statistics, main figures, or panels; reopen the plan for human correction if
  any scientific contract must change.
- A project-local method may satisfy a research capability only after the
  capability audit records its inputs, outputs, hashes, and execution scope.
- A scientific failure is not a command failure. Follow the structured rescue
  route instead of fabricating a substitute figure or weakening a gate.
- Citation repair narrows or rewrites claims while retaining curated
  references. It must run after the final assembled manuscript.
- Use `doctor` and `recover` for diagnosis. Do not edit `project.json`, stage
  manifests, passports, evidence snapshots, or append-only ledgers by hand.

## Long-running work

Use the persistent job commands for literature fetching, capability rescue,
method execution, figure generation, regressions, and independent-review
orchestration when the operation can outlive the current terminal or MCP
session.

Report the command status, scientific decision, important artifact paths, and
the verified next action.

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
