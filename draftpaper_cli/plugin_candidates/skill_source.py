# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import sys
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
    ACADEMICFORGE_COLLECTION_PREFIXES,
    DATA_CONNECTOR_KEYWORDS,
    FORMAL_DISCIPLINE_PLUGIN_TYPES,
    METHOD_TEMPLATE_KEYWORDS,
    PluginCandidateError,
    REVIEW_RULE_KEYWORDS,
    SUPPORT_LAYER_TYPES,
    SUPPORT_ROUTE_TARGETS,
    _privacy_scan_text,
    _read_text,
    _safe_id,
)

from .extractors import (
    _capability_ir_records_from_hints,
    _infer_skill_profile,
    _package_names_from_text,
    _review_rule_signal_scan,
    _support_routes_for_text,
    extract_skill_capabilities,
)


def _package_hook(name: str, fallback: Any) -> Any:
    package = sys.modules.get(__package__)
    return getattr(package, name, fallback) if package is not None else fallback

def _iter_skill_source_files(source_root: Path, *, exclude_roots: list[Path] | None = None) -> list[Path]:
    allowed = {".md", ".txt"}
    excluded = [path.resolve() for path in (exclude_roots or [])]
    generated_names = {
        "source_evidence_summary.md",
        "discipline_gap_report.md",
        "github_contribution_guide.md",
    }
    generated_dirs = {"plugin_candidates", "generalized_template", "contribution_package"}
    files: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(resolved == root or root in resolved.parents for root in excluded):
            continue
        if path.name.lower() in generated_names:
            continue
        if any(part.lower() in generated_dirs for part in path.parts):
            continue
        if path.name.lower() == "skill.md" or path.suffix.lower() in allowed:
            files.append(path)
    return files


def _skill_source_adapter_root(source_root: Path | None, output_root: str | Path | None = None) -> Path:
    if output_root:
        return Path(output_root).resolve()
    if source_root is not None:
        return source_root / "plugin_candidates" / "skill_source_adapter"
    return Path.cwd() / "plugin_candidates" / "skill_source_adapter"


def _skill_source_exclude_roots(source_root: Path, output_root: Path) -> list[Path]:
    resolved_source = source_root.resolve()
    resolved_output = output_root.resolve()
    if resolved_source == resolved_output or resolved_output in resolved_source.parents:
        return []
    return [resolved_output]


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def _requires_source_inspection(text: str) -> bool:
    return bool(re.search(r"(?im)^requires source inspection:\s*(true|yes|1)\s*$", text))


def _candidate_type_hints(text: str) -> dict[str, Any]:
    if _requires_source_inspection(text):
        return {
            "data_connector": {},
            "method_template": {},
            "review_rule": {},
            "review_rule_raw_signals": {},
            "review_rule_signal_scan": _review_rule_signal_scan(text, {}),
            "support_routes": [],
            "packages": [],
            "formal_plugin_types_present": [],
        }
    lowered = text.lower()
    data_connector_hints = {
        family: [term for term in config["terms"] if term in lowered]
        for family, config in DATA_CONNECTOR_KEYWORDS.items()
    }
    method_template_hints = {
        family: [term for term in config["terms"] if term in lowered]
        for family, config in METHOD_TEMPLATE_KEYWORDS.items()
    }
    review_rule_hints = {
        family: [term for term in config["terms"] if term in lowered]
        for family, config in REVIEW_RULE_KEYWORDS.items()
    }
    data_connector_hints = {key: value for key, value in data_connector_hints.items() if value}
    method_template_hints = {key: value for key, value in method_template_hints.items() if value}
    review_rule_hints = {key: value for key, value in review_rule_hints.items() if value}
    review_rule_signal_scan = _review_rule_signal_scan(text, review_rule_hints)
    eligible_review_rule_hints = {
        family: terms for family, terms in review_rule_hints.items()
        if family in review_rule_signal_scan["eligible_rule_families"]
    }
    support_routes = _support_routes_for_text(text)
    return {
        "data_connector": data_connector_hints,
        "method_template": method_template_hints,
        "review_rule": eligible_review_rule_hints,
        "review_rule_raw_signals": review_rule_hints,
        "review_rule_signal_scan": review_rule_signal_scan,
        "support_routes": support_routes,
        "packages": _package_names_from_text(text),
        "formal_plugin_types_present": [
            key for key, value in {
                "data_connector": data_connector_hints,
                "method_template": method_template_hints,
                "review_rule": review_rule_hints,
            }.items() if value
        ],
    }


def _source_record_from_file(path: Path, root: Path, *, include_hashes: bool) -> dict[str, Any]:
    stat = path.stat()
    text = _read_text(path, limit=30_000)
    record = {
        "relative_path": _relative_path(path, root),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_time": stat.st_mtime,
        "is_skill_file": path.name.lower() == "skill.md",
        "document_kind": "skill" if path.name.lower() == "skill.md" else ("markdown" if path.suffix.lower() == ".md" else "text"),
        "title": _markdown_title(text, path.stem),
        "privacy_status": _privacy_scan_text(text)["status"],
    }
    if include_hashes:
        record["sha256"] = _sha256_file(path)
    return record


def _detect_license_files(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered in {"license", "license.md", "license.txt", "copying", "notice", "notice.md", "notice.txt"}:
            text = _read_text(path, limit=12_000).lower()
            if "apache license" in text or "apache-2.0" in text:
                license_hint = "Apache-2.0"
            elif "mit license" in text:
                license_hint = "MIT"
            elif "creative commons" in text or "cc by" in text:
                license_hint = "Creative Commons"
            elif "gpl" in text or "gnu general public license" in text:
                license_hint = "GPL-family"
            else:
                license_hint = "unknown_or_custom"
            records.append({
                "relative_path": _relative_path(path, root),
                "license_hint": license_hint,
                "size_bytes": path.stat().st_size,
            })
    return records


def _license_audit_report(
    *,
    source: str,
    source_root: str | None,
    source_url: str | None,
    source_ref: str | None,
    license_records: list[dict[str, Any]],
) -> dict[str, Any]:
    status = "requires_review"
    if license_records and all(item.get("license_hint") not in {"unknown_or_custom", "GPL-family"} for item in license_records):
        status = "metadata_recorded"
    return {
        "status": status,
        "generated_at": utc_now(),
        "source": source,
        "source_root": source_root,
        "source_url": source_url,
        "source_ref": source_ref,
        "license_records": license_records,
        "promotion_policy": (
            "Unknown, custom, non-commercial, copyleft, or conflicting licenses must not be promoted into the core runtime "
            "without maintainer review. This command records provenance only and does not copy third-party source text."
        ),
    }


def _write_license_audit(out: Path, report: dict[str, Any]) -> None:
    _write_json(out / "LICENSE_AUDIT_REPORT.json", report)
    lines = [
        "# License Audit Report",
        "",
        f"Status: `{report.get('status')}`",
        f"Source: `{report.get('source')}`",
        f"Source URL: `{report.get('source_url') or 'not_recorded'}`",
        f"Source ref: `{report.get('source_ref') or 'not_recorded'}`",
        "",
        "## Detected License Files",
    ]
    records = report.get("license_records") or []
    if records:
        lines.extend(f"- `{item.get('relative_path')}`: `{item.get('license_hint')}`" for item in records)
    else:
        lines.append("- No license file was detected in the inspected local source tree. Treat this source as `requires_review` before promotion.")
    lines.extend(["", "## Promotion Policy", "", str(report.get("promotion_policy") or "")])
    (out / "LICENSE_AUDIT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def _github_raw_file_url(repo_url: str, ref: str, path: str) -> str | None:
    parsed = urllib.parse.urlparse(repo_url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"


def _resolve_github_commit_sha(repo_url: str | None, ref: str) -> str | None:
    if not repo_url:
        return None
    parsed = urllib.parse.urlparse(repo_url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{urllib.parse.quote(ref, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": "Draftpaper-loop metadata adapter"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - fixed GitHub API host.
            payload = json.loads(response.read().decode("utf-8-sig", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        payload = {}
    sha = str(payload.get("sha") or "") if isinstance(payload, dict) else ""
    if re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        return sha
    if shutil.which("gh"):
        try:
            completed = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/commits/{ref}", "--jq", ".sha"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{40}", candidate):
            return candidate
    return None


def _academicforge_registry_url(source_url: str | None, source_ref: str | None) -> str | None:
    if source_url and source_url.lower().endswith("skills.json"):
        return source_url
    ref = source_ref or "site-first"
    if source_url:
        raw = _github_raw_file_url(source_url, ref, "registry/skills.json")
        if raw:
            return raw
    return None


def _read_registry_json(url_or_path: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url_or_path)
    try:
        if parsed.scheme in {"http", "https", "file", "data"}:
            payload = fetch_text(
                url_or_path,
                user_agent="Draftpaper-loop metadata adapter",
                allowed_hosts={"raw.githubusercontent.com", "api.github.com"},
            )
        else:
            payload = Path(url_or_path).read_text(encoding="utf-8-sig")
    except (OSError, SafeFetchError) as exc:
        raise PluginCandidateError(f"Unable to read skill registry metadata: {url_or_path}: {exc}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PluginCandidateError(f"Invalid skill registry JSON: {url_or_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PluginCandidateError(f"Skill registry JSON must be an object: {url_or_path}")
    return data


def _registry_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        preferred = value.get("en") or value.get("zh") or value.get("text")
        if preferred is not None:
            return _registry_text(preferred)
        return "; ".join(_registry_text(item) for item in value.values() if _registry_text(item))
    if isinstance(value, list):
        return ", ".join(_registry_text(item) for item in value if _registry_text(item))
    return str(value)


def _academicforge_registry_skills(data: dict[str, Any]) -> list[dict[str, Any]]:
    skills = data.get("skills") if isinstance(data, dict) else None
    if isinstance(skills, list):
        return [item for item in skills if isinstance(item, dict)]
    return []


def _academicforge_auxiliary_url(registry_url: str, relative_path: str) -> str | None:
    normalized = registry_url.replace("\\", "/")
    marker = "/registry/skills.json"
    if normalized.startswith(("http://", "https://")) and marker in normalized:
        return normalized.split(marker, 1)[0] + "/" + relative_path.lstrip("/")
    return None


def _academicforge_expanded_skills(
    collections: list[dict[str, Any]],
    *,
    registry_url: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expand collection-level registry records without copying upstream skill bodies."""

    classification: dict[str, Any] = {}
    translations: dict[str, Any] = {}
    auxiliary_errors: list[str] = []
    for relative_path, target in [
        ("scripts/skill-classification.json", classification),
        ("scripts/skill-translations.zh.json", translations),
    ]:
        url = _academicforge_auxiliary_url(registry_url, relative_path)
        if not url:
            continue
        try:
            target.update(_package_hook("_read_registry_json", _read_registry_json)(url))
        except PluginCandidateError as exc:
            auxiliary_errors.append(str(exc))

    collection_by_prefix = {
        prefix: item
        for item in collections
        for collection_id, prefix in ACADEMICFORGE_COLLECTION_PREFIXES.items()
        if str(item.get("id") or "") == collection_id
    }
    expanded: list[dict[str, Any]] = []
    detailed_counts: dict[str, int] = {}
    for qualified_id, detail in sorted(classification.items()):
        prefix, _, skill_name = str(qualified_id).partition(".")
        collection = collection_by_prefix.get(prefix)
        if not collection or not skill_name:
            continue
        collection_id = str(collection.get("id") or prefix)
        category = str((detail or {}).get("category") or "unclassified") if isinstance(detail, dict) else "unclassified"
        translated = translations.get(qualified_id)
        inherited_tags = [str(item) for item in collection.get("tags") or []]
        expanded.append({
            **collection,
            "id": qualified_id,
            "name": skill_name.replace("-", " ").replace("_", " ").title(),
            "summary": {
                "en": f"AcademicForge skill `{qualified_id}` classified as {category}.",
                "zh": translated if isinstance(translated, str) else "",
            },
            "skill_count": 1,
            "category": category,
            "tags": list(dict.fromkeys(inherited_tags + [category, skill_name])),
            "parent_collection_id": collection_id,
            "metadata_detail_status": "classified_skill",
        })
        detailed_counts[collection_id] = detailed_counts.get(collection_id, 0) + 1

    placeholder_count = 0
    for collection in collections:
        collection_id = str(collection.get("id") or "collection")
        declared = max(1, int(collection.get("skill_count") or 1))
        known = detailed_counts.get(collection_id, 0)
        if declared == 1 and known == 0:
            expanded.append({
                **collection,
                "skill_count": 1,
                "parent_collection_id": collection_id,
                "metadata_detail_status": "registry_skill",
                "requires_source_inspection": False,
            })
            continue
        for index in range(known + 1, declared + 1):
            placeholder_count += 1
            placeholder_id = collection_id if declared == 1 else f"{collection_id}.declared-skill-{index:03d}"
            expanded.append({
                **collection,
                "id": placeholder_id,
                "name": collection.get("name") if declared == 1 else f"{collection.get('name') or collection_id} declared skill {index}",
                "skill_count": 1,
                "parent_collection_id": collection_id,
                "metadata_detail_status": "collection_declared_placeholder",
                "requires_source_inspection": True,
            })

    declared_count = sum(max(1, int(item.get("skill_count") or 1)) for item in collections)
    return expanded or collections, {
        "collection_count": len(collections),
        "declared_skill_count": declared_count,
        "expanded_skill_count": len(expanded or collections),
        "detailed_skill_count": len(expanded) - placeholder_count if expanded else 0,
        "placeholder_skill_count": placeholder_count if expanded else len(collections),
        "silent_loss_count": max(0, declared_count - len(expanded or collections)),
        "classification_metadata_count": len(classification),
        "auxiliary_metadata_errors": auxiliary_errors,
    }


def _write_academicforge_metadata_profiles(
    *,
    out: Path,
    source_url: str | None,
    source_ref: str | None,
) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    requested_ref = source_ref or "site-first"
    immutable_commit = _package_hook("_resolve_github_commit_sha", _resolve_github_commit_sha)(source_url, requested_ref)
    registry_url = _academicforge_registry_url(source_url, immutable_commit or requested_ref)
    if not registry_url:
        raise PluginCandidateError("AcademicForge snapshot requires --repo/--source-url pointing to a GitHub repo or registry/skills.json.")
    registry = _package_hook("_read_registry_json", _read_registry_json)(registry_url)
    collections = _academicforge_registry_skills(registry)
    if not collections:
        raise PluginCandidateError(f"AcademicForge registry contained no skill records: {registry_url}")
    skills, expansion = _academicforge_expanded_skills(collections, registry_url=registry_url)
    derived_root = out / "derived_skill_metadata"
    if derived_root.exists():
        shutil.rmtree(derived_root)
    derived_root.mkdir(parents=True, exist_ok=True)
    registry_records: list[dict[str, Any]] = []
    license_records: list[dict[str, Any]] = []
    for index, item in enumerate(skills, start=1):
        skill_id = _safe_id(str(item.get("id") or item.get("name") or f"skill_{index}"))
        name = _registry_text(item.get("name")) or skill_id
        summary = _registry_text(item.get("summary"))
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        repository = _registry_text(item.get("repository") or item.get("repo"))
        license_name = _registry_text(item.get("license") or "unknown") or "unknown"
        category = _registry_text(item.get("category") or item.get("domain"))
        subdiscipline = _registry_text(item.get("subdiscipline") or item.get("discipline"))
        install = item.get("install") if isinstance(item.get("install"), dict) else {}
        install_text = _registry_text(install)
        profile_path = derived_root / f"{skill_id}.md"
        lines = [
            f"# {name}",
            "",
            "Metadata-only AcademicForge skill profile generated by Draftpaper-loop.",
            "This file is derived from registry metadata only and does not copy upstream SKILL.md bodies or source code.",
            "",
            f"Skill id: {item.get('id') or skill_id}",
            f"Metadata detail status: {item.get('metadata_detail_status') or 'registry_skill'}",
            f"Requires source inspection: {'true' if item.get('requires_source_inspection') else 'false'}",
            "Source registry: AcademicForge registry metadata snapshot",
            f"Source ref: {requested_ref}",
            f"Immutable commit: {immutable_commit or 'unresolved'}",
            f"Repository: {repository or 'not recorded'}",
            f"Author: {_registry_text(item.get('author')) or 'not recorded'}",
            f"License: {license_name}",
            f"Category: {category or 'unknown'}",
            f"Subdiscipline: {subdiscipline or 'unknown'}",
            f"Tags: {', '.join(str(tag) for tag in tags) or 'none'}",
            f"Skill count: {item.get('skill_count') or 'unknown'}",
            f"Install metadata: {install_text or 'not recorded'}",
            "",
            "Summary:",
            summary or "No summary provided in registry metadata.",
        ]
        profile_path.write_text("\n".join(lines), encoding="utf-8")
        registry_records.append({
            "skill_id": skill_id,
            "registry_id": item.get("id"),
            "name": name,
            "relative_path": profile_path.relative_to(derived_root).as_posix(),
            "repository": repository,
            "author": item.get("author"),
            "license": license_name,
            "category": category,
            "subdiscipline": subdiscipline,
            "tags": tags,
            "parent_collection_id": item.get("parent_collection_id") or item.get("id"),
            "metadata_detail_status": item.get("metadata_detail_status") or "registry_skill",
            "requires_source_inspection": bool(item.get("requires_source_inspection")),
            "metadata_profile": str(profile_path),
        })
        lowered_license = license_name.lower()
        if "mit" in lowered_license:
            license_hint = "MIT"
        elif "apache" in lowered_license:
            license_hint = "Apache-2.0"
        elif "bsd" in lowered_license:
            license_hint = "BSD-family"
        elif "cc by" in lowered_license or "creative commons" in lowered_license:
            license_hint = "Creative Commons"
        elif "gpl" in lowered_license:
            license_hint = "GPL-family"
        else:
            license_hint = "unknown_or_custom"
        license_records.append({
            "relative_path": profile_path.relative_to(derived_root).as_posix(),
            "license_hint": license_hint,
            "declared_license": license_name,
            "repository": repository,
            "author": item.get("author"),
            "registry_id": item.get("id"),
        })
    adapter_report = {
        "status": "written",
        "generated_at": utc_now(),
        "adapter": "academicforge",
        "registry_url": registry_url,
        "source_ref": requested_ref,
        "immutable_commit": immutable_commit,
        "immutable_ref_resolved": bool(immutable_commit),
        "metadata_only": True,
        "source_files_copied": False,
        "skill_count": len(registry_records),
        **expansion,
        "derived_source_root": str(derived_root),
        "records": registry_records,
        "policy": "Derived profiles contain registry and classification metadata only. Upstream SKILL.md bodies and source code are not copied. Collection-only declarations remain explicit placeholders until source inspection resolves them.",
    }
    _write_json(out / "ACADEMICFORGE_REGISTRY_ADAPTER.json", adapter_report)
    return derived_root, registry_records, license_records, adapter_report


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _write_simple_yaml(path: Path, data: dict[str, Any]) -> None:
    def emit(value: Any, indent: int = 0) -> list[str]:
        prefix = " " * indent
        if isinstance(value, dict):
            lines: list[str] = []
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
            return lines
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}- {_yaml_scalar(item)}")
            return lines
        return [f"{prefix}{_yaml_scalar(value)}"]

    path.write_text("\n".join(emit(data)) + "\n", encoding="utf-8")


def _write_skill_matrix(out: Path, capability_map: dict[str, Any]) -> None:
    rows = []
    for record in capability_map.get("records") or []:
        formal = record.get("formal_targets") or {}
        rows.append([
            str(record.get("relative_path") or ""),
            str(record.get("discipline") or ""),
            ", ".join(formal.get("data_connector") or []),
            ", ".join(formal.get("method_template") or []),
            ", ".join(formal.get("review_rule") or []),
            ", ".join(str(item) for item in (record.get("support_targets") or [])),
            "yes" if record.get("review_rule_backflow_possible") else "no",
        ])
    lines = [
        "# AcademicForge Skill Matrix",
        "",
        "This matrix is metadata-only. It maps source skills to Draftpaper-loop formal plugin candidates and support-layer targets without copying third-party source text.",
        "",
        "| Skill | Discipline | Data connectors | Method templates | Review rules | Support targets | Review-rule backflow |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows)
    if not rows:
        lines.append("| none | none | none | none | none | none | no |")
    lines.extend([
        "",
        "Formal discipline modules accept only `data_connector`, `method_template`, and `review_rule`. Support-layer skills can produce review-rule backflow candidates but cannot be promoted directly into `discipline_modules/`.",
    ])
    (out / "ACADEMICFORGE_SKILL_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_discipline_gap_report(out: Path, capability_map: dict[str, Any]) -> None:
    lines = [
        "# Discipline Gap Report",
        "",
        "This report summarizes metadata-only capability coverage by discipline.",
        "",
        "| Discipline | Data connector sources | Method template sources | Review rule sources | Support sources | Packages |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for discipline, bucket in sorted((capability_map.get("discipline_map") or {}).items()):
        packages = ", ".join(sorted((bucket.get("packages") or {}).keys())) or "none"
        lines.append(
            f"| {discipline} | {bucket.get('data_connector_sources', 0)} | {bucket.get('method_template_sources', 0)} | "
            f"{bucket.get('review_rule_sources', 0)} | {bucket.get('support_sources', 0)} | {packages} |"
        )
    lines.extend([
        "",
        "Use this report to decide which validated candidates should be generalized, fixture-tested, and submitted as contribution packages.",
    ])
    (out / "DISCIPLINE_GAP_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def snapshot_skill_source(
    source_root: str | Path | None = None,
    *,
    source: str = "local_skill",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
    include_hashes: bool = True,
) -> dict[str, Any]:
    """Write a metadata-only snapshot of a skill source tree.

    The snapshot intentionally records file metadata and hashes only. It does
    not copy source files or third-party skill text into Draftpaper-loop.
    """

    root = Path(source_root).resolve() if source_root else None
    if root is not None and not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    adapter_report: dict[str, Any] | None = None
    registry_records: list[dict[str, Any]] = []
    registry_license_records: list[dict[str, Any]] = []
    if root is None and source.lower().replace("-", "_") == "academicforge":
        root, registry_records, registry_license_records, adapter_report = _write_academicforge_metadata_profiles(
            out=out,
            source_url=source_url,
            source_ref=source_ref,
        )
    files = _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)) if root is not None else []
    records = [_source_record_from_file(path, root, include_hashes=include_hashes) for path in files] if root is not None else []
    if registry_records:
        by_relative = {str(item.get("relative_path") or ""): item for item in registry_records}
        for record in records:
            registry_record = by_relative.get(str(record.get("relative_path") or ""))
            if registry_record:
                record["registry_metadata"] = registry_record
    snapshot = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root) if root is not None else None,
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "source_files_copied": False,
        "adapter_report": adapter_report,
        "file_count": len(records),
        "records": records,
        "policy": "metadata_snapshot_only; run inspect/index/classify/map before candidate extraction",
    }
    _write_json(out / "SNAPSHOT.json", snapshot)
    _write_license_audit(out, _license_audit_report(
        source=source,
        source_root=str(root) if root is not None else None,
        source_url=source_url,
        source_ref=source_ref,
        license_records=registry_license_records or (_detect_license_files(root) if root is not None else []),
    ))
    return snapshot


def inspect_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Inspect skill docs without copying their source text."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    files = _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out))
    records: list[dict[str, Any]] = []
    aggregate_packages: dict[str, int] = {}
    aggregate_formal_types: dict[str, int] = {"data_connector": 0, "method_template": 0, "review_rule": 0}
    aggregate_support_routes: dict[str, int] = {key: 0 for key in SUPPORT_ROUTE_TARGETS}
    privacy_failures = 0
    for path in files:
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        privacy = _privacy_scan_text(text)
        if privacy["status"] != "passed":
            privacy_failures += 1
        for package in hints["packages"]:
            aggregate_packages[package] = aggregate_packages.get(package, 0) + 1
        for plugin_type in hints["formal_plugin_types_present"]:
            aggregate_formal_types[plugin_type] += 1
        for route in hints["support_routes"]:
            aggregate_support_routes[route] = aggregate_support_routes.get(route, 0) + 1
        records.append({
            "relative_path": _relative_path(path, root),
            "title": _markdown_title(text, path.stem),
            "privacy_status": privacy["status"],
            "formal_plugin_types_present": hints["formal_plugin_types_present"],
            "support_routes": hints["support_routes"],
            "packages": hints["packages"],
            "matched_data_connector_families": sorted(hints["data_connector"].keys()),
            "matched_method_template_families": sorted(hints["method_template"].keys()),
            "matched_review_rule_families": sorted(hints["review_rule"].keys()),
        })
    inspection = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "file_count": len(records),
        "privacy_failure_count": privacy_failures,
        "package_counts": aggregate_packages,
        "formal_plugin_type_file_counts": aggregate_formal_types,
        "support_route_file_counts": aggregate_support_routes,
        "records": records,
        "policy": "inspection stores matched terms and route hints only; no source text is copied",
    }
    _write_json(out / "SKILL_SOURCE_INSPECTION.json", inspection)
    _write_json(out / "source_inspection.json", inspection)
    _write_license_audit(out, _license_audit_report(
        source=source,
        source_root=str(root),
        source_url=source_url,
        source_ref=source_ref,
        license_records=_detect_license_files(root),
    ))
    return inspection


def index_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Build a metadata index for skill files before candidate extraction."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    discipline_counts: dict[str, int] = {}
    review_rule_backflow_candidates = 0
    capability_records: list[dict[str, Any]] = []
    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        profile = _infer_skill_profile(text, discipline)
        primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
        discipline_counts[primary] = discipline_counts.get(primary, 0) + 1
        hints = _candidate_type_hints(text)
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        review_rule_backflow_candidates += len(hints["review_rule"])
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "title": _markdown_title(text, path.stem),
            "discipline_profile": profile,
            "formal_plugin_types_present": hints["formal_plugin_types_present"],
            "support_routes": hints["support_routes"],
            "packages": hints["packages"],
            "review_rule_backflow_family_count": len(hints["review_rule"]),
            "capability_record_count": len(skill_capability_records),
            "capability_ir_records": skill_capability_records,
            "candidate_generation_command": (
                "python -m draftpaper_cli.cli extract-skill-capabilities "
                f"--source-file {path} --source {source} --skill-id {skill_id} --discipline {primary}"
            ),
        })
    index = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "discipline": discipline,
        "metadata_only": True,
        "skill_count": len(records),
        "discipline_counts": discipline_counts,
        "review_rule_backflow_family_count": review_rule_backflow_candidates,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "skills": records,
        "policy": "index only; formal candidates are produced by extract-skill-capabilities or compile-skill-source",
    }
    _write_json(out / "SKILL_SOURCE_INDEX.json", index)
    _write_json(out / "SKILL_INDEX.json", index)
    return index


def classify_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Classify skill files into formal-candidate, support, external-only, or reject routes."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    disposition_counts: dict[str, int] = {}
    capability_records: list[dict[str, Any]] = []
    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        profile = _infer_skill_profile(text, discipline)
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        privacy = _privacy_scan_text(text)
        if _requires_source_inspection(text):
            disposition = "unresolved_metadata"
        elif privacy["status"] != "passed":
            disposition = "requires_privacy_review"
        elif hints["formal_plugin_types_present"]:
            disposition = "formal_candidate_source"
        elif hints["support_routes"]:
            disposition = "support_candidate_source"
        elif _package_names_from_text(text):
            disposition = "external_only"
        else:
            disposition = "non_research_reject"
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "title": _markdown_title(text, path.stem),
            "disposition": disposition,
            "discipline_profile": profile,
            "formal_plugin_types_present": hints["formal_plugin_types_present"],
            "support_routes": hints["support_routes"],
            "review_rule_backflow_families": sorted(hints["review_rule"].keys()),
            "capability_record_count": len(skill_capability_records),
            "capability_ir_records": skill_capability_records,
            "promotion_allowed": False,
            "next_step": "compile-skill-source" if disposition in {"formal_candidate_source", "support_candidate_source"} else "manual_review",
        })
    classification = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "disposition_counts": disposition_counts,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "records": records,
        "policy": "classification is advisory; candidate validation and human confirmation are required before promotion",
    }
    _write_json(out / "SKILL_SOURCE_CLASSIFICATION.json", classification)
    _write_json(out / "SKILL_DISPOSITION.json", classification)
    return classification


def map_skill_capabilities(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Map source skills to discipline plugin and support-layer targets."""

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)
    discipline_map: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    capability_records: list[dict[str, Any]] = []
    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        profile = _infer_skill_profile(text, discipline)
        primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        bucket = discipline_map.setdefault(primary, {
            "data_connector_sources": 0,
            "method_template_sources": 0,
            "review_rule_sources": 0,
            "support_sources": 0,
            "capability_records": 0,
            "capability_kinds": {},
            "support_routes": {},
            "packages": {},
        })
        bucket["capability_records"] += len(skill_capability_records)
        for capability in skill_capability_records:
            kind = str(capability.get("formal_plugin_type") or capability.get("support_type") or "unknown")
            bucket["capability_kinds"][kind] = bucket["capability_kinds"].get(kind, 0) + 1
        if hints["data_connector"]:
            bucket["data_connector_sources"] += 1
        if hints["method_template"]:
            bucket["method_template_sources"] += 1
        if hints["review_rule"]:
            bucket["review_rule_sources"] += 1
        if hints["support_routes"]:
            bucket["support_sources"] += 1
        for route in hints["support_routes"]:
            bucket["support_routes"][route] = bucket["support_routes"].get(route, 0) + 1
        for package in hints["packages"]:
            bucket["packages"][package] = bucket["packages"].get(package, 0) + 1
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "discipline": primary,
            "formal_targets": {
                "data_connector": sorted(hints["data_connector"].keys()),
                "method_template": sorted(hints["method_template"].keys()),
                "review_rule": sorted(hints["review_rule"].keys()),
            },
            "support_targets": [SUPPORT_ROUTE_TARGETS.get(route, {}).get("target", route) for route in hints["support_routes"]],
            "review_rule_backflow_possible": bool(hints["review_rule"]),
            "capability_record_count": len(skill_capability_records),
            "capability_ir_records": skill_capability_records,
            "packages": hints["packages"],
        })
    capability_map = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "metadata_only": True,
        "discipline_map": discipline_map,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "records": records,
        "deployment_policy": {
            "formal_discipline_plugin_types": ["data_connector", "method_template", "review_rule"],
            "support_layer_targets": SUPPORT_ROUTE_TARGETS,
            "promotion_allowed_by_this_command": False,
            "review_rule_backflow_policy": "support skills may create review_rule candidates, but only validated formal candidates can be promoted",
        },
    }
    _write_json(out / "SKILL_CAPABILITY_MAP.json", capability_map)
    _write_json(out / "SKILL_MAPPING.json", capability_map)
    _write_simple_yaml(out / "SKILL_MAPPING.yaml", capability_map)
    _write_skill_matrix(out, capability_map)
    _write_discipline_gap_report(out, capability_map)
    return capability_map


def extract_review_rule_signals(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Write a standalone review-rule signal report for a skill/source tree.

    This is the stable intermediate API between support-layer skills and
    formal discipline review-rule candidates. It scans every source file,
    regardless of whether that file is later classified as data, method,
    workflow, paper-contract, or shared-capability material.
    """

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    out = _skill_source_adapter_root(root, output_root)
    out.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    capability_records: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    recommendation_counts: dict[str, int] = {}
    support_backflow_count = 0

    for path in _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out)):
        text = _read_text(path, limit=60_000)
        hints = _candidate_type_hints(text)
        profile = _infer_skill_profile(text, discipline)
        primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
        relative = _relative_path(path, root)
        skill_id = _safe_id(str(Path(relative).with_suffix("")))
        scan = hints.get("review_rule_signal_scan") or {}
        families = scan.get("families") or {}
        eligible_families = list(scan.get("eligible_rule_families") or [])
        for family, family_scan in families.items():
            family_counts[family] = family_counts.get(family, 0) + 1
            recommendation = str(family_scan.get("recommendation") or "unknown")
            recommendation_counts[recommendation] = recommendation_counts.get(recommendation, 0) + 1
        skill_capability_records = _capability_ir_records_from_hints(
            source=source,
            skill_id=skill_id,
            profile=profile,
            hints=hints,
        )
        capability_records.extend(skill_capability_records)
        support_routes = list(hints.get("support_routes") or [])
        if support_routes and eligible_families:
            support_backflow_count += 1
        records.append({
            "skill_id": skill_id,
            "relative_path": relative,
            "title": _markdown_title(text, path.stem),
            "primary_discipline": primary,
            "secondary_disciplines": list(profile.get("secondary_disciplines") or []),
            "formal_plugin_types_present": list(hints.get("formal_plugin_types_present") or []),
            "support_routes": support_routes,
            "review_rule_backflow_families": eligible_families,
            "review_rule_signal_scan": scan,
            "capability_ir_records": skill_capability_records,
            "candidate_generation_command": (
                "python -m draftpaper_cli.cli extract-skill-capabilities "
                f"--source-file {path} --source {source} --skill-id {skill_id} --discipline {primary}"
            ),
        })

    report = {
        "status": "written",
        "generated_at": utc_now(),
        "source": source,
        "source_root": str(root),
        "source_url": source_url,
        "source_ref": source_ref,
        "discipline": discipline,
        "metadata_only": True,
        "file_count": len(records),
        "review_rule_family_counts": family_counts,
        "recommendation_counts": recommendation_counts,
        "support_backflow_source_count": support_backflow_count,
        "formal_candidate_signal_count": sum(
            1
            for record in capability_records
            if record.get("formal_plugin_type") == "review_rule"
        ),
        "support_layer_signal_count": sum(
            1
            for record in capability_records
            if record.get("capability_kind") == "support_layer_candidate"
        ),
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "records": records,
        "formal_plugin_types": FORMAL_DISCIPLINE_PLUGIN_TYPES,
        "support_layer_targets": SUPPORT_ROUTE_TARGETS,
        "review_rule_backflow_policy": {
            "formal_promotion_targets": FORMAL_DISCIPLINE_PLUGIN_TYPES,
            "support_layer_types": SUPPORT_LAYER_TYPES,
            "support_candidates_promotion_allowed": False,
            "rule": "Support-layer skills may backflow evidence-bound review_rule candidates, but they are not promoted directly into discipline_modules.",
        },
        "policy": (
            "All skill/source files are scanned for evidence-bound scientific quality signals. "
            "Support-layer records may backflow only as validated data_connector, method_template, or review_rule candidates; "
            "thresholds remain contextual unless backed by guideline, benchmark, discipline convention, or human confirmation."
        ),
    }
    _write_json(out / "REVIEW_RULE_SIGNAL_REPORT.json", report)
    _write_json(out / "review_rule_signal_report.json", report)
    lines = [
        "# Review Rule Signal Report",
        "",
        f"Source: `{source}`",
        f"Files scanned: {len(records)}",
        f"Support-layer sources with backflow signals: {support_backflow_count}",
        "",
        "## Rule Family Counts",
        *[f"- `{family}`: {count}" for family, count in sorted(family_counts.items())],
        "",
        "## Recommendation Counts",
        *[f"- `{name}`: {count}" for name, count in sorted(recommendation_counts.items())],
        "",
        "## Policy",
        "",
        str(report["policy"]),
    ]
    (out / "REVIEW_RULE_SIGNAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def compile_skill_source(
    source_root: str | Path,
    *,
    source: str = "local_skill",
    discipline: str | None = "auto",
    output_root: str | Path | None = None,
    stop_after: str = "candidate",
    jobs: int = 1,
    resume: bool = False,
) -> dict[str, Any]:
    """Batch-convert a skill/source tree into candidate-only plugin reports.

    The first implementation is intentionally sequential. The ``jobs`` value is
    recorded for future runners but does not enable concurrent writes yet.
    """

    root = Path(source_root).resolve()
    if not root.exists():
        raise PluginCandidateError(f"Missing source root: {root}")
    if stop_after != "candidate":
        raise PluginCandidateError("compile-skill-source currently supports --stop-after candidate only.")
    out = Path(output_root).resolve() if output_root else root / "plugin_candidates" / "compiled_skill_source"
    source_files = _iter_skill_source_files(root, exclude_roots=_skill_source_exclude_roots(root, out))
    out.mkdir(parents=True, exist_ok=True)
    records = []
    type_counts: dict[str, int] = {"data_connector": 0, "method_template": 0, "review_rule": 0}
    support_type_counts: dict[str, int] = {"workflow_recipe": 0, "paper_contract": 0, "shared_capability": 0}
    discipline_counts: dict[str, int] = {}
    discipline_review_rule_counts: dict[str, int] = {}
    support_backflow_records: list[dict[str, Any]] = []
    capability_records: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    support_candidate_records: list[dict[str, Any]] = []
    unresolved_source_count = 0
    for file_path in source_files:
        relative = file_path.relative_to(root)
        skill_id = _safe_id(str(relative.with_suffix("")))
        source_text = _read_text(file_path, limit=60_000)
        if _requires_source_inspection(source_text):
            unresolved_source_count += 1
            records.append({
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": skill_id,
                "candidate_count": 0,
                "plugin_type_counts": {},
                "support_candidate_count": 0,
                "support_candidates": [],
                "support_routes": [],
                "capability_record_count": 0,
                "disposition": "unresolved_metadata",
                "requires_source_inspection": True,
            })
            continue
        disposition = extract_skill_capabilities(
            file_path,
            source=source,
            skill_id=skill_id,
            discipline=discipline,
            output_root=out,
        )
        for candidate in disposition.get("candidates") or []:
            plugin_type = str(candidate.get("plugin_type") or "unknown")
            type_counts[plugin_type] = type_counts.get(plugin_type, 0) + 1
            candidate_records.append({
                **candidate,
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": disposition.get("skill_id") or skill_id,
            })
        primary = str((disposition.get("discipline_profile") or {}).get("primary_discipline") or "default")
        discipline_counts[primary] = discipline_counts.get(primary, 0) + int(disposition.get("candidate_count") or 0)
        discipline_review_rule_counts[primary] = discipline_review_rule_counts.get(primary, 0) + int((disposition.get("plugin_type_counts") or {}).get("review_rule") or 0)
        capability_records.extend([item for item in disposition.get("capability_records") or [] if isinstance(item, dict)])
        support_candidates = disposition.get("support_candidates") or []
        for support_candidate in support_candidates:
            support_type = str(support_candidate.get("support_type") or "shared_capability")
            support_type_counts[support_type] = support_type_counts.get(support_type, 0) + 1
            support_candidate_records.append({
                **support_candidate,
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": disposition.get("skill_id") or skill_id,
            })
            support_backflow_records.append({
                "source_file": str(file_path),
                "relative_path": str(relative),
                "skill_id": disposition.get("skill_id") or skill_id,
                "discipline": primary,
                "support_type": support_type,
                "support_candidate_id": support_candidate.get("candidate_id"),
                "support_candidate_path": support_candidate.get("path"),
                "intended_support_target": support_candidate.get("intended_support_target"),
                "review_rule_backflow_candidate_ids": support_candidate.get("review_rule_backflow_candidate_ids") or [],
                "review_rule_backflow_scope": support_candidate.get("review_rule_backflow_scope") or {},
                "capability_ir": support_candidate.get("capability_ir") or {},
            })
        records.append({
            "source_file": str(file_path),
            "relative_path": str(relative),
            "skill_id": disposition.get("skill_id") or skill_id,
            "candidate_count": disposition.get("candidate_count") or 0,
            "plugin_type_counts": disposition.get("plugin_type_counts") or {},
            "support_candidate_count": disposition.get("support_candidate_count") or 0,
            "support_candidates": disposition.get("support_candidates") or [],
            "support_routes": disposition.get("support_routes") or [],
            "capability_record_count": disposition.get("capability_record_count") or 0,
            "disposition": disposition.get("disposition_path"),
        })
    support_candidate_count = sum(int(item.get("support_candidate_count") or 0) for item in records)
    review_rule_backflow_count = sum(len(item.get("review_rule_backflow_candidate_ids") or []) for item in support_backflow_records)
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "source_root": str(root),
        "source": source,
        "discipline": discipline,
        "stop_after": stop_after,
        "jobs_requested": jobs,
        "resume": resume,
        "source_file_count": len(records),
        "unresolved_source_count": unresolved_source_count,
        "candidate_count": sum(int(item["candidate_count"] or 0) for item in records),
        "candidates": candidate_records,
        "plugin_type_counts": type_counts,
        "support_candidate_count": support_candidate_count,
        "support_candidates": support_candidate_records,
        "support_type_counts": support_type_counts,
        "capability_record_count": len(capability_records),
        "capability_records": capability_records,
        "review_rule_backflow_count": review_rule_backflow_count,
        "support_backflow_records": support_backflow_records,
        "discipline_candidate_counts": discipline_counts,
        "discipline_review_rule_counts": discipline_review_rule_counts,
        "records": records,
        "policy": "candidate_only; no formal discipline module writes are performed by this command",
    }
    index = {
        "status": "written",
        "source_root": str(root),
        "skills": records,
    }
    gap_lines = [
        "# Discipline Gap Report",
        "",
        "This report summarizes candidate-only coverage from the inspected skill source tree.",
        "",
        "## Plugin Type Counts",
        *[f"- {key}: {value}" for key, value in sorted(type_counts.items())],
        "",
        "## Support Candidate Counts",
        *[f"- {key}: {value}" for key, value in sorted(support_type_counts.items())],
        "",
        f"Review rule backflow links: {review_rule_backflow_count}",
        "",
        "## Discipline Candidate Counts",
        *[f"- {key}: {value}" for key, value in sorted(discipline_counts.items())],
        "",
        "## Discipline Review Rule Backflow",
        *[f"- {key}: {value}" for key, value in sorted(discipline_review_rule_counts.items())],
        "",
        "## Support Candidates With Review Rule Backflow",
        *[
            f"- {item['relative_path']} -> {item['support_type']} -> {len(item['review_rule_backflow_candidate_ids'])} review_rule candidates"
            for item in support_backflow_records
        ],
        "",
        "Support candidates stay outside `discipline_modules/`; only their validated `data_connector`, `method_template`, or `review_rule` backflow candidates can be promoted with explicit human confirmation.",
    ]
    _write_json(out / "COMPILE_SKILL_SOURCE_REPORT.json", report)
    _write_json(out / "SKILL_INDEX.json", index)
    (out / "DISCIPLINE_GAP_REPORT.md").write_text("\n".join(gap_lines), encoding="utf-8")
    return report
