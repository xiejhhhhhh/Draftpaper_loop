# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DataConnectorSpec, DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec


class GeographyModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="geography",
        display_name="Geography, GIS, and remote sensing",
        keywords=["geography", "gis", "remote sensing", "ndvi", "spatial", "raster", "zoning"],
        data_roles=[
            "analysis_ready_table",
            "spatial_group_or_coordinates",
            "temporal_window",
            "remote_sensing_index",
            "environmental_covariates",
            "quality_flag",
        ],
        method_families=[
            "spatial_exploratory_analysis",
            "remote_sensing_feature_reconstruction",
            "environmental_driver_analysis",
            "spatial_block_validation",
            "baseline_ablation",
        ],
        validation_checks=[
            "coordinate_or_spatial_group_available",
            "temporal_leakage_check",
            "spatial_block_or_region_holdout",
            "missingness_and_quality_mask_check",
        ],
        figure_families=[
            "spatial_distribution_map_or_proxy",
            "remote_sensing_index_distribution",
            "environmental_driver_response",
            "spatial_block_validation_summary",
            "feature_ablation_summary",
        ],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=[
            "data_overview",
            "remote_sensing_index_distribution",
            "environmental_driver_response",
            "predictor_correlation_structure",
            "spatial_or_validation_summary",
        ],
        formula_families=["pearson_correlation", "linear_response_r2", "spatial_group_holdout", "feature_ablation_delta"],
        reviewer_risks=[
            "weak_statistical_association_without_qc",
            "spatial_autocorrelation_or_leakage",
            "unclear_remote_sensing_preprocessing",
            "missing_external_or_spatial_validation",
        ],
        code_generation_constraints=[
            "Prefer processed analysis tables when raw rasters or cloud data are unavailable locally.",
            "Require spatial coordinates or region groups before claiming spatial generalization.",
            "If spatial roles are missing, generate only non-spatial exploratory analysis and emit a blocked rescue task.",
        ],
        data_connectors=[
            DataConnectorSpec(
                connector_id="google_earth_engine",
                display_name="Google Earth Engine remote-sensing catalog",
                access_modes=["api_access", "cloud_processing"],
                packages=["earthengine-api", "geemap"],
                package_modules=["ee", "geemap"],
                credential_env_vars=["GOOGLE_APPLICATION_CREDENTIALS"],
                download_or_access=["Earth Engine image collection query", "server-side raster reduction", "export table/image to Drive or Cloud Storage"],
                data_formats=["GeoTIFF", "CSV zonal statistics", "NetCDF-like image exports", "asset manifest"],
                requires_credentials=True,
                template_paths=["data/connectors/google_earth_engine.py.template"],
            ),
            DataConnectorSpec(
                connector_id="local_raster_vector",
                display_name="Local raster/vector parser",
                access_modes=["local_files"],
                packages=["rasterio", "geopandas", "xarray", "netCDF4"],
                package_modules=["rasterio", "geopandas", "xarray", "netCDF4"],
                download_or_access=["read GeoTIFF/NetCDF rasters", "read Shapefile/GeoJSON/GeoPackage vectors", "derive zonal summaries"],
                data_formats=["GeoTIFF", "NetCDF", "Shapefile", "GeoJSON", "GeoPackage", "CSV"],
                requires_credentials=False,
                template_paths=["data/connectors/local_raster_vector.py.template"],
            ),
        ],
        method_templates=[
            MethodTemplateSpec(
                template_id="remote_sensing_feature_reconstruction",
                display_name="Remote-sensing feature reconstruction",
                discipline="geography",
                method_family="remote_sensing_feature_reconstruction",
                input_roles=["analysis_ready_table", "remote_sensing_index", "target_or_response"],
                optional_roles=["temporal_window", "quality_flag", "environmental_covariates"],
                packages=["pandas", "numpy"],
                package_modules=["pandas", "numpy"],
                output_artifacts=["results/tables/remote_sensing_feature_summary.csv", "results/figures/remote_sensing_feature_response.png"],
                figure_groups=["remote_sensing_index_distribution", "environmental_driver_response"],
                formula_families=["linear_response_r2", "pearson_correlation"],
                validation_checks=["minimum_row_count", "missingness_check", "range_check"],
                template_path="method_templates/remote_sensing_feature_reconstruction/template.py",
                aliases=["vegetation index reconstruction", "remote sensing feature rebuild"],
                variants=["tabular_index_summary"],
                genericity_rules=["Do not hard-code a region, date range, or satellite dataset.", "Expose index, target, grouping, and quality columns as parameters."],
            ),
            MethodTemplateSpec(
                template_id="spatial_block_validation",
                display_name="Spatial block validation",
                discipline="geography",
                method_family="spatial_validation",
                input_roles=["analysis_ready_table", "target_or_response", "predictors", "spatial_group_or_coordinates"],
                optional_roles=["temporal_window", "quality_flag"],
                packages=["pandas", "numpy", "scikit-learn"],
                package_modules=["pandas", "numpy", "sklearn"],
                output_artifacts=["results/tables/spatial_validation_metrics.csv", "results/figures/spatial_or_validation_summary.png"],
                figure_groups=["spatial_or_validation_summary"],
                formula_families=["spatial_group_holdout", "validation_metric"],
                validation_checks=["minimum_group_count", "no_group_leakage", "metric_written"],
                template_path="method_templates/spatial_block_validation/template.py",
                aliases=["regional blocked validation", "leave region out validation", "spatial holdout"],
                variants=["group_kfold", "leave_one_region_out"],
                genericity_rules=["Do not hard-code study units.", "Spatial group columns must be parameters."],
            ),
        ],
    )


MODULE = GeographyModule()
