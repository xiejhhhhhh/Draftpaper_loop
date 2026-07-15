"""Independent single-manuscript review bundles and absolute release assessment."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import yaml

from .latex_assembly import _aux_requests_bibtex, _ensure_local_bibstyle_fallback, _find_latex_executable
from .project_scaffold import utc_now
from .project_state import load_project


REVIEW_ROOT = "quality_checks/blind_reviews"
BUNDLE_MANIFEST = f"{REVIEW_ROOT}/submission_bundle_manifest.json"
BUNDLE_ZIP = f"{REVIEW_ROOT}/anonymous_submission_bundle.zip"
AGGREGATE_JSON = f"{REVIEW_ROOT}/aggregate.json"
AGGREGATE_MD = f"{REVIEW_ROOT}/aggregate.md"
EVALUATION_JSON = "quality_checks/blind_manuscript_evaluation.json"

RECOMMENDATION_ORDER = {
    "accept_for_revision": 0,
    "minor_revision": 1,
    "major_revision": 2,
    "not_ready": 3,
}
SCORE_DIMENSIONS = {
    "scientific_correctness",
    "scientific_story_and_main_figure_narrative",
    "results_interpretation_and_comparison",
    "reproducible_data_methods",
    "introduction_problem_gap_contribution",
    "discussion_comparison_mechanism_limitation_innovation",
    "figure_readability_panel_logic_captions",
    "prose_naturalness_cross_section_coherence",
}

REPRODUCIBILITY_ALLOWLIST = (
    "data/source_provenance.json",
    "methods/model_provenance.json",
    "methods/environment_manifest.json",
)
REPRODUCIBILITY_GLOBS = (
    "data/scripts/*.py",
    "methods/scripts/*.py",
    "methods/tests/*.py",
)
PRIVATE_LOCATOR_PATTERNS = (
    re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/]"),
    re.compile(r"(?:^|[\s'\"])(?:/home/|/Users/|file://)"),
    re.compile(r"(?i)\b(?:password|api[_-]?key|secret|username)\s*[:=]"),
)


class IndependentReviewError(RuntimeError):
    """Raised when a review bundle or independent report violates the contract."""


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_hashes(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    result = []
    for path in sorted({item.resolve() for item in paths if item.is_file()}):
        try:
            relative = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        result.append({"path": relative, "sha256": _sha(path), "size_bytes": path.stat().st_size})
    return result


def _declared_identity(root: Path) -> list[str]:
    names = []
    metadata = _read(root / "writing" / "manuscript_metadata.json")
    yaml_path = root / "writing" / "manuscript_metadata.yaml"
    if yaml_path.is_file():
        yaml_payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig"))
        if isinstance(yaml_payload, dict):
            metadata = yaml_payload
    for author in metadata.get("authors") or []:
        if isinstance(author, dict) and author.get("name"):
            name = str(author["name"]).strip()
            if name and "anonymous" not in name.lower():
                names.append(name)
    main = (root / "latex" / "main.tex").read_text(encoding="utf-8-sig", errors="replace")
    for value in re.findall(r"\\author\{([^}]*)\}", main):
        cleaned = re.sub(r"\\\w+\{([^}]*)\}", r"\1", value).strip()
        if cleaned and not any(token in cleaned.lower() for token in ("anonymous", "placeholder", "to be supplied")):
            names.append(cleaned)
    return sorted(set(names))


def _pdf_contains_identity(pdf: Path, identities: list[str]) -> list[str]:
    if not identities:
        return []
    try:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages).lower()
    except Exception:
        return identities
    return [name for name in identities if name.lower() in text]


def _pdf_is_extractable(pdf: Path) -> bool:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf))
        for page in reader.pages:
            page.extract_text()
    except Exception:
        return False
    return True


def _anonymize_review_tex(tex: str) -> str:
    tex = re.sub(
        r"(?m)^\s*\\(?:author|affiliation|email|orcid)\{[^{}]*\}\s*\n?",
        "",
        tex,
    )
    title = re.search(r"\\title\{[^{}]*\}", tex)
    author_block = (
        "\n\\author{Anonymous Manuscript}"
        "\n\\affiliation{Withheld for anonymous review}"
        "\n\\email{withheld@anonymous.invalid}"
    )
    if title:
        tex = tex[:title.end()] + author_block + tex[title.end():]
    tex = re.sub(
        r"\\begin\{acknowledgments\}.*?\\end\{acknowledgments\}",
        "\\\\begin{acknowledgments}\nWithheld for anonymous review.\n\\\\end{acknowledgments}",
        tex,
        flags=re.S,
    )
    tex = re.sub(
        r"\\section\*\{Related Links\}.*?(?=\\bibliographystyle|\\bibliography)",
        "\\\\section*{Related Links}\nWithheld for anonymous review.\n\n",
        tex,
        flags=re.S,
    )
    tex = re.sub(r"https?://github\.com/xiej+h+/Draftpaper(?:\\?_loop)?", "withheld for anonymous review", tex, flags=re.I)
    tex = re.sub(r"(?m)^% Commercial use requires prior written authorization:.*\n?", "", tex)
    tex = tex.replace(r"\graphicspath{{../}}", r"\graphicspath{{../../../}}")
    return tex


def _compile_anonymous_review_pdf(root: Path) -> tuple[Path, list[Path]]:
    source_dir = root / "latex"
    build_dir = root / REVIEW_ROOT / "anonymous_build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    (build_dir / "sections").mkdir(parents=True, exist_ok=True)
    source_main = source_dir / "main.tex"
    main = build_dir / "main.tex"
    main.write_text(_anonymize_review_tex(source_main.read_text(encoding="utf-8-sig")), encoding="utf-8")
    copied_sources = [main]
    for source in (source_dir / "sections").glob("*.tex"):
        target = build_dir / "sections" / source.name
        shutil.copyfile(source, target)
        copied_sources.append(target)
    shutil.copyfile(source_dir / "library.bib", build_dir / "library.bib")

    engine = _find_latex_executable(["xelatex", "xelatex.exe", "pdflatex", "pdflatex.exe"])
    if not engine:
        raise IndependentReviewError("A local LaTeX engine is required to build the anonymous review manuscript.")
    bibtex = _find_latex_executable(["bibtex", "bibtex.exe"])
    _ensure_local_bibstyle_fallback(build_dir, main)
    latex_command = [engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    commands = [latex_command]
    reports: list[str] = []
    index = 0
    while index < len(commands):
        command = commands[index]
        completed = subprocess.run(
            command,
            cwd=build_dir,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            check=False,
        )
        reports.append(
            f"$ {' '.join(command)}\nexit={completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
        if completed.returncode != 0:
            log = build_dir / "main.compile.log"
            log.write_text("\n\n".join(reports), encoding="utf-8")
            raise IndependentReviewError(f"Anonymous review PDF compilation failed. See {log}.")
        if index == 0:
            if bibtex and _aux_requests_bibtex(build_dir / "main.aux"):
                commands.append([bibtex, "main"])
            commands.extend([latex_command, latex_command])
        index += 1
    (build_dir / "main.compile.log").write_text("\n\n".join(reports), encoding="utf-8")
    pdf = build_dir / "main.pdf"
    if not pdf.is_file():
        raise IndependentReviewError("Anonymous review PDF compilation completed without producing main.pdf.")
    return pdf, copied_sources


def _review_reproducibility_files(root: Path, identities: list[str]) -> tuple[list[Path], list[dict[str, str]]]:
    from .reproducibility_bundle import python_dependency_closure, selected_run_roots

    candidates = [root / relative for relative in REPRODUCIBILITY_ALLOWLIST]
    candidates.extend(python_dependency_closure(root, selected_run_roots(root)))
    accepted: list[Path] = []
    excluded: list[dict[str, str]] = []
    lowered_identities = [item.lower() for item in identities if item.strip()]
    for path in sorted({item.resolve() for item in candidates if item.is_file()}):
        relative = path.relative_to(root.resolve()).as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            excluded.append({"path": relative, "reason": "unreadable"})
            continue
        if any(pattern.search(text) for pattern in PRIVATE_LOCATOR_PATTERNS):
            excluded.append({"path": relative, "reason": "private_locator_or_credential_pattern"})
            continue
        lowered = text.lower()
        if any(identity in lowered for identity in lowered_identities):
            excluded.append({"path": relative, "reason": "declared_identity_present"})
            continue
        accepted.append(path)
    return accepted, excluded


def prepare_independent_manuscript_review(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    root = state.path
    pdf = root / "latex" / "main.pdf"
    if not pdf.is_file():
        raise IndependentReviewError("A compiled latex/main.pdf is required before independent review.")
    identities = _declared_identity(root)
    visible = _pdf_contains_identity(pdf, identities)
    if visible:
        if not _pdf_is_extractable(pdf):
            raise IndependentReviewError(
                "The review PDF still contains declared author identity. Compile an anonymized manuscript before preparing the bundle: "
                + ", ".join(visible)
            )
        pdf, anonymous_sources = _compile_anonymous_review_pdf(root)
        remaining = _pdf_contains_identity(pdf, identities)
        if remaining:
            raise IndependentReviewError("Anonymous review build still contains declared identity: " + ", ".join(remaining))
    else:
        anonymous_sources = [root / "latex" / "main.tex", *list((root / "latex" / "sections").glob("*.tex"))]
    latex_sections = list((root / "latex" / "sections").glob("*.tex"))
    from .reproducibility_bundle import selected_result_assets, smoke_dependency_closure

    figures, tables = selected_result_assets(root)
    references = [root / "references" / "reference_registry.json", root / "references" / "library.bib"]
    snapshots = [root / "results" / "promoted_evidence_snapshot.json", root / "core_evidence" / "core_evidence_report.json"]
    reproducibility, excluded_reproducibility = _review_reproducibility_files(root, identities)
    reproducibility_smoke = smoke_dependency_closure(root, reproducibility)
    if reproducibility_smoke.get("decision") != "pass":
        raise IndependentReviewError("The selected-run reproducibility dependency closure failed its compile smoke test.")
    frozen = {
        "manuscript": _relative_hashes(root, [pdf, *anonymous_sources]),
        "figures": _relative_hashes(root, figures),
        "tables": _relative_hashes(root, tables),
        "references": _relative_hashes(root, references),
        "evidence": _relative_hashes(root, snapshots),
        "reproducibility": _relative_hashes(root, reproducibility),
    }
    core = {
        "schema_version": "dpl.independent_review_bundle.v1",
        "project_id_hash": hashlib.sha256(str(state.metadata.get("project_id")).encode()).hexdigest(),
        "submission_anonymized": True,
        "full_manuscript_reviewed": True,
        "real_figures_reviewed": True,
        "baseline_material_prohibited": True,
        "frozen_artifacts": frozen,
        "reviewer_contract": {
            "same_bundle_for_all_reviewers": True,
            "reviewers_cannot_see_other_reports": True,
            "automatic_scores_withheld": True,
            "prior_audits_withheld": True,
            "required_dimensions": sorted(SCORE_DIMENSIONS),
            "required_grounding": ["page", "section", "figure_or_table_when_applicable"],
            "reproducibility_supplement_is_anonymized_and_locator_safe": True,
        },
        "excluded_reproducibility_files": excluded_reproducibility,
        "reproducibility_smoke_test": reproducibility_smoke,
        "selected_run_asset_filtering": True,
    }
    bundle_hash = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    manifest = {
        **core,
        "created_at": utc_now(),
        "bundle_hash": bundle_hash,
        "bundle_hash_semantics": "SHA-256 of the canonical frozen-artifact manifest core; not the ZIP container byte hash.",
        "bundle_zip": BUNDLE_ZIP,
    }
    manifest_path = root / BUNDLE_MANIFEST
    previous = _read(manifest_path)
    previous_hash = str(previous.get("bundle_hash") or "")
    if previous_hash and previous_hash != bundle_hash:
        superseded_root = root / REVIEW_ROOT / "superseded" / previous_hash
        superseded_root.mkdir(parents=True, exist_ok=True)
        for slot in ("reviewer_01", "reviewer_02", "reviewer_03"):
            source = root / REVIEW_ROOT / slot
            if source.exists():
                target = superseded_root / slot
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(source), str(target))
        for relative in (AGGREGATE_JSON, AGGREGATE_MD, EVALUATION_JSON):
            source = root / relative
            if source.exists():
                target = superseded_root / source.name
                shutil.move(str(source), str(target))
    _write(manifest_path, manifest)
    zip_path = root / BUNDLE_ZIP
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(pdf, "manuscript.pdf")
        archive.writestr("bundle_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in figures:
            if path.is_file():
                archive.write(path, "figures/" + path.relative_to(root / "results" / "figures").as_posix())
        for path in tables:
            if path.is_file():
                archive.write(path, "tables/" + path.relative_to(root / "results" / "tables").as_posix())
        for path in reproducibility:
            archive.write(path, "reproducibility/" + path.relative_to(root).as_posix())
    return {
        "status": "prepared",
        "project_path": str(root),
        "bundle_hash": bundle_hash,
        "bundle": BUNDLE_ZIP,
        "manifest": BUNDLE_MANIFEST,
        "reviewer_slots": ["reviewer_01", "reviewer_02"],
        "policy": "Both reviewers inspect this same anonymous generated manuscript. No original manuscript, A/B comparison, quality ratio or unblinding input is permitted.",
    }


def _forbidden_comparison_keys(payload: Any, prefix: str = "") -> list[str]:
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            lowered = str(key).lower()
            if any(token in lowered for token in ("baseline_manuscript", "original_manuscript", "quality_ratio", "a_b_mapping", "unblind")):
                found.append(path)
            found.extend(_forbidden_comparison_keys(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found.extend(_forbidden_comparison_keys(value, f"{prefix}[{index}]"))
    return found


def _review_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Independent Manuscript Review {report['reviewer_anonymous_id']}",
        "",
        f"Recommendation: **{report['overall_recommendation']}**",
        "",
        f"Bundle: `{report['frozen_submission_bundle_hash']}`",
        "",
        "## Findings",
        "",
    ]
    for item in report.get("findings") or []:
        lines.append(f"- **{item.get('severity')}** `{item.get('finding_id')}` at {item.get('locator')}: {item.get('detail')} Required: {item.get('required_action')}")
    lines.extend(["", "## Strengths", "", *[f"- {item}" for item in report.get("strengths") or []], "", "## Weaknesses", "", *[f"- {item}" for item in report.get("weaknesses") or []]])
    return "\n".join(lines) + "\n"


def record_independent_manuscript_review(project: str | Path, reviewer: str, input_path: str | Path) -> dict[str, Any]:
    state = load_project(project)
    manifest = _read(state.path / BUNDLE_MANIFEST)
    if not manifest:
        raise IndependentReviewError("Prepare the frozen independent-review bundle first.")
    slot = str(reviewer).strip().lower()
    if slot not in {"reviewer_01", "reviewer_02", "reviewer_03"}:
        raise IndependentReviewError("Reviewer slot must be reviewer_01, reviewer_02 or reviewer_03.")
    source = Path(input_path).expanduser().resolve()
    report = _read(source)
    if not report:
        raise IndependentReviewError("Independent review input must be a structured JSON object.")
    forbidden = _forbidden_comparison_keys(report)
    if forbidden:
        raise IndependentReviewError("Independent review contains prohibited original/A-B comparison fields: " + ", ".join(forbidden))
    recommendation = str(report.get("overall_recommendation") or "")
    if recommendation not in RECOMMENDATION_ORDER:
        raise IndependentReviewError("Invalid overall_recommendation.")
    if report.get("frozen_submission_bundle_hash") != manifest.get("bundle_hash"):
        raise IndependentReviewError("Review report does not bind the current frozen submission bundle hash.")
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    missing_scores = sorted(SCORE_DIMENSIONS - set(scores))
    if missing_scores:
        raise IndependentReviewError("Review is missing required score dimensions: " + ", ".join(missing_scores))
    for name, value in scores.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise IndependentReviewError(f"Review score is not numeric: {name}") from exc
        if numeric < 0 or numeric > 1:
            raise IndependentReviewError(f"Review score must be in [0,1]: {name}")
    if report.get("checked_real_figures") is not True or report.get("full_manuscript_reviewed") is not True:
        raise IndependentReviewError("Reviewer must confirm the full manuscript and real figures were checked.")
    findings = [item for item in report.get("findings") or [] if isinstance(item, dict)]
    for index, item in enumerate(findings, start=1):
        if item.get("severity") not in {"critical", "major", "minor", "advisory"}:
            raise IndependentReviewError(f"Finding {index} has invalid severity.")
        if not item.get("locator") or not item.get("detail") or not item.get("required_action"):
            raise IndependentReviewError(f"Finding {index} must be page/section/figure grounded with a required action.")
        item.setdefault("finding_id", f"{slot}:{index:03d}")
        item.setdefault("resolution_status", "open")
        item.setdefault("finding_class", "prose_local")
        if item["finding_class"] not in {"prose_local", "reproducibility", "render_only", "analysis_supplement", "claim_downgrade", "new_evidence"}:
            raise IndependentReviewError(f"Finding {index} has invalid finding_class.")
        item.setdefault("affected_claim_ids", [])
        item.setdefault("affected_artifacts", [])
        item.setdefault("requires_new_scientific_run", item["finding_class"] in {"analysis_supplement", "new_evidence"})
        item.setdefault("allowed_repair_scope", item["finding_class"])
        item.setdefault("supersedes_finding_id", None)
        item.setdefault("resolution_evidence", [])
    normalized = {
        "schema_version": "dpl.independent_manuscript_review.v1",
        "reviewer_anonymous_id": slot,
        "independent_session_provider_id_hash": str(report.get("independent_session_provider_id_hash") or ""),
        "frozen_submission_bundle_hash": manifest["bundle_hash"],
        "overall_recommendation": recommendation,
        "scores": {name: float(scores[name]) for name in sorted(SCORE_DIMENSIONS)},
        "findings": findings,
        "strengths": list(report.get("strengths") or []),
        "weaknesses": list(report.get("weaknesses") or []),
        "required_revisions": list(report.get("required_revisions") or []),
        "confidence": report.get("confidence"),
        "checked_real_figures": True,
        "full_manuscript_reviewed": True,
        "recorded_at": utc_now(),
    }
    if not normalized["independent_session_provider_id_hash"]:
        raise IndependentReviewError("An independent session/provider ID hash is required.")
    target = state.path / REVIEW_ROOT / slot
    _write(target / "report.json", normalized)
    (target / "report.md").write_text(_review_markdown(normalized), encoding="utf-8")
    return {"status": "recorded", "reviewer": slot, "report": f"{REVIEW_ROOT}/{slot}/report.json", "bundle_hash": manifest["bundle_hash"]}


def assess_manuscript_quality_release(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    manifest = _read(state.path / BUNDLE_MANIFEST)
    reports = []
    for slot in ("reviewer_01", "reviewer_02"):
        report = _read(state.path / REVIEW_ROOT / slot / "report.json")
        if not report:
            raise IndependentReviewError(f"Missing independent report: {slot}")
        if report.get("frozen_submission_bundle_hash") != manifest.get("bundle_hash"):
            raise IndependentReviewError(f"Reviewer report is stale against the current bundle: {slot}")
        reports.append(report)
    session_hashes = {str(item.get("independent_session_provider_id_hash")) for item in reports}
    if len(session_hashes) != 2:
        raise IndependentReviewError("The two reports must come from distinct independent session/provider IDs.")
    findings = [
        {**item, "reviewer": report["reviewer_anonymous_id"]}
        for report in reports
        for item in report.get("findings") or []
        if isinstance(item, dict)
    ]
    critical = [item for item in findings if item.get("severity") == "critical" and item.get("resolution_status") != "resolved"]
    major = [item for item in findings if item.get("severity") == "major" and item.get("resolution_status") != "resolved"]
    recommendations = [RECOMMENDATION_ORDER[item["overall_recommendation"]] for item in reports]
    recommendation_gap = abs(recommendations[0] - recommendations[1])
    scientific_scores = [float(item["scores"]["scientific_correctness"]) for item in reports]
    adjudication = bool(critical or recommendation_gap >= 2 or abs(scientific_scores[0] - scientific_scores[1]) >= 0.25)
    release_ready = not critical and not major and not adjudication and min(scientific_scores) >= 0.9
    aggregate = {
        "schema_version": "dpl.independent_review_aggregate.v1",
        "status": "passed" if release_ready else "adjudication_required" if adjudication else "revision_required",
        "generated_at": utc_now(),
        "frozen_submission_bundle_hash": manifest.get("bundle_hash"),
        "reviewer_count": 2,
        "reviewer_reports": [f"{REVIEW_ROOT}/{item['reviewer_anonymous_id']}/report.json" for item in reports],
        "recommendations": {item["reviewer_anonymous_id"]: item["overall_recommendation"] for item in reports},
        "score_means": {dimension: sum(float(item["scores"][dimension]) for item in reports) / 2 for dimension in sorted(SCORE_DIMENSIONS)},
        "critical_open_count": len(critical),
        "major_open_count": len(major),
        "reviewer_agreement": {"recommendation_gap": recommendation_gap, "scientific_score_gap": abs(scientific_scores[0] - scientific_scores[1])},
        "adjudication_required": adjudication,
        "release_review_status": "pass" if release_ready else "blocked",
        "revision_queue": findings,
        "relative_quality_ratio_prohibited": True,
        "policy": "This is an absolute audit of one frozen generated manuscript; no original manuscript, A/B mapping, unblinding or relative quality ratio is used.",
    }
    _write(state.path / AGGREGATE_JSON, aggregate)
    _write(state.path / EVALUATION_JSON, aggregate)
    lines = ["# Independent Manuscript Review Aggregate", "", f"Status: **{aggregate['status']}**", "", f"Critical open: {len(critical)}", f"Major open: {len(major)}", "", "## Revision Queue", ""]
    lines.extend(f"- **{item.get('severity')}** [{item.get('reviewer')}] {item.get('locator')}: {item.get('detail')}" for item in findings)
    (state.path / AGGREGATE_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return aggregate
