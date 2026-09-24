<div align="center">

[![AI Research Loop](https://img.shields.io/badge/AI-Research%20Loop-5C4D7D?style=flat-square)](#core-research-capabilities)
[![Loop Engineering](https://img.shields.io/badge/Loop-Engineering-1D7874?style=flat-square)](#end-to-end-research-workflow)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#literature-citations-and-independent-review)
[![Discipline Plugins](https://img.shields.io/badge/Discipline-Plugins-6A994E?style=flat-square)](#discipline-plugins-and-capability-extension)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#quick-start)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#contributors-license-commercial-use-and-contact)

# Draftpaper-loop

**Alibaba set out to make it easy to do business anywhere; Draftpaper-loop sets out to make no paper hard to write.**

**A local research workflow that turns an idea, discipline methods, and real data into auditable scientific figures, a complete manuscript, and a traceable `main.pdf`.**

[English](./README.md) | [中文](./README.zh-CN.md)

</div>

Draftpaper-loop organizes paper production as an evidence-first research loop. It confirms the research question and feasibility, matches or supplements data and method capabilities, executes analysis, checks whether figures support the claims, and then builds the manuscript, citation audit, discipline review, independent review, and PDF release from one evidence version.

## Project Scope and Current Release

### What users can do with Draftpaper-loop

- Create a structured paper project from a research idea, existing data, references, or project code.
- Generate a bilingual research blueprint, claim contract, statistical requirements, and main-figure storyboard for one focused human confirmation.
- Detect single or cross-disciplinary needs, bind `data_connector`, `method_template`, and `review_rule` plugins, and run real project code for data processing, training, statistics, and scientific plotting.
- Audit project-local capabilities and prepare traceable rescue tasks from the plugin registry, AcademicForge metadata, or public research-code repositories.
- Trace main figures to a research-plan claim, cohort, data plugin, method plugin, run output, evidence ID, and applicable discipline rules.
- Write Results → Introduction → Data → Methods → Discussion from the same evidence, stage-owned code, formulas, figures, and literature.
- Audit citation support, bibliography format, discipline statistics, Results semantics, and reproducibility before two independent blind reviewers inspect the manuscript.
- Complete authors, affiliations, ORCID, funding, acknowledgments, data/code links, references, and precise paragraph revisions in one packet before releasing a hash-bound `main.pdf`.

**Current release: v0.43.2.** The v0.43 series combines explicit literature admission, stronger research contracts, discipline-specific astronomy semantics, and verified publication environments. Subsequent `main` updates add evidence governance with an edit-first/reconcile-later mode, readable checkpoint changes, recovery after successful plugin reruns, and change-aware CI. These additions have not yet received a new release tag; see [Recent Updates](#recent-updates) for the distinction between released versions and current source.

## Core Research Capabilities

| Research stage | Main capability | Key artifacts |
|---|---|---|
| Research design | Idea analysis, journal profile, bilingual blueprint, claim/statistical/figure contracts, and human confirmation | confirmed plan hash, claims, figure storyboard |
| Discipline capability | Single/cross-discipline detection, data/method/review plugin matching, project-local audit, and capability rescue | discipline/capability contracts, plugin bindings |
| Data and methods | Source inventory, feasibility, stage-owned code, verified runs, formula and variable extraction | data/method manifests, run/formula manifests |
| Figures and evidence | Semantic figure/panel contracts, figure-code trace, result validity, and Result Support | main/supporting figures, result manifest, evidence registry |
| Scientific writing | Paper Narrative Engine, section evidence packets, Codex free composition, Scientific Editor | Results, Introduction, Data, Methods, Discussion |
| Literature and citations | Discipline-routed multi-source search, Zotero, local PDF/structured import, symmetric discipline gates, paper identity resolution, on-demand full text, post-fetch review, score preservation, bilingual HTML, and citation audit | identity/fetch receipts, active snapshot, quarantine, `library.bib`, citation evidence, final audit |
| Review and release | Post-Results discipline review, two blind reviewers, author-completion transaction, compilation, and release hash | reviewer reports, completion packet, `main.pdf` |
| Runtime and publication | Read-only environment contract, native PDF-parser checks, system Git detection, and isolated XeLaTeX/pdfLaTeX/BibTeX verification | environment contract, verification receipt, bilingual environment reports |

<!-- capability:checkpoint_summary_and_runtime_handshake -->
<!-- capability-meta: id=checkpoint_summary_and_runtime_handshake; status=implemented; since=0.35 -->
**Checkpoint transparency and runtime identity.** Before any human confirmation, Draftpaper-loop writes bilingual readable decision pages, an artifact manifest, confirmation request, DecisionBrief, scientific fingerprint, machine audit JSON, and readability reports. The Agent shows the readable page's project-relative and machine-absolute path first, then the semantic delta, unresolved items, and confirmation meaning; technical audit HTML is rendered from JSON only on explicit request. `session-preflight` binds the source checkout, wheel, Python, command registry, schema registry, Skill copies, and plugin catalog before project writes.
<!-- /capability:checkpoint_summary_and_runtime_handshake -->

<!-- capability:metadata_first_research_code_sources -->
<!-- capability-meta: id=metadata_first_research_code_sources; status=implemented; since=0.36 -->
**Metadata-first research-code sources.** Retained literature can carry metadata-only GitHub and Zenodo code leads, DOI/version lineage, provider receipts, and stable literature work identity. The index distinguishes paper sources from code sources; discovery does not download, install, execute, or turn a code lead into a citation or plugin.
<!-- /capability:metadata_first_research_code_sources -->

<!-- capability:safe_research_code_archive_inspection -->
<!-- capability-meta: id=safe_research_code_archive_inspection; status=implemented; since=0.36 -->
**Safe archive inspection.** A separately confirmed archive download is checked for checksum, path traversal, symlink/device entries, size/compression limits, license consistency, and static structure before any plugin promotion. Third-party code is never executed by metadata enrichment or static inspection.
<!-- /capability:safe_research_code_archive_inspection -->

<!-- capability:discipline_aware_literature_identity -->
<!-- capability-meta: id=discipline_aware_literature_identity; status=implemented; since=0.40 -->
**Discipline-aware literature identity loop.** `search-literature` defaults to `resolve_then_fetch_on_demand`: discipline-routed sources such as NASA ADS and OpenAlex discover candidates, Core writes hash-bound identity receipts for the shortlist, and the wheel's vendored paper-fetch runtime is called only when evidence needs full text. Resolved titles, abstracts, and text must pass topic, discipline, and role gates again before entering the active snapshot. `audit-literature-integrity` verifies reachability from active works to fetched artifacts. `quarantine-orphan-literature` defaults to a preview and requires the exact packet hash to apply, with a hash-verified rollback route.
See [Discipline-aware literature discovery and identity](docs/discipline_aware_literature.md) for commands and status semantics.
<!-- /capability:discipline_aware_literature_identity -->

**Evidence identity and readable stage review.** The framework validates typed `MetricEvidence`, `CountEvidence`, `AggregationContract`, `PrimaryMetricContract`, `RunEvidenceBundle`, and `FigureCodeTrace v2` before Result Support or checkpoint review. A `dpl.checkpoint_summary.v6` package separates the author-facing `HumanDecisionBrief` from a JSON-first complete audit, records scientific/audit/presentation fingerprints, bounds StageActivity to the current checkpoint window, and aligns main figures with their claim statements. Identity is checked before values are compared, so different cohorts, runs, models, validation designs, or denominators are reported as non-comparable rather than silently merged. Confirmation pages describe changes in plain language: which fact or figure changed, its previous and current value or scientific meaning, and where to inspect the current evidence. Missing prior-image previews are reported explicitly; hashes remain available in the technical audit.

**Evidence governance and deferred reconciliation.** Revision cycles now keep a trusted scientific baseline separate from the live workspace and from each candidate generation. `author_edit` lets an author continue editing prose, figures, code, and methods before one centralized reconciliation; `live` keeps immediate upstream routing. Direct editor changes are discovered in declared scientific work areas, while generated receipts and caches remain outside the scientific drift set. Binding packets validate the actual source value through JSON Pointer or auditable CSV/TSV row selectors, and the read-only `audit-evidence-governance` command produces a structured report plus optional bilingual HTML. Preview LaTeX/PDF is explicitly unreconciled and cannot become a release. Strict promotion requires an exact candidate hash, parent baseline, and immutable C3 user-confirmation receipt; scientific-semantic changes must be user-confirmed against the same candidate before reconciliation can complete. A damaged baseline, incomplete coverage, stale binding, or missing governance self-test blocks release without deleting the author's draft.

### From the early releases to the current framework

- **v0.1-v0.13: paper-project and research-stage foundations.** References, journal profiles, research plans, methods/results/discussion writing, artifact tracking, Zotero, observations, scientific plotting, and stage-owned code.
- **v0.14-v0.20: discipline plugins and result support.** Data connectors, method templates, review rules, plugin sufficiency, AcademicForge/GitHub candidate rescue, cross-discipline execution ledgers, and post-Results discipline review.
- **v0.21-v0.28: scientific narrative and evidence semantics.** Paper Narrative Engine, section evidence packets, free composition plus Scientific Editor, run/cohort/estimand binding, semantic figure contracts, independent review, and reproducibility bundles.
- **v0.28.1-v0.33: transactions, release, and exact recovery.** Artifact DAG, unified CommandSpec, scientific non-zero exits, author-completion transactions, stable paragraph locators, cross-journal/cross-platform wheel regression, Result Support v3, and release-hash binding.
- **v0.34-v0.35: cross-discipline literature quality and document evidence.** Query Contract v2 preserves multilingual topic anchors, provider routing follows discipline and language, relevance and role coverage are content-based, and local PDFs are normalized into work-bound evidence passages. pypdf remains the default; official MinerU Agent is an authorized, quality-triggered upgrade, while self-hosted CPU/GPU MinerU is represented only by a generic endpoint contract and deployment guidance.
- **v0.36-v0.37: code sources, checkpoint transparency, and release-quality closure.** Retained literature now discovers GitHub/Zenodo metadata-only code sources while preserving version DOI, paper-era lineage, license, and provider receipts; human checkpoints produce Chinese stage packages with dual paths; runtime preflight, semantic drift governance, archive security, Ruff no-new-debt, source/wheel/Skill/schema parity, and a Definition of Done audit protect release consistency. Stars/forks and paper/software citations rank and explain candidates, but do not replace scientific validation.
- **v0.37.1-v0.40: delegated review, longitudinal consistency, and literature identity.** Tiered Agent delegation, StageActivityBundle, immutable baselines, and canonical facts protect repeated runs. Query Contract v3, symmetric discipline conflicts, default identity resolution, evidence-on-demand full text, post-fetch review, active-snapshot reachability, and rollback-capable quarantine prevent cross-discipline false recall and historical orphan re-entry.
- **v0.41: readable scientific confirmation and semantic continuity.** New v5 checkpoint packages make the decision page readable without sacrificing the technical audit. Scientific, audit, and presentation identities are separate; no-op presentation or derived-artifact rebuilds preserve a valid author decision, while changes to a metric, cohort, split, method, figure semantics, or claim boundary reopen C3 with an explicit semantic delta.
- **v0.42-v0.43 and subsequent main updates: review, deployment, and iterative evidence governance.** Unified review packets, literature admission, verified publication environments, and discipline-isolated contracts are extended by edit-first reconciliation, readable fact/figure changes, plugin-rerun recovery, and tiered CI. Changes after v0.43.2 are listed separately below until a new release is tagged.

Version numbers explain capability origin. Daily use follows the current research question and project state; `status`, `doctor`, and `run-pipeline` recommend the next action.

## Quick Start

### 0. Verify the complete publication environment

Python extras install Draftpaper's Python capabilities; they do not install a TeX distribution, Visual C++ runtime, or system Git. On Windows, use the standard MiKTeX 25.12 private-install route described in [Environment Deployment](docs/environment_deployment.md), then run:

```powershell
.\tools\bootstrap_windows_environment.ps1 -Mode Check
.\.venv\Scripts\python -m draftpaper_cli doctor --target publication --json
.\.venv\Scripts\python -m draftpaper_cli verify-environment --target publication --compile-latex --output .tmp\environment-verification
```

The verifier writes its JSON receipt, bilingual report, PDFs, and logs only to the requested output directory. Do not run it inside a real paper project; use a separate Draftpaper temporary-project compile for an end-to-end check.

### 1. Install the plotting profile used by real paper projects

PowerShell:

```powershell
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -c requirements\runtime-constraints.txt -e ".[plotting]"
.\.venv\Scripts\draftpaper doctor --json
```

bash/macOS/Linux:

```bash
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -c requirements/runtime-constraints.txt -e ".[plotting]"
draftpaper doctor --json
```

### 2. Let Codex drive the workflow

Open the repository in Codex and describe the idea, data location, target journal, and existing code:

```text
Use Draftpaper-loop in this repository to create a paper project for my research idea.
Read the idea, data, and existing code first, identify the disciplines and capability gaps, and show me the research blueprint for confirmation.
After confirmation, follow project state through data, methods, figures, writing, citation audit, two independent reviews, and PDF compilation.
```

Codex handles open-ended research reasoning and prose. The Draftpaper-loop CLI records stage state, evidence binding, write boundaries, and human confirmations.

### 3. Run the shortest CLI path

```powershell
draftpaper create-project --idea "Your research idea" --field "astronomy machine learning" --target-journal MNRAS
draftpaper status --project .\projects\<project>
draftpaper run-pipeline --project .\projects\<project>
```

`run-pipeline` stops at research-blueprint, result-support, and final-release checkpoints and recommends the next command. Projects default to `projects/<project>/`; the compiled manuscript is `projects/<project>/latex/main.pdf`.

Basic tutorial video: [Bilibili](https://www.bilibili.com/video/BV1LKjS6gEh4/)

## End-to-End Research Workflow

```text
idea, existing data, project code, and literature
  -> create an isolated paper project
  -> identify disciplines and target journal
  -> search/import literature and build citation evidence
  -> generate bilingual blueprint, claims, statistics, and main-figure storyboard
  -> human confirmation of the research blueprint
  -> assess plugin sufficiency and audit project-local capabilities
  -> execute data plugins, method plugins, and real project code
  -> generate main figures, supporting evidence, tables, and evidence registry
  -> assess whether results support the planned claims
  -> accept evidence, narrow claims, or supplement data/methods
  -> Results -> Introduction -> Data -> Methods -> Discussion
  -> post-Results composite-discipline review and semantic repair
  -> final author completion and precise revisions
  -> final citation audit
  -> two independent blind reviewers
  -> integrity, journal-format, and PDF compilation checks
  -> confirm one release hash
  -> latex/main.pdf
```

### Loop behavior and human control

```text
load project state
  -> select the current stage action
  -> execute and produce structured artifacts
  -> validate scientific contracts and file hashes
  -> record artifacts, runs, evidence, and human decisions
  -> mark exact downstream stages stale when inputs change
  -> diagnose failure and route to the owning stage
  -> repeat until the manuscript is release-ready
```

Deterministic contracts own project state, cohort/run identity, plugin provenance, figure semantics, formulas, citations, stale propagation, write sets, and release hashes. Codex or another Agent owns open-ended literature interpretation, method design, scientific reasoning, and prose.

The three concentrated human checkpoints are:

1. **Research blueprint confirmation:** inspect the research question, claims, cohorts, data/method requirements, statistical standards, main figure groups, and feasibility boundary together.
2. **Core result and claim-support confirmation:** inspect verified runs, core figures, metrics, uncertainty, and maximum supported claim strength, then select the next route.
3. **Final manuscript and release confirmation:** inspect the completion packet, candidate PDF, final citation audit, two blind-review reports, and release hash together.

Before any of these checkpoints is presented, Draftpaper-loop writes an offline
package under `review/checkpoints/<checkpoint_id>/`. Open the bilingual
`stage_summary` decision page first: it shows the scientific question,
before/after semantic delta, main facts and figures, claim boundary, exclusions,
and reopen conditions. The complete technical audit is retained as
`stage_audit.json` and rendered only on demand. Research blueprints use a
versioned `HumanReviewPacket` and cannot request confirmation until the current
revision's pending tasks are complete. The Agent gives the decision page's
project-relative and absolute paths first, then the delta, blockers, and
confirmation meaning. `scientific_decision_sha256`, rather than a changing
audit package hash, determines whether a new C3 decision is needed; unchanged
science receives a continuity receipt. See
[Human Checkpoint Packages](docs/human_checkpoints.md).

### Two routes when result support is insufficient

<!-- capability:result_support_two_routes -->
<!-- capability-meta: id=result_support_two_routes; status=implemented; since=0.18 -->
- **Claim-narrowing route:** freeze accepted figures and metrics, reduce claim strength, and rebuild the affected manuscript sections.
- **Data/method rescue route:** supplement data roles, quality control, methods, or validation, then rerun the affected evidence, figure, and manuscript chain.
The current implementation selects one route for the whole result-support checkpoint; per-claim routing remains a later capability.
<!-- /capability:result_support_two_routes -->

<!-- capability:result_support_checkpoint_v3 -->
<!-- capability-meta: id=result_support_checkpoint_v3; status=implemented; since=0.32 -->
Result Support v3 prefers current resolved evidence, followed by the selected run manifest and explicitly run-bound result tables. Route commands bind the current checkpoint hash. Cohort, metric, or figure-evidence findings discovered after Results return to the same checkpoint so prose and evidence versions stay aligned.
<!-- /capability:result_support_checkpoint_v3 -->

## Discipline Plugins and Capability Extension

**Recovery after a plugin failure.** A later valid project execution for the same requirement and plugin resolves its older execution failure. Success for another binding, fixture runs, and records without qualifying output evidence cannot clear it; a later failure remains blocking. Execution ledgers retain the full history, and current-artifact validity is checked separately.

### Data, method, and review-rule plugins

`draftpaper_cli/discipline_modules/<discipline>/` registers three formal research plugin classes:

- **`data_connectors`:** access, reading, parsing, cleaning, normalization, cohort construction, and data-quality checks.
- **`method_templates`:** statistics, feature engineering, model training, validation, ablation, uncertainty estimation, and scientific plotting.
- **`review_rules`:** discipline- and method-aware checks for statistics, baselines, split/leakage, fit or classification quality, calibration, robustness, figure-claim alignment, and reproducibility.

Plugin manifests declare runtime level, validation level, dependencies, inputs/outputs, fixtures, and provenance. Contracts, mocks, and fixtures verify interfaces; main-figure evidence requires outputs and hashes validated on a real project or live run.

The research plan produces discipline/capability contracts, assigning each claim and figure requirement to primary/secondary disciplines and data/method/review capabilities. Capability gaps follow this order:

1. Audit existing project data/method code and outputs into a restricted `project_local` binding.
2. Search the current registry for reusable plugins.
3. Extract candidate capabilities from AcademicForge-style registry metadata.
4. Inspect license, structure, reproducibility, and input/output contracts in public research-code repositories.
5. Let Codex generate a project-specific implementation and validate it in the current project.
6. Send reusable capabilities through generalization, fixtures, overlap review, license review, and human-confirmed promotion.

A figure-stage blocking diagnosis appears after the data and method rescue routes have auditable outcomes and a required input or implementation remains missing.

### Main-figure trace

```text
research-plan claim
  -> data requirement -> data plugin/project-local binding
  -> method requirement -> method plugin/project-local binding
  -> verified run output
  -> evidence ID and cohort view
  -> figure/panel contract
  -> Results claim
  -> applicable discipline review rules
```

Data and method plugins produce the real figure inputs and method outputs. Matching `review_rule` plugins inspect figures and Results at `review-results-with-discipline-rules`.

### How external capabilities enter the plugin system

Public research code and AcademicForge use metadata-first candidate pipelines that retain repository, commit, license, dependency, input/output, runtime-level, and provenance records. Candidates enter formal discipline modules through `generalize-plugin-candidate`, `validate-plugin-candidate`, `package-plugin-contribution`, `preflight-plugin-contribution`, `review-plugin-contribution`, and human-confirmed `promote-plugin-candidate`.

Retained and anchor literature can also produce metadata-only GitHub and
Zenodo code-source leads. The records preserve the paper `work_id`, repository
or version DOI, release/commit identity, license, checksum hints, and provider
timestamps. `knowledge_base` prefers the latest stable release while retaining
paper-era lineage; `reproduction` is the only mode that requires an exact
paper-linked version. Stars, forks, paper citations, and software citations are
separate adoption/impact signals, never proof of scientific validity. Search
does not download or execute third-party code; archive download requires an
explicit confirmation, checksum/license inspection, and later fixture-based
promotion. See [Research-Code Sources](docs/research_code_sources.md).

`workflow_recipe`, `paper_contract`, and `shared_capability` stay in a support layer. Their verifiable statistical, baseline, ablation, split/leakage, citation-support, and reproducibility conditions may flow into discipline-specific `review_rule_candidate` records. See the [CLI Reference](docs/cli_reference.md) for the complete command chain.

`third_party/` stores upstream snapshots, immutable pointers, license notices, and provenance. The wheel-installable paper-fetch fallback lives under `draftpaper_cli/_vendor/paper_fetch_skill`.

## Figures, Evidence, and Scientific Writing

### Generate figures from a confirmed blueprint

`plan-figures` reads the confirmed research plan, claims, cohorts, data/method requirements, statistical contract, and existing evidence to produce main-figure groups, supporting/appendix figures, and caption contracts. The first caption sentence summarizes the scientific conclusion of the complete group; later sentences explain each panel, cohort, estimand, uncertainty, and claim boundary.

`generate-analysis-code` follows the figure contract and bound capabilities. Execution failures produce `figure_execution_diagnosis.json/.html` and distinguish data gaps, method gaps, dependency issues, runtime errors, insufficient result quality, and required user confirmation, with a recommended repair command.

### One evidence version drives the manuscript

Paper Narrative Engine reads the Scientific Evidence Registry, result manifest, figure story arc, literature comparison matrix, stage-owned code, and formula trace to build section evidence packets and paragraph goals. Codex composes freely inside those evidence boundaries; post-writing contracts validate numbers, cohorts, runs, models, metric dimensions, citation roles, internal paths, and claim strength.

- **Results:** interpret main figure groups and key tables, then use supporting/appendix figures for robustness, uncertainty, and boundaries.
- **Introduction:** organize the research gap from the question, significance, literature evidence, and contribution established by Results.
- **Data:** reconstruct sources, samples, variables, preprocessing, and missingness from connectors, inventory, cohort registry, and stage code.
- **Methods:** reconstruct stages from plugins, real implementation, run manifest, formula AST, and figure-code trace; explain formulas, variables, assumptions, and figure relationships.
- **Discussion:** align local findings with comparison literature and discuss mechanism, innovation, limitations, external validity, and future work.

`record-observation` stores only stage summaries already shown to the user. Paths, commands, credentials, manifest fields, and local filenames stay in internal context.

### Exact stale propagation and recovery

<!-- capability:scientific_gates_and_artifact_dag -->
<!-- capability-meta: id=scientific_gates_and_artifact_dag; status=implemented; since=0.30 -->
Scientific gates, non-zero exit status, one change taxonomy, and the artifact DAG determine which project states may continue. Data, cohort, method, run, metric, main-figure, or claim changes reopen the owning scientific chain; citation-local edits, author metadata, and presentation-only changes receive narrower stale scopes.
<!-- /capability:scientific_gates_and_artifact_dag -->

Each project records stages, inputs, outputs, confirmations, and recovery reasons through `project_passport.yaml`, `artifact_ledger.jsonl`, `checkpoint_ledger.jsonl`, `integrity_ledger.jsonl`, and artifact hashes. Use `doctor --explain` and `diagnose-gate-failures` to inspect state and the next action.

## Literature, Citations, and Independent Review

The literature stage preserves BibTeX, the reference registry, citation evidence, notes, per-paper summaries, and available PDF/full-text evidence. Search results, user-provided papers, and Zotero collections retain origin and selection policy. Writing assigns references to direct support, method provenance, data provenance, comparison context, and background roles.

### Multi-source literature and local documents

The literature registry can combine online search, Zotero, local folders, structured files, and manual records in one project. The provider router adds discipline-aware entry points such as OpenAlex, PubMed, Europe PMC, DBLP, and NASA ADS alongside the existing general providers; a provider failure is recorded as a degraded result, not treated as proof that no literature exists. Each record preserves canonical identifiers, source records, field-level provenance, deduplication decisions, file hashes, and logical locators.

Register a local library without moving it, or opt into hash-addressed attachment copies:

```powershell
draftpaper add-literature-source --project <project> --type local-folder --path <folder> --recursive
draftpaper collect-literature --project <project>
draftpaper reconcile-literature --project <project>
draftpaper review-literature-coverage --project <project>
draftpaper record-remote-parser-consent --project <project> --decision project --service official-agent --document-class published-public
draftpaper parse-literature-document --project <project> --input <paper.pdf> --document-class published-public
draftpaper benchmark-literature-quality --output docs/benchmarks/literature_quality.json
draftpaper benchmark-document-parsers --output docs/benchmarks/document_parser_quality.json
```

After literature selection, inspect possible reusable code without copying it:

```powershell
draftpaper enrich-literature-code-leads --project <project> --selection-mode knowledge_base
draftpaper inspect-research-code-source --project <project> --candidate-id <id>
```

The literature HTML index distinguishes online, Zotero, local-PDF, GitHub, and
Zenodo origins. Add `--include-online` only when public provider API enrichment
is desired; metadata-only enrichment never installs or runs a repository.

Local PDF folders and BibTeX/RIS/JSON files are retained as `local_import` sources; online results, Zotero items, manual records, and inherited records remain distinguishable in the HTML literature index and source filters. PDF parsing uses `pypdf` as the local default and can conditionally call the official MinerU Agent for eligible complex or scanned documents. The Agent connector is included in the core wheel, but it never uploads silently: a project-scoped consent record, public-document class, and provider limits are checked first. A user-provided MinerU endpoint takes precedence over the official route. Self-hosted MinerU and GPU deployment are not installed or operated by Draftpaper-loop; the endpoint contract and selection guidance are provided for privacy or high-volume users. MinerU is a document parser, not a search engine or reasoning model; extracted passages are candidates for metadata/evidence review and are never auto-cited solely because a PDF exists.

<!-- capability:cross_discipline_literature_and_document_quality -->
<!-- capability-meta: id=cross_discipline_literature_and_document_quality; status=implemented; since=0.35 -->
The literature loop writes a multilingual Query Contract, provider execution report, relevance/rejection report, role-coverage report, and one `literature_confirmation_packet` before planning. Every local or remote parse writes a normalized document, a parser receipt, a work-identity binding, bounded evidence passages, context/token estimates, and a source/parser distinction in the HTML index. `pypdf` is the complete offline path; MinerU routes are conditional and failure-safe.
<!-- /capability:cross_discipline_literature_and_document_quality -->

Zotero example:

```powershell
$env:ZOTERO_LIBRARY_ID="your_zotero_library_id"
$env:ZOTERO_LIBRARY_TYPE="user"
$env:ZOTERO_API_KEY="your_zotero_api_key"
draftpaper list-zotero-collections
draftpaper search-literature --project <project> --zotero-collection "My Paper References" --zotero-context all --zotero-min-items 20
```

Citation audit runs after the final sections and author completion, and before independent review. It compares manuscript claims with BibTeX metadata, citation evidence, passages, numbers, negation, and causal direction. It reports weak support, misplaced citations, and over-strong wording. Repair prefers tightening or rewriting prose while preserving user-confirmed references and reference coverage.

`review-results-with-discipline-rules` reads current Results, figure/plugin trace, run outputs, evidence IDs, and composite-discipline rules. It checks metric statements, sample boundaries, baselines, ablations, statistical dimensions, uncertainty, fit/classification standards, and figure interpretation. Semantic findings enter local Results revision; genuine capability gaps return to result support.

<!-- capability:completion_audit_and_readme_framework -->
<!-- capability-meta: id=completion_audit_and_readme_framework; status=implemented; since=0.32 -->
After citation audit, the loop builds a frozen anonymous single-manuscript review bundle. Two independent reviewers separately inspect scientific correctness, evidence sufficiency, structure, prose, figures, citations, and reproducibility materials. Both reports bind the same manuscript/evidence/bundle hash; critical or major findings enter revision and re-review, and final confirmation binds the latest reports and compiled PDF.
<!-- /capability:completion_audit_and_readme_framework -->

## Final Completion, Precise Revision, and Release

One `manuscript_completion.yaml` can add authors, affiliations, ORCID, corresponding author, funding, acknowledgments, keywords, short title, data/code availability, user-confirmed references, and multiple section revisions.

<!-- capability:stable_locator -->
<!-- capability-meta: id=stable_locator; status=implemented; since=0.30 -->
LaTeX line numbers are user-facing hints. Writes also validate stable `paragraph_id`, expected text, occurrence, and SHA-256. Paragraphs can be relocated after layout drift, while ambiguous, duplicate, or stale targets return the whole packet to preview.
<!-- /capability:stable_locator -->

<!-- capability:completion_change_classification -->
<!-- capability-meta: id=completion_change_classification; status=implemented; since=0.32 -->
Preview shows the user-declared change class, inferred class, candidate evidence refs, and exact stale scope. Author metadata, acknowledgments, and prose-only refinements stay downstream; new data provenance, executed-method details, metrics, claims, or figure interpretation reopen the matching research or writing stages through current evidence refs.
<!-- /capability:completion_change_classification -->

<!-- capability:manuscript_completion_transaction -->
<!-- capability-meta: id=manuscript_completion_transaction; status=implemented; since=0.30 -->
Completion first builds one diff, candidate LaTeX, and candidate PDF. After acceptance, atomic apply revalidates the packet, project revision, source map, evidence snapshot, and before hash, then writes rollback receipts and exact-text user locks.
<!-- /capability:manuscript_completion_transaction -->

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper review-final-manuscript --project <project>
draftpaper confirm-final-manuscript --project <project> --release-hash <sha256>
```

Release order is author completion and precise revision → final citation audit → two independent blind reviews → integrity and compilation checks → release-hash confirmation. See [Final Manuscript Completion](docs/manuscript_completion.md).

## Installation, Agents, and Daily Operation

### Install profiles

<!-- capability:minimal_install_cost_risk_release -->
<!-- capability-meta: id=minimal_install_cost_risk_release; status=implemented; since=0.31 -->
- `pip install -e .`: minimal control plane, project state, references, and basic PDF/image inspection.
- `pip install -e ".[plotting]"`: NumPy, pandas, Matplotlib, and standard scientific plotting/analysis entry points.
- `pip install -e ".[fulltext]"`: enhanced PDF and full-text extraction.
- `pip install -e ".[mineru-agent]"` or the legacy `.[mineru]` alias: no extra local model; the official Agent connector is already in core. Install and deploy a local MinerU runtime separately only when a user-managed endpoint is needed.
- `pip install -e ".[mcp]"`: local stdio MCP.
- `draftpaper doctor --json`: detect the current profile, missing modules, and recovery commands.
- `draftpaper token-report --project <project>`: summarize recorded token/cost receipts.
<!-- /capability:minimal_install_cost_risk_release -->

Use `.[plotting-full]` for complex plotting backends. Agents should normally inspect `status` and call `run-pipeline`; common diagnostic and recovery commands are:

```powershell
draftpaper status --project <project>
draftpaper doctor --project <project> --explain
draftpaper run-pipeline --project <project>
draftpaper detect-artifact-drift --project <project>
draftpaper sync-artifact-stale --project <project>
draftpaper diagnose-gate-failures --project <project>
draftpaper run-integrity-gate --project <project>
draftpaper audit-citations --project <project> --final
draftpaper assess-publication-readiness --project <project>
```

Agents can also use the workflow macros `start`, `status`, `continue`, `review`, `revise`, `doctor`, and `recover` to coordinate project creation, progress, review, revision, diagnosis, and recovery. Their arguments and write boundaries are documented in the [CLI Reference](docs/cli_reference.md).

The Python API exposes the same evidence-semantic entry points, including `resolve_result_evidence`, `build_scientific_evidence_registry`, `validate_figure_semantics`, `create_evidence_snapshot`, and `submit_section_draft`. MCP is a controlled projection of CommandSpec/CLI handlers for local Agent integration.

<!-- capability:command_schema_quality_contracts -->
<!-- capability-meta: id=command_schema_quality_contracts; status=implemented; since=0.31 -->
CommandSpec, the schema registry, and quality contracts form one command control plane for risk, inputs, outputs, write scope, network behavior, and human checkpoints. Generated references come from the same registry, so the README keeps only common user paths.
<!-- /capability:command_schema_quality_contracts -->

| Need | Document |
|---|---|
| Commands, parameters, inputs/outputs, and risk | [CLI Reference](docs/cli_reference.md) |
| Complete Python, system-runtime, and LaTeX publication setup | [Environment Deployment](docs/environment_deployment.md) |
| Minimal, plotting, fulltext, and MCP profiles | [Install Profiles](docs/install_profiles.md) |
| Write, network, and confirmation boundaries | [Command Risk Matrix](docs/command_risk_matrix.md) |
| Project token and cost receipts | [Token and Cost Reporting](docs/token_cost_reporting.md) |
| Final completion and stable paragraph locators | [Final Manuscript Completion](docs/manuscript_completion.md) |
| DPL schema, project state, and artifacts | [DPL Schema](docs/DPL_SCHEMA.md) |

## Project Layout, Evidence Contracts, and Engineering Boundaries

```text
draftpaper_cli/                    core Python package, CLI, state, and evidence contracts
draftpaper_cli/discipline_modules/ data connectors, method templates, and review rules
draftpaper_cli/_vendor/            wheel-installable runtime fallbacks
codex_skills/draftpaper-workflow/  Codex workflow skill and Agent contracts
docs/                              guides, schemas, audits, and generated references
tests/                             unit, adversarial, wheel, cross-platform, and release regressions
third_party/                       upstream snapshots, pointers, licenses, and provenance
projects/                          local paper projects, ignored by git by default
```

Within one paper project, data acquisition, cleaning, and cohort code belongs under `data/`; models, statistics, validation, and plotting code belongs under `methods/`; `results/` stores figures, tables, and metadata; `writing/`, `citation_audit/`, `review/`, and `latex/` store prose, audits, reviews, and the final PDF. Large datasets may remain at their source location through private locators, read-only fingerprints, and manifests while workflow artifacts remain owned by the paper project.

Every writing command checks its declared write set before and after execution and uses state revisions, project locks, artifact hashes, and transaction receipts. MCP capability tokens, executable allowlists, path confinement, network policies, and log redaction constrain application behavior. Public multi-tenant isolation, account systems, and hosted billing are separate product-engineering boundaries.

Run baseline verification with:

```powershell
python tools/validate_capability_truth_matrix.py
python -m pytest tests/test_capability_truth_matrix.py
python -m pytest
python -m build
```

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

## Star History

<a href="https://www.star-history.com/?repos=xiejhhhhhh%2FDraftpaper_loop&type=date&legend=top-left">
  <img alt="Draftpaper_loop GitHub star history snapshot" src="./docs/assets/star-history.svg" />
</a>

The chart is a repository-hosted snapshot generated from GitHub stargazer timestamps on 2026-08-04 UTC. Open [Star History](https://www.star-history.com/?repos=xiejhhhhhh%2FDraftpaper_loop&type=date&legend=top-left) for the interactive view.

## Recent Updates

Patch updates are consolidated below by capability milestone. The [historical release archive](docs/release_history_through_v0.43.2.md) preserves the original version-by-version notes. Test counts and verification claims in that archive describe the release at that time, not the current verification status of every feature.

### Updates on main (2026-09-23 to 2026-09-24, not yet released)

- **Preserved evidence and execution history.** Run evidence bundles are stored independently by content hash, with normalized input-file declarations. Registry and project-local capability audits merge their bindings without overwriting one another. A batch of row-level diagnostics counts as one repair attempt, reducing false escalation from binding problems to repeated scientific failure.
- **Edit first, reconcile later.** `author_edit` allows continuous changes to prose, methods, code, and figures before centralized drift scanning and reconciliation; `live` retains immediate upstream routing. Trusted baselines, working files, and candidate generations are kept separately, including changes made directly in an editor. Unreconciled PDF previews carry a draft notice and use separate outputs.
- **Source-value and release consistency.** Evidence bindings read actual values through JSON Pointer or unique CSV/TSV row selectors. Technical binding diagnostics are handled separately from scientific-support assessments. Promotion requires a matching candidate, parent baseline, user-confirmation receipt, and reconciliation state; `audit-evidence-governance` provides read-only reports and bilingual HTML.
- **Readable evidence changes.** Chinese and English confirmation pages explain added, removed, and changed facts, metrics, samples, and figures, including old/new values, supporting claims, and evaluation designs. Field names, list lengths, and hashes no longer stand in for an explanation. Missing prior-image previews are identified explicitly, with navigation to the current figure.
- **Recovery after successful plugin reruns.** A later valid project execution for the same requirement and plugin can resolve an earlier execution failure. Success for another binding, fixtures, or records without qualifying output evidence cannot resolve it; a subsequent failure remains blocking. Ledgers preserve history, while current artifacts still undergo separate evidence and drift checks.
- **Tiered CI.** Ordinary changes select focused tests by path and retain syntax, global-contract, and secret checks. Public interfaces, evidence gates, schemas, dependencies, orchestration, and changes without a reliable test mapping trigger the full matrix. Weekly schedules, version tags, and manual runs also use full cross-platform checks, with generated workflow templates kept in sync.

### v0.43.0-v0.43.2 (2026-08-31 to 2026-09-02) -- Literature admission, research contracts, and environment handoff

- Candidate literature is explicitly accepted, excluded, or deferred through a hash-bound packet, with stronger active-corpus, shared-evidence, and checkpoint-continuity contracts.
- Research plans gain explicit table contracts and bilingual review packets, improved feasibility recovery, derived-output recognition, and composite-profile merging. Astronomy/time-domain semantics live in the discipline plugin instead of leaking into unrelated fields.
- Runtime constraints, installation profiles, and clean-clone handoff guidance are aligned. Windows deployment covers Python, system Git, Visual C++ x64, and private MiKTeX; package prewarming and `plainnat.bst` checks support isolated publication compilation.

### v0.42.0-v0.42.2 (2026-08-23 to 2026-08-29) -- Unified review packets and publication environments

- Research plans use versioned bilingual `HumanReviewPacket` artifacts. Unfinished work produces focused blockers, equivalent revisions reuse review packets, and scientific changes request a new decision.
- Checkpoint v6 separates the author-facing decision page from JSON-first technical audit. Protected commands declare decision families, authority, and receipts; technical HTML is rendered on demand.
- Python 3.10 compatibility, read-only environment diagnostics, Windows bootstrap, and bilingual deployment guides are supplemented by isolated pypdf, XeLaTeX/pdfLaTeX, BibTeX, citation-resolution, and PDF checks.

### v0.41.0-v0.41.1 (2026-08-23) -- Readable scientific confirmation and continuity

- Checkpoint v5 introduces `HumanDecisionBrief`, bounded stage activity, figure/claim mapping, and bilingual readability checks.
- Scientific, audit, and presentation identities are separate: ordinary HTML/PDF rebuilding preserves valid confirmation, while metric, sample, method, analysis-specification, or figure-semantic changes require another scientific decision.
- Cohort-aware conflict detection, repeated-evidence locators, and anonymized showcases strengthen review, with read-only migration audits and shadow checks for older packages.

### v0.40.0 and the 2026-08-18 literature hardening -- Multi-source preservation, identity, and on-demand full text

- Online, Zotero, local PDF, structured-file, and manual sources merge incrementally, preserving work identity, provenance, scores, and summaries. Missing scores differ from scientific zero values; index and detail pages share offline Chinese/English switching.
- Query Contract v3 combines entity, discipline, method, and multilingual anchors. Symmetric discipline checks prevent false recall such as astronomy/ecology mismatches; generic words alone cannot pass relevance gates.
- DOI/title/author/year identity is checked before evidence-driven full-text retrieval and post-fetch relevance review. Local parsing binds work identity to evidence passages. Ambiguous, incorrect, and historical orphan artifacts stay outside the active citation pool, with preview, hash confirmation, and rollback for quarantine.

### v0.37.1-v0.39.0 (2026-08-11) -- Delegated review and consistency across revisions

- WorkflowTrace and stage-activity packages record reading, analysis, generation, edits, reuse, and validation. Review pages bring together deliverables, changes, blockers, and recovery routes.
- Manual/balanced/delegated modes support explicit Agent authority for eligible C1/C2 reviews; C3 scientific decisions, the final manuscript, and release remain user-confirmed.
- CanonicalFactRegistry, immutable scientific baselines, and revision cycles distinguish value conflicts, non-comparable results, and out-of-scope edits, with aligned source, wheel, Skill, schema, and release identity.

### v0.35.1-v0.37.0 (2026-08-03) -- Research-code sources and checkpoint transparency

- Retained literature discovers metadata-only GitHub/Zenodo code leads with DOI lineage, licenses, provider receipts, and work identity. Adoption and citation signals inform ranking; knowledge-base and strict-reproduction modes use different version policies.
- Archive downloads require authorization, checksums, path/compression safety, license review, and static inspection before plugin candidacy. Discovery and inspection do not execute third-party code.
- Checkpoints provide Chinese stage summaries and project-relative/absolute paths. Runtime handshakes, semantic reconciliation, Ruff no-new-debt checks, source/wheel/Skill/schema parity, and release audits protect workflow consistency.

### v0.33.2-v0.35.0 (2026-08-03) -- Cross-discipline retrieval and PDF evidence

- Search-switch propagation, candidate limits, and fallback topic anchors are corrected. Providers follow language and discipline, with content-based relevance and literature-role coverage.
- PDF parsing shares normalized documents, page/block evidence passages, context budgets, cost receipts, and work identity. pypdf is the default; MinerU is an authorized, quality-triggered upgrade. Self-hosted CPU/GPU support consists of endpoint contracts and deployment guidance.
- Release checks cover frozen discipline topics, PDF layouts, parser routes, wheels, install profiles, and provenance. Fixtures do not establish live search performance or scientific evidence.

### v0.32.1-v0.33.1 (2026-07-19 to 2026-07-25) -- Author completion, route binding, and extension ABI

- `v0.32.1-v0.32.2` introduce the capability truth matrix and author-completion shadow calibration; `v0.33.0` enables strict classification, with previewed category checks, impact scope, and suggested evidence references.
- Result Support v3 reads currently bound evidence; narrowing or rescue decisions bind the same checkpoint. Routing remains atomic for a whole checkpoint, with per-claim partitioning deferred.
- The `dpl.extension` ABI adds capabilities, entry-point discovery, workflow events, write scopes, and receipt contracts, defining Core, Pack, and community-extension boundaries.

### v0.31.1-v0.32.0 (2026-07-18) -- Framework organization and release documentation

- Module responsibilities, command entry points, and service boundaries are clarified, with generated CLI references, install profiles, command-risk documentation, and token/cost reports.
- Package, source, wheel, Skill, and release-manifest identity are aligned, supported by cross-platform/cross-discipline contract regression and completion audits.

### v0.28.1-v0.31.0 (2026-07-17 to 2026-07-18) -- Transactional evidence and precise revision

- Artifact DAGs, unified CommandSpec, write sets, and transaction receipts support precise stale propagation and explicit scientific-failure exit states.
- Final author completion uses preview/apply transactions, stable paragraph locators, and candidate hashes. Author details, citations, local revisions, and LaTeX outputs share release checks.
- Independent review, journal templates, cross-platform wheels, and release-hash contracts connect real evidence to the final PDF.

### v0.26.1-v0.28.0 (2026-07-16) -- Executable scientific semantics and recovery

- Executable contracts bind claims, cohorts, runs, estimands, statistical validation, and figure/panel semantics, distinguishing non-comparable results from evidence conflicts.
- Local invalidation, precise recovery, figure-code tracing, and reproducible review materials reduce unrelated stage reruns.

### v0.23.0-v0.26.0 (2026-07-12 to 2026-07-14) -- Project isolation and scientific execution

- Independent project workspaces, native recovery, and single-manuscript review are paired with wheel regressions that check installed runtime behavior.
- A controlled scientific runtime, runnable plugins, and thin MCP connect Agents to authoritative CLI contracts.
- Research blueprints confirm questions, claims, data, and methods together; statistical validation follows the task design, and template outputs cannot substitute for project evidence.

### v0.21.0-v0.22.8 (2026-07-11 to 2026-07-12) -- Scientific narrative and execution truth

- Paper Narrative Engine, section evidence packets, free composition, and Scientific Editor organize prose from stage code, formulas, figures, and literature.
- Figure/manuscript quality contracts and run/cohort semantics keep prose, outputs, and provenance consistent through the execution-truth and state layers.

### v0.18.1-v0.20.2 (2026-07-10 to 2026-07-11) -- Discipline plugins and result support

- Data connectors, method templates, review rules, manifest-driven plugin registration, and composite-discipline execution ledgers establish the capability layer.
- Result Support offers claim narrowing and data/method rescue. Project-local audits, AcademicForge/GitHub candidates, and third-party Skill conversion address capability gaps.
- Post-Results discipline and semantic review preserves explicit evidence boundaries for mock/fixture runs and capability-rescue records.

### v0.16.1-v0.17.7 (2026-07-07 to 2026-07-10) -- Free composition with evidence safeguards

- Section writing, figure contracts, evidence semantics, and regression checks support more natural prose while constraining what the results can support.

### v0.14.0-v0.15.12 (2026-06-24 to 2026-07-06) -- Discipline extension and citation audit

- Discipline plugins, data connectors, an evidence-first stage loop, citation auditing/repair, CLI hardening, and source-available usage boundaries extend the core framework.

### v0.11.0-v0.13.1 (2026-06-21 to 2026-06-24) -- Publication readiness and stage-owned code

- Publication-readiness checks and discipline-specific statistical rescue connect review feedback, data acquisition, method rebuilding, and stale-stage recovery. Stage-owned code and figure policies improve traceability.

### v0.7.0-v0.10.0 (2026-06-15 to 2026-06-18) -- Literature, observations, and scientific figures

- Zotero imports preserve user-selected references and provenance. Data/Methods writing uses observations rather than filling manuscript prose with commands and local paths.
- Scientific plotting, formulas, figure citations, and prose-quality checks enter the main workflow, with verifiable scientific content required in figures.

### v0.1.0-v0.6.0 (2026-06-09 to 2026-06-11) -- Paper projects and the research loop

- Project layout, literature search, journal templates, research plans, section writing, method execution, result validity, and LaTeX compilation form the initial workflow.
- Passport, artifact/hash tracking, stale propagation, integrity gates, review diagnosis, and revision routing establish the Draftpaper-loop cycle.
