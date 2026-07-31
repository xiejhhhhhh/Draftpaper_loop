---
description: Advance a Draftpaper-loop project by one verified stage
argument-hint: <project-path>
allowed-tools: Bash(python -m draftpaper_cli.cli *), Bash(draftpaper *)
---

Advance the Draftpaper-loop project at `$ARGUMENTS` by exactly one safe step:

1. `python -m draftpaper_cli.cli status --project $ARGUMENTS`
2. `python -m draftpaper_cli.cli verify-next-action --project $ARGUMENTS`
3. Only if verification passes and the next action is NOT a protected human
   checkpoint (`checkpoint`, `resume`, `confirm-research-plan`,
   `reopen-research-plan`, `confirm-final-manuscript`, `apply-result-downgrade`,
   `promote-plugin-candidate`, `accept-revision`, `rebase-project-passport`):
   run `python -m draftpaper_cli.cli continue --project $ARGUMENTS`.

If the loop stops at a human checkpoint, show the user the evidence or
decision request and wait. Afterwards report the command status, the
scientific decision, important artifact paths, and the verified next action.
