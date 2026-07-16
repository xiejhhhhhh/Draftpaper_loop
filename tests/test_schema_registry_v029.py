from __future__ import annotations

from pathlib import Path

from draftpaper_cli.schema_registry import schema_registry_report, validate_schema_compatibility


def test_schema_registry_uses_independent_namespaced_families() -> None:
    report = schema_registry_report()
    assert report["status"] == "passed"
    assert report["family_count"] >= 15
    assert validate_schema_compatibility("dpl.result_manifest.v2", "result_manifest")["status"] == "passed"
    legacy = validate_schema_compatibility("v0.16.5", "result_manifest")
    assert legacy["status"] == "failed"
    assert legacy["reason"] == "product_version_used_as_schema"
    assert legacy["adapter"] == "legacy_result_manifest_adapter"


def test_first_party_producers_do_not_emit_product_versions_as_schema_ids() -> None:
    offenders = []
    for path in Path("draftpaper_cli").glob("*.py"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if "schema_version" in line and '"v0.' in line:
                offenders.append(f"{path}:{line_number}")
    assert offenders == []
