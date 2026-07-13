"""Author-controlled manuscript metadata, stable source maps, revisions, and rollback."""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .bibliography import build_reference_registry
from .passport import utc_now
from .project_state import load_project, mark_stages_stale, update_stage_status
from .references import citation_evidence_rows, write_literature_html_summaries
from .section_contracts import validate_section_writing
from .state_kernel import append_jsonl_locked


SOURCE_MAP = "latex/manuscript_source_map.json"
METADATA_PATH = "writing/manuscript_metadata.yaml"
REVISION_ROOT = "writing/revisions"
REVISION_LEDGER = "writing/revision_ledger.jsonl"
LOCKS_PATH = "writing/user_locks.json"
WORKSPACE_PATH = "writing/revision_workspace.json"
REVIEW_QUEUE = "writing/review_revision_queue.json"

SECTION_SOURCES = {
    "introduction": "introduction/introduction.tex",
    "data": "data/data.tex",
    "methods": "methods/methods.tex",
    "results": "results/results.tex",
    "discussion": "discussion/discussion.tex",
}
SECTION_STAGES = {
    "introduction": "introduction",
    "data": "data_writing",
    "methods": "methods_writing",
    "results": "results",
    "discussion": "discussion",
}


class ManuscriptRevisionError(RuntimeError):
    """Raised when a revision cannot be located, previewed, or applied safely."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized_context(text: str) -> str:
    text = re.sub(r"%.*", "", text)
    text = re.sub(r"\\(?:cite\w*|ref|label)\{[^}]*\}", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _paragraphs(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines(keepends=True)
    blocks = []
    start = None
    for index, line in enumerate(lines, start=1):
        if line.strip() and start is None:
            start = index
        if start is not None and (not line.strip() or index == len(lines)):
            end = index - 1 if not line.strip() else index
            block = "".join(lines[start - 1:end])
            if _normalized_context(block):
                blocks.append({"line_start": start, "line_end": end, "text": block})
            start = None
    return blocks


def _anchors(text: str) -> dict[str, list[str]]:
    return {
        "figures": re.findall(r"\\(?:ref|autoref)\{([^}]*(?:fig|figure)[^}]*)\}", text, flags=re.I),
        "tables": re.findall(r"\\(?:ref|autoref)\{([^}]*(?:tab|table)[^}]*)\}", text, flags=re.I),
        "equations": re.findall(r"\\(?:ref|eqref)\{([^}]*(?:eq|equation)[^}]*)\}", text, flags=re.I),
        "citations": sorted({key.strip() for group in re.findall(r"\\cite\w*\{([^}]+)\}", text) for key in group.split(",") if key.strip()}),
    }


def _environment(text: str) -> str:
    values = re.findall(r"\\begin\{([^}]+)\}", text)
    return values[0] if values else "paragraph"


def build_manuscript_source_map(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    old = _read_json(state.path / SOURCE_MAP)
    context_index = _read_json(state.path / "writing" / "section_context_index.json")
    old_by_hash = {str(item.get("before_hash")): item for item in old.get("paragraphs") or [] if isinstance(item, dict) and item.get("before_hash")}
    locks = _read_json(state.path / LOCKS_PATH)
    locked_ids = {str(item.get("paragraph_id")) for item in locks.get("locks") or [] if isinstance(item, dict) and item.get("active", True)}
    paragraphs = []
    for section, canonical in SECTION_SOURCES.items():
        source = state.path / canonical
        projection = state.path / "latex" / "sections" / f"{section}.tex"
        path = source if source.is_file() else projection
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        context_slices = list((((context_index.get("sections") or {}).get(section) or {}).get("slices") or []))
        for index, block in enumerate(_paragraphs(text), start=1):
            before_hash = _sha_text(block["text"])
            previous = old_by_hash.get(before_hash)
            paragraph_id = str(previous.get("paragraph_id")) if previous else f"{section}:p{index:03d}:{hashlib.sha256(_normalized_context(block['text']).encode()).hexdigest()[:10]}"
            paragraphs.append({
                "file": f"latex/sections/{section}.tex",
                "canonical_file": canonical,
                "section": section,
                "paragraph_id": paragraph_id,
                "line_start": block["line_start"],
                "line_end": block["line_end"],
                "latex_environment": _environment(block["text"]),
                "anchors": _anchors(block["text"]),
                "before_hash": before_hash,
                "context_hash": _sha_text(_normalized_context(block["text"])),
                "context_excerpt": _normalized_context(block["text"])[:240],
                "evidence_ids": list(previous.get("evidence_ids") or []) if previous else list((context_slices[index - 1].get("evidence_ids") or []) if index <= len(context_slices) and isinstance(context_slices[index - 1], dict) else []),
                "origin": "user" if paragraph_id in locked_ids else str(previous.get("origin") or "generated") if previous else "generated",
                "locked_by_user": paragraph_id in locked_ids,
            })
    payload = {
        "schema_version": "dpl.manuscript_source_map.v1",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "paragraph_count": len(paragraphs),
        "paragraphs": paragraphs,
    }
    _write_json(state.path / SOURCE_MAP, payload)
    _import_review_findings(state.path, paragraphs)
    _synchronize_revision_workspace(state.path)
    return {"status": "written", "paragraph_count": len(paragraphs), "source_map": SOURCE_MAP}


def _import_review_findings(root: Path, paragraphs: list[dict[str, Any]]) -> None:
    aggregate = _read_json(root / "quality_checks" / "blind_reviews" / "aggregate.json")
    tasks = []
    for item in aggregate.get("revision_queue") or []:
        if not isinstance(item, dict):
            continue
        locator = str(item.get("locator") or "")
        section = next((name for name in SECTION_SOURCES if name in locator.lower()), None)
        candidates = [row for row in paragraphs if row.get("section") == section] if section else []
        tasks.append({
            "task_id": f"review:{item.get('reviewer')}:{item.get('finding_id')}",
            "source_finding_id": item.get("finding_id"),
            "reviewer": item.get("reviewer"),
            "severity": item.get("severity"),
            "locator": locator,
            "detail": item.get("detail"),
            "required_action": item.get("required_action"),
            "candidate_paragraph_ids": [row.get("paragraph_id") for row in candidates],
            "status": "candidate_task",
            "automatic_apply": False,
        })
    _write_json(root / REVIEW_QUEUE, {"schema_version": "dpl.review_revision_queue.v1", "tasks": tasks})


def import_review_findings(project: str | Path, review: str | Path | None = None) -> dict[str, Any]:
    state = load_project(project)
    if review:
        source = Path(review).expanduser().resolve()
        if source.suffix.lower() in {".md", ".markdown"}:
            json_peer = source.with_suffix(".json")
            if not json_peer.is_file():
                raise ManuscriptRevisionError("Markdown review import requires the structured sibling report.json.")
            source = json_peer
        if source.suffix.lower() != ".json":
            raise ManuscriptRevisionError("Structured review JSON is required for revision task import.")
        payload = _read_json(source)
        target = state.path / "quality_checks" / "blind_reviews" / "imported_review.json"
        _write_json(target, payload)
    build_manuscript_source_map(state.path)
    queue = _read_json(state.path / REVIEW_QUEUE)
    return {"status": "imported", "task_count": len(queue.get("tasks") or []), "queue": REVIEW_QUEUE}


def list_revision_tasks(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    queue = _read_json(state.path / REVIEW_QUEUE)
    return {"status": "listed", "task_count": len(queue.get("tasks") or []), "tasks": queue.get("tasks") or []}


def inspect_revision_preview(project: str | Path, revision_id: str) -> dict[str, Any]:
    state = load_project(project)
    request_path, request = _request(state.path, revision_id)
    diff_path = state.path / str(request.get("diff_path") or "")
    return {
        "status": "ready" if request.get("preview_status") == "ready" else str(request.get("preview_status") or "unknown"),
        "revision_id": revision_id,
        "request": str(request_path.relative_to(state.path)).replace("\\", "/"),
        "diff": diff_path.read_text(encoding="utf-8-sig") if diff_path.is_file() else "",
        "change_class": request.get("change_class"),
        "stale_scope": request.get("required_gates") or [],
        "user_acceptance": bool(request.get("user_acceptance")),
    }


def active_user_locks(project: str | Path, section: str | None = None) -> list[dict[str, Any]]:
    state = load_project(project)
    locks = _read_json(state.path / LOCKS_PATH)
    return [
        item for item in locks.get("locks") or []
        if isinstance(item, dict)
        and item.get("active", True)
        and (section is None or item.get("section") == section)
    ]


def assert_writer_may_replace_section(project: str | Path, section: str) -> None:
    locks = active_user_locks(project, section)
    if locks:
        ids = ", ".join(str(item.get("revision_id")) for item in locks)
        raise ManuscriptRevisionError(
            f"Section {section} contains accepted exact user text ({ids}); the writer may not silently replace it. "
            "Rollback the revision or create a new project version before regenerating this section."
        )


def _target_from_locator(root: Path, at: str | None, paragraph: str | None) -> dict[str, Any]:
    source_map = _read_json(root / SOURCE_MAP)
    if not source_map:
        build_manuscript_source_map(root)
        source_map = _read_json(root / SOURCE_MAP)
    rows = [item for item in source_map.get("paragraphs") or [] if isinstance(item, dict)]
    if paragraph:
        matches = [item for item in rows if item.get("paragraph_id") == paragraph]
        if len(matches) != 1:
            raise ManuscriptRevisionError("Stable paragraph ID is missing or ambiguous; rebuild the source map and reselect the target.")
        return matches[0]
    if not at:
        raise ManuscriptRevisionError("Provide --at file:start-end or --paragraph stable_id.")
    match = re.fullmatch(r"(.+):(\d+)(?:-(\d+))?", at.strip())
    if not match:
        raise ManuscriptRevisionError("Line target must use file:start-end.")
    requested_file = match.group(1).replace("\\", "/")
    start, end = int(match.group(2)), int(match.group(3) or match.group(2))
    matches = [
        item for item in rows
        if item.get("file") == requested_file
        and int(item.get("line_start") or 0) <= end
        and int(item.get("line_end") or 0) >= start
    ]
    if len(matches) != 1:
        raise ManuscriptRevisionError("Line range does not resolve to exactly one paragraph; use a stable paragraph ID.")
    return matches[0]


def _classify(section: str, instruction: str, content: str, explicit: str | None = None) -> tuple[str, list[str], bool]:
    if explicit:
        change_class = explicit
    else:
        text = f"{instruction} {content}".lower()
        if any(token in text for token in ("replace data", "new dataset", "rerun", "new method", "replace figure", "new run")):
            change_class = "scientific_evidence_change"
        elif re.search(r"\\cite\w*\{", content) or "citation" in text or "reference" in text:
            change_class = "citation_edit"
        elif section == "results" and (re.search(r"\b\d+(?:\.\d+)?\b", content) or "figure" in text):
            change_class = "result_interpretation"
        elif any(token in text for token in ("narrow", "weaken", "收紧", "降低结论", "limited to")):
            change_class = "claim_narrowing"
        else:
            change_class = "language_only"
    stale = {
        "language_only": ["latex", "quality_checks"],
        "citation_edit": ["latex", "quality_checks"],
        "new_reference": ["references", "latex", "quality_checks"],
        "claim_narrowing": ["discussion", "latex", "quality_checks"] if section == "results" else ["latex", "quality_checks"],
        "result_interpretation": ["discussion", "latex", "quality_checks"],
        "scientific_evidence_change": ["result_validity", "result_support", "core_evidence", "results", "introduction", "data_writing", "methods_writing", "discussion", "latex", "quality_checks"],
    }.get(change_class, ["latex", "quality_checks"])
    citation_bearing = change_class in {"citation_edit", "new_reference", "claim_narrowing", "result_interpretation", "scientific_evidence_change"} or bool(re.search(r"\\cite\w*\{", content))
    return change_class, stale, citation_bearing


def _apply_operation(text: str, block: dict[str, Any], operation: str, content: str) -> str:
    lines = text.splitlines(keepends=True)
    start, end = int(block["line_start"]) - 1, int(block["line_end"])
    value = content
    if value and not value.endswith("\n"):
        value += "\n"
    if operation == "replace":
        return "".join(lines[:start]) + value + "".join(lines[end:])
    if operation == "delete":
        return "".join(lines[:start]) + "".join(lines[end:])
    if operation == "insert_before":
        return "".join(lines[:start]) + value + "".join(lines[start:])
    if operation == "insert_after":
        return "".join(lines[:end]) + value + "".join(lines[end:])
    raise ManuscriptRevisionError(f"Unsupported revision operation: {operation}")


def _build_revision_preview_pdf(root: Path, request: dict[str, Any], proposed: str, revision_dir: Path) -> dict[str, Any]:
    main_tex = root / "latex" / "main.tex"
    library = root / "latex" / "library.bib"
    if not main_tex.is_file() or not library.is_file():
        return {"status": "not_available", "reason": "Assemble LaTeX before requesting a PDF revision preview.", "pdf": None}
    from .latex_assembly import _find_latex_executable

    engine = _find_latex_executable(["xelatex", "xelatex.exe", "pdflatex", "pdflatex.exe"])
    if not engine:
        return {"status": "skipped", "reason": "No local LaTeX engine is available.", "pdf": None}
    preview_dir = revision_dir / "preview_build"
    sections_dir = preview_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for section in SECTION_SOURCES:
        source = root / "latex" / "sections" / f"{section}.tex"
        if source.is_file():
            shutil.copyfile(source, sections_dir / source.name)
    target_section = str(request.get("section") or "")
    if target_section:
        (sections_dir / f"{target_section}.tex").write_text(proposed, encoding="utf-8")
    preview_main = main_tex.read_text(encoding="utf-8-sig")
    preview_main = preview_main.replace(
        "\\begin{document}",
        "\\graphicspath{{../../../../}{../../../../results/figures/}{../../../../results/}}\n\\begin{document}",
        1,
    )
    (preview_dir / "main.tex").write_text(preview_main, encoding="utf-8")
    shutil.copyfile(library, preview_dir / "library.bib")
    for bst in (root / "latex").glob("*.bst"):
        shutil.copyfile(bst, preview_dir / bst.name)
    commands: list[dict[str, Any]] = []

    def run(command: list[str]) -> int:
        completed = subprocess.run(
            command,
            cwd=preview_dir,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            check=False,
        )
        commands.append({"command": command, "returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]})
        return completed.returncode

    try:
        code = run([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
        aux = preview_dir / "main.aux"
        if code == 0 and aux.is_file() and "\\bibdata" in aux.read_text(encoding="utf-8", errors="ignore"):
            bibtex = _find_latex_executable(["bibtex", "bibtex.exe"])
            if bibtex:
                code = run([bibtex, "main"])
        if code == 0:
            code = run([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
        if code == 0:
            code = run([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        commands.append({"error": str(exc)})
        code = 1
    log = revision_dir / "revision_preview.compile.json"
    _write_json(log, {"status": "passed" if code == 0 else "failed", "engine": engine, "commands": commands})
    built = preview_dir / "main.pdf"
    target = revision_dir / "revision_preview.pdf"
    if code == 0 and built.is_file():
        shutil.copyfile(built, target)
        return {"status": "passed", "pdf": str(target.relative_to(root)).replace("\\", "/"), "compile_log": str(log.relative_to(root)).replace("\\", "/")}
    return {"status": "failed", "reason": "LaTeX preview compilation failed; inspect the compile log.", "pdf": None, "compile_log": str(log.relative_to(root)).replace("\\", "/")}


def preview_manuscript_revision(
    project: str | Path,
    instruction: str,
    *,
    at: str | None = None,
    paragraph: str | None = None,
    content_file: str | Path | None = None,
    operation: str = "replace",
    mode: str = "instruction_to_codex",
    change_class: str | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    target = _target_from_locator(state.path, at, paragraph)
    canonical = state.path / str(target["canonical_file"])
    current = canonical.read_text(encoding="utf-8-sig")
    block = next((item for item in _paragraphs(current) if item["line_start"] == target["line_start"] and item["line_end"] == target["line_end"]), None)
    if not block or _sha_text(block["text"]) != target.get("before_hash"):
        raise ManuscriptRevisionError("Target paragraph changed after source-map generation; rebuild and preview again.")
    content = ""
    if content_file:
        content = Path(content_file).expanduser().resolve().read_text(encoding="utf-8-sig")
    if mode == "exact_text" and not content_file:
        raise ManuscriptRevisionError("exact_text mode requires --content-file.")
    classification, stale_scope, citation_bearing = _classify(str(target["section"]), instruction, content, change_class)
    seed = f"{target['paragraph_id']}|{target['before_hash']}|{instruction}|{operation}|{len(_read_json(state.path / WORKSPACE_PATH).get('requests') or [])}"
    request_id = "revision:" + hashlib.sha256(seed.encode()).hexdigest()[:16]
    revision_dir = state.path / REVISION_ROOT / request_id.replace(":", "_")
    revision_dir.mkdir(parents=True, exist_ok=True)
    proposed = _apply_operation(current, block, operation, content) if content_file else current
    diff = "".join(difflib.unified_diff(current.splitlines(keepends=True), proposed.splitlines(keepends=True), fromfile=str(target["canonical_file"]), tofile=str(target["canonical_file"])))
    (revision_dir / "before.tex").write_text(current, encoding="utf-8")
    (revision_dir / "proposed.tex").write_text(proposed, encoding="utf-8")
    (revision_dir / "preview.diff").write_text(diff, encoding="utf-8")
    request = {
        "schema_version": "dpl.revision_request.v1",
        "revision_id": request_id,
        "target_file": target["file"],
        "canonical_file": target["canonical_file"],
        "target_line_start": target["line_start"],
        "target_line_end": target["line_end"],
        "paragraph_id": target["paragraph_id"],
        "section": target["section"],
        "operation": operation,
        "mode": mode,
        "user_instruction": instruction,
        "exact_user_text": content if mode == "exact_text" else None,
        "replacement_content": content if content_file else None,
        "affected_claims": list(target.get("evidence_ids") or []),
        "added_references": sorted(set(_anchors(content).get("citations") or []) - set(target.get("anchors", {}).get("citations") or [])),
        "expected_before_hash": target["before_hash"],
        "expected_file_hash": _sha_text(current),
        "change_class": classification,
        "required_gates": stale_scope,
        "citation_bearing": citation_bearing,
        "preview_status": "ready" if content_file else "codex_patch_required",
        "user_acceptance": False,
        "diff_path": f"{REVISION_ROOT}/{revision_dir.name}/preview.diff",
        "before_path": f"{REVISION_ROOT}/{revision_dir.name}/before.tex",
        "proposed_path": f"{REVISION_ROOT}/{revision_dir.name}/proposed.tex",
        "rollback_point": target["before_hash"],
    }
    request["pdf_preview"] = _build_revision_preview_pdf(state.path, request, proposed, revision_dir) if content_file else {"status": "pending_codex_patch", "pdf": None}
    _write_json(revision_dir / "revision_request.json", request)
    workspace = _read_json(state.path / WORKSPACE_PATH)
    requests = [item for item in workspace.get("requests") or [] if isinstance(item, dict) and item.get("revision_id") != request_id]
    requests.append({"revision_id": request_id, "request_path": f"{REVISION_ROOT}/{revision_dir.name}/revision_request.json", "status": request["preview_status"]})
    _write_json(state.path / WORKSPACE_PATH, {"schema_version": "dpl.revision_workspace.v1", "requests": requests, "pending_requests": [item for item in requests if item.get("status") != "applied"]})
    return {"status": request["preview_status"], "revision_id": request_id, "request": f"{REVISION_ROOT}/{revision_dir.name}/revision_request.json", "diff": request["diff_path"], "pdf_preview": request["pdf_preview"], "change_class": classification, "stale_scope": stale_scope}


def _request(root: Path, request_id: str) -> tuple[Path, dict[str, Any]]:
    path = root / REVISION_ROOT / request_id.replace(":", "_") / "revision_request.json"
    payload = _read_json(path)
    if not payload:
        raise ManuscriptRevisionError(f"Revision request does not exist: {request_id}")
    return path, payload


def _update_revision_workspace_status(root: Path, revision_id: str, status: str) -> None:
    workspace = _read_json(root / WORKSPACE_PATH)
    requests = []
    for item in workspace.get("requests") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if row.get("revision_id") == revision_id:
            row["status"] = status
        requests.append(row)
    _write_json(
        root / WORKSPACE_PATH,
        {
            "schema_version": "dpl.revision_workspace.v1",
            "requests": requests,
            "pending_requests": [item for item in requests if item.get("status") not in {"applied", "rolled_back", "discarded"}],
        },
    )


def _synchronize_revision_workspace(root: Path) -> None:
    workspace_path = root / WORKSPACE_PATH
    workspace = _read_json(workspace_path)
    if not workspace and not (root / REVISION_ROOT).exists():
        return
    requests = []
    for item in workspace.get("requests") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        request_path = root / str(row.get("request_path") or "")
        request = _read_json(request_path)
        if request.get("preview_status"):
            row["status"] = str(request["preview_status"])
        requests.append(row)
    _write_json(
        workspace_path,
        {
            "schema_version": "dpl.revision_workspace.v1",
            "requests": requests,
            "pending_requests": [item for item in requests if item.get("status") not in {"applied", "rolled_back", "discarded"}],
        },
    )


def apply_manuscript_revision(project: str | Path, request_id: str) -> dict[str, Any]:
    state = load_project(project)
    request_path, request = _request(state.path, request_id)
    if request.get("preview_status") != "ready" or request.get("replacement_content") is None:
        raise ManuscriptRevisionError("Revision requires a complete preview before acceptance.")
    if request.get("change_class") == "scientific_evidence_change":
        raise ManuscriptRevisionError("A prose patch cannot apply a data/method/run/core-figure change. Reopen evidence or create a clean project version.")
    build_manuscript_source_map(state.path)
    target = _target_from_locator(state.path, None, str(request["paragraph_id"]))
    canonical = state.path / str(request["canonical_file"])
    current = canonical.read_text(encoding="utf-8-sig")
    blocks = _paragraphs(current)
    block = next((item for item in blocks if _sha_text(item["text"]) == request.get("expected_before_hash")), None)
    if block is None:
        raise ManuscriptRevisionError("Paragraph hash changed or moved ambiguously after preview; no edit was applied.")
    after = _apply_operation(current, block, str(request["operation"]), str(request.get("replacement_content") or ""))
    before_hash, after_hash = _sha_text(current), _sha_text(after)
    backup = request_path.parent / "before_applied.tex"
    backup.write_text(current, encoding="utf-8")
    canonical.write_text(after, encoding="utf-8")
    projection = state.path / str(request["target_file"])
    projection.parent.mkdir(parents=True, exist_ok=True)
    projection.write_text(after, encoding="utf-8")
    stage = SECTION_STAGES[str(target["section"])]
    update_stage_status(state.path, stage, "draft")
    stale = mark_stages_stale(state.path, [item for item in request.get("required_gates") or [] if item in load_project(state.path).metadata.get("stages", {}) and item != stage])
    if request.get("citation_bearing"):
        _write_json(state.path / "citation_audit" / "stale_marker.json", {"revision_id": request_id, "after_hash": after_hash, "reason": "citation-bearing manuscript revision must be audited after acceptance"})
    if request.get("change_class") in {"claim_narrowing", "result_interpretation"}:
        _write_json(state.path / "quality_checks" / "blind_reviews" / "stale_marker.json", {"revision_id": request_id, "after_hash": after_hash, "reason": "scientific interpretation changed"})
    if request.get("mode") == "exact_text":
        locks = _read_json(state.path / LOCKS_PATH)
        rows = [item for item in locks.get("locks") or [] if isinstance(item, dict) and item.get("revision_id") != request_id]
        applied_text = str(request.get("exact_user_text") or "")
        if applied_text and not applied_text.endswith("\n"):
            applied_text += "\n"
        rows.append({"revision_id": request_id, "paragraph_id": request["paragraph_id"], "section": target["section"], "exact_text_sha256": _sha_text(applied_text), "active": True})
        _write_json(state.path / LOCKS_PATH, {"schema_version": "dpl.user_locks.v1", "locks": rows})
    request.update({"preview_status": "applied", "user_acceptance": True, "applied_at": utc_now(), "before_file_hash": before_hash, "after_file_hash": after_hash, "stale_scope_applied": stale, "rollback_file": str(backup.relative_to(state.path)).replace("\\", "/")})
    _write_json(request_path, request)
    _update_revision_workspace_status(state.path, request_id, "applied")
    append_jsonl_locked(state.path / REVISION_LEDGER, {"schema_version": "dpl.revision_ledger.v1", "revision_id": request_id, "recorded_at": utc_now(), "target": request["canonical_file"], "before_hash": before_hash, "after_hash": after_hash, "change_class": request["change_class"], "stale_scope": stale, "rollback_file": request["rollback_file"]})
    build_manuscript_source_map(state.path)
    return {"status": "applied", "revision_id": request_id, "before_hash": before_hash, "after_hash": after_hash, "stale_scope": stale, "next_commands": _next_revision_commands(state.path, request)}


def _next_revision_commands(root: Path, request: dict[str, Any]) -> list[str]:
    commands = [f'python -m draftpaper_cli.cli assemble-latex --project "{root}" --compile-pdf']
    if request.get("citation_bearing"):
        commands.append(f'python -m draftpaper_cli.cli audit-citations --project "{root}" --final')
    commands.extend([f'python -m draftpaper_cli.cli validate-bibliography --project "{root}"', f'python -m draftpaper_cli.cli quality-check --project "{root}"'])
    return commands


def rollback_manuscript_revision(project: str | Path, revision_id: str) -> dict[str, Any]:
    state = load_project(project)
    request_path, request = _request(state.path, revision_id)
    if request.get("preview_status") != "applied":
        raise ManuscriptRevisionError("Only an applied revision can be rolled back.")
    canonical = state.path / str(request["canonical_file"])
    current = canonical.read_text(encoding="utf-8-sig")
    if _sha_text(current) != request.get("after_file_hash"):
        raise ManuscriptRevisionError("Current section differs from the accepted revision; refusing destructive rollback.")
    backup = state.path / str(request["rollback_file"])
    before = backup.read_text(encoding="utf-8-sig")
    canonical.write_text(before, encoding="utf-8")
    (state.path / str(request["target_file"])).write_text(before, encoding="utf-8")
    request.update({"preview_status": "rolled_back", "rolled_back_at": utc_now(), "rollback_after_hash": _sha_text(before)})
    _write_json(request_path, request)
    _update_revision_workspace_status(state.path, revision_id, "rolled_back")
    locks = _read_json(state.path / LOCKS_PATH)
    for item in locks.get("locks") or []:
        if isinstance(item, dict) and item.get("revision_id") == revision_id:
            item["active"] = False
    _write_json(state.path / LOCKS_PATH, locks or {"schema_version": "dpl.user_locks.v1", "locks": []})
    append_jsonl_locked(state.path / REVISION_LEDGER, {"schema_version": "dpl.revision_ledger.v1", "revision_id": revision_id, "recorded_at": utc_now(), "event": "rollback", "after_hash": _sha_text(before)})
    build_manuscript_source_map(state.path)
    return {"status": "rolled_back", "revision_id": revision_id, "restored_hash": _sha_text(before)}


def set_manuscript_metadata(project: str | Path, input_path: str | Path) -> dict[str, Any]:
    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    text = source.read_text(encoding="utf-8-sig")
    payload = json.loads(text) if source.suffix.lower() == ".json" else yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ManuscriptRevisionError("Manuscript metadata input must be a JSON/YAML object.")
    allowed = {
        "title", "abstract", "authors", "affiliations", "corresponding_author", "email", "orcid",
        "credit_contributions", "acknowledgments", "funding", "data_availability",
        "code_availability", "competing_interests", "ethics_consent", "supplementary_material",
        "repository_links", "doi_links", "figure_captions",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ManuscriptRevisionError("Unknown manuscript metadata fields: " + ", ".join(unknown))
    if payload.get("authors") and not isinstance(payload["authors"], list):
        raise ManuscriptRevisionError("authors must be a list of structured author objects.")
    if payload.get("figure_captions") is not None:
        captions = payload["figure_captions"]
        if not isinstance(captions, dict) or not all(
            str(key).strip() and isinstance(value, str) and value.strip()
            for key, value in captions.items()
        ):
            raise ManuscriptRevisionError("figure_captions must map stable figure IDs or paths to non-empty caption strings.")
    if payload.get("abstract"):
        registry = _read_json(state.path / "writing" / "scientific_evidence_registry.json")
        report = validate_section_writing("abstract", str(payload["abstract"]), registry)
        if report.get("decision") != "pass":
            details = "; ".join(str(item.get("detail") or item.get("kind")) for item in report.get("issues") or [])
            raise ManuscriptRevisionError("Abstract evidence contract failed: " + details)
    target = state.path / METADATA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    stale = mark_stages_stale(state.path, [stage for stage in ("latex", "quality_checks") if stage in state.metadata.get("stages", {})])
    return {"status": "written", "metadata": METADATA_PATH, "fields": sorted(payload), "stale_scope": stale}


def add_custom_reference(project: str | Path, input_path: str | Path) -> dict[str, Any]:
    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ManuscriptRevisionError("Custom reference input must be a JSON object.")
    required = ["citation_key", "title", "authors", "year", "evidence_notes"]
    missing = [field for field in required if payload.get(field) in (None, "", [])]
    if missing:
        raise ManuscriptRevisionError("Custom reference is missing: " + ", ".join(missing))
    bib_path = state.path / "references" / "library.bib"
    bib = bib_path.read_text(encoding="utf-8-sig") if bib_path.is_file() else ""
    key = str(payload["citation_key"])
    if re.search(rf"@[A-Za-z]+\{{\s*{re.escape(key)}\s*,", bib):
        raise ManuscriptRevisionError(f"Citation key already exists: {key}")
    doi = str(payload.get("doi") or "")
    url = str(payload.get("url") or (f"https://doi.org/{doi}" if doi else ""))
    entry_type = str(payload.get("entry_type") or ("article" if payload.get("journal") else "misc"))
    fields = {
        "author": " and ".join(str(item) for item in payload["authors"]),
        "title": payload["title"],
        "year": payload["year"],
        "journal": payload.get("journal"),
        "volume": payload.get("volume"),
        "number": payload.get("issue"),
        "pages": payload.get("pages_or_article_number"),
        "doi": doi,
        "url": url,
        "eprint": payload.get("eprint"),
        "archivePrefix": payload.get("archive_prefix"),
        "primaryClass": payload.get("primary_class"),
    }
    rendered = f"@{entry_type}{{{key},\n" + ",\n".join(f"  {name} = {{{value}}}" for name, value in fields.items() if value not in (None, "")) + "\n}\n"
    bib_path.parent.mkdir(parents=True, exist_ok=True)
    bib_path.write_text(bib.rstrip() + "\n\n" + rendered, encoding="utf-8")
    items_path = state.path / "references" / "literature_items.json"
    items = json.loads(items_path.read_text(encoding="utf-8-sig")) if items_path.is_file() else []
    if not isinstance(items, list):
        items = []
    item = {
        "bibtex_key": key,
        "title": payload["title"],
        "authors": payload["authors"],
        "year": str(payload["year"]),
        "publication": payload.get("journal") or "",
        "doi": doi,
        "url": url,
        "abstract": payload.get("abstract") or "",
        "evidence_notes": payload["evidence_notes"],
        "source": "user_curated",
        "search_contexts": payload.get("search_contexts") or ["introduction", "discussion"],
        "user_confirmed": True,
    }
    items.append(item)
    items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = citation_evidence_rows(items)
    with (state.path / "references" / "citation_evidence.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["citation_key", "section", "claim", "evidence_summary", "source", "doi", "url", "citation_role", "data_citation_requirement"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    write_literature_html_summaries(state.path / "references", items)
    build_reference_registry(state.path)
    update_stage_status(state.path, "references", "draft")
    stale = mark_stages_stale(state.path, [stage for stage in ("latex", "quality_checks") if stage in state.metadata.get("stages", {})])
    _write_json(state.path / "citation_audit" / "stale_marker.json", {"reason": "custom reference added", "citation_key": key})
    return {"status": "added", "citation_key": key, "reference_registry": "references/reference_registry.json", "stale_scope": stale, "next_command": "preview-manuscript-revision"}


def prepare_revision_from_task(project: str | Path, task: str) -> dict[str, Any]:
    state = load_project(project)
    queue = _read_json(state.path / REVIEW_QUEUE)
    item = next((row for row in queue.get("tasks") or [] if isinstance(row, dict) and row.get("task_id") == task), None)
    if item is None:
        raise ManuscriptRevisionError(f"Unknown review task: {task}")
    candidates = list(item.get("candidate_paragraph_ids") or [])
    if len(candidates) != 1:
        return {"status": "target_selection_required", "task": item}
    return preview_manuscript_revision(state.path, str(item.get("required_action") or item.get("detail") or "Address reviewer finding."), paragraph=candidates[0])
