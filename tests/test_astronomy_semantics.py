from __future__ import annotations

from draftpaper_cli.data_contracts import available_data_roles
from draftpaper_cli.discipline_modules import get_discipline_module
from draftpaper_cli.research_plan import _cn_term
from draftpaper_cli.research_plan_brief import build_research_plan_decision_brief


ASTRONOMY_PROFILE = {
    "primary_discipline": "astronomy",
    "secondary_disciplines": ["machine_learning"],
}
GEOGRAPHY_PROFILE = {"primary_discipline": "geography"}


def _specialized_inventory() -> dict:
    return {
        "files": [
            {"path": "data/processed/section25_formal_event_manifest.csv", "suffix": ".csv", "columns": []},
            {"path": "data/processed/section25_acceptance_report.json", "suffix": ".json", "columns": []},
            {"path": "data/processed/current_tokens_v3.csv", "suffix": ".csv", "columns": []},
            {"path": "data/processed/history_tokens_v3.csv", "suffix": ".csv", "columns": []},
            {"path": "data/processed/spectral_fit_features_v3.csv", "suffix": ".csv", "columns": []},
            {"path": "data/processed/spectrum_file_inventory_v3.csv", "suffix": ".csv", "columns": ["lv_version"]},
        ]
    }


def test_astronomy_data_role_extensions_are_profile_scoped() -> None:
    astronomy_roles = set(
        available_data_roles(
            _specialized_inventory(),
            {"discipline_profile": ASTRONOMY_PROFILE},
        )
    )
    geography_roles = set(
        available_data_roles(
            _specialized_inventory(),
            {"discipline_profile": GEOGRAPHY_PROFILE},
        )
    )

    assert {
        "formal_event_manifest",
        "data_acceptance_report",
        "current_observation_tokens",
        "history_sequence_tokens",
        "spectral_or_remote_sensing_features",
        "spectrum_file_inventory",
        "processing_level",
    } <= astronomy_roles
    assert "formal_event_manifest" not in geography_roles
    assert "data_acceptance_report" not in geography_roles
    assert "spectrum_file_inventory" not in geography_roles
    assert "processing_level" not in geography_roles


def test_astronomy_terminology_is_not_exposed_by_generic_translation() -> None:
    phrase = "Frozen all-post and later-only AGN/XRB performance"

    assert _cn_term(phrase, ASTRONOMY_PROFILE) == "冻结的边界后全事件与边界后新出现源 AGN/XRB 分类性能"
    assert _cn_term("physical_spectrum_branch", ASTRONOMY_PROFILE) == "物理能谱分支"
    assert "边界后" not in _cn_term(phrase)
    assert _cn_term("physical_spectrum_branch") == "physical spectrum branch"
    assert "能谱" not in _cn_term("physical_spectrum_branch", GEOGRAPHY_PROFILE)


def test_composite_astronomy_machine_learning_profile_preserves_extensions() -> None:
    module = get_discipline_module(ASTRONOMY_PROFILE)
    serialized = module.spec.as_dict()

    assert module.spec.module_id == "composite:astronomy+machine_learning"
    assert serialized["data_role_aliases"]["section25_formal_event_manifest"] == "formal_event_manifest"
    assert serialized["filename_role_markers"]["spectral_fit_features"] == "spectral_or_remote_sensing_features"
    assert serialized["terminology_zh_cn"]["physical_spectrum_branch"] == "物理能谱分支"
    assert "AGN/XRB" in serialized["protected_terminology_tokens"]


def test_research_plan_brief_uses_blueprint_discipline_profile() -> None:
    contracts = {
        "research_blueprint": {
            "discipline_profile": ASTRONOMY_PROFILE,
            "research_objective": {
                "working_title": "astronomy time-domain X-ray source classification and machine learning",
                "scientific_objective": "Compare current/history/spectrum evidence.",
                "data_scope": ["Frozen all-post and later-only AGN/XRB performance"],
            },
            "research_claims": [
                {
                    "claim_id": "claim_1",
                    "research_question": "Does the physical_spectrum_branch improve classification?",
                    "expected_finding": "Compare current+spectrum with current-only.",
                    "scientific_claim_boundary": "Interpret only for the later-only source subset.",
                }
            ],
        },
        "figure_storyboard": {
            "figures": [
                {
                    "figure_id": "fig_1",
                    "proposed_title": "Calibration and selective AGN/XRB recommendation",
                    "research_question": "Does the physical_spectrum_branch improve classification?",
                    "expected_finding": "Compare current+spectrum with current-only.",
                    "scientific_claim_boundary": "Interpret only for the later-only source subset.",
                    "required_data": ["spectral_fit_features_v3"],
                    "required_method": ["physical_spectrum_branch"],
                }
            ],
            "tables": [],
        },
        "method_plan": {"method_tasks": []},
        "claim_contract": {"claims": []},
        "statistical_validation_contract": {},
    }

    brief = build_research_plan_decision_brief(
        project_metadata={"idea": "Time-domain classification"},
        fingerprint={"scientific_plan_subject": {"contracts": contracts}},
        semantic_delta={"classification": "scientific_change"},
        limitations=[],
        pre_execution_decision="pass",
        review_rule_decision="pass",
        presentation_contracts=contracts,
    )

    assert brief["title_zh"] == "天文学中的时域 X 射线源分类与机器学习"
    assert brief["figures"][0]["title_zh"] == "概率校准与选择性 AGN/XRB 分类建议"
    assert brief["figures"][0]["required_data"] == ["spectral_fit_features_v3"]
    assert "物理能谱分支" in brief["claims"][0]["research_question_zh"]
    assert brief["discipline_profile"]["primary_discipline"] == "astronomy"
