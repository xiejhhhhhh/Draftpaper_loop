# Pluggable Data Acquisition Design

## Goal

Draftpaper-loop should keep its core data stage discipline-neutral while allowing field-specific projects to use very different data access patterns. Astronomy examples may use photon APIs, WXT manifests, Swift archives, and SSH servers, while geography projects may use Google Earth Engine, GeoTIFFs, shapefiles, or local processed exports. These field-specific tools must not be hard-coded into the core data stage.

## Architecture

The core loop now separates two decisions. The shared discipline layer infers a discipline profile from the idea, field, research plan, data context, method context, journal profile, and optional external source root. Data acquisition then uses that same profile together with connector detection. Review engines and data acquisition share the discipline profile, so a reviewer/rescue issue can route back to the right data access type without duplicating discipline detection.

The first implementation keeps the connector surface intentionally small:

- `local_files` inventories local raw data, processed tables, result tables, and external source-root artifacts.
- `api_access` detects API-style workflows such as REST APIs, endpoint scripts, Google Earth Engine, photon API, and token-mediated access without executing downloads.
- `remote_server` detects server/SSH/manifest/symlink workflows where data may stay remote and only processed summaries come local.

## Data Flow

`classify-data-access` writes `data/data_access_profile.json`. `prepare-data-acquisition` writes the full plan-first artifact set:

- `data/data_acquisition_plan.json`
- `data/data_acquisition_plan.html`
- `data/data_source_manifest.csv`
- `data/data_access_log.csv`
- `data/data_provenance.json`
- `data/data_completeness_report.html`
- `data/data_acquisition_tasks.json`
- `data/data_acquisition_tasks.html`

These artifacts describe how data may be accessed, what evidence was detected, what should be checked before download or analysis, and how review/rescue loops should ask for missing data.

When reviewer or rescue artifacts exist, `prepare-data-acquisition` reads `review/actionable_analysis_tasks.json`, `review/review_engineering_plan.json`, `review/statistical_rescue_plan.json`, `review/revision_plan.json`, and `review/gate_failure_diagnosis.json`. Blocked analysis tasks become connector-aware acquisition tasks. Each task records the missing data roles, optional missing data, suggested generic connector types, whether user confirmation is required, and the confirmation question that Codex should ask before any fetch or server action.

## Boundaries

This design does not fetch field-specific data. It only classifies access modes and writes a reproducible plan. Field-specific connectors can be added later under the same interface, for example astronomy archive connectors or geography/Google Earth Engine connectors. Credentials, API keys, tokens, passwords, and private server details must not be written into tracked artifacts.

## Validation Target

The first validation target is a local cross-discipline source tree. The expected behavior is not to install field-specific code into Draftpaper-loop. Instead, the generic classifier should infer the appropriate discipline profile and detect whether the source root uses local files, API access, or remote-server/manifest patterns without documenting private paths or project-specific identifiers.
