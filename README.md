# Draftpaper-loop

**A local-first, evidence-first workflow that confirms a research blueprint and core results before composing, reviewing and releasing a traceable `main.pdf`.**

[中文说明](README.zh-CN.md) | [Install profiles](docs/install_profiles.md) | [CLI reference](docs/cli_reference.md) | [Final manuscript completion](docs/manuscript_completion.md)

Draftpaper-loop is not a one-shot paper generator. It coordinates literature, research planning, real data and method execution, core figures, Results, the remaining manuscript, citation audit, discipline review, independent review and final PDF release as a recoverable research loop. Codex retains freedom for scientific reasoning and natural prose. Deterministic contracts protect evidence versions, cohorts, runs, figure semantics, formulas, references, plugin provenance, stale state and release identity.

## Current Release

The current release is **v0.32.0**. The public CLI contains 210 commands under one `CommandSpec` control plane, 210 discipline-plugin contracts and five cross-discipline release fixtures. Fixtures prove workflow behavior, not scientific findings. A real paper still requires a live-runnable plugin or an audited project-local implementation, verified run outputs and human confirmation of the research blueprint, core evidence and final release hash.

## How a Paper Reaches `main.pdf`

```text
idea and literature
  -> bilingual research blueprint and human feasibility confirmation
  -> discipline detection and data/method capability matching
  -> real data preparation, method execution and run manifests
  -> main figure groups plus necessary supporting figures
  -> result-support checkpoint and maximum claim-strength decision
  -> Results and Chinese result summary
  -> Introduction, Data, Methods and Discussion
  -> discipline review and semantic repair
  -> final citation audit after the final citation-bearing prose
  -> two independent single-manuscript blind reviews
  -> author metadata completion and precise section revisions
  -> compilation, quality gates and release-hash confirmation
  -> latex/main.pdf
```

If verified results do not support the planned claim, the loop stops at one consolidated checkpoint. The user chooses either to narrow the claim while freezing the current figures and metrics, or to supplement data/methods and rerun the evidence chain. It does not create a similar-looking substitute figure and continue writing.

## Guarantees And Human Control

Draftpaper-loop guarantees traceability and failure visibility, not scientific correctness by assertion.

- **Evidence before prose:** the research blueprint, executable method, run output, figures and result support precede Results and the remaining manuscript.
- **Scientific writing freedom:** contracts constrain facts and boundaries; they do not reduce Codex prose to paragraph templates.
- **Runtime truth:** mock, fixture-only, contract-only and candidate plugins cannot support manuscript claims. Project-local code must be audited and bound to its run outputs.
- **Reference retention:** citation audit repairs wording, placement and support strength while preserving user-curated literature. It does not delete references to obtain a green report.
- **Precise stale propagation:** metadata-only changes rebuild publication artifacts; data, method, run, cohort, metric or core-figure changes reopen the necessary scientific stages.
- **Transactional author edits:** final metadata, references and exact section changes are previewed together, hash-bound, applied atomically and rollback-aware.
- **Human authority:** users confirm the blueprint, core evidence, claim downgrade, plugin promotion, final author packet and release hash.
- **Local boundary:** projects, private data locators and credentials remain local unless an explicitly approved connector is used.

## Install

Python 3.10 or newer is required.

| Profile | Editable checkout | Purpose |
|---|---|---|
| Minimal | `python -m pip install -e .` | Control plane, bibliography, PDF/image inspection and vendored paper-fetch fallback |
| Plotting | `python -m pip install -e ".[plotting]"` | Publication figures and NumPy/pandas scientific plugin runtime |
| Full text | `python -m pip install -e ".[fulltext]"` | Enhanced PDF/web text extraction and metadata normalization |
| MCP | `python -m pip install -e ".[mcp]"` | Local stdio MCP transport |
| Research workstation | `python -m pip install -e ".[plotting,fulltext,mcp]"` | Combined local research environment |

Verify the active interpreter rather than assuming extras are present:

```powershell
draftpaper doctor --json
draftpaper skill-doctor
draftpaper mcp-doctor
```

The Doctor report names missing modules and provides exact recovery commands. Missing optional extras do not invalidate the minimal control plane, but a scientific stage cannot claim the associated capability until it is installed.

## Quick Start

PowerShell:

```powershell
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
Set-Location Draftpaper_loop
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[plotting,fulltext]"
.\.venv\Scripts\draftpaper create-project --idea "Your research idea" --field "astronomy machine learning" --target-journal MNRAS
.\.venv\Scripts\draftpaper start --project .\projects\your-project
.\.venv\Scripts\draftpaper status --project .\projects\your-project
```

Bash:

```bash
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[plotting,fulltext]"
.venv/bin/draftpaper create-project --idea "Your research idea" --field "astronomy machine learning" --target-journal MNRAS
.venv/bin/draftpaper start --project ./projects/your-project
.venv/bin/draftpaper status --project ./projects/your-project
```

`status` is authoritative for the next action. `continue` resumes the loop after checking current artifacts and gates; it is not an instruction to overwrite finished sections.

## Researcher Commands

| Intent | Command | Behavior |
|---|---|---|
| Start the managed loop | `draftpaper start --project <project>` | Initializes or resumes through authoritative state |
| Inspect state | `draftpaper status --project <project>` | Shows next action, blockers, stale scope and human decisions |
| Continue safely | `draftpaper continue --project <project>` | Executes only the currently valid next route |
| Review current checkpoint | `draftpaper review --project <project>` | Builds a review packet without silently accepting it |
| Request a precise revision | `draftpaper revise --project <project> ...` | Produces a candidate using stable text/hash location |
| Diagnose environment/project | `draftpaper doctor --project <project> --json` | Read-only dependency, state and recovery report |
| Inspect token/cost ledger | `draftpaper token-report --project <project>` | Reports actual/estimated tokens and only explicitly recorded currency cost |
| Build a recovery plan | `draftpaper recover --project <project>` | Never accepts figures, downgrades claims, deletes references or promotes plugins |

All 210 command contracts, risks, stages, handlers and exit policies are generated in [the CLI reference](docs/cli_reference.md). Internal commands remain available for debugging and automation, but researchers should follow `status` and these workflow macros instead of manually reconstructing stage order.

## Final Author Workflow

After a complete scientific draft and required reviews exist, one YAML packet can add authors, affiliations, ORCID records, correspondence, CRediT roles, funding, acknowledgements, declarations, data/code links, supplementary material, user-confirmed references and multiple precise section revisions.

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper review-final-manuscript --project <project>
draftpaper confirm-final-manuscript --project <project> --release-hash <sha256>
```

LaTeX line numbers are display hints. Paragraph IDs, expected text and hashes identify the real target. Preview produces one metadata/section/BibTeX diff, impact report and candidate PDF without changing canonical sources. Apply rechecks every anchor and the evidence snapshot, then commits the packet as one transaction. Scientific evidence changes cannot be disguised as prose edits; they reopen the research chain. See the [completion guide](docs/manuscript_completion.md).

## Documentation

- [Workflow priority guide](docs/cli_workflow_priority_guide.md): full evidence-first stage behavior and recovery routes.
- [CLI reference](docs/cli_reference.md): generated command, stage, risk, handler and exit-policy table.
- [Install profiles](docs/install_profiles.md): minimal, plotting, fulltext and MCP boundaries.
- [Token and cost reporting](docs/token_cost_reporting.md): ledger totals, active writing budget and recorded-price boundary.
- [Command risk matrix](docs/command_risk_matrix.md): generated risk, side-effect and write-root inventory.
- [Final manuscript completion](docs/manuscript_completion.md): metadata, dual locators, preview, apply and rollback.
- [DPL schemas](docs/DPL_SCHEMA.md): artifact and contract schema families.
- [Discipline module authoring](docs/discipline_modules/codex_authoring_guide.md): local plugin templates and promotion boundary.
- [Third-party notices](third_party/THIRD_PARTY_NOTICES.md): provenance and license records for adapted or internalized ideas.
- [Commercial overview](docs/commercial_overview.md): license, deployment and current hosted-service boundary.
- [Release process](docs/release_process.md): tag identity, platform smoke, wheel and security verification.

## Release Summary

- **v0.31.1-v0.31.4:** shared IDs/utilities, plugin and Methods responsibility packages, unified figure façade and a single CommandSpec entry path.
- **v0.31.5:** registered hot-path resource schemas, 65% CI coverage floor and wider Pyright scope.
- **v0.31.6:** true minimal wheel, explicit plotting/fulltext/MCP extras, Doctor install profiles and four-profile CI smoke.
- **v0.31.7:** short bilingual start pages and generated CLI reference replace monolithic README command/history dumps.
- **v0.31.8:** read-only token/cost reporting, combined research install profile, generated command risk matrix and explicit commercial boundary.
- **v0.31.9:** macOS control-plane smoke and tag-to-wheel identity verification without enabling public package distribution.
- **v0.32.0:** integrated completion, security, stale, schema, installation and release audit with an explicit sandbox/container boundary assessment.

Historical long-form material remains available in `docs/archive/`; Git history is the authoritative release history.

## License, Provenance And Support

The repository is source-available for non-commercial use under `LicenseRef-Draftpaper-NonCommercial`; commercial use requires written authorization. See [LICENSE](LICENSE) and [NOTICE](NOTICE). `third_party/registry.json` and the notices directory record external projects and skills whose ideas, interfaces or fallback code influenced the implementation. Private datasets, credentials, paper PDFs and project-specific scripts must not enter public plugin contributions.

Project maintenance and contact information are available on the [support page](https://xiejhhhhhh.github.io/Draftpaper_loop/support/).
