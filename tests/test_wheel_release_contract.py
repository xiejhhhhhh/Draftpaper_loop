from __future__ import annotations

from tools.verify_wheel_install import (
    EXPECTED_ENTRY_COUNT,
    EXPECTED_FIXTURE_COUNT,
    EXPECTED_PACKAGE_VERSION,
    _source_registry_summary,
)


def test_wheel_release_contract_matches_source_checkout() -> None:
    summary = _source_registry_summary()

    assert summary["package_version"] == EXPECTED_PACKAGE_VERSION
    assert summary["workflow_skill_version"] == EXPECTED_PACKAGE_VERSION
    assert summary["workflow_contract_version"] == EXPECTED_PACKAGE_VERSION
    assert summary["entry_count"] == EXPECTED_ENTRY_COUNT
    assert summary["fixture_count"] == EXPECTED_FIXTURE_COUNT
