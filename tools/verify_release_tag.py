"""Verify that one release tag names the exact package, skill and manifest version."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from draftpaper_cli.toml_compat import tomllib  # noqa: E402


def _normalized_tag(tag: str) -> str:
    value = str(tag or "").strip()
    return value.rsplit("/", 1)[-1]


def _git_revision(repository: Path, revision: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", revision],
            cwd=repository,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _git_metadata_available(repository: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repository,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def build_release_tag_report(
    tag: str,
    *,
    root: str | Path = REPOSITORY_ROOT,
    verify_repository: bool = False,
) -> dict[str, Any]:
    repository = Path(root).resolve()
    pyproject = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = str(pyproject["project"]["version"])
    manifest = json.loads((repository / "draftpaper_cli/resources/release_manifest.json").read_text(encoding="utf-8"))
    skill_text = (repository / "draftpaper_cli/resources/draftpaper_workflow/SKILL.md").read_text(encoding="utf-8")
    skill_match = re.search(r"(?m)^version:\s*(\S+)", skill_text)
    skill_version = skill_match.group(1) if skill_match else None
    contract = json.loads((repository / "draftpaper_cli/resources/draftpaper_workflow/contract.json").read_text(encoding="utf-8"))
    contract_version = str(contract.get("skill_version") or "")
    normalized_tag = _normalized_tag(tag)
    expected_tag = f"v{package_version}"
    issues: list[str] = []
    if normalized_tag != expected_tag:
        issues.append("tag_version_mismatch")
    if str(manifest.get("package_version") or "") != package_version:
        issues.append("release_manifest_version_mismatch")
    if skill_version != package_version:
        issues.append("workflow_skill_version_mismatch")
    if contract_version != package_version:
        issues.append("workflow_contract_version_mismatch")
    for readme in ("README.md", "README.zh-CN.md"):
        if f"v{package_version}" not in (repository / readme).read_text(encoding="utf-8"):
            issues.append(f"readme_version_mismatch:{readme}")
    repository_metadata_available = verify_repository and _git_metadata_available(repository)
    repository_head_commit = None
    release_tag_object = None
    release_tag_commit = None
    if repository_metadata_available:
        repository_head_commit = _git_revision(repository, "HEAD^{commit}")
        release_ref = f"refs/tags/{normalized_tag}"
        release_tag_object = _git_revision(repository, f"{release_ref}^{{object}}")
        release_tag_commit = _git_revision(repository, f"{release_ref}^{{commit}}")
        if release_tag_object is None or release_tag_commit is None:
            issues.append("release_tag_ref_missing")
        elif repository_head_commit != release_tag_commit:
            issues.append("repository_head_tag_mismatch")
    return {
        "schema_version": "dpl.release_tag_validation.v1",
        "status": "passed" if not issues else "failed",
        "tag": normalized_tag,
        "expected_tag": expected_tag,
        "package_version": package_version,
        "release_manifest_version": manifest.get("package_version"),
        "workflow_skill_version": skill_version,
        "workflow_contract_version": contract_version,
        "repository_metadata_available": repository_metadata_available,
        "repository_head_commit": repository_head_commit,
        "release_tag_object": release_tag_object,
        "release_tag_commit": release_tag_commit,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    args = parser.parse_args(argv)
    report = build_release_tag_report(args.tag, root=args.root, verify_repository=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
