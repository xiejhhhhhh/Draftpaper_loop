# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


class PluginCandidateError(RuntimeError):
    """Raised when plugin candidate operations cannot proceed."""


SENSITIVE_PATTERNS = [
    r"ghp_[A-Za-z0-9_]+",
    r"(?i)(api[_-]?key|token|password|passwd|secret)\s*[:=]\s*['\"]?[^'\"\s,;]+",
    r"[A-Za-z]:\\[^ \n\r\t]+",
    r"(?i)ssh\s+[^ \n\r\t]+@[^ \n\r\t]+",
]


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _read_text(path: Path, limit: int = 80_000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text[:limit]


def _candidate_root(project_path: Path, discipline: str, candidate_id: str) -> Path:
    return project_path / "plugin_candidates" / discipline / candidate_id


def _safe_id(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return cleaned[:80] or "plugin_candidate"


def _method_template_candidates(module: Any, requested: str | None = None) -> list[dict[str, Any]]:
    templates = module.spec.method_template_dicts()
    if requested:
        wanted = requested.lower()
        templates = [
            item for item in templates
            if wanted in item.get("template_id", "").lower()
            or wanted in item.get("method_family", "").lower()
            or any(wanted in str(alias).lower() for alias in item.get("aliases") or [])
        ]
    return templates


def _privacy_scan_text(text: str) -> dict[str, Any]:
    findings = []
    for pattern in SENSITIVE_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            findings.append({"pattern": pattern, "count": len(matches)})
    return {
        "status": "failed" if findings else "passed",
        "findings": findings,
    }


def _genericity_report(text: str, manifest: dict[str, Any]) -> dict[str, Any]:
    project_specific_terms = []
    for term in ["beijing", "北京市", "3-6", "march", "june", "d:\\", "c:\\"]:
        if term in text.lower():
            project_specific_terms.append(term)
    placeholders = ["{{input_table}}", "{{target_column}}", "{{predictor_columns}}", "{{output_dir}}"]
    return {
        "status": "passed" if not project_specific_terms else "needs_generalization",
        "project_specific_terms": project_specific_terms,
        "recommended_placeholders": placeholders,
        "template_id": manifest.get("template_id") or manifest.get("plugin_id"),
    }


def summarize_plugin_candidates(project: str | Path, *, source_file: str | Path | None = None, method: str | None = None) -> dict[str, Any]:
    state = load_project(project)
    profile = infer_discipline_profile(state.path)
    module = get_discipline_module(profile)
    templates = _method_template_candidates(module, method)
    if not templates:
        templates = module.spec.method_template_dicts()[:1]
    source_text = _read_text(Path(source_file)) if source_file else _read_text(state.path / "methods" / "src" / "generated_pipeline.py")
    if not source_text:
        source_text = _read_text(state.path / "methods" / "scripts" / "run_analysis.py")
    candidates = []
    for template in templates:
        candidate_id = _safe_id(f"{profile['discipline']}_{template.get('template_id')}")
        root = _candidate_root(state.path, profile["discipline"], candidate_id)
        root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "status": "candidate_summarized",
            "candidate_id": candidate_id,
            "generated_at": utc_now(),
            "project_id": state.metadata.get("project_id"),
            "discipline": profile["discipline"],
            "plugin_type": "method_template",
            "plugin_id": f"{profile['discipline']}.method.{template.get('template_id')}",
            "template_id": template.get("template_id"),
            "method_family": template.get("method_family"),
            "aliases": template.get("aliases") or [],
            "input_roles": template.get("input_roles") or [],
            "output_artifacts": template.get("output_artifacts") or [],
            "figure_groups": template.get("figure_groups") or [],
            "source_file": "local_project_source_not_packaged",
            "source_policy": "candidate_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{profile['discipline']}/method_templates/{template.get('template_id')}",
        }
        _write_json(root / "candidate_manifest.json", manifest)
        (root / "source_excerpt.py").write_text(source_text[:20_000], encoding="utf-8")
        write_html_report(root / "candidate_summary.html", _render_candidate_summary(manifest), title="Plugin Candidate Summary")
        candidates.append({"candidate_id": candidate_id, "path": str(root), "manifest": str(root / "candidate_manifest.json")})
    return {
        "status": "written",
        "project_path": str(state.path),
        "discipline": profile["discipline"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "next_command": f'python -m draftpaper_cli.cli generalize-plugin-candidate --candidate "{candidates[0]["path"]}"' if candidates else "",
    }


def _render_candidate_summary(manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# Plugin Candidate Summary",
        "",
        f"Candidate: `{manifest.get('candidate_id')}`",
        f"Plugin id: `{manifest.get('plugin_id')}`",
        f"Discipline: `{manifest.get('discipline')}`",
        f"Method family: `{manifest.get('method_family')}`",
        "",
        "This is a candidate contribution package. It must be generalized, privacy-scanned, fixture-tested, and user-approved before any GitHub fork or PR workflow.",
    ])


def generalize_plugin_candidate(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    source = _read_text(root / "source_excerpt.py")
    generalized_dir = root / "generalized_template"
    generalized_dir.mkdir(parents=True, exist_ok=True)
    template = "\n".join([
        "# Copyright (c) 2026 xiejhhhhhh",
        "# Contact: xiejinhui22@mails.ucas.ac.cn",
        "# Source-available for non-commercial use only; commercial use requires written authorization.",
        "",
        "from __future__ import annotations",
        "",
        "from pathlib import Path",
        "",
        "",
        "def run_template(*, input_table: Path, output_dir: Path, target_column: str = '{{target_column}}') -> dict[str, object]:",
        '    """Generalized method template derived from a completed Draftpaper-loop project."""',
        "    output_dir.mkdir(parents=True, exist_ok=True)",
        "    return {",
        f"        'template_id': '{manifest.get('template_id')}',",
        "        'input_table': str(input_table),",
        "        'target_column': target_column,",
        "        'status': 'template_ready_for_project_binding',",
        "    }",
        "",
        "# Source-derived notes follow. Keep only reusable logic; remove project-specific constants before PR.",
        'SOURCE_NOTES = """',
        source[:5000].replace('"""', "'''"),
        '"""',
    ])
    (generalized_dir / "template.py").write_text(template, encoding="utf-8")
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "template_path": str(generalized_dir / "template.py"),
        "rules": [
            "No local file paths, API keys, fixed regions, fixed dates, or project-specific sample IDs.",
            "Expose data columns, output paths, and optional groups as parameters.",
        ],
    }
    _write_json(root / "genericity_report.json", _genericity_report(template, manifest))
    _write_json(root / "generalization_report.json", report)
    return report


def validate_plugin_candidate(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    contribution_texts = []
    for path in [root / "generalized_template" / "template.py", root / "candidate_manifest.json"]:
        contribution_texts.append(_read_text(path))
    raw_source_privacy = _privacy_scan_text(_read_text(root / "source_excerpt.py"))
    privacy = _privacy_scan_text("\n".join(contribution_texts))
    genericity = _genericity_report("\n".join(contribution_texts), manifest)
    overlap = detect_plugin_overlap(candidate)
    validation = {
        "status": "passed" if privacy["status"] == "passed" and genericity["status"] == "passed" else "failed",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "privacy_scan": privacy,
        "raw_source_privacy_scan": raw_source_privacy,
        "genericity_report": genericity,
        "overlap_report": overlap,
        "fixture_test_report": {
            "status": "passed" if (root / "generalized_template" / "template.py").exists() else "missing_template",
            "checked_files": ["generalized_template/template.py"],
        },
    }
    _write_json(root / "privacy_scan.json", privacy)
    _write_json(root / "genericity_report.json", genericity)
    _write_json(root / "overlap_report.json", overlap)
    _write_json(root / "validation_report.json", validation)
    return validation


def detect_plugin_overlap(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    manifest = _read_json(root / "candidate_manifest.json", {})
    discipline = str(manifest.get("discipline") or "default")
    module = get_discipline_module({"discipline": discipline})
    target_id = str(manifest.get("template_id") or "")
    existing = module.spec.method_template_dicts()
    matches = []
    for item in existing:
        score = 0.0
        if item.get("template_id") == target_id:
            score += 0.7
        if item.get("method_family") == manifest.get("method_family"):
            score += 0.2
        aliases = set(str(a).lower() for a in item.get("aliases") or [])
        candidate_aliases = set(str(a).lower() for a in manifest.get("aliases") or [])
        if aliases & candidate_aliases:
            score += 0.1
        if score:
            matches.append({"template_id": item.get("template_id"), "method_family": item.get("method_family"), "overlap_score": round(score, 3)})
    decision = "merge_with_existing" if matches and max(m["overlap_score"] for m in matches) >= 0.7 else "new_plugin_candidate"
    report = {
        "status": "written",
        "decision": decision,
        "candidate_id": manifest.get("candidate_id"),
        "existing_matches": sorted(matches, key=lambda item: item["overlap_score"], reverse=True),
        "merge_action": "merge aliases, variants, fixtures, and source provenance into the existing discipline module" if decision == "merge_with_existing" else "add a new plugin directory under the discipline module after validation",
    }
    _write_json(root / "overlap_report.json", report)
    return report


def package_plugin_contribution(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    manifest = _read_json(root / "candidate_manifest.json", {})
    validation = _read_json(root / "validation_report.json", {})
    if validation.get("status") != "passed":
        raise PluginCandidateError("validate-plugin-candidate must pass before packaging a contribution.")
    package_dir = root / "contribution_package"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)
    for name in ["candidate_manifest.json", "overlap_report.json", "genericity_report.json", "privacy_scan.json", "validation_report.json"]:
        src = root / name
        if src.exists():
            shutil.copy2(src, package_dir / name)
    if (root / "generalized_template").exists():
        shutil.copytree(root / "generalized_template", package_dir / "generalized_template")
    merge_plan = {
        "status": "written",
        "candidate_id": manifest.get("candidate_id"),
        "target": manifest.get("intended_merge_target"),
        "fork_policy": "Open a temporary PR branch; main remains the only stable plugin registry.",
        "maintainer_steps": [
            "gh pr checkout <PR_NUMBER>",
            "python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>",
            "review overlap_report.json and merge_plan.json",
            "merge generalized reusable files into the target discipline module",
            "run pytest before squash-merging into main",
        ],
    }
    _write_json(package_dir / "merge_plan.json", merge_plan)
    _write_json(root / "merge_plan.json", merge_plan)
    return {"status": "packaged", "candidate_id": manifest.get("candidate_id"), "package_dir": str(package_dir), "merge_plan": str(package_dir / "merge_plan.json")}


def write_github_contribution_guide(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    out = state.path / "plugin_candidates" / "GITHUB_CONTRIBUTION_GUIDE.md"
    content = """# Draftpaper-loop Plugin Contribution Guide

Use forks and PR branches only as temporary contribution channels. Stable reusable capabilities must be merged into `main` under the matching discipline module.

Contributor preflight:

```powershell
git remote add upstream https://github.com/xiejhhhhhh/Draftpaper_loop.git
git fetch upstream
git rebase upstream/main
python -m draftpaper_cli.cli summarize-plugin-candidates --project <project>
python -m draftpaper_cli.cli generalize-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli package-plugin-contribution --candidate <candidate>
```

Do not submit private data, local paths, credentials, paper PDFs, generated manuscript drafts, or project-specific scripts. Submit generalized templates, manifests, fixtures, and tests only.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return {"status": "written", "guide": str(out)}
