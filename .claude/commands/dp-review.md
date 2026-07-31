---
description: Walk a Draftpaper-loop project through the review / revision diagnosis chain
argument-hint: <project-path>
allowed-tools: Bash(python -m draftpaper_cli.cli *), Bash(draftpaper *)
---

Run the review-and-revision diagnosis chain for the Draftpaper-loop project at
`$ARGUMENTS`. First confirm position with `status` and `verify-next-action`,
then follow the sequence the CLI recommends, typically:

1. `python -m draftpaper_cli.cli diagnose-gate-failures --project $ARGUMENTS`
2. `python -m draftpaper_cli.cli review-draft --project $ARGUMENTS`
3. `python -m draftpaper_cli.cli assess-publication-readiness --project $ARGUMENTS`
4. `python -m draftpaper_cli.cli recommend-statistical-revision --project $ARGUMENTS`
5. `python -m draftpaper_cli.cli prepare-analysis-revision --project $ARGUMENTS`
6. `python -m draftpaper_cli.cli generate-revision-plan --project $ARGUMENTS`

Summarize each report's key findings (gate failures, submission risks,
statistical rescue advice, revision tasks) with artifact paths. Applying a
revision (`accept-revision`) is a protected human action — present the plan
and stop.
