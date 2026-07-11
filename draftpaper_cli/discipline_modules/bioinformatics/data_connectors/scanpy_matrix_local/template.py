# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from draftpaper_cli.discipline_modules.local_plugin_runtime import build_local_plugin_plan, run_local_plugin_fixture

PLUGIN_MANIFEST = {'display_name': 'Scanpy local matrix input', 'discipline': 'bioinformatics', 'packages': ['scanpy'], 'package_modules': ['scanpy'], 'maturity': 'foundation', 'runtime_class': 'local_optional_dependency', 'validation_level': 'fixture_runnable', 'aliases': ['scanpy matrix local'], 'provenance_notes': 'First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied.', 'connector_id': 'scanpy_matrix_local', 'access_modes': ['local_files'], 'download_or_access': ['Use parameterized local files or user-authorized exports.'], 'data_formats': ['csv', 'json', 'parquet'], 'requires_credentials': False, 'genericity_rules': ['Do not store credentials, server locations, or project-specific samples.']}

def build_template_plan(context=None):
    return build_local_plugin_plan(PLUGIN_MANIFEST, context)


def run_template(output_dir, fixture_path=None, context=None):
    return run_local_plugin_fixture(PLUGIN_MANIFEST, output_dir, fixture_path=fixture_path, context=context)
