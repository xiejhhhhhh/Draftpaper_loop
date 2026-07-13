from __future__ import annotations

from draftpaper_cli.release_regression import FIXTURE_NAMES, run_release_regressions


def test_v025_four_domain_and_adversarial_release_regressions(tmp_path) -> None:
    report = run_release_regressions(tmp_path)

    assert report["status"] == "passed"
    assert tuple(item["fixture_id"] for item in report["domain_regressions"]) == FIXTURE_NAMES
    assert all(all(item["checks"].values()) for item in report["domain_regressions"])
    assert all(report["adversarial_regressions"]["checks"].values())
    assert "not manuscript quality" in report["quality_claim_policy"]
