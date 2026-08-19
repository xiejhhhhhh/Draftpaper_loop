# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from ._vendor.paper_fetch_skill.provenance import PAPER_FETCH_VERSION, UPSTREAM_COMMIT
from .literature_discipline_policy import ontology_snapshot
from .literature_fetch_policy import load_literature_fetch_policy
from .literature_identity import canonical_work_id
from .literature_relevance import apply_relevance_gate
from .paper_identity_resolution import IdentityResolver, resolve_literature_identities
from .postfetch_relevance import assess_postfetch_candidates
from .project_scaffold import _write_json, utc_now


Runner = Callable[..., dict[str, Any]]
TARGET_CONTEXTS = {"data", "methods"}
MIN_CONTEXT_ITEMS = 5


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _vendored_source() -> Path | None:
    packaged = Path(__file__).resolve().parent / "_vendor" / "paper_fetch_skill"
    if (packaged / "paper_fetch" / "cli.py").exists():
        return packaged
    source_tree = _repo_root() / "third_party" / "paper-fetch-skill" / "src"
    return source_tree if source_tree.exists() else None


def resolve_paper_fetch_command(command: list[str] | None = None) -> tuple[list[str] | None, dict[str, str], str]:
    env: dict[str, str] = {}
    if command:
        executable = command[0]
        if Path(executable).exists() or shutil.which(executable):
            return command, env, "explicit"
        return None, env, "explicit_missing"
    path_command = shutil.which("paper-fetch")
    if path_command:
        return [path_command], env, "path"
    source = _vendored_source()
    if source:
        env["PYTHONPATH"] = str(source)
        return [sys.executable, "-m", "paper_fetch.cli"], env, "vendored"
    return None, env, "missing"


def _default_runner(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _target_text(item: dict[str, Any]) -> str:
    return str(item.get("doi") or item.get("url") or item.get("title") or "").strip()


def _has_readable_text(item: dict[str, Any]) -> bool:
    return bool(str(item.get("abstract") or item.get("pdf_text_excerpt") or "").strip())


def _context_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {context: 0 for context in TARGET_CONTEXTS}
    for item in items:
        context = str(item.get("search_context") or "").lower()
        if context in counts and _has_readable_text(item):
            counts[context] += 1
    return counts


def _select_targets(items: list[dict[str, Any]], *, min_per_context: int) -> list[tuple[int, dict[str, Any]]]:
    counts = _context_counts(items)
    targets = []
    for index, item in enumerate(items):
        context = str(item.get("search_context") or "").lower()
        if context not in TARGET_CONTEXTS or counts[context] >= min_per_context or _has_readable_text(item):
            continue
        if not _target_text(item):
            continue
        targets.append((index, item))
        counts[context] += 1
    return targets


def _safe_stem(text: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return (stem[:48].strip("_") or fallback)


def _extract_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    article = payload.get("article") if isinstance(payload.get("article"), dict) else payload
    metadata = article.get("metadata") if isinstance(article.get("metadata"), dict) else {}
    return metadata if isinstance(metadata, dict) else {}


def _extract_markdown(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    markdown = payload.get("markdown")
    if isinstance(markdown, str):
        return markdown
    article = payload.get("article")
    if isinstance(article, dict):
        sections = article.get("sections")
        if isinstance(sections, list):
            parts = []
            for section in sections:
                if isinstance(section, dict):
                    parts.append(str(section.get("text") or section.get("content") or ""))
            return "\n\n".join(part for part in parts if part)
    return ""


def _apply_payload(item: dict[str, Any], payload_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return item
    metadata = _extract_metadata(payload)
    markdown = _extract_markdown(payload)
    abstract = str(metadata.get("abstract") or "").strip()
    enriched = dict(item)
    enriched["paper_fetch_resolved_metadata"] = {
        key: metadata.get(key)
        for key in ("doi", "title", "authors", "year", "journal", "publication", "landing_page_url")
        if metadata.get(key)
    }
    if metadata.get("title") and not enriched.get("title"):
        enriched["title"] = metadata.get("title")
    if metadata.get("doi") and not enriched.get("doi"):
        enriched["doi"] = metadata.get("doi")
    if metadata.get("year") and not enriched.get("year"):
        enriched["year"] = str(metadata.get("year"))
    if abstract:
        enriched["abstract"] = abstract
    elif markdown:
        enriched["abstract"] = re.sub(r"\s+", " ", markdown).strip()[:1200]
    if markdown:
        enriched["pdf_text_excerpt"] = re.sub(r"\s+", " ", markdown).strip()[:5000]
    enriched["paper_fetch_markdown_path"] = str(payload_path)
    enriched["paper_fetch_status"] = "enriched" if (abstract or markdown) else "metadata_only"
    return enriched


def _legacy_enrich_with_paper_fetch(
    project: str | Path,
    items: list[dict[str, Any]],
    *,
    min_per_context: int = MIN_CONTEXT_ITEMS,
    command: list[str] | None = None,
    runner: Runner | None = None,
    timeout: int = 90,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    project_path = Path(project)
    references_dir = project_path / "references"
    fulltext_dir = references_dir / "fulltext"
    references_dir.mkdir(parents=True, exist_ok=True)
    fulltext_dir.mkdir(parents=True, exist_ok=True)

    targets = _select_targets(items, min_per_context=min_per_context)
    query_file = references_dir / "paper_fetch_queries.txt"
    query_file.write_text("\n".join(_target_text(item) for _, item in targets) + ("\n" if targets else ""), encoding="utf-8")

    if runner is not None and command is None:
        base_command, extra_env, runtime_source = ["paper-fetch"], {}, "injected"
    else:
        base_command, extra_env, runtime_source = resolve_paper_fetch_command(command)
    manifest: dict[str, Any] = {
        "status": "skipped",
        "runtime_source": runtime_source,
        "runtime_version": PAPER_FETCH_VERSION,
        "runtime_upstream_commit": UPSTREAM_COMMIT,
        "started_at": utc_now(),
        "query_file": str(query_file),
        "output_dir": str(fulltext_dir),
        "attempted_count": len(targets),
        "success_count": 0,
        "failures": [],
        "outputs": [],
    }
    if not targets:
        manifest["finished_at"] = utc_now()
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return items, manifest
    if not base_command:
        manifest["status"] = "unavailable"
        manifest["finished_at"] = utc_now()
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return items, manifest

    run = runner or _default_runner
    enriched = list(items)
    for target_index, item in targets:
        target = _target_text(item)
        output_path = fulltext_dir / f"{target_index + 1:02d}_{_safe_stem(str(item.get('title') or target), 'paper')}.json"
        fetch_command = [
            *base_command,
            "--query",
            target,
            "--format",
            "both",
            "--output",
            str(output_path),
            "--output-dir",
            str(fulltext_dir),
            "--asset-profile",
            "none",
            "--artifact-mode",
            "markdown-assets",
            "--no-download",
        ]
        try:
            result = run(fetch_command, cwd=project_path, env=extra_env, timeout=timeout)
        except Exception as exc:
            manifest["failures"].append({"query": target, "error": str(exc)})
            continue
        if int(result.get("returncode") or 0) != 0:
            manifest["failures"].append({
                "query": target,
                "returncode": result.get("returncode"),
                "stderr": result.get("stderr", ""),
            })
            continue
        if not output_path.exists():
            manifest["failures"].append({"query": target, "error": "paper-fetch produced no output file"})
            continue
        enriched[target_index] = _apply_payload(item, output_path)
        if _has_readable_text(enriched[target_index]):
            manifest["success_count"] += 1
            manifest["outputs"].append(str(output_path))
    manifest["status"] = "completed" if manifest["success_count"] else "failed"
    manifest["finished_at"] = utc_now()
    _write_json(references_dir / "paper_fetch_manifest.json", manifest)
    return enriched, manifest


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_prefetch_outputs(
    references_dir: Path,
    shortlist: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    candidate_set_hash = _canonical_hash([*shortlist, *rejected])
    report = {
        "schema_version": "dpl.prefetch_relevance_assessment.v1",
        "status": "completed",
        "candidate_count": len(shortlist) + len(rejected),
        "shortlist_count": len(shortlist),
        "rejected_count": len(rejected),
        "accepted_count": sum(item.get("gate_state") == "accepted" for item in shortlist),
        "review_required_count": sum(item.get("gate_state") == "review_required" for item in shortlist),
        "candidate_set_hash": candidate_set_hash,
        "query_contract_hash": _canonical_hash(contract),
        "generated_at": utc_now(),
        "shortlist": [
            {
                "title": item.get("title"),
                "doi": item.get("doi"),
                "candidate_state": item.get("candidate_state"),
                "gate_state": item.get("gate_state"),
                "topic_relevance_score": item.get("topic_relevance_score"),
                "discipline_match_score": item.get("discipline_match_score"),
                "review_codes": item.get("review_codes") or [],
            }
            for item in shortlist
        ],
        "rejections": [
            {
                "title": item.get("title"),
                "doi": item.get("doi"),
                "rejection_codes": item.get("rejection_codes") or [],
                "topic_relevance_score": item.get("topic_relevance_score"),
                "discipline_match_score": item.get("discipline_match_score"),
            }
            for item in rejected
        ],
    }
    _write_json(references_dir / "prefetch_relevance_report.json", report)
    (references_dir / "prefetch_literature_candidates.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in shortlist) + ("\n" if shortlist else ""),
        encoding="utf-8",
    )
    ontology = ontology_snapshot()
    ontology["ontology_hash"] = _canonical_hash(ontology)
    ontology["generated_at"] = utc_now()
    _write_json(references_dir / "discipline_ontology_snapshot.json", ontology)
    _write_json(
        references_dir / "discipline_conflict_matrix.json",
        {
            "schema_version": "dpl.discipline_conflict_matrix.v1",
            "policy": "symmetric_parent_overlap_or_explicit_cross_discipline_role",
            "symmetric": True,
            "unknown_state": "review_required",
            "hard_conflict": "disjoint_known_disciplines_without_an_explicit_cross_discipline_role",
            "allowed_roles": ["method_transfer", "comparison", "general_methodology", "statistical_method"],
            "ontology_schema": "dpl.literature_discipline_ontology.v1",
            "ontology_hash": ontology["ontology_hash"],
            "generated_at": utc_now(),
        },
    )
    return report


def _build_fetch_decisions(
    items: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    decisions: list[dict[str, Any]] = []
    mode = str(policy.get("mode") or "resolve_then_fetch_on_demand")
    remaining = int(policy.get("max_fulltext_candidates") or 0)
    for index, item in enumerate(items):
        identity_status = str(item.get("identity_resolution_status") or "unresolved")
        has_text = _has_readable_text(item)
        has_local_parse = bool(item.get("document_parses") or item.get("local_attachment_path"))
        fetch = False
        reason = "not_required"
        if item.get("paper_fetch_cache_hit"):
            reason = "verified_fulltext_cache_hit"
        elif mode in {"off", "resolve_only", "local_only"}:
            reason = f"policy_{mode}"
        elif identity_status not in {"resolved_exact", "resolved_probable"}:
            reason = f"identity_{identity_status}"
        elif has_local_parse:
            reason = "local_evidence_available"
        elif mode == "fulltext_eager":
            fetch = True
            reason = "policy_fulltext_eager"
        elif not has_text:
            fetch = True
            reason = "missing_readable_abstract_or_text"
        elif bool(item.get("requires_fulltext") or item.get("evidence_required") or item.get("citation_intent")):
            fetch = True
            reason = "declared_evidence_requirement"
        elif item.get("gate_state") == "review_required" and not item.get("pdf_text_excerpt"):
            fetch = True
            reason = "fulltext_can_resolve_prefetch_review"
        if fetch and remaining <= 0:
            fetch = False
            reason = "fulltext_candidate_limit_exceeded"
        elif fetch:
            remaining -= 1
        base = {
            "index": index,
            "candidate_id": str((item.get("identity_resolution_receipt") or {}).get("candidate_id") or ""),
            "work_id": str(item.get("resolved_work_id") or item.get("work_id") or ""),
            "query": _target_text(item),
            "fetch": fetch,
            "reason": reason,
            "identity_status": identity_status,
            "asset_profile": "none",
            "policy_hash": policy.get("policy_hash"),
        }
        base["decision_hash"] = _canonical_hash(base)
        decisions.append(base)
    packet_hash = _canonical_hash(decisions)
    return decisions, packet_hash


def _reuse_cached_fetches(project_path: Path, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    references_dir = project_path / "references"
    manifest = _load_json_object(references_dir / "paper_fetch_manifest.json")
    cached_by_work: dict[str, dict[str, Any]] = {}
    for output in manifest.get("outputs") or []:
        if not isinstance(output, dict):
            continue
        work_id = str(output.get("work_id") or "")
        if work_id and output.get("path") and output.get("sha256"):
            cached_by_work[work_id] = output
    fulltext_root = (references_dir / "fulltext").resolve()
    enriched = list(items)
    reused: list[dict[str, Any]] = []
    for index, item in enumerate(enriched):
        work_id = str(item.get("resolved_work_id") or item.get("work_id") or canonical_work_id(item))
        cached = cached_by_work.get(work_id)
        if not cached:
            continue
        path = Path(str(cached.get("path") or ""))
        if not path.is_absolute():
            path = project_path / path
        if not path.is_file() or fulltext_root not in path.resolve().parents:
            continue
        if _file_sha256(path) != cached.get("sha256"):
            continue
        enriched[index] = _apply_fetched_payload(item, path, project_path)
        enriched[index]["paper_fetch_cache_hit"] = True
        enriched[index]["paper_fetch_status"] = "cached"
        reused.append(
            {
                "candidate_id": str((item.get("identity_resolution_receipt") or {}).get("candidate_id") or ""),
                "work_id": work_id,
                "path": enriched[index]["paper_fetch_markdown_path"],
                "sha256": enriched[index]["paper_fetch_output_sha256"],
            }
        )
    return enriched, reused


def _apply_fetched_payload(item: dict[str, Any], output_path: Path, project_path: Path) -> dict[str, Any]:
    enriched = _apply_payload(item, output_path)
    try:
        relative = output_path.resolve().relative_to(project_path.resolve()).as_posix()
    except ValueError:
        relative = str(output_path)
    enriched["paper_fetch_markdown_path"] = relative
    enriched["paper_fetch_output_sha256"] = _file_sha256(output_path)
    return enriched


def _execute_batch_fetch(
    project_path: Path,
    items: list[dict[str, Any]],
    targets: list[tuple[int, dict[str, Any]]],
    *,
    base_command: list[str],
    extra_env: dict[str, str],
    run: Runner,
    timeout: int,
    concurrency: int,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    references_dir = project_path / "references"
    fulltext_dir = references_dir / "fulltext"
    query_file = references_dir / "paper_fetch_queries.txt"
    batch_results = references_dir / "paper_fetch_batch_results.jsonl"
    query_file.write_text("\n".join(decision["query"] for _, decision in targets) + "\n", encoding="utf-8")
    command = [
        *base_command,
        "--query-file",
        str(query_file),
        "--format",
        "both",
        "--output-dir",
        str(fulltext_dir),
        "--batch-results",
        str(batch_results),
        "--batch-concurrency",
        str(concurrency),
        "--asset-profile",
        "none",
        "--artifact-mode",
        "markdown-assets",
        "--no-download",
    ]
    try:
        result = run(command, cwd=project_path, env=extra_env, timeout=max(timeout, timeout * len(targets)))
    except Exception as exc:
        manifest["failures"].append({"query": "batch", "error": str(exc)})
        return items
    manifest["batch_mode"] = True
    manifest["batch_returncode"] = result.get("returncode")
    rows: list[dict[str, Any]] = []
    if batch_results.is_file():
        for line in batch_results.read_text(encoding="utf-8-sig").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    by_index = {int(row.get("index") or 0): row for row in rows}
    enriched = list(items)
    for batch_index, (item_index, decision) in enumerate(targets, start=1):
        row = by_index.get(batch_index, {})
        output_value = str(row.get("output_path") or "")
        output_path = Path(output_value) if output_value else Path()
        if output_value and not output_path.is_absolute():
            output_path = project_path / output_path
        if row.get("status") != "ok" or not output_value or not output_path.is_file():
            manifest["failures"].append(
                {
                    "query": decision["query"],
                    "status": row.get("status") or "missing_batch_result",
                    "error": row.get("error"),
                }
            )
            continue
        enriched[item_index] = _apply_fetched_payload(enriched[item_index], output_path, project_path)
        manifest["success_count"] += 1
        manifest["outputs"].append(
            {
                "candidate_id": decision["candidate_id"],
                "work_id": decision["work_id"],
                "path": enriched[item_index]["paper_fetch_markdown_path"],
                "sha256": enriched[item_index]["paper_fetch_output_sha256"],
            }
        )
    return enriched


def _execute_sequential_fetch(
    project_path: Path,
    items: list[dict[str, Any]],
    targets: list[tuple[int, dict[str, Any]]],
    *,
    base_command: list[str],
    extra_env: dict[str, str],
    run: Runner,
    timeout: int,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    fulltext_dir = project_path / "references" / "fulltext"
    enriched = list(items)
    for item_index, decision in targets:
        item = enriched[item_index]
        output_path = fulltext_dir / f"{item_index + 1:02d}_{_safe_stem(str(item.get('title') or decision['query']), 'paper')}.json"
        command = [
            *base_command,
            "--query",
            decision["query"],
            "--format",
            "both",
            "--output",
            str(output_path),
            "--output-dir",
            str(fulltext_dir),
            "--asset-profile",
            "none",
            "--artifact-mode",
            "markdown-assets",
            "--no-download",
        ]
        try:
            result = run(command, cwd=project_path, env=extra_env, timeout=timeout)
        except Exception as exc:
            manifest["failures"].append({"query": decision["query"], "error": str(exc)})
            continue
        if int(result.get("returncode") or 0) != 0 or not output_path.is_file():
            manifest["failures"].append(
                {
                    "query": decision["query"],
                    "returncode": result.get("returncode"),
                    "stderr": result.get("stderr", ""),
                }
            )
            continue
        enriched[item_index] = _apply_fetched_payload(item, output_path, project_path)
        manifest["success_count"] += 1
        manifest["outputs"].append(
            {
                "candidate_id": decision["candidate_id"],
                "work_id": decision["work_id"],
                "path": enriched[item_index]["paper_fetch_markdown_path"],
                "sha256": enriched[item_index]["paper_fetch_output_sha256"],
            }
        )
    return enriched


def _execute_fetch_decisions(
    project_path: Path,
    items: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    policy: dict[str, Any],
    *,
    command: list[str] | None,
    runner: Runner | None,
    timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    references_dir = project_path / "references"
    fulltext_dir = references_dir / "fulltext"
    fulltext_dir.mkdir(parents=True, exist_ok=True)
    targets = [(index, decision) for index, decision in enumerate(decisions) if decision.get("fetch")]
    if runner is not None and command is None:
        base_command, extra_env, runtime_source = ["paper-fetch"], {}, "injected"
    else:
        base_command, extra_env, runtime_source = resolve_paper_fetch_command(command)
    manifest: dict[str, Any] = {
        "schema_version": "dpl.paper_fetch_manifest.v2",
        "status": "skipped",
        "runtime_source": runtime_source,
        "runtime_version": PAPER_FETCH_VERSION,
        "runtime_upstream_commit": UPSTREAM_COMMIT,
        "started_at": utc_now(),
        "query_file": "references/paper_fetch_queries.txt",
        "output_dir": "references/fulltext",
        "attempted_count": len(targets),
        "success_count": 0,
        "batch_mode": False,
        "failures": [],
        "outputs": [],
        "policy_hash": policy.get("policy_hash"),
    }
    if not targets:
        manifest["finished_at"] = utc_now()
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return items, manifest
    if not base_command:
        manifest["status"] = "unavailable"
        manifest["finished_at"] = utc_now()
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return items, manifest
    run = runner or _default_runner
    if len(targets) >= 3:
        enriched = _execute_batch_fetch(
            project_path,
            items,
            targets,
            base_command=base_command,
            extra_env=extra_env,
            run=run,
            timeout=timeout,
            concurrency=int(policy.get("batch_concurrency") or 1),
            manifest=manifest,
        )
    else:
        enriched = _execute_sequential_fetch(
            project_path,
            items,
            targets,
            base_command=base_command,
            extra_env=extra_env,
            run=run,
            timeout=timeout,
            manifest=manifest,
        )
    manifest["status"] = "completed" if manifest["success_count"] == len(targets) else "degraded"
    manifest["finished_at"] = utc_now()
    _write_json(references_dir / "paper_fetch_manifest.json", manifest)
    return enriched, manifest


def enrich_with_paper_fetch(
    project: str | Path,
    items: list[dict[str, Any]],
    *,
    min_per_context: int = MIN_CONTEXT_ITEMS,
    command: list[str] | None = None,
    runner: Runner | None = None,
    timeout: int = 90,
    fetch_policy_mode: str | None = None,
    identity_resolver: IdentityResolver | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resolve shortlist identities, fetch evidence on demand, and return active candidates.

    Projects without a query contract retain the pre-v0.40 adapter behavior so
    direct callers and legacy projects remain compatible until their next
    managed literature search writes the new contract.
    """
    project_path = Path(project)
    references_dir = project_path / "references"
    contract_path = references_dir / "query_contract.json"
    if not contract_path.is_file():
        return _legacy_enrich_with_paper_fetch(
            project,
            items,
            min_per_context=min_per_context,
            command=command,
            runner=runner,
            timeout=timeout,
        )
    contract = _load_json_object(contract_path)
    policy = load_literature_fetch_policy(project_path, mode=fetch_policy_mode)
    shortlist, prefetch_rejected = apply_relevance_gate(items, contract)
    prefetch_report = _write_prefetch_outputs(references_dir, shortlist, prefetch_rejected, contract)
    if policy.get("mode") == "off":
        manifest = {
            "schema_version": "dpl.paper_fetch_manifest.v2",
            "status": "disabled",
            "runtime_source": "disabled_by_policy",
            "runtime_version": PAPER_FETCH_VERSION,
            "runtime_upstream_commit": UPSTREAM_COMMIT,
            "attempted_count": 0,
            "success_count": 0,
            "outputs": [],
            "failures": [],
            "policy_hash": policy.get("policy_hash"),
            "prefetch_report": "references/prefetch_relevance_report.json",
        }
        _write_json(references_dir / "paper_fetch_manifest.json", manifest)
        return shortlist, manifest

    allow_network = policy.get("mode") not in {"local_only", "off"} and os.getenv(
        "DRAFTPAPER_DISABLE_IDENTITY_NETWORK", ""
    ).strip().casefold() not in {"1", "true", "yes"}
    resolved, identity_summary = resolve_literature_identities(
        project_path,
        shortlist,
        query_contract=contract,
        fetch_policy=policy,
        resolver=identity_resolver,
        allow_network=allow_network,
    )
    resolved, cached_fetches = _reuse_cached_fetches(project_path, resolved)
    decisions, decision_packet_hash = _build_fetch_decisions(resolved, policy)
    for item, decision in zip(resolved, decisions, strict=True):
        item["fulltext_fetch_decision"] = decision
    _write_json(
        references_dir / "fulltext_fetch_decisions.json",
        {
            "schema_version": "dpl.fulltext_fetch_decision.v1",
            "policy_hash": policy.get("policy_hash"),
            "candidate_set_hash": prefetch_report.get("candidate_set_hash"),
            "decision_packet_hash": decision_packet_hash,
            "decision_count": len(decisions),
            "fetch_count": sum(bool(item.get("fetch")) for item in decisions),
            "decisions": decisions,
        },
    )
    fetched, manifest = _execute_fetch_decisions(
        project_path,
        resolved,
        decisions,
        policy,
        command=command,
        runner=runner,
        timeout=timeout,
    )
    for item, decision in zip(fetched, decisions, strict=True):
        if decision.get("fetch"):
            item["paper_fetch_execution_status"] = (
                "completed" if item.get("paper_fetch_output_sha256") else str(manifest.get("status") or "failed")
            )
    active, quarantine, postfetch_report = assess_postfetch_candidates(
        project_path,
        fetched,
        contract,
        prefetch_rejected=prefetch_rejected,
    )
    manifest.update(
        {
            "prefetch_report": "references/prefetch_relevance_report.json",
            "identity_summary": "references/paper_identity_resolution_summary.json",
            "identity_status_counts": identity_summary.get("status_counts") or {},
            "identity_candidate_set_hash": identity_summary.get("candidate_set_hash"),
            "query_contract_hash": identity_summary.get("query_contract_hash"),
            "decision_packet_hash": decision_packet_hash,
            "postfetch_report": "references/postfetch_relevance_report.json",
            "postfetch_assessment_hash": postfetch_report.get("assessment_hash"),
            "active_count": len(active),
            "quarantine_count": len(quarantine),
            "quarantined_work_ids": [
                str(item.get("resolved_work_id") or item.get("work_id") or canonical_work_id(item))
                for item in quarantine
                if str(item.get("postfetch_state") or "").startswith("rejected_")
                if str(item.get("resolved_work_id") or item.get("work_id") or canonical_work_id(item))
            ],
            "quarantine_artifacts": postfetch_report.get("quarantine_artifacts") or [],
            "cache_hit_count": len(cached_fetches),
            "cached_outputs": cached_fetches,
            "outputs": [*cached_fetches, *(manifest.get("outputs") or [])],
        }
    )
    if cached_fetches and not manifest.get("attempted_count"):
        manifest["status"] = "completed_from_cache"
    _write_json(references_dir / "paper_fetch_manifest.json", manifest)
    return active, manifest
