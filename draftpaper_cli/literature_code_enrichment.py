"""Metadata-first GitHub/Zenodo enrichment for retained literature."""

from __future__ import annotations

import html
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .code_sources.archive_security import audit_archive_license, inspect_archive, safe_download_archive
from .code_sources.base import canonical_url, normalize_work_id
from .code_sources.github import github_record_from_metadata, search_github
from .code_sources.zenodo import search_zenodo, zenodo_record_from_metadata
from .html_utils import write_html_report
from .project_scaffold import _write_json
from .project_state import load_project


CODE_SOURCES_JSON = "references/code_sources.json"
CODE_PROVENANCE_JSON = "references/code_source_provenance.json"
CODE_CANDIDATES_JSON = "references/code_source_candidates.json"
CODE_INDEX_HTML = "references/code_source_index.html"
CODE_QUALITY_HTML = "references/code_source_quality_report.html"
SELECTION_MODES = {"knowledge_base", "reproduction", "historical_reference", "citation_only", "plugin_candidate"}


class LiteratureCodeEnrichmentError(RuntimeError):
    """Raised when a code-source enrichment request is malformed."""


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback
    return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_tuple(providers: tuple[str, ...] | str) -> tuple[str, ...]:
    if isinstance(providers, str):
        providers = tuple(item.strip().lower() for item in providers.split(","))
    return tuple(dict.fromkeys(str(item).strip().lower() for item in providers if str(item).strip()))


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")[:96] or "candidate"


def _items(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path, [])
    raw = payload.get("items", payload) if isinstance(payload, dict) else payload
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _selected(item: dict[str, Any], selection: set[str]) -> bool:
    if "all" in selection:
        return True
    if "retained" in selection and item.get("retained"):
        return True
    if "anchor" in selection and (item.get("discipline_anchor") or item.get("target_journal_anchor")):
        return True
    if "user_selected" in selection and (item.get("user_confirmed") or item.get("selection_policy") == "user_curated_preserve"):
        return True
    return bool(item.get("code_source_selected") or item.get("research_code_lead"))


def _candidate_strings(item: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for key in ("github_url", "repository_url", "code_url", "software_url", "repository", "zenodo_doi", "software_doi", "url"):
        value = item.get(key)
        if isinstance(value, str):
            values.append((value, key))
    related = item.get("related_identifiers") or item.get("relatedIdentifier") or []
    if isinstance(related, dict):
        related = [related]
    for entry in related:
        if isinstance(entry, dict):
            value = entry.get("identifier") or entry.get("url")
            relation = entry.get("relation") or entry.get("relation_type") or "related_identifier"
        else:
            value = entry
            relation = "related_identifier"
        if isinstance(value, str):
            values.append((value, str(relation)))
    return values


def _provider_from_url(value: str) -> str | None:
    if str(value).lower().startswith("10.5281/zenodo."):
        return "zenodo"
    host = (urlsplit(value).hostname or "").lower()
    if host in {"github.com", "www.github.com"}:
        return "github"
    if "zenodo.org" in host:
        return "zenodo"
    return None


def _load_provider_seed(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = _read_json(Path(path).expanduser().resolve(), [])
    if isinstance(payload, dict):
        for key in ("records", "items", "repositories", "hits"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        return [payload]
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _matches_seed(seed: dict[str, Any], item: dict[str, Any], work_id: str) -> bool:
    if seed.get("work_id") and str(seed.get("work_id")) == work_id:
        return True
    item_doi = str(item.get("doi") or "").lower().strip()
    seed_doi = str(seed.get("paper_doi") or seed.get("work_doi") or seed.get("doi") or "").lower().strip()
    if item_doi and seed_doi and item_doi == seed_doi:
        return True
    title = " ".join(str(item.get("title") or "").lower().split())
    seed_title = " ".join(str(seed.get("paper_title") or seed.get("title") or "").lower().split())
    return bool(title and seed_title and (title in seed_title or seed_title in title))


def _link_evidence(item: dict[str, Any], value: str, locator: str) -> list[dict[str, Any]]:
    return [{
        "evidence_type": "literature_metadata_link",
        "source_field": locator,
        "value": value,
        "work_id": normalize_work_id(item),
        "retrieved_at": _now(),
        "confidence": "explicit" if locator in {"github_url", "repository_url", "code_url", "software_url"} else "related_identifier",
    }]


def _add_record(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
    identity = str(record.get("code_source_id") or "")
    existing = next((item for item in records if item.get("code_source_id") == identity), None)
    if existing is None:
        records.append(record)
        return
    for key in ("link_evidence", "limitations", "files"):
        merged = []
        for item in [*(existing.get(key) or []), *(record.get(key) or [])]:
            if item not in merged:
                merged.append(item)
        existing[key] = merged
    existing["quality_signals"] = {**existing.get("quality_signals", {}), **record.get("quality_signals", {})}


def _date_key(record: dict[str, Any]) -> str:
    return str(record.get("release_date") or "")


def select_versions(records: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode not in SELECTION_MODES:
        raise LiteratureCodeEnrichmentError(f"Unknown selection mode: {mode}")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("code_work_id") or record.get("code_source_id")), []).append(record)
    selected: list[dict[str, Any]] = []
    for group in grouped.values():
        stable = [item for item in group if item.get("latest_stable") is not False and not item.get("tombstone") and not item.get("restricted")]
        stable.sort(key=_date_key, reverse=True)
        if mode == "reproduction":
            paper_bound = [item for item in group if str(item.get("paper_alignment")) in {"exact", "paper_bound"}]
            chosen = paper_bound or []
            if not chosen:
                for item in group:
                    item["selection_status"] = "exact_version_unavailable"
        elif mode == "historical_reference":
            chosen = sorted(group, key=_date_key)[:1]
        else:
            chosen = stable[:1]
        for item in group:
            item["version_role"] = "latest_stable" if item in chosen and mode not in {"historical_reference", "reproduction"} else "paper_era" if str(item.get("paper_alignment")) in {"exact", "paper_bound"} else "historical"
            item["selected_for_execution"] = item in chosen and mode in {"knowledge_base", "plugin_candidate"}
            item["selection_mode"] = mode
            if item in chosen:
                item["selection_status"] = "selected_candidate"
                item["selection_reason"] = "latest stable version for knowledge-base use" if mode == "knowledge_base" else f"explicit {mode} policy"
            elif item.get("selection_status") != "exact_version_unavailable":
                item["selection_status"] = "lineage_only"
            selected.append(item)
    return selected


def _year_from_value(value: Any) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _exposure_years(record: dict[str, Any], signals: dict[str, Any], signal_name: str) -> float | None:
    observed_year = _year_from_value(signals.get("signals_retrieved_at") or _now())
    if observed_year is None:
        return None
    if signal_name in {"github_stars", "github_forks"}:
        start = signals.get("github_created_at") or record.get("created_at") or record.get("repository_created_at")
    elif signal_name == "paper_citation_count":
        start = signals.get("paper_publication_date") or signals.get("paper_publication_year") or record.get("paper_year")
    else:
        start = signals.get("software_publication_date") or signals.get("software_publication_year") or record.get("release_date")
    start_year = _year_from_value(start)
    if start_year is None or start_year > observed_year:
        return None
    return float(max(1, observed_year - start_year + 1))


def _log_normalize(value: Any, maximum: float, cohort: str, *, exposure_years: float | None = None) -> dict[str, Any]:
    if value is None or value == "":
        return {
            "value": None,
            "normalized_value": None,
            "normalization_cohort": cohort,
            "exposure_years": exposure_years,
            "normalization_method": "log_rate_per_year" if exposure_years else "log_count",
            "confidence": "unknown",
        }
    try:
        number = max(0.0, float(value))
    except (TypeError, ValueError):
        return {
            "value": None,
            "normalized_value": None,
            "normalization_cohort": cohort,
            "exposure_years": exposure_years,
            "normalization_method": "log_rate_per_year" if exposure_years else "log_count",
            "confidence": "invalid",
        }
    denominator_input = number / exposure_years if exposure_years and exposure_years > 0 else number
    denominator = math.log1p(max(1.0, maximum))
    return {
        "value": number,
        "normalized_value": round(math.log1p(denominator_input) / denominator, 6),
        "normalization_input": round(denominator_input, 6),
        "normalization_cohort": cohort,
        "exposure_years": exposure_years,
        "normalization_method": "log_rate_per_year" if exposure_years else "log_count",
        "confidence": "observed_age_adjusted" if exposure_years else "observed_unadjusted",
    }


def score_code_source(record: dict[str, Any], *, cohort: str = "project_candidates") -> dict[str, Any]:
    signals = dict(record.get("quality_signals") or {})
    stars = signals.get("github_stars")
    forks = signals.get("github_forks")
    paper_citations = signals.get("paper_citation_count")
    software_citations = signals.get("software_citation_count")
    signal_cohort = f"{cohort}:{signals.get('discipline') or 'unknown-discipline'}"
    stars_norm = _log_normalize(stars, 10000, signal_cohort, exposure_years=_exposure_years(record, signals, "github_stars"))
    forks_norm = _log_normalize(forks, 1000, signal_cohort, exposure_years=_exposure_years(record, signals, "github_forks"))
    paper_norm = _log_normalize(paper_citations, 10000, signal_cohort, exposure_years=_exposure_years(record, signals, "paper_citation_count"))
    software_norm = _log_normalize(software_citations, 1000, signal_cohort, exposure_years=_exposure_years(record, signals, "software_citation_count"))
    task_fit = signals.get("task_fit_score")
    if task_fit is None:
        task_fit = 0.7 if record.get("link_evidence") else 0.35
    reproducibility = 0.0
    reproducibility += 0.25 if record.get("version") or record.get("commit_sha") else 0
    reproducibility += 0.25 if record.get("doi") or record.get("release_date") else 0
    reproducibility += 0.25 if record.get("has_readme") or record.get("archive_available") else 0
    reproducibility += 0.25 if record.get("has_tests") or record.get("files") else 0
    maintenance = 0.7 if record.get("latest_stable") else 0.35
    scientific_parts = [item["normalized_value"] for item in (paper_norm, software_norm) if item["normalized_value"] is not None]
    adoption_parts = [item["normalized_value"] for item in (stars_norm, forks_norm) if item["normalized_value"] is not None]
    scientific = sum(scientific_parts) / len(scientific_parts) if scientific_parts else None
    adoption = sum(adoption_parts) / len(adoption_parts) if adoption_parts else None
    overall_parts = [
        (float(task_fit), 0.30),
        (scientific if scientific is not None else 0.0, 0.25),
        (adoption if adoption is not None else 0.0, 0.20),
        (reproducibility, 0.15),
        (maintenance, 0.10),
    ]
    risk_gate = "blocked" if record.get("tombstone") or record.get("restricted") else "review_required" if not record.get("license") else "open"
    record["quality_scores"] = {
        "task_fit_score": round(min(1.0, max(0.0, float(task_fit))), 6),
        "scientific_foundation_score": None if scientific is None else round(scientific, 6),
        "community_adoption_score": None if adoption is None else round(adoption, 6),
        "reproducibility_score": round(reproducibility, 6),
        "maintenance_score": maintenance,
        "overall_score": round(sum(value * weight for value, weight in overall_parts), 6),
        "risk_gate": risk_gate,
    }
    record["quality_signal_audit"] = {
        "github_stars": stars_norm,
        "github_forks": forks_norm,
        "paper_citations": paper_norm,
        "software_citations": software_norm,
        "provider": signals.get("signals_provider"),
        "retrieved_at": signals.get("signals_retrieved_at"),
    }
    return record


def _render_index(records: list[dict[str, Any]], provenance: dict[str, Any]) -> str:
    rows = []
    for record in records:
        scores = record.get("quality_scores") or {}
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(record.get('source_type') or ''))}</td>"
            f"<td>{html.escape(str(record.get('work_id') or ''))}</td>"
            f"<td><a href=\"{html.escape(str(record.get('canonical_url') or '#'))}\">{html.escape(str(record.get('full_name') or record.get('version') or record.get('record_id') or 'source'))}</a></td>"
            f"<td>{html.escape(str(record.get('version_role') or ''))}</td>"
            f"<td>{html.escape(str(record.get('selection_mode') or ''))}</td>"
            f"<td>{html.escape(str(record.get('license') or 'unknown'))}</td>"
            f"<td>{html.escape(str(record.get('verification_status') or 'metadata_only'))}</td>"
            f"<td>{html.escape(str(scores.get('overall_score') if scores else 'unknown'))}</td>"
            "</tr>"
        )
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>科研代码来源</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.4rem;text-align:left}}th{{background:#f3f3f3}}.note{{background:#fff7df;padding:1rem}}</style>
<h1>科研代码来源与 Zenodo 归档线索</h1>
<p class="note">本页默认只记录 metadata-only 候选。已发现、已归档、已下载、已验证和已晋升是不同状态；热度或被引量不代表科学正确性。</p>
<p>生成时间：{generated}</p><p>Provider receipts：{receipt_count}</p>
<table><thead><tr><th>来源</th><th>论文 work_id</th><th>代码来源</th><th>版本角色</th><th>选择模式</th><th>许可证</th><th>验证状态</th><th>候选评分</th></tr></thead><tbody>{rows}</tbody></table>
</html>""".format(generated=html.escape(_now()), receipt_count=len(provenance.get("provider_receipts") or []), rows="".join(rows))


def _render_quality(records: list[dict[str, Any]]) -> str:
    lines = ["<h1>科研代码来源质量审计</h1>", "<p>stars/forks、论文被引量和软件引用量是分离的采用度/影响度信号，不是科学有效性证明。</p>", "<ul>"]
    for record in records:
        scores = record.get("quality_scores") or {}
        lines.append(f"<li><strong>{html.escape(str(record.get('code_source_id')))}</strong>：{html.escape(json.dumps(scores, ensure_ascii=False))}</li>")
    lines.append("</ul>")
    return "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">" + "".join(lines) + "</html>"


def _write_outputs(root: Path, records: list[dict[str, Any]], provenance: dict[str, Any]) -> dict[str, Any]:
    references = root / "references"
    references.mkdir(parents=True, exist_ok=True)
    selected = [item for item in records if item.get("selection_status") == "selected_candidate"]
    candidates = {
        "schema_version": "dpl.research_code_leads.v1",
        "status": "written",
        "generated_at": _now(),
        "candidate_count": len(selected),
        "candidates": selected,
    }
    _write_json(root / CODE_SOURCES_JSON, {"schema_version": "dpl.code_sources.v2", "generated_at": _now(), "records": records})
    _write_json(root / CODE_PROVENANCE_JSON, provenance)
    _write_json(root / CODE_CANDIDATES_JSON, candidates)
    write_html_report(root / CODE_INDEX_HTML, _render_index(records, provenance), title="科研代码来源")
    write_html_report(root / CODE_QUALITY_HTML, _render_quality(records), title="科研代码来源质量审计")
    literature_items_path = root / "references" / "literature_items.json"
    if literature_items_path.is_file():
        from .references import write_literature_html_summaries

        write_literature_html_summaries(root / "references", _items(literature_items_path))
    return {
        "code_sources": CODE_SOURCES_JSON,
        "code_source_provenance": CODE_PROVENANCE_JSON,
        "code_source_candidates": CODE_CANDIDATES_JSON,
        "code_source_index": CODE_INDEX_HTML,
        "code_source_quality": CODE_QUALITY_HTML,
    }


def enrich_literature_code_leads(
    project: str | Path,
    *,
    work_selection: str = "retained,anchor,user_selected",
    providers: tuple[str, ...] = ("github", "zenodo"),
    selection_mode: str = "knowledge_base",
    metadata_only: bool = True,
    github_metadata: str | Path | None = None,
    zenodo_metadata: str | Path | None = None,
    include_online: bool = False,
    max_candidates: int = 30,
) -> dict[str, Any]:
    if selection_mode not in SELECTION_MODES:
        raise LiteratureCodeEnrichmentError(f"selection_mode must be one of {sorted(SELECTION_MODES)}")
    if not metadata_only:
        raise LiteratureCodeEnrichmentError("Literature enrichment is metadata-only; use the guarded archive command for downloads.")
    providers = _provider_tuple(providers)
    state = load_project(project)
    items = [item for item in _items(state.path / "references" / "literature_items.json") if _selected(item, {part.strip() for part in work_selection.split(",") if part.strip()})]
    github_seeds = _load_provider_seed(github_metadata)
    zenodo_seeds = _load_provider_seed(zenodo_metadata)
    records: list[dict[str, Any]] = []
    provider_receipts: list[dict[str, Any]] = []
    for item in items:
        work_id = normalize_work_id(item)
        for value, locator in _candidate_strings(item):
            provider = _provider_from_url(value)
            if provider not in providers:
                continue
            evidence = _link_evidence(item, value, locator)
            if provider == "github":
                raw = next((seed for seed in github_seeds if _matches_seed(seed, item, work_id) or canonical_url(seed.get("html_url")) == canonical_url(value)), {"html_url": value})
                _add_record(records, github_record_from_metadata(raw, work_id=work_id, source_intent=selection_mode, link_evidence=evidence))
            elif provider == "zenodo":
                raw = next((seed for seed in zenodo_seeds if _matches_seed(seed, item, work_id) or str(seed.get("doi") or "").lower() == value.lower() or canonical_url(seed.get("links", {}).get("html") if isinstance(seed.get("links"), dict) else seed.get("url")) == canonical_url(value)), {"links": {"html": value}, "doi": value if value.lower().startswith("10.5281/zenodo.") else None})
                _add_record(records, zenodo_record_from_metadata(raw, work_id=work_id, source_intent=selection_mode, link_evidence=evidence))
        for provider, seeds in (("github", github_seeds), ("zenodo", zenodo_seeds)):
            if provider not in providers:
                continue
            for seed in seeds:
                if not _matches_seed(seed, item, work_id):
                    continue
                evidence = [{"evidence_type": "provider_search_seed", "provider": provider, "work_id": work_id, "retrieved_at": _now()}]
                record = github_record_from_metadata(seed, work_id=work_id, source_intent=selection_mode, link_evidence=evidence) if provider == "github" else zenodo_record_from_metadata(seed, work_id=work_id, source_intent=selection_mode, link_evidence=evidence)
                _add_record(records, record)
        if include_online:
            query = " ".join(str(item.get(key) or "") for key in ("title", "doi", "authors")).strip()[:220]
            for provider in providers:
                result = search_github(query, work_id=work_id, limit=3, source_intent=selection_mode) if provider == "github" else search_zenodo(query, work_id=work_id, limit=3, source_intent=selection_mode)
                provider_receipts.append(result)
                for record in result.get("records") or []:
                    _add_record(records, record)
    records = select_versions(records[:max_candidates], selection_mode)
    work_lookup = {normalize_work_id(item): item for item in items}
    for record in records:
        work_item = work_lookup.get(str(record.get("work_id")), {})
        signals = dict(record.get("quality_signals") or {})
        signals.setdefault("paper_citation_count", work_item.get("citation_count") or work_item.get("citationCount"))
        signals.setdefault("software_citation_count", work_item.get("software_citation_count"))
        record["quality_signals"] = signals
        score_code_source(record)
    provenance = {
        "schema_version": "dpl.code_source_provenance.v1",
        "generated_at": _now(),
        "metadata_only": True,
        "work_count": len(items),
        "work_ids": [normalize_work_id(item) for item in items],
        "providers": list(providers),
        "provider_receipts": provider_receipts or [{"provider": provider, "status": "offline_or_no_seed", "metadata_only": True} for provider in providers],
        "selection_mode": selection_mode,
        "downloaded": False,
        "executed": False,
    }
    outputs = _write_outputs(state.path, records, provenance)
    return {
        "status": "written",
        "project_path": str(state.path),
        "work_count": len(items),
        "record_count": len(records),
        "candidate_count": sum(1 for item in records if item.get("selection_status") == "selected_candidate"),
        "metadata_only": True,
        **outputs,
    }


def inspect_research_code_source(project: str | Path, candidate_id: str) -> dict[str, Any]:
    state = load_project(project)
    payload = _read_json(state.path / CODE_SOURCES_JSON, {})
    records = payload.get("records") or []
    record = next((item for item in records if isinstance(item, dict) and item.get("code_source_id") == candidate_id), None)
    if record is None:
        raise LiteratureCodeEnrichmentError(f"Unknown code source candidate: {candidate_id}")
    output = state.path / "references" / "code_source_inspections" / f"{_safe_filename(candidate_id)}.json"
    inspection = {
        "schema_version": "dpl.code_source_inspection.v1",
        "status": "metadata_only",
        "generated_at": _now(),
        "candidate_id": candidate_id,
        "record": record,
        "download_required_for_archive_inspection": True,
        "execution_allowed": False,
    }
    _write_json(output, inspection)
    return {"status": "written", "inspection": str(output.relative_to(state.path)).replace("\\", "/"), "candidate_id": candidate_id, "execution_allowed": False}


def fetch_research_code_archive(project: str | Path, candidate_id: str, *, confirm_download: bool = False) -> dict[str, Any]:
    state = load_project(project)
    path = state.path / CODE_SOURCES_JSON
    payload = _read_json(path, {})
    records = payload.get("records") or []
    record = next((item for item in records if isinstance(item, dict) and item.get("code_source_id") == candidate_id), None)
    if record is None:
        raise LiteratureCodeEnrichmentError(f"Unknown code source candidate: {candidate_id}")
    if record.get("source_intent") == "citation_only":
        return {"status": "blocked", "reason": "citation_only_source_intent", "candidate_id": candidate_id}
    archive_url = record.get("archive_url")
    if not archive_url:
        return {"status": "blocked", "reason": "archive_url_missing", "candidate_id": candidate_id}
    expected = None
    for file_item in record.get("files") or []:
        if isinstance(file_item, dict) and file_item.get("checksum"):
            expected = str(file_item["checksum"])
            break
    digest_hint = str(record.get("code_source_id") or "candidate")[-32:]
    archive_path = state.path / "research_code_mining" / "archive_cache" / digest_hint / "archive.bin"
    download = safe_download_archive(archive_url, archive_path, expected_sha256=expected, confirm_download=confirm_download)
    inspection = inspect_archive(archive_path, expected_sha256=expected) if download.get("downloaded") else {"status": "not_run", "reason": download.get("reason")}
    license_audit = audit_archive_license(archive_path, record.get("license")) if download.get("downloaded") else {"status": "not_run"}
    receipt = {
        "schema_version": "dpl.code_source_archive_receipt.v1",
        "generated_at": _now(),
        "candidate_id": candidate_id,
        "download": download,
        "inspection": inspection,
        "license_audit": license_audit,
        "execution_status": "not_run",
        "promotion_status": "candidate" if inspection.get("status") != "passed" or license_audit.get("status") != "consistent" else "pending_fixture_verification",
    }
    receipt_path = state.path / "research_code_mining" / "archive_cache" / digest_hint / "download_receipt.json"
    _write_json(receipt_path, receipt)
    record["download_status"] = "downloaded" if download.get("downloaded") else str(download.get("reason") or "blocked")
    record["verification_status"] = "archive_inspected" if inspection.get("status") == "passed" else "metadata_only"
    record["execution_status"] = "not_run"
    record["archive_inspection"] = inspection
    record["license_audit"] = license_audit
    record["promotion_status"] = receipt["promotion_status"]
    _write_json(path, payload)
    return {"status": "downloaded" if download.get("downloaded") else "blocked", "candidate_id": candidate_id, "receipt": str(receipt_path.relative_to(state.path)).replace("\\", "/"), "execution_status": "not_run"}


def discover_research_code(
    *,
    output_root: str | Path,
    discipline: str,
    query: str,
    providers: tuple[str, ...] = ("github", "zenodo"),
    paper_doi: str | None = None,
    selection_mode: str = "knowledge_base",
    github_metadata: str | Path | None = None,
    zenodo_metadata: str | Path | None = None,
) -> dict[str, Any]:
    if not query.strip():
        raise LiteratureCodeEnrichmentError("query is required")
    providers = _provider_tuple(providers)
    work = {"doi": paper_doi or "", "title": query, "authors": [], "year": ""}
    work_id = normalize_work_id(work)
    records: list[dict[str, Any]] = []
    for provider, path in (("github", github_metadata), ("zenodo", zenodo_metadata)):
        if provider not in providers:
            continue
        for seed in _load_provider_seed(path):
            record = github_record_from_metadata(seed, work_id=work_id, source_intent=selection_mode, link_evidence=[{"evidence_type": "explicit_discovery_query", "query": query, "discipline": discipline}]) if provider == "github" else zenodo_record_from_metadata(seed, work_id=work_id, source_intent=selection_mode, link_evidence=[{"evidence_type": "explicit_discovery_query", "query": query, "discipline": discipline}])
            _add_record(records, record)
    selected = select_versions(records, selection_mode)
    for record in selected:
        score_code_source(record)
    root = Path(output_root).expanduser().resolve() / "research_code_mining"
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"{re.sub(r'[^a-zA-Z0-9_-]+', '_', discipline)}_code_sources.json"
    report = {"status": "written", "generated_at": _now(), "discipline": discipline, "query": query, "work_id": work_id, "metadata_only": True, "records": selected}
    _write_json(output, report)
    write_html_report(output.with_suffix(".html"), _render_index(selected, {"provider_receipts": []}), title="科研代码发现")
    return {"status": "written", "output_file": str(output), "html_report": str(output.with_suffix(".html")), "record_count": len(selected), "metadata_only": True}
