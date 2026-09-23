from __future__ import annotations

from draftpaper_cli.manuscript_scientific_surface import compare_manuscript_text


def test_numeric_and_negation_changes_are_scientific() -> None:
    result = compare_manuscript_text("The method does not improve F1=0.81.", "The method improves F1=0.98.")
    assert result["classification"] == "scientific_semantics_changed"
    assert result["numbers_changed"] is True
    assert result["negation_changed"] is True


def test_formatting_wrapper_change_is_presentation_only() -> None:
    result = compare_manuscript_text("Accuracy is 0.81.", r"\textbf{Accuracy} is 0.81.")
    assert result["classification"] == "presentation_only"
