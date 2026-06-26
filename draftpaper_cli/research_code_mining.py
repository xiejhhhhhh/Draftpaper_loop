# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
import csv
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now


class ResearchCodeMiningError(RuntimeError):
    """Raised when research-code mining cannot produce a reviewable report."""


PERMISSIVE_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"}
COPYLEFT_LICENSES = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}


def discover_research_repos(
    *,
    output_root: str | Path,
    discipline: str,
    query: str,
    from_json: str | Path | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Write a normalized repository candidate list from offline metadata.

    The minimum implementation is intentionally metadata-only. It can consume a
    GitHub-search export later, but it does not clone repositories or copy code.
    """
    if not discipline.strip():
        raise ResearchCodeMiningError("discipline is required")
    if not query.strip():
        raise ResearchCodeMiningError("query is required")

    root = _mining_root(output_root)
    repositories = _load_seed_repositories(from_json, discipline=discipline, query=query)
    normalized = [
        _normalize_repo(item, discipline=discipline, query=query)
        for item in repositories[: max(1, limit)]
    ]
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "discipline": discipline,
        "query": query,
        "source": str(from_json) if from_json else "built_in_seed_metadata",
        "repo_count": len(normalized),
        "repositories": normalized,
    }
    out = root / f"{_safe_id(discipline)}_repo_candidates.json"
    _write_json(out, payload)
    write_html_report(root / f"{_safe_id(discipline)}_repo_candidates.html", _render_discovery_report(payload), title="Research Repository Discovery")
    return {
        "status": "written",
        "discipline": discipline,
        "query": query,
        "repo_count": len(normalized),
        "output_file": str(out),
        "html_report": str(root / f"{_safe_id(discipline)}_repo_candidates.html"),
    }


def score_research_repos(*, input_file: str | Path, output_root: str | Path | None = None) -> dict[str, Any]:
    """Rank discovered repositories by reuse value and license safety."""
    source = Path(input_file)
    payload = _read_json(source)
    repositories = payload.get("repositories") or []
    if not isinstance(repositories, list):
        raise ResearchCodeMiningError(f"Invalid repository list: {source}")

    ranked = []
    for repo in repositories:
        if isinstance(repo, dict):
            scored = dict(repo)
            score_detail = _score_repo(scored)
            scored.update(score_detail)
            ranked.append(scored)
    ranked.sort(key=lambda item: (item.get("score", 0), item.get("stargazers_count", 0)), reverse=True)

    root = _mining_root(output_root or source.parent)
    out = root / f"{_safe_id(payload.get('discipline') or 'research')}_scored_repos.json"
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "discipline": payload.get("discipline"),
        "query": payload.get("query"),
        "input_file": str(source),
        "repo_count": len(ranked),
        "repositories": ranked,
    }
    _write_json(out, report)
    write_html_report(root / f"{_safe_id(payload.get('discipline') or 'research')}_scored_repos.html", _render_score_report(report), title="Research Repository Scores")
    return {
        "status": "written",
        "repo_count": len(ranked),
        "output_file": str(out),
        "html_report": str(root / f"{_safe_id(payload.get('discipline') or 'research')}_scored_repos.html"),
    }


def extract_plugin_candidates(*, input_file: str | Path, output_root: str | Path | None = None, top_n: int = 5) -> dict[str, Any]:
    """Create metadata-only plugin candidate reports from scored repositories."""
    source = Path(input_file)
    payload = _read_json(source)
    repositories = payload.get("repositories") or []
    if not isinstance(repositories, list):
        raise ResearchCodeMiningError(f"Invalid scored repository list: {source}")

    root = _mining_root(output_root or source.parent)
    discipline = str(payload.get("discipline") or "default")
    candidate_dirs: list[str] = []
    manifests = []
    for repo in repositories[: max(1, top_n)]:
        if not isinstance(repo, dict):
            continue
        candidate_id = _safe_id(f"{discipline}_{repo.get('full_name') or repo.get('name') or 'repo'}")
        candidate_root = root / "plugin_candidates" / _safe_id(discipline) / candidate_id
        candidate_root.mkdir(parents=True, exist_ok=True)
        manifest = _build_candidate_manifest(repo, discipline=discipline, candidate_id=candidate_id)
        _write_json(candidate_root / "candidate_manifest.json", manifest)
        write_html_report(candidate_root / "candidate_report.html", _render_candidate_report(manifest), title="Mined Plugin Candidate")
        candidate_dirs.append(str(candidate_root))
        manifests.append({"candidate_id": candidate_id, "path": str(candidate_root), "manifest": str(candidate_root / "candidate_manifest.json")})

    index = {
        "status": "written",
        "generated_at": utc_now(),
        "discipline": discipline,
        "input_file": str(source),
        "candidate_count": len(candidate_dirs),
        "candidates": manifests,
    }
    index_json = root / "plugin_candidates" / _safe_id(discipline) / "index.json"
    index_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(index_json, index)
    index_html = index_json.with_suffix(".html")
    write_html_report(index_html, _render_candidate_index(index), title="Mined Plugin Candidate Index")
    return {
        "status": "written",
        "candidate_count": len(candidate_dirs),
        "candidate_dirs": candidate_dirs,
        "index_json": str(index_json),
        "index_html": str(index_html),
    }


def inspect_research_repo(
    *,
    candidate: str | Path,
    local_repo: str | Path,
    output_root: str | Path | None = None,
    mode: str = "tree",
) -> dict[str, Any]:
    """Inspect a local checkout structure without copying repository source."""
    candidate_path = _candidate_manifest_path(candidate)
    manifest = _read_json(candidate_path)
    repo_path = Path(local_repo).expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise ResearchCodeMiningError(f"local_repo must be an existing directory: {repo_path}")
    if mode not in {"tree", "docs", "tree_docs"}:
        raise ResearchCodeMiningError("mode must be one of: tree, docs, tree_docs")

    root = _mining_root(output_root or candidate_path.parent)
    candidate_id = str(manifest.get("candidate_id") or _safe_id(repo_path.name))
    inspection_dir = root / "inspections" / candidate_id
    inspection_dir.mkdir(parents=True, exist_ok=True)
    files = _inventory_repository_files(repo_path)
    docs = _read_repo_docs(repo_path) if mode in {"docs", "tree_docs"} else _read_repo_docs(repo_path, metadata_only=True)
    package_manifest = _package_manifest(repo_path, files)
    source = manifest.get("source_repository") or {}
    structure = {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": candidate_id,
        "discipline": manifest.get("discipline") or "default",
        "source_repository": source,
        "local_repo_name": repo_path.name,
        "source_policy": "structure_and_docs_only_no_source_copy",
        "mode": mode,
        "file_count": len(files),
        "files": files,
        "docs": docs,
        "package_manifest": package_manifest,
    }
    structure_path = inspection_dir / "repository_structure.json"
    inventory_path = inspection_dir / "file_inventory.csv"
    package_path = inspection_dir / "package_manifest.json"
    _write_json(structure_path, structure)
    _write_file_inventory_csv(inventory_path, files)
    _write_json(package_path, package_manifest)
    write_html_report(inspection_dir / "repository_structure.html", _render_inspection_report(structure), title="Repository Structure Inspection")
    return {
        "status": "written",
        "inspection_dir": str(inspection_dir),
        "repository_structure": str(structure_path),
        "file_inventory": str(inventory_path),
        "package_manifest": str(package_path),
        "html_report": str(inspection_dir / "repository_structure.html"),
    }


def map_repository_workflow(*, inspection_file: str | Path, output_root: str | Path | None = None) -> dict[str, Any]:
    """Map a repository structure inspection to reusable workflow roles."""
    source = Path(inspection_file)
    inspection = _read_json(source)
    root = _mining_root(output_root or source.parent)
    candidate_id = str(inspection.get("candidate_id") or "candidate")
    workflow_dir = root / "workflow_maps" / candidate_id
    workflow_dir.mkdir(parents=True, exist_ok=True)
    role_map: dict[str, list[dict[str, Any]]] = {}
    for item in inspection.get("files") or []:
        if not isinstance(item, dict):
            continue
        for role in item.get("roles") or []:
            role_map.setdefault(str(role), []).append({
                "path": item.get("path"),
                "kind": item.get("kind"),
                "evidence": item.get("evidence") or [],
            })
    workflow = {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": candidate_id,
        "discipline": inspection.get("discipline") or "default",
        "source_policy": "workflow_mapping_only_no_source_copy",
        "workflow_roles": sorted(role_map),
        "role_map": role_map,
        "candidate_capabilities": _capabilities_from_role_map(role_map),
        "recommended_plugin_targets": _recommended_targets_from_roles(str(inspection.get("discipline") or "default"), role_map),
    }
    out = workflow_dir / "workflow_map.json"
    _write_json(out, workflow)
    write_html_report(workflow_dir / "workflow_map.html", _render_workflow_report(workflow), title="Repository Workflow Map")
    return {
        "status": "written",
        "workflow_map": str(out),
        "html_report": str(workflow_dir / "workflow_map.html"),
        "workflow_roles": workflow["workflow_roles"],
    }


def bootstrap_discipline_foundation(*, workflow_map: str | Path, output_root: str | Path | None = None) -> dict[str, Any]:
    """Write candidate-only discipline foundation suggestions from a workflow map."""
    source = Path(workflow_map)
    workflow = _read_json(source)
    discipline = str(workflow.get("discipline") or "default")
    root = _mining_root(output_root or source.parent)
    out_dir = root / "foundation_candidates" / _safe_id(discipline)
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = workflow.get("recommended_plugin_targets") or {}
    foundation = {
        "status": "foundation_candidate_written",
        "generated_at": utc_now(),
        "discipline": discipline,
        "source_workflow_map": str(source),
        "merge_policy": "candidate_only_do_not_modify_formal_module",
        "data_connector_candidates": targets.get("data_connectors") or _fallback_foundation_items(discipline, "data"),
        "method_template_candidates": targets.get("method_templates") or _fallback_foundation_items(discipline, "method"),
        "review_rule_candidates": targets.get("review_rules") or _fallback_foundation_items(discipline, "review"),
        "next_steps": [
            "Review candidate roles against high-quality papers and domain standards.",
            "Generalize only reusable interfaces and fixtures; do not copy source implementation.",
            "Promote to formal discipline module only after tests and maintainer review.",
        ],
    }
    out = out_dir / f"{_safe_id(workflow.get('candidate_id') or discipline)}_foundation_candidate.json"
    _write_json(out, foundation)
    write_html_report(out.with_suffix(".html"), _render_foundation_report(foundation), title="Discipline Foundation Candidate")
    return {
        "status": "written",
        "foundation_candidate": str(out),
        "html_report": str(out.with_suffix(".html")),
    }


def _mining_root(output_root: str | Path) -> Path:
    root = Path(output_root).expanduser().resolve() / "research_code_mining"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _candidate_manifest_path(candidate: str | Path) -> Path:
    path = Path(candidate).expanduser().resolve()
    if path.is_dir():
        path = path / "candidate_manifest.json"
    if not path.exists():
        raise ResearchCodeMiningError(f"Missing candidate manifest: {path}")
    return path


def _inventory_repository_files(repo_path: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    ignored = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "node_modules"}
    for path in sorted(repo_path.rglob("*")):
        if any(part in ignored for part in path.relative_to(repo_path).parts):
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(repo_path).as_posix()
        roles, evidence = _classify_file_roles(relative)
        files.append({
            "path": relative,
            "suffix": path.suffix.lower(),
            "kind": _file_kind(relative),
            "size_bytes": path.stat().st_size,
            "roles": roles,
            "evidence": evidence,
        })
        if len(files) >= limit:
            break
    return files


def _classify_file_roles(relative: str) -> tuple[list[str], list[str]]:
    text = relative.lower()
    checks = [
        ("docs", ["readme", "docs/", "tutorial", ".md", ".rst"], "documentation path"),
        ("data_connector", ["data/", "download", "fetch", "api", "dataset", "catalog", "ingest", "loader"], "data access path"),
        ("preprocessing", ["preprocess", "clean", "normalize", "transform", "feature"], "preprocessing path"),
        ("method", ["model", "method", "analysis", "train", "fit", "estimate", "event_study", "survival", "finite", "simulation"], "method path"),
        ("scientific_figure", ["plot", "figure", "visual", "chart"], "figure path"),
        ("validation", ["test", "validation", "validate", "metric", "benchmark", "ci.yml", "workflow"], "validation path"),
        ("environment", ["requirements", "pyproject", "environment", "setup.py", "package.json", "dockerfile"], "environment path"),
        ("review", ["check", "audit", "quality", "report"], "review/audit path"),
    ]
    roles: list[str] = []
    evidence: list[str] = []
    for role, keywords, reason in checks:
        if any(keyword in text for keyword in keywords):
            roles.append(role)
            evidence.append(reason)
    return roles or ["unclassified"], evidence or ["no structural keyword"]


def _file_kind(relative: str) -> str:
    suffix = Path(relative).suffix.lower()
    if suffix in {".md", ".rst", ".txt"}:
        return "documentation"
    if suffix in {".py", ".r", ".jl", ".m"}:
        return "code_file_structure_only"
    if suffix in {".ipynb"}:
        return "notebook_structure_only"
    if suffix in {".yml", ".yaml", ".toml", ".json", ".ini", ".cfg"}:
        return "configuration"
    if suffix in {".csv", ".tsv", ".parquet", ".nc", ".tif", ".tiff", ".fits"}:
        return "data_artifact_not_copied"
    return "other"


def _read_repo_docs(repo_path: Path, *, metadata_only: bool = False) -> dict[str, Any]:
    doc_names = ["README.md", "README.rst", "readme.md", "docs/README.md"]
    docs = []
    for name in doc_names:
        path = repo_path / name
        if path.exists() and path.is_file():
            text = "" if metadata_only else path.read_text(encoding="utf-8-sig", errors="replace")[:4000]
            docs.append({"path": name, "size_bytes": path.stat().st_size, "excerpt": text})
    return {"read_policy": "docs_excerpt_only" if not metadata_only else "metadata_only", "documents": docs}


def _package_manifest(repo_path: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    manifests = [item["path"] for item in files if item["path"].lower() in {"requirements.txt", "pyproject.toml", "environment.yml", "environment.yaml", "setup.py", "package.json"}]
    packages: list[str] = []
    requirements = repo_path / "requirements.txt"
    if requirements.exists():
        for line in requirements.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                packages.append(cleaned)
    return {
        "status": "written",
        "manifest_files": manifests,
        "packages": packages[:80],
        "source_policy": "package_metadata_only",
    }


def _write_file_inventory_csv(path: Path, files: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "kind", "suffix", "size_bytes", "roles", "evidence"])
        writer.writeheader()
        for item in files:
            writer.writerow({
                "path": item.get("path", ""),
                "kind": item.get("kind", ""),
                "suffix": item.get("suffix", ""),
                "size_bytes": item.get("size_bytes", 0),
                "roles": ";".join(item.get("roles") or []),
                "evidence": ";".join(item.get("evidence") or []),
            })


def _capabilities_from_role_map(role_map: dict[str, list[dict[str, Any]]]) -> list[str]:
    mapping = {
        "data_connector": "data_connector_candidate",
        "preprocessing": "preprocessing_template_candidate",
        "method": "method_template_candidate",
        "scientific_figure": "figure_template_candidate",
        "validation": "validation_gate_candidate",
        "review": "review_rule_candidate",
        "environment": "environment_fixture_candidate",
    }
    return [capability for role, capability in mapping.items() if role in role_map]


def _recommended_targets_from_roles(discipline: str, role_map: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    targets = {"data_connectors": [], "method_templates": [], "review_rules": []}
    if "data_connector" in role_map:
        targets["data_connectors"].append(_foundation_item(discipline, "mined_data_connector", "Data connector inferred from repository structure", role_map["data_connector"]))
    if "preprocessing" in role_map:
        targets["method_templates"].append(_foundation_item(discipline, "mined_preprocessing_template", "Preprocessing template inferred from repository structure", role_map["preprocessing"]))
    if "method" in role_map:
        targets["method_templates"].append(_foundation_item(discipline, "mined_method_template", "Method template inferred from repository structure", role_map["method"]))
    if "scientific_figure" in role_map:
        targets["method_templates"].append(_foundation_item(discipline, "mined_figure_template", "Figure-generation template inferred from repository structure", role_map["scientific_figure"]))
    if "validation" in role_map:
        targets["review_rules"].append(_foundation_item(discipline, "mined_validation_gate", "Validation gate inferred from repository structure", role_map["validation"]))
    if "review" in role_map:
        targets["review_rules"].append(_foundation_item(discipline, "mined_review_gate", "Review rule inferred from repository structure", role_map["review"]))
    if not targets["review_rules"]:
        targets["review_rules"].append(_foundation_item(discipline, "mined_reproducibility_gate", "Reproducibility gate inferred from repository structure", role_map.get("environment", [])))
    return targets


def _foundation_item(discipline: str, item_id: str, description: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_id": f"{discipline}.{item_id}",
        "description": description,
        "evidence_paths": [str(item.get("path")) for item in evidence[:10] if item.get("path")],
        "source_policy": "structure_only_no_source_copy",
    }


def _fallback_foundation_items(discipline: str, kind: str) -> list[dict[str, Any]]:
    return [_foundation_item(discipline, f"fallback_{kind}_candidate", f"Fallback {kind} candidate requiring domain review", [])]


def _load_seed_repositories(from_json: str | Path | None, *, discipline: str, query: str) -> list[dict[str, Any]]:
    if from_json:
        data = json.loads(Path(from_json).read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("repositories") or data.get("items") or []
        if not isinstance(data, list):
            raise ResearchCodeMiningError(f"Expected a JSON list or GitHub search payload: {from_json}")
        return [item for item in data if isinstance(item, dict)]
    return [_built_in_seed_repo(discipline=discipline, query=query)]


def _built_in_seed_repo(*, discipline: str, query: str) -> dict[str, Any]:
    return {
        "full_name": f"draftpaper-seed/{_safe_id(discipline)}-open-workflow",
        "html_url": f"https://github.com/search?q={_safe_id(query)}",
        "description": f"Seed metadata placeholder for {discipline} research-code discovery: {query}.",
        "topics": [discipline.replace("_", "-"), "reproducible-research", "scientific-workflow"],
        "language": "Python",
        "stargazers_count": 0,
        "forks_count": 0,
        "license": None,
        "has_readme": False,
        "has_tests": False,
        "has_ci": False,
        "has_requirements": False,
        "workflow_signals": ["metadata_only"],
    }


def _normalize_repo(repo: dict[str, Any], *, discipline: str, query: str) -> dict[str, Any]:
    license_value = repo.get("license")
    spdx = ""
    if isinstance(license_value, dict):
        spdx = str(license_value.get("spdx_id") or license_value.get("key") or "")
    elif license_value:
        spdx = str(license_value)
    topics = repo.get("topics") or []
    if isinstance(topics, str):
        topics = [topics]
    return {
        "full_name": repo.get("full_name") or repo.get("name") or "unknown/repository",
        "html_url": repo.get("html_url") or repo.get("url") or "",
        "description": repo.get("description") or "",
        "topics": [str(item) for item in topics],
        "language": repo.get("language") or "",
        "stargazers_count": int(repo.get("stargazers_count") or repo.get("stars") or 0),
        "forks_count": int(repo.get("forks_count") or repo.get("forks") or 0),
        "license_spdx": spdx if spdx and spdx != "NOASSERTION" else "",
        "has_readme": bool(repo.get("has_readme")),
        "has_tests": bool(repo.get("has_tests")),
        "has_ci": bool(repo.get("has_ci")),
        "has_requirements": bool(repo.get("has_requirements") or repo.get("has_pyproject")),
        "paper": repo.get("paper") or {},
        "workflow_signals": [str(item) for item in (repo.get("workflow_signals") or [])],
        "discipline_hint": discipline,
        "query": query,
    }


def _score_repo(repo: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    reasons: list[str] = []
    spdx = repo.get("license_spdx") or ""
    license_policy = _license_policy(spdx)
    if license_policy == "permissive_reusable":
        score += 20
        reasons.append("permissive license")
    elif license_policy == "copyleft_review_required":
        score += 8
        reasons.append("copyleft license requires careful review")
    else:
        reasons.append("metadata-only because license is missing or unclear")

    paper = repo.get("paper") or {}
    if paper.get("doi"):
        score += 12
        reasons.append("linked paper DOI")
    if paper.get("venue"):
        score += 6
        reasons.append("venue metadata")
    if int(paper.get("year") or 0) >= 2020:
        score += 4
        reasons.append("recent paper metadata")

    for key, points, label in [
        ("has_readme", 8, "README present"),
        ("has_tests", 10, "tests present"),
        ("has_ci", 6, "CI present"),
        ("has_requirements", 6, "environment metadata present"),
    ]:
        if repo.get(key):
            score += points
            reasons.append(label)

    workflow_signals = [str(item).lower() for item in (repo.get("workflow_signals") or [])]
    signal_points = min(20, len(set(workflow_signals)) * 4)
    score += signal_points
    if signal_points:
        reasons.append("complete workflow signals")

    score += min(12, int(repo.get("stargazers_count") or 0) / 20)
    score += min(6, int(repo.get("forks_count") or 0) / 10)
    return {
        "score": round(score, 3),
        "license_policy": license_policy,
        "score_reasons": reasons,
        "candidate_capabilities": _infer_capabilities(repo),
    }


def _license_policy(spdx: str) -> str:
    if spdx in PERMISSIVE_LICENSES:
        return "permissive_reusable"
    if spdx in COPYLEFT_LICENSES:
        return "copyleft_review_required"
    return "metadata_only_no_code_reuse"


def _infer_capabilities(repo: dict[str, Any]) -> list[str]:
    text = " ".join([
        str(repo.get("description") or ""),
        " ".join(str(item) for item in (repo.get("topics") or [])),
        " ".join(str(item) for item in (repo.get("workflow_signals") or [])),
    ]).lower()
    capability_keywords = {
        "raster": ["raster"],
        "data_connector": ["api", "download", "dataset", "data", "catalog"],
        "raster_processing": ["raster", "geotiff", "remote sensing", "remote-sensing"],
        "spatial_statistics": ["zonal", "spatial", "gis", "geography"],
        "baseline": ["baseline"],
        "baseline_model": ["baseline", "model", "machine learning", "machine-learning"],
        "ablation_study": ["ablation"],
        "evaluation_metrics": ["metric", "evaluation", "r2", "accuracy"],
        "scientific_figure": ["figure", "plot", "visualization"],
        "reproducible_environment": ["requirements", "reproducible", "workflow"],
    }
    capabilities = [
        capability
        for capability, keywords in capability_keywords.items()
        if any(keyword in text for keyword in keywords)
    ]
    return capabilities or ["workflow_metadata_review"]


def _build_candidate_manifest(repo: dict[str, Any], *, discipline: str, candidate_id: str) -> dict[str, Any]:
    return {
        "status": "candidate_report_written",
        "generated_at": utc_now(),
        "candidate_id": candidate_id,
        "discipline": discipline,
        "plugin_type": "mined_research_code_candidate",
        "source_repository": {
            "full_name": repo.get("full_name"),
            "html_url": repo.get("html_url"),
            "license_spdx": repo.get("license_spdx"),
            "license_policy": repo.get("license_policy"),
            "score": repo.get("score"),
        },
        "source_policy": "candidate_report_only_no_source_copy",
        "candidate_capabilities": repo.get("candidate_capabilities") or _infer_capabilities(repo),
        "score_reasons": repo.get("score_reasons") or [],
        "recommended_next_steps": [
            "Inspect repository manually or through a license-aware connector.",
            "Summarize reusable workflow ideas without copying third-party source code.",
            "Generalize data, method, figure, or review patterns into a Draftpaper-loop plugin template.",
            "Run privacy, license, fixture, and overlap checks before any PR.",
        ],
    }


def _render_discovery_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Research Repository Discovery",
        "",
        f"Discipline: `{payload.get('discipline')}`",
        f"Query: `{payload.get('query')}`",
        f"Repository count: `{payload.get('repo_count')}`",
        "",
        "This report is metadata-only. It does not clone repositories or copy source files.",
    ]
    for repo in payload.get("repositories") or []:
        lines.extend(["", f"## {repo.get('full_name')}", f"- URL: {repo.get('html_url')}", f"- License: {repo.get('license_spdx') or 'unknown'}"])
    return "\n".join(lines)


def _render_score_report(payload: dict[str, Any]) -> str:
    lines = ["# Research Repository Scores", "", "Repositories are ranked by license safety, reproducibility metadata, paper linkage, and workflow completeness."]
    for repo in payload.get("repositories") or []:
        lines.extend([
            "",
            f"## {repo.get('full_name')}",
            f"- Score: `{repo.get('score')}`",
            f"- License policy: `{repo.get('license_policy')}`",
            f"- Capabilities: `{', '.join(repo.get('candidate_capabilities') or [])}`",
        ])
    return "\n".join(lines)


def _render_candidate_report(manifest: dict[str, Any]) -> str:
    source = manifest.get("source_repository") or {}
    return "\n".join([
        "# Mined Plugin Candidate",
        "",
        f"Candidate: `{manifest.get('candidate_id')}`",
        f"Discipline: `{manifest.get('discipline')}`",
        f"Source repository: `{source.get('full_name')}`",
        f"Source URL: {source.get('html_url')}",
        f"License policy: `{source.get('license_policy')}`",
        f"Source policy: `{manifest.get('source_policy')}`",
        f"Candidate capabilities: `{', '.join(manifest.get('candidate_capabilities') or [])}`",
        "",
        "This candidate is a review report only. It is not a reusable plugin until it is generalized, tested, and approved.",
    ])


def _render_candidate_index(index: dict[str, Any]) -> str:
    lines = ["# Mined Plugin Candidate Index", "", f"Discipline: `{index.get('discipline')}`"]
    for item in index.get("candidates") or []:
        lines.extend(["", f"## {item.get('candidate_id')}", f"- Path: `{item.get('path')}`", f"- Manifest: `{item.get('manifest')}`"])
    return "\n".join(lines)


def _render_inspection_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Repository Structure Inspection",
        "",
        f"Candidate: `{payload.get('candidate_id')}`",
        f"Discipline: `{payload.get('discipline')}`",
        f"Source policy: `{payload.get('source_policy')}`",
        f"File count: `{payload.get('file_count')}`",
        "",
        "Only repository structure, package metadata, and optional documentation excerpts are recorded. Source directories are not copied.",
    ]
    for item in (payload.get("files") or [])[:30]:
        lines.append(f"- `{item.get('path')}` -> `{', '.join(item.get('roles') or [])}`")
    return "\n".join(lines)


def _render_workflow_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Repository Workflow Map",
        "",
        f"Candidate: `{payload.get('candidate_id')}`",
        f"Discipline: `{payload.get('discipline')}`",
        f"Source policy: `{payload.get('source_policy')}`",
        f"Workflow roles: `{', '.join(payload.get('workflow_roles') or [])}`",
        "",
        "The map is a structural interpretation for plugin candidate review, not a source-code import.",
    ]
    role_map = payload.get("role_map") or {}
    for role, items in role_map.items():
        lines.extend(["", f"## {role}"])
        for item in items[:8]:
            lines.append(f"- `{item.get('path')}`")
    return "\n".join(lines)


def _render_foundation_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Discipline Foundation Candidate",
        "",
        f"Discipline: `{payload.get('discipline')}`",
        f"Merge policy: `{payload.get('merge_policy')}`",
        "",
        "This report suggests discipline foundation additions. It does not modify formal modules.",
    ]
    for key in ["data_connector_candidates", "method_template_candidates", "review_rule_candidates"]:
        lines.extend(["", f"## {key}"])
        for item in payload.get(key) or []:
            lines.append(f"- `{item.get('candidate_id')}`: {item.get('description')}")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ResearchCodeMiningError(f"Missing input file: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ResearchCodeMiningError(f"Expected JSON object: {path}")
    return data


def _safe_id(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(text).strip().lower()).strip("_")
    return cleaned[:100] or "research_code"
