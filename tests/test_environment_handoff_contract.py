from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_profile_python_boundaries_match_vendored_runtime_support() -> None:
    from draftpaper_cli.install_profiles import inspect_install_profiles

    report = inspect_install_profiles(
        module_available=lambda _name: True,
        python_version=(3, 10, 14),
    )

    assert report["profiles"]["minimal"]["status"] == "available"
    assert report["profiles"]["plotting"]["status"] == "available"
    assert report["profiles"]["mcp"]["status"] == "available"
    assert report["profiles"]["fulltext"]["status"] == "unsupported_python"
    assert report["profiles"]["research"]["status"] == "unsupported_python"
    assert report["profiles"]["browser"]["status"] == "unsupported_python"


def test_handoff_files_are_present_and_secret_free() -> None:
    required = (
        ROOT / "config" / "environment.example",
        ROOT / "requirements" / "runtime-constraints.txt",
        ROOT / "requirements" / "ci-constraints.txt",
    )
    for path in required:
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8").lower()
        assert "github_pat_" not in text
        assert "api_key=real" not in text
        assert "token=real" not in text

    example = (ROOT / "config" / "environment.example").read_text(encoding="utf-8")
    assert "ZOTERO_API_KEY=" in example
    assert "NASA_ADS_API_TOKEN=" in example
    assert "DRAFTPAPER_MINERU_ENDPOINT=" in example


def test_release_manifest_describes_all_handoff_profiles() -> None:
    manifest = json.loads(
        (ROOT / "draftpaper_cli" / "resources" / "release_manifest.json").read_text(encoding="utf-8")
    )
    environment = manifest["environment_contract"]
    assert environment["status"] == "passed"
    assert set(environment["profiles"]) >= {"minimal", "plotting", "fulltext", "mcp", "browser", "mineru-agent"}
    assert environment["python_ranges"]["fulltext"] == ">=3.11,<3.13"
    assert environment["runtime_constraints"] == "requirements/runtime-constraints.txt"
    assert environment["missing_required_files"] == []
    assert environment["vendored_paper_fetch_import_smoke"] is True


def test_bootstrap_targets_an_independent_python_311_runtime() -> None:
    source = (ROOT / "tools" / "bootstrap_windows_environment.ps1").read_text(encoding="utf-8")
    assert "Python.Python.3.11" in source
    assert "^3\\.11" in source
    assert "hermes-agent" in source
