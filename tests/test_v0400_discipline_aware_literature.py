from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from draftpaper_cli.literature_discipline_policy import assess_discipline_compatibility, discipline_evidence
from draftpaper_cli.literature_fetch_policy import load_literature_fetch_policy
from draftpaper_cli.literature_benchmark import run_literature_quality_benchmark
from draftpaper_cli.literature_integrity import (
    audit_literature_integrity,
    manage_orphan_literature_quarantine,
    rollback_orphan_literature_quarantine,
)
from draftpaper_cli.literature_language import discipline_hypotheses
from draftpaper_cli.literature_provider_planner import plan_provider_ids
from draftpaper_cli.literature_relevance import apply_relevance_gate
from draftpaper_cli.literature_search import search_literature_for_project
from draftpaper_cli.paper_identity_resolution import resolve_candidate_identity, resolve_literature_identities
from draftpaper_cli.paper_fetch_adapter import enrich_with_paper_fetch
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.schema_registry import validate_schema_compatibility


def _contract(*, entities: list[str], disciplines: list[str], methods: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": "dpl.literature_query.v3",
        "entity_anchors": entities,
        "discipline_anchors": [],
        "method_anchors": methods or [],
        "generic_terms": ["population", "classification", "catalog", "diversity"],
        "optional_terms": [],
        "discipline_hypotheses": disciplines,
    }


def _candidate(title: str, abstract: str, **extra: object) -> dict[str, object]:
    return {
        "title": title,
        "authors": ["A. Author"],
        "year": "2025",
        "abstract": abstract,
        **extra,
    }


def _write_contract(project, contract: dict[str, object]) -> None:
    (project / "references" / "query_contract.json").write_text(json.dumps(contract), encoding="utf-8")


def test_ecology_markers_do_not_fall_back_to_general() -> None:
    text = "Ecological biodiversity and ecosystem multifunctionality across habitats"
    assert "ecology" in discipline_hypotheses(text)
    evidence = discipline_evidence(text)
    ecology = next(row for row in evidence if row["discipline"] == "ecology")
    assert {"ecological", "biodiversity", "ecosystem"} <= set(ecology["high_specificity_markers"])


def test_unclassified_content_is_unknown_not_general() -> None:
    assert discipline_hypotheses("A generic reusable workflow") == ["discipline_unknown"]


def test_astronomy_ecology_conflict_is_symmetric() -> None:
    ecology_evidence = discipline_evidence("ecological biodiversity and ecosystem structure")
    astronomy_evidence = discipline_evidence("galaxy redshift and astrophysics")
    forward = assess_discipline_compatibility(["astronomy"], ["ecology"], candidate_evidence=ecology_evidence)
    reverse = assess_discipline_compatibility(["ecology"], ["astronomy"], candidate_evidence=astronomy_evidence)
    assert forward["state"] == "rejected"
    assert reverse["state"] == "rejected"


def test_explicit_method_transfer_is_reviewable_not_silently_active() -> None:
    assessment = assess_discipline_compatibility(
        ["astronomy"],
        ["machine_learning"],
        candidate_evidence=discipline_evidence("deep learning neural network"),
        item={"cross_discipline_role": "method_transfer"},
    )
    assert assessment["state"] == "review_required"
    assert assessment["score"] < 1.0


def test_shared_population_classification_words_cannot_activate_ecology_for_astronomy() -> None:
    contract = _contract(entities=["galaxy"], disciplines=["astronomy"])
    accepted, rejected = apply_relevance_gate(
        [_candidate("Population classification catalog", "Ecological biodiversity and ecosystem population diversity.")],
        contract,
    )
    assert accepted == []
    assert rejected[0]["candidate_state"] == "rejected"
    assert "discipline_mismatch" in rejected[0]["rejection_codes"]


def test_high_specificity_astronomy_anchor_remains_active() -> None:
    contract = _contract(entities=["Euclid", "galaxy", "redshift"], disciplines=["astronomy"])
    accepted, rejected = apply_relevance_gate(
        [_candidate("Euclid galaxy population catalog", "Galaxy redshift classification for astrophysics.")],
        contract,
    )
    assert rejected == []
    assert accepted[0]["gate_state"] == "accepted"
    assert accepted[0]["topic_relevance_score"] >= 0.55


def test_astronomy_provider_plan_prioritizes_ads_before_supplemental_openalex() -> None:
    selected, decisions = plan_provider_ids(
        {"discipline_hypotheses": ["astronomy"], "languages": ["en"]},
        ["openalex", "pubmed", "nasa_ads"],
    )
    assert selected == ["nasa_ads", "openalex"]
    assert decisions["nasa_ads"] == "planned_primary"
    assert decisions["openalex"] == "planned_supplemental"
    assert decisions["pubmed"] == "skipped_discipline_mismatch"


def test_online_search_uses_discipline_provider_router_by_default(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    with patch("draftpaper_cli.literature_search.search_free_literature", return_value=[]), patch(
        "draftpaper_cli.literature_search.search_provider_router",
        return_value=([], {"provider_status": [], "degraded": False}),
    ) as routed, patch(
        "draftpaper_cli.literature_search.enrich_with_paper_fetch",
        side_effect=lambda project_path, items: (items, {"status": "skipped"}),
    ):
        search_literature_for_project(project, enrich_code_sources=False)
    assert routed.call_count >= 1


def test_default_fetch_policy_is_hash_bound_and_disables_assets(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Galaxy morphology", field="astronomy").path
    policy = load_literature_fetch_policy(project)
    assert policy["mode"] == "resolve_then_fetch_on_demand"
    assert policy["asset_profile"] == "none"
    assert policy["policy_hash"].startswith("sha256:")
    written = json.loads((project / "references" / "literature_fetch_policy.json").read_text(encoding="utf-8"))
    assert written["policy_hash"] == policy["policy_hash"]


def test_doi_identity_resolution_writes_exact_hash_bound_receipt(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Galaxy morphology", field="astronomy").path
    items, summary = resolve_literature_identities(
        project,
        [_candidate("Euclid galaxy morphology", "Galaxy morphology evidence.", doi="https://doi.org/10.1000/EUCLID")],
        query_contract=_contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"]),
    )
    receipt = items[0]["identity_resolution_receipt"]
    assert receipt["status"] == "resolved_exact"
    assert receipt["checks"]["doi_match"] is True
    assert receipt["input_hash"].startswith("sha256:")
    assert summary["resolved_count"] == 1
    assert (project / "references" / "paper_identity_resolutions.jsonl").is_file()


def test_identity_mismatch_is_not_promoted() -> None:
    item = _candidate("Euclid galaxy morphology", "Astronomy.", doi="10.1000/input")
    receipt = resolve_candidate_identity(
        item,
        resolver=lambda _: {
            "doi": "10.1000/different",
            "title": "Ecological biodiversity classification",
            "authors": ["B. Researcher"],
            "year": "2018",
            "confidence": 1.0,
            "independently_resolved_fields": ["doi", "title", "authors", "year"],
        },
    )
    assert receipt["status"] == "mismatch"
    assert {"doi_mismatch", "title_mismatch", "author_mismatch", "year_mismatch"} <= set(receipt["reason_codes"])


def test_ambiguous_title_resolution_is_explicit() -> None:
    receipt = resolve_candidate_identity(
        _candidate("Shared paper title", "A study."),
        resolver=lambda _: {
            "title": "Shared paper title",
            "confidence": 0.7,
            "candidates": [{"doi": "10.1/a"}, {"doi": "10.1/b"}],
            "independently_resolved_fields": ["title"],
        },
    )
    assert receipt["status"] == "ambiguous"
    assert receipt["reason_codes"] == ["multiple_resolution_candidates"]


def test_resolution_provider_failure_is_per_candidate_degraded(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Galaxy morphology", field="astronomy").path

    def fail(_: dict[str, object]) -> dict[str, object]:
        raise TimeoutError("provider timeout")

    original = _candidate("Title-only candidate", "Galaxy morphology evidence.")
    items, summary = resolve_literature_identities(project, [original], resolver=fail, allow_network=True)
    assert items[0]["title"] == original["title"]
    assert items[0]["identity_resolution_status"] == "provider_degraded"
    assert summary["status_counts"]["provider_degraded"] == 1


def test_stable_identity_receipt_is_reused_by_input_hash(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Galaxy morphology", field="astronomy").path
    calls = 0

    def resolver(_: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "doi": "10.1000/title-resolved",
            "title": "Galaxy morphology catalogue",
            "authors": ["A. Author"],
            "year": "2025",
            "confidence": 0.99,
            "independently_resolved_fields": ["doi", "title", "authors", "year"],
        }

    item = _candidate("Galaxy morphology catalogue", "Galaxy astrophysics evidence.")
    first, _ = resolve_literature_identities(project, [item], resolver=resolver)
    second, _ = resolve_literature_identities(project, [item], resolver=resolver)
    assert calls == 1
    assert first[0]["identity_resolution_receipt"]["cache_hit"] is False
    assert second[0]["identity_resolution_receipt"]["cache_hit"] is True


def test_on_demand_fetch_produces_active_postfetch_candidate(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    contract = _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"])
    _write_contract(project, contract)
    commands: list[list[str]] = []

    def runner(command, *, cwd, env, timeout):
        commands.append(command)
        output_path = command[command.index("--output") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "markdown": "# Methods\nEuclid galaxy morphology and redshift evidence.",
                    "article": {
                        "metadata": {
                            "doi": "10.1000/euclid",
                            "title": "Euclid galaxy morphology",
                            "authors": ["A. Author"],
                            "year": "2025",
                            "abstract": "Euclid galaxy morphology and redshift evidence for astrophysics.",
                        }
                    },
                },
                handle,
            )
        return {"returncode": 0, "stdout": "", "stderr": ""}

    active, manifest = enrich_with_paper_fetch(
        project,
        [_candidate("Euclid galaxy morphology", "", doi="10.1000/euclid", search_context="methods")],
        runner=runner,
    )
    assert manifest["status"] == "completed"
    assert manifest["attempted_count"] == 1
    assert active[0]["postfetch_state"] == "accepted_active"
    assert active[0]["citation_eligibility"] == "eligible_for_declared_role"
    assert "--asset-profile" in commands[0]
    assert commands[0][commands[0].index("--asset-profile") + 1] == "none"


def test_verified_fulltext_cache_prevents_duplicate_fetch(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    _write_contract(project, _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"]))
    calls = 0

    def runner(command, *, cwd, env, timeout):
        nonlocal calls
        calls += 1
        output_path = command[command.index("--output") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "markdown": "# Methods\nEuclid galaxy redshift evidence.",
                    "article": {
                        "metadata": {
                            "doi": "10.1000/cache",
                            "title": "Euclid galaxy morphology cache",
                            "authors": ["A. Author"],
                            "year": "2025",
                            "abstract": "Euclid galaxy redshift astrophysics evidence.",
                        }
                    },
                },
                handle,
            )
        return {"returncode": 0, "stdout": "", "stderr": ""}

    candidate = _candidate("Euclid galaxy morphology cache", "", doi="10.1000/cache", search_context="methods")
    first, _ = enrich_with_paper_fetch(project, [candidate], runner=runner)
    second, manifest = enrich_with_paper_fetch(project, [candidate], runner=runner)
    assert calls == 1
    assert first and second
    assert manifest["status"] == "completed_from_cache"
    assert manifest["cache_hit_count"] == 1


def test_fetch_provider_failure_preserves_previous_active_snapshot(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    baseline = _candidate(
        "Euclid galaxy morphology baseline",
        "Euclid galaxy redshift astrophysics evidence.",
        doi="10.1000/preserve",
        source="manual",
        reference_origin="manual",
        retained=True,
    )
    first = write_reference_outputs(project, [baseline], query="Euclid galaxy morphology")
    contract = _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"])
    _write_contract(project, contract)
    active, manifest = enrich_with_paper_fetch(
        project,
        [_candidate("Euclid galaxy morphology baseline", "", doi="10.1000/preserve", search_context="methods")],
        command=["definitely-missing-paper-fetch"],
    )
    assert active == []
    assert manifest["status"] == "unavailable"
    second = write_reference_outputs(
        project,
        active,
        query="Euclid galaxy morphology",
        search_queries={
            "query_contract": contract,
            "paper_fetch_pipeline": {
                "policy_hash": manifest["policy_hash"],
                "quarantined_work_ids": manifest["quarantined_work_ids"],
            },
        },
    )
    assert second["item_count"] == 1
    assert first["item_count"] == second["item_count"]
    items = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    assert items[0]["doi"] == "10.1000/preserve"


def test_ambiguous_identity_never_triggers_fulltext_fetch(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    _write_contract(project, _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"]))

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("ambiguous identity must not fetch")

    active, manifest = enrich_with_paper_fetch(
        project,
        [_candidate("Euclid galaxy morphology", "", search_context="methods")],
        runner=forbidden_runner,
        identity_resolver=lambda _: {
            "title": "Euclid galaxy morphology",
            "confidence": 0.8,
            "candidates": [{"doi": "10.1000/a"}, {"doi": "10.1000/b"}],
            "independently_resolved_fields": ["title"],
        },
    )
    assert active == []
    assert manifest["attempted_count"] == 0
    decisions = json.loads((project / "references" / "fulltext_fetch_decisions.json").read_text(encoding="utf-8"))
    assert decisions["decisions"][0]["reason"] == "identity_ambiguous"


def test_fetched_cross_discipline_identity_mismatch_is_quarantined(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    _write_contract(project, _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"]))

    def runner(command, *, cwd, env, timeout):
        output_path = command[command.index("--output") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "markdown": "# Results\nEcological biodiversity and ecosystem population diversity.",
                    "article": {
                        "metadata": {
                            "doi": "10.1000/euclid",
                            "title": "Ecological biodiversity classification",
                            "authors": ["B. Researcher"],
                            "year": "2018",
                            "abstract": "Ecological biodiversity and ecosystem population diversity.",
                        }
                    },
                },
                handle,
            )
        return {"returncode": 0, "stdout": "", "stderr": ""}

    active, manifest = enrich_with_paper_fetch(
        project,
        [_candidate("Euclid galaxy morphology", "", doi="10.1000/euclid", search_context="methods")],
        runner=runner,
    )
    assert active == []
    assert manifest["quarantine_count"] == 1
    quarantine = json.loads((project / "references" / "quarantined_literature_candidates.json").read_text(encoding="utf-8"))
    assert quarantine["items"][0]["postfetch_state"] == "rejected_identity_mismatch"
    artifact = quarantine["artifacts"][0]
    assert artifact["to"].startswith("references/quarantine/rejected_candidates/")
    assert (project / artifact["to"]).is_file()
    assert not (project / artifact["from"]).exists()


def test_three_fetch_targets_use_one_batch_command(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    _write_contract(project, _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"]))
    titles = [f"Euclid galaxy morphology {index}" for index in range(3)]
    calls: list[list[str]] = []

    def runner(command, *, cwd, env, timeout):
        calls.append(command)
        assert "--query-file" in command
        output_dir = project / "references" / "fulltext"
        results_path = command[command.index("--batch-results") + 1]
        rows = []
        for index, title in enumerate(titles, start=1):
            output_path = output_dir / f"batch_{index}.json"
            output_path.write_text(
                json.dumps(
                    {
                        "markdown": f"# Methods\n{title} redshift astrophysics.",
                        "article": {
                            "metadata": {
                                "doi": f"10.1000/euclid{index}",
                                "title": title,
                                "authors": ["A. Author"],
                                "year": "2025",
                                "abstract": f"{title} redshift astrophysics.",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            rows.append({"index": index, "query": f"10.1000/euclid{index}", "status": "ok", "output_path": str(output_path)})
        with open(results_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(json.dumps(row) for row in rows) + "\n")
        return {"returncode": 0, "stdout": "", "stderr": ""}

    active, manifest = enrich_with_paper_fetch(
        project,
        [
            _candidate(title, "", doi=f"10.1000/euclid{index}", search_context="methods")
            for index, title in enumerate(titles, start=1)
        ],
        runner=runner,
    )
    assert len(calls) == 1
    assert manifest["batch_mode"] is True
    assert manifest["success_count"] == 3
    assert len(active) == 3


def test_active_snapshot_and_bilingual_html_expose_pipeline_identity(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    contract = _contract(entities=["Euclid", "galaxy"], disciplines=["astronomy"])
    _write_contract(project, contract)
    active, manifest = enrich_with_paper_fetch(
        project,
        [
            _candidate(
                "Euclid galaxy morphology",
                "Euclid galaxy redshift morphology for astrophysics.",
                doi="10.1000/euclid",
                search_context="introduction",
            )
        ],
        fetch_policy_mode="resolve_only",
    )
    search_queries = {
        "query_contract": contract,
        "paper_fetch_pipeline": {
            "policy_hash": manifest["policy_hash"],
            "identity_candidate_set_hash": manifest["identity_candidate_set_hash"],
            "query_contract_hash": manifest["query_contract_hash"],
            "decision_packet_hash": manifest["decision_packet_hash"],
            "postfetch_assessment_hash": manifest["postfetch_assessment_hash"],
            "quarantined_work_ids": manifest["quarantined_work_ids"],
        },
    }
    result = write_reference_outputs(project, active, query="Euclid galaxy morphology", search_queries=search_queries)
    snapshot = json.loads((project / "references" / "literature_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["snapshot_hash"] == result["snapshot_hash"]
    assert snapshot["active_work_ids"] == ["doi:10.1000/euclid"]
    assert snapshot["fetch_policy_hash"] == manifest["policy_hash"]
    assert snapshot["postfetch_assessment_hash"] == manifest["postfetch_assessment_hash"]
    html = (project / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
    assert "Literature pipeline summary" in html
    assert "文献处理流程摘要" in html
    assert "Identity status" in html
    assert "身份解析状态" in html
    assert "accepted_active" in html


def test_orphan_quarantine_cli_path_is_preview_hash_apply_and_rollback(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Euclid galaxy morphology", field="astronomy").path
    write_reference_outputs(
        project,
        [
            _candidate(
                "Euclid galaxy morphology",
                "Galaxy morphology evidence.",
                doi="10.1000/euclid",
                source="manual",
                reference_origin="manual",
                retained=True,
            )
        ],
        query="Euclid galaxy morphology",
    )
    orphan = project / "references" / "fulltext" / "ecology_orphan.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text(json.dumps({"doi": "10.1000/ecology", "title": "Ecological biodiversity"}), encoding="utf-8")
    audit_literature_integrity(project)
    preview = manage_orphan_literature_quarantine(project)
    assert preview["status"] == "preview"
    assert preview["artifact_count"] == 1
    assert orphan.is_file()
    with pytest.raises(ValueError, match="hash"):
        manage_orphan_literature_quarantine(project, apply=True, packet_hash="sha256:stale")
    applied = manage_orphan_literature_quarantine(project, apply=True, packet_hash=preview["packet_hash"])
    assert applied["moved_count"] == 1
    assert not orphan.exists()
    rolled_back = rollback_orphan_literature_quarantine(project)
    assert rolled_back["restored_count"] == 1
    assert orphan.is_file()


def test_all_discipline_benchmark_has_zero_hard_negative_activation() -> None:
    report = run_literature_quality_benchmark()
    assert report["status"] == "passed"
    assert report["topic_count"] >= 5
    assert report["mean_positive_recall"] >= 0.95
    assert report["hard_negative_active_count"] == 0
    assert report["mean_off_discipline_contamination_rate"] == 0.0


def test_new_literature_contracts_are_registered_and_packaged() -> None:
    contracts = {
        "literature_query": ("dpl.literature_query.v3", "literature_query_v3.json"),
        "literature_fetch_policy": ("dpl.literature_fetch_policy.v1", "literature_fetch_policy_v1.json"),
        "literature_discipline_ontology": (
            "dpl.literature_discipline_ontology.v1",
            "literature_discipline_ontology_v1.json",
        ),
        "discipline_conflict_matrix": ("dpl.discipline_conflict_matrix.v1", "discipline_conflict_matrix_v1.json"),
        "prefetch_relevance_assessment": (
            "dpl.prefetch_relevance_assessment.v1",
            "prefetch_relevance_assessment_v1.json",
        ),
        "paper_identity_resolution": ("dpl.paper_identity_resolution.v1", "paper_identity_resolution_v1.json"),
        "fulltext_fetch_decision": ("dpl.fulltext_fetch_decision.v1", "fulltext_fetch_decision_v1.json"),
        "paper_fetch_manifest": ("dpl.paper_fetch_manifest.v2", "paper_fetch_manifest_v2.json"),
        "postfetch_relevance_assessment": (
            "dpl.postfetch_relevance_assessment.v1",
            "postfetch_relevance_assessment_v1.json",
        ),
        "literature_quarantine_record": (
            "dpl.literature_quarantine_record.v1",
            "literature_quarantine_record_v1.json",
        ),
    }
    schema_root = Path("draftpaper_cli/resources/schemas")
    for family, (schema_id, filename) in contracts.items():
        assert validate_schema_compatibility(schema_id, family)["status"] == "passed"
        payload = json.loads((schema_root / filename).read_text(encoding="utf-8"))
        assert payload["$id"] == schema_id
