"""Choose a conservative GitHub Actions test scope from changed files."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"
ZERO_SHA = "0" * 40

DOC_TESTS = (
    "tests/test_capability_truth_matrix.py",
    "tests/test_v0317_readme_and_cli_reference.py",
    "tests/test_v0318_cost_risk_product_docs.py",
)
SKILL_TESTS = (
    "tests/test_claude_code_compat.py",
    "tests/test_codex_skill_wrapper.py",
    "tests/test_foundation_skill_coverage.py",
    "tests/test_skill_capability_extraction.py",
)
CHECKPOINT_PRESENTATION_TESTS = (
    "tests/test_checkpoint_digest.py",
    "tests/test_checkpoint_html_showcase.py",
    "tests/test_checkpoint_human_delta.py",
    "tests/test_checkpoint_scope.py",
    "tests/test_checkpoint_summary.py",
    "tests/test_checkpoint_summary_v3.py",
    "tests/test_checkpoint_v5_decision.py",
    "tests/test_strict_checkpoint_html.py",
    "tests/test_v041_checkpoint_definition_of_done.py",
    "tests/test_v042_checkpoint_json_audit.py",
)

HIGH_RISK_ROOT_FILES = {
    ".coveragerc",
    ".python-version",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "uv.lock",
    "poetry.lock",
    "requirements.txt",
}
HIGH_RISK_SOURCE_NAMES = {
    "__init__.py",
    "checkpoint_fingerprint.py",
    "cli.py",
    "command_registry.py",
    "integrity_gate.py",
    "orchestrator.py",
    "project_state.py",
    "release_contract.py",
    "revision_cycle.py",
    "schema_registry.py",
    "state_kernel.py",
}
HIGH_RISK_SOURCE_TOKENS = (
    "claim",
    "contract",
    "evidence",
    "gate",
    "governance",
    "passport",
    "research_plan_confirmation",
    "schema",
    "state",
    "transaction",
    "workflow",
)
HIGH_RISK_TEST_INFRA = {
    "tests/conftest.py",
    "tests/helpers.py",
}


@dataclass(frozen=True)
class TestScope:
    mode: str
    pytest_targets: tuple[str, ...]
    reason: str


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return str(PurePosixPath(normalized))


def _is_high_risk(path: str) -> bool:
    if path.startswith((".github/", "requirements/", "scripts/", "tools/")):
        return True
    if path in HIGH_RISK_ROOT_FILES or path in HIGH_RISK_TEST_INFRA:
        return True
    if path.startswith("draftpaper_cli/"):
        normalized = path.lower()
        filename = PurePosixPath(path).name.lower()
        return filename in HIGH_RISK_SOURCE_NAMES or any(
            token in normalized for token in HIGH_RISK_SOURCE_TOKENS
        )
    return False


def _existing_targets(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            path
            for path in set(paths)
            if (REPO_ROOT / path).is_file()
        )
    )


def _targets_for_path(path: str) -> tuple[str, ...] | None:
    if path.startswith("tests/test_") and path.endswith(".py"):
        return (path,) if (REPO_ROOT / path).is_file() else None

    if path == "README.md" or path.startswith("docs/"):
        return _existing_targets(DOC_TESTS)

    if path.startswith(("codex_skills/", ".claude/")):
        return _existing_targets(SKILL_TESTS)

    if path in {
        "draftpaper_cli/checkpoint_html.py",
        "draftpaper_cli/checkpoint_readability.py",
        "draftpaper_cli/checkpoint_brief.py",
        "draftpaper_cli/checkpoint_summary.py",
        "draftpaper_cli/checkpoint_summary_v3.py",
    }:
        return _existing_targets(CHECKPOINT_PRESENTATION_TESTS)

    if path.startswith("draftpaper_cli/") and path.endswith(".py"):
        stem = PurePosixPath(path).stem
        candidates = sorted(TESTS_ROOT.glob(f"test_{stem}*.py"))
        if candidates:
            return tuple(candidate.relative_to(REPO_ROOT).as_posix() for candidate in candidates)

    return None


def classify_changed_paths(paths: Iterable[str]) -> TestScope:
    normalized = tuple(sorted({_normalize(path) for path in paths if path.strip()}))
    if not normalized:
        return TestScope("full", (), "no changed files were identified; fail closed")

    high_risk = tuple(path for path in normalized if _is_high_risk(path))
    if high_risk:
        return TestScope(
            "full",
            (),
            "high-risk paths require the full matrix: " + ", ".join(high_risk),
        )

    targets: set[str] = set()
    for path in normalized:
        selected = _targets_for_path(path)
        if selected is None:
            return TestScope(
                "full",
                (),
                f"no focused test mapping for {path}; fail closed to the full matrix",
            )
        targets.update(selected)

    return TestScope(
        "focused",
        tuple(sorted(targets)),
        "all changed paths have focused test coverage",
    )


def changed_paths(base: str, head: str) -> tuple[str, ...]:
    if not base or not head or base == ZERO_SHA:
        raise ValueError("base/head commit is unavailable")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRT", f"{base}...{head}"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _write_github_output(scope: TestScope, output_path: str | None) -> None:
    values = {
        "mode": scope.mode,
        "pytest_targets_json": json.dumps(scope.pytest_targets),
    }
    print(f"reason={scope.reason}")
    for key, value in values.items():
        print(f"{key}={value}")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8", newline="\n") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("DPL_CI_BASE_SHA", ""))
    parser.add_argument("--head", default=os.environ.get("DPL_CI_HEAD_SHA", ""))
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
    parser.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args(argv)

    try:
        if args.event not in {"push", "pull_request"} or args.ref.startswith("refs/tags/"):
            scope = TestScope("full", (), f"{args.event or 'manual'} event requires full validation")
        else:
            scope = classify_changed_paths(changed_paths(args.base, args.head))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        scope = TestScope("full", (), f"unable to determine changed paths; fail closed: {error}")

    _write_github_output(scope, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
