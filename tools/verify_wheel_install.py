"""Verify that a built wheel preserves the source discipline-plugin registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


RESOURCE_PATTERNS = ("*.json", "*.csv", "*.md")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODULE_ROOT = REPOSITORY_ROOT / "draftpaper_cli" / "discipline_modules"
SOURCE_CAPABILITY_PACK_ROOT = REPOSITORY_ROOT / "draftpaper_cli" / "capability_packs"
SOURCE_RELEASE_MANIFEST_PATH = REPOSITORY_ROOT / "draftpaper_cli" / "resources" / "release_manifest.json"
SOURCE_RELEASE_MANIFEST = json.loads(SOURCE_RELEASE_MANIFEST_PATH.read_text(encoding="utf-8"))
EXPECTED_ENTRY_COUNT = int(SOURCE_RELEASE_MANIFEST["plugin_count"])
EXPECTED_FIXTURE_COUNT = int(SOURCE_RELEASE_MANIFEST["fixture_count"])
EXPECTED_PACKAGE_VERSION = str(SOURCE_RELEASE_MANIFEST["package_version"])
EXPECTED_CLI_COMMANDS = tuple(SOURCE_RELEASE_MANIFEST["required_cli_commands"])
EXPECTED_RELEASE_FIXTURE_IDS = tuple(SOURCE_RELEASE_MANIFEST["release_fixture_ids"])


def _resource_counts(root: Path) -> dict[str, int]:
    return {pattern: len(list(root.rglob(pattern))) for pattern in RESOURCE_PATTERNS}


def _source_registry_summary() -> dict[str, object]:
    """Inspect checkout resources without importing the source package.

    The wheel check intentionally runs before installing project dependencies.
    Importing ``draftpaper_cli`` here would resolve the checkout package and turn
    this resource check into an accidental editable-environment check.
    """

    manifests = sorted(SOURCE_MODULE_ROOT.glob("*/*/*/manifest.json"))
    fixture_count = sum(
        1
        for manifest in manifests
        for path in manifest.parent.iterdir()
        if path.is_file() and path.name.startswith("fixture")
    )
    pyproject = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, flags=re.MULTILINE)
    skill = REPOSITORY_ROOT / "draftpaper_cli" / "resources" / "draftpaper_workflow" / "SKILL.md"
    skill_contract = skill.with_name("contract.json")
    skill_text = skill.read_text(encoding="utf-8")
    skill_version = re.search(r"^version:\s*(\S+)", skill_text, flags=re.MULTILINE)
    contract_payload = json.loads(skill_contract.read_text(encoding="utf-8"))
    return {
        "package_version": version_match.group(1) if version_match else None,
        "workflow_skill_version": skill_version.group(1) if skill_version else None,
        "workflow_skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
        "workflow_contract_version": contract_payload.get("skill_version"),
        "workflow_contract_sha256": hashlib.sha256(skill_contract.read_bytes()).hexdigest(),
        "cli_help_commands": list(EXPECTED_CLI_COMMANDS),
        "entry_count": len(manifests),
        "fixture_count": fixture_count,
        "resource_counts": _resource_counts(SOURCE_MODULE_ROOT),
        "capability_pack_count": len(list(SOURCE_CAPABILITY_PACK_ROOT.glob("*/manifest.json"))),
        "vendored_paper_fetch_present": (REPOSITORY_ROOT / "draftpaper_cli" / "_vendor" / "paper_fetch_skill" / "paper_fetch").is_dir(),
        "third_party_provenance_status": "passed",
        "third_party_source_count": len(json.loads((REPOSITORY_ROOT / "third_party" / "registry.json").read_text(encoding="utf-8"))["sources"]),
        "release_manifest": SOURCE_RELEASE_MANIFEST,
    }


def _release_regressions_passed(report: dict[str, object]) -> bool:
    release = report.get("release_regressions") or {}
    fixture_ids = tuple(release.get("domain_fixture_ids") or ())
    adversarial_checks = release.get("adversarial_checks") or {}
    return (
        release.get("status") == "passed"
        and fixture_ids == EXPECTED_RELEASE_FIXTURE_IDS
        and bool(adversarial_checks)
        and all(adversarial_checks.values())
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    args = parser.parse_args()

    wheels = [args.wheel] if args.wheel else sorted((args.wheel_dir or Path("dist")).glob("draftpaper_cli-*.whl"))
    if not wheels or wheels[-1] is None or not wheels[-1].is_file():
        raise SystemExit("No draftpaper-cli wheel was found.")
    wheel = wheels[-1].resolve()

    source_summary = _source_registry_summary()

    if source_summary["entry_count"] != EXPECTED_ENTRY_COUNT or source_summary["fixture_count"] != EXPECTED_FIXTURE_COUNT:
        raise SystemExit(
            f"Source registry contract changed: expected {EXPECTED_ENTRY_COUNT}/{EXPECTED_FIXTURE_COUNT}, "
            f"got {source_summary['entry_count']}/{source_summary['fixture_count']}."
        )

    with tempfile.TemporaryDirectory(prefix="draftpaper-wheel-") as temp:
        temp_root = Path(temp)
        environment = temp_root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheel)],
            check=True,
        )
        probe = """
import json
import sys
from unittest.mock import patch
from pathlib import Path
from hashlib import sha256
from importlib.metadata import version
from importlib.resources import files
from draftpaper_cli.capability_packs import discover_capability_packs
from draftpaper_cli.paper_fetch_adapter import resolve_paper_fetch_command
from draftpaper_cli.template_registry import discover_template_registry
from draftpaper_cli.third_party_provenance import validate_third_party_provenance
r = discover_template_registry()
root = Path(r['root'])
with patch('draftpaper_cli.paper_fetch_adapter.shutil.which', return_value=None):
    command, env, runtime_source = resolve_paper_fetch_command()
provenance = validate_third_party_provenance()
skill = files('draftpaper_cli').joinpath('resources/draftpaper_workflow/SKILL.md')
skill_contract = files('draftpaper_cli').joinpath('resources/draftpaper_workflow/contract.json')
release_manifest = files('draftpaper_cli').joinpath('resources/release_manifest.json')
skill_bytes = skill.read_bytes()
contract_bytes = skill_contract.read_bytes()
contract_payload = json.loads(contract_bytes.decode('utf-8'))
release_payload = json.loads(release_manifest.read_text(encoding='utf-8'))
skill_text = skill_bytes.decode('utf-8')
skill_version = next((line.split(':', 1)[1].strip() for line in skill_text.splitlines() if line.startswith('version:')), None)
print(json.dumps({
    'package_version': version('draftpaper-cli'),
    'workflow_skill_version': skill_version,
    'workflow_skill_sha256': sha256(skill_bytes).hexdigest(),
    'workflow_contract_version': contract_payload.get('skill_version'),
    'workflow_contract_sha256': sha256(contract_bytes).hexdigest(),
    'entry_count': r['entry_count'],
    'fixture_count': sum(len(e.get('fixtures') or []) for e in r['entries']),
    'resource_counts': {p: len(list(root.rglob(p))) for p in ('*.json', '*.csv', '*.md')},
    'capability_pack_count': len(discover_capability_packs()),
    'vendored_paper_fetch_present': (
        runtime_source == 'vendored'
        and bool(command)
        and '_vendor' in env.get('PYTHONPATH', '')
        and (Path(env['PYTHONPATH']) / 'paper_fetch' / 'cli.py').is_file()
    ),
    'third_party_provenance_status': provenance['status'],
    'third_party_source_count': provenance['source_count'],
    'release_manifest': release_payload,
}))
"""
        completed = subprocess.run(
            [str(python), "-c", probe],
            check=True,
            cwd=temp_root,
            capture_output=True,
            text=True,
        )
        installed_summary = json.loads(completed.stdout.strip().splitlines()[-1])
        cli_help = subprocess.run(
            [str(python), "-m", "draftpaper_cli.cli", "--help"],
            check=True,
            cwd=temp_root,
            capture_output=True,
            text=True,
        ).stdout
        installed_summary["cli_help_commands"] = [
            command for command in EXPECTED_CLI_COMMANDS if command in cli_help
        ]
        regression_root = temp_root / "release-regressions"
        release_completed = subprocess.run(
            [str(python), "-m", "draftpaper_cli.release_regression", "--output", str(regression_root)],
            check=True,
            cwd=temp_root,
            capture_output=True,
            text=True,
        )
        release_report = json.loads(release_completed.stdout)

    report = {
        "wheel": str(wheel),
        "source": source_summary,
        "installed": installed_summary,
        "matched": source_summary == installed_summary,
        "release_regressions": {
            "status": release_report.get("status"),
            "domain_fixture_ids": [item.get("fixture_id") for item in release_report.get("domain_regressions") or []],
            "adversarial_checks": (release_report.get("adversarial_regressions") or {}).get("checks") or {},
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    release_passed = _release_regressions_passed(report)
    version_passed = installed_summary.get("package_version") == EXPECTED_PACKAGE_VERSION
    return 0 if report["matched"] and release_passed and version_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
