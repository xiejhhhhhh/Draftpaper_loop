from __future__ import annotations

import hashlib
import json
from pathlib import Path

from draftpaper_cli.literature_confirmation import (
    build_literature_confirmation_packet,
    confirm_literature_corpus,
)
from draftpaper_cli.literature_teaching_corpus import (
    TEACHING_CORPUS_PATH,
    build_literature_teaching_corpus,
    literature_confirmation_binding,
    literature_confirmation_packet_hash,
    write_literature_teaching_corpus,
)
from draftpaper_cli.references import write_literature_html_summaries


def _write(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _enrichment_hash(document: dict[str, object]) -> str:
    payload = {key: value for key, value in document.items() if key != "enrichment_hash"}
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _project(tmp_path: Path) -> Path:
    references = tmp_path / "references"
    _write(
        references / "reference_registry.json",
        {
            "schema_version": "dpl.reference_registry.v1",
            "status": "ready",
            "project_id": "fixture",
            "records": [
                {
                    "canonical_work_id": "doi:10.1/a",
                    "citation_key": "Astronomy2024",
                    "title_original": "An astronomy paper",
                    "doi_normalized": "10.1/a",
                    "year": "2024",
                }
            ],
        },
    )
    _write(
        references / "active_literature_1.json",
        {
            "items": [
                {
                    "bibtex_key": "Astronomy2024",
                    "title": "An astronomy paper",
                    "abstract": "Specific astronomy abstract.",
                    "citation_eligibility": "eligible",
                },
                {
                    "bibtex_key": "BioAgent2026",
                    "title": "An unrelated biomedical workflow",
                    "abstract": "This is a rejected candidate.",
                },
            ]
        },
    )
    _write(
        references / "reference_usage_plan.json",
        {
            "entries": [
                {
                    "citation_key": "Astronomy2024",
                    "required": True,
                    "citation_role": "dataset_provenance",
                    "citation_intent": "defines the catalogue",
                    "target_section": "data",
                },
                {
                    "citation_key": "BioAgent2026",
                    "citation_role": "method_or_tool_background",
                },
            ]
        },
    )
    (tmp_path / "research_plan").mkdir()
    (tmp_path / "research_plan" / "research_plan.md").write_text("# plan\n", encoding="utf-8")
    binding = literature_confirmation_binding(tmp_path)
    packet = {
        "schema_version": "dpl.literature_confirmation_packet.v1",
        "status": "ready_for_human_confirmation",
        "confirmation_binding": binding,
    }
    packet["packet_hash"] = literature_confirmation_packet_hash(packet)
    _write(references / "literature_confirmation_packet.json", packet)
    _write(
        references / "literature_confirmation_receipt.json",
        {
            "schema_version": "dpl.literature_confirmation_receipt.v1",
            "status": "confirmed",
            "decision": "accepted",
            "confirmation_packet_hash": packet["packet_hash"],
            "confirmation_binding": binding,
        },
    )
    return tmp_path


def test_teaching_corpus_admits_only_the_confirmed_registry_intersection(tmp_path: Path) -> None:
    corpus = build_literature_teaching_corpus(_project(tmp_path))

    assert corpus["corpus_status"] == "confirmed"
    assert corpus["confirmation_source"] == "explicit_confirmation_receipt"
    assert [item["citation_key"] for item in corpus["accepted_works"]] == ["Astronomy2024"]
    assert corpus["accepted_works"][0]["role_bindings"][0]["citation_role"] == "dataset_provenance"
    assert {item["kind"] for item in corpus["accepted_works"][0]["source_artifacts"]} == {
        "active_literature_item",
        "reference_usage_plan_entry",
        "canonical_reference_registry_record",
    }
    assert corpus["excluded_works"] == [
        {
            "citation_key": "BioAgent2026",
            "selection_state": "excluded",
            "reason": "not_in_canonical_registry",
        }
    ]


def test_teaching_corpus_is_hash_bound_and_written_to_one_canonical_path(tmp_path: Path) -> None:
    project = _project(tmp_path)
    first = write_literature_teaching_corpus(project)
    second = build_literature_teaching_corpus(project)

    assert (project / TEACHING_CORPUS_PATH).is_file()
    assert first["corpus_snapshot_hash"] == second["corpus_snapshot_hash"]
    assert first["accepted_works"] == second["accepted_works"]


def test_confirmed_summary_index_uses_the_same_corpus_and_excludes_extra_active_items(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    references = project / "references"
    active = json.loads((references / "active_literature_1.json").read_text(encoding="utf-8"))["items"]

    outputs = write_literature_html_summaries(references, active)
    corpus = json.loads((project / TEACHING_CORPUS_PATH).read_text(encoding="utf-8"))
    index = (references / "literature_summaries" / "index.html").read_text(encoding="utf-8")

    assert TEACHING_CORPUS_PATH in outputs
    assert corpus["corpus_snapshot_hash"] in index
    assert "An astronomy paper" in index
    assert "Unrelated biomedical workflow" not in index
    detail = project / corpus["accepted_works"][0]["summary_detail_path"]
    assert detail.is_file()


def test_summary_index_projects_current_verified_guidance_analysis(tmp_path: Path) -> None:
    project = _project(tmp_path)
    references = project / "references"
    corpus = write_literature_teaching_corpus(project)
    analysis = {
        field: {
            "en": f"Specific {field} explanation.",
            "zh-CN": f"具体的 {field} 说明。",
            "source_ids": ["source:fixture"],
            "statement_scope": "project_synthesis"
            if field in {"relation_to_project", "transfer_boundary"}
            else "paper_synthesis",
            "evidence_quotes": [
                {"source_id": "source:fixture", "quote": f"Original {field} evidence."}
            ],
        }
        for field in (
            "one_sentence",
            "research_question",
            "data",
            "method",
            "validation",
            "result",
            "limitation",
            "contribution",
            "relation_to_project",
            "transfer_boundary",
        )
    }
    enrichment = {
        "schema_version": "dpl.literature_summary_enrichment.v1",
        "core_corpus_snapshot_hash": corpus["corpus_snapshot_hash"],
        "accepted_work_count": 1,
        "verified_analysis_count": 1,
        "papers": [
            {
                "citation_key": "Astronomy2024",
                "analysis": analysis,
                "reading_order": 1,
                "citation_roles": ["dataset_provenance"],
                "prerequisites": ["research_question"],
                "evidence_status": "deep_verified",
            }
        ],
    }
    enrichment["enrichment_hash"] = _enrichment_hash(enrichment)
    _write(
        project / "guidance" / "learning" / "literature" / "core_summary_enrichment.json",
        enrichment,
    )
    active = json.loads((references / "active_literature_1.json").read_text(encoding="utf-8"))["items"]
    active[0]["deep_summary"] = {
        "research_question": "The paper appears to address a topic related to astronomy.",
        "methods": "model-based analysis",
    }

    write_literature_html_summaries(references, active)

    detail = (references / "literature_summaries" / "01_astronomy2024.html").read_text(encoding="utf-8")
    index = (references / "literature_summaries" / "index.html").read_text(encoding="utf-8")
    assert "Specific research_question explanation." in detail
    assert "Specific relation_to_project explanation." in detail
    assert "data-dpl-localized" in detail
    assert "Field-level evidence mapping" in detail
    assert "The paper appears to address" not in detail
    assert "dataset_provenance" in index
    assert "Open the linked learning portal" in index


def test_summary_enrichment_is_rejected_when_its_corpus_hash_is_stale(tmp_path: Path) -> None:
    project = _project(tmp_path)
    references = project / "references"
    corpus = write_literature_teaching_corpus(project)
    _write(
        project / "guidance" / "learning" / "literature" / "core_summary_enrichment.json",
        {
            "schema_version": "dpl.literature_summary_enrichment.v1",
            "core_corpus_snapshot_hash": "sha256:stale",
            "accepted_work_count": 1,
            "verified_analysis_count": 1,
            "papers": [
                {
                    "citation_key": "Astronomy2024",
                    "analysis": {
                        "research_question": {"en": "This stale text must not render.", "zh-CN": "过期内容"}
                    },
                }
            ],
        },
    )
    active = json.loads((references / "active_literature_1.json").read_text(encoding="utf-8"))["items"]

    write_literature_html_summaries(references, active)

    detail = (references / "literature_summaries" / "01_astronomy2024.html").read_text(encoding="utf-8")
    assert corpus["corpus_snapshot_hash"] in detail
    assert "This stale text must not render." not in detail


def test_legacy_active_snapshot_stays_pending_without_human_confirmation(tmp_path: Path) -> None:
    project = _project(tmp_path)
    receipt = project / "references" / "literature_confirmation_receipt.json"
    receipt.unlink()

    corpus = build_literature_teaching_corpus(project)

    assert corpus["corpus_status"] == "confirmation_pending"
    assert corpus["confirmation_source"] == "confirmation_receipt_missing"


def test_confirmed_receipt_is_invalidated_when_its_usage_plan_changes(tmp_path: Path) -> None:
    project = _project(tmp_path)
    usage_path = project / "references" / "reference_usage_plan.json"
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    usage["entries"][0]["citation_intent"] = "changed placement in the current project"
    _write(usage_path, usage)

    corpus = build_literature_teaching_corpus(project)

    assert corpus["corpus_status"] == "confirmation_pending"
    assert corpus["confirmation_source"] == "confirmation_receipt_stale_or_invalid"


def test_hash_bound_literature_confirmation_writes_a_receipt(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write(project / "project.json", {"project_id": "fixture", "stages": {}})
    review = build_literature_confirmation_packet(project)

    result = confirm_literature_corpus(project, packet_hash=review["packet_hash"])

    assert result["status"] == "confirmed"
    markdown = (project / "references" / "literature_confirmation_packet.zh-CN.md").read_text(
        encoding="utf-8"
    )
    assert f"确认哈希：`{review['packet_hash']}`" in markdown
    receipt = json.loads(
        (project / "references" / "literature_confirmation_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["confirmation_packet_hash"] == review["packet_hash"]
    assert build_literature_teaching_corpus(project)["corpus_status"] == "confirmed"
