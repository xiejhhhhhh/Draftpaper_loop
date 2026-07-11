# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from draftpaper_cli.discipline_modules.local_plugin_runtime import build_local_plugin_plan, run_local_plugin_fixture

PLUGIN_MANIFEST = {'display_name': 'WCS coordinate transform', 'discipline': 'astronomy', 'packages': ['astropy'], 'package_modules': ['astropy'], 'maturity': 'foundation', 'runtime_class': 'local_optional_dependency', 'validation_level': 'fixture_runnable', 'aliases': ['wcs coordinate transform'], 'provenance_notes': 'First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied.', 'template_id': 'wcs_coordinate_transform', 'method_family': 'wcs_coordinate_transform', 'input_roles': ['analysis_table_or_array'], 'optional_roles': ['sample_group', 'metadata'], 'output_artifacts': ['methods/src/wcs_coordinate_transform.py', 'results/tables/wcs_coordinate_transform_summary.json'], 'figure_groups': ['method_diagnostic_or_result_summary'], 'formula_families': [], 'validation_checks': ['input_schema_check', 'dependency_check', 'held_out_or_sensitivity_check'], 'genericity_rules': ['Parameterize input columns, units, splits, and scientific hypotheses.']}

def build_template_plan(context=None):
    return build_local_plugin_plan(PLUGIN_MANIFEST, context)


def run_template(output_dir, fixture_path=None, context=None):
    return run_local_plugin_fixture(PLUGIN_MANIFEST, output_dir, fixture_path=fixture_path, context=context)
