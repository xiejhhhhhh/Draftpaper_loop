---
name: draftpaper-workflow
version: 0.41.1
description: Use when Claude Code, Codex, or another supported coding agent operates Draftpaper-loop projects through the authoritative CLI workflow and evidence gates.
---

# Draftpaper-loop Workflow

Use the installed `draftpaper_cli` package as the workflow authority. Do not
reimplement stage ordering, infer stale stages from memory, or write project
state by hand. In particular, never directly edit `project.json`, stage
manifests, passports, evidence snapshots, or append-only ledgers.
Do not directly edit project.json or stage_manifest files.
Do not directly edit stage_manifest files.

## Before project changes

Run the control loop first:

```powershell
python -m draftpaper_cli.cli session-preflight --project <project>
python -m draftpaper_cli.cli status --project <project>
python -m draftpaper_cli.cli verify-next-action --project <project>
```

Use the recommended command only when its preconditions pass. Normal
progression is:

```powershell
python -m draftpaper_cli.cli continue --project <project>
```

A runtime identity mismatch stops the workflow. After release-candidate
checks and explicit user acceptance, use `session-preflight --accept-runtime-update`;
this writes only a migration receipt and runtime lock. If a transaction reports
`rollback_incomplete`, stop and run `doctor` or `recover`.

## Evidence and execution truth

- Read normalized plugin manifests and execution contracts. Plan-only,
  mock-only, candidate, and fixture plugins cannot be reported as live paper
  execution; a fixture proves a contract, not a scientific result.
- A project-local method is usable only after its inputs, outputs, hashes, and
  execution scope are recorded. A scientific failure follows its rescue route;
  it is not permission to fabricate a figure or weaken a gate.
- Before Result Support or a checkpoint, validate `MetricEvidence`,
  `CountEvidence`, the active `RunEvidenceBundle`, and `FigureCodeTrace v2`.
  Compare identity before values: different models, validation designs,
  cohorts, or denominator nodes are non-comparable, not numeric conflicts.
- Use `audit-evidence-identity` for a read-only migration audit. It reports
  legacy presentation files, derived rebuilds, and scientific reruns but never
  guesses missing semantics or edits project state.

## Human checkpoints

Every new checkpoint writes a v5 package with `stage_summary.zh-CN.html`
(readable decision page), `stage_audit.zh-CN.html` (technical audit),
`stage_summary.json`, `artifact_manifest.json`, and `confirmation_request.json`.
The decision page covers the question, semantic delta, scientific context,
figures, boundaries, exclusions, reopen conditions, and deliverables; never
create a project-external readability sidecar. v1/v2 are read-only legacy;
v3/v4 remain readable and are never rewritten. Earlier v5 packages created
before FigureClaimMap-bound scientific fingerprints are also read-only; they
must receive an explicit new C3 checkpoint before they can use continuity.
The request binds `scientific_decision_sha256` and the DecisionBrief semantic
hash, not the audit/package hash. Identical valid prior user decisions write a
continuity receipt and continue as a notification. Metric, cohort, split,
sample-unit, method, figure-semantic, or claim-boundary changes require C3.
Show readable relative/absolute paths first, then the audit path, delta,
artifacts, issues, and confirmation meaning. Previews, stale, blocked, and
identity-missing packages cannot be confirmed.

Agent review may continue only inside an active, hash-bound delegation and
must record `agent_approved`; it must never write `user_confirmed`. C0
notification checkpoints may record a `system_acknowledged` receipt and
continue automatically. C1 review must revalidate the policy, runtime,
summary, scope, expiry, revision cycle, change class, unresolved-item, and
side-effect boundaries. C2 additionally needs explicit scientific-freeze
permission and a reviewer Agent independent of the recorded producer. C3
scientific routes, mutually exclusive claim choices, plugin promotion,
licenses, author identity, final manuscript, and release remain human-only.
An anonymous fixture may record `test_auto_confirmation=true` while testing
HTML; that marker must never confirm a real research result or change real
project state. New projects may use `balanced`; existing projects remain
`manual` until the owner opts in.

## Scientific boundaries and order

Preserve the evidence-first order: literature and plan, data and methods,
executable figures, human core-evidence confirmation, manuscript, final
citations, independent reviews, quality checks, and final confirmation. Key
figure code runs only against the confirmed plan hash; implementation repair
cannot change claims, data roles, methods, statistics, or figure contracts.
Reopen the scientific checkpoint when those contracts change.

New projects use the configured central projects root. Large datasets remain
read-only through private locators and public data contracts. Literature may
attach metadata-only GitHub and Zenodo code leads; release/version, stars,
forks, and citation counts are provenance or adoption signals, not validity
proof. Archive download requires the guarded confirmation, checksum, license,
and static inspection route; never execute third-party archive code during
metadata enrichment.

Literature discovery, identity resolution, and evidence fetching are separate
contracts. A discovery provider proposes candidates; it does not prove paper
identity or citation fitness. `search-literature` applies symmetric discipline
and tiered topic gates, resolves shortlist DOI/title/author/year identity, and
uses the vendored paper-fetch adapter only for evidence-on-demand full text.
Ambiguous or mismatched identities never trigger automatic full-text fetching.
Fetched metadata and text are scored again before a work becomes active.
Review-required, topic-mismatched, discipline-mismatched, identity-mismatched,
and orphan artifacts stay outside the active literature snapshot, citation
pool, summaries consumed by Agents, and writing context. Historical orphan
files require `quarantine-orphan-literature` preview, packet-hash apply, and a
hash-verified rollback route. Use `audit-literature-integrity` to verify active
work reachability; never infer active evidence from files merely existing under
`references/fulltext/`. The external Agent `paper-fetch-skill` is useful for
interactive single-paper work, but Core availability depends on the pinned
vendored adapter rather than a user-installed Agent skill.

The CLI owns the exact next action. When references change, regenerate the
affected plan and writing. When results change, reopen core evidence and
regenerate Results and downstream sections; let `status` compute stale scope.

The normal stage route includes `create-project`, `search-literature`,
`resolve-journal-template`, `generate-plan`, `collect-method-plan`,
`verify-methods`, `assess-result-validity`, `inventory-results`,
`write-results`, `write-introduction`, `write-methods`, `write-discussion`,
`assemble-latex`, and `quality-check`.
