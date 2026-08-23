# Human Checkpoint Packages

New checkpoints use `dpl.checkpoint_summary.v6`. v1-v5 records are historical
read-only packages: they remain readable and comparable, but are never
overwritten or silently upgraded into a new scientific decision.

## What the author opens first

Every v6 checkpoint writes a portable package under
`review/checkpoints/<checkpoint_id>/`:

```text
stage_summary.zh-CN.html              # readable author decision page
stage_summary.en.html                 # English rendering of the same decision
stage_audit.json                      # complete machine technical audit
stage_summary.json                    # v6 package contract
human_decision_brief_v1.json          # facts and decision statements shown to the author
scientific_decision_fingerprint_v1.json
checkpoint_audit_fingerprint_v1.json
checkpoint_presentation_fingerprint_v1.json
stage_activity_bundle.json
artifact_manifest.json
figure_claim_map_v1.json
confirmation_request.json
agent_payload.json
checkpoint_readability_report.json
```

Open `stage_summary.zh-CN.html` first. It is the formal, hash-bound decision
page, not a reduced sidecar made by an Agent. In roughly one minute it states:

- what scientific decision is requested;
- what changed since the last valid author decision;
- the sample, validation design, main result, main figures, and claim boundary;
- what is explicitly outside this confirmation;
- what would reopen scientific confirmation; and
- the readable deliverables and next action.

`stage_audit.json` contains the complete technical trail: bounded current
activity window, artifact inventory, transaction delta, validation tables,
evidence identity, hashes, and recovery details. Ordinary review does not load
it. Use `render-checkpoint-audit` to create a disposable HTML cache under
`.draftpaper/render_cache/audit/` when technical investigation is needed.

## Decision identity and continuity

v6 separates three identities:

| Identity | Covers | Effect of a change |
|---|---|---|
| `scientific_decision_sha256` | data/cohort/split/sample unit, executable analysis specification, method contract/run, metric/uncertainty, figure semantics, and claim boundary | new C3 author decision |
| `audit_bundle_sha256` | artifact manifest, activity receipts, validation reports, and technical audit | audit refresh only |
| `presentation_sha256` | decision-page rendering and localization | page rebuild only |

The confirmation request binds the scientific decision hash and the semantic
DecisionBrief hash, not the full audit page or a regenerated PDF. If the latest
valid user receipt has exactly the same scientific and brief identities, and no
missing, stale, conflict, or unclassified evidence exists, Draftpaper-loop
writes `confirmation_continuity_receipt.json`. The new checkpoint becomes a
notification and can continue without asking the author to enter another C3
hash. This preserves the previous user decision; it never pretends that a
system or Agent made a new scientific decision.

Changes to a metric value or definition, uncertainty, cohort, split, sample
unit, executable analysis specification, method contract, declared
implementation entry point, run identity, figure semantic series, or claim
boundary always create a new scientific delta and require a new author
decision. A core-evidence package without an executable analysis specification
or method-contract identity is fail-closed and cannot use continuity.

## Bounded scope and review authority

`StageActivityBundle v2` begins after the previous checkpoint boundary and
does not narrate historic checkpoints, resumes, or unrelated retries. Artifact
selection is manifest-first with bounded stage discovery; old
`review/checkpoints/`, cache, lineage, and historical result directories are
not promoted into a current decision package merely because they exist.

The decision page is author-visible. Internal ledgers, trace rows, package
hashes, and audit attachments remain `internal_audit`; independent manuscript
review must consume only `reviewer_visible` material. `FigureClaimMap` binds a
main figure to its decision statement and blocks declared cohort/split conflicts
between figure metadata, caption metadata, and the active evidence identity.

C0 notification packages may record `system_acknowledged`; C1/C2 packages may
use a valid scoped Agent delegation; C3 scientific routes remain human-only
unless a continuity receipt proves that the author has already confirmed the
identical scientific decision. An Agent may record `agent_approved`, never
`user_confirmed`.

## Literature corpus confirmation

Formal literature teaching is a separate, compact human checkpoint. First run
`review-literature-coverage` and inspect
`references/literature_confirmation_packet.zh-CN.md`. Then confirm the exact
packet hash:

```powershell
draftpaper confirm-literature-corpus --project <project> --packet-hash <hash>
```

The receipt binds the canonical reference registry, the active literature
snapshot, and the project usage plan. It does not add citations or change the
scientific manuscript. A later change to any bound set produces a new packet;
Learn returns to `corpus_confirmation_pending` instead of using stale cards or
unrelated historical references.

## Commands

```powershell
draftpaper show-checkpoint-summary --project <project> --view decision
draftpaper show-checkpoint-summary --project <project> --view decision --language en
draftpaper show-checkpoint-audit --project <project> --checkpoint-package-id <id>
draftpaper render-checkpoint-audit --project <project> --checkpoint-package-id <id>
draftpaper compare-checkpoint-decision --project <project> --against latest-confirmed
draftpaper explain-reconfirmation --project <project> --checkpoint-package-id <id>
draftpaper validate-checkpoint-readability --project <project> --checkpoint-package-id <id>
draftpaper validate-checkpoint-readability --project <project> --checkpoint-package-id <id> --language en
draftpaper show-confirmation-continuity --project <project> --checkpoint-type core_evidence
draftpaper rebuild-checkpoint-presentation --project <project> --checkpoint-package-id <id>
draftpaper shadow-checkpoint-v6 --project <project> --output-root <outside-project-directory>
draftpaper validate-research-plan-review --project <project>
draftpaper show-human-review-packet --project <project>
draftpaper inspect-review-evidence --project <project> --ref artifact:results/metrics.json
draftpaper resume --project <project> --checkpoint-hash <hash>
```

`compare-checkpoint-decision`, `explain-reconfirmation`, and
`validate-checkpoint-readability` are read-only. Rebuilding presentation can
rewrite only the two HTML files and readability report; it does not alter the
scientific decision fingerprint or create a new confirmation obligation.

`blocked`, `stale`, `preview_only`, identity-missing, legacy, or conflict
packages never expose an author confirmation command. `preview-checkpoint-summary`
remains a non-consumable derived package. Anonymous fixtures may use
`test_auto_confirmation=true`, but that marker cannot confirm a real project.

## Legacy migration and shadow verification

v1-v5 packages are historical evidence only. They may be inspected through a
migration audit, but cannot be silently continued. When semantic equivalence or
a hash-bound user receipt cannot be proven, the workflow creates one new v6 C3
decision package.

`shadow-checkpoint-v6` is a regression audit for an existing project. Its
`--output-root` must be outside the project directory. The command records
before/after hashes for the passport, ledgers, promoted snapshot, checkpoint
records, and manuscript PDF, then writes JSON and HTML reports outside the
project. A failed unchanged-state check is a blocker, never a reason to repair
project evidence during the audit.

## Runtime identity updates

`session-preflight` blocks an existing project when its wheel, source commit,
command registry, schema registry, or workflow Skill differs from the recorded
runtime. After release-candidate validation, accept that runtime migration
explicitly:

```powershell
python -m draftpaper_cli.cli session-preflight --project <project> --accept-runtime-update
```

The command only updates `.draftpaper/runtime_lock.json` and writes a migration
receipt. It does not alter research evidence, a scientific decision, or a
checkpoint package.
