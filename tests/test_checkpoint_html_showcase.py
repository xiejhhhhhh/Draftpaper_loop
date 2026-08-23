from __future__ import annotations

import json
from pathlib import Path

from tools.generate_checkpoint_html_showcase import generate


def test_anonymous_showcase_covers_multiple_checkpoint_states(tmp_path: Path) -> None:
    report = generate(tmp_path / "showcase")

    assert len(report["checkpoints"]) == 6
    states = {item["stage"]: item["review_state"] for item in report["checkpoints"]}
    assert states["research_plan"] == "confirmable"
    assert states["data"] == "confirmable"
    assert states["methods"] == "confirmable"
    assert states["result_support"] == "blocked"
    assert states["core_evidence"] == "confirmable"
    assert states["quality_checks"] == "confirmable"

    for checkpoint in report["checkpoints"]:
        html_path = Path(checkpoint["absolute_html"])
        summary_path = Path(checkpoint["absolute_summary"])
        audit_path = Path(checkpoint["absolute_audit_html"])
        assert html_path.is_file()
        assert summary_path.is_file()
        assert audit_path.is_file()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        html = html_path.read_text(encoding="utf-8")
        audit_html = audit_path.read_text(encoding="utf-8")
        request = json.loads((html_path.parent / "confirmation_request.json").read_text(encoding="utf-8"))
        readability = json.loads((html_path.parent / "checkpoint_readability_report.json").read_text(encoding="utf-8"))
        assert summary["test_auto_confirmation"] is True
        assert summary["schema_version"] == "dpl.checkpoint_summary.v5"
        assert request["scientific_decision_sha256"] == summary["scientific_decision_fingerprint"]["scientific_decision_sha256"]
        assert readability["status"] == "passed"
        if summary["review_state"] == "blocked":
            assert request["confirmation_command"] is None
        else:
            assert request["confirmation_command"]
        assert "本次确认什么" in html
        assert "Agent实际工作" not in html
        assert "Agent实际工作" in audit_html
        assert "stage summary hash" not in html

    plan = json.loads(
        Path(next(item["absolute_summary"] for item in report["checkpoints"] if item["stage"] == "research_plan")).read_text(
            encoding="utf-8"
        )
    )
    assert plan["decision_brief"]["latest_user_visible_deliverables"]
