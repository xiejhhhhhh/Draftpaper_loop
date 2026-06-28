# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DisciplineModule, DisciplineModuleSpec


class BioinformaticsModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="bioinformatics",
        display_name="Bioinformatics and public omics repositories",
        keywords=["bioinformatics", "omics", "gene expression", "geo", "sra", "ena", "fastq", "fasta"],
        data_roles=["sample_metadata", "expression_or_sequence_matrix", "case_control_or_phenotype_label", "batch_or_platform", "quality_flag"],
        method_families=["public_repository_import", "sample_qc", "differential_or_feature_analysis", "batch_effect_check", "pathway_or_annotation_summary"],
        validation_checks=["metadata_completeness_check", "sample_qc_check", "batch_effect_check", "replicate_or_group_balance_check"],
        figure_families=["sample_metadata_overview", "qc_distribution", "expression_or_feature_structure", "differential_signal_summary", "annotation_or_pathway_summary"],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=["data_overview", "sample_qc", "feature_structure", "differential_or_signal_summary", "annotation_summary"],
        formula_families=["normalization", "differential_statistic", "multiple_testing", "effect_size"],
        reviewer_risks=["metadata_incomplete", "batch_effect_uncontrolled", "qc_threshold_unclear", "multiple_testing_missing"],
        code_generation_constraints=[
            "Require sample metadata and phenotype labels before differential or supervised biological claims.",
            "Do not download large sequence archives without explicit user confirmation.",
        ],
        data_connectors=[
            {
                "connector_id": "geo_sra_ena_api",
                "display_name": "GEO/SRA/ENA public repository access",
                "access_modes": ["api_access", "remote_server_ssh"],
                "packages": ["requests", "biopython", "pysradb"],
                "package_modules": ["requests", "Bio", "pysradb"],
                "download_or_access": ["query GEO/SRA/ENA metadata", "download sample sheets", "prepare accession manifest", "optionally fetch processed matrices"],
                "data_formats": ["SOFT", "MINiML", "SRA run table", "FASTQ manifest", "CSV/TSV metadata", "expression matrix"],
                "requires_credentials": False,
            },
            {
                "connector_id": "remote_omics_server",
                "display_name": "Remote omics processing server",
                "access_modes": ["remote_server_ssh"],
                "packages": ["paramiko", "scp"],
                "package_modules": ["paramiko", "scp"],
                "credential_env_vars": ["DRAFTPAPER_SSH_HOST", "DRAFTPAPER_SSH_USER"],
                "download_or_access": ["create remote sample manifest", "run server-side QC/quantification", "download processed count matrices and QC reports"],
                "data_formats": ["FASTQ manifest", "count matrix", "QC HTML/PDF", "CSV/TSV"],
                "requires_credentials": True,
            },
        ],
    )


MODULE = BioinformaticsModule()
