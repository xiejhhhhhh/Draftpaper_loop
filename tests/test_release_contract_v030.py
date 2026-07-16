from __future__ import annotations

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
