from __future__ import annotations

import json
import tomllib
from pathlib import Path

from draftpaper_cli.release_contract import build_release_manifest


PLAN = Path("docs/superpowers/plans/2026-07-18-draftpaper-loop-integrated-completion-and-code-audit-optimization.md")
AUDIT = Path("docs/audits/2026-07-18-v0320-completion-audit.md")
SANDBOX = Path("docs/audits/2026-07-18-v0320-sandbox-container-evaluation.md")


def test_v0320_release_identity_and_scope() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    manifest = build_release_manifest()

    assert version == "0.32.0"
    assert manifest["package_version"] == version
    assert manifest["command_count"] == 210
    assert len(manifest["release_fixture_ids"]) == 5
    assert manifest["resource_schema_status"] == "passed"
    assert manifest["release_security"]["public_pypi_publish"] is False
    assert "v0.32.0" in Path("README.md").read_text(encoding="utf-8")
    assert "v0.32.0" in Path("README.zh-CN.md").read_text(encoding="utf-8")


def test_integrated_plan_and_requirement_audit_are_versioned() -> None:
    assert PLAN.is_file()
    plan = PLAN.read_text(encoding="utf-8")
    audit = AUDIT.read_text(encoding="utf-8")

    for issue in ("H-01", "H-02", "H-03", "H-04", "H-05", "H-06", "H-07", "M-01", "M-12"):
        assert issue in plan
        assert issue in audit
    for requirement in range(1, 12):
        assert f"R{requirement:02d}" in audit
    assert "three-journal completion" in audit.lower()
    assert "five-domain release regression" in audit.lower()
    assert "762 passed" not in audit  # final count must include v0.31.6-v0.32.0 tests


def test_sandbox_evaluation_does_not_claim_cloud_isolation() -> None:
    text = SANDBOX.read_text(encoding="utf-8").lower()

    assert "not a production sandbox" in text
    assert "multi-tenant" in text
    assert "outbound" in text
    assert "authentication" in text
    assert "public hosted api" in text
    assert "write-set" in text
    assert "executable allowlist" in text


def test_release_evidence_files_cover_three_journals_and_five_domains() -> None:
    journal_test = Path("tests/test_v0310_completion_multi_journal.py").read_text(encoding="utf-8")
    fixtures = sorted(Path("draftpaper_cli/release_fixtures").glob("*.json"))

    assert all(token in journal_test for token in ("general", "aas", "mnras"))
    assert len(fixtures) == 5
    assert all(json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "dpl.release_fixture.v1" for path in fixtures)
