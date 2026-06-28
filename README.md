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

Draftpaper-loop is a local-first research paper loop engine. It is not just a one-shot draft generator and not merely a command-line utility. The CLI is the stable tool surface, while the product concept is a repeatable loop: read project state, retrieve evidence, plan the paper, run methods, validate results, assemble LaTeX, review failures, mark stale stages, and rerun only the necessary upstream work until the manuscript is scientifically auditable.

The project follows the loop-engineering shift from prompting an agent turn by turn to designing a system that prompts, observes, verifies, stores state, and decides the next action. For research writing, this matters because a paper draft is rarely correct after one generation. Literature, data, methods, results, journal constraints, and reviewer feedback change each other. Draftpaper-loop treats those changes as first-class loop events instead of ad hoc chat history.

Draftpaper-loop is also intended to become a learning research workflow rather than a fixed template library. The goal is to preserve paper revision experience, reviewer-response logic, data-analysis methods, and code implementation patterns as reusable discipline modules. It should not replace scientific judgment; it should structure accumulated methods and review experience so later researchers can enter a field faster, understand its basic research patterns, and judge whether cross-disciplinary combinations are scientifically plausible.

The current user experience is strongest for geography, environmental science, remote sensing, and agricultural-environment studies, because those are the first domains with deeper data/method/reviewer loops. Other fields such as biology, medicine, engineering, computer science, astronomy, finance, and materials science can already use the general loop and the foundation discipline modules, but deep use will improve as each discipline accumulates more data connectors, runnable method templates, reviewer gates, fixtures, and real project feedback. Contributions from researchers in different fields are expected to make each module progressively more useful.

Author / developer: Jinray.

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
- Pluggable data acquisition planning for local files, API-style access, and remote/server-side data without hard-coding field-specific packages into the core Data stage.
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
- Discipline-specific reviewer-engineering engines with geography/remote-sensing support, reserved astronomy and machine-learning branches, and a default fallback.
- Metadata-only research-code mining that discovers, scores, and reports public repository candidates for future discipline plugin sedimentation without copying third-party source code.
- Codex skill wrapper that remains only a calling layer.

## Project Layout

```text
draftpaper_cli/                 # Core Python package and CLI stage commands
codex_skills/draftpaper-workflow # Optional Codex skill wrapper
docs/                           # Workflow design and priority guide
tests/                          # Unit tests
third_party/paper-fetch-skill/   # Vendored MIT paper-fetch runtime
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
python -m draftpaper_cli.cli prepare-data-acquisition --project <repo>\projects\your_project --source-root C:\external\research_folder
python -m draftpaper_cli.cli record-observation --project <repo>\projects\your_project --stage data --kind agent_analysis --text "Visible Codex data summary..."
python -m draftpaper_cli.cli build-data-context --project <repo>\projects\your_project
python -m draftpaper_cli.cli write-data --project <repo>\projects\your_project
python -m draftpaper_cli.cli list-zotero-collections
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --zotero-collection "Your Zotero Collection" --zotero-context all
python -m draftpaper_cli.cli prepare-method-blueprint --project <repo>\projects\your_project
python -m draftpaper_cli.cli plan-figures --project <repo>\projects\your_project
python -m draftpaper_cli.cli generate-analysis-code --project <repo>\projects\your_project
python -m draftpaper_cli.cli record-observation --project <repo>\projects\your_project --stage methods --kind method_rationale --text "Visible Codex method rationale..."
python -m draftpaper_cli.cli build-method-context --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-citation-repair-loop --project <repo>\projects\your_project
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

The current implementation already contains the core loop primitives: an orchestrator layer (`status`, `checkpoint`, `resume`, `run-pipeline`), hash-based stale synchronization (`detect-artifact-drift`, `sync-artifact-stale`), project state commands, literature search, journal profile resolution, research plan generation, Introduction, observation recording, Data writing context generation, Data writing, pluggable data acquisition planning, data inventory and feasibility checks, method-plan collection, discipline-aware method blueprint generation, project-specific figure planning, figure-plan-driven analysis-code generation, method execution verification, Methods writing context generation, Methods writing, result validity checks, result inventory, Results writing, Discussion, LaTeX assembly, PDF compilation, independent integrity checks, review/revision routing, publication-readiness assessment, discipline-specific review-engineering discovery, statistical rescue planning, and final quality checks.

Every project carries a DraftPaper Passport at `project_passport.yaml` plus append-only `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, and `integrity_ledger.jsonl`. These files record project artifacts, hashes, explicit user checkpoints, and integrity events so the project can be moved across machines and later audited without relying on Codex conversation memory.

When a tracked artifact hash changes, `status` reports `pipeline_state=drift_detected` and recommends `sync-artifact-stale`. That command maps changed artifact paths back to their source stages, marks downstream dependent stages stale, records the drift in `integrity_ledger.jsonl`, and refreshes the passport hash baseline.

`prepare-method-blueprint` connects the inferred discipline module, data inventory, data-acquisition profile, method requirements, and reviewer/rescue tasks into `methods/method_blueprint.json`, `methods/method_data_contract.json`, `methods/method_code_plan.json`, and `methods/method_formula_plan.json`. `plan-figures` observes the current idea, research plan, target journal, data inventory, method requirements, literature metadata, method blueprint, and any supplied local result artifacts, then writes `results/figure_plan.json` and `results/figure_plan.html`. Discipline modules can now declare minimum/target main-figure counts and required figure groups; the default first-draft policy plans at least five generated main figures when data are available. With `--use-review-tasks`, it also turns executable or partial reviewer/rescue tasks into revised figures while skipping blocked tasks. `generate-analysis-code` reads that figure plan and writes canonical project-local method code under `methods/scripts/` and `methods/src/`, plus `methods/method_code_manifest.json`; `code/` is retained only as a compatibility launcher/copy. With `--use-review-tasks`, it also emits `results/tables/review_task_coverage.csv` and `results/tables/review_task_metrics.csv` for cleaning/QC, feature reconstruction, baseline/ablation, and validation coverage. If raw data are remote, private, or too large for local processing, users can provide processed tables or final figures/tables locally and continue through `inventory-results` and `write-results` with claims limited to those artifacts. `verify-methods` must still run the generated command, record `methods/run_manifest.yaml`, and block Methods writing until every declared output and required review task coverage exists.

`write-results` now writes result prose that explicitly points readers to the supporting figures and tables through LaTeX labels such as `Figure~\ref{...}` and `Table~\ref{...}`. Internal loop vocabulary, local-path safeguards, gate names, and project-management wording are kept out of the manuscript body and reserved for logs, reports, or acknowledgments. `assemble-latex` inserts a default acknowledgment before the bibliography noting that Draftpaper-loop assisted staged literature organization, analysis traceability, figure inventory, and manuscript drafting.

`run-integrity-gate` writes `integrity/integrity_report.json` and `integrity/integrity_report.md`, then appends an `integrity_gate` event to `integrity_ledger.jsonl`. It checks that manuscript citations exist in BibTeX, that Introduction/Data/Methods/Discussion citations are traceable to `references/citation_evidence.csv`, that Results contains no citation commands, and that every result claim in `results/result_manifest.yaml` is bound to an existing local figure or table.

`audit-citations`, `generate-citation-repair-plan`, `apply-citation-repair`, `re-audit-citations`, and `run-citation-repair-loop` add an independent citation audit and repair loop after integrity checks and before final quality checks. The loop compares each manuscript citation usage against BibTeX metadata and `references/citation_evidence.csv` at claim level, writes intermediate HTML reports under `citation_audit/iterations/`, and writes `citation_audit/final_citation_audit_report.html` only after the strict report has no unsupported or unverifiable citation usages. If citation audit fails, `status` and `run-pipeline` recommend the citation repair loop rather than continuing blindly to `quality-check`. The final quality gate also requires `citation_audit/final_citation_audit_report.json` with `status=passed`, so direct `quality-check` calls cannot skip source-support verification.

`diagnose-gate-failures`, `review-draft`, `assess-publication-readiness`, `discover-review-workflow-gaps`, `propose-review-engineering-plan`, `recommend-statistical-revision`, `prepare-analysis-revision`, `generate-revision-plan`, `apply-revision`, and `re-review` implement the review-revise-re-review loop. Gate failures are converted into unified revision issues with target stages, files to inspect, required user decisions, and recommended CLI reruns. The publication-readiness layer estimates target-journal submission risk from saved data, methods, result, figure, integrity, quality, and journal-profile artifacts, then writes a Codex/LLM-readable archive review packet at `review/codex_archive_review_context.json` and `.html`. The reviewer-engineering layer infers a discipline and runs a matching engine; geography covers remote-sensing, agricultural-geography, and spatial-analysis manuscripts, astronomy covers catalog/light-curve/source-classification review risks, machine learning covers leakage, validation, baseline, ablation, calibration, and imbalance risks, and unmatched projects use a default fallback. Its output includes user-confirmation requests plus a `codex_enhancement_context` extension point so Codex can append literature- and manuscript-specific reviewer suggestions on top of deterministic rules. The statistical rescue layer recommends robust statistics, missingness audits, method rebuilding, explicit success thresholds, domain-aware feature rebuilding, spatial validation, model validation checks, or claim reframing when weak data or weak results might still support a defensible exploratory paper. `prepare-analysis-revision` converts review/rescue advice into executable analysis tasks, checks required data roles, and blocks impossible reruns before new figure planning or code generation. When integrity or final quality reports failed, `status` and `run-pipeline` now walk through the review sequence: gate diagnosis, reviewer pass, publication readiness, review-engineering discovery and planning, statistical rescue, analysis-revision preparation, and revision planning.

`record-observation` preserves visible Codex/user analysis summaries inside `observations/observations.jsonl`. These records are used by `build-data-context` and `build-method-context` to create manuscript-facing writing packets. The writers use those packets instead of raw file inventories or execution manifests, so Data and Methods sections describe sources, variables, processing, analytical design, validation, and claim boundaries without exposing local filenames, paths, commands, or manifest dumps.

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

This repository vendors [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) under `third_party/paper-fetch-skill`. The adapter prefers a `paper-fetch` command on `PATH`; if unavailable, it can use the vendored runtime source. For a clean environment:

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

The third-party runtime is MIT licensed. Keep its license notice when redistributing.

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

开发不易，给点tokens费OTZ

Donation supports maintenance only and does not grant commercial use rights.

<p align="center">
  <img src="./docs/assets/donate_alipay.jpg" alt="Alipay donation QR code" width="260">
  <img src="./docs/assets/donate_wechat.png" alt="WeChat Pay donation QR code" width="260">
</p>

## Recent Updates

### v0.14.9 (2026-06-28) -- public IP protection and DPL schema provenance layer

- Added public compliance documentation that clarifies the non-commercial source-available boundary, commercial authorization requirement, sponsorship-not-license rule, and prohibited anti-abuse mechanisms such as hidden payloads, telemetry, device fingerprinting, remote license checks, or destructive checks.
- Added the public DPL schema family documentation and generated project provenance blocks for project metadata, stage manifests, and project passports.
- Added stable public contract helpers for claim IDs and evidence IDs, plus tests that verify deterministic DPL identifiers and generated project metadata.
- Added public forensic-fingerprinting guidance at a high level.
- Updated commercial license and trademark notes so project terms such as Draftpaper-loop, DPL loop engine, project passport, claim trace, and evidence binding cannot be used to imply commercial authorization or official endorsement.

### v0.14.8 (2026-06-28) -- citation audit and repair loop

- Added an independent citation audit and repair loop: `audit-citations`, `generate-citation-repair-plan`, `apply-citation-repair`, `re-audit-citations`, and `run-citation-repair-loop`.
- Added claim-level local citation support checking against BibTeX and `references/citation_evidence.csv`, with RefCheck-style HTML reports under `citation_audit/iterations/` and a final pass report at `citation_audit/final_citation_audit_report.html`.
- Updated `status` and `run-pipeline` so final quality checks are blocked after integrity checks until citation audit passes; failed citation audits now route into the citation repair loop instead of continuing blindly to `quality-check`.
- Upgraded `quality-check` so direct calls require `citation_audit/final_citation_audit_report.json` with `status=passed`, preventing source-support verification from being skipped.

### v0.14.7 (2026-06-26) -- learning loop and runnable foundation modules

- Added discipline module maturity metadata with `foundation`, `runnable`, and `mature` as the intended progression.
- Added `capture-discipline-learning`, which summarizes reusable project lessons from observations, method artifacts, review plans, data contexts, result metadata, and rescue plans into `plugin_candidates/from_loop/...` without copying raw data or hidden reasoning.
- Added `classify-plugin-reusability`, which separates reusable method/review/data signals from project-specific identifiers, local paths, credentials, fixed regions, and other non-generalizable content before any promotion.
- Upgraded finance, medicine, biology, and engineering from foundation-only specs to runnable foundation modules by adding one standard-library fixture-backed method template per discipline.
- Added foundation reviewer engines for finance, medicine, biology, and engineering so these disciplines no longer fall back directly to the default reviewer route.

### v0.14.6 (2026-06-26) -- repository inspection and foundation discipline seeds

- Added `inspect-research-repo`, which reads a candidate repository checkout as structure/docs/package metadata only and writes `repository_structure.json`, `file_inventory.csv`, `package_manifest.json`, and HTML inspection reports without copying source code.
- Added `map-repository-workflow`, which maps repository file roles into data connector, preprocessing, method, figure, validation, review, environment, and documentation capabilities.
- Added `bootstrap-discipline-foundation`, which writes candidate-only discipline foundation suggestions from workflow maps; it does not modify formal modules by default.
- Added foundation discipline modules for finance, medicine, biology, and engineering, each with initial data connector specs, method template specs, and reviewer-rule groups.

### v0.14.5 (2026-06-26) -- metadata-only research-code mining

- Added the first minimal public research-code mining chain: `discover-research-repos`, `score-research-repos`, and `extract-plugin-candidates`.
- The new flow writes metadata-only JSON/HTML reports under `research_code_mining/`, ranking repositories by license safety, reproducibility metadata, linked-paper signals, workflow completeness, and reusable capability hints.
- Candidate extraction produces `candidate_manifest.json`, `candidate_report.html`, and an index report while explicitly avoiding repository cloning, third-party source copying, or direct plugin installation.
- This creates a safer front door for future discipline-module expansion: public code can inspire generalized data/method/figure/review templates only after license, privacy, overlap, fixture, and maintainer review.

### v0.14.4 (2026-06-25) -- public wording and license positioning

- Kept the custom source-available non-commercial license instead of switching to Apache-2.0 or another standard SPDX license, because preserving commercial authorization requirements needs non-standard terms.
- Cleaned public update wording so plugin seeds are described by reusable capabilities rather than by specific source projects or private validation targets.
- Added a README policy expectation that future public changelog entries should avoid exposing concrete internal project names, local validation folders, private datasets, or project-specific research directions.

### v0.14.3 (2026-06-25) -- composite discipline modules

- Added runtime composite discipline modules for cross-disciplinary papers. The loop now records `primary_discipline`, `secondary_disciplines`, `discipline_scores`, and ordered `discipline_modules`.
- `get_discipline_module` can now merge `default`, the primary discipline, and secondary disciplines, deduplicating connectors, method templates, and review rules by stable ids.
- Cross-disciplinary projects such as geography + machine learning or astronomy + machine learning can expose both domain data/method plugins and ML modelling/reviewer plugins in `prepare-method-blueprint`, `prepare-data-acquisition`, and `plan-figures`.
- Plugin candidate manifests now record primary and secondary disciplines while still keeping stable reusable capabilities under their intended home module.

### v0.14.2 (2026-06-24) -- geography and tabular-ML plugin seeds

- Added built-in geography data connectors for Earth Engine precipitation export planning, NetCDF-to-GeoTIFF planning, gridded text-to-raster conversion, and ArcGIS/project-bound zonal statistics manifests.
- Added geography method templates for monthly remote-sensing index summaries, phenology curve smoothing, NDVI temporal K-means zoning, and cluster statistical diagnostics.
- Added machine-learning data/model seeds for tabular environmental dataset profiling, sanitized saved-model manifests, RF/XGBoost/GBDT/stacking regression plans, observed-predicted diagnostics, feature importance, PDP/ICE, SHAP planning, and a model statistical-validity reviewer gate.
- Kept these seeds fixture-backed and dependency-light so reusable plugin code stays generic while project-specific paths, API accounts, data windows, and model binaries remain local.

### v0.14.1 (2026-06-24) -- astronomy and deep-learning plugin sedimentation

- Added astronomy connector and method seeds for photon-event access planning, observation/product manifests, long-term light-curve feature extraction, and event-level sequence input construction.
- Added machine-learning/deep-learning connector and method seeds for vision catalog alignment, pretrained backbone metadata, self-supervised training plans, checkpoint compatibility diagnostics, embedding health checks, few-label evaluation, and similarity retrieval.
- Added fixture-backed tests so these discipline plugins can be validated without private data, API credentials, large checkpoints, or GPU training.
- Kept project-specific paths, credentials, checkpoint binaries, and sample selections out of reusable plugin templates; real projects bind those values locally through Draftpaper-loop project files.

### v0.14.0 (2026-06-24) -- discipline plugin contribution workflow

- Added full `DataConnectorSpec` and `MethodTemplateSpec` schemas for discipline modules.
- Reorganized discipline modules toward a three-layer model: `data_connectors/`, `method_templates/`, and `review_rules/`.
- Added geography method templates for `remote_sensing_feature_reconstruction` and `spatial_block_validation`.
- Added machine-learning method templates for `baseline_model`, `ablation_study`, and `train_validation_test_split_check`.
- Added plugin contribution preflight commands: `summarize-plugin-candidates`, `generalize-plugin-candidate`, `validate-plugin-candidate`, `package-plugin-contribution`, and `write-github-contribution-guide`.
- Documented fork/PR rules: forks and branches are temporary contribution channels; stable reusable capabilities merge into `main` under the matching discipline module after privacy, genericity, overlap, fixture, and validation checks.

### v0.13.1 (2026-06-24) -- discipline figure policy and data connector catalog

- Upgraded `plan-figures` so discipline modules can declare `minimum_main_figures`, `target_main_figures`, and `required_figure_groups`; first drafts now aim for at least five generated main figures when data are available.
- Extended discipline modules with data connector catalogs that include packages, import modules, API/download routes, credential requirements, expected data formats, and local feasibility status.
- Added `ecology` and `bioinformatics` module skeletons alongside `default`, `geography`, `astronomy`, and `machine_learning`.
- Expanded geography/agriculture, astronomy, ecology/environment, machine-learning, and bioinformatics data acquisition routes for research-plan data suggestions and missing-data rescue.

### v0.13.0 (2026-06-24) -- stage-owned method code and discipline modules

- Added a stage-owned code layout: data acquisition/preprocessing code belongs under `data/scripts`, method/model/statistical/spatial/figure-generation code belongs under `methods/scripts` and `methods/src`, and `results` keeps only produced figures, tables, and metadata.
- Added `prepare-method-blueprint`, which writes `methods/method_blueprint.json`, `methods/method_data_contract.json`, `methods/method_code_plan.json`, and `methods/method_formula_plan.json`.
- Added the `discipline_modules` framework with default, geography, astronomy, and machine-learning module skeletons for shared data, method, figure, formula, and reviewer constraints.
- Upgraded `generate-analysis-code` so canonical generated code is saved under `methods/` while `code/` remains a compatibility launcher/copy for older workflows.
- Added contributor documentation under `docs/discipline_modules/` for future discipline-module submissions.

### v0.12.1 (2026-06-24) -- reviewer/rescue data acquisition tasks

- Connected reviewer/rescue missing-data advice to `prepare-data-acquisition`.
- `prepare-data-acquisition` now reads `review/actionable_analysis_tasks.json`, `review/review_engineering_plan.json`, `review/statistical_rescue_plan.json`, `review/revision_plan.json`, and `review/gate_failure_diagnosis.json`.
- Added `data/data_acquisition_tasks.json` and `data/data_acquisition_tasks.html`, turning blocked analysis tasks into explicit missing-data requests with `needed_data`, `optional_data`, `suggested_connectors`, and user-confirmation questions.
- Updated `status` and `run-pipeline` so review/rescue execution now recommends `prepare-data-acquisition` after `prepare-analysis-revision` and before `plan-figures --use-review-tasks`.

### v0.12.0 (2026-06-23) -- pluggable data acquisition planning

- Added a shared discipline inference layer used by both data-acquisition planning and reviewer-engineering engines, so Data and review/rescue routes no longer maintain separate discipline guesses.
- Added `classify-data-access`, `prepare-data-acquisition`, and `inventory-data-sources` for plan-first data access classification.
- Added generic connector profiles for `local_files`, `api_access`, and `remote_server`. These detect access patterns without downloading data, writing credentials, or hard-coding astronomy/geography packages into the core Data stage.
- Added acquisition artifacts: `data/data_access_profile.json`, `data/data_acquisition_plan.json`, `data/data_acquisition_plan.html`, `data/data_source_manifest.csv`, `data/data_access_log.csv`, `data/data_provenance.json`, and `data/data_completeness_report.html`.
- Added design and implementation notes under `docs/superpowers/specs/` and `docs/superpowers/plans/`.
- Validated the generic layer against a local cross-discipline source tree while detecting local-file, API-access, and remote-server data modes without documenting private paths or project-specific identifiers.

### v0.11.1 (2026-06-23) -- source-available protection and generator provenance

- Added repository-level protection files: `NOTICE`, `COMMERCIAL_LICENSE.md`, and `TRADEMARK.md`.
- Updated `LICENSE` wording from the older DraftPaper CLI identity to Draftpaper-loop and clarified commercial-use examples such as API services, manuscript-production services, and paid course bundles.
- Added copyright and contact headers to first-party Python files while keeping vendored third-party files untouched.
- Added stable Draftpaper-loop generator provenance to generated LaTeX, HTML reports, generated Python scripts, and JSON reports that include `generated_at`.
- Local verification: `python -m unittest discover -s tests`
- Current suite: 130 tests

### v0.11.0 (2026-06-21) -- publication-readiness reviewer and statistical rescue planning

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
