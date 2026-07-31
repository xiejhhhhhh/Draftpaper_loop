---
description: Report a Draftpaper-loop project's state and the verified next safe action
argument-hint: <project-path>
allowed-tools: Bash(python -m draftpaper_cli.cli *), Bash(draftpaper *)
---

Run the Draftpaper-loop control loop for the project at `$ARGUMENTS`:

1. `python -m draftpaper_cli.cli status --project $ARGUMENTS`
2. `python -m draftpaper_cli.cli verify-next-action --project $ARGUMENTS`

Then report: the current pipeline state, any stale stages or drift, the
verified next action, and whether that action is an explicit human checkpoint.
If it is a human checkpoint, present the evidence or decision request and stop
— never confirm it on the user's behalf. Do not run any mutating command from
this slash command.
