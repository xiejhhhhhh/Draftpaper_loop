---
name: draftpaper-workflow
version: 0.42.0
description: Use when Claude Code, Codex, or another supported coding agent operates Draftpaper-loop projects through the authoritative CLI workflow and evidence gates.
---

# Draftpaper-loop Workflow

Use the installed `draftpaper_cli` CLI as the workflow authority. Do not infer
stage order from memory or edit workflow state by hand. Do not directly edit project.json. Do not directly edit stage_manifest files, including passports, evidence snapshots, or append-only ledgers.

## Control Loop

Before changing a project, run:

```powershell
python -m draftpaper_cli.cli session-preflight --project <project>
python -m draftpaper_cli.cli status --project <project>
python -m draftpaper_cli.cli verify-next-action --project <project>
```

Use `continue` only when its reported preconditions pass. A runtime identity
mismatch stops the workflow; after an accepted runtime update, use
`session-preflight --accept-runtime-update`. If a transaction reports
`rollback_incomplete`, stop and use `doctor` or `recover`.

## Evidence and Literature

Treat a fixture, candidate, plan-only plugin, or mock as a contract check, not
live scientific evidence. A project-local method is usable only after its
inputs, outputs, hashes, and execution scope are recorded. Validate
`MetricEvidence`, `CountEvidence`, the active `RunEvidenceBundle`, and
`FigureCodeTrace v2` before result support or a checkpoint. Compare evidence
identity before values: different models, cohorts, splits, or denominators are
not numerically comparable.

Literature discovery, identity resolution, and full-text fetching are separate.
Discovery sources propose candidates; they do not prove citation fitness.
`search-literature` applies symmetric discipline and topic gates, resolves
DOI/title/author/year identity, then uses the vendored paper-fetch adapter for
evidence-on-demand. Do not fetch all candidates by default. Re-score fetched
metadata or text; mismatched, off-topic, ambiguous, review-required, and orphan
records remain quarantined outside active snapshots, citation pools, summaries,
and Agent context. GitHub and Zenodo code leads are metadata-only unless the
guarded archive route is explicitly approved; never execute third-party archive
code during enrichment.

Teaching uses an explicit confirmed corpus, not an inferred active directory.
After `review-literature-coverage`, show the hash-bound
`literature_confirmation_packet` and use `confirm-literature-corpus --packet-hash
<hash>` only after human review. Its receipt binds the canonical registry, active
literature snapshot, and project usage plan; any change to those inputs requires
a fresh packet and confirmation before Learn may publish deep literature cards.

## Human Review

New checkpoints write readable Chinese and English decision pages,
`stage_audit.json`, `stage_summary.json`, an artifact manifest, and a
confirmation request. Technical audit HTML is created only by
`render-checkpoint-audit` in `.draftpaper/render_cache/audit/`; it is temporary
and never an immutable package artifact. Do not create a project-external
readability sidecar.

Research-plan confirmation uses an immutable, versioned `HumanReviewPacket`.
Read it with `show-human-review-packet`; validate it with
`validate-research-plan-review`; compare decisions with
`compare-research-plan-decision`; and explain an actual reopen with
`explain-research-plan-reconfirmation`. Equivalent valid reviews reuse the
prior packet and produce a continuity receipt. Scientific question, data role,
method, cohort, split, metric, claim boundary, or figure semantics changes need
an explicit new human decision.

For a checkpoint, show the readable decision page before audit paths, then its
semantic delta, deliverables, exclusions, unresolved issues, and confirmation
meaning. Use `inspect-review-evidence --ref <reference>` only for selected
evidence. `show-checkpoint-summary`, `render-checkpoint-audit`,
`validate-checkpoint-readability`, and `shadow-checkpoint-v6` are read-only
inspection or shadow tools.

`checkpoint` constructs the packet; `resume` consumes a valid receipt. Agent
approval is permitted only within an active hash-bound delegation and records
`agent_approved`, never `user_confirmed`. C0 may be system-acknowledged; C1
revalidates policy and scope; C2 needs scientific-freeze permission and an
independent reviewer; C3 scientific routes, claim choices, plugin promotion,
licenses, author identity, final manuscript, and release remain human-only.

## Stage Order

Use the CLI-owned sequence: `create-project`, `search-literature`,
`resolve-journal-template`, `generate-plan`, `collect-method-plan`,
`verify-methods`, `assess-result-validity`, `inventory-results`,
`write-results`, `write-introduction`, `write-methods`, `write-discussion`,
`assemble-latex`, and `quality-check`. When references change, regenerate the
affected plan and writing. When results change, reopen core evidence and
regenerate Results and downstream sections; use `status` to compute stale
scope.
