from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from draftpaper_cli.cli import build_parser
from draftpaper_cli.command_registry import command_spec
from draftpaper_cli.manuscript_completion import (
    COMPLETION_SCHEMA,
    ManuscriptCompletionError,
    manuscript_completion_status,
    prepare_manuscript_completion,
    validate_manuscript_completion_payload,
)
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.schema_registry import schema_family


def _project(tmp_path: Path) -> Path:
    return create_project(
        root=tmp_path,
        idea="Completion schema test",
        field="astronomy",
        target_journal="MNRAS",
    ).path


def test_completion_schema_is_registered_and_prepare_writes_author_template(tmp_path: Path) -> None:
    project = _project(tmp_path)

    result = prepare_manuscript_completion(project)

    assert COMPLETION_SCHEMA == "dpl.manuscript_completion.v1"
    assert schema_family(COMPLETION_SCHEMA) == "manuscript_completion"
    assert result["status"] == "template_written"
    template_path = project / result["template"]
    report_path = project / result["missing_fields"]
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert template["project_id"] == json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"]
    assert template["target_journal"] == "MNRAS"
    assert set(template) == {
        "schema_version",
        "project_id",
        "target_journal",
        "metadata",
        "custom_references",
        "section_revisions",
    }
    assert "authors" in report["missing_required"]
    assert report["schema_version"] == "dpl.manuscript_completion_missing.v1"


def test_missing_report_uses_journal_required_recommended_placeholder_and_not_applicable(tmp_path: Path) -> None:
    project = _project(tmp_path)
    profile = {
        "target_journal": "MNRAS",
        "rules": {"requires_keywords": True},
        "completion_fields": {
            "required": ["title", "authors", "affiliations", "abstract", "keywords", "data_availability"],
            "recommended": ["short_title", "orcid", "funding", "code_availability"],
            "not_applicable": ["ethics_consent"],
        },
    }
    profile_path = project / "journal_profile" / "journal_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    metadata_path = project / "writing" / "manuscript_metadata.yaml"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        yaml.safe_dump(
            {
                "title": "A completed title",
                "authors": [{"id": "author-1", "name": "Draft Author", "affiliations": ["inst-1"]}],
                "affiliations": [{"id": "inst-1", "name": "Institute"}],
                "abstract": "A bounded abstract.",
                "keywords": ["galaxy morphology"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    prepare_manuscript_completion(project)
    report = json.loads(
        (project / "writing" / "manuscript_completion" / "missing_fields.json").read_text(encoding="utf-8")
    )

    assert report["required_fields"] == profile["completion_fields"]["required"]
    assert report["recommended_fields"] == profile["completion_fields"]["recommended"]
    assert report["missing_required"] == ["data_availability"]
    assert set(report["missing_recommended"]) == {"short_title", "orcid", "funding", "code_availability"}
    assert report["placeholder_fields"] == ["authors[0].name"]
    assert report["not_applicable"] == ["ethics_consent"]
    assert report["complete"] is False


def test_completion_payload_validates_metadata_and_reference_schema_without_scientific_evidence_mutation(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    project_id = json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"]
    payload = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": project_id,
        "target_journal": "MNRAS",
        "metadata": {
            "title": "Completed title",
            "short_title": "Short title",
            "keywords": ["galaxies"],
            "authors": [{"id": "author-1", "name": "Alice Example", "affiliations": ["inst-1"]}],
            "affiliations": [{"id": "inst-1", "name": "Institute of Tests"}],
            "funding": [{"funder": "Test Council", "award_id": "ABC-1"}],
            "data_availability": "Data are available from the named archive.",
            "code_availability": "Code is available from the named repository.",
        },
        "custom_references": [
            {
                "citation_key": "Example2026",
                "title": "A bounded reference",
                "authors": ["A. Example"],
                "year": 2026,
                "doi": "10.1234/example",
                "evidence_notes": "Supports the stated comparison boundary.",
            }
        ],
        "section_revisions": [],
    }

    normalized = validate_manuscript_completion_payload(project, payload)

    assert normalized["schema_version"] == COMPLETION_SCHEMA
    assert normalized["metadata"]["funding"][0]["award_id"] == "ABC-1"
    assert normalized["custom_references"][0]["citation_key"] == "Example2026"

    for forbidden in ("scientific_evidence", "result_metrics", "claim_contract", "core_figures"):
        invalid = {**payload, forbidden: {"replace": True}}
        with pytest.raises(ManuscriptCompletionError, match="Unsupported completion fields"):
            validate_manuscript_completion_payload(project, invalid)


def test_completion_status_and_cli_expose_only_v0304_surface(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prepare_manuscript_completion(project)

    status = manuscript_completion_status(project)

    assert status["status"] == "needs_author_input"
    assert status["target_journal"] == "MNRAS"
    assert status["template_exists"] is True
    prepare_spec = command_spec("prepare-manuscript-completion")
    status_spec = command_spec("manuscript-completion-status")
    assert prepare_spec is not None and prepare_spec.handler_name == "prepare_manuscript_completion"
    assert status_spec is not None and status_spec.mutates_project is False
    parser = build_parser()
    assert parser.parse_args(["prepare-manuscript-completion", "--project", str(project)]).command == "prepare-manuscript-completion"
    assert parser.parse_args(["manuscript-completion-status", "--project", str(project)]).command == "manuscript-completion-status"
    assert command_spec("preview-manuscript-completion") is None
    assert command_spec("apply-manuscript-completion") is None
    assert command_spec("rollback-manuscript-completion") is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("funding", [{"award_id": "missing-funder"}], "metadata.funding"),
        ("section_revisions", ["replace the Results"], r"section_revisions\[0\]"),
        (
            "custom_references",
            [
                {
                    "citation_key": "BadYear",
                    "title": "Invalid year",
                    "authors": ["A. Example"],
                    "year": "twenty twenty-six",
                    "evidence_notes": "Boundary note.",
                }
            ],
            "year",
        ),
    ],
)
def test_completion_schema_rejects_unstructured_nested_records(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    project = _project(tmp_path)
    project_id = json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"]
    payload = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": project_id,
        "target_journal": "MNRAS",
        "metadata": {},
        "custom_references": [],
        "section_revisions": [],
    }
    if field in {"custom_references", "section_revisions"}:
        payload[field] = value
    else:
        payload["metadata"][field] = value

    with pytest.raises(ManuscriptCompletionError, match=message):
        validate_manuscript_completion_payload(project, payload)
