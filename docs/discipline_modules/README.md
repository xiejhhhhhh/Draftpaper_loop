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

## Scenario Coverage

| Research scenario | Discipline module | Data acquisition connectors |
| --- | --- | --- |
| Einstein Probe TDE/source identification | `astronomy` | mission/archive API, remote server SSH, instrument archive |
| Wheat NDVI geography/agriculture analysis | `geography` | Google Earth Engine, local raster/vector parser |
| Ecological or environmental monitoring | `ecology` | public web download, API access, GeoTIFF/NetCDF parser |
| Deep-learning image classification | `machine_learning` | local files, Kaggle/Hugging Face datasets, cloud storage |
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
