"""Domain-neutral provenance, cohort, and analysis-view contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now


DATA_PROVENANCE_CONTRACT = "data/data_provenance_contract.json"
COHORT_REGISTRY = "data/cohort_registry.json"
COHORT_VIEW_REGISTRY = "data/cohort_view_registry.json"
JOIN_FILTER_LEDGER = "data/join_and_filter_ledger.jsonl"


class CohortSemanticError(RuntimeError):
    """Raised when data provenance or cohort-view semantics are inconsistent."""


@dataclass(frozen=True)
class SemanticIssue:
    code: str
    message: str
    artifact_id: str = ""
    blocking: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "artifact_id": self.artifact_id,
            "blocking": self.blocking,
        }


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _stable_id(prefix: str, payload: Any) -> str:
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def validate_data_provenance(contract: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[SemanticIssue] = []
    for source in contract.get("sources") or []:
        if not isinstance(source, dict):
            issues.append(SemanticIssue("invalid_data_source", "Each provenance source must be an object."))
            continue
        source_id = str(source.get("data_source_id") or "")
        if not source_id:
            issues.append(SemanticIssue("missing_data_source_id", "Every data source requires data_source_id."))
        for field in ("source_type", "access_boundary", "version_status"):
            if not str(source.get(field) or "").strip():
                issues.append(SemanticIssue(f"missing_{field}", f"Data source {source_id or '<unknown>'} lacks {field}.", source_id))
        if source.get("version_status") == "known" and not str(source.get("release_or_version") or "").strip():
            issues.append(SemanticIssue("known_version_without_value", f"Data source {source_id} declares a known version without its value.", source_id))
    return [item.as_dict() for item in issues]


def _registry_items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in payload.get(key) or [] if isinstance(item, dict)]


def validate_cohort_registries(
    cohort_registry: dict[str, Any],
    view_registry: dict[str, Any],
    bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cohorts = _registry_items(cohort_registry, "cohorts")
    views = _registry_items(view_registry, "views")
    issues: list[SemanticIssue] = []
    cohort_index: dict[str, dict[str, Any]] = {}
    for cohort in cohorts:
        cohort_id = str(cohort.get("cohort_id") or "")
        if not cohort_id:
            issues.append(SemanticIssue("missing_cohort_id", "Every cohort requires cohort_id."))
            continue
        if cohort_id in cohort_index:
            issues.append(SemanticIssue("duplicate_cohort_id", f"Duplicate cohort_id {cohort_id}.", cohort_id))
        cohort_index[cohort_id] = cohort
        if not str(cohort.get("sample_unit") or "").strip():
            issues.append(SemanticIssue("missing_sample_unit", f"Cohort {cohort_id} lacks sample_unit.", cohort_id))
        parent_id = str(cohort.get("parent_cohort_id") or "")
        if parent_id and parent_id not in {str(item.get("cohort_id") or "") for item in cohorts}:
            issues.append(SemanticIssue("unknown_parent_cohort", f"Cohort {cohort_id} refers to unknown parent {parent_id}.", cohort_id))
        count = cohort.get("count")
        if count is not None and (not isinstance(count, int) or count < 0):
            issues.append(SemanticIssue("invalid_cohort_count", f"Cohort {cohort_id} count must be a non-negative integer.", cohort_id))
    for cohort in cohorts:
        parent = cohort_index.get(str(cohort.get("parent_cohort_id") or ""))
        if parent and isinstance(parent.get("count"), int) and isinstance(cohort.get("count"), int) and cohort["count"] > parent["count"]:
            issues.append(SemanticIssue("child_count_exceeds_parent", f"Cohort {cohort.get('cohort_id')} count exceeds parent cohort count.", str(cohort.get("cohort_id"))))

    view_index: dict[str, dict[str, Any]] = {}
    for view in views:
        view_id = str(view.get("cohort_view_id") or "")
        parent_id = str(view.get("parent_cohort_id") or "")
        if not view_id:
            issues.append(SemanticIssue("missing_cohort_view_id", "Every cohort view requires cohort_view_id."))
            continue
        if view_id in view_index:
            issues.append(SemanticIssue("duplicate_cohort_view_id", f"Duplicate cohort_view_id {view_id}.", view_id))
        view_index[view_id] = view
        parent = cohort_index.get(parent_id)
        if parent is None:
            issues.append(SemanticIssue("unknown_view_parent", f"Cohort view {view_id} refers to unknown parent {parent_id}.", view_id))
        if not str(view.get("sample_unit") or "").strip():
            issues.append(SemanticIssue("missing_view_sample_unit", f"Cohort view {view_id} lacks sample_unit.", view_id))
        elif parent and str(parent.get("sample_unit")) != str(view.get("sample_unit")) and not view.get("unit_conversion_contract"):
            issues.append(SemanticIssue("silent_sample_unit_change", f"Cohort view {view_id} changes sample unit without a conversion contract.", view_id))
        if not str(view.get("missingness_policy") or "").strip():
            issues.append(SemanticIssue("missing_missingness_policy", f"Cohort view {view_id} lacks missingness_policy.", view_id))
        if not view.get("allowed_uses"):
            issues.append(SemanticIssue("missing_allowed_uses", f"Cohort view {view_id} must declare allowed_uses.", view_id))
        count = view.get("count")
        if parent and isinstance(count, int) and isinstance(parent.get("count"), int) and count > parent["count"]:
            issues.append(SemanticIssue("view_count_exceeds_parent", f"Cohort view {view_id} count exceeds parent cohort count.", view_id))

    for binding in bindings or []:
        if not isinstance(binding, dict):
            continue
        artifact_id = str(binding.get("artifact_id") or binding.get("panel_id") or binding.get("estimand_id") or "artifact")
        view_id = str(binding.get("cohort_view_id") or "")
        if not view_id:
            issues.append(SemanticIssue("artifact_missing_cohort_view", f"{artifact_id} must bind an explicit cohort_view_id.", artifact_id))
            continue
        view = view_index.get(view_id)
        if view is None:
            issues.append(SemanticIssue("artifact_unknown_cohort_view", f"{artifact_id} binds unknown cohort view {view_id}.", artifact_id))
            continue
        declared_count = binding.get("count")
        if isinstance(declared_count, int) and isinstance(view.get("count"), int) and declared_count != view["count"]:
            issues.append(SemanticIssue("artifact_cohort_count_mismatch", f"{artifact_id} count {declared_count} differs from cohort view {view_id} count {view['count']}.", artifact_id))
        declared_unit = str(binding.get("sample_unit") or "")
        if declared_unit and declared_unit != str(view.get("sample_unit") or ""):
            issues.append(SemanticIssue("artifact_sample_unit_mismatch", f"{artifact_id} sample unit {declared_unit} differs from cohort view {view_id}.", artifact_id))

    blocking = [item.as_dict() for item in issues if item.blocking]
    return {
        "decision": "blocked" if blocking else "pass",
        "issues": [item.as_dict() for item in issues],
        "blocking_issues": blocking,
        "cohort_count": len(cohorts),
        "cohort_view_count": len(views),
    }


def build_data_semantic_contracts(project: str | Path) -> dict[str, Any]:
    """Build a conservative semantic baseline; unknown provenance remains explicit."""
    root = Path(project)
    inventory = _read_json(root / "data" / "data_inventory.json", {})
    files = [item for item in inventory.get("files") or [] if isinstance(item, dict)]
    sources: list[dict[str, Any]] = []
    for index, item in enumerate(files, start=1):
        relative = str(item.get("relative_path") or item.get("path") or item.get("name") or f"source_{index}")
        sources.append({
            "data_source_id": _stable_id("data_source", relative),
            "source_type": str(item.get("kind") or "project_data_asset"),
            "public_name": str(item.get("public_name") or Path(relative).name),
            "release_or_version": item.get("release_or_version"),
            "version_status": "known" if item.get("release_or_version") else "unknown",
            "access_boundary": str(item.get("access_boundary") or "project_private_locator"),
            "locator_disclosure": "private",
            "checksum": item.get("sha256"),
            "label_provenance": item.get("label_provenance") or "unknown",
        })
    if not sources:
        sources.append({
            "data_source_id": "data_source:unresolved",
            "source_type": "unresolved",
            "public_name": "Unresolved project data source",
            "release_or_version": None,
            "version_status": "unknown",
            "access_boundary": "unknown",
            "locator_disclosure": "none",
            "checksum": None,
            "label_provenance": "unknown",
        })
    provenance = {
        "schema_version": "dpl.data_provenance_contract.v1",
        "generated_at": utc_now(),
        "sources": sources,
        "unknown_fields_narrow_claims": True,
    }
    total = inventory.get("total_rows")
    sample_unit = str(inventory.get("sample_unit") or "record")
    cohort = {
        "cohort_id": "cohort:inventory_all",
        "parent_cohort_id": None,
        "data_source_ids": [item["data_source_id"] for item in sources],
        "sample_unit": sample_unit,
        "source_release": [item.get("release_or_version") for item in sources if item.get("release_or_version")],
        "selection_expression": "all inventoried records",
        "join_keys": list(inventory.get("join_keys") or []),
        "duplicate_policy": str(inventory.get("duplicate_policy") or "unknown"),
        "count": int(total) if isinstance(total, int) else None,
        "split_unit": str(inventory.get("split_unit") or sample_unit),
        "group_unit": str(inventory.get("group_unit") or sample_unit),
        "label_source": str(inventory.get("label_source") or "unknown"),
    }
    cohorts = {"schema_version": "dpl.cohort_registry.v1", "generated_at": utc_now(), "cohorts": [cohort]}
    view = {
        "cohort_view_id": "cohort_view:inventory_all",
        "parent_cohort_id": cohort["cohort_id"],
        "filter_expression": "true",
        "sample_unit": sample_unit,
        "count": cohort["count"],
        "missingness_policy": str(inventory.get("missingness_policy") or "report_missingness_without_silent_exclusion"),
        "split_id": str(inventory.get("split_id") or "not_yet_assigned"),
        "allowed_uses": ["descriptive_inventory"],
        "claim_boundary": "Descriptive use only until an analysis-specific view is registered.",
    }
    views = {"schema_version": "dpl.cohort_view_registry.v1", "generated_at": utc_now(), "views": [view]}
    validation = validate_cohort_registries(cohorts, views)
    provenance["validation"] = {"decision": "blocked" if validate_data_provenance(provenance) else "pass", "issues": validate_data_provenance(provenance)}
    views["validation"] = validation
    _write_json(root / DATA_PROVENANCE_CONTRACT, provenance)
    _write_json(root / COHORT_REGISTRY, cohorts)
    _write_json(root / COHORT_VIEW_REGISTRY, views)
    ledger = root / JOIN_FILTER_LEDGER
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists():
        ledger.write_text("", encoding="utf-8")
    return {
        "decision": "pass" if validation["decision"] == "pass" else "blocked",
        "data_provenance_contract": DATA_PROVENANCE_CONTRACT,
        "cohort_registry": COHORT_REGISTRY,
        "cohort_view_registry": COHORT_VIEW_REGISTRY,
        "join_and_filter_ledger": JOIN_FILTER_LEDGER,
        "validation": validation,
    }
