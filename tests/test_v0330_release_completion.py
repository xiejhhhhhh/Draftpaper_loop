from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.completion_change_classifier import DEFAULT_ENFORCEMENT_MODE
from draftpaper_cli.release_contract import build_release_manifest
from draftpaper_cli.toml_compat import tomllib


VERSION = "0.33.1"


def _skill_version(path: Path) -> str:
    match = re.search(r"^version:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_v0330_release_identity_is_consistent() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    stored = json.loads(Path("draftpaper_cli/resources/release_manifest.json").read_text(encoding="utf-8"))
    built = build_release_manifest()

    assert version == VERSION
    assert stored == built
    assert built["package_version"] == VERSION
    required_release_commands = {
        "assess-result-support",
        "apply-result-downgrade",
        "prepare-result-rescue",
        "review-final-manuscript",
        "confirm-final-manuscript",
        "audit-citations",
        "re-audit-citations",
        "prepare-independent-manuscript-review",
        "record-independent-manuscript-review",
        "assess-manuscript-quality-release",
        "assemble-latex",
        "run-integrity-gate",
        "quality-check",
    }
    assert required_release_commands <= set(built["required_cli_commands"])
    assert set(built["required_cli_commands"]) <= set(COMMAND_SPECS)


def test_v0330_tag_build_runs_tests_before_wheel_verification() -> None:
    workflow = Path(".github/workflows/tag-build-verify.yml").read_text(encoding="utf-8")

    pytest_position = workflow.index("python -m pytest")
    build_position = workflow.index("python -m build --wheel")
    assert pytest_position < build_position


def test_v0330_tag_build_checks_out_the_exact_event_release_ref() -> None:
    workflow = Path(".github/workflows/tag-build-verify.yml").read_text(encoding="utf-8")

    assert "format('refs/tags/{0}', inputs.release_tag)" in workflow


def test_release_tag_verifier_rejects_same_named_branch_at_a_different_commit(tmp_path: Path) -> None:
    from tools.verify_release_tag import build_release_tag_report

    source = Path.cwd()
    repository = tmp_path / "repository"
    required_files = (
        "pyproject.toml",
        "README.md",
        "README.zh-CN.md",
        "draftpaper_cli/resources/release_manifest.json",
        "draftpaper_cli/resources/draftpaper_workflow/SKILL.md",
        "draftpaper_cli/resources/draftpaper_workflow/contract.json",
    )
    for relative in required_files:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source / relative).read_bytes())

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True, text=True)

    git("init")
    git("config", "user.email", "release-test@example.invalid")
    git("config", "user.name", "Release Test")
    git("add", ".")
    git("commit", "-m", "tagged release")
    git("tag", f"v{VERSION}")
    (repository / "branch-only.txt").write_text("same-named branch drift\n", encoding="utf-8")
    git("add", "branch-only.txt")
    git("commit", "-m", "branch drift")
    git("branch", f"v{VERSION}")
    git("checkout", f"v{VERSION}")

    report = build_release_tag_report(f"v{VERSION}", root=repository, verify_repository=True)

    assert report["status"] == "failed"
    assert "repository_head_tag_mismatch" in report["issues"]
    assert report["repository_head_commit"] != report["release_tag_commit"]


def test_v0330_workflow_skill_source_and_wheel_resource_are_synchronized() -> None:
    source_skill = Path("codex_skills/draftpaper-workflow/SKILL.md")
    resource_skill = Path("draftpaper_cli/resources/draftpaper_workflow/SKILL.md")
    source_contract = Path("codex_skills/draftpaper-workflow/contract.json")
    resource_contract = Path("draftpaper_cli/resources/draftpaper_workflow/contract.json")

    assert _skill_version(source_skill) == VERSION
    assert _skill_version(resource_skill) == VERSION
    assert json.loads(source_contract.read_text(encoding="utf-8"))["skill_version"] == VERSION
    assert json.loads(resource_contract.read_text(encoding="utf-8"))["skill_version"] == VERSION
    assert source_skill.read_text(encoding="utf-8") == resource_skill.read_text(encoding="utf-8")
    assert json.loads(source_contract.read_text(encoding="utf-8")) == json.loads(resource_contract.read_text(encoding="utf-8"))


def test_v0330_readmes_and_truth_matrix_publish_the_new_capabilities() -> None:
    matrix = json.loads(Path("docs/capability_truth_matrix.json").read_text(encoding="utf-8"))
    by_id = {item["capability_id"]: item for item in matrix["capabilities"]}

    assert by_id["completion_change_classification"]["status"] == "implemented"
    assert by_id["result_support_checkpoint_v3"]["status"] == "implemented"
    for readme in (Path("README.md"), Path("README.zh-CN.md")):
        content = readme.read_text(encoding="utf-8")
        assert "v0.33.1" in content
        assert "v0.32.1-v0.32.2" in content
        assert "completion_change_classification" in content
        assert "result_support_checkpoint_v3" in content


def test_v0330_enables_strict_completion_classification() -> None:
    assert DEFAULT_ENFORCEMENT_MODE == "strict"
