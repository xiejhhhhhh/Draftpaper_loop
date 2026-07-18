from __future__ import annotations

import re
import tomllib
from pathlib import Path

from draftpaper_cli.release_contract import build_release_manifest


def _version() -> str:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_release_tag_report_binds_package_skill_manifest_and_readmes() -> None:
    from tools.verify_release_tag import build_release_tag_report

    version = _version()
    passed = build_release_tag_report(f"v{version}")
    failed = build_release_tag_report("v0.0.0")

    assert passed["status"] == "passed", passed["issues"]
    assert passed["package_version"] == version
    assert passed["release_manifest_version"] == version
    assert passed["workflow_skill_version"] == version
    assert passed["workflow_contract_version"] == version
    assert failed["status"] == "failed"
    assert "tag_version_mismatch" in failed["issues"]


def test_ci_has_macos_smoke_and_nonpublishing_tag_verification() -> None:
    tests_workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    tag_workflow = Path(".github/workflows/tag-build-verify.yml").read_text(encoding="utf-8")

    assert "macos-smoke:" in tests_workflow
    assert "macos-latest" in tests_workflow
    assert "verify_release_tag.py" in tag_workflow
    assert "verify_wheel_install.py" in tag_workflow
    assert "verify_install_matrix.py" in tag_workflow
    assert "publish" not in tag_workflow.lower()
    for workflow in (tests_workflow, tag_workflow):
        for action in re.findall(r"uses:\s*([^\s]+)", workflow):
            assert re.search(r"@[0-9a-f]{40}(?:\s|$)", action), action


def test_release_manifest_declares_platform_and_distribution_boundary() -> None:
    security = build_release_manifest()["release_security"]

    assert security["ci_platforms"] == ["ubuntu", "windows", "macos_smoke"]
    assert security["tag_build_verify"] is True
    assert security["public_pypi_publish"] is False


def test_release_process_document_states_license_boundary() -> None:
    for path in (Path("docs/release_process.md"), Path("docs/release_process.zh-CN.md")):
        text = path.read_text(encoding="utf-8").lower()
        assert "verify_release_tag.py" in text
        assert "licenseref-draftpaper-noncommercial" in text
        assert "public pypi" in text or "公开 pypi" in text
