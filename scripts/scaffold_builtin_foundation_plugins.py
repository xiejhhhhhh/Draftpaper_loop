# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Generate the deterministic first-party local discipline plugin foundation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1] / "draftpaper_cli" / "discipline_modules"

NEW_DISCIPLINES: dict[str, dict[str, list[tuple[str, str, list[str]]]]] = {
    "chemistry": {
        "connectors": [("rdkit_structure_table", "RDKit structure table", ["rdkit"]), ("matchms_spectral_library", "Mass-spectrometry spectral library", ["matchms"]), ("molecular_descriptor_table", "Molecular descriptor table", ["datamol"])],
        "methods": [("molecular_standardization", "Molecular standardization", ["rdkit", "datamol"]), ("descriptor_qsar_baseline", "Descriptor-based QSAR baseline", ["scikit-learn", "rdkit"]), ("chemical_similarity_network", "Chemical similarity network", ["rdkit", "networkx"]), ("mass_spectrum_matching", "Mass-spectrum matching", ["matchms"]), ("medicinal_chemistry_filter", "Medicinal-chemistry filter", ["medchem"])],
        "rules": [("chemical_identity_gate", "Chemical identity and standardization gate", []), ("assay_split_gate", "Assay split and leakage gate", []), ("chemical_space_gate", "Chemical-space coverage gate", []), ("unit_assay_gate", "Assay-unit consistency gate", []), ("qsar_validation_gate", "QSAR validation gate", [])],
    },
    "materials_science": {
        "connectors": [("materials_structure_table", "Materials structure table", ["pymatgen"]), ("computed_materials_export", "Computed materials export", ["pymatgen"]), ("spectral_property_table", "Spectral property table", ["pymatgen"])],
        "methods": [("crystal_structure_featurization", "Crystal-structure featurization", ["pymatgen"]), ("formation_energy_regression", "Formation-energy regression", ["scikit-learn"]), ("phase_stability_analysis", "Phase-stability analysis", ["pymatgen"]), ("materials_property_visualization", "Materials-property visualization", ["matplotlib"]), ("composition_generalization_split", "Composition-aware generalization split", ["scikit-learn"])],
        "rules": [("materials_provenance_gate", "Materials provenance gate", []), ("composition_leakage_gate", "Composition leakage gate", []), ("structure_relaxation_gate", "Structure-relaxation boundary gate", []), ("unit_property_gate", "Property-unit consistency gate", []), ("materials_validation_gate", "Materials validation gate", [])],
    },
    "physics": {
        "connectors": [("laboratory_timeseries_manifest", "Laboratory time-series manifest", []), ("simulation_field_array", "Simulation field array", ["zarr"]), ("physical_constants_table", "Physical constants table", ["sympy"])],
        "methods": [("symbolic_dimension_check", "Symbolic dimensional analysis", ["sympy"]), ("dynamical_system_simulation", "Dynamical-system simulation", ["numpy", "scipy"]), ("spectral_signal_analysis", "Spectral signal analysis", ["numpy", "scipy"]), ("uncertainty_propagation", "Uncertainty propagation", ["numpy"]), ("physics_informed_fit", "Physics-informed model fit", ["scipy"])],
        "rules": [("dimension_consistency_gate", "Dimensional consistency gate", []), ("boundary_initial_condition_gate", "Boundary and initial-condition gate", []), ("conservation_law_gate", "Conservation-law gate", []), ("uncertainty_reporting_gate", "Uncertainty reporting gate", []), ("simulation_convergence_gate", "Simulation convergence gate", [])],
    },
    "quantum_science": {
        "connectors": [("quantum_circuit_spec", "Quantum circuit specification", ["qiskit"]), ("local_measurement_counts", "Local measurement-count table", ["qiskit"]), ("hamiltonian_operator_table", "Hamiltonian operator table", ["qutip"])],
        "methods": [("local_circuit_simulation", "Local circuit simulation", ["qiskit"]), ("variational_quantum_optimization", "Variational quantum optimization", ["qiskit"]), ("open_quantum_system_simulation", "Open quantum-system simulation", ["qutip"]), ("quantum_state_tomography_plan", "Quantum-state tomography plan", ["qiskit"]), ("noise_sensitivity_analysis", "Noise sensitivity analysis", ["qiskit"])],
        "rules": [("classical_baseline_gate", "Classical-baseline comparison gate", []), ("shot_uncertainty_gate", "Shot-uncertainty gate", []), ("noise_model_gate", "Noise-model declaration gate", []), ("circuit_reproducibility_gate", "Circuit reproducibility gate", []), ("quantum_claim_scope_gate", "Quantum claim-scope gate", [])],
    },
    "neuroscience": {
        "connectors": [("bids_neuroimaging_dataset", "BIDS neuroimaging dataset", ["pybids"]), ("pydicom_imaging_manifest", "DICOM imaging manifest", ["pydicom"]), ("physiological_signal_table", "Physiological signal table", ["neurokit2"])],
        "methods": [("bids_preprocessing_audit", "BIDS preprocessing audit", ["pybids"]), ("physiological_signal_features", "Physiological signal features", ["neurokit2"]), ("neuroimaging_connectivity_analysis", "Neuroimaging connectivity analysis", ["numpy"]), ("survival_outcome_model", "Survival outcome model", ["scikit-survival"]), ("brain_behavior_association", "Brain-behavior association", ["statsmodels"])],
        "rules": [("neuroimaging_qc_gate", "Neuroimaging quality-control gate", []), ("multiple_comparison_gate", "Multiple-comparison gate", []), ("subject_leakage_gate", "Subject leakage gate", []), ("clinical_privacy_gate", "Clinical privacy gate", []), ("neuroscience_reproducibility_gate", "Neuroscience reproducibility gate", [])],
    },
}

EXTRA_PLUGINS: dict[str, dict[str, list[tuple[str, str, list[str]]]]] = {
    "default": {
        "methods": [
            ("exploratory_data_analysis", "Exploratory data analysis", ["pandas"]),
            ("statistical_analysis_workbench", "Statistical analysis workbench", ["statsmodels", "scipy"]),
            ("statistical_power_analysis", "Statistical power analysis", ["statsmodels", "scipy"]),
            ("experimental_design_planner", "Experimental design planner", ["scipy"]),
            ("scikit_learn_classical_model_selection", "Scikit-learn classical model selection", ["scikit-learn"]),
            ("pymoo_multiobjective_optimization", "Pymoo multi-objective optimization", ["pymoo"]),
            ("polars_dataframe_transform", "Polars dataframe transformation", ["polars"]),
            ("vaex_out_of_core_table", "Vaex out-of-core table analysis", ["vaex"]),
            ("dask_local_parallel_analysis", "Dask local parallel analysis", ["dask"]),
            ("zarr_chunked_array_analysis", "Zarr chunked array analysis", ["zarr"]),
            ("matplotlib_publication_figure", "Matplotlib publication figure", ["matplotlib"]),
            ("seaborn_statistical_plotting", "Seaborn statistical plotting", ["seaborn"]),
            ("scientific_visualization_contract", "Scientific visualization contract", ["matplotlib", "seaborn"]),
            ("academic_plotting_quality_assurance", "Academic plotting quality assurance", ["matplotlib"]),
            ("networkx_graph_analysis", "NetworkX graph analysis", ["networkx"]),
        ],
        "rules": [
            ("statistical_assumption_gate", "Statistical assumption gate", []),
            ("statistical_power_gate", "Statistical power gate", []),
            ("experimental_design_gate", "Experimental design gate", []),
            ("peer_review_evidence_gate", "Peer-review evidence gate", []),
            ("rigor_reviewer_reproducibility_gate", "Rigor reviewer reproducibility gate", []),
            ("nature_reporting_completeness_gate", "Nature-style reporting completeness gate", []),
            ("visualization_readability_gate", "Visualization readability gate", []),
            ("baseline_ablation_gate", "Baseline and ablation gate", []),
        ],
    },
    "machine_learning": {
        "methods": [
            ("statsmodels_regression_diagnostics", "Statsmodels regression diagnostics", ["statsmodels"]),
            ("pymc_bayesian_inference", "PyMC Bayesian inference", ["pymc"]),
            ("aeon_time_series_classification", "Aeon time-series classification", ["aeon"]),
            ("umap_embedding_analysis", "UMAP embedding analysis", ["umap-learn"]),
            ("shap_explainability_audit", "SHAP explainability audit", ["shap"]),
            ("pymoo_multiobjective_model_search", "Pymoo multi-objective model search", ["pymoo"]),
        ],
    },
    "astronomy": {
        "connectors": [("astropy_fits_wcs_local", "Astropy FITS and WCS local reader", ["astropy"]), ("fits_table_local_reader", "FITS table local reader", ["astropy"])],
        "methods": [("astropy_time_units_coordinates", "Astropy Time, units, and coordinates", ["astropy"]), ("wcs_coordinate_transform", "WCS coordinate transform", ["astropy"]), ("time_scale_normalization", "Astronomical time-scale normalization", ["astropy"]), ("unit_safe_quantity_conversion", "Unit-safe quantity conversion", ["astropy"])],
        "rules": [("fits_wcs_provenance_gate", "FITS and WCS provenance gate", []), ("astropy_unit_consistency_gate", "Astronomical unit consistency gate", []), ("time_system_declaration_gate", "Time-system declaration gate", [])],
    },
    "geography": {
        "connectors": [("geopandas_vector_local", "GeoPandas local vector reader", ["geopandas"]), ("geomaster_local_coordinate_inputs", "GeoMaster local coordinate inputs", ["geopandas", "pyproj"])],
        "methods": [("geopandas_crs_geometry_validation", "GeoPandas CRS and geometry validation", ["geopandas"]), ("coordinate_reference_harmonization", "Coordinate reference harmonization", ["geopandas", "pyproj"]), ("local_geometric_overlay", "Local geometric overlay", ["geopandas"]), ("raster_vector_zonal_feature_extraction", "Raster-vector zonal feature extraction", ["geopandas", "rasterio"])],
        "rules": [("crs_consistency_gate", "Coordinate-reference consistency gate", []), ("geometry_validity_gate", "Geometry validity gate", []), ("spatial_unit_alignment_gate", "Spatial-unit alignment gate", []), ("local_spatial_coverage_gate", "Local spatial coverage gate", [])],
    },
    "bioinformatics": {
        "connectors": [("anndata_h5ad_local", "AnnData H5AD local dataset", ["anndata"]), ("biopython_sequence_records", "Biopython sequence records", ["biopython"]), ("bulk_rnaseq_count_matrix", "Bulk RNA-seq count matrix", ["pandas"]), ("pysam_alignment_bam", "Pysam alignment BAM input", ["pysam"]), ("flowio_fcs_cytometry", "FlowIO FCS cytometry input", ["flowio"]), ("scanpy_matrix_local", "Scanpy local matrix input", ["scanpy"])],
        "methods": [("anndata_qc_normalization", "AnnData QC and normalization", ["anndata"]), ("biopython_sequence_qc", "Biopython sequence quality control", ["biopython"]), ("bulk_rnaseq_differential_expression", "Bulk RNA-seq differential expression", ["pydeseq2"]), ("cobrapy_flux_balance", "COBRApy flux balance analysis", ["cobrapy"]), ("deeptools_coverage_profile", "DeepTools coverage profile", ["deeptools"]), ("etetoolkit_phylogeny", "ETE toolkit phylogeny", ["ete3"]), ("flowio_cytometry_qc", "FlowIO cytometry quality control", ["flowio"]), ("pydeseq2_differential_expression", "PyDESeq2 differential expression", ["pydeseq2"]), ("pysam_alignment_qc", "Pysam alignment quality control", ["pysam"]), ("scanpy_cpu_clustering", "Scanpy CPU clustering", ["scanpy"]), ("scikit_bio_diversity", "Scikit-bio diversity analysis", ["scikit-bio"]), ("scvelo_rna_velocity", "Scvelo RNA velocity", ["scvelo"])],
        "rules": [("bioinformatics_replicate_gate", "Bioinformatics replicate gate", []), ("batch_effect_gate", "Batch-effect gate", []), ("multiple_testing_fdr_gate", "Multiple-testing FDR gate", []), ("sequence_alignment_qc_gate", "Sequence-alignment QC gate", []), ("count_matrix_normalization_gate", "Count-matrix normalization gate", []), ("single_cell_cluster_stability_gate", "Single-cell cluster stability gate", [])],
    },
    "medicine": {
        "connectors": [("bids_pydicom_local_manifest", "BIDS and DICOM local manifest", ["pydicom"]), ("bids_local_dataset", "BIDS local dataset", ["pybids"]), ("neurokit2_physiology_table", "NeuroKit2 physiology table", ["neurokit2"]), ("survival_cohort_local_table", "Local survival cohort table", ["scikit-survival"])],
        "methods": [("bids_dataset_validation", "BIDS dataset validation", ["pybids"]), ("pydicom_metadata_qc", "Pydicom metadata quality control", ["pydicom"]), ("neurokit2_signal_features", "NeuroKit2 signal features", ["neurokit2"]), ("scikit_survival_time_to_event", "Scikit-survival time-to-event analysis", ["scikit-survival"])],
        "rules": [("medical_imaging_deidentification_gate", "Medical imaging de-identification gate", []), ("clinical_endpoint_definition_gate", "Clinical endpoint-definition gate", []), ("survival_censoring_gate", "Survival censoring gate", []), ("clinical_model_calibration_gate", "Clinical model calibration gate", []), ("clinical_data_leakage_gate", "Clinical data leakage gate", [])],
    },
    "chemistry": {"methods": [("molfeat_molecular_embedding", "Molfeat molecular embedding", ["molfeat"])]},
    "materials_science": {"methods": [("pymatgen_cif_normalization", "Pymatgen CIF normalization", ["pymatgen"])]},
    "physics": {"connectors": [("fluidsim_cpu_field_output", "FluidSim CPU field output", ["fluidsim"])], "methods": [("fluidsim_cpu_simulation", "FluidSim CPU simulation", ["fluidsim"])]},
    "quantum_science": {"methods": [("cirq_local_circuit_simulation", "Cirq local circuit simulation", ["cirq"])]},
}

EXTERNAL_FOUNDATIONS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "astronomy": {"connectors": [
        {"plugin_id": "photon_archive_api_contract", "display_name": "Photon archive API task contract", "packages": ["requests"], "runtime_class": "remote_api", "access_modes": ["api_access", "instrument_archive"], "credential_env_vars": ["ASTRONOMY_ARCHIVE_TOKEN"]},
        {"plugin_id": "remote_fits_ssh_task_contract", "display_name": "Remote FITS SSH task contract", "packages": ["paramiko"], "runtime_class": "remote_server", "access_modes": ["remote_server_ssh"], "credential_env_vars": ["DRAFTPAPER_REMOTE_HOST", "DRAFTPAPER_REMOTE_USER"]},
    ]},
    "geography": {"connectors": [
        {"plugin_id": "google_earth_engine_api_contract", "display_name": "Google Earth Engine API task contract", "packages": ["earthengine-api"], "runtime_class": "remote_api", "access_modes": ["api_access", "cloud_export"], "credential_env_vars": ["EARTHENGINE_PROJECT"]},
    ]},
    "bioinformatics": {"connectors": [
        {"plugin_id": "ncbi_entrez_api_contract", "display_name": "NCBI Entrez API task contract", "packages": ["biopython"], "runtime_class": "remote_api", "access_modes": ["api_access"], "credential_env_vars": ["NCBI_API_KEY"]},
        {"plugin_id": "ena_sra_api_contract", "display_name": "ENA and SRA API task contract", "packages": ["requests"], "runtime_class": "remote_api", "access_modes": ["api_access"], "credential_env_vars": []},
    ]},
    "medicine": {"connectors": [
        {"plugin_id": "fhir_ehr_api_contract", "display_name": "FHIR EHR API task contract", "packages": ["requests"], "runtime_class": "remote_api", "access_modes": ["api_access"], "credential_env_vars": ["FHIR_ACCESS_TOKEN"]},
    ]},
    "chemistry": {"connectors": [
        {"plugin_id": "pubchem_api_contract", "display_name": "PubChem API task contract", "packages": ["requests"], "runtime_class": "remote_api", "access_modes": ["api_access"], "credential_env_vars": []},
    ]},
    "materials_science": {"connectors": [
        {"plugin_id": "materials_project_api_contract", "display_name": "Materials Project API task contract", "packages": ["mp-api"], "runtime_class": "remote_api", "access_modes": ["api_access"], "credential_env_vars": ["MP_API_KEY"]},
    ]},
    "machine_learning": {"methods": [
        {"plugin_id": "pytorch_gpu_training_contract", "display_name": "PyTorch GPU training task contract", "packages": ["torch"], "runtime_class": "gpu_model", "credential_env_vars": []},
        {"plugin_id": "ray_remote_training_contract", "display_name": "Ray remote training task contract", "packages": ["ray"], "runtime_class": "remote_server", "credential_env_vars": ["RAY_ADDRESS"]},
    ]},
    "quantum_science": {"connectors": [
        {"plugin_id": "ibm_quantum_backend_contract", "display_name": "IBM Quantum backend task contract", "packages": ["qiskit-ibm-runtime"], "runtime_class": "remote_api", "access_modes": ["api_access"], "credential_env_vars": ["IBM_QUANTUM_TOKEN"]},
    ]},
    "physics": {"methods": [
        {"plugin_id": "remote_simulation_cluster_contract", "display_name": "Remote simulation-cluster task contract", "packages": [], "runtime_class": "remote_server", "credential_env_vars": ["SIMULATION_CLUSTER_HOST"]},
    ]},
}


def _safe_module(package: str) -> str:
    mapping = {
        "scikit-learn": "sklearn",
        "scikit-bio": "skbio",
        "scikit-survival": "sksurv",
        "umap-learn": "umap",
        "pybids": "bids",
        "biopython": "Bio",
        "cobrapy": "cobra",
        "earthengine-api": "ee",
        "mp-api": "mp_api",
        "qiskit-ibm-runtime": "qiskit_ibm_runtime",
        "zarr": "zarr",
        "rdkit": "rdkit",
    }
    return mapping.get(package, package.replace("-", "_"))


def _manifest(discipline: str, kind: str, plugin_id: str, display_name: str, packages: list[str], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = dict(overrides or {})
    runtime_class = str(overrides.get("runtime_class") or ("local_optional_dependency" if packages else "local_pure_python"))
    validation_level = "mock_validated" if runtime_class in {"remote_api", "remote_server", "gpu_model"} else "fixture_runnable"
    common = {"display_name": display_name, "discipline": discipline, "packages": packages, "package_modules": [_safe_module(package) for package in packages], "maturity": "foundation", "runtime_class": runtime_class, "validation_level": validation_level, "aliases": [plugin_id.replace("_", " ")], "provenance_notes": "First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied."}
    if runtime_class in {"remote_api", "remote_server", "gpu_model"}:
        common.update({"live_execution_performed": False, "task_contract": {"execution_mode": "mock_only", "live_execution_performed": False, "required_user_inputs": list(overrides.get("credential_env_vars") or []), "next_step": "Provide user-authorized credentials, endpoint or compute environment for live validation."}})
    if kind == "data_connectors":
        return common | {"connector_id": plugin_id, "access_modes": ["local_files"], "download_or_access": ["Use parameterized local files or user-authorized exports."], "data_formats": ["csv", "json", "parquet"], "requires_credentials": bool(overrides.get("credential_env_vars")), "genericity_rules": ["Do not store credentials, server locations, or project-specific samples."]} | overrides
    if kind == "method_templates":
        return common | {"template_id": plugin_id, "method_family": plugin_id, "input_roles": ["analysis_table_or_array"], "optional_roles": ["sample_group", "metadata"], "output_artifacts": [f"methods/src/{plugin_id}.py", f"results/tables/{plugin_id}_summary.json"], "figure_groups": ["method_diagnostic_or_result_summary"], "formula_families": [], "validation_checks": ["input_schema_check", "dependency_check", "held_out_or_sensitivity_check"], "genericity_rules": ["Parameterize input columns, units, splits, and scientific hypotheses."]} | overrides
    return common | {"rule_id": plugin_id, "rule_group_id": plugin_id, "rule_family": "discipline_scientific_quality", "criterion_type": "scientific_quality_gate", "applicable_disciplines": [discipline], "evidence_roles": ["method_output", "result_metric"], "evidence_binding": {"registry_record_types": ["result_metric"], "required_fields": ["run_id"], "forbidden_conflicts": []}, "checks": [f"Confirm that {display_name.lower()} is addressed with project-specific evidence."], "threshold_policy": {"mode": "contextual"}, "threshold_source": {"type": "discipline_convention", "citation_or_note": "Foundation rule requires user or literature confirmation before hard blocking."}, "threshold_mode": "contextual", "threshold_validation_status": "candidate_unverified", "blocking_level": "warn_and_repair", "failure_route": "human_checkpoint", "pipeline_hooks": {"result_validity": "advisory"}, "deployment_state": "review_rule_candidate", "human_confirmation_required": True, "review_question": display_name, "scientific_risk": "Unverified or mismatched evidence can overstate a discipline-specific claim.", "minimum_evidence_required": ["method_output", "result_metric"], "allowed_claim_strength": "exploratory", "repair_priority": ["human_checkpoint"]} | overrides


def _template_source(manifest: dict[str, Any], kind: str) -> str:
    payload = repr(manifest)
    if kind == "review_rules":
        function = "def evaluate_rule(evidence=None):\n    return evaluate_local_review_rule(PLUGIN_MANIFEST, evidence)\n"
        imports = "from draftpaper_cli.discipline_modules.local_plugin_runtime import evaluate_local_review_rule\n"
    else:
        function = "def build_template_plan(context=None):\n    return build_local_plugin_plan(PLUGIN_MANIFEST, context)\n\n\ndef run_template(output_dir, fixture_path=None, context=None):\n    return run_local_plugin_fixture(PLUGIN_MANIFEST, output_dir, fixture_path=fixture_path, context=context)\n"
        imports = "from draftpaper_cli.discipline_modules.local_plugin_runtime import build_local_plugin_plan, run_local_plugin_fixture\n"
    return "# Copyright (c) 2026 Jinray Xie\n# Contact: xiejinhui22@mails.ucas.ac.cn\n# Source-available for non-commercial use only; commercial use requires written authorization.\n\nfrom __future__ import annotations\n\n" + imports + "\nPLUGIN_MANIFEST = " + payload + "\n\n" + function


def _write_plugin(discipline: str, kind: str, descriptor: tuple[str, str, list[str]] | dict[str, Any]) -> None:
    if isinstance(descriptor, dict):
        plugin_id = str(descriptor["plugin_id"])
        display_name = str(descriptor["display_name"])
        packages = list(descriptor.get("packages") or [])
        overrides = {key: value for key, value in descriptor.items() if key not in {"plugin_id", "display_name", "packages"}}
    else:
        plugin_id, display_name, packages = descriptor
        overrides = {}
    path = ROOT / discipline / kind / plugin_id
    path.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(discipline, kind, plugin_id, display_name, packages, overrides)
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (path / "fixture_minimal.json").write_text(json.dumps({"plugin_id": plugin_id, "roles": ["analysis_table_or_array", "method_output", "result_metric"]}, indent=2) + "\n", encoding="utf-8")
    (path / "fixture_failure.json").write_text(json.dumps({"plugin_id": plugin_id, "roles": []}, indent=2) + "\n", encoding="utf-8")
    (path / "fixture_boundary.json").write_text(json.dumps({"plugin_id": plugin_id, "boundary": "No credentials, remote endpoint, project record, or private data."}, indent=2) + "\n", encoding="utf-8")
    if manifest["validation_level"] == "mock_validated":
        (path / "fixture_mock_request.json").write_text(json.dumps({"plugin_id": plugin_id, "execution_mode": "mock_only", "live_execution_performed": False, "task_contract": manifest["task_contract"]}, indent=2) + "\n", encoding="utf-8")
    (path / "template.py").write_text(_template_source(manifest, kind), encoding="utf-8")


def main() -> None:
    for discipline, groups in NEW_DISCIPLINES.items():
        for kind, descriptors in groups.items():
            directory = {"connectors": "data_connectors", "methods": "method_templates", "rules": "review_rules"}[kind]
            for descriptor in descriptors:
                _write_plugin(discipline, directory, descriptor)
    for discipline, groups in EXTRA_PLUGINS.items():
        for kind, descriptors in groups.items():
            directory = {"connectors": "data_connectors", "methods": "method_templates", "rules": "review_rules"}[kind]
            for descriptor in descriptors:
                _write_plugin(discipline, directory, descriptor)
    for discipline, groups in EXTERNAL_FOUNDATIONS.items():
        for kind, descriptors in groups.items():
            directory = {"connectors": "data_connectors", "methods": "method_templates", "rules": "review_rules"}[kind]
            for descriptor in descriptors:
                _write_plugin(discipline, directory, descriptor)


if __name__ == "__main__":
    main()
