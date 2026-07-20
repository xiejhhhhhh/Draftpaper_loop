from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from draftpaper_cli.release_contract import _sha, build_release_manifest, validate_release_manifest
from draftpaper_cli.release_regression import FIGURE_IDS, FIXTURE_NAMES


def test_release_manifest_is_current_and_security_hardened() -> None:
    report = validate_release_manifest()
    assert report["status"] == "passed", report
    security = report["current"]["release_security"]
    assert security["license_identifier"] == "LicenseRef-Draftpaper-NonCommercial"
    assert security["license_files"] == ["LICENSE", "NOTICE"]
    assert security["github_actions_pinned"] is True
    assert security["ci_constraints_sha256"]
    assert security["sbom_format"] == "CycloneDX JSON"


def test_v030_release_matrix_has_five_domains_and_six_main_groups() -> None:
    manifest = build_release_manifest()
    assert manifest["release_fixture_ids"] == list(FIXTURE_NAMES)
    assert len(FIXTURE_NAMES) == 5
    assert len(FIGURE_IDS) == 6


def test_release_hash_is_stable_across_text_line_endings(tmp_path) -> None:
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    crlf.write_bytes(b"alpha\r\nbeta\r\n")
    assert _sha(lf) == _sha(crlf)


def test_release_contract_uses_resources_from_supplied_root(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    copied_root = tmp_path / "copied-root"
    copied_root.mkdir()
    shutil.copy2(source_root / "pyproject.toml", copied_root / "pyproject.toml")
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(source_root / name, copied_root / name)
    for relative in ("draftpaper_cli", "third_party", "requirements", ".github"):
        shutil.copytree(source_root / relative, copied_root / relative)

    registry_path = copied_root / "draftpaper_cli" / "resources" / "schemas" / "schema_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["schema_version"] = "dpl.schema_registry.copied_root.v1"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    built = build_release_manifest(copied_root)
    assert built["schema_registry_version"] == "dpl.schema_registry.copied_root.v1"

    copied_manifest = copied_root / "draftpaper_cli" / "resources" / "release_manifest.json"
    copied_manifest.write_text(json.dumps(built), encoding="utf-8")
    assert validate_release_manifest(copied_root)["status"] == "passed"

    command_registry = copied_root / "draftpaper_cli" / "command_registry.py"
    command_registry.write_text(
        command_registry.read_text(encoding="utf-8") + "\nCOMMAND_SPECS.clear()\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.release_contract", "--root", str(copied_root)],
        cwd=source_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode != 0, completed.stdout
    assert '"command_count": 210' not in completed.stdout
