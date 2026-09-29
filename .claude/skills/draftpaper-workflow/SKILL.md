---
name: draftpaper-workflow
version: 0.43.2
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

## Environment

Before publication, run `doctor --target publication --json`. On Windows,
`tools/bootstrap_windows_environment.ps1 -Mode Check` checks Visual C++ x64,
Git, and MiKTeX. Review remediation, then verify in a temporary directory:

```powershell
python -m draftpaper_cli verify-environment --target publication --compile-latex --output <output>
```

It checks pypdf, XeLaTeX/pdfLaTeX, BibTeX, `kpsewhich`, citations, and a
non-empty PDF. Output stays in that directory; never target a real paper
project. End-to-end checks use a separate temporary project. MinerU, GPU,
Node.js, Java, and discipline packages are optional. Use
`requirements/runtime-constraints.txt` with the selected extra. `minimal` and
`plotting` support Python 3.10-3.12; other extras need 3.11-3.12. `research`
adds fulltext; `agent` adds MCP. Browser assets are opt-in. Doctor does not
expose optional-provider secrets.

## Evidence and Literature

Fixtures, mocks, and plan-only plugins test contracts, not scientific results.
Record local method inputs, outputs, hashes, and scope. Validate
`MetricEvidence`, `CountEvidence`, active `RunEvidenceBundle`, and
`FigureCodeTrace v2`; compare identity before values because models, cohorts,
splits, or denominators may differ.

Literature discovery, identity resolution, and full-text fetching are separate.
`search-literature` proposes candidates, applies symmetric discipline/topic
gates, and resolves DOI/title/author/year identity. The vendored paper-fetch
adapter resolves known candidates and fetches evidence on demand; it does not
discover topics or justify fetching every result. Re-score fetched content;
keep mismatched, off-topic, ambiguous, review-required, and orphan records out
of active snapshots, citation pools, summaries, and Agent context. GitHub and
Zenodo code leads stay metadata-only unless the guarded archive route is
approved; never execute third-party code during enrichment.

After search, inspect the hash-bound packet from
`prepare-literature-admission`; accept, exclude, or defer every candidate.
Gate-rejected candidates need a reason and explicit override before activation.
Run `activate-literature-corpus` with that packet hash and decision manifest,
then `review-literature-coverage`. Teaching uses only the explicitly confirmed
corpus, never an inferred active directory. Show its hash-bound
`literature_confirmation_packet`, then run
`confirm-literature-corpus --packet-hash <hash>` only after human review. Its
receipt binds the canonical registry, active snapshot, and usage plan; input
changes require a fresh packet before Learn publishes literature cards.

## Human Review

New checkpoints write readable Chinese and English decision pages,
`stage_audit.json`, `stage_summary.json`, an artifact manifest, and a
confirmation request. Technical audit HTML is created only by
`render-checkpoint-audit` in `.draftpaper/render_cache/audit/`; it is temporary
and never an immutable package artifact. Do not create a project-external
readability sidecar.

Research-plan review uses an immutable `HumanReviewPacket`: read with
`show-human-review-packet`, validate with `validate-research-plan-review`,
compare with `compare-research-plan-decision`, and explain reopens with
`explain-research-plan-reconfirmation`. Equivalent reviews reuse the packet;
changes to question, data role, method, cohort, split, metric, claim boundary,
or figure semantics need a new decision.

For a checkpoint, show the readable decision page first, then its semantic
delta, deliverables, exclusions, unresolved issues, and confirmation meaning.
Use `inspect-review-evidence --ref <reference>` only for selected evidence.
`show-checkpoint-summary`, `render-checkpoint-audit`,
`validate-checkpoint-readability`, and `shadow-checkpoint-v6` are read-only.

`checkpoint` constructs the packet; `resume` consumes a valid receipt. Agent
approval requires active hash-bound delegation and records `agent_approved`,
never `user_confirmed`. C0 may be system-acknowledged; C1 revalidates policy
and scope; C2 needs scientific-freeze permission and an independent reviewer.
C3 scientific routes, claims, plugin promotion, licenses, author identity,
final manuscript, and release remain human-only. For C3 delivery, query
`pending-checkpoint-notification` with the request and stable consumer ID; show
the returned page, then acknowledge only after display. Acknowledgement records
delivery only (`decision_status=pending`), never scientific approval; an
already-delivered notice must not be repeated.

Before C3, use `prepare-core-evidence-batch` and resolve readiness blockers.
For a legacy checkpoint without batch scope, inspect
`shadow-core-evidence-batch-migration` before any resume, confirmation, or Agent
review. If it reports `associate_complete_legacy_request`, register the full
authoritative scope with `prepare-core-evidence-batch`; this may seal the
unchanged request association without rewriting the checkpoint event. Reuse
only a complete, unchanged package/candidate; pending still needs author
confirmation, and only a valid `approve/user_confirmed` receipt may resume that
same checkpoint. Never reuse rejected, refinement, Agent, or system decisions.
If scope or identity is incomplete/mismatched, reconcile fully and prepare a
new batch; retain the old packet as audit-only.

## Stage Order

Use the CLI-owned sequence: `create-project`, `search-literature`,
`resolve-journal-template`, `generate-plan`, `collect-method-plan`,
`verify-methods`, `assess-result-validity`, `inventory-results`,
`write-results`, `write-introduction`, `write-methods`, `write-discussion`,
`assemble-latex`, and `quality-check`. When references change, regenerate the
affected plan and writing. When results change, reopen core evidence and
regenerate Results and downstream sections; use `status` to compute stale
scope.

## Evidence and Revision

Use `prepare-evidence-rebind`/`apply-evidence-rebind` for legacy outputs;
`author_edit` previews stay unreconciled until reconciliation. A semantic
revision can be applied only after a C3 user-confirmation page displays the
same frozen candidate SHA-256 and produces a candidate-bound receipt. Final
promotion requires the exact candidate hash, parent baseline ID, and immutable
user receipt ID; never hand-write a receipt or reuse one from an older
candidate.
