<div align="center">

[![AI Research Loop](https://img.shields.io/badge/AI-Research%20Loop-5C4D7D?style=flat-square)](#what-it-does)
[![Loop Engineering](https://img.shields.io/badge/Loop-Engineering-1D7874?style=flat-square)](#loop-model)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#key-features)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#key-features)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#quick-start)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#license-commercial-use-and-contact)

# Draftpaper-loop

**Local-first research paper loop engine for auditable, traceable manuscript drafts.**

[English](./README.md) | [中文](./README.zh-CN.md)

</div>

Draftpaper-loop is a local-first research paper loop engine. It is not just a one-shot draft generator and not merely a command-line utility. The CLI is the stable tool surface, while the product concept is a repeatable loop: read project state, retrieve evidence, plan the paper, run methods, validate results, assemble LaTeX, review failures, mark stale stages, and rerun only the necessary upstream work until the manuscript is scientifically auditable.

The project follows the loop-engineering shift from prompting an agent turn by turn to designing a system that prompts, observes, verifies, stores state, and decides the next action. For research writing, this matters because a paper draft is rarely correct after one generation. Literature, data, methods, results, journal constraints, and reviewer feedback change each other. Draftpaper-loop treats those changes as first-class loop events instead of ad hoc chat history.

## What It Does

Draftpaper-loop organizes one paper as one local project directory and advances it through explicit, rerunnable stages: project creation, literature search, journal template profiling, research planning, Introduction, Data, Methods, Results, Discussion, LaTeX assembly, PDF review, integrity gates, reviewer-style revision routing, and final quality gates.

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
- Data feasibility gate before method planning.
- Project-specific figure planning before analysis-code generation.
- Methods hard gate requiring successful local code execution.
- Result validity gate before Results writing.
- Results no-citation enforcement with explicit `Figure~\ref{...}` and `Table~\ref{...}` references in result prose.
- LaTeX assembly with optional local PDF compilation.
- Default acknowledgments noting Draftpaper-loop assistance and linking to the project repository.
- Independent integrity gate for BibTeX existence, citation evidence, and result artifact binding.
- Manuscript writing-quality gates for section length, paragraph structure, citation placement, Methods formulas, Results figure count, and non-bulleted natural prose.
- Review-revise-re-review loop with gate-failure routing and commitment ledger.
- Publication-readiness reviewer layer with journal-fit risk, submission-readiness scoring, statistical rescue planning, and claim-evidence matrix outputs.
- Codex skill wrapper that remains only a calling layer.

## Project Layout

```text
draftpaper_cli/                 # Core Python package and CLI stage commands
codex_skills/draftpaper-workflow # Optional Codex skill wrapper
docs/                           # Workflow design and priority guide
tests/                          # Unit tests
third_party/paper-fetch-skill/   # Vendored MIT paper-fetch runtime
```

Generated paper projects are stored under `projects/` locally and are intentionally ignored by git to avoid uploading research data, generated drafts, full-text paper caches, and result artifacts.

## Quick Start

### Use Through Codex

The intended workflow is to let Codex read this repository and call the Draftpaper-loop CLI surface for you. After cloning the repository locally, open or point Codex to the repository directory and ask in natural language, for example:

```text
Use Draftpaper-loop in <repo> to create a paper project for this idea, search literature, write the research plan, and tell me which loop stage is blocked.
```

Codex should then run the appropriate CLI commands, inspect the generated local project files, and report the next safe stage. The raw `draftpaper` commands below are the underlying loop interface for debugging, automation, and non-Codex use; they are not meant to replace normal conversation with Codex.

For staged work, Codex should first call the orchestrator layer:

```powershell
python -m draftpaper_cli.cli status --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project <repo>\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project <repo>\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\your_project
python -m draftpaper_cli.cli diagnose-gate-failures --project <repo>\projects\your_project
python -m draftpaper_cli.cli assess-publication-readiness --project <repo>\projects\your_project
python -m draftpaper_cli.cli recommend-statistical-revision --project <repo>\projects\your_project
python -m draftpaper_cli.cli generate-revision-plan --project <repo>\projects\your_project
```

### One-Command Local Setup

Run this from the directory where you want to place the repository. The command clones the repository, creates a local virtual environment, installs the Draftpaper-loop CLI surface, and prints the CLI help. The paper-fetch runtime is vendored in `third_party/paper-fetch-skill`; install it separately only when full-text fetching is needed.

```powershell
powershell -ExecutionPolicy Bypass -Command "git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git; cd Draftpaper_loop; py -3 -m venv .venv; .\.venv\Scripts\python -m pip install -U pip; .\.venv\Scripts\python -m pip install -e .[plotting]; .\.venv\Scripts\draftpaper --help"
```

Optional full-text fetch runtime:

```powershell
.\.venv\Scripts\python -m pip install -e third_party\paper-fetch-skill
```

After setup, the installed `draftpaper` command can be used from the repository root:

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper status --project .\projects\your_project
.\.venv\Scripts\draftpaper run-pipeline --project .\projects\your_project
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --query "topic keywords"
.\.venv\Scripts\draftpaper validate-project --project .\projects\your_project
```

For a quick local smoke test without live literature search, create and validate a project:

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "X-ray flaring source classification" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper validate-project --project .\projects\x-ray-flaring-source-classification
```

### Editable Install

```powershell
python -m pip install -e .[plotting]
python -m draftpaper_cli.cli create-project --root <repo>\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project <repo>\projects\your_project
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli record-observation --project <repo>\projects\your_project --stage data --kind agent_analysis --text "Visible Codex data summary..."
python -m draftpaper_cli.cli build-data-context --project <repo>\projects\your_project
python -m draftpaper_cli.cli write-data --project <repo>\projects\your_project
python -m draftpaper_cli.cli list-zotero-collections
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --zotero-collection "Your Zotero Collection" --zotero-context all
python -m draftpaper_cli.cli plan-figures --project <repo>\projects\your_project
python -m draftpaper_cli.cli generate-analysis-code --project <repo>\projects\your_project
python -m draftpaper_cli.cli record-observation --project <repo>\projects\your_project --stage methods --kind method_rationale --text "Visible Codex method rationale..."
python -m draftpaper_cli.cli build-method-context --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\your_project
python -m draftpaper_cli.cli assess-publication-readiness --project <repo>\projects\your_project
python -m draftpaper_cli.cli recommend-statistical-revision --project <repo>\projects\your_project
python -m draftpaper_cli.cli validate-project --project <repo>\projects\your_project
```

Run tests:

```powershell
python -m unittest discover -s tests
```

For lightweight CI or metadata-only testing, `python -m pip install -e .` still installs the minimal CLI. Real paper projects should use `.[plotting]` so Matplotlib, SciencePlots, pandas, scipy, seaborn, and scikit-learn are available for publication-grade figure generation. `.[plotting-full]` additionally installs Marsilea, reportlab, and scikit-plot for complex figure layouts and optional reporting workflows.

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

The current implementation already contains the core loop primitives: an orchestrator layer (`status`, `checkpoint`, `resume`, `run-pipeline`), hash-based stale synchronization (`detect-artifact-drift`, `sync-artifact-stale`), project state commands, literature search, journal profile resolution, research plan generation, Introduction, observation recording, Data writing context generation, Data writing, data inventory and feasibility checks, method-plan collection, project-specific figure planning, figure-plan-driven analysis-code generation, method execution verification, Methods writing context generation, Methods writing, result validity checks, result inventory, Results writing, Discussion, LaTeX assembly, PDF compilation, independent integrity checks, review/revision routing, publication-readiness assessment, statistical rescue planning, and final quality checks.

Every project carries a DraftPaper Passport at `project_passport.yaml` plus append-only `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`. These files record project artifacts, hashes, explicit user checkpoints, and integrity events so the project can be moved across machines and later audited without relying on Codex conversation memory.

When a tracked artifact hash changes, `status` reports `pipeline_state=drift_detected` and recommends `sync-artifact-stale`. That command maps changed artifact paths back to their source stages, marks downstream dependent stages stale, records the drift in `integrity_ledger.jsonl`, and refreshes the passport hash baseline.

`plan-figures` observes the current idea, research plan, target journal, data inventory, method requirements, literature metadata, and any supplied local result artifacts, then writes `results/figure_plan.json` and `results/figure_plan.html`. This is where the loop decides which figures the current paper actually needs. `generate-analysis-code` then reads that figure plan and writes reviewable project-local Python code under `code/` plus `methods/analysis_code_manifest.json`; it does not emit a fixed set of default workflow diagrams. If raw data are remote, private, or too large for local processing, users can provide processed tables or final figures/tables locally and continue through `inventory-results` and `write-results` with claims limited to those artifacts. `verify-methods` must still run the generated command, record `methods/run_manifest.yaml`, and block Methods writing until every declared output exists.

`write-results` now writes result prose that explicitly points readers to the supporting figures and tables through LaTeX labels such as `Figure~\ref{...}` and `Table~\ref{...}`. Internal loop vocabulary, local-path safeguards, gate names, and project-management wording are kept out of the manuscript body and reserved for logs, reports, or acknowledgments. `assemble-latex` inserts a default acknowledgment before the bibliography noting that Draftpaper-loop assisted staged literature organization, analysis traceability, figure inventory, and manuscript drafting.

`run-integrity-gate` writes `integrity/integrity_report.json` and `integrity/integrity_report.md`, then appends an `integrity_gate` event to `integrity_ledger.jsonl`. It checks that manuscript citations exist in BibTeX, that Introduction/Data/Methods/Discussion citations are traceable to `references/citation_evidence.csv`, that Results contains no citation commands, and that every result claim in `results/result_manifest.yaml` is bound to an existing local figure or table.

`diagnose-gate-failures`, `review-draft`, `assess-publication-readiness`, `recommend-statistical-revision`, `generate-revision-plan`, `apply-revision`, and `re-review` implement the review-revise-re-review loop. Gate failures are converted into unified revision issues with target stages, files to inspect, required user decisions, and recommended CLI reruns. The publication-readiness layer estimates target-journal submission risk from saved data, methods, result, figure, integrity, quality, and journal-profile artifacts, then writes a Codex/LLM-readable archive review packet at `review/codex_archive_review_context.json` and `.html`. Its report also includes a reviewer-style narrative grounded in archived project files rather than chat-only memory. The statistical rescue layer recommends robust statistics, missingness audits, method rebuilding, explicit success thresholds, domain-aware feature rebuilding, spatial validation, model validation checks, or claim reframing when weak data or weak results might still support a defensible exploratory paper. When integrity or final quality reports failed, `status` and `run-pipeline` now walk through the review sequence: gate diagnosis, reviewer pass, publication readiness, statistical rescue, and revision planning.

`record-observation` preserves visible Codex/user analysis summaries inside `observations/observations.jsonl`. These records are used by `build-data-context` and `build-method-context` to create manuscript-facing writing packets. The writers use those packets instead of raw file inventories or execution manifests, so Data and Methods sections describe sources, variables, processing, analytical design, validation, and claim boundaries without exposing local filenames, paths, commands, or manifest dumps.

## Paper Fetch Integration

This repository vendors [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) under `third_party/paper-fetch-skill`. The adapter prefers a `paper-fetch` command on `PATH`; if unavailable, it can use the vendored runtime source. For a clean environment:

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

The third-party runtime is MIT licensed. Keep its license notice when redistributing.

## Recent Updates

### v0.11.0 (2026-06-21) -- publication-readiness reviewer and statistical rescue planning

- Added `assess-publication-readiness` to score target-journal submission readiness from saved loop artifacts, including data feasibility, method verification, result validity, figure metadata, integrity, quality, and journal profile state.
- Added `recommend-statistical-revision` to generate a statistical rescue plan when weak data or unsupported results may be improved through robust statistics, missingness analysis, method rebuilding, explicit success thresholds, domain-aware feature rebuilding, spatial validation, model validation checks, or claim reframing.
- Added review outputs: `review/publication_readiness_report.json`, `review/publication_readiness_report.html`, `review/codex_archive_review_context.json`, `review/codex_archive_review_context.html`, `review/statistical_rescue_plan.json`, `review/statistical_rescue_plan.html`, `review/journal_fit_report.html`, and `review/claim_evidence_matrix.csv`.
- Added a project-archive reviewer context layer so publication readiness reports can produce more natural reviewer-like assessments from saved research plan, literature, data, method, result, figure, journal, integrity, and quality artifacts.
- Added discipline-aware statistical rescue routes for agricultural remote sensing, spatial/ecological analysis, astronomical time series, and machine-learning validation when those signals appear in the archived project context.
- Upgraded `status`, `run-pipeline`, `generate-revision-plan`, and `re-review` so quality/integrity failures route through gate diagnosis, reviewer pass, publication readiness, statistical rescue, and one shared stale-stage rerun path.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 112 tests

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

### v0.7.1 (2026-06-15) -- preserved Zotero evidence in literature summaries

- Preserved Zotero-imported references as user-curated evidence outside external-search ranking, recency, abstract/PDF filtering, and the default 30-paper external cap.
- Added Zotero source/origin/collection/selection-policy metadata to literature review notes, per-paper HTML summaries, and `references/literature_summaries/index.html`.
- Added tests confirming Zotero references appear together with searched literature while remaining distinguishable.

### v0.7.0 (2026-06-15) -- Zotero collection import for references

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
- Added HTML outputs for summary-style artifacts such as research plans, research questions, novelty reports, figure plans, and literature review notes while keeping Markdown compatibility files.
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

## License, Commercial Use, And Contact

Draftpaper-loop is source-available for non-commercial research, evaluation, education, and personal paper-writing workflows. Commercial use, paid services, SaaS deployment, enterprise deployment, resale, or integration into commercial products requires separate written authorization from the developer.

For commercial authorization, contact [xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn).

Personal homepage: [https://xiejhhhhhh.github.io/Jinhui_profile/](https://xiejhhhhhh.github.io/Jinhui_profile/)

Third-party components keep their own licenses.
