# Discipline Modules

Draftpaper-loop now treats a discipline module as the shared plugin layer for data acquisition, method generation, figure planning, and reviewer/rescue diagnosis.

Core modules currently shipped:

- `default`: conservative cross-disciplinary fallback.
- `geography`: GIS, remote sensing, spatial validation, environmental response, and agricultural geography.
- `astronomy`: source catalogs, light curves, multiwavelength features, catalog crossmatch, and rare-class validation.
- `machine_learning`: baseline modelling, supervised learning, deep learning, ablation, leakage checks, and error analysis.
- `ecology`: ecological and environmental monitoring with public web/API data and GeoTIFF/NetCDF parsing.
- `bioinformatics`: GEO/SRA/ENA-style public omics access, sample metadata, QC, and processed expression/sequence manifests.

Each module declares data roles, method families, validation checks, figure families, minimum/target main-figure counts, required figure groups, formula families, reviewer risks, code-generation constraints, and data connectors. The CLI command `prepare-method-blueprint` reads the selected module and writes project-local method planning artifacts under `methods/`. The CLI command `prepare-data-acquisition` reads the same module and writes a connector catalog under `data/data_acquisition_plan.json`, including packages, API/download routes, expected data formats, and a local feasibility status.

## Composite Discipline Modules

Cross-disciplinary papers are handled by a runtime composite module rather than a permanent branch or a new copied discipline folder. Discipline inference now records a `primary_discipline`, `secondary_disciplines`, `discipline_scores`, and ordered `discipline_modules`. The runtime composer merges `default`, the primary module, and any secondary modules in order, then deduplicates data connectors, method templates, and review rules by stable ids.

Examples:

- Wheat NDVI plus RF/XGBoost/SHAP: `default + geography + machine_learning`.
- Time-domain astronomy source classification with transformers: `default + astronomy + machine_learning`.
- Environmental monitoring with geospatial rasters and ecological claims: `default + ecology + geography` when both signal groups are present.

Reusable plugin contributions still merge into one stable home module. Cross-disciplinary composition only decides which modules a paper project can call during a run; it does not create one permanent branch per paper direction.

## Scenario Coverage

| Research scenario | Discipline module | Data acquisition connectors |
| --- | --- | --- |
| Time-domain astronomy source identification | `astronomy` | photon-event API planning, observation/product manifests, mission/archive API, remote server SSH |
| Wheat NDVI geography/agriculture analysis | `geography` | Google Earth Engine, precipitation export planning, NetCDF/GeoTIFF conversion, gridded-text raster conversion, ArcGIS zonal statistics, local raster/vector parser |
| Ecological or environmental monitoring | `ecology` | public web download, API access, GeoTIFF/NetCDF parser |
| Deep-learning image classification and tabular modelling | `machine_learning` | local files, tabular environment dataset profiling, saved-model manifests, vision catalog/image connector, pretrained backbone metadata, Kaggle/Hugging Face datasets, cloud storage |
| Bioinformatics public-data study | `bioinformatics` | GEO/SRA/ENA API, remote server SSH |

## Stage-Owned Code Rule

Executable code belongs to the paper stage that owns the scientific action:

- `data/scripts/`: data collection, API access, remote manifests, preprocessing, cleaning, and data exports.
- `methods/scripts/`: modelling, statistics, spatial analysis, validation, and figure-generation entrypoints.
- `methods/src/`: reusable project-local method runtime modules.
- `results/`: only produced figures, tables, and metadata.
- `code/`: compatibility launchers and shared utility copies only.

## Contribution Flow

Forks and PR branches are temporary contribution channels. Stable reusable capabilities must be merged into `main` under the matching discipline module. Do not keep one permanent branch per research direction.

Recommended preflight:

```powershell
python -m draftpaper_cli.cli summarize-plugin-candidates --project <project>
python -m draftpaper_cli.cli generalize-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli package-plugin-contribution --candidate <candidate>
python -m draftpaper_cli.cli write-github-contribution-guide --project <project>
```

Only generalized templates, manifests, fixtures, tests, privacy scans, overlap reports, validation reports, and merge plans should be submitted. Do not submit local data, private paths, credentials, generated manuscripts, PDFs, or project-specific scripts.

## Built-in Plugin Seeds

The astronomy module includes reusable seeds for photon-event and time-domain source workflows:

- `einstein_probe_photon_api`: environment-only photon API configuration, query construction, raw JSON caching, and normalized light-curve rows.
- `wxt_manifest_product`: WXT observation/product id normalization and server product manifest construction.
- `long_term_light_curve_feature_extraction`: source-level long-term light-curve statistics, activity fraction, cadence/duration summaries, and CSV feature output.
- `event_level_transformer_input_builder`: event manifest plus source feature joining, class-count summaries, and transformer-data completeness reporting.

The machine-learning module includes reusable deep-learning and representation-learning seeds:

- `vision_catalog_image`: image-folder and catalog table alignment with object-id parsing and label filtering.
- `pretrained_backbone`: sanitized backbone metadata recording without uploading checkpoint binaries.
- `self_supervised_dino_training`: project-bound DINO/teacher-student training plan generation.
- `checkpoint_shape_adapter`: checkpoint/model shape comparison and position-embedding resize diagnostics.
- `embedding_extraction_health_diagnostics`: embedding norm, active-dimension, and collapse-risk diagnostics.
- `few_label_probe_benchmark`: few-label linear/MLP probe result aggregation.
- `embedding_similarity_retrieval`: cosine top-k retrieval over embedding matrices.

The geography module also includes reusable GIS/agricultural remote-sensing seeds:

- `google_earth_engine_precip_export`: user-confirmed precipitation export planning for cloud-side Earth Engine workflows.
- `netcdf_to_geotiff_converter`: NetCDF variable and coordinate normalization before project-bound GeoTIFF export.
- `gridded_text_to_geotiff_converter`: gridded TXT/CSV reshaping and raster-export manifest planning.
- `arcgis_zonal_statistics_adapter`: ArcGIS/project-bound zonal statistics job manifests.
- `monthly_remote_sensing_index_summary`: month-wise NDVI/LAI or other index summary tables.
- `phenology_curve_smoothing`: generic moving-average seasonal curve smoothing and peak-timing extraction.
- `ndvi_temporal_kmeans_zoning`: deterministic temporal-profile clustering for zoning-style analysis.
- `ndvi_cluster_statistical_diagnostics`: descriptive cluster diagnostics with explicit separation from formal tests that require scipy/statsmodels.

The machine-learning module now includes tabular modelling and interpretation seeds:

- `tabular_environment_dataset`: table profiling for environmental/crop-style feature matrices.
- `saved_model_loader`: sanitized saved-model manifest writing without committing model binaries.
- `random_forest_regression_gridsearch`, `xgboost_optuna_regression`, `gradient_boosting_regression_pipeline`, and `stacking_regression_ensemble`: configurable regression modelling plans that can be expanded into project-local code.
- `observed_predicted_scatter_grid`, `feature_importance_report`, `partial_dependence_ice_analysis`, and `shap_tree_explainer_report`: model diagnostics and interpretation artifacts.
- `model_statistical_validity_gate`: reviewer-side checks that keep p-values as statistical-confidence evidence and R2/task metrics as fit or effect-size evidence.

These seeds are intentionally small and fixture-backed. Full project execution may bind them to large data, API calls, servers, checkpoints, or GPU training locally, but those project bindings should not be committed as reusable plugins.
