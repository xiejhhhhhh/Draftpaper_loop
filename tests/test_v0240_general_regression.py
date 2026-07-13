from __future__ import annotations

from draftpaper_cli.capability_packs import evaluate_capability_routing, route_capability_requirement
from draftpaper_cli.command_registry import COMMAND_SPECS


def test_capability_routing_meets_release_thresholds_without_forcing_unknown_topic() -> None:
    report = evaluate_capability_routing()
    assert report["status"] == "passed"
    assert report["precision"] >= 0.95
    assert report["recall"] >= 0.95
    assert not report["ownership"]["conflicts"]

    unknown = route_capability_requirement(
        {
            "kind": "method",
            "method_family": "scribal ductus chronology from multispectral parchment traces",
            "research_question": "Can ink-stroke morphology distinguish manuscript workshops?",
        },
        primary_discipline="palaeography",
        secondary_disciplines=["cultural_heritage"],
    )
    assert unknown["status"] == "unrouted"
    assert unknown["selected_pack_id"] is None


def test_v0240_public_command_surface_contains_recovery_review_revision_and_eval_loops() -> None:
    required = {
        "doctor",
        "recover",
        "eval",
        "prepare-independent-manuscript-review",
        "record-independent-manuscript-review",
        "assess-manuscript-quality-release",
        "build-manuscript-source-map",
        "revise",
        "import-review-findings",
        "list-revision-tasks",
        "prepare-revision",
        "preview-revision",
        "accept-revision",
        "rollback-manuscript-revision",
        "set-manuscript-metadata",
        "add-custom-reference",
    }
    assert required <= set(COMMAND_SPECS)
