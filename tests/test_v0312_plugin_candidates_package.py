from __future__ import annotations

from pathlib import Path


def test_plugin_candidate_public_api_is_reexported_from_responsibility_package() -> None:
    import draftpaper_cli.plugin_candidates as candidates
    from draftpaper_cli.plugin_candidates import contribution, extractors, promotion, skill_source

    assert Path(candidates.__file__).name == "__init__.py"
    assert candidates.extract_skill_capabilities is extractors.extract_skill_capabilities
    assert candidates.snapshot_skill_source is skill_source.snapshot_skill_source
    assert candidates.promote_plugin_candidate is promotion.promote_plugin_candidate
    assert candidates.package_plugin_contribution is contribution.package_plugin_contribution
    assert candidates._read_registry_json is skill_source._read_registry_json


def test_plugin_candidate_monolith_has_been_removed() -> None:
    package_root = Path(__file__).parents[1] / "draftpaper_cli"
    assert not (package_root / "plugin_candidates.py").exists()
