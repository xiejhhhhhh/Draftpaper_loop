# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DataConnectorSpec, DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec


class BiologyModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="biology",
        display_name="General biology and molecular-analysis workflow",
        maturity="runnable",
        keywords=["biology", "gene", "protein", "assay", "cell", "differential expression", "pathway", "replicate"],
        data_roles=["sample_id", "condition", "biological_replicate", "feature_id", "measurement", "batch"],
        method_families=["differential_expression", "enrichment_analysis", "assay_qc", "protein_feature_analysis", "replicate_validation"],
        validation_checks=["biological_replicate_check", "batch_effect_check", "multiple_testing_check", "negative_positive_control_check"],
        figure_families=["volcano_plot", "heatmap", "pathway_enrichment", "qc_distribution"],
        formula_families=["fold_change", "fdr_adjustment", "enrichment_score"],
        reviewer_risks=["insufficient_replicates", "batch_effect", "multiple_testing_without_fdr", "missing_controls", "overstated_biological_validation"],
        data_connectors=[
            DataConnectorSpec("public_sequence_repository", "Public sequence or expression repository", ["api_access", "public_web_download"], [], [], ["GEO, SRA, ENA, ArrayExpress, or local accession manifest"], ["fastq", "fasta", "csv", "h5ad"], genericity_rules=["Store accession ids and manifests, not private raw data."]),
            DataConnectorSpec("protein_annotation_database", "Protein and gene annotation database", ["api_access", "public_web_download"], [], [], ["UniProt, Ensembl, NCBI, KEGG, GO, Reactome"], ["json", "tsv", "gff", "gtf"], genericity_rules=["Expose organism/build/version as parameters."]),
            DataConnectorSpec("local_assay_table", "Local de-identified assay table", ["local_files"], [], [], ["qPCR, ELISA, imaging, or plate-reader export"], ["csv", "xlsx", "tsv"], genericity_rules=["Keep sample labels generic and preserve replicate metadata."]),
        ],
        method_templates=[
            MethodTemplateSpec("differential_expression", "Differential expression or measurement comparison", "biology", "differential_expression", ["feature_id", "measurement", "condition", "replicate"], ["batch"], ["pandas", "statsmodels"], ["pandas", "statsmodels"], ["differential_table", "volcano_plot"], ["volcano_plot", "effect_size_distribution"], ["fold_change", "fdr_adjustment"], ["replicate_check", "multiple_testing_fdr_check"], template_path="method_templates/differential_expression/template.py", fixture_paths=["method_templates/differential_expression/fixture_expression.csv"], aliases=["DE analysis"], maturity="runnable"),
            MethodTemplateSpec("pathway_enrichment", "Pathway or ontology enrichment analysis", "biology", "enrichment_analysis", ["feature_list", "background_set"], ["organism"], [], [], ["enrichment_table", "pathway_barplot"], ["pathway_enrichment"], ["enrichment_score"], ["background_set_check", "fdr_check"], aliases=["GO enrichment", "KEGG enrichment"]),
            MethodTemplateSpec("assay_quality_control", "Assay QC and replicate consistency", "biology", "assay_qc", ["sample_id", "measurement", "replicate"], ["plate_id", "batch"], ["pandas", "numpy"], ["pandas", "numpy"], ["qc_table", "replicate_consistency_figure"], ["qc_distribution", "replicate_consistency"], ["coefficient_of_variation"], ["control_check", "batch_effect_check"], aliases=["biological replicate QC"]),
        ],
        review_rule_groups=[
            {"rule_group_id": "multiple_testing_fdr_gate", "checks": ["large feature-set claims require FDR or equivalent multiple-testing control"]},
            {"rule_group_id": "biological_replicate_gate", "checks": ["biological and technical replicates must be distinguished"]},
            {"rule_group_id": "batch_control_gate", "checks": ["batch, plate, donor, or sequencing-run effects must be assessed when present"]},
        ],
    )


MODULE = BiologyModule()
