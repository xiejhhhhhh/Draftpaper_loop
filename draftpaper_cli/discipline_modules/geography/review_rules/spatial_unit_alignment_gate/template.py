# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from draftpaper_cli.discipline_modules.local_plugin_runtime import evaluate_local_review_rule

PLUGIN_MANIFEST = {'display_name': 'Spatial-unit alignment gate', 'discipline': 'geography', 'packages': [], 'package_modules': [], 'maturity': 'foundation', 'runtime_class': 'local_pure_python', 'validation_level': 'fixture_runnable', 'aliases': ['spatial unit alignment gate'], 'provenance_notes': 'First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied.', 'rule_id': 'spatial_unit_alignment_gate', 'rule_group_id': 'spatial_unit_alignment_gate', 'rule_family': 'discipline_scientific_quality', 'criterion_type': 'scientific_quality_gate', 'applicable_disciplines': ['geography'], 'evidence_roles': ['method_output', 'result_metric'], 'evidence_binding': {'registry_record_types': ['result_metric'], 'required_fields': ['run_id'], 'forbidden_conflicts': []}, 'checks': ['Confirm that spatial-unit alignment gate is addressed with project-specific evidence.'], 'threshold_policy': {'mode': 'contextual'}, 'threshold_source': {'type': 'discipline_convention', 'citation_or_note': 'Foundation rule requires user or literature confirmation before hard blocking.'}, 'threshold_mode': 'contextual', 'threshold_validation_status': 'candidate_unverified', 'blocking_level': 'warn_and_repair', 'failure_route': 'human_checkpoint', 'pipeline_hooks': {'result_validity': 'advisory'}, 'deployment_state': 'review_rule_candidate', 'human_confirmation_required': True, 'review_question': 'Spatial-unit alignment gate', 'scientific_risk': 'Unverified or mismatched evidence can overstate a discipline-specific claim.', 'minimum_evidence_required': ['method_output', 'result_metric'], 'allowed_claim_strength': 'exploratory', 'repair_priority': ['human_checkpoint']}

def evaluate_rule(evidence=None):
    return evaluate_local_review_rule(PLUGIN_MANIFEST, evidence)
