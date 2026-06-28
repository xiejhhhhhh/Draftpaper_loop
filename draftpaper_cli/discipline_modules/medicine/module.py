# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DataConnectorSpec, DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec


class MedicineModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="medicine",
        display_name="Clinical and biomedical manuscript workflow",
        maturity="runnable",
        keywords=["medicine", "clinical", "patient", "ehr", "cohort", "trial", "survival", "diagnosis", "treatment"],
        data_roles=["patient_id", "index_date", "exposure", "outcome", "covariates", "follow_up_time", "censoring_indicator"],
        method_families=["cohort_construction", "survival_analysis", "propensity_score", "diagnostic_model", "calibration_analysis"],
        validation_checks=["ethics_privacy_check", "missingness_mechanism_check", "external_validation_check", "calibration_check"],
        figure_families=["cohort_flow", "kaplan_meier_curve", "calibration_curve", "decision_curve"],
        formula_families=["hazard_ratio", "odds_ratio", "propensity_score", "calibration_slope"],
        reviewer_risks=["privacy_or_ethics_omission", "unclear_inclusion_criteria", "confounding", "missing_external_validation", "miscalibration"],
        data_connectors=[
            DataConnectorSpec("clinical_trials_registry", "Clinical trial registry metadata", ["api_access", "public_web_download"], [], [], ["ClinicalTrials.gov, WHO ICTRP, or local registry export"], ["json", "csv"], genericity_rules=["Do not claim patient-level access from registry metadata."]),
            DataConnectorSpec("ehr_omop_fhir_manifest", "De-identified EHR manifest via OMOP/FHIR/local tables", ["local_files", "api_access", "remote_server"], [], [], ["OMOP CDM, FHIR export, de-identified local EHR tables"], ["csv", "parquet", "json", "database"], requires_credentials=True, credential_env_vars=["MEDICINE_DATA_ACCESS_TOKEN"], genericity_rules=["Never store patient identifiers or credentials."]),
            DataConnectorSpec("medical_imaging_manifest", "Medical imaging manifest", ["local_files", "remote_server"], ["pydicom", "nibabel"], ["pydicom", "nibabel"], ["DICOM, NIfTI, or de-identified local image manifest"], ["dcm", "nii", "csv"], genericity_rules=["Keep only de-identified paths and modality metadata in manifests."]),
        ],
        method_templates=[
            MethodTemplateSpec("cohort_construction", "Cohort construction with inclusion/exclusion criteria", "medicine", "cohort_construction", ["patient_id", "index_date", "exposure", "outcome"], ["covariates"], ["pandas"], ["pandas"], ["cohort_flow_table", "cohort_flow_figure"], ["cohort_flow"], ["risk_set_definition"], ["inclusion_exclusion_check", "privacy_check"], template_path="method_templates/cohort_construction/template.py", fixture_paths=["method_templates/cohort_construction/fixture_patients.csv"], aliases=["STROBE cohort"], maturity="runnable"),
            MethodTemplateSpec("survival_analysis", "Time-to-event survival analysis", "medicine", "survival_analysis", ["follow_up_time", "event_indicator", "exposure"], ["covariates"], ["lifelines"], ["lifelines"], ["hazard_ratio_table", "kaplan_meier_figure"], ["kaplan_meier_curve"], ["cox_model", "hazard_ratio"], ["proportional_hazards_check", "censoring_check"], aliases=["Cox model", "Kaplan-Meier"]),
            MethodTemplateSpec("propensity_score_adjustment", "Propensity score matching or weighting", "medicine", "propensity_score", ["exposure", "covariates", "outcome"], ["follow_up_time"], ["pandas", "sklearn"], ["pandas", "sklearn"], ["balance_table", "adjusted_effect_table"], ["covariate_balance"], ["propensity_score"], ["balance_check", "positivity_check"], aliases=["PSM", "IPTW"]),
        ],
        review_rule_groups=[
            {"rule_group_id": "ethics_and_privacy_gate", "checks": ["ethics approval, consent/waiver, and de-identification boundary must be stated"]},
            {"rule_group_id": "clinical_cohort_gate", "checks": ["inclusion/exclusion criteria, index date, follow-up, and outcome definition must be explicit"]},
            {"rule_group_id": "clinical_validation_gate", "checks": ["model claims require calibration, missingness discussion, and internal/external validation boundary"]},
        ],
    )


MODULE = MedicineModule()
