---
description: Diagnose a Draftpaper-loop project and propose safe recovery
argument-hint: <project-path>
allowed-tools: Bash(python -m draftpaper_cli.cli *), Bash(draftpaper *)
---

Diagnose the Draftpaper-loop project at `$ARGUMENTS`:

1. `python -m draftpaper_cli.cli doctor --project $ARGUMENTS --json`
2. Interpret the findings for the user: what is inconsistent, which artifacts
   drifted, and what the CLI recommends.
3. If the report recommends recovery, propose
   `python -m draftpaper_cli.cli recover --project $ARGUMENTS` and run it only
   after the user agrees.

Never repair state by editing `project.json`, stage manifests, passports,
evidence snapshots, or append-only ledgers by hand.
