# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DisciplineModule, DisciplineModuleSpec


class EcologyModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="ecology",
        display_name="Ecology and environmental monitoring",
        keywords=["ecology", "environment", "environmental monitoring", "habitat", "biodiversity", "netcdf", "geotiff"],
        data_roles=["monitoring_observations", "environmental_covariates", "spatial_group_or_coordinates", "temporal_window", "quality_flag"],
        method_families=["environmental_trend_analysis", "spatiotemporal_summary", "habitat_or_exposure_response", "uncertainty_analysis"],
        validation_checks=["temporal_coverage_check", "spatial_coverage_check", "sensor_or_qc_flag_check", "external_covariate_alignment"],
        figure_families=["monitoring_coverage_summary", "environmental_time_series", "spatial_exposure_distribution", "driver_response", "uncertainty_summary"],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=["data_overview", "monitoring_coverage", "environmental_time_series", "driver_response", "uncertainty_or_validation_summary"],
        formula_families=["trend_estimator", "linear_or_generalized_response", "uncertainty_interval", "spatial_summary"],
        reviewer_risks=["insufficient_temporal_coverage", "sensor_qc_unclear", "spatial_sampling_bias", "overclaiming_causality"],
        code_generation_constraints=[
            "Do not claim ecological causality from monitoring correlations alone.",
            "Require temporal and spatial coverage roles before writing monitoring generalization claims.",
        ],
        data_connectors=[
            {
                "connector_id": "public_web_download",
                "display_name": "Public environmental data download",
                "access_modes": ["public_web_download", "api_access"],
                "packages": ["requests", "pooch"],
                "package_modules": ["requests", "pooch"],
                "download_or_access": ["download public archives", "cache source manifest", "verify checksum when provided"],
                "data_formats": ["CSV", "GeoTIFF", "NetCDF", "ZIP", "JSON metadata"],
                "requires_credentials": False,
            },
            {
                "connector_id": "geotiff_netcdf_parser",
                "display_name": "GeoTIFF and NetCDF parser",
                "access_modes": ["local_files"],
                "packages": ["rasterio", "xarray", "netCDF4", "geopandas"],
                "package_modules": ["rasterio", "xarray", "netCDF4", "geopandas"],
                "download_or_access": ["read local GeoTIFF/NetCDF grids", "extract time series", "join monitoring observations with covariates"],
                "data_formats": ["GeoTIFF", "NetCDF", "Zarr", "CSV", "GeoJSON"],
                "requires_credentials": False,
            },
        ],
    )


MODULE = EcologyModule()
