# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

from draftpaper_cli.discipline_modules import get_discipline_module, list_discipline_modules
from draftpaper_cli.template_registry import discover_template_registry, validate_template_registry


ROOT = Path(__file__).resolve().parents[1] / "draftpaper_cli" / "discipline_modules"


def _load_template(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_only_disciplines_are_automatically_registered() -> None:
    module_ids = {item["module_id"] for item in list_discipline_modules()}
    assert {"chemistry", "materials_science", "physics", "quantum_science", "neuroscience"} <= module_ids
    chemistry = get_discipline_module({"discipline": "chemistry"}).spec.as_dict()
    assert len(chemistry["data_connectors"]) >= 3
    assert len(chemistry["method_templates"]) >= 5
    assert len(chemistry["review_rule_groups"]) >= 5
    assert "molecular_standardization" in {item["template_id"] for item in chemistry["method_templates"]}


def test_new_manifest_runtime_fields_are_present_and_valid() -> None:
    report = validate_template_registry()
    assert report["status"] == "passed"
    registry = discover_template_registry()
    expected = {"local_pure_python", "local_optional_dependency", "remote_api", "remote_server", "gpu_model", "laboratory_hardware", "support_only"}
    for entry in registry["entries"]:
        assert entry["runtime_class"] in expected
        assert entry["validation_level"] in {"plan_only", "mock_validated", "fixture_runnable", "live_validated"}


def test_generated_foundation_template_has_fixture_execution_contract() -> None:
    path = ROOT / "chemistry" / "method_templates" / "molecular_standardization" / "template.py"
    module = _load_template(path)
    with tempfile.TemporaryDirectory() as tmp:
        result = module.run_template(
            tmp,
            fixture_path=path.parent / "fixture_minimal.json",
            context={"research_question": "generic molecule preprocessing"},
        )
    assert result["status"] == "written"
    assert Path(result["result"]).name == "plugin_fixture_result.json"


def test_generated_review_rule_stays_advisory_until_promoted() -> None:
    path = ROOT / "quantum_science" / "review_rules" / "classical_baseline_gate" / "template.py"
    module = _load_template(path)
    outcome = module.evaluate_rule({"roles": []})
    assert outcome["decision"] == "review_required"
    assert outcome["blocking"] is False


def test_every_new_foundation_template_imports_and_accepts_its_fixture_contract() -> None:
    registry = discover_template_registry()
    generated = [
        entry for entry in registry["entries"]
        if str((entry.get("manifest_data") or {}).get("provenance_notes") or "").startswith("First-party foundation distilled")
    ]
    local = [entry for entry in generated if entry["runtime_class"] in {"local_pure_python", "local_optional_dependency"}]
    external = [entry for entry in generated if entry["runtime_class"] in {"remote_api", "remote_server", "gpu_model"}]
    assert len(local) >= 80
    assert len(external) >= 10
    for entry in generated:
        plugin_path = ROOT / str(entry["path"])
        module = _load_template(plugin_path / "template.py")
        fixture = plugin_path / "fixture_minimal.json"
        if entry["kind"] == "review":
            outcome = module.evaluate_rule(json.loads(fixture.read_text(encoding="utf-8")))
            assert outcome["blocking"] is False
        else:
            with tempfile.TemporaryDirectory() as tmp:
                result = module.run_template(tmp, fixture_path=fixture)
                assert result["status"] == "written"


def test_manifest_runtime_reads_new_plugin_without_static_module_edit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin = root / "demo_science" / "method_templates" / "demo_method"
        plugin.mkdir(parents=True)
        (plugin / "manifest.json").write_text(json.dumps({
            "template_id": "demo_method",
            "display_name": "Demo method",
            "discipline": "demo_science",
            "method_family": "demo_method",
            "runtime_class": "local_pure_python",
            "validation_level": "fixture_runnable",
        }), encoding="utf-8")
        from draftpaper_cli.discipline_modules.manifest_runtime import dynamic_manifest_module

        module = dynamic_manifest_module("demo_science", root)
        assert module is not None
        assert module.spec.method_template_dicts()[0]["template_id"] == "demo_method"


def test_manifest_overlay_augments_an_existing_plugin_id_without_duplication() -> None:
    from draftpaper_cli.discipline_modules.base import DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec
    from draftpaper_cli.discipline_modules.manifest_runtime import merge_manifest_plugins

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin = root / "demo_science" / "method_templates" / "baseline"
        plugin.mkdir(parents=True)
        (plugin / "template.py").write_text("def run_template():\n    return {}\n", encoding="utf-8")
        (plugin / "manifest.json").write_text(json.dumps({
            "template_id": "baseline",
            "discipline": "demo_science",
            "aliases": ["external baseline"],
            "variants": ["candidate variant"],
            "merge_strategy": "augment_existing",
            "candidate_id": "academicforge_baseline",
            "runtime_class": "local_optional_dependency",
            "validation_level": "plan_only",
        }), encoding="utf-8")
        base = DisciplineModule()
        base.spec = DisciplineModuleSpec(
            module_id="demo_science",
            display_name="Demo science",
            method_templates=[MethodTemplateSpec(
                "baseline", "Baseline", "demo_science", "baseline", aliases=["internal baseline"], maturity="runnable"
            )],
        )
        merged = merge_manifest_plugins(base, root).spec.method_template_dicts()
        assert len(merged) == 1
        assert {"internal baseline", "external baseline"} <= set(merged[0]["aliases"])
        assert merged[0]["merge_strategy"] == "augment_existing"
        assert merged[0]["merged_candidate_ids"] == ["academicforge_baseline"]
