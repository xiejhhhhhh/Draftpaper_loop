# Stage-Owned Discipline Methods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move generated Draftpaper-loop data and method code into stage-owned project folders, add a pluggable discipline method framework, and validate the migration on the NDVI/wheat project.

**Architecture:** The paper project owns executable code by stage: data acquisition/preprocessing code lives under `data/scripts`, method/model/statistical/spatial/plotting code lives under `methods/scripts` and `methods/src`, and `results` only contains outputs and metadata. `code/` remains as a compatibility launcher and shared-runtime bridge for existing commands.

**Tech Stack:** Python standard library, existing Draftpaper CLI modules, local JSON/HTML manifests, pytest.

---

### Task 1: Stage-Owned Directory Model

**Files:**
- Modify: `draftpaper_cli/project_scaffold.py`
- Modify: `docs/cli_workflow_priority_guide.md`
- Test: `tests/test_project_scaffold.py`

- [ ] Add `data/scripts`, `data/acquisition`, `methods/scripts`, `methods/src`, and `code/shared` to project scaffolds.
- [ ] Keep `code/scripts`, `code/src`, and `code/tests` as compatibility folders.
- [ ] Verify new projects contain both stage-owned and compatibility code directories.

### Task 2: Data/Method Code Manifests

**Files:**
- Modify: `draftpaper_cli/analysis_code.py`
- Create: `draftpaper_cli/method_blueprint.py`
- Test: `tests/test_analysis_code_generation.py`
- Test: `tests/test_method_blueprint.py`

- [ ] Write generated method runtime to `methods/src/generated_pipeline.py`.
- [ ] Write method execution entrypoint to `methods/scripts/run_analysis.py`.
- [ ] Write plotting requirement installer to `methods/scripts/install_plotting_requirements.py`.
- [ ] Write compatibility launchers under `code/scripts`.
- [ ] Write `methods/method_code_manifest.json` and retain `methods/analysis_code_manifest.json` as a compatibility copy.
- [ ] Write `data/data_code_manifest.json` when data acquisition code scaffolding is generated.

### Task 3: Discipline Module Framework

**Files:**
- Create: `draftpaper_cli/discipline_modules/base.py`
- Create: `draftpaper_cli/discipline_modules/registry.py`
- Create: `draftpaper_cli/discipline_modules/default/module.py`
- Create: `draftpaper_cli/discipline_modules/geography/module.py`
- Create: `draftpaper_cli/discipline_modules/astronomy/module.py`
- Create: `draftpaper_cli/discipline_modules/machine_learning/module.py`
- Test: `tests/test_discipline_modules.py`

- [ ] Define a stable module contract for data roles, method families, validation checks, figure families, and reviewer rescue routes.
- [ ] Connect the existing discipline classifier to the discipline module registry.
- [ ] Add default, geography, astronomy, and machine-learning module skeletons.

### Task 4: Method Blueprint CLI

**Files:**
- Create: `draftpaper_cli/method_blueprint.py`
- Modify: `draftpaper_cli/cli.py`
- Modify: `draftpaper_cli/orchestrator.py`
- Test: `tests/test_method_blueprint.py`

- [ ] Add `prepare-method-blueprint --project`.
- [ ] Read project idea, field, target journal, data inventory, method requirements, literature, review rescue tasks, and discipline profile.
- [ ] Write `methods/method_blueprint.json`, `methods/method_blueprint.html`, `methods/method_data_contract.json`, `methods/method_code_plan.json`, and `methods/method_formula_plan.json`.
- [ ] Recommend method blueprint generation before analysis-code generation.

### Task 5: Verification and Writing Context

**Files:**
- Modify: `draftpaper_cli/methods.py`
- Modify: `draftpaper_cli/results.py`
- Modify: `draftpaper_cli/quality_gate.py`
- Test: `tests/test_methods.py`
- Test: `tests/test_methods_results_pipeline.py`

- [ ] `verify-methods` should accept and prefer `methods/scripts/run_analysis.py`.
- [ ] Methods writing context should read `methods/method_code_manifest.json`, code-plan summaries, and method-blueprint artifacts.
- [ ] Results writing should consume only `results/figures`, `results/tables`, and figure metadata.
- [ ] Quality gates should flag generated primary method code that only exists under `code/`.

### Task 6: Contributor Documentation

**Files:**
- Create: `docs/discipline_modules/README.md`
- Create: `docs/discipline_modules/module_contract.md`
- Create: `docs/discipline_modules/codex_authoring_guide.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] Document how to contribute discipline modules.
- [ ] Document how Codex should summarize a discipline module from a real paper workflow.
- [ ] Update README command examples with stage-owned code locations.

### Task 7: NDVI/Wheat Migration Validation

**Files:**
- Modify project files under `D:\SW_Maping\Draftpaper_loop\projects\exploratory-analysis-of-relationships-between-ndvi-time-series-indicators-wheat`

- [ ] Run `prepare-method-blueprint`.
- [ ] Run `generate-analysis-code` and confirm method code lands under `methods/`.
- [ ] Confirm compatibility launchers remain under `code/`.
- [ ] Run `verify-methods`.
- [ ] Confirm results contain PNG/table/metadata outputs only.
- [ ] Rebuild method context if verification succeeds.
