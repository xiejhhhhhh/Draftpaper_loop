# Draftpaper-loop Manuscript Quality Architecture v0.21.1-v0.22.0

> Recovery rule: this Markdown file is the persistent source of truth for the active v0.21.1-v0.22.0 goal. After every context compaction, task resumption, interruption, or model handoff, read this file before taking any implementation action. Do not infer progress from conversation memory alone.

## Mandatory context recovery protocol

Run the following sequence after every context compaction or resume:

```powershell
Get-Content -Raw C:\Draftpaper_commercial\docs\superpowers\plans\2026-07-12-manuscript-quality-architecture.md
Set-Location C:\Draftpaper_commercial
git status -sb
git diff
```

Then continue from `Latest recovery checkpoint` and `Next executable steps`. Do not recreate completed work, discard uncommitted changes, or change the architectural decisions recorded here. Before declaring the goal complete, update this document with the final implementation status and verification results.

## Objective

Raise Draftpaper-loop output to functional parity with a strong researcher-authored manuscript. The target is not lexical similarity. Hard scientific correctness must be 100%; calibrated functional quality must be at least 0.95. The architecture must improve generation and reasoning, not merely add more post-generation gates.

## Core architecture

```text
approved evidence snapshot + research plan + plugin/run/figure traces + literature evidence
  -> Paper Narrative Engine
  -> section-specific evidence packs
  -> paragraph-level reasoning outlines
  -> Codex free-prose candidates
  -> paragraph-local Scientific Editor
  -> SectionWritingContract validation
  -> cross-section consistency + final citation audit + parity release
```

## Invariants

- Constraints protect facts, evidence boundaries, citations, formulas, figures, and traceability; they do not prescribe template sentences.
- No astronomy-, NDVI-, Transformer-, model-, metric-, field-, or fixed-figure-count assumptions may enter generic code.
- Deterministic writers are legacy/offline diagnostics only. A parity release requires validated Codex free-prose candidates for all core sections.
- Main and supporting figures must remain traceable to research-plan claims, plugins, runs, evidence, and review rules.
- Citation audit runs after final drafting and repairs claims before considering reference removal.

## Version route and live status

### v0.21.1 Paper Narrative Engine

Status: implemented and verified.

Outputs:
- `writing/paper_brief.json`
- `writing/figure_story_arc.json`
- `writing/manuscript_argument_map.json`
- `writing/section_claim_allocation.json`

Requirements:
- Parse true YAML as well as JSON.
- Group figures through `figure_group_id`, `figure_group`, `parent_figure_group`, `linked_main_figure`, storyboard and panel relationships.
- Bind supporting figures to stability, error, uncertainty, ablation, or boundary roles of a main finding.
- Every story group declares question, finding, evidence, and claim boundary.

### v0.21.2 Section-specific Evidence Packs

Status: implemented and verified.

Each section pack must declare allowed evidence IDs, cohort/unit/split/model/metric scope, allowed and forbidden facts, figure/table/formula/code-stage links, citation roles, and internal-language restrictions.

Section rules:
- Results: approved result evidence only; no literature citations.
- Introduction: problem, gap, hypothesis, and design; no result leakage.
- Data/Methods: data lifecycle, stage-owned code, formulas, and plugin execution.
- Discussion: finding-to-literature comparison matrix; no unsupported mechanism expansion.

### v0.21.3 Outline-first Codex free writing

Status: implemented and release-enforced.

- `prepare-section-outline` creates paragraph jobs, evidence, transitions, citation intent, and forbidden moves.
- `submit-section-draft` validates continuous Codex free prose.
- Outline labels never become manuscript prose.
- Any fallback section makes parity release `not_eligible`.

### v0.21.4 Results Synthesis Engine

Status: implemented and verified.

- Build finding blocks rather than one paragraph per PNG.
- Preserve scientific question, observed evidence, explicit comparisons, quantitative support, interpretation, and boundary.
- Main and appendix/supporting figures share one story group.
- Metrics bind by evidence ID, run ID, or figure/artifact links, never title-string guessing.

### v0.21.5 Introduction and Discussion argument matrices

Status: implemented and verified.

Outputs:
- Introduction gap matrix: known evidence -> unresolved gap -> paper response -> citation role.
- Discussion matrix: current finding -> comparable literature evidence -> agreement/difference -> mechanism -> boundary -> contribution/limitation.

Acceptance: paragraphs perform scientific reasoning rather than listing references or repeating Results.

### v0.21.6 Data/Methods lifecycle writing

Status: implemented and verified.

Data lifecycle:
- source and access boundary;
- raw-to-processed transformation;
- analysis cohort and subsets;
- feature/content groups;
- coverage, missingness, exclusions, and claim boundary.

Methods lifecycle:
- sample construction;
- data/feature/representation construction;
- model, estimator, or physical fit;
- objective and optimization;
- validation, metrics, ablation, uncertainty, and robustness;
- stage-owned code, formulas, plugin runs, and figure-code evidence.

Formula rules:
- Every core mathematical stage has a real traceable formula or explicitly records that it is deterministic and needs no formula.
- Variables, units/ranges, scientific meaning, and affected figures/results are explained.

### v0.21.7 Panel-aware Figure Narrative Contract

Status: implemented and verified.

Each panel declares:
- panel question;
- data subset and scientific unit;
- method output and comparison;
- required statistical check;
- chart grammar;
- expected conclusion and claim boundary;
- parent figure group.

Repair is panel-local. It diagnoses data, method, rendering, statistical, or claim mismatch and reruns only affected chains. It never silently replaces a failed scientific panel with a weaker substitute.

### v0.21.8 Style and Venue Adapter

Status: implemented and verified.

Learn only functional style signals:
- section length and information density;
- caption density;
- active/passive preference;
- numeric reporting and terminology-definition policy;
- Results/Discussion interpretation density;
- table and supplement usage.

Outputs affect prompts and editor suggestions only; they never override evidence or claim contracts and never copy exemplar wording.

### v0.21.9 Bounded Local Scientific Editor

Status: implemented and verified.

Maximum three paragraph-local rounds:
- paragraph scientific job;
- evidence, claim, figure, metric, formula, and citation binding;
- natural language and internal-artifact cleanup.

The editor cannot invent unbound values, delete references to solve citation audit issues, or rewrite a whole section because of one local defect. Every change records paragraph, evidence, reason, and iteration.

### v0.22.0 Cross-discipline regression and calibrated release

Status: implemented and verified across three discipline combinations.

Hard correctness: 100%.
- Same approved evidence version across metrics, numbers, models, cohort, unit, split, figures, formulas, and manuscript.
- No source/observation confusion, mixed-dimension plots, or unsupported values.
- Citation audit runs after final manuscript.

Functional quality target: >= 0.95 using calibrated weights:
- scientific story and main-figure narrative: 0.20;
- Results evidence interpretation and comparison: 0.20;
- reproducible Data/Methods expression: 0.15;
- Introduction problem, gap, and contribution: 0.15;
- Discussion comparison, mechanism, limitation, and innovation: 0.15;
- figure readability, panel logic, and captions: 0.10;
- prose naturalness and cross-section coherence: 0.05.

Calibration fixtures:
- astronomy + machine learning;
- geography + machine learning;
- bioinformatics / medicine.

Fixtures validate generality only. Generic code must not contain their figure counts, metrics, model names, fields, prose, or conclusions.

## Verification log

- 2026-07-12: Results-focused regressions initially passed with 13 tests.
- 2026-07-12: Narrative/composer/results/manuscript-quality focused suite passed with 22 tests.
- 2026-07-12: Expanded architecture-focused suite passed with 24 tests.
- 2026-07-12: Initial full repository suite passed with 389 tests in 152.94 seconds.
- 2026-07-12: Final full repository suite passed with 394 tests in 148.26 seconds after adding deterministic-fallback, citation-ordering, cross-discipline, CLI-import, and package-API coverage.
- 2026-07-12: Discipline/plugin regression subset passed with 17 tests.
- 2026-07-12: Three-domain integrated manuscript-architecture regression passed with 3 tests.
- 2026-07-12: Final focused architecture suite passed with 29 tests.
- 2026-07-12: `py_compile`, CLI help visibility, two command-level smoke executions, and 12 package-level API exports passed.
- 2026-07-12: Citation-audit ordering was checked against the actual report writers: both final citation audit and section validation reports use `generated_at`.
- Transient full-suite logs were removed after verification and are not part of the release diff.

## Latest recovery checkpoint

Implemented in the working tree:
- v0.21.1 Paper Narrative Engine with true YAML parsing, paper brief, figure story arc, manuscript argument map, and claim allocation.
- v0.21.2 section evidence packs carrying evidence boundaries, argument matrices, lifecycle bindings, formula/plugin/code traces, and style guidance.
- v0.21.3 outline-first Codex free-writing preparation and validated draft submission; deterministic fallback remains ineligible for parity release.
- v0.21.4 Results synthesis based on finding blocks, main/supporting figure relationships, and explicit evidence/run binding.
- v0.21.5 Introduction gap matrix and Discussion finding-comparison matrix.
- v0.21.6 Data/Methods lifecycle reconstruction and formula contracts with variable, unit/range, scientific-meaning, stage, and result links.
- v0.21.7 semantic panel contracts and panel-local repair preparation.
- v0.21.8 venue writing contract and functional style profile.
- v0.21.9 bounded paragraph-local Scientific Editor preparation and revision recording.
- v0.22.0 calibrated functional-quality scoring and independent hard scientific-correctness checks.

Verified commands and public CLI surfaces include:
- `build-paper-narrative`
- `prepare-section-outline`
- `build-results-synthesis`
- `build-argument-matrices`
- `build-section-lifecycles`
- `build-panel-contracts`
- `prepare-panel-repair`
- `resolve-venue-writing-style`
- `prepare-scientific-editor`
- `record-scientific-editor-revision`
- `assess-functional-quality-release`
- `submit-section-draft`
- `prepare-section-writing`

Expected uncommitted implementation paths:
- modified: `README.md`, `README.zh-CN.md`, `draftpaper_cli/__init__.py`, `draftpaper_cli/cli.py`, `draftpaper_cli/manuscript_composer.py`, `draftpaper_cli/paper_quality_parity.py`, `draftpaper_cli/results.py`, `pyproject.toml`, `tests/test_paper_quality_parity.py`;
- new: `draftpaper_cli/paper_narrative.py`, `draftpaper_cli/structured_io.py`, `draftpaper_cli/writing_architecture.py`, `tests/test_paper_narrative.py`, `tests/test_manuscript_architecture_cross_discipline.py`, and this plan.

Do not recreate the completed architecture and do not discard unrelated user changes.

## Final implementation checkpoint

All planned v0.21.1-v0.22.0 architecture items are implemented in the working tree and verified. Remaining work is release hygiene, not architecture implementation:

1. Remove transient test logs.
2. Inspect `git diff --check`, `git status -sb`, and the final diff summary.
3. Do not commit or push unless the user explicitly requests it.
4. If work resumes after compaction before commit, repeat the mandatory recovery protocol at the top of this document.
