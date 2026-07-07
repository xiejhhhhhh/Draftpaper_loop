# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.method_feasibility import assess_method_feasibility
from draftpaper_cli.project_scaffold import create_project


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class MethodFeasibilityTests(unittest.TestCase):
    def test_method_feasibility_blocks_missing_required_data_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Spatial crop validation", field="geography")
            _write_json(project.path / "methods" / "method_blueprint.json", {"status": "written"})
            _write_json(project.path / "methods" / "method_data_contract.json", {"required_roles": ["spatial_group_or_coordinates", "target_or_response"], "available_roles": ["target_or_response"]})
            _write_json(project.path / "methods" / "method_code_plan.json", {"method_families": ["spatial_block_validation"], "validation_checks": ["spatial_holdout"]})
            _write_json(project.path / "methods" / "method_formula_plan.json", {"formula_families": ["blockwise_metric"]})

            result = assess_method_feasibility(project.path)
            report = json.loads((project.path / "methods" / "method_feasibility_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(report["recommended_next_action"], "prepare-data-acquisition")
            self.assertTrue(any(issue["kind"] == "missing_data_role" for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
