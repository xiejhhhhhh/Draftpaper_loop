"""Parser router with pypdf baseline and optional MinerU connectors.

MinerU is never a core dependency.  The router records the actual parser,
route, quality decision and evidence binding; bibliography extraction never
becomes an automatic citation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .document_context_budget import ensure_context_policy, load_context_policy, select_with_budget
from .document_identity import resolve_work_identity
from .document_normalization import load_mineru_markdown_or_json, normalize_pypdf
from .document_parse_binding import bind_document_parse
from .document_parse_quality import assess_extraction_quality, extract_pypdf_pages
from .evidence_passages import select_evidence_passages
from .project_scaffold import _write_json
from .project_state import load_project
from .references import _extract_pdf_text_from_path
from .remote_document_policy import check_remote_parse_eligibility
from .remote_parser_consent import consent_for_route


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_mineru_output(root: Path) -> Path | None:
    for name in ("content_list_v2.json", "content_list.json", "full.md", "content.md"):
        matches = sorted(root.rglob(name))
        if matches:
            return matches[0]
    return None


def _local_mineru_parse(source: Path, output_root: Path, timeout_seconds: int) -> tuple[Path | None, dict[str, Any]]:
    executable = os.getenv("MINERU_EXECUTABLE", "mineru").strip() or "mineru"
    if not shutil.which(executable):
        return None, {"status": "unavailable", "error_type": "executable_missing"}
    try:
        completed = subprocess.run(
            [executable, "-p", str(source), "-o", str(output_root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
        )
    except subprocess.TimeoutExpired:
        return None, {"status": "failed", "error_type": "timeout"}
    except OSError as exc:
        return None, {"status": "failed", "error_type": type(exc).__name__}
    parsed = _find_mineru_output(output_root)
    if completed.returncode == 0 and parsed:
        return parsed, {"status": "parsed", "return_code": 0, "route": "local"}
    return None, {"status": "failed", "return_code": completed.returncode, "error_type": "missing_expected_output"}


def _write_parse_receipt(output_root: Path, receipt: dict[str, Any]) -> Path:
    path = output_root / "parse_receipt.json"
    _write_json(path, receipt)
    return path


def _request_fingerprint(
    input_hash: str,
    *,
    parser: str,
    route: str,
    purpose: str,
    endpoint: str = "",
    document_class: str = "unknown",
) -> str:
    payload = {
        "input_sha256": input_hash,
        "parser": parser,
        "route": route,
        "purpose": purpose,
        "endpoint": endpoint,
        "document_class": document_class,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _cached_parse(
    state_path: Path,
    output_root: Path,
    *,
    fingerprint: str,
) -> dict[str, Any] | None:
    receipt_path = output_root / "parse_receipt.json"
    normalized_path = output_root / "normalized_document.json"
    if not receipt_path.is_file() or not normalized_path.is_file():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(receipt, dict) or receipt.get("request_fingerprint") != fingerprint or receipt.get("status") != "parsed":
        return None
    output = receipt.get("output")
    if output:
        output_path = (state_path / str(output)).resolve()
        if state_path not in output_path.parents and output_path != state_path:
            return None
        if not output_path.is_file():
            return None
    receipt = {**receipt, "cache_hit": True}
    try:
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    passage_path = output_root / "evidence_passages.jsonl"
    passages: list[dict[str, Any]] = []
    if passage_path.is_file():
        for line in passage_path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                passages.append(value)
    return {
        "status": "cached",
        "receipt": receipt,
        "receipt_path": receipt_path.relative_to(state_path).as_posix(),
        "normalized_path": normalized_path.relative_to(state_path).as_posix(),
        "normalized": normalized,
        "passages": passages,
        "binding": {"status": "cached", "work_id": receipt.get("work_id"), "normalized_output": normalized_path.relative_to(state_path).as_posix(), "passage_count": receipt.get("evidence_passage_count", 0)},
        "citation_policy": "bibliography_candidates_require_identity_and_metadata_audit",
    }


def _append_project_record(path: Path, record: dict[str, Any], *, key: str = "records") -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    raw_values = payload.get(key)
    values: list[Any] = raw_values if isinstance(raw_values, list) else []
    marker = str(record.get("document_id") or record.get("input_sha256") or "")
    values = [value for value in values if not isinstance(value, dict) or str(value.get("document_id") or value.get("input_sha256") or "") != marker]
    values.append(record)
    payload["schema_version"] = payload.get("schema_version") or "dpl.document_parse_cost_report.v1"
    payload[key] = values
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(path, payload)


def _refresh_literature_index(project: Path) -> None:
    items_path = project / "references" / "literature_items.json"
    if not items_path.is_file():
        return
    try:
        payload = json.loads(items_path.read_text(encoding="utf-8"))
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        if isinstance(items, list):
            from .references import write_literature_html_summaries

            write_literature_html_summaries(project / "references", items)
    except (OSError, json.JSONDecodeError):
        return


def parse_literature_document(
    project: str | Path,
    input_path: str | Path,
    *,
    use_mineru: bool = True,
    timeout_seconds: int = 600,
    parser: str = "auto",
    mineru_route: str = "auto",
    purpose: str = "evidence",
    work_id: str | None = None,
    remote_consent: str = "ask_once",
    document_class: str = "unknown",
    custom_endpoint: str | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("parse-literature-document requires an existing PDF file.")
    input_hash = _sha256(source)
    doc_id = f"sha256:{input_hash}"
    output_root = state.path / "references" / "document_parses" / input_hash[:16]
    output_root.mkdir(parents=True, exist_ok=True)
    ensure_context_policy(state.path)
    pages = extract_pypdf_pages(source)
    quick_text = _extract_pdf_text_from_path(str(source), max_pages=8, max_chars=16000)
    if not pages and quick_text:
        pages = [{"page": 1, "text": quick_text, "char_count": len(quick_text)}]
    quality = assess_extraction_quality(pages, purpose=purpose)
    identity = resolve_work_identity(state.path, quick_text or "\n".join(str(page.get("text") or "") for page in pages), input_document_id=doc_id, explicit_work_id=work_id)
    receipt: dict[str, Any] = {
        "schema_version": "dpl.document_parse_receipt.v2",
        "input_sha256": input_hash,
        "input_name": source.name,
        "source_locator": "external_local_file",
        "document_id": doc_id,
        "work_id": identity["work_id"],
        "identity_status": identity["status"],
        "identity_confidence": identity["confidence"],
        "identity_reason": identity["reason"],
        "status": "metadata_only",
        "parser": "none",
        "parser_version": "",
        "route": "pypdf",
        "purpose": purpose,
        "quality": quality,
        "bibliography_auto_citation": False,
        "remote_upload": False,
    }
    normalized: dict[str, Any]
    route_report: dict[str, Any] = {"status": "not_attempted", "reason_codes": []}
    parsed_output: Path | None = None
    selected_parser = parser.lower().strip() or "auto"
    route = mineru_route.lower().strip() or "auto"
    if not use_mineru:
        selected_parser = "pypdf"
    should_upgrade = selected_parser == "mineru" or selected_parser == "auto" and quality.get("status") != "passed"
    effective_route = "pypdf"
    if should_upgrade and selected_parser != "pypdf":
        effective_route = route
        if effective_route == "auto":
            if custom_endpoint or os.getenv("DRAFTPAPER_MINERU_ENDPOINT", "").strip():
                effective_route = "custom-endpoint"
            elif os.getenv("MINERU_EXECUTABLE", "").strip() and shutil.which(os.getenv("MINERU_EXECUTABLE", "").strip()):
                effective_route = "local"
            else:
                effective_route = "official-agent"
    endpoint_for_fingerprint = custom_endpoint or os.getenv("DRAFTPAPER_MINERU_ENDPOINT", "").strip() if effective_route == "custom-endpoint" else os.getenv("MINERU_AGENT_ENDPOINT", "") if effective_route == "official-agent" else ""
    request_fingerprint = _request_fingerprint(
        input_hash,
        parser="mineru" if should_upgrade and selected_parser != "pypdf" else "pypdf",
        route=effective_route,
        purpose=purpose,
        endpoint=endpoint_for_fingerprint,
        document_class=document_class,
    )
    if should_upgrade and selected_parser != "pypdf":
        cached = _cached_parse(state.path, output_root, fingerprint=request_fingerprint)
        if cached is not None:
            cached["binding"] = bind_document_parse(
                state.path,
                receipt=cached["receipt"],
                normalized=cached["normalized"],
                passages=cached["passages"],
            )
            _refresh_literature_index(state.path)
            cached.pop("normalized", None)
            cached.pop("passages", None)
            return cached
    if should_upgrade and selected_parser != "pypdf":
        if effective_route == "local":
            parsed_output, route_report = _local_mineru_parse(source, output_root, timeout_seconds)
        elif effective_route == "custom-endpoint":
            from .mineru_endpoint_client import parse_with_custom_endpoint

            endpoint = custom_endpoint or os.getenv("DRAFTPAPER_MINERU_ENDPOINT", "").strip()
            consent = consent_for_route(state.path, route="custom-endpoint", requested=remote_consent)
            eligibility = check_remote_parse_eligibility(
                source,
                page_count=len(pages),
                document_class=document_class,
                consent=consent.get("decision", "ask_once"),
                allowed_document_classes=set(consent.get("document_classes") or []),
                max_mb=200,
                max_pages=600,
                require_known_page_count=False,
            )
            eligibility["consent_source"] = consent.get("source")
            route_report = {"status": "skipped", "reason_codes": eligibility["reason_codes"], "eligibility": eligibility}
            if endpoint and eligibility["eligible"]:
                try:
                    remote = parse_with_custom_endpoint(source, endpoint=endpoint, timeout_seconds=timeout_seconds)
                    if remote.get("markdown"):
                        (output_root / "custom_endpoint.md").write_text(str(remote["markdown"]), encoding="utf-8")
                        parsed_output = output_root / "custom_endpoint.md"
                        route_report = {**remote, "status": "parsed", "eligibility": eligibility}
                except Exception as exc:
                    route_report = {"status": "failed", "error_type": type(exc).__name__, "eligibility": eligibility}
        elif effective_route == "official-agent":
            consent = consent_for_route(state.path, route="official-agent", requested=remote_consent)
            eligibility = check_remote_parse_eligibility(
                source,
                page_count=len(pages),
                document_class=document_class,
                consent=consent.get("decision", "ask_once"),
                allowed_document_classes=set(consent.get("document_classes") or []),
            )
            eligibility["consent_source"] = consent.get("source")
            route_report = {"status": "skipped", "reason_codes": eligibility["reason_codes"], "eligibility": eligibility}
            if eligibility["eligible"]:
                from .mineru_agent_client import DEFAULT_ENDPOINT, installation_device_id, parse_with_official_agent

                device_id = installation_device_id(state.path / "references" / "private" / "remote_device.json")
                try:
                    remote = parse_with_official_agent(source, endpoint=os.getenv("MINERU_AGENT_ENDPOINT", DEFAULT_ENDPOINT), device_id=device_id, timeout_seconds=timeout_seconds)
                    route_report = {**remote, "eligibility": eligibility}
                    if remote.get("markdown"):
                        (output_root / "official_agent.md").write_text(str(remote["markdown"]), encoding="utf-8")
                        parsed_output = output_root / "official_agent.md"
                except Exception as exc:
                    route_report = {"status": "failed", "error_type": type(exc).__name__, "eligibility": eligibility}
        receipt["route"] = effective_route
    if parsed_output is None and should_upgrade and selected_parser != "pypdf" and route == "auto" and os.getenv("MINERU_EXECUTABLE"):
        parsed_output, route_report = _local_mineru_parse(source, output_root, timeout_seconds)
        receipt["route"] = "local"
    if parsed_output is not None and parsed_output.is_file():
        raw_path = output_root / f"raw_{parsed_output.name}"
        if parsed_output.resolve() != raw_path.resolve():
            shutil.copy2(parsed_output, raw_path)
        normalized = load_mineru_markdown_or_json(raw_path, document_id=doc_id, work_id=identity["work_id"], parser_version=str(route_report.get("parser_version") or ""), mode=str(route_report.get("route") or receipt.get("route") or "mineru"))
        receipt.update({"status": "parsed", "parser": "mineru", "parser_version": str(route_report.get("parser_version") or ""), "output": raw_path.relative_to(state.path).as_posix(), "route_report": route_report, "remote_upload": receipt.get("route") in {"official-agent", "custom-endpoint"}, "remote_attempted": receipt.get("route") in {"official-agent", "custom-endpoint"}, "request_fingerprint": request_fingerprint})
    else:
        fallback_path = output_root / "pypdf_excerpt.txt"
        fallback_path.write_text(quick_text or "", encoding="utf-8")
        normalized = normalize_pypdf(source, pages, document_id=doc_id, work_id=identity["work_id"], quality=quality)
        receipt.update({"status": "fallback" if should_upgrade else "parsed", "parser": "pypdf", "output": fallback_path.relative_to(state.path).as_posix(), "text_chars": len(quick_text or ""), "route_report": route_report, "upgrade_recommended": bool(should_upgrade and not parsed_output), "request_fingerprint": request_fingerprint, "remote_attempted": receipt.get("route") in {"official-agent", "custom-endpoint"}, "remote_upload": bool(receipt.get("route") in {"official-agent", "custom-endpoint"} and route_report.get("status") in {"parsed", "submitted"})})
    anchors = []
    contract_path = state.path / "references" / "query_contract.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.is_file() else {}
        anchors = [str(value) for value in contract.get("must_preserve_terms") or []]
    except (OSError, json.JSONDecodeError):
        contract = {}
    policy = load_context_policy(state.path)
    passages = select_evidence_passages(
        normalized,
        anchors=anchors,
        max_passages=int(policy.get("max_candidate_passages_per_work") or 12),
        max_chars=int(policy.get("max_chars_per_passage") or 1800),
    )
    selected_passages, context_manifest = select_with_budget(
        passages,
        max_passages=int(policy.get("max_context_passages_per_work") or 6),
        max_chars=int(policy.get("max_total_chars_per_work") or 9000),
        max_chars_per_passage=int(policy.get("max_chars_per_passage") or 1800),
        include_sections={str(value) for value in policy.get("include_sections") or []},
        exclude_sections={str(value) for value in policy.get("exclude_sections") or ["references"]},
    )
    context_manifest.update({"document_id": doc_id, "work_id": identity["work_id"], "parser": receipt["parser"], "route": receipt["route"]})
    receipt["evidence_passage_count"] = len(selected_passages)
    receipt["context_manifest"] = context_manifest
    receipt_path = _write_parse_receipt(output_root, receipt)
    _write_json(output_root / "extraction_quality.json", quality)
    _write_json(output_root / "document_context_manifest.json", context_manifest)
    binding = bind_document_parse(state.path, receipt=receipt, normalized=normalized, passages=selected_passages)
    cost_record = {
        "document_id": doc_id,
        "input_sha256": input_hash,
        "parser": receipt["parser"],
        "route": receipt["route"],
        "remote_upload": receipt["remote_upload"],
        "remote_attempted": receipt.get("remote_attempted", False),
        "estimated_input_tokens": context_manifest.get("estimated_input_tokens", 0),
        "selected_passage_count": context_manifest.get("selected_passage_count", 0),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_project_record(state.path / "references" / "document_parse_cost_report.json", {
        "schema_version": "dpl.document_parse_cost_report.v1",
        **cost_record,
        "policy": "parser_cost_is_local_resource_or_provider_quota;_llm_tokens_only_count_downstream_context",
    })
    _refresh_literature_index(state.path)
    return {
        "status": receipt["status"],
        "project_path": str(state.path),
        "receipt": receipt,
        "receipt_path": receipt_path.relative_to(state.path).as_posix(),
        "binding": binding,
        "citation_policy": "bibliography_candidates_require_identity_and_metadata_audit",
    }
