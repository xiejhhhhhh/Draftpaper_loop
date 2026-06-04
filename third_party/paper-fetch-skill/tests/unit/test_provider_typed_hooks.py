from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest
from bs4 import BeautifulSoup

from paper_fetch.extraction.html.provider_rules import (
    AMS_POST_CONTENT_BREAK_TOKENS,
    SCIENCE_POST_CONTENT_BREAK_TOKENS,
    DomHooks,
    MarkdownHooks,
    provider_html_rules,
)
import paper_fetch.providers._ams_html as ams_html
import paper_fetch.providers._iop_html as iop_html
import paper_fetch.providers._pnas_html as pnas_html
import paper_fetch.providers._science_html as science_html
import paper_fetch.providers._wiley_html as wiley_html
from paper_fetch.providers._atypon_browser_workflow_profiles import (
    ATYPON_BROWSER_WORKFLOW_PROVIDER_NAMES,
    publisher_profile,
)


@pytest.mark.parametrize("provider", ATYPON_BROWSER_WORKFLOW_PROVIDER_NAMES)
def test_publisher_profile_hooks_round_trip_provider_rules(provider: str) -> None:
    rules = provider_html_rules(provider)
    profile = publisher_profile(provider)

    assert profile.dom_hooks == rules.dom_hooks
    assert profile.markdown_hooks == rules.markdown_hooks
    assert any(
        getattr(profile.dom_hooks, field.name) is not None
        for field in fields(profile.dom_hooks)
    )
    assert not hasattr(profile, "dom_postprocess")
    assert not hasattr(profile, "markdown_postprocess")
    assert not hasattr(profile, "post_content_break_tokens")


def test_hook_dataclasses_are_frozen() -> None:
    dom_hooks = DomHooks()
    markdown_hooks = MarkdownHooks()

    with pytest.raises(FrozenInstanceError):
        dom_hooks.before_block_normalization = lambda _container: None
    with pytest.raises(FrozenInstanceError):
        markdown_hooks.normalize_markdown = lambda value: value


def test_provider_rules_register_provider_owned_hook_functions() -> None:
    pnas_rules = provider_html_rules("pnas")
    science_rules = provider_html_rules("science")
    wiley_rules = provider_html_rules("wiley")
    ams_rules = provider_html_rules("ams")
    iop_rules = provider_html_rules("iop")

    assert (
        pnas_rules.dom_hooks.before_block_normalization.__name__
        == pnas_html.pnas_before_block_normalization.__name__
    )
    assert (
        pnas_rules.markdown_hooks.suppress_missing_abstract.__name__
        == pnas_html.pnas_suppress_missing_abstract.__name__
    )
    assert (
        science_rules.dom_hooks.asset_figure_extraction.__name__
        == science_html.science_asset_figure_extraction.__name__
    )
    assert (
        science_rules.markdown_hooks.normalize_markdown.__name__
        == science_html.science_normalize_markdown.__name__
    )
    assert (
        wiley_rules.dom_hooks.after_block_normalization.__name__
        == wiley_html.wiley_after_block_normalization.__name__
    )
    assert (
        ams_rules.markdown_hooks.classify_heading.__name__
        == ams_html.ams_classify_heading.__name__
    )
    assert (
        iop_rules.dom_hooks.body_container.__name__
        == iop_html.iop_body_container.__name__
    )
    assert (
        iop_rules.dom_hooks.asset_body_container.__name__
        == iop_html.iop_asset_body_container.__name__
    )
    assert (
        iop_rules.dom_hooks.asset_figure_extraction.__name__
        == iop_html.iop_asset_figure_extraction.__name__
    )


def test_provider_markdown_hooks_preserve_key_behaviour() -> None:
    pnas_hooks = provider_html_rules("pnas").markdown_hooks
    science_hooks = provider_html_rules("science").markdown_hooks
    ams_hooks = provider_html_rules("ams").markdown_hooks

    assert pnas_hooks.suppress_missing_abstract is not None
    assert pnas_hooks.suppress_missing_abstract(
        "# Title\n\n## Significance\n\nText\n\n## Abstract\n\nText"
    )
    assert not pnas_hooks.suppress_missing_abstract("# Title\n\n## Abstract\n\nText")

    assert science_hooks.normalize_markdown is not None
    assert science_hooks.normalize_markdown("*A1*, *B2*") == "*A1, B2*"
    assert science_hooks.keep_unknown_abstract_block is not None
    assert science_hooks.keep_unknown_abstract_block("A substantial abstract block.")

    assert ams_hooks.classify_heading is not None
    assert ams_hooks.classify_heading("Acknowledgments", None) == "body_heading"
    assert ams_hooks.classify_heading("References", None) is None

    assert ams_hooks.normalize_markdown is not None
    normalized = ams_hooks.normalize_markdown(
        "\n\n".join(
            [
                "# Title",
                "## Acknowledgments",
                "Thanks.",
                "## APPENDIX A",
                "Appendix text.",
                "## Data availability statement",
                "Data are archived.",
            ]
        )
    )
    assert normalized.index("## Acknowledgments") < normalized.index(
        "## Data availability statement"
    )
    assert normalized.index("## Data availability statement") < normalized.index(
        "## APPENDIX A"
    )


def test_provider_dom_hooks_preserve_key_behaviour() -> None:
    pnas_hook = provider_html_rules("pnas").dom_hooks.before_block_normalization
    assert pnas_hook is not None
    body_text = "Body text. " * 80
    pnas_soup = BeautifulSoup(
        f"<article><section><p>Sign up for PNAS alerts</p></section><p>{body_text}</p></article>",
        "html.parser",
    )
    pnas_hook(pnas_soup.article)
    assert "Sign up for PNAS alerts" not in pnas_soup.get_text(" ", strip=True)
    assert "Body text." in pnas_soup.get_text(" ", strip=True)

    ams_hook = provider_html_rules("ams").dom_hooks.before_block_normalization
    assert ams_hook is not None
    ams_soup = BeautifulSoup(
        "<article><button class='download-figure'>PowerPoint</button><p>Body text.</p></article>",
        "html.parser",
    )
    ams_hook(ams_soup.article)
    assert "PowerPoint" not in ams_soup.get_text(" ", strip=True)
    assert "Body text." in ams_soup.get_text(" ", strip=True)


def test_post_content_break_tokens_live_in_cleanup_rules() -> None:
    assert (
        provider_html_rules("science").cleanup.post_content_break_tokens
        == SCIENCE_POST_CONTENT_BREAK_TOKENS
    )
    assert (
        provider_html_rules("ams").cleanup.post_content_break_tokens
        == AMS_POST_CONTENT_BREAK_TOKENS
    )
