# Human Checkpoint Packages

Draftpaper-loop pauses for a human decision only after it has written one
portable checkpoint package. The package is offline and reviewable without the
CLI or a web service:

```text
review/checkpoints/<checkpoint_id>/
├── stage_summary.zh-CN.html
├── stage_summary.json
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

`change_report.json` is the machine-readable summary of generated, modified,
deployed, validated, and failed content. `unresolved_issues.json` is the
structured unresolved-issue projection, and `agent_payload.json` contains the
exact relative/absolute paths, primary artifacts, confirmation meaning, and
the single confirmation command. All companions are required for a consumable
checkpoint. Presentation-only changes to the HTML do not change the scientific
checkpoint hash, while upstream evidence changes invalidate it.
