from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.checkpoint_summary import (
    render_checkpoint_audit,
    show_checkpoint_audit,
    show_checkpoint_summary,
    validate_checkpoint_summary,
)
from draftpaper_cli.orchestrator import checkpoint_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.checkpoint_shadow import shadow_checkpoint_v6


def test_new_checkpoint_uses_json_first_audit_and_explicit_cache_renderer(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="JSON audit package", field="generic").path
    created = checkpoint_project(project, stage="data")
    package = project / created["checkpoint_summary"]["project_relative_dir"]
    summary = json.loads((package / "stage_summary.json").read_text(encoding="utf-8"))
    request = json.loads((package / "confirmation_request.json").read_text(encoding="utf-8"))
    agent = json.loads((package / "agent_payload.json").read_text(encoding="utf-8"))
    audit = json.loads((package / "stage_audit.json").read_text(encoding="utf-8"))

    assert summary["schema_version"] == "dpl.checkpoint_summary.v6"
    assert summary["audit_bundle_ref"].endswith("stage_audit.json")
    assert summary["audit_render_policy"] == "on_demand_cache_only"
    assert request["summary_schema"] == "dpl.checkpoint_summary.v6"
    assert agent["schema_version"] == "dpl.checkpoint_agent_payload.v3"
    assert "technical_audit_html" not in agent
    assert agent["technical_audit_json"]["project_relative_path"].endswith("stage_audit.json")
    assert len(json.dumps(agent, ensure_ascii=False).encode("utf-8")) <= 12 * 1024
    assert audit["stage_summary_sha256"] == summary["stage_summary_sha256"]
    assert audit["audit_bundle_sha256"] == summary["audit_bundle_sha256"]
    assert not (package / "stage_audit.zh-CN.html").exists()
    assert validate_checkpoint_summary(project, {"stage_summary_json": created["checkpoint_summary"]["stage_summary_json"]})["valid"]

    shown = show_checkpoint_summary(project, created["checkpoint_hash"])
    assert shown["stage_audit_json"]["absolute_path"].endswith("stage_audit.json")
    audit_shown = show_checkpoint_audit(project, checkpoint_package_id=summary["checkpoint_id"])
    assert audit_shown["technical_audit_json"]["absolute_path"].endswith("stage_audit.json")
    assert "render-checkpoint-audit" in audit_shown["render_command"]

    rendered = render_checkpoint_audit(project, checkpoint_package_id=summary["checkpoint_id"])
    cache = Path(rendered["rendered_audit_html"]["absolute_path"])
    assert rendered["status"] == "passed"
    assert cache.is_file()
    assert package not in cache.parents
    assert not (package / "stage_audit.zh-CN.html").exists()

    shadow = shadow_checkpoint_v6(project, output_root=tmp_path / "shadow")
    assert shadow["status"] == "passed"
    assert shadow["report"]["project_state_unchanged"] is True
    assert shadow["report"]["checkpoints"][0]["status"] == "passed"
