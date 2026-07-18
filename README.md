<div align="center">

[![AI Research Loop](https://img.shields.io/badge/AI-Research%20Loop-5C4D7D?style=flat-square)](#what-it-does)
[![Loop Engineering](https://img.shields.io/badge/Loop-Engineering-1D7874?style=flat-square)](#loop-model)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#key-features)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#key-features)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#quick-start)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#contributors-license-commercial-use-and-contact)

# Draftpaper-loop

**Alibaba set out to make it easy to do business anywhere; Draftpaper-loop sets out to make no paper hard to write.**

**Local-first research paper loop engine for auditable, traceable manuscript drafts.**

[English](./README.md) | [中文](./README.zh-CN.md)

</div>

Draftpaper-loop is a local-first, evidence-first research workflow. It confirms the research blueprint and executable scientific evidence before writing, lets Codex compose natural scientific prose from that evidence, and publishes a traceable `main.pdf` only after citation, discipline, integrity and independent-review checks.

## Current Release

The current release is v0.32.0. Cross-discipline fixtures validate workflow contracts, not scientific results. A real paper still requires live-runnable discipline plugins or auditable project-local code, verified run outputs, human confirmation of the research blueprint and core evidence, and final author acceptance. Mock and fixture outputs never qualify as manuscript evidence.

This README remains the detailed project guide. Use the generated [CLI Reference](docs/cli_reference.md) for the complete 210-command inventory, [Install Profiles](docs/install_profiles.md) for optional runtimes, the [Command Risk Matrix](docs/command_risk_matrix.md) for write/network/confirmation boundaries, and [Token and Cost Reporting](docs/token_cost_reporting.md) for project-level usage accounting. Product and deployment limits are documented separately in the [Product Boundary](docs/commercial_overview.md).

## How a Paper Reaches `main.pdf`

```text
idea and literature
  -> bilingual research blueprint and human confirmation
  -> data/method capability matching and real execution
  -> main figure groups plus supporting/appendix evidence
  -> result-support and claim-strength confirmation
  -> Results
  -> Introduction, Data, Methods and Discussion
  -> discipline review and final citation audit
  -> two independent blind reviewers
  -> final author completion and precise revisions
  -> compile, bind and confirm one release hash
  -> latex/main.pdf
```

If the verified results do not support the planned claim, the loop stops. The user must either narrow the claim while freezing the accepted figures and metrics, or supplement data/methods and rerun the scientific evidence chain. Draftpaper-loop does not substitute a similar-looking figure and continue writing.

## Guarantees and Human Control

Deterministic contracts check project state, cohort/run identity, plugin provenance, figure semantics, formulas, citations, stale propagation, write boundaries and release hashes. Codex remains responsible for open-ended research reasoning and natural prose. Humans confirm the research blueprint, core evidence, result-support route, author completion packet and final release hash. Path confinement, write-set checks, executable allowlists and MCP capability checks are application-level safeguards rather than an operating-system or multi-tenant production sandbox.

## Completing and Revising the Final Manuscript

One `manuscript_completion.yaml` can provide authors, affiliations, ORCID, funding, acknowledgments, data/code links, user-confirmed references and multiple paragraph revisions. Line numbers are hints; stable `paragraph_id`, expected text and SHA-256 are the write guards. The system first produces one diff and candidate PDF, then applies the accepted packet atomically.

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper review-final-manuscript --project <project>
draftpaper confirm-final-manuscript --project <project> --release-hash <sha256>
```

See [Final Manuscript Completion](docs/manuscript_completion.md) for the complete locator, preview, rollback and release-ordering contract.

## What It Does

Draftpaper-loop organizes one paper as one local project directory and advances it through explicit, rerunnable stages. The main loop is evidence-first: project creation, literature search, journal template profiling, research planning, data acquisition/integration, method planning, figure planning, analysis-code generation, method verification, result validity, result support checkpoint, run-aware result evidence resolution, semantic figure-contract validation, core-evidence review and human confirmation, Results writing, Introduction/Data/Methods/Discussion writing, final citation audit, LaTeX assembly, PDF review, integrity gates, reviewer-style revision routing, and quality gates. When current results cannot support the planned claim, the loop stops before manuscript writing and asks for an explicit route: downgrade the claim while freezing the verified figures/metrics, or supplement data/methods and rerun the evidence chain.

The reference workflow uses free literature providers first, including Semantic Scholar, arXiv, Crossref, and optional SerpApi. It writes BibTeX, citation evidence, literature notes, HTML paper summaries, and context-aware evidence for Introduction, Data, and Methods. When data or method references lack readable abstract evidence, Draftpaper-loop can call the vendored `paper-fetch-skill` runtime through `paper_fetch_adapter.py` to fetch full-text Markdown/JSON evidence.

## Loop Model

Draftpaper-loop uses a deterministic outer loop around open-ended research and writing work:

```text
observe project state
  -> decide next safe stage
  -> run the stage command
  -> verify outputs and gates
  -> record artifacts, hashes, and decisions
  -> mark downstream stages stale when inputs change
  -> diagnose failures and route revision
  -> repeat until the draft is reviewable
```

The loop is intentionally hybrid. Fixed scientific contracts such as citation existence, result artifact binding, Results no-citation checks, and stale-stage propagation are handled deterministically. Open-ended work such as literature interpretation, research planning, method design, and revision decisions can be assisted by Codex or other agents, but those agents are expected to call the same local project loop instead of bypassing it.

The loop is designed around five engineering components:

- Goal: each paper stage has an explicit target, such as a traceable research plan, a verified method run, a result manifest, or a compilable LaTeX draft.
- Context: each iteration reloads stable project files, including `project_passport.yaml`, stage manifests, citation evidence, run manifests, result manifests, review reports, and artifact hashes, instead of relying on unbounded chat history.
- Tools: agents operate through a controlled CLI surface, so literature search, stale synchronization, method verification, integrity checks, and revision routing remain reproducible.
- Evaluation: automated gates decide whether the current state is acceptable, including data feasibility, method execution, result validity, citation traceability, Results no-citation checks, and final quality checks.
- Stop conditions: the loop stops when gates pass, pauses for human checkpoints on high-risk scientific decisions, or routes backward when repeated failures show that data, methods, or claims need revision.

## Key Features

- Single-paper local project model with staged manifests.
- Orchestrator commands for status, next action, checkpoint, resume, and pipeline execution.
- Hash-based stale detection and backtracking when upstream artifacts change.
- Context-aware literature retrieval for `idea`, `data`, and `methods`.
- Zotero collection import for user-curated reference sets.
- Traceable `citation_evidence.csv` for auditable manuscript claims.
- Journal profile stage for target-journal LaTeX constraints.
- Pluggable data acquisition planning for local files, API-style access, and remote/server-side data without hard-coding field-specific packages into the core Data stage.
- Data feasibility gate before method planning.
- Project-specific figure planning before analysis-code generation.
- Methods hard gate requiring successful local code execution.
- Result validity gate before Results writing.
- Paper Narrative Engine that organizes main and supporting figures into finding-level stories, builds section evidence packs, Introduction/Discussion argument matrices, Data/Methods lifecycles, and outline-first Codex free-writing jobs.
- Scientific Editor and absolute-quality release: repair only affected paragraphs, reject deterministic fallback as a release candidate, require the final citation audit after all section validations, and require two independent reviewers to audit one frozen anonymous generated manuscript without an original-manuscript comparison.
- Clean project versioning with read-only parent projects, allowlisted asset import, lineage receipts, independent passports, and rebuildable derived state instead of copying stale reports into a new `_vN` project.
- Capability packs with routing evaluations, explicit plugin ownership, project-local method implementation contracts, and rescue routes that let an Agent implement a genuinely new method before plugin sufficiency is reassessed.
- Task-scoped Figure and Paragraph Evidence Resolvers that bind current runs and claims while controlling repeated writing context and token cost.
- Native `doctor`, `recover`, `start`, `continue`, `review`, and `revise` commands backed by one declarative command registry; Gbrain is not a runtime dependency or command-schema source.
- Canonical bibliography registry, duplicate-work/version resolution, journal-style validation, and rendered reference proof separated from citation-support auditing.
- Recursive third-party provenance for vendored code, taxonomy inspiration, derived templates, upstream skill repositories, commits, licenses, and affected paths.
- Stable paragraph and LaTeX line anchors for previewing, accepting, and rolling back author revisions, including metadata, acknowledgements, data/code links, custom prose, and additional references.
- Core evidence gate before manuscript writing, checking data supplementation, data integration, method execution, figure production, figure metadata, and result validity before human figure confirmation.
- Evidence-first manuscript writing: Results are written from confirmed figures first, then Introduction, Data, Methods, and Discussion are generated without leaking numeric results into earlier sections.
- Brief-guided Data and Methods writing: the loop preserves hard evidence contracts while avoiding rigid context dumping, local paths, script names, and internal workflow language in manuscript prose.
- Results no-citation enforcement with explicit `Figure~\ref{...}` and `Table~\ref{...}` references in result prose.
- Chinese Results review summary at `results/results_summary_zh.md` for quick human inspection of figure-level interpretation.
- LaTeX assembly with optional local PDF compilation.
- Default acknowledgments noting Draftpaper-loop assistance and linking to the project repository.
- Independent integrity gate for BibTeX existence, citation evidence, and result artifact binding.
- Manuscript writing-quality gates for section length, paragraph structure, citation placement, Methods formulas, Results figure count, and non-bulleted natural prose.
- Review-revise-re-review loop with gate-failure routing and commitment ledger.
- Publication-readiness reviewer layer with journal-fit risk, submission-readiness scoring, statistical rescue planning, and claim-evidence matrix outputs.
- Discipline-specific reviewer-engineering engines with geography/remote-sensing support, reserved astronomy and machine-learning branches, and a default fallback.
- Metadata-only research-code mining that discovers, scores, and reports public repository candidates for future discipline plugin sedimentation without copying third-party source code.
- Codex skill wrapper that remains only a calling layer.

## Project Layout

```text
draftpaper_cli/                   # Core Python package and CLI stage commands
draftpaper_cli/discipline_modules # Registered data, method and review-rule plugins
draftpaper_cli/_vendor/           # Wheel-installable runtime fallbacks
codex_skills/draftpaper-workflow  # Optional Codex skill wrapper
docs/                             # Workflow, contracts, generated references and audits
tests/                            # Unit and release-contract tests
third_party/                      # Upstream snapshots, provenance pointers and notices
third_party/registry.json         # Recursive provenance for borrowed or internalized influence
```

Generated paper projects are stored under `projects/` locally and are intentionally ignored by git to avoid uploading research data, generated drafts, full-text paper caches, and result artifacts. Within a generated paper project, executable code is stage-owned: `data/scripts/` keeps data collection, API/remote-manifest, preprocessing, and cleaning code; `methods/scripts/` and `methods/src/` keep model, statistical, spatial-analysis, validation, and figure-generation code; `results/` keeps only produced figures, tables, and metadata. The legacy `code/` folder remains as a compatibility launcher/shared-runtime bridge.

## Quick Start

### Tutorial

Basic tutorial video: [Bilibili](https://www.bilibili.com/video/BV1LKjS6gEh4/?spm_id_from=333.1387.homepage.video_card.click&vd_source=463ffa8de6f1dbe750355ef3225fa45a)

### Use Through Codex

The intended workflow is to let Codex read this repository and call the Draftpaper-loop CLI surface for you. After cloning the repository locally, open or point Codex to the repository directory and ask in natural language, for example:

```text
Use Draftpaper-loop in <repo> to create a paper project for this idea, search literature, write the research plan, and tell me which loop stage is blocked.
```

Codex should then run the appropriate CLI commands, inspect the generated local project files, and report the next safe stage. The raw `draftpaper` commands below are the underlying loop interface for debugging, automation, and non-Codex use; they are not meant to replace normal conversation with Codex.

### Evidence-Semantic API

The public Python API exposes the same safeguards used by the CLI. `resolve_result_evidence` resolves metrics only from verified, run-bound outputs; `build_scientific_evidence_registry` rejects contradictory facts within the same cohort; `validate_figure_semantics` rejects identifier-versus-identifier and mixed-unit scientific figures; `create_evidence_snapshot` freezes human-confirmed core evidence; and `submit_section_draft` validates a freely composed section before installation. Existing rendered figures can be mapped only through explicit, auditable `submit-figure-semantic-annotations` input with variable roles and evidence-source identifiers.

```python
from draftpaper_cli import (
    build_scientific_evidence_registry,
    create_evidence_snapshot,
    resolve_result_evidence,
    submit_section_draft,
    validate_figure_semantics,
)

evidence = resolve_result_evidence(project_path)
registry = build_scientific_evidence_registry(project_path)
snapshot = create_evidence_snapshot(project_path)
```

Use `reopen-core-evidence --reason "..."` before a scientific data, method, metric, or figure change. Citation-only and presentation-only changes receive narrower stale propagation; a final citation audit must run after the final five manuscript sections and must match the promoted evidence snapshot.

For staged work, Codex should first call the orchestrator layer:

```powershell
python -m draftpaper_cli.cli status --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project <repo>\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project <repo>\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\your_project
python -m draftpaper_cli.cli audit-citations --project <repo>\projects\your_project --final
python -m draftpaper_cli.cli generate-citation-repair-plan --project <repo>\projects\your_project
python -m draftpaper_cli.cli apply-citation-repair --project <repo>\projects\your_project
python -m draftpaper_cli.cli re-audit-citations --project <repo>\projects\your_project
python -m draftpaper_cli.cli diagnose-gate-failures --project <repo>\projects\your_project
python -m draftpaper_cli.cli assess-publication-readiness --project <repo>\projects\your_project
python -m draftpaper_cli.cli discover-review-workflow-gaps --project <repo>\projects\your_project
python -m draftpaper_cli.cli propose-review-engineering-plan --project <repo>\projects\your_project
python -m draftpaper_cli.cli recommend-statistical-revision --project <repo>\projects\your_project
python -m draftpaper_cli.cli generate-revision-plan --project <repo>\projects\your_project
```

### One-Command Local Setup

Run this from the directory where you want to place the repository. The command clones the repository, creates a local virtual environment, installs the Draftpaper-loop plotting profile, and prints the CLI help. A paper-fetch fallback is packaged under `draftpaper_cli/_vendor/`; `third_party/` retains the upstream snapshot and provenance record rather than acting as the required runtime install path.

```powershell
powershell -ExecutionPolicy Bypass -Command "git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git; cd Draftpaper_loop; py -3 -m venv .venv; .\.venv\Scripts\python -m pip install -U pip; .\.venv\Scripts\python -m pip install -e .[plotting]; .\.venv\Scripts\draftpaper --help"
```

Optional enhanced full-text extraction profile:

```powershell
.\.venv\Scripts\python -m pip install -e ".[fulltext]"
```

After setup, the installed `draftpaper` command can be used from the repository root:

```powershell
.\.venv\Scripts\draftpaper create-project --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper status --project .\projects\your_project
.\.venv\Scripts\draftpaper run-pipeline --project .\projects\your_project
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --query "topic keywords"
.\.venv\Scripts\draftpaper validate-project --project .\projects\your_project
```

For a quick local smoke test without live literature search, create and validate a project:

```powershell
.\.venv\Scripts\draftpaper create-project --idea "X-ray flaring source classification" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper validate-project --project .\projects\x-ray-flaring-source-classification
```

### Editable Install

```powershell
python -m pip install -e .[plotting]
python -m draftpaper_cli.cli create-project --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project <repo>\projects\your_project
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli prepare-data-acquisition --project <repo>\projects\your_project --source-root C:\external\research_folder
python -m draftpaper_cli.cli record-observation --project <repo>\projects\your_project --stage data --kind agent_analysis --text "Visible Codex data summary..."
python -m draftpaper_cli.cli list-zotero-collections
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --zotero-collection "Your Zotero Collection" --zotero-context all
python -m draftpaper_cli.cli prepare-method-blueprint --project <repo>\projects\your_project
python -m draftpaper_cli.cli plan-figures --project <repo>\projects\your_project
python -m draftpaper_cli.cli generate-analysis-code --project <repo>\projects\your_project
python -m draftpaper_cli.cli classify-code-ownership --project <repo>\projects\your_project
python -m draftpaper_cli.cli route-stage-code --project <repo>\projects\your_project
python -m draftpaper_cli.cli build-code-provenance --project <repo>\projects\your_project
python -m draftpaper_cli.cli extract-method-formulas --project <repo>\projects\your_project
python -m draftpaper_cli.cli trace-figures-to-code --project <repo>\projects\your_project
python -m draftpaper_cli.cli diagnose-figure-execution --project <repo>\projects\your_project
python -m draftpaper_cli.cli repair-figure-data --project <repo>\projects\your_project
python -m draftpaper_cli.cli repair-figure-method --project <repo>\projects\your_project
python -m draftpaper_cli.cli record-observation --project <repo>\projects\your_project --stage methods --kind method_rationale --text "Visible Codex method rationale..."
python -m draftpaper_cli.cli assess-result-validity --project <repo>\projects\your_project
python -m draftpaper_cli.cli assess-core-evidence --project <repo>\projects\your_project
python -m draftpaper_cli.cli checkpoint --project <repo>\projects\your_project --stage core_evidence --note "User approved core figures and evidence"
python -m draftpaper_cli.cli inventory-results --project <repo>\projects\your_project
python -m draftpaper_cli.cli write-results --project <repo>\projects\your_project
python -m draftpaper_cli.cli write-introduction --project <repo>\projects\your_project
python -m draftpaper_cli.cli build-data-context --project <repo>\projects\your_project
python -m draftpaper_cli.cli write-data --project <repo>\projects\your_project
python -m draftpaper_cli.cli build-method-context --project <repo>\projects\your_project
python -m draftpaper_cli.cli write-methods --project <repo>\projects\your_project
python -m draftpaper_cli.cli prepare-discussion-comparison --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-citation-repair-loop --project <repo>\projects\your_project
python -m draftpaper_cli.cli assess-publication-readiness --project <repo>\projects\your_project
python -m draftpaper_cli.cli recommend-statistical-revision --project <repo>\projects\your_project
python -m draftpaper_cli.cli validate-project --project <repo>\projects\your_project
```

Run tests:

```powershell
python -m pytest
```

`python -m pip install -e .` installs the minimal control plane without NumPy, pandas or Matplotlib. Real paper projects should use `.[plotting]`; add `.[fulltext]` and `.[mcp]` only when those capabilities are needed. `draftpaper doctor --json` reports each profile, missing modules and the exact recovery command. See [Install Profiles](docs/install_profiles.md) for the minimal/plotting/fulltext/MCP matrix and `.[plotting-full]` advanced figure backends.

### Zotero Collection Import Through Codex

Draftpaper-loop can import references from a specific Zotero collection during the literature stage. Configure credentials as environment variables in the same shell or Codex terminal session:

```powershell
$env:ZOTERO_LIBRARY_ID="your_zotero_library_id"
$env:ZOTERO_LIBRARY_TYPE="user"   # or "group"
$env:ZOTERO_API_KEY="your_zotero_api_key"
```

Then ask Codex to call the loop, or run the CLI directly:

```powershell
python -m draftpaper_cli.cli list-zotero-collections
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --zotero-collection "My Paper References" --zotero-context all --zotero-min-items 20
```

`list-zotero-collections` returns collection names and keys without printing credentials. `search-literature --zotero-collection` reads only the selected collection and writes `references/zotero_collection_manifest.json`. Zotero-imported references are treated as user-curated evidence: they are preserved even when they lack an abstract/PDF, fall outside the recency preference, or exceed the external-search 30-paper ranking cap. The loop still writes them into the same outputs as searched papers, including `references/library.bib`, `references/literature_items.json`, `references/citation_evidence.csv`, `references/literature_review_notes.html`, per-paper HTML summaries, and `references/literature_summaries/index.html`. They are marked with `source=zotero_collection`, `reference_origin=existing_zotero`, and `selection_policy=zotero_collection_preserved` so later review can distinguish them from ranked external search results. If the collection has fewer than `--zotero-min-items` usable references, the loop supplements with free external search unless `--no-zotero-supplement` is set. In Codex chat, a good request is: "Call Draftpaper-loop, list my Zotero collections, then search literature for this project using the collection named `My Paper References`."

## Implementation Status

The current implementation already contains the core loop primitives: an orchestrator layer (`status`, `checkpoint`, `resume`, `run-pipeline`), hash-based stale synchronization (`detect-artifact-drift`, `sync-artifact-stale`), project state commands, literature search, journal profile resolution, research plan generation, claim contracts, observation recording, pluggable data acquisition planning, data inventory and feasibility checks, method-plan collection, discipline-aware method blueprint generation, project-specific figure planning, figure-plan-driven analysis-code generation, method execution verification, result validity checks, result support checkpointing, downgrade/rescue route planning, core evidence assessment, result inventory, Results writing with Chinese review summary, Introduction, Data writing context generation, Data writing, Methods writing context generation, Methods writing, Discussion, LaTeX assembly, PDF compilation, independent integrity checks, review/revision routing, publication-readiness assessment, discipline-specific review-engineering discovery, statistical rescue planning, and final quality checks.

The v0.32.0 control plane registers 210 public commands through one `CommandSpec` inventory and gives scientific hard gates nonzero failure status. Central fetch, execution, write-set and MCP policies protect project boundaries; one change taxonomy and artifact DAG control precise stale propagation. After the scientific and writing chain passes, the final-author workflow collects publication metadata, user-confirmed references and bounded paragraph edits in one packet, previews a unified diff and candidate PDF, applies the accepted packet atomically, and records rollback and exact-text locks. Final confirmation binds the completion manifest, canonical sections, bibliography, promoted evidence, citation audit, two independent reviews and compiled PDF to one release hash.

Every project carries a DraftPaper Passport at `project_passport.yaml` plus append-only `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`. These files record project artifacts, hashes, explicit user checkpoints, and integrity events so the project can be moved across machines and later audited without relying on Codex conversation memory.

When a tracked artifact hash changes, `status` reports `pipeline_state=drift_detected` and recommends `sync-artifact-stale`. That command maps changed artifact paths back to their source stages, marks downstream dependent stages stale, records the drift in `integrity_ledger.jsonl`, and refreshes the passport hash baseline.

`prepare-method-blueprint` connects the inferred discipline module, data inventory, data-acquisition profile, method requirements, and reviewer/rescue tasks into `methods/method_blueprint.json`, `methods/method_data_contract.json`, `methods/method_code_plan.json`, and `methods/method_formula_plan.json`. `plan-figures` observes the current idea, research plan, target journal, data inventory, method requirements, literature metadata, method blueprint, and any supplied local result artifacts, then writes `results/figure_plan.json`, `results/figure_plan.html`, `results/figure_contracts.json`, and `results/storyboard_alignment_report.json`. Figure storyboard entries from the research plan are treated as strict main-result contracts: validation plots, workflow diagrams, or supporting diagnostics may be useful, but they cannot silently replace a planned main figure. Discipline modules can declare minimum/target main-figure counts and required figure groups; the default first-draft policy plans at least five generated main figures when data are available. With `--use-review-tasks`, `plan-figures` turns executable or partial reviewer/rescue tasks into revised figures while skipping blocked tasks. `generate-analysis-code` reads the figure plan and contracts, writes canonical project-local method code under `methods/scripts/` and `methods/src/`, plus `methods/method_code_manifest.json`; `code/` is retained only as a compatibility launcher/copy. The generated pipeline records `results/figure_execution_diagnosis.json` and `.html`; when a contracted figure cannot be produced, the loop records whether the blocker is missing data or missing method code and routes to `repair-figure-data` or `repair-figure-method` before entering human core-evidence confirmation. With `--use-review-tasks`, it also emits `results/tables/review_task_coverage.csv` and `results/tables/review_task_metrics.csv` for cleaning/QC, feature reconstruction, baseline/ablation, and validation coverage. If raw data are remote, private, or too large for local processing, users can provide processed tables or final figures/tables locally and continue through `inventory-results` and `write-results` with claims limited to those artifacts. `verify-methods` can now read `methods/method_code_manifest.json` directly, prefer the generated `verify_command_argv`, record `methods/run_manifest.yaml`, and block Methods writing until every declared output, main figure contract, figure metadata item, and required review task coverage exists. The CLI exits non-zero when this hard gate records `status=failed`, so shell scripts, Codex automation, and CI cannot mistake a failed method run for success.

Figure repair is intentionally repair-first rather than downgrade-first. `diagnose-figure-execution` summarizes planned main-figure contracts and execution state; `repair-figure-data` creates a data-repair plan using existing data acquisition connectors, public databases/APIs, remote-server workflows, or user-provided artifacts; `repair-figure-method` creates a method-repair plan that points Codex toward existing discipline plugins, project code, public research-code repositories, literature implementation repositories, or newly generated project-specific method code. Only after those repair attempts still cannot satisfy the figure contract should the project enter `assess-core-evidence` as a human confirmation checkpoint. Single-figure downgrades are avoided because claim reframing belongs in the research plan, not as a quiet substitute for a failed main result.

`write-results` now writes result prose that explicitly points readers to the supporting figures and tables through LaTeX labels such as `Figure~\ref{...}` and `Table~\ref{...}`. Internal loop vocabulary, local-path safeguards, gate names, and project-management wording are kept out of the manuscript body and reserved for logs, reports, or acknowledgments. `assemble-latex` inserts a default acknowledgment before the bibliography noting that Draftpaper-loop assisted staged literature organization, analysis traceability, figure inventory, and manuscript drafting.

`run-integrity-gate` writes `integrity/integrity_report.json` and `integrity/integrity_report.md`, then appends an `integrity_gate` event to `integrity_ledger.jsonl`. It checks that manuscript citations exist in BibTeX, that Introduction/Data/Methods/Discussion citations are traceable to `references/citation_evidence.csv`, that Results contains no citation commands, and that every result claim in `results/result_manifest.yaml` is bound to an existing local figure or table.

`audit-citations`, `generate-citation-repair-plan`, `apply-citation-repair`, `re-audit-citations`, and `run-citation-repair-loop` add an independent citation audit and repair loop after integrity checks and before final quality checks. The loop compares each manuscript citation usage against BibTeX metadata and `references/citation_evidence.csv` at claim level, writes intermediate HTML reports under `citation_audit/iterations/`, and writes `citation_audit/final_citation_audit_report.html` only after the strict report has no unsupported or unverifiable citation usages. It also enforces reference coverage: every retained reference listed in `references/literature_summaries/` is assigned through `references/reference_usage_plan.json` and must be cited at least once outside Results. Citation audit is not a reference-quality filter. Reference quality is controlled during literature search and human review; the audit preserves retained references and repairs manuscript wording so each citation is truthful, specific, and semantically close to the cited evidence. The final citation audit report merges the claim-level audit with `citation_audit/reference_coverage_report.html`, including citation usage count, unique cited reference count, summarized reference count, summarized-but-uncited references, and topic-suspect references. If citation audit fails, `status` and `run-pipeline` recommend the citation repair loop rather than continuing blindly to `quality-check`. The final quality gate also requires `citation_audit/final_citation_audit_report.json` with `status=passed`, so direct `quality-check` calls cannot skip source-support or reference-coverage verification.

`diagnose-gate-failures`, `review-draft`, `assess-publication-readiness`, `discover-review-workflow-gaps`, `propose-review-engineering-plan`, `recommend-statistical-revision`, `prepare-analysis-revision`, `generate-revision-plan`, `apply-revision`, and `re-review` implement the review-revise-re-review loop. Gate failures are converted into unified revision issues with target stages, files to inspect, required user decisions, and recommended CLI reruns. The publication-readiness layer estimates target-journal submission risk from saved data, methods, result, figure, integrity, quality, and journal-profile artifacts, then writes a Codex/LLM-readable archive review packet at `review/codex_archive_review_context.json` and `.html`. The reviewer-engineering layer infers a discipline and runs a matching engine; geography covers remote-sensing, agricultural-geography, and spatial-analysis manuscripts, astronomy covers catalog/light-curve/source-classification review risks, machine learning covers leakage, validation, baseline, ablation, calibration, and imbalance risks, and unmatched projects use a default fallback. Its output includes user-confirmation requests plus a `codex_enhancement_context` extension point so Codex can append literature- and manuscript-specific reviewer suggestions on top of deterministic rules. The statistical rescue layer recommends robust statistics, missingness audits, method rebuilding, explicit success thresholds, domain-aware feature rebuilding, spatial validation, model validation checks, or claim reframing when weak data or weak results might still support a defensible exploratory paper. `prepare-analysis-revision` converts review/rescue advice into executable analysis tasks, checks required data roles, and blocks impossible reruns before new figure planning or code generation. When integrity or final quality reports failed, `status` and `run-pipeline` now walk through the review sequence: gate diagnosis, reviewer pass, publication readiness, review-engineering discovery and planning, statistical rescue, analysis-revision preparation, and revision planning.

`record-observation` preserves visible Codex/user analysis summaries inside `observations/observations.jsonl`. These records are used by `build-data-context` and `build-method-context` to create manuscript-facing writing packets. The writers use those packets instead of raw file inventories or execution manifests, so Data and Methods sections describe sources, variables, processing, analytical design, validation, and claim boundaries without exposing local filenames, paths, commands, or manifest dumps.

Stage-owned code routing is now explicit. `classify-code-ownership` scans project-local Python code, `route-stage-code` copies or moves legacy `code/` scripts into `data/scripts/`, `methods/scripts/`, `methods/src/`, or `methods/plotting/`, and `build-code-provenance` records the project-level code trail. `extract-method-formulas` writes `methods/method_formula_manifest.json` and `methods/method_formulas.tex` from code annotations, static formula patterns, and figure metadata; `trace-figures-to-code` writes `results/figure_code_trace.json` and `.html`. `build-data-context` reads `data/data_code_manifest.json`, while `build-method-context` reads `methods/method_code_manifest.json`, `methods/method_formula_manifest.json`, and `results/figure_code_trace.json`, so Data and Methods writing can explain data construction, variables, formulas, validation, and figure provenance from stage-owned code rather than from a generic `code/` dump.

Discussion writing now has a comparison-preparation step. `prepare-discussion-comparison` writes `discussion/comparison_literature_matrix.csv`, `discussion/comparison_evidence_notes.html`, and `discussion/innovation_limitations_plan.json` by anchoring confirmed Results claims or metrics to retained citation evidence and literature summaries. `write-discussion` can then compare the accepted local findings with prior studies, state innovation more narrowly, and define limitations without inventing unsupported literature contrasts.

`classify-data-access`, `prepare-data-acquisition`, and `inventory-data-sources` add a discipline-neutral data acquisition layer before ordinary data inventory. The layer shares the same discipline profile used by the reviewer-engineering system, then detects connector types such as `local_files`, `api_access`, and `remote_server`. It writes a plan-first artifact set under `data/` and does not fetch external data or install field-specific packages by default. Domain-specific connectors such as astronomy archives, Google Earth Engine, or bioinformatics repositories can later plug into this interface while the core Data stage remains reusable across disciplines. After reviewer/rescue analysis creates blocked missing-data tasks, `prepare-data-acquisition` writes `data/data_acquisition_tasks.json` and `.html` so Codex can tell the user which data roles are missing, which connector type is suitable, and which confirmation is needed before fetching, linking, or server-side processing.

Discipline modules also declare data acquisition connectors for research planning and missing-data repair. Astronomy covers mission/archive APIs and remote server SSH; geography covers Google Earth Engine plus local raster/vector parsing; ecology covers public web/API download plus GeoTIFF/NetCDF parsing; machine learning covers local files plus Kaggle/Hugging Face/cloud storage; bioinformatics covers GEO/SRA/ENA API access plus remote omics servers. `prepare-data-acquisition` records connector packages, API/download routes, expected data formats, and feasibility states such as `locally_feasible`, `requires_package_install`, or `requires_credentials`.

## Research-Code Mining

Draftpaper-loop can now prepare metadata-only candidate reports from public research-code repositories before any plugin code is written. This is a curation aid for building discipline modules, not a code-copying tool. The first minimal chain is:

```powershell
python -m draftpaper_cli.cli discover-research-repos --output-root .\mining --discipline geography --query "remote sensing raster workflow" --from-json .\repo_candidates.json
python -m draftpaper_cli.cli score-research-repos --input .\mining\research_code_mining\geography_repo_candidates.json --output-root .\mining
python -m draftpaper_cli.cli extract-plugin-candidates --input .\mining\research_code_mining\geography_scored_repos.json --output-root .\mining --top-n 5
python -m draftpaper_cli.cli inspect-research-repo --candidate .\mining\research_code_mining\plugin_candidates\geography\<candidate> --local-repo .\local_checkout --output-root .\mining --mode tree_docs
python -m draftpaper_cli.cli map-repository-workflow --inspection .\mining\research_code_mining\inspections\<candidate>\repository_structure.json --output-root .\mining
python -m draftpaper_cli.cli bootstrap-discipline-foundation --workflow-map .\mining\research_code_mining\workflow_maps\<candidate>\workflow_map.json --output-root .\mining
```

The generated reports record repository metadata, license policy, reproducibility signals, workflow signals, file-tree roles, candidate capabilities, and discipline-foundation suggestions. They intentionally do not clone repositories, copy source folders, or package third-party code; later generalization still needs manual/Codex review, privacy checks, license checks, fixture tests, and overlap review before a plugin can be proposed for `main`.

## Third-party Skills Integration

This repository keeps [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) under `third_party/paper-fetch-skill` for source provenance and packages the runnable fallback under `draftpaper_cli/_vendor/paper_fetch_skill`. The adapter prefers a `paper-fetch` command on `PATH`; if unavailable, it can use the packaged fallback. Install `.[fulltext]` only when the enhanced article/PDF extraction stack is required.

The third-party runtime is MIT licensed. Keep its license notice when redistributing.

Third-party research skills, skills distilled from local research projects, and external skill catalogs such as AcademicForge can be converted into Draftpaper-loop candidate plugin reports through a metadata-only pipeline. The pipeline reads file names, summaries, dependencies, input/output shapes, artifact types, keywords, and structured descriptions; it does not copy third-party `SKILL.md` bodies, source code, paper PDFs, private data, credentials, or local paths.

Recommended pipeline:

```powershell
python -m draftpaper_cli.cli snapshot-skill-source --source-root .\external_skills --output-root .\plugin_mining
python -m draftpaper_cli.cli inspect-skill-source --snapshot .\plugin_mining\SNAPSHOT.json --output-root .\plugin_mining
python -m draftpaper_cli.cli index-skill-source --inspection .\plugin_mining\SKILL_SOURCE_INSPECTION.json --output-root .\plugin_mining
python -m draftpaper_cli.cli classify-skill-source --index .\plugin_mining\SKILL_INDEX.json --output-root .\plugin_mining
python -m draftpaper_cli.cli map-skill-capabilities --index .\plugin_mining\SKILL_INDEX.json --output-root .\plugin_mining
python -m draftpaper_cli.cli extract-review-rule-signals --index .\plugin_mining\SKILL_INDEX.json --output-root .\plugin_mining
python -m draftpaper_cli.cli compile-skill-source --index .\plugin_mining\SKILL_INDEX.json --output-root .\plugin_mining
```

For an AcademicForge-style registry, start from registry metadata rather than copying upstream skill files:

```powershell
python -m draftpaper_cli.cli snapshot-skill-source --source academicforge --repo HughYau/AcademicForge --ref site-first --output-root .\plugin_mining\academicforge
python -m draftpaper_cli.cli inspect-skill-source --snapshot .\plugin_mining\academicforge\SNAPSHOT.json --output-root .\plugin_mining\academicforge
python -m draftpaper_cli.cli index-skill-source --snapshot .\plugin_mining\academicforge\SNAPSHOT.json --output-root .\plugin_mining\academicforge
python -m draftpaper_cli.cli classify-skill-source --index .\plugin_mining\academicforge\SKILL_INDEX.json --output-root .\plugin_mining\academicforge
python -m draftpaper_cli.cli extract-review-rule-signals --index .\plugin_mining\academicforge\SKILL_INDEX.json --output-root .\plugin_mining\academicforge
```

This writes derived metadata profiles under the output folder and records `ACADEMICFORGE_REGISTRY_ADAPTER.json`. The profiles are generated from registry fields such as id, summary, tags, repository, license, and install metadata; upstream `SKILL.md` bodies and source code are not copied.

The adapter resolves the requested GitHub ref to an immutable commit when GitHub metadata access is available, then reconciles collection-level `skill_count` declarations with AcademicForge's public classification metadata. Every declared subskill enters the snapshot ledger: records with classification metadata become detailed profiles, while unresolved collection-only declarations remain explicit `requires_source_inspection` placeholders. The adapter reports `declared_skill_count`, `expanded_skill_count`, `placeholder_skill_count`, and `silent_loss_count` so a top-level collection count cannot be mistaken for complete skill coverage.

Formal discipline modules accept only three promotable subplugin types: `data_connector`, `method_template`, and `review_rule`. `workflow_recipe`, `paper_contract`, and `shared_capability` are preserved as support-layer candidates rather than written directly into `discipline_modules/<discipline>/`. However, their verifiable statistical, model-baseline, ablation, split/leakage, figure-claim, citation-support, data/code-availability, and reproducibility conditions are scanned with `review_rule_signal_scan` and can backflow into discipline-specific `review_rule_candidate`s.

Use `extract-review-rule-signals` when you want to audit this backflow before generating candidate packages. It scans every skill/source record, including workflow, paper-contract, and shared-capability material, and writes `REVIEW_RULE_SIGNAL_REPORT.json` / `.md` without promoting anything into the formal discipline modules.

A `review_rule` is not plain reviewer-comment text. It is an evidence-bound scientific quality gate that must declare its applicable discipline, method family, data roles, evidence roles, threshold source, failure route, and human-confirmation state. Thresholds such as F1, AUC, R², RMSE, MAE, p values, FDR, sample size, spatial resolution, and temporal coverage default to `contextual`, `comparative`, or `human_confirmed` rules unless they are backed by journal guidance, discipline convention, a public benchmark, or explicit user confirmation; they are not promoted as global fixed thresholds automatically.

Before a candidate becomes a formal contribution, run:

```powershell
python -m draftpaper_cli.cli generalize-plugin-candidate --candidate <candidate_dir>
python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate_dir>
python -m draftpaper_cli.cli package-plugin-contribution --candidate <candidate_dir>
python -m draftpaper_cli.cli preflight-plugin-contribution --package <candidate_dir>\contribution_package
python -m draftpaper_cli.cli review-plugin-contribution --package <candidate_dir>\contribution_package
python -m draftpaper_cli.cli promote-plugin-candidate --candidate <candidate_dir> --require-human-confirmation
```

Support-layer candidates cannot be packaged as formal discipline plugins directly. Submit their generalized formal candidates instead. A `review_rule` remains non-promotable while its maturity is `candidate` or `validated`; it must have an executable discipline fixture, reach at least `runnable`, pass validation, and receive explicit human confirmation before promotion.

PRs that include packaged plugin contributions are checked by `.github/workflows/plugin-contribution-preflight.yml`. The workflow scans for `contribution_package/candidate_manifest.json`, runs `preflight-plugin-contribution`, and then runs `review-plugin-contribution` on each package so maintainers can review metadata, generalized templates, fixtures, validation reports, provenance, support-layer backflow families, threshold policy, human-confirmation requirements, files to review, and a read-only merge recommendation without ingesting third-party source text.

## Contributors, License, Commercial Use, And Contact

Draftpaper-loop welcomes reusable discipline-module contributions, especially data connectors, method templates, reviewer rules, fixtures, and project-tested workflow lessons that can be generalized without private paths, credentials, raw data, or project-specific claims.

Current contributors:

- Jinray Xie: overall Draftpaper-loop framework, including literature workflows, data and methods auditing, result-output auditing, rollback mechanisms, and discipline-module contributions for deep learning, astronomy, and geography.
- Chen Wei: astronomy discipline-module supplements and related validation generation.

Draftpaper-loop is source-available for non-commercial research, evaluation, education, and personal paper-writing workflows. Commercial use, paid services, SaaS deployment, enterprise deployment, resale, or integration into commercial products requires separate written authorization from the developer.

Sponsorship or donation supports project maintenance but does not grant commercial use rights. Commercial use still requires separate prior written authorization.

Draftpaper-loop uses the DPL schema family to represent local-first paper-loop state, including project passports, stage manifests, citation evidence, run manifests, result manifests, artifact hashes, claim traces, and loop events.

See [`LICENSE`](./LICENSE), [`NOTICE`](./NOTICE), [`COMMERCIAL_LICENSE.md`](./COMMERCIAL_LICENSE.md), [`TRADEMARK.md`](./TRADEMARK.md), [`COMPLIANCE.md`](./COMPLIANCE.md), [`docs/DPL_SCHEMA.md`](./docs/DPL_SCHEMA.md), and [`docs/FORENSIC_FINGERPRINTING.md`](./docs/FORENSIC_FINGERPRINTING.md) for the current non-commercial source-available terms, attribution notice, commercial authorization scope, project-name/trademark policy, public schema identity, and compliance boundary.

For commercial authorization, contact [xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn).

Personal homepage: [https://xiejhhhhhh.github.io/Jinhui_profile/](https://xiejhhhhhh.github.io/Jinhui_profile/)

Third-party components keep their own licenses.

## Support

Building this takes time; a few tokens for maintenance are appreciated!!!

<p align="center">
  <a href="https://xiejhhhhhh.github.io/Draftpaper_loop/support/"><strong>Open the interactive support page / 打开交互式支持页</strong></a>
</p>

<table align="center">
  <tr>
    <td align="center">
      <img src="./docs/assets/donate_wechat_clean.png" alt="WeChat Pay QR code" width="190"><br>
      <strong>WeChat Pay</strong><br>
      微信支付
    </td>
    <td align="center">
      <img src="./docs/assets/donate_alipay_clean.png" alt="Alipay QR code" width="190"><br>
      <strong>Alipay</strong><br>
      支付宝
    </td>
    <td align="center">
      <img src="./docs/assets/donate_paypal_clean.png" alt="PayPal QR code" width="190"><br>
      <strong>PayPal</strong><br>
      International support
    </td>
  </tr>
</table>

Donation supports maintenance only and does not grant commercial use rights.

## Recent Updates
### v0.31.1-v0.32.0 (2026-07-18) -- Architecture, Release Documentation, Cross-platform Identity and Completion Audit

- `v0.32.0` reconciles the complete `H-01-H-07`, `M-01-M-12` and `R01-R11` release requirements. It validates one 210-command control plane in source, editable and isolated-wheel installations; runs General/AAS/MNRAS author-completion regression and five-domain adversarial release regression; restores Python 3.10 TOML compatibility; hardens optional bibliography-tool lookup; and publishes explicit completion and sandbox-boundary audits. These regressions validate workflow contracts rather than scientific conclusions or production-hosting isolation.
- `v0.31.9` verifies release identity across package metadata, release manifest, README, Git tag and the selected wheel. CI covers Windows and Linux on Python 3.10-3.12, adds a macOS control-plane smoke test, rejects stale distributions and validates minimal, plotting, full-text and MCP install profiles independently.
- `v0.31.8` adds the read-only `token-report`, separates recorded token/cost receipts from estimates, generates the command risk matrix, and documents local-product, license and hosted-service boundaries. Monetary prices are never inferred when no provider receipt or explicit price table exists.
- `v0.31.7` generates the exhaustive CLI reference from the authoritative `CommandSpec` registry, so command names, handlers, risk levels and checkpoint metadata no longer need to be duplicated manually. The bilingual README keeps its established detailed-guide structure and links to the generated command reference instead of replacing the original project documentation.

- `v0.31.6` makes the default wheel a minimal workflow, bibliography and PDF/image-inspection runtime without silently installing NumPy, pandas or Matplotlib. Plotting, enhanced full-text extraction and MCP use explicit extras; scientific plugin NumPy imports are lazy, Doctor reports profile availability and recovery commands, and CI installs minimal/plotting/fulltext/MCP environments independently. A wheel metadata verifier prevents optional stacks from drifting back into core dependencies, while the packaged paper-fetch fallback remains available in minimal installs.

- `v0.31.5` registers schema families for release fixtures, capability packs, command contracts, release manifests, method run/formula manifests and figure assessments. Release validation checks packaged resource schemas instead of trusting structurally plausible JSON. CI raises first-party coverage from 45% to 65%, and Pyright now includes the command control plane, completion/stale paths, figure façade and split Methods modules.

- `v0.31.4` routes all 209 CLI commands available at that stage through `CommandSpec`; `legacy_dispatch_count` is zero and `cli.py` no longer contains a command-specific fallback chain. Commands awaiting direct typed handlers use an explicit namespace compatibility adapter whose count remains visible rather than being reported as completed migration. Pipeline-stage commands are generated from registry metadata, and `assess-figure-contracts` now uses the unified figure façade.

- `v0.31.3` separates method execution verification, formula extraction and manuscript writing into responsibility modules behind the stable `draftpaper_cli.methods` API. A figure-contract façade normalizes gate, semantic, confirmed-blueprint and caption findings into one deterministic `{source, code, severity, message}` issue list; existing run-manifest strings remain available for compatibility while new consumers use `normalized_issues`.

- `v0.31.2` replaces the 3,700-line plugin-candidate monolith with separate skill-source loading, capability extraction, guarded promotion and contribution-review modules. The established `draftpaper_cli.plugin_candidates` imports remain stable, including the audited registry hooks, while focused package tests prevent the monolith from returning and preserve extraction, AcademicForge metadata, provenance, promotion, fixture and contribution behavior.

- `v0.31.1` connects stable DPL claim and evidence IDs to the real claim-contract and Scientific Evidence Registry fallback paths instead of leaving them in a test helper. Explicit project IDs remain authoritative. Shared JSON/text IO, citation parsing and LaTeX escaping are consolidated for the active claim, evidence, reference and Data-writing paths, while the unused parallel dependency map has been removed from the artifact DAG.

### v0.30.1-v0.31.0 (2026-07-18) -- Release Gates, Precise Stale Propagation and Author Completion Transactions

- `v0.30.1` reconciles the public command inventory and release manifest without exposing the experimental manuscript-completion prototype. Core evidence, data quality, result validity, method verification and integrity gates now return nonzero process status for non-passing scientific decisions. MCP artifact reads reject private locators and credential-like files, and journal/registry metadata fetching is routed through an HTTPS, host, DNS and response-size policy.
- `v0.30.2` applies one project-local runner contract to manifest and CLI method verification, rejects inline Python and shell runners, confines declared inputs/outputs, records explicit system-binary opt-in, passes only allowlisted scientific environment variables and redacts process logs. Mutating commands now validate declared write roots before running and still verify the actual write set afterward. Literature retrieval distinguishes `success_with_items`, `success_empty`, `provider_error`, `auth_required`, `rate_limited` and `offline_fallback` in stage manifests, `status` and `doctor`.
- `v0.30.3` replaces the three competing revision/stale vocabularies with one 13-class change taxonomy. Artifact DAG, external drift sync, section revision, author revision and reviewer repair now emit the same canonical names and derive stale impact from the same contract. Methods and Discussion edits start from their actual section stages, evidence-changing patches reopen the scientific chain, and revision preview/apply is bound to one promoted evidence snapshot.
- `v0.30.4` registers `dpl.manuscript_completion.v1` and adds `prepare-manuscript-completion` plus the read-only `manuscript-completion-status`. The generated author template covers structured metadata, funding, availability statements, short title, keywords and user-confirmed references; its journal report separates required, recommended, missing, placeholder and not-applicable fields. Completion input cannot directly replace scientific evidence, metrics, claims or figures, and later preview/apply commands remain unpublished until their own transaction gates pass.
- `v0.30.5` resolves author edits through stable paragraph ID, expected text/hash and optional occurrence while treating LaTeX line numbers as non-authoritative hints. Line drift is reported and re-anchored only when stable anchors still agree; stale, ambiguous, duplicate-key and duplicate-target packets are rejected as a whole. One packet can resolve multiple sections and user-confirmed references against one source-map/project revision, and project revision files can no longer read content from outside the project boundary.
- `v0.30.6` adds completion preview, apply and rollback as one hash-bound transaction flow. Preview produces a unified metadata/section/BibTeX diff, candidate LaTeX and candidate PDF without touching canonical sources. Apply rechecks the packet, project revision, source map, evidence snapshot and before hashes, then atomically writes metadata, references, sections, stale state, ledgers and exact-text user locks. Repeated apply is idempotent, injected failures restore the full write set, and rollback refuses to overwrite any artifact changed after completion. `compile_required`, unresolved Codex instructions and scientific evidence changes are explicitly non-passing.
- `v0.30.7` binds the applied completion manifest, manuscript metadata, every canonical section, BibTeX/reference registry, promoted evidence, result/figure manifests, final citation-audit snapshot, integrity/quality reports, two independent blind reviews and `main.pdf` into one release hash. Non-passing or stale bound artifacts block review and confirmation. The README opening now presents the current evidence-first path and final-author checkpoint directly, with complete English and Chinese completion guides under `docs/`.
- `v0.31.0` completes multi-journal author-workspace regression with general article, AAS and MNRAS frontmatter semantics and real XeLaTeX candidate compilation. The release tests single and multiple authors and affiliations, ORCID, corresponding-author metadata, funding and repository links, user-confirmed references, multi-paragraph atomic edits, rollback, user locks and final release binding in both source checkout and isolated wheel installations.

### v0.28.1-v0.30.0 (2026-07-17) -- Transactional Evidence Architecture and Cross-discipline Release Contracts

- `v0.28.1` makes section revision a real multi-artifact transaction. Accepted edits are installed into canonical section sources, survive repeated LaTeX assembly, propagate real downstream stale state, and roll back canonical, candidate and project-state artifacts together on injected failure. This completes the transaction guarantee first introduced in `v0.27.2`.
- `v0.28.2` migrates all 210 discipline plugins to explicit manifest v2 contracts. Runtime class, validation level, maturity, deployment state, fixture inventory and execution policy are no longer silently inferred; source and wheel registries now agree on 546 fixtures and 175 contract-only, 25 code-generator and 10 fixture-executed runtime records.
- `v0.28.3` adds project-level state revisions, locking and rollback across `project.json`, its YAML mirror and every stage manifest. Write-set violations restore project-local changes where possible, and MCP science/network execution requires a short-lived HMAC capability token bound to the exact project, command and arguments.
- `v0.29.0` upgrades the artifact dependency model to real paths, hashes, owners, producer/consumer edges and authoritative/derived roles. Product release numbers are removed from first-party schema IDs and replaced by a versioned schema-family registry.
- `v0.29.1` introduces one normalized runtime command-contract view for all 204 CLI commands and makes it authoritative for consistency validation, MCP schemas and doctor diagnostics. The report exposes the migration boundary explicitly: 80 registered handlers and 124 compatibility dispatches remain, so future decomposition is measurable rather than hidden.
- `v0.29.2` adds targeted Ruff and pyright gates, coverage, project-scoped dependency auditing with CycloneDX SBOM output, secret scanning, pinned GitHub Action SHAs, reproducible CI tool constraints, source/wheel release identity, SPDX-style license metadata and clean wheel manifest rules.
- `v0.30.0` expands the wheel-installable release matrix across scientific-image+ML, geography+ML, astronomy+ML, bioinformatics+medicine and physics/quantum projects. Each fixture now carries six main figure groups through claim, data plugin, method plugin, project run output, evidence ID and review-rule trace, while adversarial cohort/run/unit/model/metric/dimension, blank-figure, plugin and citation cases must still be rejected.

Release checks:

```powershell
draftpaper validate-command-contracts
python -m draftpaper_cli.release_contract
python -m draftpaper_cli.release_regression --output tmp/release-v0300
```

### v0.26.1-v0.28.0 (2026-07-16) -- Executable Scientific Semantics and Precise Recovery

- `v0.26.1` separates stale artifacts, citation support, manuscript semantics, reproducibility packages, render quality, scientific analysis, figure contracts, and human review into explicit failure domains. Citation or bundle failures no longer fall back to `plan-figures`; hard-check reports name the failed predicate, artifact, and valid next command. Interactive CLI output is compact, while redirected/API output preserves complete JSON; `--compact` and `--json-full` select either contract explicitly.
- `v0.26.2` adds domain-neutral `DataProvenanceContract`, `CohortRegistry`, `CohortViewRegistry`, and append-only join/filter ledger artifacts. Every analysis view declares its parent cohort, sample unit, count, missingness policy, split, allowed use, and claim boundary. Distinct display and regression subsets may coexist, but silent count or sample-unit reuse is rejected.
- `v0.26.3` adds `ExecutableAnalysisSpec`, formula AST, resampling contract, and prespecified run-selection policy. Estimand, cohort view, split, preprocessing scope, implementation entry point, uncertainty semantics, calibration definition, formulas, and variable explanations now share one contract. ECE definition drift, false paired/grouped intervals, and unlocked best-seed headline selection are blocking semantic errors.
- `v0.27.0` splits plugin sufficiency into bootstrap and release decisions. Auditable project-local implementations can unblock a new topic before formal reusable plugins exist; final release still requires verified data/method bindings, input/output hashes, execution scope, and a capability passport. AcademicForge/GitHub rescue runs only for a real unresolved capability gap.
- `v0.27.1` upgrades the Scientific Evidence Registry key to estimand/cohort-view/analysis-spec/run/model/split/aggregation/dimension and writes section claim maps with sentence hashes and evidence IDs. Figure Contract v2 binds claims, panels, cohort views, estimands, analysis specs, runs, evidence and rendered text; journal-width QA records font, overlap, crop, color and caption checks. Post-Results discipline rules consume compiled claim-level evidence rather than broad role strings.
- `v0.27.2` adds an artifact dependency DAG and transactional `apply-section-revision`. Citation-only, presentation-only, prose-semantic, cohort, analysis, run, figure and claim-contract changes propagate to different minimal stale sets. A current functional section release is authoritative over optional manifest backfills, while changed accepted hashes still reopen the correct chain.
- `v0.27.3` builds anonymous review supplements from the selected run and Python import dependency closure, excludes unrelated historical figures/tables, compiles the closure before release, and archives reviewer reports under the superseded bundle hash when the manuscript, evidence or bundle changes. Review findings carry structured repair classes for prose, rendering, reproducibility, analysis supplements, claim downgrade or new evidence.
- `v0.28.0` adds normalized citation intents for direct support, method/tool provenance, comparison context, and dataset/product provenance while retaining all curated references and repairing prose first. Paragraph evidence remains content-addressed and delta-cached. Five cross-domain release fixtures plus adversarial cohort, calibration, run-selection, figure, plugin, and citation regressions guard the generic architecture.
- Added `JournalIntentContract`: only a confirmed journal may render a submission label; provisional and unset projects remain neutral drafts. Status distinguishes `draft_pdf_ready`, `review_blocked`, and `release_ready`, and `doctor --explain` exposes the read-only artifact DAG and recovery rationale.

Key commands:

```powershell
draftpaper doctor --project <project> --explain
draftpaper apply-section-revision --project <project> --section methods --input revised_methods.tex
draftpaper prepare-independent-manuscript-review --project <project>
draftpaper status --project <project> --compact
```

### v0.25.1-v0.26.0 (2026-07-14) -- Confirmed Research Blueprints, Task-aware Statistics, and Project Workspace Isolation

- New papers now default to the configured central `projects` root instead of following the idea or dataset location. `DRAFTPAPER_PROJECTS_ROOT`, user config, and `--projects-root` control the root; generated slugs are capped at 48 characters and use an eight-character stable project ID. Clean `_vN` children use the same short-name policy.
- Added `ProjectWorkspacePolicy`, `ArtifactOwnershipGuard`, `path-budget-check`, `doctor-project-layout`, and hash-aware `adopt-orphan-artifacts`. Managed outputs, logs, and temporary files stay inside the paper project unless an explicit export is requested.
- Large datasets remain read-only in place. Public source contracts and fingerprints use logical IDs and relative locators, while machine-local absolute paths move to ignored `external_data_locators.private.json`; the default copy policy is `manifest_only`.
- Added task-aware `StatisticalValidationContract` and `review_rule_coverage_report`. Classification, regression/fitting, grouped or temporal validation, spatial analysis, representation confounding, anomaly stability, survival, and simulation convergence receive different evidence requirements. Universal F1, R2, p-value, or fit thresholds are forbidden unless a user/journal, cited domain source, or validated discipline plugin supplies them.
- The Chinese-first research-plan packet is now a real human checkpoint. `review-research-plan` presents the plan, claims, storyboard, panel structure, method/data requirements, statistical contract, plugin preview, and feasibility limits; `confirm-research-plan` freezes their exact hash. `reopen-research-plan` is mandatory before any scientific contract change.
- Key-figure code can consume only the active confirmed blueprint. Every main figure and panel carries the confirmed plan hash, claim, data and method requirement IDs, and statistical validation IDs. `validate-confirmed-figure-alignment` rejects missing, substituted, extra, or semantically changed main figures.
- Removed discipline fallback figures from explicit research storyboards. Main-figure count can no longer be satisfied with generic histograms, correlations, or metric summaries; missing scientific story roles return to research-plan revision instead of producing filler.
- Added structured figure-caption contracts. The first sentence summarizes the complete figure group without comma-linked fragments; later sentences explain every panel, cohort, estimand, uncertainty definition, and claim boundary. Short `fig_01.png`-style paths keep scientific titles in metadata rather than filenames.
- Added the pre-execution support loop. Capability gaps first produce project-local, discipline-plugin, AcademicForge, GitHub, and connector rescue tasks. If rescue remains insufficient, the user chooses data/method supplementation or research-scope downgrade before key-figure code is generated. Post-result claim downgrade remains separate and freezes existing figures and metrics.
- The user-facing core-evidence page is now “Key Results and Claim Support Confirmation” and explains the research question, cohort, method run, statistical evidence, uncertainty, and maximum claim strength being approved. Final release adds a separate hash-bound packet containing `main.pdf`, final citation audit, both independent blind-review reports, and the quality report.
- The wheel regression now covers scientific-image astronomy+ML, geography+ML, time-domain astronomy+ML, bioinformatics/medicine, and physics/quantum, with task-aware statistical contracts and explicit rule-gap checks. Current source verification is `565 passed`; the complete 15-item evidence matrix is in [`docs/audits/2026-07-14-v0260-acceptance-report.md`](docs/audits/2026-07-14-v0260-acceptance-report.md).

Key workflow additions:

```powershell
draftpaper create-project --idea "Your research idea" --field "astronomy machine learning"
draftpaper review-research-plan --project <project>
draftpaper confirm-research-plan --project <project> --plan-hash <hash>
draftpaper path-budget-check --project <project>
draftpaper doctor-project-layout --project <project>
```

### v0.24.1-v0.25.0 (2026-07-13) -- Secure Scientific Runtime, Runnable Plugins, and Thin MCP

- Packaged the canonical `draftpaper-workflow` skill inside the wheel and added `install-skill` / `skill-doctor`. Agent instructions now defer stage order to `status`, `verify-next-action`, and `continue`, so an old user-level skill cannot silently drive a new CLI through an obsolete workflow.
- Upgraded all 186 public commands to CommandSpec v2 metadata: risk class, read/write globs, forbidden paths, resource class, timeout, idempotency, confirmation policy, and typed input/output schemas. Mutating project commands are checked against their actual post-run write set; parent traversal, UNC/device paths, symlink/reparse escapes, protected actions, arbitrary shell/raw writes, SQL, Git push, and credential disclosure are excluded from the MCP surface.
- Added Plugin Execution Contract v2 and deterministic `plugin_catalog_snapshot.json`. All 209 plugin manifests receive a valid explicit or compatibility-adapted execution contract, while `catalog_hash` and per-plugin contract hashes flow through sufficiency, binding, execution, figure trace, and discipline review. Contract/fixture-only or mock API/GPU/server plugins still cannot support a scientific result.
- Promoted 22 high-frequency local data/method capabilities and 10 review rules through an explicit runnable-profile registry. Each promoted capability executes a deterministic scientific algorithm with minimal, failure, and boundary fixtures; review rules include an applicability boundary and threshold source. Remaining foundation rules stay advisory and external contracts stay mock-only until real validation.
- Made research-plan figure story roles explicit, removed the formal-writing first-eight evidence fallback, and added claim/run/cohort/model/figure/citation-role retrieval. Paragraph evidence is content-addressed, cached, and delta-aware; the held-out repeated-evidence regression reduces actual paragraph input by at least 35% while preserving every evidence ID.
- Added Citation Role Contract v2 (`dataset_provenance`, instrument/product definition, processing support, method/tool background, prior-result comparison, mechanism/interpretation, and general background). Roles are assigned before writing; citation audit validates their use afterward and retains the established rewrite-before-delete policy.
- Integrity now prefers promoted, run-aware Scientific Evidence Registry counts and reports legacy unbound `sample_composition.csv` as a compatibility source. Main-figure narratives explicitly reserve direct scientific signal, comparison, mechanism/ablation, and uncertainty/boundary roles instead of allowing diagnostics to occupy every main slot.
- Added `workflow_trace.jsonl` and `audit-workflow-runtime` with run/command IDs, attempts, duration, input hashes, process/command/scientific/transaction outcomes, loop detection, duplicate-run detection, and packet metering. Added SQLite-backed `submit-job`, `job-status`, `job-cancel`, `job-notifications`, and `recover-jobs`; workers survive the initiating terminal and lost workers become `orphaned` rather than silently retried.
- Added a ten-tool local stdio Draftpaper MCP (`python -m draftpaper_cli.mcp.server`) with portable `mcp-install` and deterministic `mcp-doctor`. It is a thin projection over CommandSpec and CLI handlers, provides bounded artifact selectors, and cannot directly execute human checkpoints or destructive administration.
- Expanded wheel-shipped held-out release regressions to astronomy+ML, Euclid-context geography+ML, bioinformatics+medicine, and previously unused physics+quantum capability chains, plus adversarial scope, figure, plugin-runtime, and citation checks. The machine-readable closure ledger is [`docs/audits/v025_issue_ledger.json`](docs/audits/v025_issue_ledger.json); the 41 AcademicForge collection-level placeholders remain explicitly `requires_source_inspection` and do not enter sufficiency.
- Final source verification: all `555` tests pass, including the explicit four-domain wheel-verifier contract regression. Package compilation, isolated v0.25.0 wheel installation, canonical skill hash, 209-plugin catalog, 32 runnable profiles, ten-tool MCP stdio handshake, four held-out domains, and all adversarial release checks pass.

Key setup and diagnostics:

```powershell
python -m pip install -e .[mcp]
draftpaper install-skill --force
draftpaper skill-doctor
draftpaper mcp-doctor
draftpaper mcp-install --output .mcp.json
```

### v0.23.1-v0.24.0 (2026-07-13) -- Project Isolation, Native Recovery, and Independent Manuscript Review

- Added clean `_vN` project versioning. The parent stays read-only; only allowlisted reusable assets are imported with hashes and lineage receipts. Passports, stage manifests, sufficiency reports, figure metadata, audits, snapshots, and other derived state are rebuilt in the child instead of being copied as active evidence.
- Added a project system of record, command transactions, stage receipts, exact stale propagation, and rebuild plans for derived artifacts. Results lifecycle repair now rebuilds the current result manifest before discipline review, preventing an old review from being applied to changed prose or evidence.
- Added capability packs, routing evaluations, ownership checks, project-local data/method audits, and project implementation contracts. Missing formal plugins no longer create a "method code cannot be generated until the method already exists" deadlock; only an exhausted data/method rescue route can block scientific figure production.
- Added run-aware Figure and Paragraph Evidence Resolvers with task budgets. Doctor evaluates the latest packet for each writing task while retaining lifetime token cost separately, so historical retries do not leave a repaired project permanently in warning state.
- Added a canonical reference registry, work/version duplicate resolution, journal bibliography contracts, and rendered reference proofs. Bibliography formatting is now checked separately from claim-level citation support, and citation repair continues to preserve retained references.
- Added recursive third-party provenance for paper-fetch-skill, AcademicForge, upstream scientific skill repositories, Gbrain design influence, and Superpowers planning influence, including pinned commits, licenses, use modes, and affected paths. Gbrain remains optional design context only.
- Added native Draftpaper-loop `doctor`, `recover`, `start`, `continue`, `review`, and `revise` commands, with all CLI parsers registered under one `CommandSpec` contract. Doctor is deterministic and read-only; recovery never silently accepts figures, downgrades claims, deletes references, or promotes plugins.
- Replaced manuscript A/B and original-manuscript quality ratios with a single-manuscript independent review contract. Two reviewers inspect the same frozen anonymous generated manuscript and real figures in independent sessions; release requires no unresolved critical or major findings, and disagreements enter adjudication rather than score averaging.
- Added a post-review manuscript revision workspace with stable paragraph IDs and LaTeX line anchors, structured metadata, custom references, diff/PDF preview, hash-checked acceptance, rollback, and precise stale effects.
- Added locator-safe reproducibility supplements to anonymous review bundles: source/model provenance, safe stage-owned scripts and tests, and dependency-free frozen-output replay can be reviewed without exposing private paths, credentials or identity. Caption corrections can be applied through structured metadata without rewriting scientific figure evidence.
- Added model-comparison semantics to section packets. Writers may describe an incremental or conditional contribution only when preprocessing and model nesting are verified; otherwise the manuscript must report an exact pipeline-performance contrast and keep fold-mean, pooled and resampling estimands distinct.
- Completed general software regressions for astronomy+ML, geography+ML, and bioinformatics+medicine capability chains, then completed an unfamiliar scientific-image manuscript from read-only local data through human core-evidence confirmation, final writing, PDF, integrity, bibliography and citation gates. The final citation audit retained all 17 references across 30 usages with no unsupported or unverifiable use.
- Two fresh independent sessions reviewed the same frozen anonymous final manuscript without an original or prior report. Both returned only minor revisions, scientific-correctness scores were 0.95 and 0.91, unresolved critical/major counts were zero, no adjudication was required, and the release gate passed. Minor recommendations remain visible in the revision queue rather than being silently marked resolved.
- Final verification: `537 passed`; package/tests compile cleanly; the isolated v0.24.0 wheel matches 209 plugins, 545 fixtures, six capability packs and six third-party source lineages; all three domain regressions and every adversarial release check pass. GitHub Actions is green for wheel installation and the complete Linux/Windows Python 3.10-3.12 matrix. Eval capture/replay is structural and privacy-preserving and never treats an existing manuscript as a quality baseline.

### v0.23.0 (2026-07-12) -- Wheel Release Regressions and Verifiable Quality Claims

- Added wheel-shipped, de-identified regression contracts for geography+machine learning, astronomy+machine learning, and bioinformatics+medicine. An ordinary `pip install` now exercises plugin sufficiency, project execution evidence, figure traceability, rendered-pixel and source-table checks, the Scientific Evidence Registry, Results binding, composite review rules, and the real final citation producer.
- Added adversarial regressions for wrong runs, cohorts, units, splits, models, metrics or dimensions, forged metadata on blank figures, contract/fixture-only plugins, citation negation, numeric mismatch, and causal reversal. `status` must also leave every project-file hash unchanged.
- Automated keywords, metadata, and file-presence scores can no longer authorize a quality claim. The provisional v0.23.0 comparison protocol is superseded by the v0.24.0 single-manuscript independent-review contract; current projects do not require or receive an original manuscript.
- Isolated wheel verification requires both source and installed registries to discover 209 plugins and 545 fixtures, then runs all three domain and adversarial regressions inside the installed environment. CI also covers Python 3.10-3.12 on Linux and Windows.
- Completed an evidence-first astronomy+machine-learning full run through research contracts, project-local capability rescue, six scientific figure groups, all five free-writing/editor lifecycles, final PDF assembly, and citation re-audit. The final citation snapshot retained all 12 summarized references across 25 usages with zero unsupported or blocking usages.
- The rendered technical comparison found that the generated manuscript preserved the verified cohorts, baseline/Transformer metrics, ablation direction, uncertainty boundary, and six-figure story. Introduction and Discussion were comparable or stronger in structure, while direct observational examples and Data/Methods/Results detail remained thinner than the reference manuscript. The automated functional score was 0.9825, but no formal 95% claim is made without the required independent blind reviews.
- Observable free-writing usage, measured with `tiktoken` `o200k_base`, was 122,238 section-packet input tokens and 5,716 accepted-candidate output tokens (127,954 total): Results 40,075; Introduction 15,691; Data 17,139; Methods 22,920; Discussion 32,129. Deterministic CLI stages used no model tokens; hidden reasoning and platform overhead are not estimated. See [`docs/audits/2026-07-12-astronomy-v0230-full-run.md`](docs/audits/2026-07-12-astronomy-v0230-full-run.md).
- Full local verification after the run: `441 passed`. The final quality gate has no unresolved scientific, writing, figure, evidence-snapshot, PDF, or citation error; it remains intentionally unreleased until the required two-reviewer blind comparison is recorded.

### v0.22.1-v0.22.8 (2026-07-12) -- Evidence Semantics, Runtime Truth, and State Kernel

- Fixed wheel resources and citation-audit/parity schemas. Formal writing now follows section packet -> free Codex composition -> candidate validation -> Scientific Editor -> explicit acceptance -> release; deterministic fallback remains diagnostic-only.
- Evidence Binding v2 binds quantitative claims to `evidence_id/run/cohort/sample_unit/split/model/metric_dimension` and verifies metric identity and dimension. Wrong scopes or same-value semantic substitutions block writing.
- Plugin runtime truth now distinguishes `contract_only`, `code_generator`, `fixture_executed`, `project_validated`, and `live_validated`; only hashed project or live outputs can satisfy a main-figure capability.
- Reviewer Engine v2 consumes a standard EvidenceBundle and executes real thresholds, dimensions, baseline, ablation, uncertainty, and plugin `evaluate_rule` checks. Scientific anomalies route first to local Results semantic repair.
- Figure checks inspect rendered pixels, axis/text regions, panels, and source tables. Citation audit adds passage, numeric, negation, causal-direction, and claim-strength checks while preserving references and emitting paragraph-rewrite tasks.
- Added a read-only state kernel, explicit migration, atomic JSON/JSONL writes, cross-platform locks, and separate command registry, artifact repository, schema adapters, plugin runtime, writing coordinator, and release coordinator boundaries.

### v0.21.1-v0.22.0 (2026-07-12) -- Paper Narrative and Scientific Writing Architecture

- Added the discipline-neutral Paper Narrative Engine. It reads true YAML/JSON research artifacts and produces `paper_brief.json`, `figure_story_arc.json`, `manuscript_argument_map.json`, and `section_claim_allocation.json`; main and supporting figures are grouped into finding-level stories with explicit questions, evidence, comparisons, and claim boundaries.
- Added section evidence packs, paragraph outlines, and Results synthesis plans. Introduction and Discussion receive gap/comparison matrices; Data and Methods receive lifecycle reconstructions from inventories, stage-owned code, plugin ledgers, formulas, and figure-code traces. Metrics bind through evidence, run, or artifact identifiers rather than title-string guessing.
- Added semantic panel contracts and `prepare-panel-repair`. Each panel declares its question, subset, scientific unit, data roles, method output, comparison, statistical check, chart grammar, expected conclusion, and claim boundary; repair remains local to the failed panel chain and cannot substitute weaker evidence.
- Added venue writing contracts and functional style profiles that learn section order, information density, caption density, voice, numeric reporting, terminology, and reasoning function without copying wording from a reference manuscript.
- Added a bounded paragraph-local Scientific Editor with at most three auditable iterations. It records paragraph hashes, rejects excessive whole-section churn, preserves evidence and citations, and forbids reference deletion as a shortcut for citation-audit repair.
- Replaced marker-count parity scoring with calibrated scientific dimensions. A release requires validated `codex_free_candidate` prose for all core sections, one consistent evidence snapshot, passed Results and figure quality, no blocking evidence conflicts, preserved reference coverage, and a citation audit generated after the final validated draft. Hard scientific correctness remains mandatory; functional quality must reach at least 0.95.
- Added cross-disciplinary architecture regressions for geography+machine learning, astronomy+machine learning, and bioinformatics/medicine to verify generality without embedding fixture-specific models, metrics, figure counts, or prose in generic code.

### v0.21.0 (2026-07-11) -- 95% Figure and Manuscript Quality Contracts

- Added `results_narrative_contract.json`, which assigns distinct scientific jobs to main figures: study boundary, pre-model signal, model comparison, component attribution, and error/uncertainty. Each role is bound to run-consistent metrics, its scientific question, and claim boundary, while Codex retains free prose composition.
- Added `prepare-section-writing` and `assess-manuscript-quality`. Results are scored for evidence fidelity, narrative coverage, scientific reasoning, claim calibration, and prose diversity; a formal candidate must reach 0.95, while wrong metrics and repetitive template prose enter repair.
- Added `assess-figure-publication-quality`. A non-empty PNG is no longer sufficient: main figures must satisfy semantic contracts, data/method plugin run provenance, panel completeness, statistical interpretation, pixel dimensions, and legibility.
- The generic plotter no longer silently replaces an unknown main-result figure with a data overview. Missing main-figure methods enter plugin rescue; generic diagnostic views remain available only when explicitly planned.
- Added `prepare-results-semantic-repair` and `assess-paper-quality-parity`. The former repairs only affected claims while preserving verified figure narratives; the latter aggregates figures, Results, Introduction, Data, Methods, Discussion, and citation audit, and final `quality-check` cannot pass below 0.95.

### v0.20.2 (2026-07-11) -- Post-Results Discipline Review and Capability Rescue Boundary

- Figure contracts no longer execute discipline `review_rule` gates before plotting. Data and method plugins produce figures; only figures with actual plugin traces activate matching discipline rules in `review-results-with-discipline-rules`.
- Untraceable metrics, internal artifact language, misplaced citations, and missing figure interpretation now enter `repair_required`, which prioritizes rewriting or narrowing Results claims instead of treating prose defects as figure-generation failures.
- Capability gaps first enter `rescue_required` and are checked against project-local assets, the registered plugin catalog, AcademicForge, and GitHub research code. The new `record-plugin-rescue-outcome` command permits `blocked_unavailable` only after all four routes have auditable search evidence and the required data or method capability still cannot be found.

### v0.20.1 (2026-07-11) -- Project-Local Capability Audit and Results Semantics

- Added `audit-project-capabilities` between plugin sufficiency and external rescue. It audits stage-owned local data and method assets, records privacy-safe relative evidence paths plus hashes, and creates constrained `covered_project_local` bindings only for the active project. These bindings never modify global discipline modules or bypass candidate validation and explicit promotion.
- Results discipline review now audits manuscript prose as well as figures: it detects untraceable metric claims, internal artifact language, citations used as result evidence, missing figure interpretation, incomplete plugin/run traces, and review-rule evidence conflicts.
- Data and Methods writing contexts now include sanitized descriptions of bound data and method roles, so reusable plugins and audited project-local implementations can improve scientific exposition without exposing paths, commands, manifests, or credentials.

### v0.18.9-v0.20.0 (2026-07-11) -- Capability-Driven Composite Discipline Execution

- Added a final `discipline_contract.json` and `research_capability_contract.json` immediately after research planning. They declare the primary and secondary disciplines, cross-discipline data/method/review ownership, and stable requirements for each planned claim and main figure.
- Added `assess-plugin-sufficiency`. It performs structured matching against registered `data_connector`, `method_template`, and `review_rule` manifests using roles, method families, outputs, runtime class, validation level, aliases, and discipline compatibility. A mock, plan-only, or external contract never counts as executable support for a main figure.
- Added `prepare-plugin-rescue`. A capability gap becomes a scoped route through existing plugins, AcademicForge candidate processing, license-aware public research-code discovery, generalization, validation, de-duplication, and explicit human-confirmed `promote-plugin-candidate --write`. Project-specific or license-uncertain code remains project-local.
- Added `execute-data-plugins` and `execute-method-plugins`, plus stage-owned `plugin_execution_ledger.jsonl` records. Manifest/template hashes, parameters, runtime state, input/output hashes, and fixture-versus-project-result status are preserved; fixture execution is explicitly not treated as scientific evidence.
- Added `results/figure_plugin_trace_report.json/.html`. Each main figure must trace to a research-plan claim, covered data plugin, covered method plugin, review-rule route, and a verified project run output before Results evidence is accepted. Code generation may proceed only from an explicit pre-run binding chain; missing links route to plugin rescue rather than a substitute figure.
- Added `review-results-with-discipline-rules` after `write-results`. It combines Results prose, complete figure traces, plugin bindings, verified run outputs, and composite-discipline review rules. Only mature, promoted, evidence-bound rules may block scientifically; trace gaps always stop downstream manuscript writing.
- `status` and `run-pipeline` now expose `plugin_sufficiency_required` and `plugin_gap_detected` states. Cross-discipline regression fixtures cover geography+machine learning, astronomy+machine learning, and bioinformatics+medicine chains.

### v0.18.8 (2026-07-11) -- Expanded Local Skill Foundations and Mock External Contracts

- Expanded the first-party local foundation catalog to 159 parameterized plugins across statistics, experimental design, classical ML, tabular/array processing, scientific visualization, geography, astronomy, bioinformatics, medicine, chemistry, materials science, physics, and quantum science. Every plugin is placed only under its discipline's `data_connectors`, `method_templates`, or `review_rules` directory.
- Split previously combined capabilities into independently selectable contracts, including statistical analysis/power/design, Polars, Vaex, Dask local mode, Zarr, Matplotlib, Seaborn, NetworkX, GeoMaster-style local coordinate operations, Astropy FITS/WCS/Time/units/coordinates, Bioinformatics CPU workflows, Pydicom/BIDS/NeuroKit2/survival analysis, Molfeat, FluidSim CPU, and Cirq local simulation.
- Added 12 external foundation contracts for API, remote-server, and GPU routes. They use `mock_validated` fixtures and an explicit `task_contract`; every one records `live_execution_performed: false`, does not fetch data or contact external services, and surfaces required credentials as user-confirmed inputs.
- Real external validation is deliberately project-specific: validate an API, SSH server, or GPU model only when a user-authorized paper project needs it, then upgrade that individual plugin's validation level with provenance instead of claiming a globally live capability.

### v0.18.7 (2026-07-11) -- Manifest-Driven Local Discipline Foundations

- Discipline plugin manifests now participate in runtime module registration. Adding a valid directory under `discipline_modules/<discipline>/{data_connectors,method_templates,review_rules}/<plugin>/` automatically extends that discipline's `DisciplineModuleSpec`; a manifest-only discipline is available without adding a static `module.py`.
- Added explicit plugin execution metadata: `runtime_class` distinguishes `local_pure_python`, `local_optional_dependency`, `remote_api`, `remote_server`, `gpu_model`, `laboratory_hardware`, and `support_only`; `validation_level` distinguishes `plan_only`, `mock_validated`, `fixture_runnable`, and `live_validated`. A local template never claims that an unavailable package, remote service, cluster, or GPU job has run.
- Added 80 first-party, parameterized foundation plugins with `template.py`, manifest, and normal/failure/boundary fixtures. They cover local statistics and classic ML, tabular and array processing, scientific visualization, Astropy FITS/WCS/Time/units/coordinates, GeoPandas vector/CRS work, and five new foundations: chemistry, materials science, physics, quantum science, and neuroscience.
- Each new discipline starts with 3 local data connectors, 5 method templates, and 5 advisory evidence-bound review rules. Review rules remain contextual candidates until discipline evidence, fixtures, and explicit promotion justify a blocking threshold.
- Candidate promotion now writes one canonical `manifest.json` next to `template.py`, fixture files, and provenance. That manifest is immediately consumable by runtime auto-registration; overlapping candidates become `augment_existing` overlays that merge aliases, variants, fixture references, and provenance instead of silently creating duplicate plugin contracts.

### v0.18.6 (2026-07-11) -- Third-party Skills to Discipline Plugins and Runtime Review Rules

- Added a metadata-only third-party skill conversion pipeline: `snapshot-skill-source`, `inspect-skill-source`, `index-skill-source`, `classify-skill-source`, `map-skill-capabilities`, `extract-skill-capabilities`, and `compile-skill-source`. It turns AcademicForge-style skill catalogs, personal research skills, or project-distilled skills into candidate reports without copying source code or installing plugins directly.
- AcademicForge collection records are expanded against public classification metadata and reconciled with each collection's declared skill count. Detailed records and unresolved placeholders are both indexed, with an explicit silent-loss count; a live metadata-only check currently reconciles all 340 declared skills as 299 detailed registry/classification records plus 41 source-inspection placeholders.
- Clarified that formal discipline modules accept only three promotable subplugin types: `data_connector`, `method_template`, and `review_rule`. `workflow_recipe`, `paper_contract`, and `shared_capability` remain support-layer candidates rather than being written into `discipline_modules/<discipline>/`.
- Added `review_rule_signal_scan` and support-layer backflow records so statistical validation, model baseline/ablation, split/leakage, figure-claim consistency, citation support, data/code availability, and reproducibility conditions from workflow, paper-contract, and shared-capability skills can become discipline-specific `review_rule_candidate`s.
- Expanded `ReviewRuleSpec`: review rules are evidence-bound scientific quality gates with explicit discipline, method family, data role, evidence binding, criterion type, threshold mode, threshold validation status, support-layer signal refs, fixture refs, aliases/variants, backflow source type, threshold source, failure route, maturity, and human-confirmation metadata. Model-score, goodness-of-fit, and statistical-significance thresholds default to contextual/comparative/human-confirmed rules unless backed by journal guidance, discipline convention, public benchmarks, or user confirmation.
- Added runtime review-rule gates. `prepare-method-blueprint`, Semantic Figure Contract assessment, `assess-result-validity`, `assess-result-support`, and citation audit now write review-rule gate reports so promoted, runnable/mature, evidence-bound rules can block weak or unsupported claims while candidate/foundation rules remain advisory.
- Runtime gates now consume `evidence_binding.required_fields` and `evidence_binding.forbidden_conflicts`, so promoted rules can block missing evidence or contradictions such as train/test leakage while support-layer and candidate rules remain non-blocking until reviewed.
- Review-rule gate reports now include `rescue_tasks` and `recommended_next_commands`, routing failures to data rescue, method rescue, result downgrade, manuscript repair, citation repair, or human checkpoints instead of leaving weak rules as plain reviewer text.
- Added `assess-review-rules` for direct inspection of the active discipline review rules at stages such as `method_plan`, `assess_result_validity`, `result_support_checkpoint`, and `citation_audit`.
- Added package/preflight/provenance safeguards: contribution packages contain only generalized templates, fixtures, validation reports, and provenance/backflow summaries. Support-layer candidates cannot be submitted as formal discipline plugins directly; contributors should submit the generalized and tested formal candidates that backflow from them.
- Generalized templates now retain source identifiers and matched signal metadata only; bounded source excerpts stay outside contribution packages and are not embedded back into generated Python templates. Review-rule validation checks the positive/negative synthetic fixture contract, while promotion additionally requires runnable-or-higher maturity and explicit human confirmation.
- Added `review-plugin-contribution`, a read-only maintainer review helper that summarizes package preflight status, metadata-only source policy, support-layer backflow families, threshold and human-confirmation policy, files to review, and whether the package is ready for human review before any promotion.

### v0.18.1-v0.18.5 (2026-07-10) -- Result Support, Claim Contracts, and Rescue Routes

- Added `research_plan/claim_contract.json`, generated with the research plan. It records planned claims, active claims, claim strength, linked figures, evidence roles, and claim boundaries so later writing follows an explicit scientific contract instead of silently overclaiming from weak figures.
- Added `apply-result-downgrade`. When current verified figures and metrics are scientifically usable but weaker than the original research plan, this command freezes the existing result artifacts in `results/result_evidence_freeze.json` and a versioned `results/evidence_snapshots/result_freeze_*.json`, downgrades only the active claim boundary, and does not rerun data, methods, figures, or metrics.
- Added `prepare-result-rescue`. When the user wants to keep the stronger claim, this route prepares connector-aware data supplement tasks, method supplement tasks, and open-source research-code discovery tasks through the discipline plugin layer, then reopens the data/method/figure/evidence/manuscript chain for regeneration and validation.
- Added decision-aware stale propagation. Downgrade stales manuscript and claim-boundary consumers while preserving current result evidence; supplement stales data, method planning, figure contracts, code, method verification, result validity, core evidence, results, and downstream manuscript stages.
- Updated `status` and `run-pipeline` so failed result support becomes a clear human decision point with the two executable routes: `apply-result-downgrade` or `prepare-result-rescue`. The pipeline stops there instead of continuing into manuscript writing or blind quality checks.

- Added `assess-result-support`, a scientific support checkpoint between `assess-result-validity` and `assess-core-evidence`. Technical result validity still checks outputs, metrics, and figure execution, while result support checks whether the current evidence can actually sustain the planned research claims.
- Added `results/result_support_checkpoint.json/.md/.html`. When figures or metrics only partially support the research plan, the report stops manuscript writing and records two user-facing routes: downgrade the research claims to the current evidence, or supplement data/method evidence and regenerate core figures.
- Updated the staged pipeline so `status` and `run-pipeline` stop at `result_support` when the support decision fails. Existing failed checkpoints also block `write-results`, preventing the loop from turning weak or contradictory evidence into manuscript claims.

### v0.17.0-v0.17.7 (2026-07-08 to 2026-07-10) -- Evidence-Semantic Manuscript Safeguards and Freer Writing

- Replaced the permissive fact-ledger writing path with a domain-neutral Scientific Evidence Registry. Evidence records carry role, cohort, sample unit, split, run, model, source, and confidence so contradictory cohort facts block writing instead of becoming prose hallucinations.
- Added run-aware result-evidence resolution. Metrics are selected from verified method runs and explicitly anchored sibling tables rather than from an arbitrary generic `metrics.csv`; Results, Methods, validity checks, and figure metadata share evidence identifiers and provenance.
- Added Semantic Figure Contracts. Main figures now declare scientific question, variable roles, forbidden roles, method outputs, panel structure, plot grammar, metric dimensions, and expected claim. Identifier-versus-identifier plots, mixed-unit axes, missing method outputs, and incomplete panels are rejected before core-evidence confirmation.
- Added precise change classification and stale propagation. Citation-local and presentation-only changes no longer invalidate evidence generation, whereas data, method, result, figure, and research-design changes reopen the necessary scientific chain.
- Added human-approved evidence snapshots and explicit reopening. No writer, LaTeX assembly, or final citation audit can silently mix a changed figure, metric, or manuscript section with an older evidence approval.
- Preserved Codex freedom at sentence level through section evidence packets and post-writing contracts. Freely composed section candidates are accepted only when they respect result-citation, evidence coverage, formula explanation, internal-language, and result-leakage rules.
- Added `submit-figure-semantic-annotations` for explicit, auditable legacy-figure mappings; the loop does not infer scientific meaning from an old PNG. Cross-project v0.18.0 release regression remains a separate forthcoming validation step.

- Added `writing/scientific_fact_ledger.json`, a shared manuscript-facing ledger for must-preserve scientific facts such as sample sizes, class balance, token coverage, stress-test boundaries, and result metrics.
- Connected the fact ledger to Data and Methods writing briefs, Data/Methods prose, Discussion comparison, and the final quality gate, so cleaning internal paths or raw fields no longer silently removes key scientific facts.
- Added `results/figure_interpretation_blueprint.json` so Results writing is driven by main figure groups, scientific questions, primary metrics, claim boundaries, and appendix diagnostics rather than generic artifact summaries.
- Added relevance filtering for Introduction, Data, and Discussion citation insertion, preventing same-discipline but weakly related literature from being written into inappropriate manuscript positions.
- Extended quality checks with must-preserve fact coverage, and verified the astronomy regression sections against the current `main.pdf`: v0.17.0 keeps Results citation-free and subsection-free, increases formula and figure-reference coverage, removes path/raw-field leakage, and preserves the current evidence ledger's key data facts.

### v0.16.1-v0.16.9 (2026-07-07 to 2026-07-08) -- Manuscript Writing, Figure Contracts, and Regression Hardening

- Added the `learn-writing-style-from-draft` path and `writing_style.py` profile so approved drafts can provide non-verbatim style signals without weakening evidence gates.
- Completed a full astronomy regression on the local time-aware flaring-source project: refreshed plan/data/method/figure stages, verified methods, compiled the APJS/AAS PDF, passed the integrity gate, and passed the final quality gate.
- Confirmed the regression keeps 6/6 main figure contracts satisfied, records 13 rendered scientific figures, excludes 4 unrendered supporting figures from the result manifest, preserves 12/12 BibTeX references in the assembled manuscript, and keeps Results free of citations and subsections.

- Reworked Discussion generation so filesystem artifacts, figure paths, table paths, manifest names, and Draftpaper-loop implementation language are sanitized before they can enter manuscript prose.
- Added discussion comparison preparation and citation-evidence coverage so Discussion can compare results with literature while preserving the post-writing citation audit principle: repair weak claims and placements, do not delete confirmed references.
- Added regression coverage for discussion artifact sanitization and citation-evidence expansion.

- Upgraded Data writing to preserve scientific detail such as sample roles, class balance, token coverage, modality availability, and claim boundaries while keeping paths, filenames, script names, and raw field dumps out of manuscript text.
- Upgraded Methods writing to use method-stage manifests, extracted formulas, formula-variable explanations, and figure-code traces, so Methods prose is organized around sample construction, feature/token construction, model logic, validation, metrics, and ablation evidence.
- Added AASTeX-safe LaTeX assembly fallbacks for author metadata, table rendering, and missing local bibliography styles so local review PDFs can compile reliably.

- Rewrote Results generation around `results/result_manifest.yaml`, figure metadata, metrics, captions, scientific questions, and claim boundaries instead of generic artifact summaries.
- Results now cites main figures and appendix diagnostics by role, removes literature citations, avoids subsections, and converts internal identifiers such as `row_count` or `source_id` into manuscript-facing scientific wording.
- Added idempotent Results behavior so confirmed Results are not rewritten when downstream manuscript stages rerun with unchanged result evidence.

- Upgraded `inventory-results` to write a structured v0.16.5 result manifest with `main_figures`, `appendix_figures`, `supporting_links`, `claim_boundaries`, internal tables, and figure-code traces.
- Fixed stale-output handling: planned generated figures that were not rendered in the current run are listed under `excluded_unrendered_figures` and no longer enter Results or quality checks merely because an old PNG remains on disk.
- Added regression coverage to ensure unrendered supporting/appendix figures remain in diagnosis/repair context but are excluded from the scientific result inventory.

- Expanded Data Role aliases for event-level samples, sample groups, current-observation tokens, historical sequence tokens, modality availability, feature matrices, astronomy products, and model-evaluation fields.
- Strengthened figure contract validation so 5-6 main figure groups are checked separately from supporting or appendix diagnostics, and planned main results cannot be silently replaced by validation artifacts.
- Connected method feasibility, figure execution diagnosis, result validity, and core evidence checks so missing data or method coverage routes to repair before human confirmation.

- Reframed the figure contract around 5-6 main figure groups instead of a hard cap on generated PNG files. A main figure group may contain multiple panels or generated artifacts, so extra generated outputs are valid when they serve the planned figure story.
- Added main/supporting/appendix figure accounting to `figure_plan.json` and `figure_contracts.json`. Supporting diagnostics no longer replace main results, but can be cited as Appendix Figures when they strengthen reliability or validation arguments in Results and Discussion.
- Updated `assess-figure-contracts` so it checks the number of main figure groups, allows additional panels and appendix diagnostics, and reports generated/supporting/appendix counts separately.
- Connected figure-contract failures to `repair-figure-data` and `repair-figure-method`, so missing data or missing method coverage produces concrete acquisition or method-repair tasks before the loop asks for human confirmation.
- Strengthened Data/Methods manuscript generation for astronomy and machine-learning projects with role-aware evidence numbers, safer product terminology, stage-specific Methods subsection profiles, and instruction-residue filtering.
- Made final `quality-check` fail when citation reference coverage fails, preserving the no-delete citation audit principle that retained literature summaries must be represented in the manuscript rather than silently dropped.
- Added regression tests for main-figure-group accounting, contract-gate repair tasks, appendix figure citations in Results, citation coverage quality gating, and astronomy Methods prose cleanup.

- Hardened `verify-methods` after the local code audit: verification now resolves commands to an argv list, executes with `shell=False`, rejects shell operators and explicit shell runners, and records `shell_used=false` in `methods/run_manifest.yaml`.
- Added `verify_command_argv` and `{python}` placeholders to generated method-code manifests so project artifacts no longer embed the developer machine's Python executable path. The legacy `verify_command` string remains only for compatibility.
- Moved full method stdout/stderr into project-local `methods/run_logs/` files while keeping bounded excerpts and log metadata in the run manifest.
- Clarified the analysis-code output contract: generated analysis code is canonical under `methods/`, while `code/` is a compatibility copy for older workflows.
- Removed duplicated core-evidence test setup by sharing one test helper, and added regression coverage for manifest-driven argv execution, shell rejection, log manifests, and canonical/compatibility output separation.

- Added a Data/Methods writing-brief layer. `build-data-context` and `build-method-context` now write `data/data_writing_brief.json/.html` and `methods/method_writing_brief.json/.html` before manuscript prose is generated.
- Reworked Data and Methods writing so section text is guided by required evidence roles and method stages instead of mechanically dumping context fields into the manuscript.
- Added research feasibility and research-plan feasibility gates before downstream data/method/figure work. The loop now records whether the proposed study has enough data roles, method intent, and figure-storyboard evidence before code generation.
- Added data role coverage, method feasibility, method repair, and method degradation reports so missing data or method capability is diagnosed before figure/code execution.
- `prepare-data-acquisition` now consumes data role coverage and research-plan feasibility gaps, turning missing data roles into connector-aware acquisition tasks instead of waiting for a later reviewer loop.
- Added a figure contract gate. `generate-analysis-code` now refuses blocked main-figure contracts instead of silently replacing planned result figures with validation or diagnostic fallback plots.
- `revise-research-plan` now writes a human-readable revision packet under `research_plan/` so data/method repair, scope fallback, and regeneration instructions are visible before the plan is rerun.
- `assess-result-validity` now reads figure contracts, the figure contract gate, and figure execution diagnosis; blocked or missing planned main figures force a repair route even when tabular metrics pass.
- Connected `status` and `run-pipeline` to the new repair-first route: repair data, repair methods, or revise the research plan before narrowing the scientific claim.
- Synchronized the bundled Draftpaper workflow skill and command reference with the new preflight, research-plan feasibility, method feasibility, and figure-contract stages.
- Fixed data-role canonicalization so short aliases such as `ra` do not corrupt broader roles such as spectral or remote-sensing features.
- Tightened composite-discipline method blueprints: the full plugin catalog remains available, but the method data contract is now built from templates selected for the current research plan, storyboard, method requirements, and review tasks.
- Added integrity checks for writing-brief coverage, Methods formula rendering, and formula-variable explanation while keeping prose style open enough for Codex to write natural scientific paragraphs.
- Local verification: `python -m pytest tests/test_cli_feasibility_commands.py tests/test_research_feasibility.py tests/test_research_plan_feasibility_gate.py tests/test_method_feasibility.py tests/test_figure_contract_gate.py tests/test_orchestrator_research_feasibility_routing.py`
- Local verification: `python -m pytest tests/test_data_feasibility.py tests/test_methods.py tests/test_integrity_gate.py tests/test_composite_discipline_modules.py tests/test_method_blueprint.py`
- Full local verification: `python -m pytest`, 241 tests passed.

### v0.15.1-v0.15.12 (2026-07-01 to 2026-07-06) -- Evidence-First Loop, Citation Audit, and CLI Hardening

- Hardened Data/Methods manuscript generation so local paths, filenames, workflow artifacts, implementation-only script names, and internal manifest language are cleaned before they can enter paper prose.
- Added astronomy-aware observation-product wording for spectral, response, light-curve, event, image, and exposure products, so technical columns such as PHA, ARF, RMF, and light-curve descriptors are translated into manuscript-facing data descriptions.
- Expanded method-formula extraction for time-aware classification workflows: Time2Vec-style temporal encoding, sequence position encoding, masked pooling, multimodal classifier logits, cross-entropy, macro-F1, ROC-AUC, confusion matrices, ablation deltas, correlation, and goodness-of-fit formulas now include variable explanations and figure links.
- Upgraded the integrity gate with manuscript-language linting and Data/Results sample-count consistency checks based on `results/tables/sample_composition.csv`, preventing stale or inflated evidence counts from passing silently.
- Repositioned citation audit as a post-writing claim-tightening loop: retained references are preserved, unsupported or weak usages are repaired by narrowing claims, moving citations to better-supported sentences, or adding evidence metadata; citation-bearing claims are no longer deleted by the repair step.
- Local verification: `python -m pytest`
- Current suite: 228 tests

- Fixed `write-results` so repeated calls no longer rewrite `results/results.tex` or `results/results_summary_zh.md` when the result manifest and generated text are unchanged.
- Prevented accidental downstream stale propagation after confirmed Results writing: Introduction, Data, Methods, Discussion, LaTeX, and quality stages are no longer marked stale merely because `write-results` is called again during later manuscript assembly.
- Added a regression test for the evidence-first writing order where Results are confirmed first and later writing stages continue without being invalidated by an unchanged Results rerun.
- Local verification: `python -m pytest`
- Current suite: 224 tests

- Added `classify-code-ownership`, `route-stage-code`, `build-code-provenance`, `extract-method-formulas`, and `trace-figures-to-code` so project-specific or legacy scripts under `code/` can be routed into stage-owned `data/scripts/`, `methods/scripts/`, `methods/src/`, and `methods/plotting/` locations.
- Added `data/data_code_manifest.json`, extended `methods/method_code_manifest.json`, added `methods/method_formula_manifest.json`, `methods/method_formulas.tex`, and `results/figure_code_trace.json` as manuscript-facing provenance inputs.
- Upgraded `build-data-context` and `build-method-context` so Data and Methods writing must read stage-owned code manifests, formula extraction, and figure-code traces instead of treating `code/` as an undifferentiated script dump.
- Added `prepare-discussion-comparison`, which writes a comparison-literature matrix, HTML evidence notes, and innovation/limitations prompts before `write-discussion`.
- Extended astronomy, geography, and machine-learning discipline modules with stage-owned code-layout and formula/figure-trace constraints.
- Revalidated the migration path on the local astronomy project: legacy `code/` scripts were classified, routed, formula-scanned, and traced to result figures; Methods context remained correctly blocked while the upstream method-plan stage was stale after artifact-drift synchronization.

- Switched GitHub Actions to install `.[dev]` and run `python -m pytest`, matching the local verification path used during development.
- Fixed direct `csv.DictReader(path.open(...))` patterns in built-in discipline templates so CSV inputs are opened through context managers.
- Local verification: `python -m pytest`
- Current suite: 219 tests

- Added `draftpaper_cli/template_registry.py` and `draftpaper validate-template-registry` for validating built-in discipline plugin manifests, template files, fixtures, plugin identifiers, and maturity metadata.
- Added tests so future discipline plugin contributions can be checked before promotion into the formal module library.

- Added `io_utils`, `latex_utils`, and `citation_utils` to reduce repeated JSON/text loading, LaTeX escaping, BibTeX parsing, and citation-key parsing logic.
- Migrated high-risk manuscript and gate modules, including Methods, Results, Introduction, Discussion, LaTeX assembly, and quality checks, onto shared helpers.
- Preserved support for common LaTeX citation commands such as `\cite{}` and `\citep{}`.

- Added focused common-utility tests and aligned gate behavior around shared parsing helpers.
- Kept `methods/` as the canonical generated-analysis-code location while retaining `code/` as compatibility output.

- `verify-methods` now reads `methods/method_code_manifest.json` when `--command` is not supplied, using generated verification metadata, declared outputs, and selected input data.
- Method verification now checks `results/figure_contracts.json`; missing or placeholder contracted main figures fail the hard gate.
- `generate-analysis-code` now writes manifest-driven verification and plotting-install metadata and recommends a shorter manifest-driven verification command.

- Packaged the paper-fetch runtime under `draftpaper_cli/_vendor/paper_fetch_skill` so wheel installs retain the fallback source instead of relying on a source-tree-only `third_party/` path.
- Added a `fulltext` optional extra for heavier article/PDF extraction dependencies while keeping the default install lighter.
- Verified with `python -m pip wheel . --no-deps` that the wheel contains the vendored paper-fetch CLI and third-party license.

- Fixed `verify-methods` CLI semantics so failed method verification returns a non-zero process exit code while still printing the run manifest JSON. Automation can now treat the command as a real hard gate.
- Removed the developer-local historical source path from newly generated `project.json` files and replaced it with a neutral `legacy_mvp_reference` note, improving project portability across machines and public examples.
- Added regression tests for failed `verify-methods` exit codes and portable project scaffolding metadata.
- Refreshed README workflow wording so the documented paper loop stays evidence-first: literature and planning are followed by data/method execution, figure generation, result validity, and core evidence review before manuscript writing.

- Upgraded `plan-figures` so research-plan storyboard figures become strict main-result contracts written to `results/figure_contracts.json` and checked through `results/storyboard_alignment_report.json`.
- Upgraded `generate-analysis-code` to write `results/figure_execution_diagnosis.json` and `.html`; missing data and missing method code are diagnosed explicitly instead of silently replacing a failed main figure with a validation, workflow, or supporting plot.
- Added `diagnose-figure-execution`, `repair-figure-data`, and `repair-figure-method`. These commands create data/method repair plans using existing connectors, public data/API routes, remote-server workflows, discipline plugins, public research-code repositories, literature implementation repositories, or Codex-generated project-specific method code.
- Upgraded `assess-core-evidence`, `status`, `run-pipeline`, and the final quality path so unsatisfied main-figure contracts route to data/method repair first; human confirmation is reserved for cases where automated repair still cannot produce the planned core evidence.

- Reordered the main paper pipeline so literature and research planning are followed by data acquisition/integration, method/code execution, figure production, result validity, and a core evidence gate before manuscript-section writing.
- Added `assess-core-evidence`, writing `core_evidence/core_evidence_report.json` and `.html` to check data supplementation, data integration, method analysis, figure production, figure metadata, and result validity before human figure confirmation.
- Split execution stages from manuscript-writing stages: `data` and `methods` now prove data/method readiness, while `data_writing` and `methods_writing` produce `data.tex` and `methods.tex` after Results evidence exists.
- Updated Results writing to keep continuous prose without per-figure subsections and to write `results/results_summary_zh.md` for Chinese review of figure-level interpretation.
- Updated orchestration, LaTeX assembly, quality gates, review routing, and the Codex skill wrapper to follow the evidence-first loop.

### v0.14.0-v0.14.13 (2026-06-24 to 2026-07-01) -- Discipline Plugins, Citation Repair, IP Protection, and Data Connectors

- Added the astronomy `remote_fits_zip_stream` data connector for remote-server or instrument-archive workflows where large FITS/ZIP observation products remain external and Draftpaper-loop only persists compact manifests, processed tables, parse-status reports, and provenance records.
- Added a generic public template for event-product manifest construction, ZIP member availability inspection, dense observation-window selection, and streaming data contracts without hard-coded private server addresses, user names, passwords, source identifiers, or project-specific labels.
- Split training smoke validation into method templates: astronomy now exposes `source_holdout_stream_smoke_test`, while machine learning exposes `group_holdout_training_smoke_test`, so event-random metrics remain leakage-risk contrasts and group/source-held-out metrics become the primary validation path when feasible.
- Upgraded `prepare-data-acquisition` to detect `fits_zip_stream` access patterns and route astronomy missing-data tasks toward the proper connector.

- Made DOI and URL fields clickable in per-paper literature summary HTML files.
- Reworked literature query planning so idea/title text is reduced to short phrases such as method, instrument, data, and task terms before being crossed with data and method queries.
- Prevented long full-title research ideas from being repeated across every search query while keeping discipline anchors such as high-energy time-domain astronomy and X-ray transient classification.
- Revalidated the astronomy workflow with `search-literature -> generate-plan`; the generated query plan now avoids full-sentence idea duplication while preserving 12 retained references, 6 planned figures, and 1 planned core table.

- Changed `generate-plan` so the human-facing research plan is written as `research_plan/research_plan.md` and `research_plan/research_plan.zh-CN.md`; `research_plan.html` and separate `research_questions.*` outputs are no longer generated.
- Embedded research questions, figure storyboard, method-plan contract, expected tables, risk checks, and the literature-summary index link directly into the research plan Markdown files.
- Upgraded the Chinese research-plan renderer so it writes a fluent Chinese planning document from the same blueprint instead of only translating section headings.
- Added structured literature query planning with context, query ID, combination level, discipline anchor, and query components for introduction/data/method/target-journal searches.
- Added low-count fallback searches for astronomy-style projects and records query provenance in `references/search_queries.json`, `references/literature_items.json`, and per-paper literature summary HTML files.
- Verified the new flow on the local astronomy project by rerunning `search-literature -> generate-plan`; the project now records 12 retained references, 30 citation-evidence rows, 6 planned main figures, and 1 planned core table.

- Added citation-use metadata for claim-level audit records, including citation intent, support status, topic relevance score, claim-alignment score, blocking status, and repair hints.
- Updated citation repair planning so unsupported or imprecise citation usages preserve retained references and rewrite manuscript claims to match existing evidence; citation audit no longer plans reference deletion or citation-bearing sentence deletion.
- Added `references/reference_usage_plan.json` so retained literature summaries are assigned to manuscript sections and must be cited at least once outside Results.
- Added `citation_audit/reference_coverage_report.json` and `citation_audit/reference_coverage_report.html` to compare `references/literature_summaries/` against unique cited references; summarized-but-uncited literature is now a blocking citation-audit failure instead of a silent bibliography shrinkage.
- Added regression tests for preserving method/tool/background citations, keeping relevant contextual citations available for rewrite, and reporting reference-coverage gaps separately from unsupported citations.

- Added public compliance documentation that clarifies the non-commercial source-available boundary, commercial authorization requirement, sponsorship-not-license rule, and prohibited anti-abuse mechanisms such as hidden payloads, telemetry, device fingerprinting, remote license checks, or destructive checks.
- Added the public DPL schema family documentation and generated project provenance blocks for project metadata, stage manifests, and project passports.
- Added stable public contract helpers for claim IDs and evidence IDs, plus tests that verify deterministic DPL identifiers and generated project metadata.
- Added public forensic-fingerprinting guidance at a high level.
- Updated commercial license and trademark notes so project terms such as Draftpaper-loop, DPL loop engine, project passport, claim trace, and evidence binding cannot be used to imply commercial authorization or official endorsement.

- Added an independent citation audit and repair loop: `audit-citations`, `generate-citation-repair-plan`, `apply-citation-repair`, `re-audit-citations`, and `run-citation-repair-loop`.
- Added claim-level local citation support checking against BibTeX and `references/citation_evidence.csv`, with RefCheck-style HTML reports under `citation_audit/iterations/` and a final pass report at `citation_audit/final_citation_audit_report.html`.
- Updated `status` and `run-pipeline` so final quality checks are blocked after integrity checks until citation audit passes; failed citation audits now route into the citation repair loop instead of continuing blindly to `quality-check`.
- Upgraded `quality-check` so direct calls require `citation_audit/final_citation_audit_report.json` with `status=passed`, preventing source-support verification from being skipped.

- Added discipline module maturity metadata with `foundation`, `runnable`, and `mature` as the intended progression.
- Added `capture-discipline-learning`, which summarizes reusable project lessons from observations, method artifacts, review plans, data contexts, result metadata, and rescue plans into `plugin_candidates/from_loop/...` without copying raw data or hidden reasoning.
- Added `classify-plugin-reusability`, which separates reusable method/review/data signals from project-specific identifiers, local paths, credentials, fixed regions, and other non-generalizable content before any promotion.
- Upgraded finance, medicine, biology, and engineering from foundation-only specs to runnable foundation modules by adding one standard-library fixture-backed method template per discipline.
- Added foundation reviewer engines for finance, medicine, biology, and engineering so these disciplines no longer fall back directly to the default reviewer route.

- Added `inspect-research-repo`, which reads a candidate repository checkout as structure/docs/package metadata only and writes `repository_structure.json`, `file_inventory.csv`, `package_manifest.json`, and HTML inspection reports without copying source code.
- Added `map-repository-workflow`, which maps repository file roles into data connector, preprocessing, method, figure, validation, review, environment, and documentation capabilities.
- Added `bootstrap-discipline-foundation`, which writes candidate-only discipline foundation suggestions from workflow maps; it does not modify formal modules by default.
- Added foundation discipline modules for finance, medicine, biology, and engineering, each with initial data connector specs, method template specs, and reviewer-rule groups.

- Added the first minimal public research-code mining chain: `discover-research-repos`, `score-research-repos`, and `extract-plugin-candidates`.
- The new flow writes metadata-only JSON/HTML reports under `research_code_mining/`, ranking repositories by license safety, reproducibility metadata, linked-paper signals, workflow completeness, and reusable capability hints.
- Candidate extraction produces `candidate_manifest.json`, `candidate_report.html`, and an index report while explicitly avoiding repository cloning, third-party source copying, or direct plugin installation.
- This creates a safer front door for future discipline-module expansion: public code can inspire generalized data/method/figure/review templates only after license, privacy, overlap, fixture, and maintainer review.

- Kept the custom source-available non-commercial license instead of switching to Apache-2.0 or another standard SPDX license, because preserving commercial authorization requirements needs non-standard terms.
- Cleaned public update wording so plugin seeds are described by reusable capabilities rather than by specific source projects or private validation targets.
- Added a README policy expectation that future public changelog entries should avoid exposing concrete internal project names, local validation folders, private datasets, or project-specific research directions.

- Added runtime composite discipline modules for cross-disciplinary papers. The loop now records `primary_discipline`, `secondary_disciplines`, `discipline_scores`, and ordered `discipline_modules`.
- `get_discipline_module` can now merge `default`, the primary discipline, and secondary disciplines, deduplicating connectors, method templates, and review rules by stable ids.
- Cross-disciplinary projects such as geography + machine learning or astronomy + machine learning can expose both domain data/method plugins and ML modelling/reviewer plugins in `prepare-method-blueprint`, `prepare-data-acquisition`, and `plan-figures`.
- Plugin candidate manifests now record primary and secondary disciplines while still keeping stable reusable capabilities under their intended home module.

- Added built-in geography data connectors for Earth Engine precipitation export planning, NetCDF-to-GeoTIFF planning, gridded text-to-raster conversion, and ArcGIS/project-bound zonal statistics manifests.
- Added geography method templates for monthly remote-sensing index summaries, phenology curve smoothing, NDVI temporal K-means zoning, and cluster statistical diagnostics.
- Added machine-learning data/model seeds for tabular environmental dataset profiling, sanitized saved-model manifests, RF/XGBoost/GBDT/stacking regression plans, observed-predicted diagnostics, feature importance, PDP/ICE, SHAP planning, and a model statistical-validity reviewer gate.
- Kept these seeds fixture-backed and dependency-light so reusable plugin code stays generic while project-specific paths, API accounts, data windows, and model binaries remain local.

- Added astronomy connector and method seeds for photon-event access planning, observation/product manifests, long-term light-curve feature extraction, and event-level sequence input construction.
- Added machine-learning/deep-learning connector and method seeds for vision catalog alignment, pretrained backbone metadata, self-supervised training plans, checkpoint compatibility diagnostics, embedding health checks, few-label evaluation, and similarity retrieval.
- Added fixture-backed tests so these discipline plugins can be validated without private data, API credentials, large checkpoints, or GPU training.
- Kept project-specific paths, credentials, checkpoint binaries, and sample selections out of reusable plugin templates; real projects bind those values locally through Draftpaper-loop project files.

- Added full `DataConnectorSpec` and `MethodTemplateSpec` schemas for discipline modules.
- Reorganized discipline modules toward a three-layer model: `data_connectors/`, `method_templates/`, and `review_rules/`.
- Added geography method templates for `remote_sensing_feature_reconstruction` and `spatial_block_validation`.
- Added machine-learning method templates for `baseline_model`, `ablation_study`, and `train_validation_test_split_check`.
- Added plugin contribution preflight commands: `summarize-plugin-candidates`, `generalize-plugin-candidate`, `validate-plugin-candidate`, `package-plugin-contribution`, and `write-github-contribution-guide`.
- Documented fork/PR rules: forks and branches are temporary contribution channels; stable reusable capabilities merge into `main` under the matching discipline module after privacy, genericity, overlap, fixture, and validation checks.

### v0.13.0-v0.13.1 (2026-06-24) -- Stage-Owned Method Code and Discipline Figure Policies

- Upgraded `plan-figures` so discipline modules can declare `minimum_main_figures`, `target_main_figures`, and `required_figure_groups`; first drafts now aim for at least five generated main figures when data are available.
- Extended discipline modules with data connector catalogs that include packages, import modules, API/download routes, credential requirements, expected data formats, and local feasibility status.
- Added `ecology` and `bioinformatics` module skeletons alongside `default`, `geography`, `astronomy`, and `machine_learning`.
- Expanded geography/agriculture, astronomy, ecology/environment, machine-learning, and bioinformatics data acquisition routes for research-plan data suggestions and missing-data rescue.

- Added a stage-owned code layout: data acquisition/preprocessing code belongs under `data/scripts`, method/model/statistical/spatial/figure-generation code belongs under `methods/scripts` and `methods/src`, and `results` keeps only produced figures, tables, and metadata.
- Added `prepare-method-blueprint`, which writes `methods/method_blueprint.json`, `methods/method_data_contract.json`, `methods/method_code_plan.json`, and `methods/method_formula_plan.json`.
- Added the `discipline_modules` framework with default, geography, astronomy, and machine-learning module skeletons for shared data, method, figure, formula, and reviewer constraints.
- Upgraded `generate-analysis-code` so canonical generated code is saved under `methods/` while `code/` remains a compatibility launcher/copy for older workflows.
- Added contributor documentation under `docs/discipline_modules/` for future discipline-module submissions.

### v0.12.0-v0.12.1 (2026-06-23 to 2026-06-24) -- Pluggable Data Acquisition and Reviewer Rescue Tasks

- Connected reviewer/rescue missing-data advice to `prepare-data-acquisition`.
- `prepare-data-acquisition` now reads `review/actionable_analysis_tasks.json`, `review/review_engineering_plan.json`, `review/statistical_rescue_plan.json`, `review/revision_plan.json`, and `review/gate_failure_diagnosis.json`.
- Added `data/data_acquisition_tasks.json` and `data/data_acquisition_tasks.html`, turning blocked analysis tasks into explicit missing-data requests with `needed_data`, `optional_data`, `suggested_connectors`, and user-confirmation questions.
- Updated `status` and `run-pipeline` so review/rescue execution now recommends `prepare-data-acquisition` after `prepare-analysis-revision` and before `plan-figures --use-review-tasks`.

- Added a shared discipline inference layer used by both data-acquisition planning and reviewer-engineering engines, so Data and review/rescue routes no longer maintain separate discipline guesses.
- Added `classify-data-access`, `prepare-data-acquisition`, and `inventory-data-sources` for plan-first data access classification.
- Added generic connector profiles for `local_files`, `api_access`, and `remote_server`. These detect access patterns without downloading data, writing credentials, or hard-coding astronomy/geography packages into the core Data stage.
- Added acquisition artifacts: `data/data_access_profile.json`, `data/data_acquisition_plan.json`, `data/data_acquisition_plan.html`, `data/data_source_manifest.csv`, `data/data_access_log.csv`, `data/data_provenance.json`, and `data/data_completeness_report.html`.
- Added design and implementation notes under `docs/superpowers/specs/` and `docs/superpowers/plans/`.
- Validated the generic layer against a local cross-discipline source tree while detecting local-file, API-access, and remote-server data modes without documenting private paths or project-specific identifiers.

### v0.11.0-v0.11.1 (2026-06-21 to 2026-06-23) -- Publication Readiness, Statistical Rescue, and Source-Available Protection

- Added repository-level protection files: `NOTICE`, `COMMERCIAL_LICENSE.md`, and `TRADEMARK.md`.
- Updated `LICENSE` wording from the older DraftPaper CLI identity to Draftpaper-loop and clarified commercial-use examples such as API services, manuscript-production services, and paid course bundles.
- Added copyright and contact headers to first-party Python files while keeping vendored third-party files untouched.
- Added stable Draftpaper-loop generator provenance to generated LaTeX, HTML reports, generated Python scripts, and JSON reports that include `generated_at`.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 130 tests

- Added `assess-publication-readiness` to score target-journal submission readiness from saved loop artifacts, including data feasibility, method verification, result validity, figure metadata, integrity, quality, and journal profile state.
- Added `discover-review-workflow-gaps` and `propose-review-engineering-plan` for discipline-specific reviewer-engineering. The first deterministic engine is geography, covering remote sensing, agricultural geography, spatial scale alignment, remote-sensing QC, spatial autocorrelation, stratified heterogeneity, and weak-fit backtracking; astronomy and machine-learning engines are now reserved with baseline reviewer rules; unmatched projects use a default fallback.
- Added `recommend-statistical-revision` to generate a statistical rescue plan when weak data or unsupported results may be improved through robust statistics, missingness analysis, method rebuilding, explicit success thresholds, domain-aware feature rebuilding, spatial validation, model validation checks, or claim reframing.
- Added review-engineering outputs: `review/review_discipline_profile.json`, `review/review_workflow_gap_report.json`, `review/review_workflow_gap_report.html`, `review/review_engineering_plan.json`, `review/review_engineering_plan.html`, and `review/user_confirmation_requests.json`.
- Added `prepare-analysis-revision`, which converts reviewer/rescue recommendations into `review/actionable_analysis_tasks.json`, checks data-role completeness in `review/analysis_revision_feasibility.json` and `.html`, and writes downstream hints to `methods/analysis_revision_requirements.json` and `results/revision_figure_plan_delta.json`.
- Connected `plan-figures --use-review-tasks` and `generate-analysis-code --use-review-tasks` so executable/partial reviewer tasks become revised figures, review-task coverage tables, and review-task metrics; blocked tasks remain explicit data requests.
- Added review outputs: `review/publication_readiness_report.json`, `review/publication_readiness_report.html`, `review/codex_archive_review_context.json`, `review/codex_archive_review_context.html`, `review/statistical_rescue_plan.json`, `review/statistical_rescue_plan.html`, `review/journal_fit_report.html`, and `review/claim_evidence_matrix.csv`.
- Added a project-archive reviewer context layer so publication readiness reports can produce more natural reviewer-like assessments from saved research plan, literature, data, method, result, figure, journal, integrity, and quality artifacts.
- Added discipline-aware statistical rescue routes for agricultural remote sensing, spatial/ecological analysis, astronomical time series, and machine-learning validation when those signals appear in the archived project context.
- Added statistical-metric semantics to result validity and review rescue: p-values are evaluated against alpha thresholds such as 0.05, while R2 is treated as goodness of fit, correlation coefficients are treated as effect sizes, and low figure-level R2/r values trigger data-quality, proxy-variable, outlier, spatial-alignment, and method-rebuild recommendations only when the project methods actually produce those statistical outputs.
- Upgraded `status`, `run-pipeline`, `generate-revision-plan`, and `re-review` so quality/integrity failures route through gate diagnosis, reviewer pass, publication readiness, statistical rescue, and one shared stale-stage rerun path.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 127 tests

### v0.10.0 (2026-06-18) -- manuscript-quality gates and clean Results/acknowledgment writing

- Added manuscript writing-quality checks for minimum section length, substantive paragraph counts, non-bulleted natural prose, arbitrary bold avoidance, Introduction/Discussion citation presence, Methods formula presence, and Results figure-count requirements.
- Upgraded `write-results` so result paragraphs cite their supporting figures and tables with LaTeX labels, for example `Figure~\ref{...}` and `Table~\ref{...}`.
- Cleaned manuscript-facing Results and Discussion prose so internal loop terms, gate names, local-file safeguards, manifest references, and Draftpaper-loop implementation wording are not written into the scientific body text.
- Added default LaTeX acknowledgments that disclose Draftpaper-loop assistance and include the project link `https://github.com/xiejhhhhhh/Draftpaper_loop`.
- Strengthened Methods outputs with formula manifests and `methods/method_formulas.tex`, then connected quality checks so Methods drafts cannot silently omit mathematical expressions.
- Expanded scientific-figure verification so generated figures must provide PNG/publication metadata, axis labels, text elements, statistics, interpretation summaries, and publication-ready backend evidence.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 111 tests

### v0.9.0 (2026-06-16) -- scientific figure loop and plotting dependencies

- Added plotting dependency extras: `.[plotting]` for the recommended research environment and `.[plotting-full]` for advanced figure/report backends.
- Added a project-local scientific plotting runtime copied into generated projects under `code/src/scientific_plotting.py`, improving portability across machines.
- Upgraded `plan-figures` from simple visualization labels to figure specifications with `figure_type`, variables, statistical transforms, backend preferences, and `no_flowchart_fallback`.
- Upgraded `generate-analysis-code` so generated pipelines produce empirical SVG figures, `results/figure_metadata.json`, and `results/figure_quality_report.json`.
- Added numpy/stdlib-compatible scientific SVG plots for scatter-regression, histogram, class-support, correlation heatmap, and metric-summary outputs.
- Upgraded Results inventory/writing so result claims use figure metadata such as sample size, association direction, R/R2, class support, and metric summaries instead of generic artifact text.
- Upgraded quality checks so generated empirical figures must have scientific metadata, axes/scale evidence, and interpretation summaries; workflow diagrams can no longer silently replace Results figures.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 103 tests

### v0.8.0 (2026-06-15) -- observation-driven Data and Methods loop

- Added `record-observation` so visible Codex/user analysis summaries can be preserved locally without storing hidden reasoning.
- Added `build-data-context` and `write-data` so the Data section is written from source/content/processing/claim-boundary context rather than file paths.
- Added `build-method-context` and upgraded `write-methods` so Methods is written from method rationale, data role, verification summary, and claim boundary rather than commands or manifest dumps.
- Upgraded `run-pipeline` so multi-step Data and Methods stages are not marked complete until required context and manuscript outputs exist.
- Added quality-gate lint that fails Data/Methods sections containing local filenames, filesystem paths, execution commands, or manifest-style output text.

### v0.7.0-v0.7.1 (2026-06-15) -- Zotero Reference Import and Literature Evidence Preservation

- Preserved Zotero-imported references as user-curated evidence outside external-search ranking, recency, abstract/PDF filtering, and the default 30-paper external cap.
- Added Zotero source/origin/collection/selection-policy metadata to literature review notes, per-paper HTML summaries, and `references/literature_summaries/index.html`.
- Added tests confirming Zotero references appear together with searched literature while remaining distinguishable.

- Added `list-zotero-collections` for inspecting Zotero collection names from Codex or the local CLI.
- Added `search-literature --zotero-collection` so a paper project can import user-curated references from one Zotero collection.
- Added `--zotero-context`, `--zotero-min-items`, and `--no-zotero-supplement` to control citation-evidence context and MVP-style external supplementation.
- Added `references/zotero_collection_manifest.json` to record the requested collection, matched collection, collection key, usable item count, and supplemental count.
- Documented how to configure `ZOTERO_LIBRARY_ID`, `ZOTERO_LIBRARY_TYPE`, and `ZOTERO_API_KEY` for Codex-driven loop calls without exposing credentials in outputs.

### v0.6.0 (2026-06-11) -- renamed and reframed as Draftpaper-loop

- Reframed the project from a CLI-first paper drafting tool to a loop-engineered research manuscript system.
- Renamed the README identity from DraftPaper CLI to Draftpaper-loop while keeping `draftpaper` as the stable command-line interface.
- Added an explicit loop model covering observe, decide, run, verify, persist state, mark stale stages, diagnose failures, and rerun.
- Added `plan-figures` so the loop plans project-specific scientific figures before generating analysis code.
- Changed `generate-analysis-code` to follow `results/figure_plan.json` instead of producing fixed workflow figures.
- Added remote/server/API data handling through source manifests and supplied processed/result artifacts with claim-limited conditional passes.
- Added HTML outputs for report-style artifacts such as novelty reports, figure plans, and literature review notes. Later versions moved the main research plan back to Markdown-first outputs for better direct review and editing.
- Moved contact, commercial-use terms, and homepage information to the end of the README after the update log.

### v0.5.0 (2026-06-09) -- review routing and gate-failure diagnosis

- Added `diagnose-gate-failures`, `review-draft`, `generate-revision-plan`, `apply-revision`, and `re-review`.
- Added unified revision issues with `source`, `target_stage`, `files_to_add_or_edit`, `required_user_input`, and `recommended_commands`.
- Added `review/commitment_ledger.csv` so user revision decisions can be tracked across review cycles.
- Connected `status` and `run-pipeline` to failed integrity/quality reports so they recommend `diagnose-gate-failures` instead of repeated blind gate reruns.
- Kept `apply-revision` intentionally conservative: it marks affected stages stale and does not rewrite scientific content automatically.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 95 tests

### v0.4.0 (2026-06-09) -- integrity gate and artifact traceability

- Added `run-integrity-gate`.
- Added `integrity/integrity_report.json` and `integrity/integrity_report.md`.
- Validates BibTeX citation existence, `citation_evidence.csv` traceability, Results no-citation rules, and result-claim artifact binding.
- Connected `status` and `run-pipeline` so final quality checks wait for a passed integrity report.

### v0.3.0 (2026-06-09) -- passport, stale sync, and staged orchestration

- Added DraftPaper Passport files: `project_passport.yaml`, `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`.
- Added `status`, `checkpoint`, `resume`, and `run-pipeline`.
- Added hash-based drift detection with `detect-artifact-drift` and `sync-artifact-stale`.
- Added literature-informed analysis-code generation and early method/result artifact checks for local workflow smoke tests.

### v0.2.0 (2026-06-09) -- Methods, Results, Discussion, and LaTeX hard gates

- Added `collect-method-plan` to convert user method notes and literature-informed method summaries into `methods/method_requirements.json`.
- Added `generate-analysis-code` to create reviewable baseline analysis code from retrieved literature, data inventory, and method requirements.
- Added `verify-methods` and `methods/run_manifest.yaml`; Methods writing now requires a successful local method-code run.
- Added `assess-result-validity` so unsupported results can route back to data, methods, or the research plan.
- Added `inventory-results` and `write-results`; Results writing is bound to real figures/tables and rejects citation commands.
- Added `write-discussion`, `assemble-latex`, `compile-latex-pdf`, and `quality-check`.

### v0.1.0 (2026-06-09) -- project model, references, journal profile, and first writers

- Added the single-paper project directory model with `idea/`, `references/`, `research_plan/`, `introduction/`, `data/`, `methods/`, `results/`, `discussion/`, and `latex/`.
- Added `create-project`, `load-project`, `validate-project`, `update-stage-status`, and `mark-stage-stale`.
- Added free-first literature retrieval through Semantic Scholar, arXiv, Crossref, and optional SerpApi.
- Standardized reference outputs: `references/library.bib`, `references/literature_items.json`, `references/citation_evidence.csv`, and literature review notes in Markdown plus HTML.
- Added target-journal template resolution through `resolve-journal-template` and literature-informed `generate-plan`.
- Added a traceable Introduction writer whose citation keys must exist in both BibTeX and citation evidence.
