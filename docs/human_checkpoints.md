# Human Checkpoint Packages

The current checkpoint contract is `dpl.checkpoint_summary.v4`. v1/v2
summaries remain readable for audit, and v3 packages remain read-compatible;
legacy packages are not upgraded in place. v4 adds review requirement,
decision actor, StageActivityBundle, and scientific-baseline references.

Draftpaper-loop pauses for a human decision only after it has written one
portable checkpoint package. The package is offline and reviewable without the
CLI or a web service:

```text
review/checkpoints/<checkpoint_id>/
├── stage_summary.zh-CN.html
├── stage_summary.json
├── stage_activity_bundle.json
├── artifact_manifest.json
├── confirmation_request.json
├── change_report.json
├── unresolved_issues.json
└── agent_payload.json
```

The Chinese HTML is the primary user-facing artifact. It explains the stage
purpose, scientific summary, generated files, modified files, deployments and
bindings, validation results, failures, unresolved issues, primary inspection
targets, confirmation meaning, rejection route, and the exact confirmation
command. Each path is shown relative to the project and, in the Agent response,
as an absolute path on the current machine.

The v4 summary explicitly records `identity`, `core_metrics`, `sample_flow`,
`review_state`, `review_requirement`, `decision_status`, `decision_actor_type`,
`stage_activity_bundle`, `baseline_refs`, `confirmation_contract`, and the
recovery route. The HTML, JSON, and Agent payload are projections of the same
summary facts. `confirmable` means that the machine contract passed; it does
not mean that the user has confirmed the scientific interpretation. An
authorized Agent decision is `agent_approved`, never `user_confirmed`; C3
remains human-only.

Checkpoint state and decision authority are separate. C0 notification packages
are system-acknowledged and may continue automatically while remaining fully
inspectable. C1 packages may be reviewed by an Agent only under a current,
hash-bound delegation. C2 packages additionally require explicit scientific-
freeze authority and an independent reviewer Agent. C3 scientific routes,
external side effects, licenses, author identity, and release remain human-only.
Delegation eligibility is rechecked against the policy hash, runtime identity,
scope, revision cycle, expiry, change-class boundary, unresolved items, and
summary validation before every Agent decision. Revocation writes a separate
receipt and never rewrites the original delegation file.

The checkpoint binds semantic and evidence identities, not report timestamps,
HTML styling, or machine-specific absolute paths. Changing an upstream data,
method, run, metric, cohort, or evidence artifact invalidates the old
checkpoint. A stale checkpoint cannot be consumed by `resume`.

Use:

```powershell
python -m draftpaper_cli.cli show-checkpoint-summary --project <project>
python -m draftpaper_cli.cli resume --project <project> --checkpoint-hash <hash>
```

The Agent must show the summary path, primary artifact paths, unresolved issue
count, confirmation meaning, and one command. It must never ask for an
unexplained “please confirm”. The current version groups one stage or external
edit batch into one atomic checkpoint; multi-claim decomposition remains a
future feature.

`blocked`, `stale`, `preview_only`, identity-missing, and `legacy_unqualified`
pages must not expose a confirmation command. An anonymous fixture showcase may
set `test_mode=true` and `test_auto_confirmation=true` to exercise the page
flow, but those markers must never enter a real project's confirmation record,
ledger, or active pointer.

`change_report.json` is the machine-readable summary of generated, modified,
deployed, validated, and failed content. `unresolved_issues.json` is the
structured unresolved-issue projection, and `agent_payload.json` contains the
exact relative/absolute paths, primary artifacts, confirmation meaning, and
the single confirmation command. All companions are required for a consumable
checkpoint. Presentation-only changes to the HTML do not change the scientific
checkpoint hash, while upstream evidence changes invalidate it.

## Complete deliverables versus transaction changes

The HTML has two separate views. **Complete stage deliverables** is the review
scope: every relevant figure, table, text report, run manifest, evidence file,
and code file that belongs to the stage, including artifacts whose bytes were
unchanged at checkpoint time. **Transaction changes** is only the delta from
the previous passport snapshot. An empty delta therefore never means that the
stage produced nothing.

For `core_evidence`, the summary also reads the project-local core-evidence
report, validity and support reports, metric CSV previews, figure metadata, and
figure-to-code trace. Each listed artifact has a project-relative link, a local
hash, a purpose, and an optional image or bounded table preview. The HTML is a
review index, not a replacement for the original files; the original paths and
hashes remain the source of truth.

When an upstream artifact has drifted, use the read-only preview command:

```powershell
python -m draftpaper_cli.cli preview-checkpoint-summary --project <project> --checkpoint-hash <hash>
```

The preview writes a derived `*-preview` package without changing the ledger or
checkpoint index. It is explicitly non-consumable and hides the resume command.
Resolve the drift and create a new canonical checkpoint before asking for a
human confirmation.

## Runtime identity updates

`session-preflight` intentionally blocks an existing project when its wheel,
source commit, command registry, schema, or workflow Skill differs from the
recorded runtime. After the new runtime has passed release-candidate checks,
accept the runtime migration explicitly:

```powershell
python -m draftpaper_cli.cli session-preflight --project <project> --accept-runtime-update
```

This only updates `.draftpaper/runtime_lock.json` and writes a runtime migration
receipt. It does not change the research plan, passport, data, methods, results,
or any scientific checkpoint. Without explicit acceptance, do not use the flag;
after migration, rerun `status`, `verify-next-action`, and the applicable
scientific evidence gates.
