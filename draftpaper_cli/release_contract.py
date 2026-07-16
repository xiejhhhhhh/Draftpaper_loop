"""Generated release identity shared by source, wheel, CI, and verifiers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .command_contracts import build_command_contracts
from .plugin_catalog import build_plugin_catalog_snapshot
from .schema_registry import load_schema_registry
from .template_registry import discover_template_registry
from .release_regression import FIXTURE_NAMES


RELEASE_MANIFEST = Path(__file__).resolve().parent / "resources" / "release_manifest.json"
CI_CONSTRAINTS = Path("requirements/ci-constraints.txt")
EXPECTED_LICENSE = "LicenseRef-Draftpaper-NonCommercial"
ANY_ACTION_RE = re.compile(r"\buses:\s*[^\s@]+@([^\s#]+)")


def _version(root: Path) -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ValueError("pyproject.toml has no project version.")
    return match.group(1)


def _sha(path: Path) -> str:
    value = path.read_bytes()
    if path.suffix.lower() in {".json", ".py", ".md", ".yaml", ".yml", ".csv", ".txt"}:
        value = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(value).hexdigest()


def _project_license(root: Path) -> str:
    match = re.search(r'^license\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def _actions_pinned(root: Path) -> bool:
    workflow_root = root / ".github" / "workflows"
    references = []
    for path in sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml")):
        references.extend(ANY_ACTION_RE.findall(path.read_text(encoding="utf-8")))
    return bool(references) and all(re.fullmatch(r"[0-9a-f]{40}", reference) for reference in references)


def build_release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    repository = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    registry = discover_template_registry(repository / "draftpaper_cli" / "discipline_modules")
    catalog = build_plugin_catalog_snapshot(root=repository / "draftpaper_cli" / "discipline_modules", refresh=True)
    commands = build_command_contracts()
    skill = repository / "draftpaper_cli" / "resources" / "draftpaper_workflow" / "SKILL.md"
    skill_contract = skill.with_name("contract.json")
    available_release_fixtures = {path.stem for path in (repository / "draftpaper_cli" / "release_fixtures").glob("*.json")}
    release_fixtures = [fixture_id for fixture_id in FIXTURE_NAMES if fixture_id in available_release_fixtures]
    third_party = repository / "third_party" / "registry.json"
    constraints = repository / CI_CONSTRAINTS
    return {
        "schema_version": "dpl.release_manifest.v1",
        "package_version": _version(repository),
        "workflow_skill_sha256": _sha(skill),
        "workflow_contract_sha256": _sha(skill_contract),
        "plugin_count": registry["entry_count"],
        "fixture_count": sum(len(entry.get("fixtures") or []) for entry in registry["entries"]),
        "plugin_catalog_hash": catalog["catalog_hash"],
        "command_count": commands["command_count"],
        "command_contract_status": commands["status"],
        "required_cli_commands": [
            "review-research-plan",
            "confirm-research-plan",
            "reopen-research-plan",
            "path-budget-check",
            "validate-confirmed-figure-alignment",
            "apply-section-revision",
            "review-final-manuscript",
            "validate-command-contracts",
        ],
        "schema_registry_version": load_schema_registry()["schema_version"],
        "capability_pack_ids": sorted(path.parent.name for path in (repository / "draftpaper_cli" / "capability_packs").glob("*/manifest.json")),
        "release_fixture_ids": release_fixtures,
        "third_party_registry_sha256": _sha(third_party),
        "release_security": {
            "license_identifier": _project_license(repository),
            "license_files": [name for name in ("LICENSE", "NOTICE") if (repository / name).is_file()],
            "github_actions_pinned": _actions_pinned(repository),
            "ci_constraints_sha256": _sha(constraints) if constraints.is_file() else "",
            "sbom_format": "CycloneDX JSON",
            "dependency_audit_scope": "project_dependency_graph",
        },
    }


def validate_release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    expected = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8")) if RELEASE_MANIFEST.is_file() else {}
    current = build_release_manifest(root)
    raw_security = current.get("release_security")
    security: dict[str, Any] = raw_security if isinstance(raw_security, dict) else {}
    security_issues = []
    if security.get("license_identifier") != EXPECTED_LICENSE:
        security_issues.append("invalid_license_identifier")
    if security.get("license_files") != ["LICENSE", "NOTICE"]:
        security_issues.append("missing_license_files")
    if not security.get("github_actions_pinned"):
        security_issues.append("github_action_not_pinned_to_commit")
    if not security.get("ci_constraints_sha256"):
        security_issues.append("missing_ci_constraints")
    changed_fields = sorted(key for key in set(expected) | set(current) if expected.get(key) != current.get(key))
    return {
        "schema_version": "dpl.release_manifest_validation.v1",
        "status": "passed" if expected == current and not security_issues else "failed",
        "expected": expected,
        "current": current,
        "changed_fields": changed_fields,
        "security_issues": security_issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = build_release_manifest(args.root)
    if args.write:
        RELEASE_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
