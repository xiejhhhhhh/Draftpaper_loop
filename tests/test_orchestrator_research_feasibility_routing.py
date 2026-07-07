# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.project_scaffold import create_project


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class OrchestratorResearchFeasibilityRoutingTests(unittest.TestCase):
    def test_run_pipeline_recommends_research_plan_revision_when_feasibility_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Unsupported main result", field="astronomy")
            _write_json(project.path / "research_plan" / "research_plan_feasibility_report.json", {"decision": "blocked", "recommended_next_action": "revise-research-plan"})

            result = run_pipeline(project.path)

            self.assertEqual(result["next_action"]["stage"], "research_plan_feasibility")
            self.assertEqual(result["next_action"]["command"], "revise-research-plan")


if __name__ == "__main__":
    unittest.main()
