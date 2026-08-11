from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.install_profiles import inspect_install_profiles
from draftpaper_cli.release_contract import build_release_manifest
from draftpaper_cli.toml_compat import tomllib


def test_v0350_release_identity_and_literature_contracts() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    manifest = build_release_manifest()
    assert version == "0.37.0"
    assert manifest["package_version"] == version
    assert manifest["command_count"] == 228
    assert {"benchmark-literature-quality", "benchmark-document-parsers"} <= set(manifest["required_cli_commands"])
    matrix = json.loads(Path("docs/capability_truth_matrix.json").read_text(encoding="utf-8"))
    record = next(item for item in matrix["capabilities"] if item["capability_id"] == "cross_discipline_literature_and_document_quality")
    assert record["status"] == "implemented"
    for readme in (Path("README.md"), Path("README.zh-CN.md")):
        content = readme.read_text(encoding="utf-8")
        assert "v0.37.0" in content
        assert "cross_discipline_literature_and_document_quality" in content
        assert "literature_confirmation_packet" in content
        assert "benchmark-document-parsers" in content


def test_mineru_agent_profile_is_dependency_free_and_explicit() -> None:
    report = inspect_install_profiles(module_available=lambda _name: False)
    profile = report["profiles"]["mineru-agent"]
    assert profile["status"] == "available"
    assert profile["required_modules"] == []
    assert "official_mineru_agent_connector" in profile["capabilities"]


def test_frozen_m4_benchmark_reports_are_passing_and_transparent() -> None:
    literature = json.loads(Path("docs/benchmarks/literature_quality_v0.35.0.json").read_text(encoding="utf-8"))
    parsers = json.loads(Path("docs/benchmarks/document_parser_quality_v0.35.0.json").read_text(encoding="utf-8"))
    assert literature["status"] == "passed"
    assert literature["topic_count"] == 8
    assert parsers["status"] == "passed"
    assert parsers["case_count"] == 4
    assert parsers["deployment_required"] is False
    assert "not a live MinerU accuracy benchmark" in parsers["note"]
    assert parsers["route_summary"]["pypdf"]["capability_recall"] < parsers["route_summary"]["official-agent"]["capability_recall"]
