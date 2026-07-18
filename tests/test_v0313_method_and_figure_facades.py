from __future__ import annotations

from pathlib import Path


def test_methods_public_api_is_reexported_from_responsibility_package() -> None:
    import draftpaper_cli.methods as methods
    from draftpaper_cli.methods import formulas, verification, writer

    assert Path(methods.__file__).name == "__init__.py"
    assert methods.verify_methods is verification.verify_methods
    assert methods.build_method_writing_context is writer.build_method_writing_context
    assert methods.write_methods is writer.write_methods
    assert methods._write_method_formulas is formulas._write_method_formulas
    assert not (Path(__file__).parents[1] / "draftpaper_cli" / "methods.py").exists()


def test_figure_contract_facade_normalizes_one_deduplicated_issue_list() -> None:
    from draftpaper_cli.figure_contracts import collect_figure_contract_issues

    report = collect_figure_contract_issues(
        gate_report={
            "decision": "revise_required",
            "issues": [{"severity": "blocking", "kind": "missing_method", "detail": "Method output is missing."}],
        },
        semantic_report={
            "decision": "blocked",
            "issues": [{"severity": "blocking", "code": "mixed_dimension", "message": "Axes mix count and score."}],
        },
        alignment_report={
            "decision": "blocked",
            "figure_checks": [{"figure_id": "fig_1", "issues": ["Method output is missing."]}],
        },
        caption_report={
            "decision": "repair_required",
            "figure_checks": [{"figure_id": "fig_1", "issues": ["headline is incomplete"]}],
        },
    )

    assert report["schema_version"] == "dpl.figure_contract_assessment.v1"
    assert report["decision"] == "blocked"
    assert [item["source"] for item in report["issues"]] == [
        "figure_contract_gate",
        "figure_semantics",
        "confirmed_alignment",
        "caption_contract",
    ]
    assert all(set(item) >= {"source", "code", "severity", "message"} for item in report["issues"])
