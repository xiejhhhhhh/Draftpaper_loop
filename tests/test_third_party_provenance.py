from __future__ import annotations

import pytest

from draftpaper_cli.third_party_provenance import (
    ThirdPartyProvenanceError,
    validate_candidate_promotion_provenance,
    validate_third_party_provenance,
)


def _external_candidate() -> dict:
    return {
        "source": "academicforge",
        "upstream_refs": ["academicforge", "scientific_agent_skills"],
        "catalog_ref": "academicforge:scientific-agent-skills/sa.astropy",
        "original_repository": "https://github.com/K-Dense-AI/scientific-agent-skills",
        "original_skill_path": "skills/astropy",
        "upstream_commit": "4d97e293dc6f604fb6b63dcd49b9028df413d65b",
        "license_spdx_or_expression": "MIT AND BSD-3-Clause",
        "license_file": "third_party/upstream-skills/k-dense-ai__scientific-agent-skills/LICENSE.snapshot",
        "derivation_kind": "derived_template",
        "copied_code": False,
        "copied_text": False,
        "transformed_fields": ["input_roles", "output_roles"],
    }


def test_repository_third_party_registry_and_formal_plugins_are_traceable() -> None:
    report = validate_third_party_provenance()
    assert report["status"] == "passed"
    assert report["source_count"] >= 6
    assert report["formal_plugin_count"] >= 200
    assert report["issues"] == []


def test_academicforge_cannot_be_terminal_plugin_provenance() -> None:
    candidate = _external_candidate()
    candidate.pop("original_repository")
    with pytest.raises(ThirdPartyProvenanceError, match="direct and transitive provenance"):
        validate_candidate_promotion_provenance(candidate)


def test_unknown_license_or_unlocated_copied_code_cannot_be_promoted() -> None:
    unknown = _external_candidate()
    unknown["license_spdx_or_expression"] = "NOASSERTION"
    with pytest.raises(ThirdPartyProvenanceError, match="License-unknown"):
        validate_candidate_promotion_provenance(unknown)

    copied = _external_candidate()
    copied["copied_code"] = True
    with pytest.raises(ThirdPartyProvenanceError, match="source_code_path"):
        validate_candidate_promotion_provenance(copied)
