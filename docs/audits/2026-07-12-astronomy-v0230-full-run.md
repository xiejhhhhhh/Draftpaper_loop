# Draftpaper-loop v0.23.0 Astronomy Full-Run Audit

Date: 2026-07-12

## Scope

This audit runs the current Draftpaper-loop against an isolated copy of an astronomy and machine-learning paper project. The original manuscript PDF remains the comparison baseline and is not overwritten.

- Test project: `time-aware-transformer-classification-of-ep-wxt-flaring-sources-using-long-term_v0230_full_run`
- Baseline manuscript: the original project's `latex/main.pdf`
- Test objective: regenerate the research contracts, data/method evidence chain, figures, manuscript, citation audit, and PDF; then compare scientific and writing quality.
- Token policy: report observable model input/output tokens for free-writing stages. Local deterministic CLI stages use zero model tokens. Hidden reasoning and platform overhead are not estimated or presented as measured usage.

## Issues Observed During Execution

### Recording policy

This audit preserves intermediate failures even when a later repair allows the run to continue. Each issue records the stage boundary, observed behavior, user-visible or scientific impact, and the framework-level correction. A later successful rerun does not erase the original failure. Project-specific adapters may verify a proposed correction, but the public fix must remain discipline-neutral and must not depend on private astronomy paths, filenames, or values.

The issue lifecycle used in this audit is:

- `observed`: reproduced in the full workflow;
- `protected`: an existing gate correctly rejected invalid output, but the upstream producer still needs correction;
- `corrected_in_worktree`: a generic framework fix and focused regression test exist locally;
- `verified_in_project`: the corrected path has passed this isolated project run;
- `pending_general_regression`: broader cross-discipline regression is still required.

### ASTR-001: Plugin sufficiency and code generation form a circular dependency

- Stage: capability audit -> figure contract -> analysis code generation
- Severity: blocking
- Observed behavior: plugin sufficiency runs before the Agent can add project-local method code. Missing method code blocks the figure contract, while the blocked figure contract prevents `generate-analysis-code` from creating that code.
- Scientific risk: a genuinely new topic cannot reach the dynamic method-design path even when its data and research contract are otherwise adequate.
- Required correction: distinguish `unavailable_after_exhaustive_rescue` from `project_method_implementation_required`. The second state must open a bounded Agent code-generation task and only block after project-local implementation, registry lookup, AcademicForge lookup, and research-code search all fail.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The project-local capability audit can now bind stage-owned method code with hashes and permit controlled code generation. The remaining framework work is to make the rescue sequence explicit in `status`/`run-pipeline` for a completely new project, so plugin sufficiency is a routing decision rather than a pre-implementation dead end.

### ASTR-002: Classification storyboard hard-coded astronomy-specific physical variables

- Stage: `generate-plan`
- Severity: blocking
- Observed behavior: every classification project received a third main-figure contract requiring `hardness`, `flux`, and `class_label`, even when hardness-ratio data were not present.
- Scientific risk: the workflow either blocks a valid project or encourages a spectral-count proxy to be mislabeled as a physical hardness ratio.
- Correction applied in the current working tree: use a spectral-feature role and class label rather than inventing hardness and flux. Physical variables remain valid only when the project inventory or user plan explicitly provides them.

### ASTR-003: Project-local capability aliases were incomplete

- Stage: `audit-project-capabilities`
- Severity: high
- Observed behavior: existing `history_lc` data and baseline, class-balance, and feature-diagnostic scripts were reported missing because the audit recognized only literal role names.
- Risk: false plugin gaps trigger unnecessary rescue and can prevent use of verified local scientific code.
- Correction applied in the current working tree: add conservative aliases for light curves, class-balance diagnostics, feature-space diagnostics, and baseline models. Bindings still require a stage-owned file and SHA-256 evidence.

### ASTR-004: A copied legacy project initially reports pervasive artifact drift

- Stage: first rerun in an isolated project copy
- Severity: high for regression testing; migration-related for users
- Observed behavior: the copied passport retained the original artifact baseline. New stage outputs then produced dozens of drift events; synchronizing after running stages marked the newly completed stages stale again.
- Risk: expensive work can be invalidated if migration/snapshot rebasing is performed after rather than before the first new-version command.
- Required correction: provide an explicit `clone-project-for-regression` or `rebase-project-passport` command that validates the copy, records its origin, and establishes the new baseline before any stage runs.

### ASTR-005: Previous figure metadata can contaminate a pre-execution contract check

- Stage: `assess-figure-contracts`
- Severity: high
- Observed behavior: when a project already contains old `figure_metadata.json`, the new pre-code-generation gate may validate that metadata against a newly generated contract even though the current method run has not executed.
- Risk: stale figures can create misleading semantic failures or, if metadata happens to align superficially, contaminate the new evidence version.
- Required correction: consume produced figure metadata only when it is bound to the current run and evidence snapshot. Otherwise classify it as historical input and ignore it during the pre-execution contract check.

### ASTR-006: Generic classification planning can select semantically weak figure inputs

- Stage: `plan-figures`
- Severity: high
- Observed behavior: the planner selected one broad history-token table for multiple heterogeneous figure groups and proposed generic axes even when dedicated baseline, ablation, prediction, spectral, and uncertainty tables existed.
- Scientific risk: figures may be valid PNG files but fail to answer their research questions.
- Required correction: resolve one evidence table per figure contract from declared variable roles and run outputs. Main figures must not fall back to the globally largest or first readable table.

### ASTR-007: Installed data plugins can be selected while remaining plan-only

- Stage: `execute-data-plugins`
- Severity: medium
- Observed behavior: a connector could be selected with `validation_level=plan_only`, producing a `prepared_for_project_execution` ledger event with no output hashes and no scientific evidence.
- Risk: binding count can look substantial while executable scientific coverage remains unchanged.
- Current protection: v0.23.0 does not treat these events as established scientific evidence.
- Required correction: user-facing summaries should separate planned bindings, fixture-executed bindings, and project-validated bindings instead of reporting one undifferentiated count.

### ASTR-008: Capability resolution consumed a previous result storyboard

- Stage: `generate-plan` -> `assess-plugin-sufficiency`
- Severity: blocking
- Observed behavior: the new research plan correctly replaced an unavailable hardness-ratio requirement, but `research_capability_contract.json` was rebuilt from the previous run's `results/figure_storyboard.json` and stale figure contracts.
- Scientific risk: data, methods, figures, and manuscript writing can silently belong to different research-plan versions.
- Correction applied in the current working tree: `research_plan/figure_storyboard.json` is the canonical planning source. Existing result contracts may override it only when they cover exactly the current storyboard figure IDs.

### ASTR-009: Project-local audit skipped `execution_required` capabilities

- Stage: `assess-plugin-sufficiency` -> `audit-project-capabilities`
- Severity: blocking
- Observed behavior: code-generator plugins correctly produced `execution_required`, but the local capability audit ignored that state and therefore never checked whether the project already contained an executable implementation.
- Risk: local research code cannot close a plugin gap, leaving the workflow in the code-generation circular dependency described in ASTR-001.
- Correction applied in the current working tree: data and method requirements in `execution_required` now enter the same stage-owned file and SHA-256 audit as missing and partially covered requirements.

### ASTR-010: Pre-code-generation gate required post-generation method evidence

- Stage: `assess-figure-contracts`
- Severity: blocking
- Observed behavior: every method-backed main figure was rejected because `method_source_status` was not already `implemented`, even when the audited plugin trace decision was `ready_for_codegen`.
- Risk: the workflow cannot enter its own controlled analysis-code generation stage.
- Correction applied in the current working tree: an audited `ready_for_codegen` trace permits code generation. Implemented code, current-run outputs, semantic metadata, and hashes remain mandatory after execution.

### ASTR-011: Old successful run manifest activated stale figure metadata

- Stage: pre-execution `assess-figure-contracts`
- Severity: blocking
- Observed behavior: a historical `run_manifest` with `status=success` caused stale metadata to be treated as current even though its declared figure paths did not match the new contracts.
- Risk: evidence from different runs can be mixed or can falsely block a valid rerun.
- Correction applied in the current working tree: a run is current for figure-contract purposes only when it declares every current main-contract figure path. Metadata is ignored unless its path is declared by that run.

### ASTR-012: Generic execution passed structure checks but generated scientifically invalid figures

- Stage: generated analysis execution -> post-run semantic figure contract
- Severity: blocking
- Observed behavior: the generic runtime selected one index table for all figures, plotted `source_id` against `obs_id`, mixed row counts and dimensionless scores on one metric axis, and replaced verified 0.8667/0.8053/0.8205 model evidence with a 0.5002 majority-class score.
- Protection that worked: the post-run semantic contract rejected identifier-versus-identifier science and mixed dimensions.
- Required correction: resolve each figure to its own run-aware evidence table; generic `metrics.csv` must never outrank verified baseline, Transformer, ablation, prediction, and uncertainty outputs.

### ASTR-013: Figure semantic roles were inferred from temporary selected columns

- Stage: `plan-figures` -> semantic contract creation
- Severity: blocking
- Observed behavior: all main figures inherited `history_detnam` because the generic planner selected it as an axis from one table, even when the research contract required class support, model comparison, ablation, or uncertainty.
- Correction applied in the current working tree: semantic roles now derive from plot grammar and research-plan data roles. Workflow, class distribution, model comparison, ablation, uncertainty, and feature relationships receive different role contracts; temporary x/y choices cannot redefine the scientific question.

### ASTR-014: Method verification required fake axes for workflow schematics

- Stage: `verify-methods`
- Severity: medium
- Observed behavior: a workflow schematic was rejected unless metadata claimed axes and axis labels.
- Risk: producers are encouraged to write inaccurate metadata merely to satisfy a visual checklist.
- Correction applied in the current working tree: `workflow_schematic` is exempt from axis requirements in both method verification and core-evidence review, but still requires a valid image, publication dimensions, textual elements, statistics, interpretation, and semantic contract fields.

### ASTR-015: Substring and narrative leakage corrupted figure semantics

- Stage: semantic figure contract
- Severity: high
- Observed behavior: `spectral_features` was classified as spatial because it contains the character sequence `ra`; a baseline-versus-model figure was classified as ablation because its expected-finding prose mentioned ablation.
- Risk: semantically correct figures fail for lexical accidents, while titles and intended plot types lose authority.
- Correction applied in the current working tree: short coordinate aliases such as RA/Dec require exact matches, and metric-summary grammar is selected from the explicit title/group rather than downstream narrative prose.

### ASTR-016: Result validity averaged metrics across different models

- Stage: `assess-result-validity`
- Severity: high
- Observed behavior: the resolver selected the correct verified metrics table but averaged logistic baseline, random-forest baseline, full Time2Vec Transformer, and no-history Transformer macro-F1 values into one observed value (0.8353).
- Scientific risk: the validity decision has no single model identity and can hide the fact that the transparent baseline (0.8667) outperforms the full Transformer (0.8053), while the no-history variant reaches 0.8205.
- Required correction: primary-metric resolution must require an explicit `model_id` or select the research-plan primary model. Cross-model aggregation belongs in a comparison artifact, not the scalar validity field.

### ASTR-017: Core-evidence resume invalidated its own confirmation

- Stage: `checkpoint` -> `resume` -> `status`
- Severity: blocking
- Observed behavior: resume promoted an evidence snapshot and updated `core_evidence_report.json`, but did not refresh the artifact passport. The next read-only status classified that internal update as external drift.
- Risk: a successful human confirmation immediately reopens the evidence chain and can create an endless confirmation loop.
- Correction applied in the current working tree: core-evidence resume refreshes the passport after writing the promoted snapshot ID and confirmation metadata, before status is evaluated.

### ASTR-018: The recommended next action violates its own stage precondition

- Stage: resumed core evidence -> `status`/next-action routing -> `verify-methods`
- Severity: blocking
- Observed behavior: after core-evidence confirmation resumed successfully and `status` reported `pipeline_state=ready`, both commands recommended `verify-methods`. Executing that exact recommendation failed immediately because `method_plan` was stale and `verify-methods` requires a non-stale method plan.
- User-visible impact: the workflow presents an apparently valid recovery command that cannot run, leaving users to infer an undocumented upstream rerun and weakening trust in pipeline guidance.
- Required correction: next-action resolution and command precondition checks must consume the same stage-state graph. If `method_plan` is genuinely stale, route to the earliest required planning command; if confirmation should not have invalidated it, correct stale propagation instead. Add a regression test that every emitted next-action command is executable under the reported passport state.
- Current lifecycle: `observed`; root-cause inspection pending.

### ASTR-019: Core evidence can pass while its scientific dependencies are stale

- Stage: result support -> `assess-core-evidence` -> checkpoint/resume
- Severity: blocking
- Observed behavior: core evidence passed and was human-confirmed even though the project state still marked the research plan, data, method plan, figure plan, methods, and result validity as stale. The assessment verified artifact content but did not enforce the declared dependency-state contract.
- Scientific risk: a polished set of figures can be promoted from artifacts that do not belong to one current research-plan/data/method version. Human confirmation then gives an inconsistent evidence bundle false authority.
- Required correction: `assess-core-evidence` and `resume` must require all declared scientific dependencies to be current or explicitly frozen under the same evidence snapshot. Existing files are not sufficient. Add a regression in which valid-looking figure files coexist with one stale upstream scientific stage and confirmation is rejected.
- Current lifecycle: `observed`; generic dependency validation pending.

### ASTR-020: A historical Results review can override a newly confirmed evidence snapshot

- Stage: core-evidence resume -> next-action routing
- Severity: blocking
- Observed behavior: an earlier `result_discipline_review_report.json` matched the unchanged old `results.tex` hash and retained `decision=repair_required`. After a new figure/evidence snapshot was confirmed, the orchestrator still treated this historical review as current and routed to its old `verify-methods` recommendation.
- Scientific risk: review findings, Results prose, figures, and evidence snapshots can come from different versions. A text hash alone cannot prove that a Results review belongs to the current scientific evidence.
- Required correction: bind Results review reports to the accepted Results hash, promoted evidence snapshot ID, result-manifest hash, and figure-plugin-trace hash. Ignore or mark stale any report missing those current bindings, then route to `inventory-results` and new Results writing/review.
- Current lifecycle: `observed`; snapshot-aware review routing pending.

### ASTR-021: Successful CLI stage writes are immediately reported as external artifact drift

- Stage: any mutating stage command -> next `status`
- Severity: blocking
- Observed behavior: a successful official `generate-plan` updated the research artifacts, project metadata, and dependent stage manifests. The immediately following read-only `status` reported 24 drifted artifacts and recommended `sync-artifact-stale`, treating the CLI's own writes as external edits.
- User-visible impact: following the documented command sequence creates a drift loop. Synchronization can then mark the newly generated stage and its downstream chain stale, which explains several apparently contradictory states observed earlier in this run.
- Required correction: every successful state-owning CLI command must atomically refresh or append the passport baseline after all project and manifest writes complete. Drift detection must remain reserved for changes made outside the command transaction. Add an integration test that runs a mutating command followed immediately by `status` and asserts `pipeline_state != drift_detected`.
- Current lifecycle: `observed`; CLI transaction/passport integration pending.

### ASTR-022: Substage routing treats a historical output file as current

- Stage: `collect-method-plan` -> method blueprint -> method feasibility
- Severity: high
- Observed behavior: after the method plan and requirements were regenerated, a blueprint file from the previous run still existed. The orchestrator checked only file existence and recommended `assess-method-feasibility`, skipping regeneration of the blueprint against the new requirements.
- Scientific risk: feasibility, code generation, formulas, and figures can be based on a method blueprint from a different research-plan version.
- Required correction: multi-command stages must route from the current stage manifest or explicit input/output hashes, not bare path existence. `prepare-method-blueprint` remains required until the current method-plan manifest declares its blueprint artifacts.
- Current lifecycle: `observed`; method-plan substage correction pending, with the same pattern to be audited in data and writing substages.

### ASTR-023: Plugin sufficiency can be reused after the capability contract changes

- Stage: regenerated research plan/capability contract -> figure contracts -> code generation
- Severity: blocking
- Observed behavior: the new research capability contract was generated, but an older passing `plugin_sufficiency_report.json` remained on disk. Because routing checked only report existence and decision, it skipped the new sufficiency assessment and proposed analysis code generation.
- Scientific risk: data and method plugins validated for an earlier set of claims and figures can be treated as support for a changed research plan.
- Required correction: bind every sufficiency report to the SHA-256 of the exact research capability contract it assessed. A missing or mismatched hash makes the report historical and routes back to `assess-plugin-sufficiency`.
- Current lifecycle: `observed`; contract-hash binding pending verification.

### ASTR-024: A historical project-local capability audit can skip re-auditing new plugin gaps

- Stage: current plugin sufficiency failure -> project-local capability audit
- Severity: blocking
- Observed behavior: the current sufficiency assessment reported 26 core data/method gaps, but an audit file from the previous assessment already existed. Routing therefore skipped `audit-project-capabilities` and proposed external rescue immediately.
- Scientific risk: usable project-local labels, feature tables, and method implementations are ignored, while users are sent into unnecessary plugin mining or manual intervention.
- Required correction: bind the project-local audit to both the research capability contract hash and the exact sufficiency assessment generation ID. Any mismatch requires a fresh local audit before external rescue.
- Current lifecycle: `observed`; sufficiency-to-audit binding pending verification.

### ASTR-025: Stale propagation and promoted evidence lifecycle are disconnected

- Stage: research-plan regeneration -> analysis-code regeneration
- Severity: blocking
- Observed behavior: regenerating the research plan correctly marked downstream code and figure stages stale, but the previous human-approved evidence snapshot remained promoted. The later `generate-analysis-code` command then refused to overwrite promoted evidence.
- User-visible impact: the workflow permits an upstream scientific change and only much later reveals that the old confirmation should have been reopened, leaving the user in a partially updated state.
- Required correction: when the earliest required stage can alter scientific evidence, `status`/`run-pipeline` must route first to explicit `reopen-core-evidence`. The old snapshot is archived, not silently deleted; only then may data, methods, figures, or result evidence regenerate.
- Current lifecycle: `observed`; reopen-aware routing pending project verification.

### ASTR-026: A downstream semantic recheck invalidates its verified producer stages

- Stage: `assess-result-validity` -> internal figure-contract semantic recheck
- Severity: blocking
- Observed behavior: result validity correctly re-ran rendered figure semantics, but the shared figure-contract function also marked the figure-contract stage draft. Normal downstream propagation then marked code and methods stale, even though the recheck had not changed the plan, code, or figures.
- User-visible impact: a successful validation command sends the pipeline backwards to code generation, creating another loop around already verified outputs.
- Required correction: separate report-only post-run semantic validation from state-changing pre-code contract assessment. Result validity may refresh semantic reports but must not propagate producer-stage stale state unless the contract itself changes.
- Current lifecycle: `observed`; non-propagating semantic recheck pending project verification.

### ASTR-027: Result support offers a downgrade command that has no eligible claim

- Stage: `assess-result-support` -> downgrade route
- Severity: blocking
- Observed behavior: all five bounded claim assessments were marked supported, but result validity was `conditional_pass` only because no numerical acceptance threshold was configured. Result support nevertheless required a route choice and advertised `apply-result-downgrade`; that command then failed because no claim was partially supported or unsupported.
- Required correction: conditional validity alone does not imply claim overreach. Require downgrade/supplement only when an individual claim is partial/unsupported or technical validity fails. Every advertised route command must have an eligible target under the same report.
- Current lifecycle: `observed`; shared decision semantics pending verification.

### ASTR-028: Result support ignores run-aware evidence and reuses historical generic metrics

- Stage: result evidence resolution -> result support
- Severity: high
- Observed behavior: the resolver correctly preserved the four model F1 values, but the support checkpoint still reported the historical generic `F1=0.500167` and stale cohort counts from an old result manifest.
- Scientific risk: claim support can be decided from a different run than result validity and the figures.
- Required correction: result support must consume `resolved_result_evidence.json` with model-qualified metric keys and ignore a stale result manifest. Generic run-manifest scalars may be fallback context only; they cannot override run-aware model evidence.
- Current lifecycle: `observed`; resolver-to-support binding pending project verification.

### ASTR-029: Scientific decision exit code 1 leaves managed report writes uncommitted

- Stage: any gate/checkpoint command that writes a report and returns nonzero for a non-passing decision
- Severity: high
- Observed behavior: `assess-result-support` intentionally wrote a complete route-decision report and returned exit code 1. The CLI transaction wrapper refreshed passports only for exit code 0, so the next status would treat the managed report and stage updates as external drift.
- Required correction: passport transaction outcome and scientific gate outcome are separate dimensions. If a CLI command starts from a clean baseline, all managed writes must be recorded even when its scientific decision is failed, partial, or requires user action; the nonzero exit code remains visible to automation.
- Current lifecycle: `observed`; nonzero managed-transaction recording pending verification.

### ASTR-030: A stale result manifest bypasses inventory and contaminates the writing packet

- Stage: core-evidence resume -> Results writing preparation
- Severity: blocking
- Observed behavior: the writing coordinator checked only whether `results/result_manifest.yaml` existed. A stale manifest from the copied project therefore bypassed `inventory-results`, and historical generic figure groups entered the new narrative packet.
- Required correction: section preconditions require both the artifact and a non-stale owning stage. Results must run current inventory before free-writing preparation; the same rule applies to Data and Methods contexts.
- Current lifecycle: `observed`; stage-aware section preconditions pending verification.

### ASTR-031: Section preparation can emit an empty Scientific Evidence Registry

- Stage: `prepare-section-writing`
- Severity: blocking
- Observed behavior: the packet read `writing/scientific_evidence_registry.json` if present but never built it when absent, yielding an empty registry despite current resolved result evidence.
- Scientific risk: free writing receives metrics without the binding/conflict surface intended to prevent cohort, model, and split hallucinations.
- Required correction: section packet preparation must build and conflict-check the registry transactionally before creating narrative, outline, or candidate instructions.
- Current lifecycle: `observed`; registry build integration pending verification.

### ASTR-032: Panel writing contracts use historical generic groups instead of current semantic contracts

- Stage: Results/Discussion writing preparation
- Severity: high
- Observed behavior: panel contracts preferred broad legacy `figure_groups` and failed to merge current rendered metadata. The six verified figures were marked repair-required, and unrelated generic groups such as feature distribution and validation summary were added.
- Required correction: current `figure_contracts.json` is the canonical panel source. Merge by figure/storyboard ID with rendered metadata and require the scientific question, method output, chart grammar, expected conclusion, and claim boundary; do not invent legacy panels.
- Current lifecycle: `observed`; semantic-contract-first panel preparation pending verification.

### ASTR-033: Result inventory admits historical artifacts outside the current run

- Stage: `inventory-results` -> Results writing preparation
- Severity: high
- Observed behavior: the current method run declared six figures and one scientific result table, but inventory enumerated every retained file under `results/figures` and `results/tables`, producing 16 figures and 10 tables.
- Scientific risk: legacy generic plots and metrics from different evidence versions enter the current story, weakening run provenance and encouraging contradictory interpretation.
- Correction applied in the current working tree: when a successful run declares outputs, inventory now intersects declared figures with current rendered metadata and accepts only declared result tables. Directory enumeration remains a compatibility fallback only when no run-bound inventory exists.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The rerun inventories exactly six current-run figures and `verified_model_metrics.csv`; historical files remain on disk but are excluded from the manuscript inventory.

### ASTR-034: Section evidence packets embed oversized nested ledgers

- Stage: `prepare-section-writing`
- Severity: high for cost and writing quality
- Observed behavior: the Results packet reached approximately 733,807 characters and 45,726 words because full registries, plugin execution ledgers, manifests, and overlapping narrative structures were embedded together.
- User-visible impact: avoidable token cost, slower composition, and reduced attention to the six-figure scientific story.
- Required correction: build a section-specific compact evidence slice containing only relevant evidence records, claims, figure metadata, paragraph jobs, citation roles, and writing constraints. Preserve full ledgers on disk for audit, but reference them by hash/path rather than copying them into every writing prompt.
- Correction applied in the current working tree: section packets now carry a section-filtered registry, compact run/result references, the active section lifecycle only, and prose-job allocations without duplicate numeric facts. Full ledgers remain addressable through explicit audit-source paths.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The Results packet decreased from approximately 551,607 to 116,048 characters while retaining all 60 section-relevant evidence records, six current figures, and one current result table.

### ASTR-035: Introduction claim allocation leaks observed Results language

- Stage: paper narrative -> Introduction writing preparation
- Severity: high
- Observed behavior: figure-level observed claims such as one model outperforming another were copied into the Introduction allocation and merely relabeled as a research-question role.
- Scientific risk: the Introduction can reveal the final comparison before the study question and methods are established, creating hindsight framing and inconsistency with the evidence-first section contract.
- Correction applied in the current working tree: Introduction allocations now use each figure group's scientific question and an explicit unresolved-question boundary. Results retains observed claims; Discussion retains interpretation and comparison claims.
- Current lifecycle: `corrected_in_worktree`; focused regression and generated Introduction verification pending.

### ASTR-036: Numeric claim validation leaks Python sets into managed JSON

- Stage: `submit-section-draft`
- Severity: blocking
- Observed behavior: the Results candidate reached quantitative binding validation, but `scope_signals` contained Python `set` values. Writing the claim-binding report failed with `Object of type set is not JSON serializable` before a scientific decision was returned.
- User-visible impact: a valid or repairable free-writing candidate cannot enter the editor lifecycle, and the CLI exposes an implementation error rather than actionable claim feedback.
- Correction applied in the current working tree: scope signals remain sets during matching but are converted to sorted lists at every report boundary; a serialization regression test covers the public validation payload.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. Results resubmission reached the scientific gates and produced a serializable 25-claim binding report.

### ASTR-037: Results quality contract ignores run-aware resolved metrics

- Stage: Results candidate quality assessment
- Severity: blocking
- Observed behavior: the quality contract read only `methods/run_manifest.yaml.metrics`, which is intentionally empty for the verified storyboard run, while the validated model metrics reside in `results/resolved_result_evidence.json`. Correct macro-F1 claims were therefore classified as untraceable and evidence fidelity fell to zero.
- Correction applied in the current working tree: the narrative contract now consumes run-aware resolved metrics first, preserving model, cohort, split, and run identifiers, with run-manifest scalars retained only as a legacy fallback.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The same Results candidate now receives evidence fidelity 1.0 and total narrative-quality score 1.0.

### ASTR-038: Quantitative binding rejects rounded and figure-derived current-run facts

- Stage: Results quantitative claim binding
- Severity: blocking
- Observed behavior: normal four-decimal reporting was compared with an overly strict relative tolerance; metric-family aliases omitted names such as `no_current_f1_macro`; duplicate historical summaries created ambiguity; and current figure statistics lacked complete run/split bindings.
- Correction applied in the current working tree: matching now respects the reported decimal precision, recognizes metric-family suffixes and `dimensionless_score`, prefers the current validated run, expands nested figure statistics, and binds current figure evidence to its run and split. Count-like figure statistics are explicitly typed as counts rather than scores.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. All 25 quantitative claims in the Results candidate are bound and the candidate passed submission.

### ASTR-039: Scientific Editor treats LaTeX figure paths as prose leakage

- Stage: `prepare-scientific-editor`
- Severity: blocking for acceptance
- Observed behavior: six valid figure environments were parsed as prose paragraphs and flagged because `includegraphics` necessarily contains a project-relative result path.
- User-visible impact: a Results section that correctly embeds its scientific figures is sent into six meaningless local revisions.
- Correction applied in the current working tree: the paragraph-local editor removes figure and table environments before prose segmentation. Section contract validation continues to inspect actual prose while allowing project-relative LaTeX asset arguments.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The editor no longer emits tasks for the six LaTeX figure environments.

### ASTR-040: Writing outline assigns a pre-model diagnostic to model comparison

- Stage: figure semantics -> paper narrative -> Scientific Editor
- Severity: high
- Observed behavior: the third figure is a relationship/PCA diagnostic before model fitting, but a mismatched planned question containing the word `baseline` caused its paragraph job to become `model_comparison`. Correct pre-model interpretation was then flagged as weak alignment.
- Scientific risk: the editor can push a scientifically correct paragraph toward the wrong rhetorical and evidentiary role.
- Correction applied in the current working tree: rendered plot grammar now propagates through the result manifest and takes precedence when assigning narrative jobs. When a pre-model grammar conflicts with a model-performance question, the writing question is recalibrated to feature-space structure without changing the approved observed evidence.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The regenerated story arc assigns the rendered relationship diagnostic to `premodel_signal` and recalibrates its writing question.

### ASTR-041: Scientific Editor aligns paragraph jobs by raw paragraph position

- Stage: Scientific Editor paragraph-local review
- Severity: high
- Observed behavior: the editor assumed prose paragraph N corresponded to outline job N. Opening and transition paragraphs shifted the mapping, so a feature-space paragraph was checked against a later model-comparison job even after the semantic role was corrected.
- User-visible impact: richer, more natural scientific prose is penalized simply because it contains useful transitions beyond the minimum outline length.
- Correction applied in the current working tree: paragraph jobs are matched by normalized Figure/Table references. Unreferenced opening and transition paragraphs remain subject to prose and internal-language checks but are not forced into an unrelated positional job.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The accepted Results candidate includes opening and transition paragraphs without positional false positives.

### ASTR-042: Historical generic figure groups collapse distinct current main-figure jobs

- Stage: result manifest -> figure story arc -> section outline
- Severity: high
- Observed behavior: Figures 4--6 retained the legacy generic group `metric_summary`, so baseline comparison, ablation, and uncertainty were represented as one model-comparison paragraph job despite having separate current storyboard IDs and semantic contracts.
- Scientific risk: component attribution and error analysis lose their independent narrative roles, reproducing the shallow template prose the narrative engine is intended to replace.
- Correction applied in the current working tree: current main figures use their storyboard IDs as narrative units; appendix figures still attach to an explicit parent/supporting group. Paragraph matching also accepts multiple jobs when one paragraph cites both a figure and a table.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The regenerated Results outline preserves separate study-boundary, pre-model, model-comparison, component-attribution, and uncertainty jobs; the Scientific Editor returns no tasks.

### ASTR-043: Post-Results discipline review reuses stale plugin events and metric aliases

- Stage: `review-results-with-discipline-rules`
- Severity: blocking for downstream writing
- Observed behavior: repeated plugin event IDs caused the figure-quality scorer to select the oldest ledger event; current figure metadata and images were then compared with historical output hashes. The review runtime also treated `score` and `dimensionless_score` as mixed dimensions and searched metric names, rather than model identities, for baseline and ablation evidence.
- User-visible impact: accepted current figures and a Results section scoring 1.0 are routed backward to `verify-methods` for repairs that have already been completed.
- Correction applied in the current working tree: ledger resolution uses the latest matching event, run-hashed figure metadata plus the rendered figure can bind reported statistics, plugin data-role IDs participate in semantic alignment, equivalent score dimensions are canonicalized, and baseline/ablation/run evidence is discovered from run-aware model records. Results semantic audit now reads the canonical resolved-evidence file.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The refreshed six-figure trace resolves current events and the complete post-Results discipline review now passes with Results narrative score 1.0.

### ASTR-044: Introduction packet drops consolidated literature summaries

- Stage: `prepare-section-writing --section introduction`
- Severity: blocking for evidence-based writing
- Observed behavior: 12 retained references exist in `references/literature_items.json` with HTML literature summaries, but the narrative layer only searched for one-JSON-file-per-paper summaries. The Introduction packet therefore reported zero reference items.
- Scientific risk: free writing either omits the literature basis or invents citation placement without the available evidence summaries.
- Correction applied in the current working tree: reference loading now consumes the consolidated literature item list, including BibTeX key, deep summary or abstract, and search contexts, then merges and deduplicates legacy per-paper JSON summaries.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The regenerated Introduction packet contains all 12 retained literature summaries and the accepted section uses them through role-specific citations.

### ASTR-045: Data writing packet cannot access verified cohort counts

- Stage: `build-data-context` -> `prepare-section-writing --section data`
- Severity: blocking for scientifically complete Data prose
- Observed behavior: current figure-derived cohort and source counts were targeted only to Results and Discussion, leaving the Data packet with zero registry records even though Data must report the verified sample boundary.
- Scientific risk: the writer must either omit essential cohort information or duplicate unbound numbers from internal context.
- Correction applied in the current working tree: run-bound figure statistics typed as counts are now available to Data, Results, and Discussion. Performance scores and other result metrics remain excluded from Data to prevent result leakage.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The accepted Data section distinguishes the 6,290-event static cohort, 6,010-event token-ready cohort, and 60-source study boundary without leaking performance results.

### ASTR-046: Methods packet embeds the complete plugin execution ledger

- Stage: `prepare-section-writing --section methods`
- Severity: high for cost and composition focus
- Observed behavior: the compact packet logic retained the entire method lifecycle because Methods needs formulas and code trace. Sixty-five plugin execution events contributed approximately 98,651 characters, expanding the packet to about 208,595 characters.
- User-visible impact: most prompt space describes repeated execution bookkeeping rather than sample construction, representation, equations, validation, and ablation design.
- Correction applied in the current working tree: Methods retains stages, formula contracts, figure-code trace, and prose constraints, but replaces raw plugin events with unique plugin IDs, statuses, event count, and an audit-source reference.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The regenerated Methods packet is 87,754 characters and retains formulas, method stages, and trace summaries without embedding the raw 65-event ledger.

### ASTR-047: Accepted Methods prose contains malformed inline LaTeX

- Stage: Methods candidate -> LaTeX assembly and PDF compilation
- Severity: blocking
- Observed behavior: displayed equations were valid, but inline variable delimiters lost their backslashes during candidate creation and one `\\bar` sequence became a backspace control character. The section passed writing and editor gates, then XeLaTeX failed on an underscore outside math mode.
- User-visible impact: all scientific writing stages appear green, but the first PDF build fails on malformed variable explanations.
- Correction applied in the current working tree: the Methods candidate uses stable dollar-delimited inline mathematics, and section validation now rejects non-whitespace control characters plus unescaped underscores outside math environments before acceptance.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The corrected Methods candidate passed validation and editor review, and XeLaTeX generated the manuscript PDF successfully.

### ASTR-048: Integrity summary promotes a historical inventory cohort

- Stage: `run-integrity-gate`
- Severity: high
- Observed behavior: the top-level integrity summary surfaces a retained historical inventory of 1,025 events and 11 sources even though role-aware evidence checks correctly bind the current 6,290-event static cohort, 6,010-event token-ready cohort, and 60-source study cohort.
- Scientific risk: a reader or downstream gate can mistake an intermediate parser-validation subset for the final modeling cohort, despite the semantic evidence registry containing the correct role distinctions.
- Required correction: integrity summaries must resolve cohort counts through the current evidence snapshot and semantic number roles. Historical inventory values may remain in the audit trail but must not be promoted as the current sample composition.
- Current lifecycle: `observed`; role-aware top-level integrity rendering remains pending.

### ASTR-049: Workflow schematic is judged by empirical-axis metadata rules

- Stage: `quality-check`
- Severity: blocking
- Observed behavior: the first main figure is an approved workflow schematic with process nodes and directed transitions, but the generic quality gate requires empirical axis variables and emits `figure_metadata_not_scientific`.
- User-visible impact: a scientifically valid study-design figure cannot pass final quality unless it invents meaningless axes.
- Correction applied in the current working tree: route workflow schematics through their semantic plot grammar. They must declare process stages, transitions, scientific question, and claim boundary, while empirical figures retain axis, unit, method-output, and statistics requirements.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. The workflow figure passes without fake axes, while malformed empirical metadata remains rejected in focused tests.

### ASTR-050: Final assembly invalidates an otherwise passing citation audit snapshot

- Stage: citation audit -> final `assemble-latex` -> paper-quality parity
- Severity: blocking
- Observed behavior: citation audit reached zero unsupported and zero blocking usages with all 12 retained references cited, but a later final assembly changed the manuscript snapshot. The release contract correctly reports `citation_audit_after_final_draft=false`.
- Scientific risk: a passing report can describe a manuscript version other than the released PDF.
- Required correction: the final citation audit must run after the last accepted section and final assembly. Any later manuscript mutation must make citation audit stale and require a new audit before release.
- Current lifecycle: `verified_in_project`. The final re-audit covers the current manuscript hashes, preserves all 12 references, and reports zero unsupported or blocking usages.

### ASTR-051: The 95% parity gate requires a full blind manuscript comparison

- Stage: final quality parity
- Severity: blocking for release evidence
- Observed behavior: automated structural and evidence scoring reaches 0.9825, but the hard release contract correctly refuses to infer writing parity without `quality_checks/blind_manuscript_evaluation.json`.
- User-visible impact: the requested comparison with the original manuscript cannot be claimed from unit tests or section-local quality scores alone.
- Required correction: compare the complete generated PDF and its real figures against the baseline with at least two independent reviewer records covering scientific narrative, cohort boundaries, model comparisons, ablation, uncertainty, equations, citations, figures, and layout. Scores must be grounded in inspected artifacts rather than fabricated to satisfy the gate.
- Current lifecycle: `protected`; blind comparison pending.

### ASTR-052: Snapshot-bound citation audit fails a timestamp-only release check

- Stage: final citation audit -> paper-quality parity
- Severity: blocking
- Observed behavior: the final citation audit was rerun after assembly and its manuscript/BibTeX hashes match the current files, but `citation_audit_after_final_draft` remained false because section-validation reports do not contain `generated_at`. The implementation required at least one section timestamp before it would accept the citation-audit time.
- User-visible impact: repeated citation re-audits can never satisfy the release contract even though the stronger hash-based snapshot check passes.
- Correction applied in the current working tree: prefer validation of the bound manuscript snapshot. Use timestamp ordering only as a compatibility fallback for legacy citation reports that predate snapshot binding.
- Current lifecycle: `verified_in_project`, `pending_general_regression`. Six focused parity tests pass and the project now reports `citation_audit_after_final_draft=true` from the current manuscript snapshot.

### ASTR-053: A contract-valid support figure can still weaken direct observational evidence

- Stage: figure storyboard -> complete-manuscript comparison
- Severity: high for parity, non-blocking for scientific correctness
- Observed behavior: the generated six-figure story replaces the baseline manuscript's representative current-observation light-curve panels with a class-support and modality-completeness summary. The replacement is scientifically valid and supports cohort interpretation, but it no longer lets the reader inspect the short-timescale input morphology directly.
- Scientific impact: the generated Results remain correct, yet the visual argument is less persuasive about what signal enters the current-observation encoder.
- Required correction: panel and figure planning must distinguish necessary cohort diagnostics from direct scientific signal examples. When both are important, preserve the planned main-figure story through a multi-panel group or move the cohort diagnostic to a supporting figure instead of silently consuming the observational-example slot.
- Current lifecycle: `observed`; this should be addressed in generic figure-story optimization rather than by hard-coding an astronomy plot.

### ASTR-054: Section packets remain expensive relative to accepted prose

- Stage: free section writing
- Severity: medium for cost and model attention
- Observed behavior: five section packets contain 122,238 observable `o200k_base` input tokens, while the five accepted candidates contain 5,716 output tokens. Results alone consumes 38,245 input tokens for 1,830 output tokens.
- User-visible impact: the evidence-first architecture preserves correctness but still pays a roughly 21.4:1 packet-to-candidate token ratio, increasing cost and making relevant evidence compete with repeated contract material.
- Required correction: add evidence retrieval by paragraph job, deduplicate cross-section constraints, replace repeated full objects with stable evidence IDs plus compact excerpts, and cache immutable literature/method summaries across section calls. Token reduction must preserve all quantitative bindings and claim boundaries.
- Current lifecycle: `observed`; packet compaction improved earlier oversized artifacts but has not yet reached an efficient steady state.

### ASTR-055: AASTeX is falsely warned for not explicitly loading natbib

- Stage: final bibliography quality check
- Severity: low
- Observed behavior: the generated manuscript uses the `aastex701` document class, which provides natbib-compatible citation commands, but the generic checker warns whenever `\\usepackage{natbib}` is absent from `main.tex`.
- User-visible impact: a correct journal template produces a distracting dependency warning and may encourage an unnecessary or conflicting package declaration.
- Correction applied in the current working tree: recognize AASTeX document classes as providing natbib support; retain the explicit-package warning for document classes that do not provide it.
- Current lifecycle: `corrected_in_worktree`; focused quality-gate verification pending.

### ASTR-056: Data-context literature warning does not distinguish provenance from background

- Stage: bibliography section-context check
- Severity: advisory
- Observed behavior: two references ranked for a data search context are not cited in Data, even though the accepted Data section describes project observations and all 12 retained references are accurately cited elsewhere.
- Scientific risk: automatically inserting those citations into Data could imply that external papers are the provenance of project observations when they are only methodological or mission background.
- Required correction: classify data-context references as dataset provenance, instrument/product definition, processing-method support, or background. Require a Data citation only for the first three roles; keep background coverage as a manuscript-wide requirement.
- Current lifecycle: `observed`; warning remains non-blocking pending role-aware citation placement.

### ASTR-057: LaTeX asset identifiers trigger prose underscore validation

- Stage: deterministic diagnostic Results -> section contract
- Severity: compatibility regression
- Observed behavior: the section contract correctly blocks bare underscores in manuscript prose, but it also inspected `includegraphics`, `label`, `ref`, and bibliography arguments. Valid project-relative asset identifiers therefore blocked legacy diagnostic writers and downstream tests.
- Correction applied in the current working tree: remove recognized LaTeX command arguments before checking prose underscores. Bare underscores in scientific prose and malformed inline mathematics remain blocking.
- Current lifecycle: `verified_in_tests`; Results and Discussion writer regressions pass.

### ASTR-058: Numeric scope mismatch is invisible when the stated scope is absent from same-value candidates

- Stage: quantitative claim binding
- Severity: blocking scientific correctness
- Observed behavior: a claim could state a smoke-test cohort, random split, observation unit, or different model while using a number that existed only for another scope. The resolver searched scope terms only among same-value candidates, so the contradictory stated scope was never considered.
- Scientific risk: a correct value can be attached to the wrong cohort, sample unit, split, run, or model without triggering `numeric_claim_scope_mismatch`.
- Correction applied in the current working tree: detect explicit scope signals across the full registry, then require same-value candidates to match every stated scope. The existing evidence ID and binding-field checks remain unchanged.
- Current lifecycle: `verified_in_tests`; wrong cohort/unit/split/model cases block and three-domain release regressions pass.

### ASTR-059: A failed quality stage is skipped by review routing

- Stage: `run-pipeline` after quality failure
- Severity: high
- Observed behavior: `_gate_failure_action` required `quality_checks` to have a completed-like status before reading a failed quality report. A stage explicitly marked `failed` therefore fell through to an earlier incomplete data action instead of entering reviewer diagnosis.
- User-visible impact: users can be sent backward into scientific generation even though the actionable failure is already known at final quality review.
- Correction applied in the current working tree: treat a non-stale `failed` quality stage as eligible for the review sequence and preserve the existing completed-report behavior.
- Current lifecycle: `verified_in_tests`; failed quality now recommends the review stage.

## Run Progress

| Phase | Status | Current evidence |
| --- | --- | --- |
| Literature import and journal profile | Passed | 12 retained references; APJS/AAS journal profile resolved |
| Research preflight and blueprint | Passed with conditional feasibility | Six main figure groups and one table planned |
| Data inventory and quality | Passed | 25 local data files, 97,545 inventoried rows, no required-column quality issue |
| Method planning and feasibility | Passed | Source-held-out classification, baselines, Transformer ablation, error analysis, and stress-test boundary retained |
| Plugin sufficiency | Blocked before corrections | False negatives plus one invented hardness requirement exposed |
| Figure generation | Passed after protected rerun | Six verified scientific figure groups restored; invalid generic identifier and mixed-dimension figures were rejected |
| Core evidence confirmation | Passed | Six figure semantics passed and checkpoint `3b339bcafc24` awaits/records the corrected confirmation path |
| Manuscript generation | Passed | All five sections completed free draft, submission, Scientific Editor, acceptance, and formal writer lifecycle |
| Citation audit and PDF | Passed | Final audit covers the current manuscript snapshot; 25 usages, 12/12 retained references cited, zero unsupported or blocking usages |
| Baseline comparison | Technical comparison complete; independent blind review pending | Generated PDF is 9 pages versus 11 pages; scientific facts and six-figure narrative are correct, but direct observational examples and section detail remain thinner |

## Token Ledger

The table reports observable artifact tokens with `tiktoken` `o200k_base`. It measures serialized section packets as input and accepted candidates as output. Deterministic local CLI stages are zero model tokens. Hidden reasoning, orchestration messages, retries outside saved packets, and platform overhead are not estimated.

| Stage | Input tokens | Output tokens | Total | Measurement |
| --- | ---: | ---: | ---: | --- |
| Literature/plan/data/method/figure CLI stages | 0 | 0 | 0 | Local deterministic execution |
| Results free writing | 38,245 | 1,830 | 40,075 | `writing/section_packets/results.json` + accepted candidate |
| Introduction free writing | 14,929 | 762 | 15,691 | `writing/section_packets/introduction.json` + accepted candidate |
| Data free writing | 16,614 | 525 | 17,139 | `writing/section_packets/data.json` + accepted candidate |
| Methods free writing | 21,458 | 1,462 | 22,920 | `writing/section_packets/methods.json` + accepted candidate |
| Discussion free writing | 30,992 | 1,137 | 32,129 | `writing/section_packets/discussion.json` + accepted candidate |
| **Observable writing total** | **122,238** | **5,716** | **127,954** | Five free-writing calls; `o200k_base` |
| Scientific Editor and validation | 0 | 0 | 0 | Local deterministic paragraph tasks, contracts, and acceptance checks in this run |

## Complete Manuscript Comparison

This is a technical, non-blind comparison and does not satisfy the two-independent-reviewer release contract.

| Dimension | Generated manuscript | Baseline manuscript | Assessment |
| --- | --- | --- | --- |
| Complete PDF | 9 pages; 4,205 extracted words | 11 pages; 5,101 extracted words | Generated draft is materially more concise |
| Scientific facts | Preserves 6,290/6,010 cohort distinction, 60 sources, 30+30 source balance, and 0.8667/0.8486/0.8053/0.8205 metrics | Preserves the same core model evidence, with more project-background detail | Core correctness aligned; generated cohort semantics are clearer |
| Six-figure story | Workflow, cohort support, pre-model structure, baselines, ablation, uncertainty | Workflow, direct light-curve examples, pre-model structure, baselines, ablation, uncertainty | Both are coherent; baseline has stronger direct observational evidence |
| Results | Correctly states that transparent baselines outperform the full Transformer and explains the history-branch failure without overclaiming | More detailed treatment of model variants and observational context | Generated reasoning is strong but shorter |
| Introduction | 543 source words and eight citation commands; explicit unresolved questions and contribution boundary | 462 source words and eight citation commands | Generated Introduction is at least comparable in structure and evidence use |
| Data | 427 source words; clean cohort roles and no internal paths | 742 source words; richer acquisition, product, stress-test, and modality details | Baseline remains stronger |
| Methods | 918 source words, nine displayed equations, variable explanations, source-held-out validation and ablation | 1,214 source words, eight displayed equations, more implementation and representation detail | Generated equations improved; baseline remains more complete |
| Discussion | 762 source words and ten citation commands; integrates comparisons, mechanism, limitations, and next steps | 547 source words and three citation commands; concise project-specific interpretation | Generated Discussion is broader and more literature-integrated |
| Layout | Clean 9-page AASTeX PDF; six figures and one table are legible | Clean 11-page AASTeX PDF; six figures, including detailed light-curve panels | Both render correctly; baseline figures carry more observational detail |

The generated manuscript clears the framework's automated functional score at 0.9825 and has no detected scientific contradiction, unsupported citation, evidence conflict, or figure-contract failure. A formal claim that it reaches 95% of the baseline remains intentionally unavailable until two independent blinded reviewers inspect the complete manuscripts and real figures. The present technical comparison identifies the remaining substantive gap as direct observational illustration and Data/Methods/Results detail, not template-like prose or incorrect metrics.

## Verification

- Complete repository suite: `441 passed in 360.20s`.
- Final project citation audit: passed with 25 usages, 12/12 reference coverage, zero unsupported usages, and zero blocking issues.
- Final project quality gate: all scientific, writing, figure, evidence, PDF, and citation checks pass; release remains blocked only by the intentionally missing two-reviewer blind evaluation. Conditional data/result scope and role-aware Data citation placement remain advisory warnings.
