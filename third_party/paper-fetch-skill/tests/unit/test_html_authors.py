from __future__ import annotations

from paper_fetch.providers._html_authors import (
    AuthorExtractionPipeline,
    AuthorStep,
)


def test_author_extraction_pipeline_accepts_callables_and_named_steps() -> None:
    calls: list[str] = []

    def empty_step(html_text: str) -> list[str]:
        calls.append("empty")
        assert html_text == "<html></html>"
        return []

    def author_step(html_text: str) -> list[str]:
        calls.append("authors")
        assert html_text == "<html></html>"
        return ["Ada Lovelace", "Ada Lovelace", "Grace Hopper"]

    def late_step(_: str) -> list[str]:
        calls.append("late")
        return ["Ignored Author"]

    pipeline = AuthorExtractionPipeline(
        empty_step,
        AuthorStep("author-step", author_step),
        AuthorStep("late-step", late_step),
    )

    assert [step.name for step in pipeline.steps] == [
        "empty_step",
        "author-step",
        "late-step",
    ]
    assert pipeline.extractors[0] is empty_step
    assert pipeline("<html></html>") == ["Ada Lovelace", "Grace Hopper"]
    assert calls == ["empty", "authors"]


def test_author_extraction_pipeline_returns_empty_when_all_steps_miss() -> None:
    pipeline = AuthorExtractionPipeline(
        AuthorStep("empty", lambda _: []),
        AuthorStep("also-empty", lambda _: []),
    )

    assert pipeline("<html></html>") == []
