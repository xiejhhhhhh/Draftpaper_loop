from __future__ import annotations

import pytest

from paper_fetch.extraction.html.availability_policy import AvailabilityPolicy
from paper_fetch.extraction.html.provider_rules import (
    ProviderHtmlRules,
    merged_site_rule,
    provider_html_rules,
)
from paper_fetch.quality.html_profiles import site_rule_for_publisher


@pytest.mark.parametrize(
    "publisher",
    [
        None,
        "science",
        "aaas",
        "pnas",
        "wiley",
        "ams",
        "ieee",
        "elsevier",
        "springer_nature",
    ],
)
def test_site_rule_for_publisher_matches_merged_site_rule(
    publisher: str | None,
) -> None:
    assert site_rule_for_publisher(publisher) == merged_site_rule(
        provider_html_rules(publisher)
    )


def test_merged_site_rule_returns_independent_copy() -> None:
    rules = ProviderHtmlRules(
        name="custom",
        availability=AvailabilityPolicy(
            name="custom",
            site_rule_overrides={
                "candidate_selectors": ["article", ".custom-article"],
                "drop_keywords": {"custom-chrome"},
                "nested": {"selectors": [".custom-nested"]},
            },
        ),
    )

    first = merged_site_rule(rules)
    first["candidate_selectors"].append(".mutated")
    first["drop_keywords"].add("mutated")
    first["nested"]["selectors"].append(".mutated")

    second = merged_site_rule(rules)

    assert ".custom-article" in second["candidate_selectors"]
    assert second["candidate_selectors"].count("article") == 1
    assert ".mutated" not in second["candidate_selectors"]
    assert "custom-chrome" in second["drop_keywords"]
    assert "mutated" not in second["drop_keywords"]
    assert second["nested"] == {"selectors": [".custom-nested"]}
