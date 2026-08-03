from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.literature_code_enrichment import enrich_literature_code_leads, score_code_source, select_versions
from draftpaper_cli.project_scaffold import create_project


def test_enrichment_is_retained_work_scoped_and_metadata_only(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Digital village evaluation", field="rural geography").path
    (project / "references" / "literature_items.json").write_text(
        json.dumps({"items": [
            {"title": "Retained paper", "doi": "10.1000/retained", "retained": True},
            {"title": "Unselected paper", "doi": "10.1000/unselected", "retained": False},
        ]}),
        encoding="utf-8",
    )
    github_seed = tmp_path / "github.json"
    github_seed.write_text(json.dumps([{
        "paper_doi": "10.1000/retained",
        "full_name": "org/retained",
        "html_url": "https://github.com/org/retained",
        "license": {"spdx_id": "MIT"},
        "stargazers_count": 10,
        "forks_count": 2,
        "has_readme": True,
        "latest_release": {"tag_name": "v1.0.0", "published_at": "2026-01-01"},
    }]), encoding="utf-8")
    result = enrich_literature_code_leads(project, providers="github", github_metadata=github_seed)
    assert result["work_count"] == 1
    assert result["metadata_only"] is True
    records = json.loads((project / "references" / "code_sources.json").read_text(encoding="utf-8"))["records"]
    assert len(records) == 1
    assert records[0]["verification_status"] == "metadata_only"
    assert records[0]["download_status"] == "not_requested"
    assert (project / "references" / "code_source_index.html").is_file()


def test_version_policy_keeps_latest_and_historical_lineage() -> None:
    records = [
        {"code_work_id": "code:x", "code_source_id": "old", "version": "0.9", "release_date": "2024-01-01", "latest_stable": True},
        {"code_work_id": "code:x", "code_source_id": "new", "version": "1.0", "release_date": "2026-01-01", "latest_stable": True},
    ]
    selected = select_versions(records, "knowledge_base")
    assert [item["selection_status"] for item in selected].count("selected_candidate") == 1
    assert next(item for item in selected if item["selection_status"] == "selected_candidate")["code_source_id"] == "new"
    assert any(item["version_role"] == "historical" for item in selected)


def test_quality_signal_missing_is_unknown_and_cannot_open_risk_gate() -> None:
    record = {"code_source_id": "x", "link_evidence": [], "license": None, "latest_stable": True}
    scored = score_code_source(record)
    assert scored["quality_signal_audit"]["github_stars"]["normalized_value"] is None
    assert scored["quality_scores"]["risk_gate"] == "review_required"


def test_quality_signals_record_age_adjusted_normalization_and_field_cohort() -> None:
    record = {
        "code_source_id": "aged",
        "link_evidence": [{"evidence_type": "explicit"}],
        "license": "MIT",
        "latest_stable": True,
        "release_date": "2025-01-01",
        "quality_signals": {
            "github_stars": 100,
            "github_forks": 10,
            "paper_citation_count": 50,
            "software_citation_count": 5,
            "github_created_at": "2020-01-01",
            "paper_publication_year": 2022,
            "software_publication_year": 2024,
            "signals_retrieved_at": "2026-08-03T00:00:00Z",
            "discipline": "astronomy",
        },
    }
    scored = score_code_source(record)
    stars = scored["quality_signal_audit"]["github_stars"]
    paper = scored["quality_signal_audit"]["paper_citations"]
    assert stars["exposure_years"] == 7.0
    assert paper["exposure_years"] == 5.0
    assert stars["confidence"] == "observed_age_adjusted"
    assert paper["normalization_cohort"] == "project_candidates:astronomy"
