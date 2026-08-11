from __future__ import annotations

import json

from draftpaper_cli.code_ownership import assess_figure_code_trace, trace_figures_to_code
from draftpaper_cli.project_scaffold import create_project


def _fixture(tmp_path):
    project = create_project(root=tmp_path, idea="trace", field="generic").path
    figure = project / "results" / "figures" / "figure1.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    figure.write_bytes(b"figure-bytes")
    metadata = project / "results" / "figure_metadata.json"
    metadata.write_text(json.dumps({"figures": [{"path": "results/figures/figure1.png", "figure_id": "fig-1"}]}), encoding="utf-8")
    code = project / "methods" / "plotting" / "make_figure.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("# fig-1\nprint('figure')\n", encoding="utf-8")
    run = project / "methods" / "run_manifest.yaml"
    run.write_text(json.dumps({"status": "success", "run_id": "run-1", "run_transaction_id": "txn-1"}), encoding="utf-8")
    return project, figure, code


def test_trace_v2_binds_current_hashes_and_run(tmp_path) -> None:
    project, _, _ = _fixture(tmp_path)
    report = trace_figures_to_code(project)
    assert report["schema_version"] == "dpl.figure_code_trace.v2"
    assert report["traces"][0]["trace_status"] == "current"
    assert assess_figure_code_trace(project)["status"] == "current"


def test_trace_v2_becomes_stale_after_figure_or_code_changes(tmp_path) -> None:
    project, figure, code = _fixture(tmp_path)
    trace_figures_to_code(project)
    figure.write_bytes(b"changed-figure")
    code.write_text("# changed\n", encoding="utf-8")
    validation = assess_figure_code_trace(project)
    assert validation["status"] == "stale"
    issue_kinds = {issue["kind"] for check in validation["checks"] for issue in check["issues"]}
    assert "figure_hash_changed" in issue_kinds
    assert "producer_code_hash_changed" in issue_kinds
