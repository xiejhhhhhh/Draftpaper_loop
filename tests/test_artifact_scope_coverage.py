from __future__ import annotations

import json
from pathlib import Path

import draftpaper_cli.artifact_scope as artifact_scope
import draftpaper_cli.passport as passport_module
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project


def test_scope_reports_reachable_missing_tex_dependency(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="scope", field="astronomy").path
    main = project / "latex" / "main.tex"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("\\input{sections/results}\n", encoding="utf-8")
    refresh_project_passport(project, event="fixture")
    report = artifact_scope.collect_artifact_scope(project)
    assert report["status"] == "coverage_incomplete"
    assert any(item["path"] == "latex/sections/results.tex" for item in report["missing"])


def test_large_expected_artifact_blocks_formal_coverage(monkeypatch, tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="large scope", field="astronomy").path
    source = project / "methods" / "large.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("value = 1", encoding="utf-8")
    refresh_project_passport(project, event="fixture")
    monkeypatch.setattr(passport_module, "DIRECT_DISCOVERY_MAX_BYTES", 1)
    monkeypatch.setattr(artifact_scope, "DIRECT_DISCOVERY_MAX_BYTES", 1)

    report = artifact_scope.collect_artifact_scope(project)

    assert report["status"] == "coverage_incomplete"
    assert report["release_eligible"] is False
    assert any(item["path"] == "methods/large.py" for item in report["excluded"])


def test_tex_reachability_uses_latex_compilation_root(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="tex root", field="astronomy").path
    main = project / "latex" / "main.tex"
    section = project / "latex" / "sections" / "methods.tex"
    derived = project / "results" / "derived.tex"
    section.parent.mkdir(parents=True, exist_ok=True)
    derived.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("\\input{sections/methods}\n", encoding="utf-8")
    section.write_text("\\input{../results/derived}\n", encoding="utf-8")
    derived.write_text("Derived result.\n", encoding="utf-8")
    refresh_project_passport(project, event="fixture")

    report = artifact_scope.collect_artifact_scope(project)

    assert not any(item.get("path") == "results/derived.tex" for item in report["missing"])
    assert any(item.get("path") == "results/derived.tex" for item in report["checked"])


def test_scope_preserves_and_reports_declared_path_escape(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="scope escape", field="astronomy").path
    registry = project / "writing" / "scientific_evidence_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"records": [{"source_artifact": "../outside.csv"}]}),
        encoding="utf-8",
    )

    report = artifact_scope.collect_artifact_scope(project)

    escaped = [item for item in report["missing"] if item.get("path") == "../outside.csv"]
    assert escaped
    assert escaped[0]["reason"] == "path_escapes_project_root"
    assert report["status"] == "coverage_incomplete"
    assert report["release_eligible"] is False
