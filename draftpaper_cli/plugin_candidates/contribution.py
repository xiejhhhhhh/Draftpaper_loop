# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from ..discipline import infer_discipline_from_text, infer_discipline_profile
from ..discipline_modules import get_discipline_module
from ..html_utils import write_html_report
from ..project_scaffold import _write_json, utc_now
from ..project_state import load_project
from ..safe_fetch import SafeFetchError, fetch_text

from .common import (
    PluginCandidateError,
    _privacy_scan_text,
    _read_json,
    _read_text,
)

from .promotion import (
    _support_backflow_provenance,
)

def _render_contribution_provenance(provenance: dict[str, Any]) -> str:
    return "\n".join([
        "# Contribution Provenance and Backflow",
        "",
        f"Candidate: `{provenance.get('candidate_id')}`",
        f"Plugin type: `{provenance.get('plugin_type')}`",
        f"Source skill: `{provenance.get('source')}:{provenance.get('source_skill_id')}`",
        "",
        "## Support Routes",
        *[f"- `{route}`" for route in (provenance.get("backflow_from_support_routes") or [])],
        "",
        "## Support Candidates",
        *[
            f"- `{item.get('candidate_id')}` ({item.get('support_type')}) -> {item.get('intended_support_target')}"
            for item in (provenance.get("support_candidates") or [])
        ],
        "",
        "## Review Rule Backflow Signal Scan",
        *[
            f"- `{item.get('candidate_id')}` eligible families: "
            f"{', '.join((item.get('backflow_signal_scan') or {}).get('eligible_rule_families') or []) or 'none'}"
            for item in (provenance.get("support_candidates") or [])
        ],
        "",
        "This package includes metadata-only provenance. It intentionally excludes source evidence summaries, third-party source code, private files, credentials, PDFs, and project-specific artifacts.",
    ])


def _render_contribution_preflight_actions() -> str:
    return "\n".join([
        "# GitHub Actions Preflight",
        "",
        "Use this snippet in a PR workflow to check packaged plugin contributions before maintainer review.",
        "It validates the contribution package itself and does not read third-party source text.",
        "",
        "```yaml",
        "name: Draftpaper plugin contribution preflight",
        "on: [pull_request]",
        "jobs:",
        "  plugin-preflight:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        "      - uses: actions/setup-python@v5",
        "        with:",
        "          python-version: '3.11'",
        "      - run: python -m pip install -e .",
        "      - run: python -m draftpaper_cli.cli preflight-plugin-contribution --package <path-to-contribution_package>",
        "```",
        "",
        "The package must contain only metadata, generalized templates, fixtures, validation reports, and provenance/backflow summaries.",
    ])


def _render_contributor_checklist(manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# Plugin Contribution Checklist",
        "",
        f"Candidate: `{manifest.get('candidate_id')}`",
        f"Plugin type: `{manifest.get('plugin_type')}`",
        f"Target: `{manifest.get('intended_merge_target')}`",
        "",
        "Before opening a PR:",
        "",
        "- Run `generalize-plugin-candidate` and `validate-plugin-candidate` locally.",
        "- Run `package-plugin-contribution` and then `preflight-plugin-contribution` on the generated package.",
        "- Confirm the package contains no third-party skill text, source excerpts, PDFs, private data, local paths, server names, credentials, or generated manuscript drafts.",
        "- Confirm support-layer candidates are not submitted as formal discipline plugins; submit validated backflow candidates instead.",
        "- Confirm any fixed threshold has a journal guideline, discipline convention, or benchmark source. Otherwise keep it contextual, comparative, or human-confirmed.",
        "- Confirm normal, failure, and boundary fixtures are small, public, credential-free, and CI-suitable before requesting promotion beyond candidate/foundation maturity.",
    ])


def package_plugin_contribution(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    if (root / "support_manifest.json").exists():
        raise PluginCandidateError("Support candidates cannot be packaged as formal discipline plugin contributions; package their validated formal backflow candidates instead.")
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
    for name in ["rule_rationale.md", "positive_fixture.json", "negative_fixture.json", "provenance_summary.json"]:
        src = root / name
        if src.exists():
            shutil.copy2(src, package_dir / name)
    if (root / "generalized_template").exists():
        shutil.copytree(root / "generalized_template", package_dir / "generalized_template")
    provenance = _support_backflow_provenance(root, manifest)
    _write_json(package_dir / "PROVENANCE_AND_BACKFLOW.json", provenance)
    (package_dir / "PROVENANCE_AND_BACKFLOW.md").write_text(_render_contribution_provenance(provenance), encoding="utf-8")
    (package_dir / "CONTRIBUTOR_CHECKLIST.md").write_text(_render_contributor_checklist(manifest), encoding="utf-8")
    (package_dir / "GITHUB_ACTIONS_PREFLIGHT.md").write_text(_render_contribution_preflight_actions(), encoding="utf-8")
    merge_plan = {
        "status": "written",
        "candidate_id": manifest.get("candidate_id"),
        "target": manifest.get("intended_merge_target"),
        "fork_policy": "Open a temporary PR branch; main remains the only stable plugin registry.",
        "source_policy": "Only metadata, generalized templates, validation reports, and provenance/backflow summaries are packaged. Third-party source text and source_evidence_summary.md are excluded.",
        "provenance": "PROVENANCE_AND_BACKFLOW.json",
        "maintainer_steps": [
            "gh pr checkout <PR_NUMBER>",
            "python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>",
            "review overlap_report.json and merge_plan.json",
            "review PROVENANCE_AND_BACKFLOW.json to confirm support-skill backflow and source policy",
            "run review-plugin-contribution to generate a read-only maintainer review report",
            "merge generalized reusable files into the target discipline module",
            "run pytest before squash-merging into main",
        ],
    }
    _write_json(package_dir / "merge_plan.json", merge_plan)
    _write_json(root / "merge_plan.json", merge_plan)
    return {"status": "packaged", "candidate_id": manifest.get("candidate_id"), "package_dir": str(package_dir), "merge_plan": str(package_dir / "merge_plan.json")}


def _resolve_contribution_package_root(package: str | Path) -> tuple[Path, Path]:
    requested_root = Path(package).resolve()
    root = requested_root
    if not root.exists() or not root.is_dir():
        raise PluginCandidateError(f"Missing contribution package directory: {root}")
    if not (root / "candidate_manifest.json").exists():
        if (root / "contribution_package" / "candidate_manifest.json").exists():
            root = root / "contribution_package"
        elif root.name == "generalized_template" and (root.parent / "candidate_manifest.json").exists():
            root = root.parent
    return requested_root, root


def preflight_plugin_contribution_package(package: str | Path) -> dict[str, Any]:
    """Validate a packaged contribution before GitHub PR review.

    This checks the package boundary, not the original third-party skill source.
    It is intended for contributor-side preflight and GitHub Actions.
    """

    requested_root, root = _resolve_contribution_package_root(package)
    stale_report = root / "PLUGIN_CONTRIBUTION_PREFLIGHT.json"
    if stale_report.exists():
        stale_report.unlink()

    required_files = [
        "candidate_manifest.json",
        "validation_report.json",
        "PROVENANCE_AND_BACKFLOW.json",
        "merge_plan.json",
        "genericity_report.json",
        "privacy_scan.json",
    ]
    missing_files = [name for name in required_files if not (root / name).exists()]
    forbidden_names = {
        "source_evidence_summary.md",
        "source_excerpt.md",
        "source_excerpt.py",
        "SKILL.md",
        "paper.pdf",
        "main.pdf",
        "main.tex",
    }
    forbidden_suffixes = {".pdf", ".docx", ".zip", ".7z", ".tar", ".gz", ".pt", ".pth", ".ckpt", ".pkl"}
    forbidden_paths = []
    text_chunks = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        lowered = path.name.lower()
        if lowered in {item.lower() for item in forbidden_names} or path.suffix.lower() in forbidden_suffixes:
            forbidden_paths.append(rel)
        if path.suffix.lower() in {".json", ".md", ".py", ".txt", ".yaml", ".yml"}:
            text_chunks.append(_read_text(path, limit=50_000))

    manifest = _read_json(root / "candidate_manifest.json", {})
    validation = _read_json(root / "validation_report.json", {})
    provenance = _read_json(root / "PROVENANCE_AND_BACKFLOW.json", {})
    merge_plan = _read_json(root / "merge_plan.json", {})
    plugin_type = str(manifest.get("plugin_type") or "")
    allowed_types = {"data_connector", "method_template", "review_rule"}
    generalized_dir = root / "generalized_template"
    expected_generalized = {
        "data_connector": generalized_dir / "data_connector.json",
        "method_template": generalized_dir / "method_template.json",
        "review_rule": generalized_dir / "review_rule.json",
    }
    generalized_missing = []
    if plugin_type in expected_generalized and not expected_generalized[plugin_type].exists():
        generalized_missing.append(str(expected_generalized[plugin_type].relative_to(root).as_posix()))
    if not (generalized_dir / "template.py").exists():
        generalized_missing.append("generalized_template/template.py")

    privacy = _privacy_scan_text("\n".join(text_chunks))
    problems: list[str] = []
    if missing_files:
        problems.append("missing_required_files")
    if forbidden_paths:
        problems.append("forbidden_source_or_binary_files")
    if plugin_type not in allowed_types:
        problems.append("unsupported_or_support_layer_plugin_type")
    if validation.get("status") != "passed":
        problems.append("candidate_validation_not_passed")
    if privacy.get("status") != "passed":
        problems.append("privacy_or_secret_scan_failed")
    if generalized_missing:
        problems.append("missing_generalized_template_files")
    if "metadata_only" not in str(provenance.get("source_policy") or ""):
        problems.append("provenance_source_policy_not_metadata_only")
    if "discipline_modules" not in str(merge_plan.get("target") or manifest.get("intended_merge_target") or ""):
        problems.append("merge_target_not_formal_discipline_module")
    if manifest.get("source_policy") != "candidate_only_no_direct_upload":
        problems.append("candidate_source_policy_not_candidate_only")

    preflight = {
        "status": "passed" if not problems else "failed",
        "generated_at": utc_now(),
        "requested_package_dir": str(requested_root),
        "resolved_package_dir": str(root),
        "package_dir": root.name,
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": plugin_type,
        "problems": problems,
        "missing_files": missing_files,
        "forbidden_paths": forbidden_paths,
        "generalized_missing": generalized_missing,
        "privacy_scan": privacy,
        "validation_status": validation.get("status"),
        "promotion_allowed_by_preflight": False,
        "policy": "Preflight verifies package safety and reviewability only; promotion still requires maintainer review and explicit human confirmation.",
    }
    _write_json(root / "PLUGIN_CONTRIBUTION_PREFLIGHT.json", preflight)
    return preflight


def _render_plugin_contribution_review(review: dict[str, Any]) -> str:
    lines = [
        "# Plugin Contribution Maintainer Review",
        "",
        f"- Status: `{review.get('status')}`",
        f"- Recommendation: `{review.get('maintainer_recommendation')}`",
        f"- Candidate: `{review.get('candidate_id')}`",
        f"- Plugin type: `{review.get('plugin_type')}`",
        f"- Discipline: `{review.get('discipline')}`",
        f"- Target: `{review.get('target')}`",
        "",
        "## Preflight",
        "",
        f"- Preflight status: `{review.get('preflight_status')}`",
        f"- Problems: {', '.join(review.get('preflight_problems') or []) or 'none'}",
        "",
        "## Source And Backflow",
        "",
        f"- Source policy: {review.get('source_policy') or 'not declared'}",
        f"- Metadata-only source: `{review.get('metadata_only_source')}`",
        f"- Backflow from support routes: {', '.join(review.get('backflow_from_support_routes') or []) or 'none'}",
        f"- Backflow rule families: {', '.join(review.get('backflow_rule_families') or []) or 'none'}",
        "",
        "## Threshold And Review Policy",
        "",
        f"- Threshold mode: `{review.get('threshold_mode')}`",
        f"- Threshold source: `{review.get('threshold_source_type')}`",
        f"- Threshold validation status: `{review.get('threshold_validation_status')}`",
        f"- Human confirmation required: `{review.get('human_confirmation_required')}`",
        f"- Blocking level: `{review.get('blocking_level')}`",
        f"- Failure route: `{review.get('failure_route')}`",
        "",
        "## Files To Review",
        "",
    ]
    for item in review.get("files_to_review") or []:
        lines.append(f"- `{item}`")
    if not review.get("files_to_review"):
        lines.append("- none")
    lines.extend([
        "",
        "## Maintainer Notes",
        "",
    ])
    for note in review.get("maintainer_notes") or []:
        lines.append(f"- {note}")
    if not review.get("maintainer_notes"):
        lines.append("- No additional notes.")
    lines.extend([
        "",
        "## Next Steps",
        "",
    ])
    for step in review.get("next_steps") or []:
        lines.append(f"- {step}")
    if not review.get("next_steps"):
        lines.append("- No next steps recorded.")
    return "\n".join(lines) + "\n"


def review_plugin_contribution_package(package: str | Path) -> dict[str, Any]:
    """Create a read-only maintainer review report for a packaged contribution."""

    requested_root, root = _resolve_contribution_package_root(package)
    preflight = preflight_plugin_contribution_package(root)
    manifest = _read_json(root / "candidate_manifest.json", {})
    validation = _read_json(root / "validation_report.json", {})
    provenance = _read_json(root / "PROVENANCE_AND_BACKFLOW.json", {})
    merge_plan = _read_json(root / "merge_plan.json", {})
    genericity = _read_json(root / "genericity_report.json", {})
    privacy = _read_json(root / "privacy_scan.json", {})

    plugin_type = str(manifest.get("plugin_type") or "")
    threshold_policy = manifest.get("threshold_policy") if isinstance(manifest.get("threshold_policy"), dict) else {}
    threshold_source = manifest.get("threshold_source") if isinstance(manifest.get("threshold_source"), dict) else {}
    backflow_routes = provenance.get("backflow_from_support_routes") or []
    support_candidates = provenance.get("support_candidates") if isinstance(provenance.get("support_candidates"), list) else []
    backflow_families: set[str] = set()
    for item in support_candidates:
        if not isinstance(item, dict):
            continue
        scan = item.get("backflow_signal_scan") if isinstance(item.get("backflow_signal_scan"), dict) else {}
        for family in scan.get("families") or item.get("review_rule_backflow_scope") or []:
            backflow_families.add(str(family))
    if manifest.get("rule_family"):
        backflow_families.add(str(manifest.get("rule_family")))

    files_to_review = [
        name for name in [
            "candidate_manifest.json",
            "validation_report.json",
            "PROVENANCE_AND_BACKFLOW.json",
            "merge_plan.json",
            "genericity_report.json",
            "privacy_scan.json",
            "rule_rationale.md" if plugin_type == "review_rule" else "",
            "positive_fixture.json" if plugin_type == "review_rule" else "",
            "negative_fixture.json" if plugin_type == "review_rule" else "",
            f"generalized_template/{plugin_type}.json" if plugin_type else "",
            "generalized_template/template.py",
        ]
        if name and (root / name).exists()
    ]

    notes: list[str] = []
    if plugin_type == "review_rule":
        notes.append("Review the rule family, evidence binding, failure route, and threshold policy before any promotion.")
    if backflow_routes:
        notes.append("This candidate includes support-layer backflow; confirm workflow/paper/shared skill content was generalized into a formal rule rather than copied.")
    if threshold_policy.get("mode") in {"fixed", "journal_guided"}:
        notes.append("Confirm the threshold source is a journal guideline, public benchmark, discipline convention, or explicit human confirmation.")
    elif plugin_type == "review_rule":
        notes.append("Contextual or comparative thresholds should remain advisory until they are evidence-bound in a paper workflow.")
    if preflight.get("status") != "passed":
        notes.append("Preflight failed; do not review for merge until the package boundary problems are fixed.")
    if privacy.get("status") and privacy.get("status") != "passed":
        notes.append("Privacy scan is not clean; inspect all flagged paths before continuing.")
    if genericity.get("status") and genericity.get("status") != "passed":
        notes.append("Genericity report is not clean; require a more reusable template or fixture boundary.")

    if preflight.get("status") != "passed":
        recommendation = "fix_required"
    elif plugin_type not in {"data_connector", "method_template", "review_rule"}:
        recommendation = "reject_support_layer_or_unsafe"
    elif manifest.get("source_policy") != "candidate_only_no_direct_upload":
        recommendation = "fix_required"
    else:
        recommendation = "ready_for_human_review"

    next_steps = [
        "Review the listed files without opening or copying third-party source repositories into the public tree.",
        "Confirm overlap and aliases before merging to avoid duplicate discipline plugins.",
        "Run validate-plugin-candidate and the relevant discipline regression tests before promotion.",
    ]
    if plugin_type == "review_rule":
        next_steps.append("Confirm the rule can bind to Scientific Evidence Registry records before enabling any blocking behavior.")
    if recommendation == "fix_required":
        next_steps.insert(0, "Ask the contributor to fix the preflight or package-policy problems before maintainer review.")

    review = {
        "status": "written",
        "generated_at": utc_now(),
        "requested_package_dir": str(requested_root),
        "resolved_package_dir": str(root),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": plugin_type,
        "discipline": manifest.get("discipline") or manifest.get("primary_discipline"),
        "target": merge_plan.get("target") or manifest.get("intended_merge_target"),
        "preflight_status": preflight.get("status"),
        "preflight_problems": preflight.get("problems") or [],
        "validation_status": validation.get("status"),
        "source_policy": provenance.get("source_policy") or manifest.get("source_policy"),
        "metadata_only_source": "metadata_only" in str(provenance.get("source_policy") or ""),
        "backflow_from_support_routes": sorted(str(item) for item in backflow_routes),
        "backflow_rule_families": sorted(backflow_families),
        "threshold_mode": threshold_policy.get("mode"),
        "threshold_source_type": threshold_source.get("type"),
        "threshold_validation_status": manifest.get("threshold_validation_status"),
        "human_confirmation_required": bool(manifest.get("human_confirmation_required")),
        "blocking_level": manifest.get("blocking_level"),
        "failure_route": manifest.get("failure_route"),
        "files_to_review": files_to_review,
        "maintainer_notes": notes,
        "maintainer_recommendation": recommendation,
        "next_steps": next_steps,
        "policy": "Read-only maintainer review. This report never promotes, copies, or vendors third-party source files.",
    }
    _write_json(root / "PLUGIN_CONTRIBUTION_REVIEW.json", review)
    (root / "PLUGIN_CONTRIBUTION_REVIEW.md").write_text(_render_plugin_contribution_review(review), encoding="utf-8")
    return review


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
python -m draftpaper_cli.cli extract-skill-capabilities --source-file <SKILL.md> --source local_skill --discipline auto --output-root <out>
python -m draftpaper_cli.cli compile-skill-source --source-root <skills_or_project_docs> --source local_skill --discipline auto --output-root <compiled>
python -m draftpaper_cli.cli summarize-plugin-candidates --project <project>
python -m draftpaper_cli.cli generalize-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli validate-plugin-candidate --candidate <candidate>
python -m draftpaper_cli.cli package-plugin-contribution --candidate <candidate>
python -m draftpaper_cli.cli preflight-plugin-contribution --package <candidate>/contribution_package
python -m draftpaper_cli.cli review-plugin-contribution --package <candidate>/contribution_package
python -m draftpaper_cli.cli promote-plugin-candidate --candidate <candidate> --require-human-confirmation --dry-run
```

Formal discipline plugin PRs can include only validated `data_connector`, `method_template`, or `review_rule` candidates. `workflow_recipe`, `paper_contract`, and `shared_capability` outputs are support-layer candidates: keep them as provenance/backflow records, and submit the extracted formal backflow candidates instead.

For review rules, include `rule_rationale.md`, `positive_fixture.json`, `negative_fixture.json`, `provenance_summary.json`, and `PROVENANCE_AND_BACKFLOW.json`. A review rule should describe the evidence role it checks, the pipeline hooks where it applies, the failure route, and whether any threshold is contextual, comparative, journal-guided, or human-confirmed.

Do not submit private data, local paths, credentials, paper PDFs, generated manuscript drafts, or project-specific scripts. Submit generalized templates, manifests, fixtures, preflight reports, and tests only.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return {"status": "written", "guide": str(out)}
