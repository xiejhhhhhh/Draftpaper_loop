# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from draftpaper_cli.discipline_modules import get_discipline_module
from draftpaper_cli.template_registry import discover_template_registry


def _ids(discipline: str, key: str, id_key: str) -> set[str]:
    return {str(item[id_key]) for item in get_discipline_module({"discipline": discipline}).spec.as_dict()[key]}


def test_local_foundation_catalog_covers_the_named_local_skill_families() -> None:
    expected = {
        "default": {
            "method_templates": {"statistical_analysis_workbench", "statistical_power_analysis", "experimental_design_planner", "pymoo_multiobjective_optimization", "polars_dataframe_transform", "vaex_out_of_core_table", "dask_local_parallel_analysis", "zarr_chunked_array_analysis", "matplotlib_publication_figure", "seaborn_statistical_plotting", "networkx_graph_analysis"},
            "review_rule_groups": {"statistical_assumption_gate", "statistical_power_gate", "experimental_design_gate", "peer_review_evidence_gate", "rigor_reviewer_reproducibility_gate", "nature_reporting_completeness_gate"},
        },
        "bioinformatics": {
            "method_templates": {"anndata_qc_normalization", "biopython_sequence_qc", "bulk_rnaseq_differential_expression", "cobrapy_flux_balance", "deeptools_coverage_profile", "etetoolkit_phylogeny", "flowio_cytometry_qc", "pydeseq2_differential_expression", "pysam_alignment_qc", "scanpy_cpu_clustering", "scikit_bio_diversity", "scvelo_rna_velocity"},
        },
        "geography": {"method_templates": {"coordinate_reference_harmonization", "local_geometric_overlay", "raster_vector_zonal_feature_extraction"}},
        "astronomy": {"method_templates": {"wcs_coordinate_transform", "time_scale_normalization", "unit_safe_quantity_conversion"}},
        "physics": {"method_templates": {"fluidsim_cpu_simulation"}},
        "quantum_science": {"method_templates": {"cirq_local_circuit_simulation"}},
        "chemistry": {"method_templates": {"molfeat_molecular_embedding"}},
        "medicine": {"method_templates": {"bids_dataset_validation", "pydicom_metadata_qc", "neurokit2_signal_features", "scikit_survival_time_to_event"}},
    }
    for discipline, categories in expected.items():
        for category, required in categories.items():
            id_key = "rule_group_id" if category == "review_rule_groups" else "template_id"
            assert required <= _ids(discipline, category, id_key), discipline


def test_external_foundations_are_mock_validated_and_never_claim_live_execution() -> None:
    external = [
        entry for entry in discover_template_registry()["entries"]
        if entry["runtime_class"] in {"remote_api", "remote_server", "gpu_model"}
    ]
    assert len(external) >= 10
    assert all(entry["validation_level"] == "mock_validated" for entry in external)
    assert all((entry["manifest_data"] or {}).get("live_execution_performed") is False for entry in external)
    assert all((entry["manifest_data"] or {}).get("task_contract") for entry in external)
    assert all(
        not (entry["manifest_data"] or {}).get("credential_env_vars")
        or (entry["manifest_data"] or {}).get("requires_credentials", True)
        for entry in external
    )


def test_external_template_executes_only_a_mock_task_contract() -> None:
    path = Path("draftpaper_cli/discipline_modules/astronomy/data_connectors/photon_archive_api_contract/template.py")
    spec = importlib.util.spec_from_file_location("photon_archive_api_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        result = module.run_template(Path(tmp), fixture_path=path.parent / "fixture_mock_request.json")
    assert result["plan"]["execution_mode"] == "mock_contract_only"
    assert result["plan"]["live_execution_performed"] is False
