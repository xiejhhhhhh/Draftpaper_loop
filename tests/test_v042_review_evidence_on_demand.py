from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.review_evidence import MAX_PREVIEW_BYTES, inspect_review_evidence


def test_explicit_review_evidence_is_project_bound_and_bounded(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="evidence query", field="generic").path
    payload = {"claims": [{"id": "claim-a", "value": 0.71}], "cohort": "held-out"}
    path = project / "results" / "evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    selected = inspect_review_evidence(project, ref="artifact:results/evidence.json#/claims/0")
    assert selected["status"] == "passed"
    assert selected["content"] == {"id": "claim-a", "value": 0.71}
    assert selected["project_relative_path"] == "results/evidence.json"

    blocked = inspect_review_evidence(project, ref="../outside.json")
    assert blocked["status"] == "blocked"

    large = project / "results" / "large.txt"
    large.write_text("x" * (MAX_PREVIEW_BYTES + 1), encoding="utf-8")
    preview = inspect_review_evidence(project, ref="results/large.txt")
    assert preview["status"] == "passed"
    assert preview["truncated"] is True
    assert len(preview["content"].encode("utf-8")) <= MAX_PREVIEW_BYTES
