"""Generated release identity shared by source, wheel, CI, and verifiers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

RELEASE_MANIFEST = Path(__file__).resolve().parent / "resources" / "release_manifest.json"
CI_CONSTRAINTS = Path("requirements/ci-constraints.txt")
EXPECTED_LICENSE = "LicenseRef-Draftpaper-NonCommercial"
ANY_ACTION_RE = re.compile(r"\buses:\s*[^\s@]+@([^\s#]+)")
REQUIRED_CLI_COMMANDS = (
    "assemble-latex",
    "run-integrity-gate",
    "quality-check",
    "review-research-plan",
    "confirm-research-plan",
    "reopen-research-plan",
    "path-budget-check",
    "token-report",
    "validate-confirmed-figure-alignment",
    "apply-section-revision",
    "review-final-manuscript",
    "confirm-final-manuscript",
    "audit-citations",
    "re-audit-citations",
    "prepare-independent-manuscript-review",
    "record-independent-manuscript-review",
    "assess-manuscript-quality-release",
    "validate-command-contracts",
    "prepare-manuscript-completion",
    "preview-manuscript-completion",
    "apply-manuscript-completion",
    "manuscript-completion-status",
    "rollback-manuscript-completion",
    "assess-result-support",
    "apply-result-downgrade",
    "prepare-result-rescue",
)


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


def _release_manifest_path(root: Path) -> Path:
    return root / "draftpaper_cli" / "resources" / "release_manifest.json"


def _load_schema_registry(root: Path) -> dict[str, Any]:
    path = root / "draftpaper_cli" / "resources" / "schemas" / "schema_registry.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Package schema registry is invalid under supplied root: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("families"), dict):
        raise ValueError(f"Package schema registry is invalid under supplied root: {path}")
    return payload


def _schema_family(registry: dict[str, Any], schema_id: str) -> str | None:
    for family, raw_contract in registry["families"].items():
        if not isinstance(raw_contract, dict):
            continue
        accepted = raw_contract.get("accepted")
        accepted_ids = accepted if isinstance(accepted, list) else []
        if schema_id == raw_contract.get("current") or schema_id in accepted_ids:
            return str(family)
    return None


def _validate_packaged_resource_schemas(root: Path, registry: dict[str, Any]) -> dict[str, Any]:
    package_root = root / "draftpaper_cli"
    checks: list[dict[str, str]] = []
    issues: list[str] = []

    release_files = sorted((package_root / "release_fixtures").glob("*.json"))
    for path in release_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_id = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
        family = _schema_family(registry, schema_id) if schema_id else None
        resource = f"release_fixtures/{path.name}"
        checks.append({"resource": resource, "schema_id": schema_id, "family": str(family or "")})
        if family != "release_fixture":
            issues.append(f"{resource}:unregistered_or_wrong_schema:{schema_id or 'missing'}")

    capability_files = sorted((package_root / "capability_packs").glob("*/manifest.json"))
    for path in capability_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_id = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
        family = _schema_family(registry, schema_id) if schema_id else None
        resource = f"capability_packs/{path.parent.name}/manifest.json"
        checks.append({"resource": resource, "schema_id": schema_id, "family": str(family or "")})
        if family != "research_capability_pack":
            issues.append(f"{resource}:unregistered_or_wrong_schema:{schema_id or 'missing'}")

    return {
        "schema_version": "dpl.packaged_resource_schema_report.v1",
        "status": "passed" if not issues else "failed",
        "release_fixture_count": len(release_files),
        "capability_pack_count": len(capability_files),
        "checks": checks,
        "issues": issues,
    }


def _build_release_manifest_isolated(repository: Path) -> dict[str, Any]:
    marker = "__DRAFTPAPER_RELEASE_MANIFEST__="
    bootstrap = (
        "import json, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1]).resolve()\n"
        "sys.path.insert(0, str(root))\n"
        "from draftpaper_cli.release_contract import build_release_manifest\n"
        f"print({marker!r} + json.dumps(build_release_manifest(), ensure_ascii=False))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", bootstrap, str(repository)],
        cwd=repository,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise ValueError(f"Release manifest build failed in supplied root {repository}: {detail}")
    encoded = next((line[len(marker) :] for line in completed.stdout.splitlines() if line.startswith(marker)), "")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Release manifest build returned invalid output from supplied root {repository}.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Release manifest build returned a non-object from supplied root {repository}.")
    return payload


def _build_release_manifest_local(repository: Path) -> dict[str, Any]:
    from .command_contracts import build_command_contracts
    from .command_registry import COMMAND_SPECS
    from .plugin_catalog import build_plugin_catalog_snapshot
    from .release_regression import FIXTURE_NAMES
    from .template_registry import discover_template_registry

    schema_registry = _load_schema_registry(repository)
    registry = discover_template_registry(repository / "draftpaper_cli" / "discipline_modules")
    catalog = build_plugin_catalog_snapshot(root=repository / "draftpaper_cli" / "discipline_modules", refresh=True)
    commands = build_command_contracts()
    skill = repository / "draftpaper_cli" / "resources" / "draftpaper_workflow" / "SKILL.md"
    skill_contract = skill.with_name("contract.json")
    available_release_fixtures = {path.stem for path in (repository / "draftpaper_cli" / "release_fixtures").glob("*.json")}
    release_fixtures = [fixture_id for fixture_id in FIXTURE_NAMES if fixture_id in available_release_fixtures]
    third_party = repository / "third_party" / "registry.json"
    constraints = repository / CI_CONSTRAINTS
    resource_schemas = _validate_packaged_resource_schemas(repository, schema_registry)
    missing_commands = sorted(set(REQUIRED_CLI_COMMANDS) - set(COMMAND_SPECS))
    if missing_commands:
        raise ValueError("Required release commands are not registered in CommandSpec: " + ", ".join(missing_commands))
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
        "required_cli_commands": list(REQUIRED_CLI_COMMANDS),
        "schema_registry_version": schema_registry["schema_version"],
        "resource_schema_status": resource_schemas["status"],
        "resource_schema_issue_count": len(resource_schemas["issues"]),
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
            "ci_platforms": ["ubuntu", "windows", "macos_smoke"],
            "tag_build_verify": True,
            "public_pypi_publish": False,
        },
    }


def build_release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    repository = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    if root is not None:
        return _build_release_manifest_isolated(repository)
    return _build_release_manifest_local(repository)


def validate_release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    repository = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    manifest_path = _release_manifest_path(repository)
    expected = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    current = build_release_manifest(repository if root is not None else None)
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
    if current.get("resource_schema_status") != "passed" or current.get("resource_schema_issue_count"):
        security_issues.append("packaged_resource_schema_validation_failed")
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
    repository = Path(args.root).resolve()
    payload = build_release_manifest(repository)
    if args.write:
        _release_manifest_path(repository).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
