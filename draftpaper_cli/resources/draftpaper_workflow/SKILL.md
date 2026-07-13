---
name: draftpaper-workflow
version: 0.25.0
description: Use when Codex operates Draftpaper-loop projects through the authoritative CLI workflow and evidence gates.
---

# Draftpaper-loop Workflow

Treat the installed `draftpaper_cli` package as the workflow authority. Do not
reimplement stage ordering, write project state directly, or infer stale stages
from memory.

Do not directly edit project.json. Do not directly edit stage_manifest files.

## Required control loop

Before changing a paper project:

```powershell
python -m draftpaper_cli.cli status --project <project>
python -m draftpaper_cli.cli verify-next-action --project <project>
```

Use the recommended command only when verification passes. For ordinary
progression, call:

```powershell
python -m draftpaper_cli.cli continue --project <project>
```

When `status` reports an explicit human checkpoint, show the evidence or
decision request to the user and stop. Never accept core evidence, promote a
plugin, downgrade a claim, or accept a manuscript revision on the user's
behalf.

## Scientific boundaries

- Preserve the evidence-first order: literature and research plan, data and
  methods, executable figures, human core-evidence confirmation, manuscript,
  final citation audit, then independent reviews.
- A project-local method may satisfy a research capability only after the
  capability audit records its inputs, outputs, hashes, and execution scope.
- A scientific failure is not a command failure. Follow the structured rescue
  route instead of fabricating a substitute figure or weakening a gate.
- Citation repair narrows or rewrites claims while retaining curated
  references. It must run after the final assembled manuscript.
- Use `doctor` and `recover` for diagnosis. Do not edit `project.json`, stage
  manifests, passports, evidence snapshots, or append-only ledgers by hand.

## Long-running work

Use the persistent job commands for literature fetching, capability rescue,
method execution, figure generation, regressions, and independent-review
orchestration when the operation can outlive the current terminal or MCP
session.

Report the command status, scientific decision, important artifact paths, and
the verified next action.

## Stage order

The CLI owns the exact next action. Its scientific order is `create-project`,
`search-literature`, `resolve-journal-template`, `generate-plan`, data and
`collect-method-plan`, figure planning and `verify-methods`,
`assess-result-validity`, core-evidence confirmation, `inventory-results`,
`write-results`, `write-introduction`, Data and `write-methods`,
`write-discussion`, `assemble-latex`, integrity, citation audit, independent
reviews, and `quality-check`.

## Rerun rules

When references change, regenerate the plan and affected evidence/writing.
When results change, reopen core evidence and regenerate Results and downstream
sections. Let `status` and `verify-next-action` compute the precise stale scope.
