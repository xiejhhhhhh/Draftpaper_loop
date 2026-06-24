# Pluggable Data Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal discipline-shared, connector-based data acquisition planning layer for Draftpaper-loop.

**Architecture:** Add a shared discipline inference module, route review engines through it, add a data acquisition module with `local_files`, `api_access`, and `remote_server` connector profiles, expose CLI commands, and verify with unit tests plus the Flares source root.

**Tech Stack:** Python standard library, existing Draftpaper-loop CLI, existing HTML report helper, unittest/pytest.

---

### Task 1: Shared Discipline Layer

**Files:**
- Create: `draftpaper_cli/discipline.py`
- Modify: `draftpaper_cli/review_engines/__init__.py`

- [x] Add discipline inference helpers that read project metadata and optional external context.
- [x] Replace duplicated review-engine discipline scoring with the shared helper.
- [x] Preserve existing geography, astronomy, machine-learning, and default routing behavior.

### Task 2: Data Acquisition Planning Module

**Files:**
- Create: `draftpaper_cli/data_acquisition.py`
- Modify: `draftpaper_cli/data_feasibility.py`

- [x] Add `classify_data_access(project, source_root=None)`.
- [x] Add `prepare_data_acquisition(project, source_root=None)`.
- [x] Write JSON, HTML, CSV, provenance, and completeness artifacts.
- [x] Keep behavior plan-first and credential-safe.

### Task 3: CLI and Exports

**Files:**
- Modify: `draftpaper_cli/cli.py`
- Modify: `draftpaper_cli/__init__.py`

- [x] Add `classify-data-access`.
- [x] Add `prepare-data-acquisition`.
- [x] Add `inventory-data-sources` as an alias that refreshes the acquisition manifest.

### Task 4: Tests and Validation

**Files:**
- Create: `tests/test_data_acquisition.py`

- [x] Test generic local/API/remote detection.
- [x] Test CLI commands.
- [x] Test shared discipline routing between data acquisition and review engines.
- [x] Validate against `C:\Flares_classificaiton` with `--source-root`.

