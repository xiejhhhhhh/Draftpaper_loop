from __future__ import annotations

from collections import Counter

from draftpaper_cli.plugin_catalog import build_plugin_catalog_snapshot
from draftpaper_cli.plugin_manifest_contract import PLUGIN_MANIFEST_SCHEMA_VERSION, migrate_plugin_manifests
from draftpaper_cli.template_registry import discover_template_registry, validate_template_registry


def test_all_builtin_manifests_use_explicit_v2_contracts() -> None:
    report = migrate_plugin_manifests("draftpaper_cli/discipline_modules")
    assert report["status"] == "passed"
    assert report["manifest_count"] == 210
    assert report["changed_count"] == 0
    registry = discover_template_registry()
    assert all(entry["manifest_data"]["schema_version"] == PLUGIN_MANIFEST_SCHEMA_VERSION for entry in registry["entries"])
    assert validate_template_registry()["status"] == "passed"


def test_registry_and_catalog_share_one_runtime_truth() -> None:
    registry = discover_template_registry()
    catalog = build_plugin_catalog_snapshot(refresh=True)
    registry_levels = Counter(entry["runtime_level"] for entry in registry["entries"])
    catalog_levels = Counter(entry["runtime_level"] for entry in catalog["entries"])
    assert registry_levels == catalog_levels
    assert not [entry for entry in catalog["entries"] if entry["execution_contract"]["compatibility_adapter"]]
