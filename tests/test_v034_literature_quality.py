from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.literature_benchmark import run_document_parser_benchmark, run_literature_quality_benchmark
from draftpaper_cli.literature_language import tokenize_multilingual
from draftpaper_cli.literature_providers import search_provider_router
from draftpaper_cli.literature_search import _fallback_query_plan
from draftpaper_cli.mineru_adapter import parse_literature_document
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.remote_document_policy import check_remote_parse_eligibility
from draftpaper_cli.remote_parser_consent import record_consent


def test_cjk_tokenizer_preserves_topic_phrase_and_ngrams() -> None:
    tokens = tokenize_multilingual("数字乡村与农村治理")
    assert "数字乡村" in tokens
    assert "乡村" in tokens
    assert "农村治理" in tokens


def test_fallback_queries_preserve_query_contract_anchor() -> None:
    plan = _fallback_query_plan({
        "query_contract": {"must_preserve_terms": ["数字乡村"]},
        "query_plan": [{"discipline_anchor": "social science", "query_components": {"idea": ["数字乡村"]}}],
    })
    assert plan
    assert all("数字乡村" in entry["query"] for entry in plan)


def test_provider_router_skips_cross_discipline_sources() -> None:
    calls: list[str] = []

    def fake_openalex(query: str, limit: int) -> list[dict[str, object]]:
        calls.append("openalex")
        return []

    with patch.dict("draftpaper_cli.literature_providers._PROVIDERS", {"openalex": fake_openalex}, clear=False):
        _, report = search_provider_router(
            "数字乡村",
            query_contract={"discipline_hypotheses": ["social_science"], "languages": ["zh-CN"], "must_preserve_terms": ["数字乡村"]},
        )
    assert calls == ["openalex"]
    statuses = {row["provider"]: row["status"] for row in report["provider_status"]}
    assert statuses["europe_pmc"] == "skipped_discipline_mismatch"
    assert statuses["openalex"] == "success_empty"


def test_final_reference_limit_is_applied_after_relevance_gate(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="数字乡村治理", field="社会科学").path
    items = [
        {"title": f"数字乡村治理研究 {index}", "authors": ["Author"], "year": "2024", "doi": f"10.1000/dv{index}", "abstract": "数字乡村治理与农村公共服务。", "source": "openalex"}
        for index in range(5)
    ]
    result = write_reference_outputs(
        project,
        items,
        query="数字乡村治理",
        limit=2,
        search_queries={"query_contract": {"schema_version": "dpl.literature_query.v2", "must_preserve_terms": ["数字乡村"], "optional_terms": [], "discipline_hypotheses": ["social_science"], "languages": ["zh-CN"]}},
    )
    assert result["item_count"] <= 2
    assert len(json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))) <= 2


def test_pypdf_parse_binds_to_doi_work_and_writes_passages(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="PDF evidence", field="science").path
    write_reference_outputs(project, [{"title": "A PDF work", "authors": ["Author"], "year": "2024", "doi": "10.1000/pdfwork", "abstract": "Methods and results for a data study.", "source": "manual", "reference_origin": "manual", "retained": True}], query="PDF evidence")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    with patch("draftpaper_cli.mineru_adapter.extract_pypdf_pages", return_value=[]), patch("draftpaper_cli.mineru_adapter._extract_pdf_text_from_path", return_value="A PDF work\nDOI 10.1000/pdfwork\nMethods and results"):
        result = parse_literature_document(project, pdf, use_mineru=False, parser="pypdf")
    assert result["receipt"]["parser"] == "pypdf"
    assert result["binding"]["status"] == "bound"
    items = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    assert items[0]["document_parses"]
    assert items[0]["binding_status"] == "bound_to_work"
    assert (project / "references" / "literature_work_registry.json").is_file()


def test_remote_policy_requires_public_class_and_consent(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    assert not check_remote_parse_eligibility(pdf, page_count=2, document_class="unpublished", consent="project")["eligible"]
    assert check_remote_parse_eligibility(pdf, page_count=2, document_class="published-public", consent="project")["eligible"]


def test_frozen_quality_benchmarks_pass_without_mineru_deployment(tmp_path: Path) -> None:
    literature = run_literature_quality_benchmark(tmp_path / "literature.json")
    parser = run_document_parser_benchmark(tmp_path / "parser.json")
    assert literature["status"] == "passed"
    assert parser["status"] == "passed"
    assert parser["deployment_required"] is False


def test_project_consent_enables_official_agent_and_refreshes_html_index(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="PDF evidence", field="science").path
    write_reference_outputs(
        project,
        [{"title": "A PDF work", "authors": ["Author"], "year": "2024", "doi": "10.1000/pdfwork", "abstract": "Methods and results for a data study.", "source": "manual", "reference_origin": "manual", "retained": True}],
        query="PDF evidence",
    )
    record_consent(project, decision="project", service="official-agent", document_classes=["published-public"])
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    with patch("draftpaper_cli.mineru_adapter.extract_pypdf_pages", return_value=[{"page": 1, "text": "A PDF work\nDOI 10.1000/pdfwork", "char_count": 30}]), patch(
        "draftpaper_cli.mineru_adapter._extract_pdf_text_from_path", return_value="A PDF work\nDOI 10.1000/pdfwork"
    ), patch("draftpaper_cli.mineru_agent_client.parse_with_official_agent", return_value={"status": "parsed", "route": "official-agent", "markdown": "# Methods\nA reproducible method."}) as remote:
        result = parse_literature_document(project, pdf, parser="mineru", mineru_route="official-agent", document_class="published-public")
    assert result["receipt"]["remote_upload"] is True
    assert remote.call_count == 1
    index = (project / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
    assert "official-agent" in index
    report = json.loads((project / "references" / "document_parse_cost_report.json").read_text(encoding="utf-8"))
    assert report["records"][0]["remote_upload"] is True


def test_remote_parse_cache_prevents_duplicate_upload(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="PDF evidence", field="science").path
    write_reference_outputs(project, [{"title": "A PDF work", "authors": ["Author"], "year": "2024", "doi": "10.1000/pdfwork", "abstract": "Methods and results.", "source": "manual", "reference_origin": "manual", "retained": True}], query="PDF evidence")
    record_consent(project, decision="project", service="official-agent", document_classes=["published-public"])
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    with patch("draftpaper_cli.mineru_adapter.extract_pypdf_pages", return_value=[{"page": 1, "text": "", "char_count": 0}]), patch("draftpaper_cli.mineru_adapter._extract_pdf_text_from_path", return_value=""), patch(
        "draftpaper_cli.mineru_agent_client.parse_with_official_agent", return_value={"status": "parsed", "route": "official-agent", "markdown": "# Results\nA result."}
    ) as remote:
        first = parse_literature_document(project, pdf, parser="mineru", mineru_route="official-agent", document_class="published-public")
        second = parse_literature_document(project, pdf, parser="mineru", mineru_route="official-agent", document_class="published-public")
    assert first["status"] == "parsed"
    assert second["status"] == "cached"
    assert remote.call_count == 1


def test_literature_confirmation_packet_is_generated_without_auto_citation(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="数字乡村治理", field="社会科学").path
    write_reference_outputs(project, [{"title": "数字乡村建设与农村治理", "authors": ["Author"], "year": "2024", "doi": "10.1000/village", "abstract": "数字乡村治理与数据治理。", "source": "openalex"}], query="数字乡村治理")
    packet = json.loads((project / "references" / "literature_confirmation_packet.json").read_text(encoding="utf-8"))
    assert packet["policy"]["does_not_auto_cite"] is True
    assert (project / "references" / "literature_confirmation_packet.zh-CN.md").is_file()
    assert (project / "references" / "unresolved_reference_tasks.json").is_file()
