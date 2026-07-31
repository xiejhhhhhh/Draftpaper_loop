# CLAUDE.md

Draftpaper-loop is a local-first, staged research-paper loop engine. The
installed `draftpaper_cli` package is the workflow authority: it owns stage
ordering, stale propagation, evidence gates, and the exact next action.

## Non-negotiable rules

- Never reimplement stage ordering, write project state directly, or infer
  stale stages from memory. Drive everything through the CLI.
- Never edit these by hand: `project.json`, `project.yaml`, stage manifests,
  `project_passport.yaml`, evidence snapshots, or the append-only ledgers
  (`artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, `integrity_ledger.jsonl`,
  `transaction_ledger.jsonl`). Use `doctor` and `recover` for diagnosis.
- A scientific failure is not a command failure. Follow the structured rescue
  route (`diagnose-figure-execution`, `repair-figure-data`,
  `repair-figure-method`, statistical rescue) instead of fabricating a
  substitute figure or weakening a gate.

## Required control loop

Before changing any paper project:

```bash
python -m draftpaper_cli.cli status --project <project>
python -m draftpaper_cli.cli verify-next-action --project <project>
```

Run the recommended command only when verification passes. For ordinary
progression:

```bash
python -m draftpaper_cli.cli continue --project <project>
```

## Human checkpoints (never act on the user's behalf)

When `status` reports an explicit human checkpoint, show the evidence or
decision request to the user and stop. Protected actions that must always be
confirmed by the human: `checkpoint`, `resume`, `confirm-research-plan`,
`reopen-research-plan`, `confirm-final-manuscript`, `apply-result-downgrade`,
`promote-plugin-candidate`, `accept-revision`, `rebase-project-passport`.

## Repository layout

- `draftpaper_cli/` — core package and CLI (`python -m draftpaper_cli.cli`,
  or the `draftpaper` entry point after `pip install -e .`).
- `draftpaper_cli/resources/draftpaper_workflow/` — canonical agent skill
  (single source of truth; repo copies under `.claude/skills/` and
  `codex_skills/` are generated from it and hash-checked).
- `.claude/skills/draftpaper-workflow/` — Claude Code project skill.
- `codex_skills/draftpaper-workflow/` — Codex skill wrapper; its
  `references/commands.md` is the full command reference shared by all agents.
- `projects/` — generated paper projects (git-ignored).
- `tests/` — pytest suite; run with `python -m pytest`.

## Development commands

```bash
python -m pip install -e .[dev,plotting]
python -m pytest                      # full suite
python -m ruff check draftpaper_cli   # lint
draftpaper skill-doctor --agent claude
draftpaper mcp-doctor
```

## MCP

A project-scoped `.mcp.json` at the repository root starts the local stdio
MCP server (`python -m draftpaper_cli.mcp.server`). It is a thin, bounded
projection over the CLI: human checkpoints and destructive administration are
excluded by CommandSpec policy. Regenerate the config with
`draftpaper mcp-install --output .mcp.json`.
