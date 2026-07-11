# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from draftpaper_cli.discipline_modules.local_plugin_runtime import build_local_plugin_plan, run_local_plugin_fixture

PLUGIN_MANIFEST = {'display_name': 'PubChem API task contract', 'discipline': 'chemistry', 'packages': ['requests'], 'package_modules': ['requests'], 'maturity': 'foundation', 'runtime_class': 'remote_api', 'validation_level': 'mock_validated', 'aliases': ['pubchem api contract'], 'provenance_notes': 'First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied.', 'live_execution_performed': False, 'task_contract': {'execution_mode': 'mock_only', 'live_execution_performed': False, 'required_user_inputs': [], 'next_step': 'Provide user-authorized credentials, endpoint or compute environment for live validation.'}, 'connector_id': 'pubchem_api_contract', 'access_modes': ['api_access'], 'download_or_access': ['Use parameterized local files or user-authorized exports.'], 'data_formats': ['csv', 'json', 'parquet'], 'requires_credentials': False, 'genericity_rules': ['Do not store credentials, server locations, or project-specific samples.'], 'credential_env_vars': []}

def build_template_plan(context=None):
    return build_local_plugin_plan(PLUGIN_MANIFEST, context)


def run_template(output_dir, fixture_path=None, context=None):
    return run_local_plugin_fixture(PLUGIN_MANIFEST, output_dir, fixture_path=fixture_path, context=context)
