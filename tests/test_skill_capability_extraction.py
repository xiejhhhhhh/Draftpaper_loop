# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SkillCapabilityExtractionTests(unittest.TestCase):
    def test_review_rule_spec_is_normalized_in_module_hints(self) -> None:
        from draftpaper_cli.discipline_modules.base import DisciplineModuleSpec, PaperContractSpec, ReviewRuleSpec, WorkflowRecipeSpec

        spec = DisciplineModuleSpec(
            module_id="test",
            display_name="Test",
            review_rule_groups=[
                ReviewRuleSpec(
                    rule_id="contextual_auc_gate",
                    display_name="Contextual AUC gate",
                    rule_family="model_validity",
                    criterion_type="model_quality_condition",
                    applicable_disciplines=["machine_learning"],
                    evidence_roles=["model_metric_evidence"],
                    evidence_binding={
                        "registry_record_types": ["metric"],
                        "required_fields": ["model_metric_evidence"],
                        "forbidden_conflicts": ["train_test_leakage"],
                    },
                    metric_family="auc",
                    threshold_policy={"mode": "contextual"},
                    threshold_source={"type": "benchmark_comparison", "citation_or_note": "compare with baseline"},
                    threshold_mode="contextual",
                    threshold_validation_status="comparative_context_required",
                    failure_route="method_rescue",
                    pipeline_hooks={"method_plan": "required", "result_support_checkpoint": "required"},
                    positive_fixture_refs=["positive_fixture.json"],
                    negative_fixture_refs=["negative_fixture.json"],
                    backflow_source_type="workflow_recipe",
                    support_layer_signal_refs=[{"source_type": "workflow_recipe", "rule_family": "model_validity"}],
                    aliases=["auc_gate"],
                    variants=["ml_auc_contextual"],
                ),
                {"rule_group_id": "legacy_gate", "display_name": "Legacy gate", "checks": ["legacy_check"]},
            ],
        )
        rules = spec.review_rule_dicts()
        self.assertEqual(rules[0]["rule_group_id"], "contextual_auc_gate")
        self.assertEqual(rules[0]["rule_family"], "model_validity")
        self.assertEqual(rules[0]["criterion_type"], "model_quality_condition")
        self.assertEqual(rules[0]["pipeline_hooks"]["method_plan"], "required")
        self.assertEqual(rules[0]["threshold_mode"], "contextual")
        self.assertEqual(rules[0]["threshold_validation_status"], "comparative_context_required")
        self.assertEqual(rules[0]["maturity"], "candidate")
        self.assertEqual(rules[0]["deployment_state"], "review_rule_candidate")
        self.assertTrue(rules[0]["human_confirmation_required"])
        self.assertEqual(rules[0]["evidence_binding"]["registry_record_types"], ["metric"])
        self.assertEqual(rules[0]["positive_fixture_refs"], ["positive_fixture.json"])
        self.assertEqual(rules[0]["negative_fixture_refs"], ["negative_fixture.json"])
        self.assertEqual(rules[0]["backflow_source_type"], "workflow_recipe")
        self.assertEqual(rules[0]["support_layer_signal_refs"][0]["source_type"], "workflow_recipe")
        self.assertEqual(rules[0]["aliases"], ["auc_gate"])
        self.assertEqual(rules[0]["variants"], ["ml_auc_contextual"])
        self.assertEqual(rules[1]["rule_id"], "legacy_gate")
        self.assertEqual(rules[1]["threshold_policy"]["mode"], "contextual")
        self.assertEqual(rules[1]["threshold_mode"], "contextual")
        self.assertEqual(rules[1]["criterion_type"], "scientific_quality_gate")
        self.assertEqual(rules[1]["pipeline_hooks"], {})
        self.assertEqual(rules[1]["deployment_state"], "promoted_review_rule")
        self.assertIn("evidence_binding", rules[1])
        self.assertEqual(rules[1]["backflow_source_type"], "explicit_review")
        self.assertEqual(rules[1]["support_layer_signal_refs"], [])

        workflow = WorkflowRecipeSpec(
            recipe_id="ml_result_rescue",
            display_name="ML result rescue",
            applicable_disciplines=["machine_learning"],
            orchestrates=["method_template", "review_rule"],
            failure_routes=["method_rescue", "result_downgrade"],
            review_rule_backflow_ids=["split_leakage_gate"],
        ).as_dict()
        self.assertEqual(workflow["support_type"], "workflow_recipe")
        self.assertFalse(workflow["promotion_allowed"])
        self.assertEqual(workflow["deployment_target"], "draftpaper_cli/pipeline_recipes/")

        contract = PaperContractSpec(
            contract_id="citation_claim_scope",
            display_name="Citation claim scope",
            applicable_sections=["results", "discussion"],
            required_evidence=["citation_usage"],
            repair_routes=["citation_repair", "manuscript_repair"],
        ).as_dict()
        self.assertEqual(contract["support_type"], "paper_contract")
        self.assertFalse(contract["promotion_allowed"])
        self.assertEqual(contract["deployment_target"], "draftpaper_cli/paper_contracts/")

    def test_extract_skill_capabilities_backflows_support_skill_to_review_rules(self) -> None:
        from draftpaper_cli.plugin_candidates import (
            PluginCandidateError,
            extract_skill_capabilities,
            generalize_plugin_candidate,
            package_plugin_contribution,
            preflight_plugin_contribution_package,
            promote_plugin_candidate,
            review_plugin_contribution_package,
            validate_plugin_candidate,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "SKILL.md"
            skill.write_text(
                """
# Model evaluation workflow

Use machine learning baselines, ablation studies, held-out train validation test split,
data leakage checks, calibration, AUC/F1 comparison, and figure caption checks.
Report confidence interval, p-value only with context, data/code availability, random seed,
environment versions, smoke test fixtures, and manuscript claim scope.
""",
                encoding="utf-8",
            )
            result = extract_skill_capabilities(
                skill,
                source="academicforge",
                skill_id="ml.model-evaluation-workflow",
                discipline="machine_learning",
                output_root=root / "out",
            )
            self.assertEqual(result["status"], "written")
            self.assertIn("workflow_recipe", result["support_routes"])
            self.assertGreaterEqual(result["support_candidate_count"], 1)
            self.assertGreaterEqual(result["candidate_count"], 3)
            self.assertGreaterEqual(result["capability_record_count"], result["candidate_count"])
            self.assertTrue(result["capability_records"])
            support_candidate = Path(result["support_candidates"][0]["path"])
            support_manifest = json.loads((support_candidate / "support_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(support_manifest["candidate_kind"], "support_candidate")
            self.assertFalse(support_manifest["promotion_allowed"])
            self.assertEqual(support_manifest["deployment_state"], "support_only")
            self.assertIn("model_validity", support_manifest["review_rule_backflow_scope"])
            self.assertEqual(support_manifest["capability_ir"]["capability_kind"], "support_layer_candidate")
            self.assertIn("ml_model_evaluation_workflow_model_validity", support_manifest["review_rule_backflow_candidate_ids"])
            self.assertEqual(support_manifest["backflow_signal_scan"]["scan_version"], "review_rule_signal_scan.v1")
            self.assertIn("model_validity", support_manifest["backflow_signal_scan"]["families"])
            self.assertIn("model_validity", support_manifest["backflow_signal_scan"]["eligible_rule_families"])
            self.assertIn("review_rule_signal_scan", support_manifest["capability_ir"])
            self.assertIn("model_validity", support_manifest["capability_ir"]["review_rule_signal_scan"]["families"])
            self.assertIn("review_rule_backflow_scope", result["support_candidates"][0])
            self.assertEqual(result["support_candidates"][0]["capability_ir"]["support_type"], support_manifest["support_type"])
            backflow_links = json.loads((support_candidate / "review_rule_backflow_links.json").read_text(encoding="utf-8"))
            self.assertFalse(backflow_links["promotion_allowed"])
            self.assertIn("ml_model_evaluation_workflow_model_validity", backflow_links["backflow_review_rule_ids"])
            self.assertIn("model_validity", backflow_links["backflow_scope"])
            self.assertEqual(backflow_links["backflow_signal_scan"]["scan_version"], "review_rule_signal_scan.v1")
            self.assertIn("model_validity", backflow_links["backflow_signal_scan"]["families"])
            families = {item["rule_family"] for item in result["candidates"] if item["plugin_type"] == "review_rule"}
            self.assertIn("model_validity", families)
            self.assertIn("statistical_validity", families)
            self.assertIn("citation_and_manuscript_validity", families)

            candidate = Path(next(item["path"] for item in result["candidates"] if item.get("rule_family") == "model_validity"))
            manifest = json.loads((candidate / "candidate_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["plugin_type"], "review_rule")
            self.assertEqual(manifest["criterion_type"], "model_quality_condition")
            self.assertEqual(manifest["threshold_policy"]["mode"], "comparative")
            self.assertEqual(manifest["threshold_mode"], "comparative")
            self.assertEqual(manifest["threshold_validation_status"], "comparative_context_required")
            self.assertEqual(manifest["pipeline_hooks"]["method_plan"], "required")
            self.assertEqual(manifest["pipeline_hooks"]["result_support_checkpoint"], "required")
            self.assertEqual(manifest["maturity"], "candidate")
            self.assertEqual(manifest["deployment_state"], "review_rule_candidate")
            self.assertTrue(manifest["human_confirmation_required"])
            self.assertTrue(manifest["review_question"])
            self.assertTrue(manifest["scientific_risk"])
            self.assertIn("model_validity_evidence", manifest["minimum_evidence_required"])
            self.assertIn("model_validity_evidence", manifest["evidence_binding"]["required_fields"])
            self.assertIn("metric", manifest["evidence_binding"]["registry_record_types"])
            self.assertEqual(manifest["positive_fixture_refs"], ["positive_fixture.json"])
            self.assertEqual(manifest["negative_fixture_refs"], ["negative_fixture.json"])
            self.assertEqual(manifest["backflow_source_type"], "workflow_recipe")
            self.assertEqual(manifest["support_layer_signal_refs"][0]["source_type"], "workflow_recipe")
            self.assertEqual(manifest["support_layer_signal_refs"][0]["rule_family"], "model_validity")
            self.assertIn("model_validity", manifest["aliases"])
            self.assertTrue(manifest["variants"])
            self.assertEqual(manifest["allowed_claim_strength"], "predictive")
            self.assertTrue(manifest["repair_priority"])
            self.assertEqual(manifest["capability_ir"]["formal_plugin_type"], "review_rule")
            self.assertEqual(manifest["review_rule_signal_scan"]["rule_family"], "model_validity")
            self.assertTrue(manifest["review_rule_signal_scan"]["core_ready"])
            self.assertTrue(manifest["review_rule_signal_scan"]["evidence_bound"])
            self.assertIn(manifest["backflow_recommendation"], {"review_rule_candidate", "contextual_or_human_confirmed_candidate"})
            self.assertIn("evidence_binding", manifest["signal_dimensions"])
            self.assertIn("review_rule_signal_scan", manifest["capability_ir"])
            self.assertEqual(manifest["capability_ir"]["review_rule_signal_scan"]["rule_family"], "model_validity")
            self.assertTrue((candidate / "rule_rationale.md").exists())
            self.assertIn("Signal Scan", (candidate / "rule_rationale.md").read_text(encoding="utf-8"))
            self.assertTrue((candidate / "positive_fixture.json").exists())
            self.assertTrue((candidate / "negative_fixture.json").exists())
            self.assertIn("draftpaper_cli/discipline_modules/machine_learning/review_rules", manifest["intended_merge_target"])

            generalize_plugin_candidate(candidate)
            validation = validate_plugin_candidate(candidate)
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(validation["schema_report"]["plugin_type"], "review_rule")
            self.assertIn("positive_fixture.json", validation["fixture_test_report"]["checked_files"])
            self.assertEqual(validation["fixture_test_report"]["validation_level"], "synthetic_contract")
            self.assertFalse(validation["fixture_test_report"]["runtime_execution_performed"])
            self.assertFalse(validation["fixture_test_report"]["problems"])
            generalized_rule = json.loads((candidate / "generalized_template" / "review_rule.json").read_text(encoding="utf-8"))
            generalized_template = (candidate / "generalized_template" / "template.py").read_text(encoding="utf-8")
            self.assertIn("'source_text_copied': False", generalized_template)
            self.assertNotIn("Use CSV table data and scikit-learn", generalized_template)
            self.assertEqual(generalized_rule["deployment_state"], "review_rule_candidate")
            self.assertEqual(generalized_rule["criterion_type"], "model_quality_condition")
            self.assertEqual(generalized_rule["threshold_mode"], "comparative")
            self.assertEqual(generalized_rule["threshold_validation_status"], "comparative_context_required")
            self.assertTrue(generalized_rule["review_question"])
            self.assertIn("method_rescue", generalized_rule["repair_priority"])
            self.assertIn("evidence_binding", generalized_rule)
            self.assertEqual(generalized_rule["positive_fixture_refs"], ["positive_fixture.json"])
            self.assertEqual(generalized_rule["negative_fixture_refs"], ["negative_fixture.json"])
            self.assertEqual(generalized_rule["backflow_source_type"], "workflow_recipe")
            self.assertEqual(generalized_rule["support_layer_signal_refs"][0]["source_type"], "workflow_recipe")
            with self.assertRaises(PluginCandidateError):
                validate_plugin_candidate(support_candidate)
            with self.assertRaises(PluginCandidateError):
                promote_plugin_candidate(support_candidate, require_human_confirmation=True)
            with self.assertRaises(PluginCandidateError):
                package_plugin_contribution(support_candidate)

            with self.assertRaises(PluginCandidateError):
                promote_plugin_candidate(candidate, require_human_confirmation=True, dry_run=True, target_root=root / "discipline_modules")
            packaged = package_plugin_contribution(candidate)
            package_dir = Path(packaged["package_dir"])
            self.assertTrue((package_dir / "PROVENANCE_AND_BACKFLOW.json").exists())
            self.assertTrue((package_dir / "PROVENANCE_AND_BACKFLOW.md").exists())
            self.assertTrue((package_dir / "rule_rationale.md").exists())
            self.assertTrue((package_dir / "positive_fixture.json").exists())
            self.assertTrue((package_dir / "negative_fixture.json").exists())
            self.assertFalse((package_dir / "source_evidence_summary.md").exists())
            provenance = json.loads((package_dir / "PROVENANCE_AND_BACKFLOW.json").read_text(encoding="utf-8"))
            self.assertIn("workflow_recipe", provenance["backflow_from_support_routes"])
            self.assertTrue(provenance["support_candidates"][0]["review_rule_backflow_scope"])
            self.assertIn("backflow_signal_scan", provenance["support_candidates"][0])
            self.assertIn("model_validity", provenance["support_candidates"][0]["backflow_signal_scan"]["families"])
            self.assertIn("metadata_only", provenance["source_policy"])

            preflight = preflight_plugin_contribution_package(package_dir)
            self.assertEqual(preflight["status"], "passed")
            self.assertFalse(preflight["promotion_allowed_by_preflight"])
            self.assertTrue((package_dir / "PLUGIN_CONTRIBUTION_PREFLIGHT.json").exists())
            self.assertTrue((package_dir / "CONTRIBUTOR_CHECKLIST.md").exists())
            self.assertTrue((package_dir / "GITHUB_ACTIONS_PREFLIGHT.md").exists())
            child_preflight = preflight_plugin_contribution_package(package_dir / "generalized_template")
            self.assertEqual(child_preflight["status"], "passed")
            self.assertEqual(Path(child_preflight["resolved_package_dir"]), package_dir)
            review = review_plugin_contribution_package(package_dir / "generalized_template")
            self.assertEqual(review["status"], "written")
            self.assertEqual(review["maintainer_recommendation"], "ready_for_human_review")
            self.assertEqual(review["plugin_type"], "review_rule")
            self.assertTrue(review["metadata_only_source"])
            self.assertIn("workflow_recipe", review["backflow_from_support_routes"])
            self.assertIn("model_validity", review["backflow_rule_families"])
            self.assertEqual(review["threshold_mode"], "comparative")
            self.assertEqual(review["threshold_validation_status"], "comparative_context_required")
            self.assertTrue(review["human_confirmation_required"])
            self.assertIn("rule_rationale.md", review["files_to_review"])
            self.assertTrue((package_dir / "PLUGIN_CONTRIBUTION_REVIEW.json").exists())
            self.assertTrue((package_dir / "PLUGIN_CONTRIBUTION_REVIEW.md").exists())

            (package_dir / "SKILL.md").write_text("third-party source text should not be packaged", encoding="utf-8")
            failed_preflight = preflight_plugin_contribution_package(package_dir)
            self.assertEqual(failed_preflight["status"], "failed")
            self.assertIn("forbidden_source_or_binary_files", failed_preflight["problems"])
            failed_review = review_plugin_contribution_package(package_dir)
            self.assertEqual(failed_review["maintainer_recommendation"], "fix_required")

    def test_extract_skill_capabilities_writes_data_method_and_review_candidates(self) -> None:
        from draftpaper_cli.plugin_candidates import (
            extract_skill_capabilities,
            generalize_plugin_candidate,
            validate_plugin_candidate,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "SKILL.md"
            skill.write_text(
                """
# Astronomy time-series skill

Query an astronomy archive API for FITS light curve catalog data, cache CSV summaries,
then train a Transformer deep learning classifier with baseline, ablation, held-out split,
F1/AUC metrics, calibration checks, and caption/claim consistency review.
""",
                encoding="utf-8",
            )
            result = extract_skill_capabilities(
                skill,
                source="academicforge",
                skill_id="astronomy.time-series-classification",
                discipline="astronomy",
                output_root=root / "out",
            )
            self.assertEqual(result["status"], "written")
            plugin_types = {item["plugin_type"] for item in result["candidates"]}
            self.assertIn("data_connector", plugin_types)
            self.assertIn("method_template", plugin_types)
            self.assertIn("review_rule", plugin_types)
            self.assertGreaterEqual(result["support_candidate_count"], 1)

            data_candidates = [Path(item["path"]) for item in result["candidates"] if item["plugin_type"] == "data_connector"]
            data_candidate = next(
                candidate for candidate in data_candidates
                if "fits" in [str(item).lower() for item in json.loads((candidate / "candidate_manifest.json").read_text(encoding="utf-8"))["data_formats"]]
            )
            data_manifest = json.loads((data_candidate / "candidate_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(data_manifest["source_policy"], "candidate_only_no_direct_upload")
            self.assertIn("fits", [str(item).lower() for item in data_manifest["data_formats"]])
            generalize_plugin_candidate(data_candidate)
            data_validation = validate_plugin_candidate(data_candidate)
            self.assertEqual(data_validation["status"], "passed")
            self.assertEqual(data_validation["schema_report"]["plugin_type"], "data_connector")
            self.assertTrue((data_candidate / "generalized_template" / "data_connector.json").exists())

            method_candidate = Path(next(item["path"] for item in result["candidates"] if item["plugin_type"] == "method_template"))
            generalize_plugin_candidate(method_candidate)
            method_validation = validate_plugin_candidate(method_candidate)
            self.assertEqual(method_validation["status"], "passed")
            self.assertTrue((method_candidate / "generalized_template" / "method_template.json").exists())

    def test_compile_skill_source_batch_writes_candidate_reports(self) -> None:
        from draftpaper_cli.plugin_candidates import compile_skill_source

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "geo" / "SKILL.md").parent.mkdir(parents=True)
            (root / "geo" / "SKILL.md").write_text(
                "Use Google Earth Engine API raster GeoTIFF data, CRS checks, spatial block validation, residual diagnostics, and figure caption claim review.",
                encoding="utf-8",
            )
            (root / "ml.md").write_text(
                "Build machine learning baselines, ablation studies, train validation test split checks, calibration, AUC/F1 metrics, and reproducibility smoke test fixtures.",
                encoding="utf-8",
            )
            report = compile_skill_source(
                root,
                source="academicforge",
                discipline="auto",
                output_root=root / "compiled",
            )
            self.assertEqual(report["status"], "written")
            self.assertEqual(report["source_file_count"], 2)
            self.assertGreaterEqual(report["candidate_count"], 3)
            self.assertGreaterEqual(report["support_candidate_count"], 2)
            self.assertIn("workflow_recipe", report["support_type_counts"])
            self.assertGreaterEqual(report["capability_record_count"], report["candidate_count"])
            self.assertTrue(any(item["capability_kind"] == "support_layer_candidate" for item in report["capability_records"]))
            self.assertGreaterEqual(report["review_rule_backflow_count"], 2)
            self.assertTrue(report["support_backflow_records"])
            self.assertTrue(report["support_backflow_records"][0]["review_rule_backflow_scope"])
            self.assertTrue(report["support_backflow_records"][0]["capability_ir"])
            self.assertTrue(report["discipline_review_rule_counts"])
            self.assertTrue((root / "compiled" / "COMPILE_SKILL_SOURCE_REPORT.json").exists())
            self.assertTrue((root / "compiled" / "SKILL_INDEX.json").exists())
            self.assertTrue((root / "compiled" / "DISCIPLINE_GAP_REPORT.md").exists())
            gap_report = (root / "compiled" / "DISCIPLINE_GAP_REPORT.md").read_text(encoding="utf-8")
            self.assertIn("Support Candidate Counts", gap_report)
            self.assertIn("Support Candidates With Review Rule Backflow", gap_report)

    def test_skill_source_adapter_writes_metadata_only_reports(self) -> None:
        from draftpaper_cli.plugin_candidates import (
            classify_skill_source,
            extract_review_rule_signals,
            index_skill_source,
            inspect_skill_source,
            map_skill_capabilities,
            snapshot_skill_source,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "astro" / "SKILL.md").parent.mkdir(parents=True)
            (root / "skills" / "astro" / "SKILL.md").write_text(
                """
# Astronomy archive workflow

Use astropy and astroquery to query FITS light curve catalogs. Validate time-series
classification with held-out source-level splits, AUC/F1 metrics, baseline models,
ablation studies, figure-caption claim checks, and reproducibility smoke tests.
""",
                encoding="utf-8",
            )
            (root / "skills" / "writing.md").write_text(
                "# Paper claim contract\nCheck citation support, claim scope, data availability, and manuscript section leakage.",
                encoding="utf-8",
            )
            out = root / "adapter"

            snapshot = snapshot_skill_source(
                root / "skills",
                source="academicforge",
                source_url="https://example.invalid/repo",
                source_ref="test-ref",
                output_root=out,
            )
            self.assertEqual(snapshot["status"], "written")
            self.assertTrue(snapshot["metadata_only"])
            self.assertFalse(snapshot["source_files_copied"])
            self.assertEqual(snapshot["file_count"], 2)
            self.assertIn("sha256", snapshot["records"][0])
            self.assertTrue((out / "SNAPSHOT.json").exists())
            self.assertTrue((out / "LICENSE_AUDIT_REPORT.md").exists())

            inspection = inspect_skill_source(root / "skills", source="academicforge", output_root=out)
            self.assertEqual(inspection["status"], "written")
            self.assertGreaterEqual(inspection["formal_plugin_type_file_counts"]["review_rule"], 1)
            self.assertIn("astropy", inspection["package_counts"])
            self.assertTrue((out / "SKILL_SOURCE_INSPECTION.json").exists())
            self.assertTrue((out / "source_inspection.json").exists())

            index = index_skill_source(root / "skills", source="academicforge", discipline="auto", output_root=out)
            self.assertEqual(index["skill_count"], 2)
            self.assertGreaterEqual(index["review_rule_backflow_family_count"], 1)
            self.assertGreater(index["capability_record_count"], 0)
            self.assertTrue(index["capability_records"])
            self.assertTrue(index["skills"][0]["capability_ir_records"])
            self.assertTrue(any(item["formal_plugin_type"] == "review_rule" for item in index["capability_records"]))
            self.assertTrue(any(item["capability_kind"] == "support_layer_candidate" for item in index["capability_records"]))
            index_review_records = [item for item in index["capability_records"] if item["formal_plugin_type"] == "review_rule"]
            self.assertTrue(any(item.get("review_rule_signal_scan") for item in index_review_records))
            self.assertTrue(any((item.get("review_rule_signal_scan") or {}).get("core_ready") for item in index_review_records))
            index_support_records = [item for item in index["capability_records"] if item["capability_kind"] == "support_layer_candidate"]
            self.assertTrue(any(item.get("review_rule_signal_scan") for item in index_support_records))
            self.assertIn("candidate_generation_command", index["skills"][0])
            self.assertTrue((out / "SKILL_SOURCE_INDEX.json").exists())
            self.assertTrue((out / "SKILL_INDEX.json").exists())

            classification = classify_skill_source(root / "skills", source="academicforge", discipline="auto", output_root=out)
            dispositions = {record["disposition"] for record in classification["records"]}
            self.assertIn("formal_candidate_source", dispositions)
            self.assertGreater(classification["capability_record_count"], 0)
            self.assertTrue(classification["records"][0]["capability_ir_records"])
            self.assertTrue(all(record["promotion_allowed"] is False for record in classification["records"]))
            self.assertTrue(any(
                (item.get("review_rule_signal_scan") or {}).get("core_ready")
                for record in classification["records"]
                for item in record["capability_ir_records"]
                if item.get("formal_plugin_type") == "review_rule"
            ))
            self.assertTrue((out / "SKILL_SOURCE_CLASSIFICATION.json").exists())
            self.assertTrue((out / "SKILL_DISPOSITION.json").exists())

            capability_map = map_skill_capabilities(root / "skills", source="academicforge", discipline="auto", output_root=out)
            self.assertFalse(capability_map["deployment_policy"]["promotion_allowed_by_this_command"])
            self.assertIn("review_rule", capability_map["deployment_policy"]["formal_discipline_plugin_types"])
            self.assertGreater(capability_map["capability_record_count"], 0)
            self.assertTrue(capability_map["capability_records"])
            self.assertTrue(any(item["formal_plugin_type"] == "review_rule" for item in capability_map["capability_records"]))
            self.assertTrue(any(item["capability_kind"] == "support_layer_candidate" for item in capability_map["capability_records"]))
            self.assertTrue(any(
                (item.get("review_rule_signal_scan") or {}).get("core_ready")
                for item in capability_map["capability_records"]
                if item.get("formal_plugin_type") == "review_rule"
            ))
            self.assertTrue(any(record["review_rule_backflow_possible"] for record in capability_map["records"]))
            self.assertTrue(any(record["capability_ir_records"] for record in capability_map["records"]))
            self.assertTrue((out / "SKILL_CAPABILITY_MAP.json").exists())
            self.assertTrue((out / "SKILL_MAPPING.json").exists())
            self.assertTrue((out / "SKILL_MAPPING.yaml").exists())
            self.assertTrue((out / "ACADEMICFORGE_SKILL_MATRIX.md").exists())
            self.assertTrue((out / "DISCIPLINE_GAP_REPORT.md").exists())

            signal_report = extract_review_rule_signals(
                root / "skills",
                source="academicforge",
                discipline="auto",
                output_root=out,
            )
            self.assertEqual(signal_report["status"], "written")
            self.assertGreaterEqual(signal_report["support_backflow_source_count"], 1)
            self.assertGreater(signal_report["capability_record_count"], 0)
            self.assertIn("model_validity", signal_report["review_rule_family_counts"])
            self.assertTrue(any(record["review_rule_backflow_families"] for record in signal_report["records"]))
            self.assertTrue((out / "REVIEW_RULE_SIGNAL_REPORT.json").exists())
            self.assertTrue((out / "review_rule_signal_report.json").exists())
            self.assertTrue((out / "REVIEW_RULE_SIGNAL_REPORT.md").exists())

            source_only = snapshot_skill_source(
                None,
                source="local_skill",
                source_url="https://github.com/HughYau/AcademicForge",
                source_ref="site-first",
                output_root=root / "source_only_snapshot",
            )
            self.assertEqual(source_only["file_count"], 0)
            self.assertIsNone(source_only["source_root"])
            self.assertTrue((root / "source_only_snapshot" / "LICENSE_AUDIT_REPORT.json").exists())

    def test_academicforge_registry_snapshot_generates_metadata_profiles(self) -> None:
        from draftpaper_cli.plugin_candidates import (
            classify_skill_source,
            index_skill_source,
            inspect_skill_source,
            map_skill_capabilities,
            snapshot_skill_source,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "skills.json"
            registry.write_text(json.dumps({
                "skills": [
                    {
                        "id": "ml-eval",
                        "name": "Machine learning evaluation workflow",
                        "summary": {"en": "Baseline, ablation, held-out split, leakage, calibration, AUC/F1, confidence interval, and reproducibility smoke tests."},
                        "repository": "https://example.invalid/ml-eval",
                        "license": "MIT",
                        "tags": ["workflow", "machine-learning", "baseline", "ablation", "leakage"],
                        "install": {"method": "sparse-checkout", "sparse_path": "skills"},
                    },
                    {
                        "id": "astro-fits",
                        "name": "Astropy FITS archive helper",
                        "summary": {"en": "Use astropy and astroquery to query FITS catalog light curve data and validate unit consistency and figure claim scope."},
                        "repository": "https://example.invalid/astro-fits",
                        "license": "BSD-3-Clause",
                        "tags": ["astronomy", "fits", "catalog", "light curve", "api"],
                    },
                ]
            }), encoding="utf-8")
            out = root / "adapter"

            snapshot = snapshot_skill_source(
                None,
                source="academicforge",
                source_url=str(registry),
                source_ref="fixture-ref",
                output_root=out,
            )
            self.assertEqual(snapshot["status"], "written")
            self.assertEqual(snapshot["file_count"], 2)
            self.assertTrue(snapshot["metadata_only"])
            self.assertFalse(snapshot["source_files_copied"])
            derived_root = Path(snapshot["source_root"])
            self.assertTrue((out / "ACADEMICFORGE_REGISTRY_ADAPTER.json").exists())
            self.assertTrue((derived_root / "ml_eval.md").exists())
            self.assertIn("registry metadata only", (derived_root / "ml_eval.md").read_text(encoding="utf-8"))
            self.assertIn("registry_metadata", snapshot["records"][0])

            inspection = inspect_skill_source(derived_root, source="academicforge", output_root=out)
            self.assertGreaterEqual(inspection["formal_plugin_type_file_counts"]["review_rule"], 1)
            index = index_skill_source(derived_root, source="academicforge", discipline="auto", output_root=out)
            self.assertEqual(index["skill_count"], 2)
            self.assertGreater(index["capability_record_count"], 0)
            classification = classify_skill_source(derived_root, source="academicforge", discipline="auto", output_root=out)
            self.assertIn("formal_candidate_source", classification["disposition_counts"])
            capability_map = map_skill_capabilities(derived_root, source="academicforge", discipline="auto", output_root=out)
            self.assertGreater(capability_map["capability_record_count"], 0)
            self.assertTrue((out / "ACADEMICFORGE_SKILL_MATRIX.md").exists())

    def test_academicforge_registry_expands_declared_subskills_without_silent_loss(self) -> None:
        from unittest.mock import patch

        from draftpaper_cli.plugin_candidates import snapshot_skill_source

        registry = {
            "skills": [{
                "id": "scientific-agent-skills",
                "name": "Scientific Agent Skills",
                "summary": {"en": "Three scientific skills."},
                "repository": "https://example.invalid/scientific-agent-skills",
                "license": "MIT",
                "skill_count": 3,
                "tags": ["science"],
            }]
        }
        classification = {
            "sa.statistical-power": {"category": "statistics"},
            "sa.experimental-design": {"category": "methodology"},
        }
        translations = {
            "sa.statistical-power": "统计功效",
            "sa.experimental-design": "实验设计",
        }

        def fake_registry_read(url: str) -> dict:
            if url.endswith("registry/skills.json"):
                return registry
            if url.endswith("scripts/skill-classification.json"):
                return classification
            if url.endswith("scripts/skill-translations.zh.json"):
                return translations
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmp, patch(
            "draftpaper_cli.plugin_candidates._read_registry_json",
            side_effect=fake_registry_read,
        ), patch(
            "draftpaper_cli.plugin_candidates._resolve_github_commit_sha",
            return_value="a" * 40,
        ):
            snapshot = snapshot_skill_source(
                None,
                source="academicforge",
                source_url="https://github.com/HughYau/AcademicForge",
                source_ref="site-first",
                output_root=Path(tmp) / "adapter",
            )

            adapter = snapshot["adapter_report"]
            self.assertEqual(snapshot["file_count"], 3)
            self.assertEqual(adapter["declared_skill_count"], 3)
            self.assertEqual(adapter["expanded_skill_count"], 3)
            self.assertEqual(adapter["detailed_skill_count"], 2)
            self.assertEqual(adapter["placeholder_skill_count"], 1)
            self.assertEqual(adapter["silent_loss_count"], 0)
            self.assertEqual(adapter["immutable_commit"], "a" * 40)
            self.assertTrue(adapter["immutable_ref_resolved"])
            self.assertTrue(any(record["requires_source_inspection"] for record in adapter["records"]))

    def test_cli_skill_source_conversion_backflows_support_rules(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = root / "skills"
            (skills / "ml_workflow" / "SKILL.md").parent.mkdir(parents=True)
            (skills / "ml_workflow" / "SKILL.md").write_text(
                """
# Machine learning evidence workflow

Plan baseline comparisons, ablation studies, train/validation/test split checks,
data leakage diagnostics, calibration, uncertainty, AUC and F1 reporting, claim
scope review, figure-caption consistency, reproducibility fixtures, and result
rescue routes before accepting predictive claims.
""",
                encoding="utf-8",
            )

            signal_out = root / "signals"
            signal_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "extract-review-rule-signals",
                "--source-root",
                str(skills),
                "--source",
                "academicforge",
                "--discipline",
                "machine_learning",
                "--output-root",
                str(signal_out),
            ]
            signal_proc = subprocess.run(signal_cmd, cwd=repo_root, text=True, capture_output=True, check=False)
            self.assertEqual(signal_proc.returncode, 0, signal_proc.stderr)
            signal_report = json.loads(signal_proc.stdout)
            self.assertGreaterEqual(signal_report["support_backflow_source_count"], 1)
            self.assertGreaterEqual(signal_report["formal_candidate_signal_count"], 1)
            self.assertIn("model_validity", signal_report["review_rule_family_counts"])
            self.assertTrue((signal_out / "REVIEW_RULE_SIGNAL_REPORT.json").exists())

            compile_out = root / "compiled"
            compile_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "compile-skill-source",
                "--source-root",
                str(skills),
                "--source",
                "academicforge",
                "--discipline",
                "machine_learning",
                "--output-root",
                str(compile_out),
            ]
            compile_proc = subprocess.run(compile_cmd, cwd=repo_root, text=True, capture_output=True, check=False)
            self.assertEqual(compile_proc.returncode, 0, compile_proc.stderr)
            compile_report = json.loads(compile_proc.stdout)
            self.assertGreaterEqual(compile_report["support_candidate_count"], 1)
            self.assertGreaterEqual(compile_report["review_rule_backflow_count"], 1)
            self.assertIn("workflow_recipe", compile_report["support_type_counts"])
            self.assertTrue((compile_out / "COMPILE_SKILL_SOURCE_REPORT.json").exists())

            support_candidate = Path(compile_report["support_candidates"][0]["path"])
            support_manifest = json.loads((support_candidate / "support_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(support_manifest["candidate_kind"], "support_candidate")
            self.assertFalse(support_manifest["promotion_allowed"])
            self.assertIn("workflow_recipe", support_manifest["support_type"])
            backflow_links = json.loads((support_candidate / "review_rule_backflow_links.json").read_text(encoding="utf-8"))
            self.assertFalse(backflow_links["promotion_allowed"])
            self.assertTrue(backflow_links["backflow_review_rule_ids"])

            review_candidates = [
                item for item in compile_report["candidates"]
                if item.get("plugin_type") == "review_rule"
            ]
            self.assertTrue(review_candidates)
            review_manifest = json.loads((Path(review_candidates[0]["manifest"])).read_text(encoding="utf-8"))
            self.assertEqual(review_manifest["plugin_type"], "review_rule")
            self.assertEqual(review_manifest["backflow_source_type"], "workflow_recipe")
            self.assertIn("workflow_recipe", review_manifest["backflow_from_support_routes"])

    def test_promote_plugin_candidate_requires_validation_and_confirmation(self) -> None:
        from draftpaper_cli.plugin_candidates import (
            PluginCandidateError,
            extract_skill_capabilities,
            generalize_plugin_candidate,
            promote_plugin_candidate,
            validate_plugin_candidate,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "SKILL.md"
            skill.write_text(
                "Use CSV table data and scikit-learn baseline models with ablation checks and AUC metrics.",
                encoding="utf-8",
            )
            result = extract_skill_capabilities(
                skill,
                source="academicforge",
                skill_id="ml.baseline",
                discipline="machine_learning",
                output_root=root / "out",
            )
            candidate = Path(next(item["path"] for item in result["candidates"] if item["plugin_type"] == "method_template"))
            generalize_plugin_candidate(candidate)
            with self.assertRaises(PluginCandidateError):
                promote_plugin_candidate(candidate, require_human_confirmation=True, dry_run=True, target_root=root / "discipline_modules")
            validate_plugin_candidate(candidate)
            with self.assertRaises(PluginCandidateError):
                promote_plugin_candidate(candidate, dry_run=True, target_root=root / "discipline_modules")
            promotion = promote_plugin_candidate(candidate, require_human_confirmation=True, dry_run=True, target_root=root / "discipline_modules")
            self.assertEqual(promotion["status"], "planned")
            self.assertIn("discipline_modules", promotion["target_dir"])


if __name__ == "__main__":
    unittest.main()
