"""Third-party source registry validation and guarded plugin promotion provenance."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def _resource_path(relative: str) -> Path:
    checkout = REPO_ROOT / relative
    if checkout.is_file():
        return checkout
    parts = Path(relative).parts
    share = Path(sys.prefix) / "share" / "draftpaper-cli"
    if parts[:1] == ("third_party",):
        if len(parts) == 2:
            return share / parts[-1]
        return share / "licenses" / Path(*parts[1:])
    return share / Path(relative).name


REGISTRY_PATH = _resource_path("third_party/registry.json")
NOTICES_PATH = _resource_path("third_party/THIRD_PARTY_NOTICES.md")


class ThirdPartyProvenanceError(RuntimeError):
    """Raised when a third-party source or candidate lacks verifiable provenance."""


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThirdPartyProvenanceError(f"Invalid third-party registry artifact {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ThirdPartyProvenanceError(f"Third-party registry artifact must be an object: {path}")
    return payload


def _source_index() -> dict[str, dict[str, Any]]:
    registry = _read(REGISTRY_PATH)
    return {
        str(item.get("source_id")): item
        for item in registry.get("sources") or []
        if isinstance(item, dict) and item.get("source_id")
    }


def validate_third_party_provenance() -> dict[str, Any]:
    sources = _source_index()
    issues = []
    required = {
        "source_id",
        "repository",
        "commit",
        "license_expression",
        "license_file",
        "use_mode",
        "local_paths",
        "copied_code",
        "copied_text",
        "review_status",
    }
    for source_id, item in sources.items():
        for field in required:
            if item.get(field) in (None, "", []):
                issues.append({"severity": "error", "kind": "missing_source_field", "source_id": source_id, "field": field})
        license_expression = str(item.get("license_expression") or "").lower()
        if "unknown" in license_expression or "noassertion" in license_expression:
            issues.append({"severity": "error", "kind": "unknown_license", "source_id": source_id})
        license_path = _resource_path(str(item.get("license_file") or ""))
        if not license_path.is_file():
            issues.append({"severity": "error", "kind": "license_file_missing", "source_id": source_id, "path": str(item.get("license_file"))})
        if item.get("copied_code") and not item.get("commit"):
            issues.append({"severity": "error", "kind": "copied_code_missing_commit", "source_id": source_id})
        for transitive in item.get("transitive_source_ids") or []:
            if str(transitive) not in sources:
                issues.append({"severity": "error", "kind": "missing_transitive_source", "source_id": source_id, "target": transitive})

    plugin_count = 0
    for manifest_path in (REPO_ROOT / "draftpaper_cli" / "discipline_modules").glob("*/*/*/manifest.json"):
        plugin_count += 1
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            issues.append({"severity": "error", "kind": "invalid_plugin_manifest", "path": str(manifest_path.relative_to(REPO_ROOT))})
            continue
        refs = [str(item) for item in manifest.get("upstream_refs") or []]
        for source_id in refs:
            if source_id not in sources:
                issues.append({"severity": "error", "kind": "unknown_plugin_upstream_ref", "path": str(manifest_path.relative_to(REPO_ROOT)), "source_id": source_id})
        if manifest.get("copied_code") is True:
            for field in ("original_repository", "original_skill_path", "upstream_commit", "license_spdx_or_expression"):
                if not manifest.get(field):
                    issues.append({"severity": "error", "kind": "copied_plugin_missing_provenance", "path": str(manifest_path.relative_to(REPO_ROOT)), "field": field})
    return {
        "status": "passed" if not [item for item in issues if item["severity"] == "error"] else "failed",
        "source_count": len(sources),
        "formal_plugin_count": plugin_count,
        "notices_present": NOTICES_PATH.is_file(),
        "issues": issues,
    }


def validate_candidate_promotion_provenance(candidate: dict[str, Any]) -> dict[str, Any]:
    source = str(candidate.get("source") or candidate.get("source_type") or "first_party").strip().lower()
    first_party = source in {"", "first_party", "local", "project_local", "draftpaper"}
    if first_party:
        return {
            "derivation_kind": "first_party",
            "upstream_refs": [],
            "copied_code": False,
            "copied_text": False,
            "provenance_reviewed_at": candidate.get("provenance_reviewed_at") or "promotion_time",
        }
    upstream_refs = [str(item) for item in candidate.get("upstream_refs") or []]
    if source == "academicforge" and "academicforge" not in upstream_refs:
        upstream_refs.insert(0, "academicforge")
    required = [
        "catalog_ref",
        "original_repository",
        "original_skill_path",
        "upstream_commit",
        "license_spdx_or_expression",
        "derivation_kind",
    ]
    missing = [field for field in required if candidate.get(field) in (None, "")]
    if missing:
        raise ThirdPartyProvenanceError(
            "External plugin promotion requires direct and transitive provenance; missing: " + ", ".join(missing)
        )
    license_expression = str(candidate.get("license_spdx_or_expression") or "").lower()
    if "unknown" in license_expression or "tbd" in license_expression or "noassertion" in license_expression:
        raise ThirdPartyProvenanceError("License-unknown candidates must remain project-local and cannot be promoted.")
    copied_code = bool(candidate.get("copied_code"))
    copied_text = bool(candidate.get("copied_text"))
    if copied_code and not candidate.get("source_code_path"):
        raise ThirdPartyProvenanceError("copied_code=true requires source_code_path in addition to repository, commit and license.")
    sources = _source_index()
    unknown_refs = [item for item in upstream_refs if item not in sources]
    if unknown_refs:
        raise ThirdPartyProvenanceError("Candidate upstream_refs are absent from third_party/registry.json: " + ", ".join(unknown_refs))
    return {
        "upstream_refs": upstream_refs,
        "catalog_ref": candidate.get("catalog_ref"),
        "original_repository": candidate.get("original_repository"),
        "original_skill_path": candidate.get("original_skill_path"),
        "upstream_commit": candidate.get("upstream_commit"),
        "license_spdx_or_expression": candidate.get("license_spdx_or_expression"),
        "license_file": candidate.get("license_file"),
        "derivation_kind": candidate.get("derivation_kind"),
        "copied_code": copied_code,
        "copied_text": copied_text,
        "transformed_fields": list(candidate.get("transformed_fields") or []),
        "attribution_required": bool(candidate.get("attribution_required", True)),
        "provenance_reviewed_at": candidate.get("provenance_reviewed_at") or "promotion_time",
    }


def render_third_party_notices() -> dict[str, Any]:
    sources = _source_index()
    lines = ["# Third-Party Notices", "", "Generated from `third_party/registry.json`.", ""]
    for source_id, item in sorted(sources.items()):
        lines.extend(
            [
                f"## {item.get('name') or source_id}",
                "",
                f"- Repository: {item.get('repository')}",
                f"- Commit: `{item.get('commit')}`",
                f"- License: `{item.get('license_expression')}`",
                f"- Use mode: `{item.get('use_mode')}`",
                f"- Copied code: `{str(bool(item.get('copied_code'))).lower()}`",
                f"- License file: `{item.get('license_file')}`",
                "",
            ]
        )
    NOTICES_PATH.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "written", "source_count": len(sources), "notices": str(NOTICES_PATH.relative_to(REPO_ROOT))}
