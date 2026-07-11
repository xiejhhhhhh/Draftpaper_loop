# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from draftpaper_cli.discipline_modules.local_plugin_runtime import build_local_plugin_plan, run_local_plugin_fixture

PLUGIN_MANIFEST = {'display_name': 'PyTorch GPU training task contract', 'discipline': 'machine_learning', 'packages': ['torch'], 'package_modules': ['torch'], 'maturity': 'foundation', 'runtime_class': 'gpu_model', 'validation_level': 'mock_validated', 'aliases': ['pytorch gpu training contract'], 'provenance_notes': 'First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied.', 'live_execution_performed': False, 'task_contract': {'execution_mode': 'mock_only', 'live_execution_performed': False, 'required_user_inputs': [], 'next_step': 'Provide user-authorized credentials, endpoint or compute environment for live validation.'}, 'template_id': 'pytorch_gpu_training_contract', 'method_family': 'pytorch_gpu_training_contract', 'input_roles': ['analysis_table_or_array'], 'optional_roles': ['sample_group', 'metadata'], 'output_artifacts': ['methods/src/pytorch_gpu_training_contract.py', 'results/tables/pytorch_gpu_training_contract_summary.json'], 'figure_groups': ['method_diagnostic_or_result_summary'], 'formula_families': [], 'validation_checks': ['input_schema_check', 'dependency_check', 'held_out_or_sensitivity_check'], 'genericity_rules': ['Parameterize input columns, units, splits, and scientific hypotheses.'], 'credential_env_vars': []}

def build_template_plan(context=None):
    return build_local_plugin_plan(PLUGIN_MANIFEST, context)


def run_template(output_dir, fixture_path=None, context=None):
    return run_local_plugin_fixture(PLUGIN_MANIFEST, output_dir, fixture_path=fixture_path, context=context)
