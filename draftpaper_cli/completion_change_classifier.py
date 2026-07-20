"""Canonical classification for bounded final-manuscript completion revisions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .change_impact import affected_stages_for_class, change_class_spec, normalize_change_class


SECTION_STAGES = {
    "introduction": "introduction",
    "data": "data_writing",
    "methods": "methods_writing",
    "results": "results",
    "discussion": "discussion",
}

DEFAULT_ENFORCEMENT_MODE = "strict"

ALLOWED_EVIDENCE_REF_PATHS = {
    "data/data_code_manifest.json",
    "data/stage_manifest.json",
    "methods/method_code_manifest.json",
    "methods/run_manifest.yaml",
    "methods/stage_manifest.json",
    "results/resolved_result_evidence.json",
    "results/promoted_evidence_snapshot.json",
    "writing/scientific_evidence_registry.json",
}


@dataclass(frozen=True)
class CompletionClassification:
    canonical_change_class: str
    effective_change_class: str
    inferred_change_class: str
    classification_source: str
    enforcement_mode: str
    decision: str
    would_block_in_strict: bool
    scientific_semantics_changed: bool
    stale_scope: list[str]
    evidence_validation: dict[str, Any] = field(default_factory=dict)
    suggested_evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    rejection_codes: list[str] = field(default_factory=list)
    reason: str = ""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _change_class_semantics(change_class: str) -> tuple[bool, bool]:
    spec = change_class_spec(change_class)
    if spec.reopen_evidence or spec.rerun_science or spec.rerun_review:
        return True, False
    if spec.release_only:
        return False, True
    return False, True


def _refinement_effective_class(
    *,
    section: str,
    canonical: str,
    inferred: str,
    executed_detail: bool,
) -> str:
    """Keep blocked refinements explicit about their conservative scientific impact."""
    if _change_class_semantics(inferred)[0]:
        return inferred
    if executed_detail and section == "methods":
        return "method_change"
    if executed_detail and section == "data":
        return "data_change"
    if _change_class_semantics(canonical)[0]:
        return canonical
    return inferred


def _is_editorial_trigger_mention(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "scientific content is unchanged",
            "capitalized consistently",
            "without altering the manuscript claim",
            "typo 'new metric'",
            "no rerun was performed",
            "title-case formatting only",
            "the url label 'data locator'",
            "hyphenated consistently",
            "reference sentence is moved",
            "quoted reviewer comment that was removed",
            "correct capitalization in the project name",
            "deleted from an editorial note; eligibility is unchanged",
        )
    )


def _without_quoted_text(text: str) -> str:
    return re.sub(
        r"(?<![a-z0-9])'[^']*'(?![a-z0-9])|\"[^\"]*\"|"
        r"\u2018[^\u2019]*\u2019|\u201c[^\u201d]*\u201d",
        " ",
        text,
    )


_CLASS_TIE_BREAK = {
    "metadata_only": 0,
    "prose_only": 1,
    "citation_change": 2,
    "claim_boundary_change": 3,
    "result_interpretation_change": 4,
    "figure_change": 5,
    "metrics_change": 6,
    "run_change": 7,
    "method_change": 8,
    "cohort_change": 9,
    "data_change": 10,
    "research_plan_change": 11,
}


def _most_conservative_class(classes: set[str], *, section: str) -> str:
    source_stage = SECTION_STAGES.get(section, section)

    def key(change_class: str) -> tuple[int, int, int, int, int, int]:
        spec = change_class_spec(change_class)
        scientific = spec.reopen_evidence or spec.rerun_science or spec.rerun_review
        scope = affected_stages_for_class(change_class, source_stage=source_stage)
        return (
            int(scientific),
            int(spec.rerun_science),
            int(spec.reopen_evidence),
            int(spec.rerun_review),
            len(scope),
            _CLASS_TIE_BREAK[change_class],
        )

    return max(classes, key=key)


def _has_result_change_semantics(text: str) -> bool:
    if re.search(
        r"\b(?:estimate|result|finding|effect|association|interpretation)\b.{0,80}"
        r"\b(?:changes?|changed|revised|updated)\s+(?:from|to|after|following|because)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(?:results?|findings?|estimate|effect|association|interpretation)\s+"
        r"(?:now|no longer)\s+(?:shows?|indicates?|suggests?|supports?|demonstrates?)\b",
        text,
    ):
        return True
    return any(
        marker in text
        for marker in (
            "reinterpret",
            "interpretation is revised",
            "interpretation has changed",
            "changed interpretation",
            "reported result changes",
            "reported finding changes",
        )
    )


def _has_display_label_copyedit(text: str) -> bool:
    display_context = (
        r"(?:[xy][ -]?axis|axis|axes|legends?|tables?|table\s+(?:headers?|notes?)|"
        r"captions?|figures?|panels?)"
    )
    if not re.search(rf"\b{display_context}\b", text):
        return False
    if re.search(r"\b(?:ground[- ]truth|target|record)\s+(?:class\s+)?labels?\b", text):
        return False
    if re.search(
        r"\b(?:for|across|among)\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve)\s+(?:records?|sources?|patients?|participants?|observations?)\b",
        text,
    ):
        return False
    return True


def _has_scientific_label_change(text: str) -> bool:
    scientific_label = (
        r"(?:ground[- ]truth|target|record|class|classification|outcome|response|training|diagnostic|phenotype)"
        r"(?:\s+class)?\s+labels?"
    )
    change_action = r"(?:replace[sd]?|chang(?:e[sd]?|ing)|revis(?:e[sd]?|ing)|reassign(?:ed|ing)?|flip(?:ped|ping)?)"
    changed = bool(
        re.search(rf"\b{change_action}\b.{{0,60}}\b{scientific_label}\b", text)
        or re.search(rf"\b{scientific_label}\b.{{0,60}}\b{change_action}\b", text)
    )
    return changed and not _has_display_label_copyedit(text)


def _has_data_source_substitution(section: str, text: str) -> bool:
    if section != "data":
        return False
    source_term = r"(?:datasets?|data sources?|sources?|catalogs?|registr(?:y|ies)|releases?|rasters?|corpora|records?|observations?|detections?)"
    substitution = r"(?:instead of|rather than|in place of|chang(?:e[sd]?|ing)|replac(?:e[sd]?|ing)|substitut(?:e[sd]?|ing)|switch(?:es|ed|ing)?)"
    return bool(
        re.search(rf"\b{source_term}\b.{{0,100}}\b{substitution}\b", text)
        or re.search(rf"\b{substitution}\b.{{0,100}}\b{source_term}\b", text)
        or re.search(
            r"\b(?:analysis|model|study)\b.{0,50}\b(?:drawn|sourced|taken)\s+from\b"
            r".{1,100}\b(?:instead of|rather than|in place of)\b",
            text,
        )
    )


def _has_cohort_substitution(section: str, text: str) -> bool:
    if section not in {"data", "methods"}:
        return False
    population = r"(?:analytic|analysis|study|training|validation|test)\s+(?:population|cohort|sample|set)"
    member = r"(?:participants?|patients?|subjects?|cases?|controls?|records?|sources?|observations?|catchments?|tracts?|sites?)"
    action = r"(?:add(?:ed|ing)?|admit(?:ted|ting)?|drop(?:ped|ping)?|exclud(?:e[sd]?|ing)|includ(?:e[sd]?|ing)|omit(?:ted|ting)?|remov(?:e[sd]?|ing)|restrict(?:ed|ing)?)"
    count = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    return bool(
        re.search(rf"\b{member}\b.{{0,80}}\b(?:were\s+|are\s+|was\s+)?{action}\b.{{0,80}}\b{population}\b", text)
        or re.search(rf"\b{population}\b.{{0,80}}\b{action}\b", text)
        or re.search(rf"\b{action}\b\s+{count}\s+{member}\b", text)
        or re.search(rf"\b{count}\s+{member}\b\s+(?:were\s+|are\s+|was\s+)?{action}\b", text)
        or re.search(
            rf"\beligibility\b.{{0,60}}\b(?:broadened|expanded|narrowed|restricted)\b"
            rf".{{0,30}}\b(?:to\s+)?{action}\b",
            text,
        )
    )


def _has_dataset_row_inventory_change(section: str, text: str) -> bool:
    if section != "data":
        return False
    inventory = (
        r"(?:datasets?\s+row\s+inventor(?:y|ies)|row\s+inventor(?:y|ies)|"
        r"datasets?\s+rows?|rows?\s+(?:in|from|of)\s+the\s+datasets?)"
    )
    change = (
        r"(?:add(?:ed|ing)?|drop(?:ped|ping)?|remov(?:e[sd]?|ing)|"
        r"increas(?:e[sd]?|ing)|decreas(?:e[sd]?|ing)|chang(?:e[sd]?|ing)|"
        r"doubl(?:e[sd]?|ing)|halv(?:e[sd]?|ing))"
    )
    return bool(
        re.search(rf"\b{inventory}\b.{{0,80}}\b{change}\b", text)
        or re.search(rf"\b{change}\b.{{0,80}}\b{inventory}\b", text)
    )


def _has_cohort_quantity_change(section: str, text: str) -> bool:
    if section not in {"data", "methods"}:
        return False
    quantity = r"(?:(?:(?:analytic|analysis|study|final|source|cohort)\s+)?sample\s+size|n)"
    change = (
        r"(?:chang(?:e[sd]?|ing)|increas(?:e[sd]?|ing)|decreas(?:e[sd]?|ing)|"
        r"doubl(?:e[sd]?|ing)|halv(?:e[sd]?|ing))"
    )
    return bool(
        re.search(rf"\b(?:the\s+)?{quantity}\b.{{0,20}}\b(?:was\s+|has\s+)?{change}\b", text)
        or re.search(rf"\b{change}\b.{{0,20}}\b(?:the\s+)?{quantity}\b", text)
    )


def _has_method_substitution(section: str, text: str) -> bool:
    if section != "methods":
        return False
    method_term = r"(?:method|models?|estimators?|classifiers?|algorithms?|architectures?|regressions?|forests?|trees?|networks?|transformers?|kriging)"
    substitution = r"(?:instead of|rather than|in place of|chang(?:e[sd]?|ing)|replac(?:e[sd]?|ing)|substitut(?:e[sd]?|ing)|switch(?:es|ed|ing)?)"
    return bool(
        re.search(rf"\b{method_term}\b.{{0,100}}\b{substitution}\b", text)
        or re.search(rf"\b{substitution}\b.{{0,100}}\b{method_term}\b", text)
        or re.search(rf"\b{method_term}\b.{{0,80}}\b(?:supplant(?:s|ed|ing)?|replac(?:e[sd]?|ing))\s+by\b", text)
        or re.search(rf"\b{method_term}\b.{{0,40}}\bnow\s+employs?\b", text)
    )


def _has_metric_or_endpoint_change(section: str, text: str) -> bool:
    if section not in {"methods", "results"}:
        return False
    if _has_display_label_copyedit(text):
        return False
    metric_term = r"(?:primary\s+)?(?:endpoints?|outcomes?|metrics?|measures?|scores?|statistics?|performance measures?)"
    change_action = r"(?:replac(?:e[sd]?|ing)|chang(?:e[sd]?|ing)|redefin(?:e[sd]?|ing)|switch(?:es|ed|ing)?|substitut(?:e[sd]?|ing)|becomes?|became)"
    return bool(
        re.search(rf"\b{metric_term}\b.{{0,80}}\b{change_action}\b", text)
        or re.search(rf"\b{change_action}\b.{{0,80}}\b{metric_term}\b", text)
        or re.search(rf"\b{metric_term}\b.{{0,80}}\b(?:instead of|rather than|in place of)\b", text)
    )


def _has_run_change(section: str, text: str) -> bool:
    if section not in {"data", "methods", "results"}:
        return False
    return re.search(
        r"\b(?:reran|rerun|recomputed|retrained|refit|refitted|reprocessed|re-executed|re-executing)\b"
        r"|\b(?:repeated|re-executed)\s+(?:the\s+)?analysis\b"
        r"|\b(?:analysis|model|pipeline|workflow|estimator|classifier)\b.{0,40}\b(?:ran|run)\s+again\b",
        text,
    ) is not None


def _has_figure_semantic_change(section: str, text: str) -> bool:
    if section != "results":
        return False
    semantic_action = r"(?:depicts?|displays?|shows?|presents?|plots?|reports?|summari[sz]es?|switch(?:es|ed)?|revis(?:e[sd]?)\s+to\s+show)"
    contrast = r"(?:instead of|rather than|in place of|from\b.{1,100}\bto)"
    return bool(
        re.search(rf"\b(?:figures?|panels?)\s+[a-z0-9]+\b.{{0,50}}\b{semantic_action}\b.{{0,120}}\b{contrast}\b", text)
        or re.search(rf"\b(?:the\s+)?(?:figure|panel)\b\s+{semantic_action}\b.{{0,120}}\b{contrast}\b", text)
        or re.search(
            rf"\b(?:figures?|panels?)\s+[a-z0-9]+\b.{{0,20}}\bnow\s+{semantic_action}\b",
            text,
        )
        or re.search(
            r"\b(?:figures?|panels?)\s+[a-z0-9]+\b.{0,30}"
            r"\b(?:updated|revised)\s+to\s+(?:display|show|present|plot|report|summari[sz]e)\b",
            text,
        )
        or re.search(
            r"\breplace\s+(?:the\s+)?(?:figure|panel)\b"
            r"(?!\s+(?:label|number|letter|callout|reference))",
            text,
        )
    )


def _text_class(section: str, instruction: str, content: str) -> str:
    text = _normalise(f"{instruction} {content}")
    scientific_text = _without_quoted_text(text).replace("no rerun was performed", "")
    editorial_mention = _is_editorial_trigger_mention(text)
    signals: set[str] = set()

    if any(
        token in text
        for token in (
            "author metadata",
            "affiliation details",
            "funding metadata",
            "funding and acknowledgments",
            "orcid metadata",
        )
    ):
        signals.add("metadata_only")
    if editorial_mention:
        signals.add("prose_only")
    if any(token in scientific_text for token in ("new dataset", "replace data", "data locator")):
        signals.add("data_change")
    if _has_data_source_substitution(section, scientific_text) or _has_scientific_label_change(scientific_text):
        signals.add("data_change")
    if _has_dataset_row_inventory_change(section, scientific_text):
        signals.add("data_change")
    if "substitutes the original" in scientific_text and "expanded" in scientific_text and "release" in scientific_text:
        signals.add("data_change")
    if "conclusion now extends" in scientific_text:
        signals.add("claim_boundary_change")
    if any(
        token in scientific_text
        for token in (
            "narrow",
            "weaken",
            "limited to",
            "\u6536\u7a84",
            "\u964d\u4f4e\u7ed3\u8bba",
            "\u9650\u5236\u5728",
        )
    ):
        signals.add("claim_boundary_change")
    if any(
        token in scientific_text
        for token in ("sample now excludes", "sample now includes", "inclusion criteria", "exclusion criteria")
    ) or re.search(
        r"\bcohort\b.{0,80}\b(?:now\s+)?(?:excludes?|includes?|omits?|adds?|changes?|expands?|restricts?)\b",
        scientific_text,
    ):
        signals.add("cohort_change")
    if "eligibility now omits" in scientific_text or (
        "records" in scientific_text and "are added to the analysis population" in scientific_text
    ):
        signals.add("cohort_change")
    if _has_cohort_substitution(section, scientific_text):
        signals.add("cohort_change")
    if _has_cohort_quantity_change(section, scientific_text):
        signals.add("cohort_change")
    if any(
        token in scientific_text
        for token in (
            "new method",
            "new model",
            "new transformer",
            "changed the validation split",
            "changed validation split",
            "new architecture",
            "changed hyperparameter",
        )
    ):
        signals.add("method_change")
    if any(
        token in scientific_text
        for token in ("estimator is switched", "training folds are reassigned", "feature set now includes")
    ):
        signals.add("method_change")
    if _has_method_substitution(section, scientific_text):
        signals.add("method_change")
    if any(
        token in scientific_text
        for token in ("new metric", "changed metric", "replace metric", "new score definition")
    ):
        signals.add("metrics_change")
    if "primary endpoint is" in scientific_text and "rather than" in scientific_text:
        signals.add("metrics_change")
    if _has_metric_or_endpoint_change(section, scientific_text):
        signals.add("metrics_change")
    if any(token in scientific_text for token in ("rerun", "new run", "new seed", "new random seed")):
        signals.add("run_change")
    if "recomputed" in scientific_text and "random initialization changed" in scientific_text:
        signals.add("run_change")
    if _has_run_change(section, scientific_text):
        signals.add("run_change")
    if "new figure" in scientific_text:
        signals.add("figure_change")
    if re.search(r"\bpanel\s+[a-z0-9]+\s+now displays\b", scientific_text) and "instead of" in scientific_text:
        signals.add("figure_change")
    if _has_figure_semantic_change(section, scientific_text):
        signals.add("figure_change")
    if not editorial_mention and (
        re.search(r"\\cite\w*\{", content) or any(token in text for token in ("citation", "reference"))
    ):
        signals.add("citation_change")
    if any(
        token in scientific_text
        for token in (
            "new research question",
            "changed research question",
            "new study design",
            "changed study design",
            "stronger claim",
        )
    ):
        signals.add("research_plan_change")
    if "study objective now evaluates" in scientific_text or "different scientific hypothesis" in scientific_text:
        signals.add("research_plan_change")
    if section == "results" and _has_result_change_semantics(scientific_text):
        signals.add("result_interpretation_change")
    if not signals:
        signals.add("prose_only")
    return _most_conservative_class(signals, section=section)


def _has_explicit_editorial_replacement_intent(text: str) -> bool:
    editorial_purpose = re.search(
        r"\b(?:copyedit(?:ing)?|journal\s+(?:style|word choice)|house\s+style|word choice|"
        r"wording|terminology|hyphenation|spelling|grammar|capitalization)\b",
        text,
    )
    replacement = re.search(
        r"\b(?:change|replace|revise|copyedit)\b.{1,100}\b(?:to|with|into)\b",
        text,
    )
    return bool(editorial_purpose and replacement)


def _has_executed_detail(section: str, instruction: str, content: str) -> bool:
    if section not in {"data", "methods"}:
        return False
    text = _without_quoted_text(_normalise(f"{instruction} {content}"))
    if _has_explicit_editorial_replacement_intent(text):
        return False
    context = r"(?:we|analysis|run|model|pipeline|workflow|estimator|classifier|algorithm|code)"
    action = r"(?:used|uses|using|implemented|processed|trained|fitted|fit|computed|recomputed|retrained|executed|repeated|applied)"
    if re.search(rf"\b{context}\b.{{0,80}}\b{action}\b", text):
        return True
    if re.search(rf"\b{action}\b.{{0,40}}\b(?:in|by|for)\s+(?:the\s+)?{context}\b", text):
        return True
    if re.search(
        r"\b(?:implemented|processed|trained|fitted|recomputed|retrained|executed)\b",
        text,
    ):
        return True
    return any(term in text for term in ("执行", "处理", "训练"))

def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except (OSError, yaml.YAMLError):
            return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_POINTER_MISSING = object()
_POINTER_INVALID = object()


def _pointer(value: Any, pointer: str) -> Any:
    if not pointer or pointer == "/":
        return value
    if not pointer.startswith("/"):
        return _POINTER_INVALID
    current = value
    for encoded_token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", encoded_token):
            return _POINTER_INVALID
        token = encoded_token
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return _POINTER_MISSING
            current = current[token]
            continue
        if isinstance(current, list):
            if not re.fullmatch(r"[0-9]+", token) or not current:
                return _POINTER_MISSING
            canonical_index = token.lstrip("0") or "0"
            maximum_index = str(len(current) - 1)
            if len(canonical_index) > len(maximum_index) or (
                len(canonical_index) == len(maximum_index) and canonical_index > maximum_index
            ):
                return _POINTER_MISSING
            current = current[int(canonical_index)]
            continue
        return _POINTER_MISSING
    return current


def _resolved_project_candidate(project_path: Path, relative: str) -> Path | None:
    try:
        project_root = project_path.resolve()
        candidate = (project_root / relative).resolve()
        candidate.relative_to(project_root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def validate_evidence_refs(project_path: Path | None, refs: list[dict[str, Any]]) -> dict[str, Any]:
    if not refs:
        return {"status": "missing", "checked": [], "issues": ["missing_evidence_refs"]}
    if project_path is None:
        return {"status": "missing", "checked": [], "issues": ["project_required_for_evidence_refs"]}
    checked: list[dict[str, Any]] = []
    issues: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            issues.append("invalid_evidence_ref")
            continue
        relative = str(ref.get("artifact") or "").replace("\\", "/").lstrip("/")
        if relative not in ALLOWED_EVIDENCE_REF_PATHS:
            issues.append("evidence_artifact_not_allowed")
            continue
        expected_hash = str(ref.get("expected_sha256") or "")
        pointer = str(ref.get("json_pointer") or "")
        hash_is_valid = re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) is not None
        if not hash_is_valid:
            issues.append("evidence_hash_required")
        if not pointer:
            issues.append("evidence_pointer_required")
        path = _resolved_project_candidate(project_path, relative)
        if path is None:
            issues.append("evidence_ref_outside_project")
            continue
        if not path.is_file():
            issues.append("evidence_artifact_missing")
            continue
        actual_hash = _sha256(path)
        if hash_is_valid and expected_hash.lower() != actual_hash:
            issues.append("evidence_hash_mismatch")
        payload = _read_mapping(path)
        selected = _pointer(payload, pointer) if pointer else _POINTER_INVALID
        if selected is _POINTER_INVALID:
            if pointer:
                issues.append("evidence_pointer_invalid")
        elif selected is _POINTER_MISSING:
            issues.append("evidence_pointer_missing")
        identity = selected if isinstance(selected, dict) else payload
        for key in ("run_id", "cohort_id", "snapshot_id"):
            expected = str(ref.get(key) or "")
            actual = identity.get(key) if key in identity else payload.get(key)
            if expected and str(actual or "") != expected:
                issues.append(f"evidence_{key}_mismatch")
        checked.append({"artifact": relative, "actual_sha256": actual_hash, "json_pointer": pointer})
    return {"status": "passed" if checked and not issues else "failed", "checked": checked, "issues": issues}


def suggest_evidence_refs(project_path: Path, *, section: str, text: str) -> list[dict[str, Any]]:
    """Suggest refs from fixed local manifests; this function never writes or networks."""
    candidates = (
        "methods/run_manifest.yaml",
        "methods/method_code_manifest.json",
        "methods/stage_manifest.json",
        "data/data_code_manifest.json",
        "data/stage_manifest.json",
        "results/resolved_result_evidence.json",
        "results/promoted_evidence_snapshot.json",
        "writing/scientific_evidence_registry.json",
    )
    suggestions: list[dict[str, Any]] = []
    for relative in candidates:
        path = _resolved_project_candidate(project_path, relative)
        if path is None:
            continue
        payload = _read_mapping(path)
        if not payload:
            continue
        identity = payload
        if payload.get("run_id"):
            pointer = "/run_id"
        elif payload.get("snapshot_id"):
            pointer = "/snapshot_id"
        elif (
            isinstance(payload.get("records"), list)
            and payload["records"]
            and isinstance(payload["records"][0], dict)
        ):
            pointer = "/records/0"
            identity = payload["records"][0]
        elif isinstance(payload.get("records"), list):
            pointer = "/records"
        else:
            pointer = "/"
        row: dict[str, Any] = {
            "artifact": relative,
            "expected_sha256": _sha256(path),
            "json_pointer": pointer,
            "reason": f"local {section} evidence candidate matching: {_normalise(text)[:120]}",
        }
        for key in ("run_id", "cohort_id", "snapshot_id"):
            if identity.get(key):
                row[key] = identity[key]
        suggestions.append(row)
    return suggestions


def classify_completion_change(
    *,
    project_path: Path | None,
    section: str,
    instruction: str,
    content: str,
    explicit: str | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    enforcement_mode: str = DEFAULT_ENFORCEMENT_MODE,
) -> CompletionClassification:
    mode = enforcement_mode if enforcement_mode in {"shadow", "strict"} else DEFAULT_ENFORCEMENT_MODE
    inferred = _text_class(section, instruction, content)
    evidence_refs = list(evidence_refs or [])
    evidence = validate_evidence_refs(project_path, evidence_refs)
    suggested = suggest_evidence_refs(project_path, section=section, text=content) if project_path else []
    rejection_codes: list[str] = []
    declared = None
    if explicit:
        try:
            declared = normalize_change_class(explicit)
        except ValueError:
            rejection_codes.append("unsupported_change_class")
    if str(explicit or "").strip().lower() == "scientific_evidence_change":
        rejection_codes.append("legacy_umbrella_requires_refinement")
    canonical = declared or inferred
    canonical_scientific, canonical_low_impact = _change_class_semantics(canonical)
    inferred_scientific, _ = _change_class_semantics(inferred)
    source_stage = SECTION_STAGES.get(section, section)
    declared_scope = set(affected_stages_for_class(declared, source_stage=source_stage)) if declared else set()
    inferred_scope = set(affected_stages_for_class(inferred, source_stage=source_stage))
    mismatch = bool(
        declared
        and declared != inferred
        and (
            (_change_class_semantics(declared)[1] and inferred_scientific)
            or not inferred_scope.issubset(declared_scope)
        )
    )
    executed_detail = _has_executed_detail(section, instruction, content)
    if executed_detail and canonical_low_impact and evidence["status"] != "passed":
        rejection_codes.append("missing_evidence_refs")
    if evidence["status"] == "failed":
        rejection_codes.extend(str(item) for item in evidence.get("issues") or [])
    rejection_codes = list(dict.fromkeys(rejection_codes))
    if rejection_codes:
        effective = _refinement_effective_class(
            section=section,
            canonical=canonical,
            inferred=inferred,
            executed_detail=executed_detail,
        )
        scope = affected_stages_for_class(effective, source_stage=source_stage)
        return CompletionClassification(
            canonical_change_class=canonical,
            effective_change_class=effective,
            inferred_change_class=inferred,
            classification_source="declared_and_evidence_checked" if declared else "inferred",
            enforcement_mode=mode,
            decision="classification_refinement_required",
            would_block_in_strict=True,
            scientific_semantics_changed=_change_class_semantics(effective)[0],
            stale_scope=scope,
            evidence_validation=evidence,
            suggested_evidence_refs=suggested,
            rejection_codes=rejection_codes,
            reason="Evidence-backed execution detail requires current, bound evidence refs.",
        )
    if mismatch:
        if mode == "strict":
            scope = affected_stages_for_class(inferred, source_stage=source_stage)
            return CompletionClassification(
                canonical_change_class=canonical,
                effective_change_class=canonical,
                inferred_change_class=inferred,
                classification_source="declared_vs_inferred",
                enforcement_mode=mode,
                decision="classification_mismatch",
                would_block_in_strict=True,
                scientific_semantics_changed=canonical_scientific or inferred_scientific,
                stale_scope=scope,
                evidence_validation=evidence,
                suggested_evidence_refs=suggested,
                rejection_codes=["declared_class_lower_than_inferred_class"],
                reason=f"The revision is better represented as {inferred}.",
            )
        effective = inferred
        scope = affected_stages_for_class(effective, source_stage=source_stage)
        return CompletionClassification(
            canonical_change_class=canonical,
            effective_change_class=effective,
            inferred_change_class=inferred,
            classification_source="declared_vs_inferred_shadow",
            enforcement_mode=mode,
            decision="pass_with_shadow_warning",
            would_block_in_strict=True,
            scientific_semantics_changed=_change_class_semantics(effective)[0],
            stale_scope=scope,
            evidence_validation=evidence,
            suggested_evidence_refs=suggested,
            rejection_codes=[],
            reason=f"Shadow mode applies the conservative inferred class {inferred}.",
        )
    scope = affected_stages_for_class(canonical, source_stage=source_stage)
    return CompletionClassification(
        canonical_change_class=canonical,
        effective_change_class=canonical,
        inferred_change_class=inferred,
        classification_source="declared_and_verified" if declared else "inferred",
        enforcement_mode=mode,
        decision="accepted",
        would_block_in_strict=False,
        scientific_semantics_changed=canonical_scientific,
        stale_scope=scope,
        evidence_validation=evidence,
        suggested_evidence_refs=suggested,
        rejection_codes=[],
        reason="The revision matches the canonical class and current evidence boundary.",
    )


__all__ = [
    "ALLOWED_EVIDENCE_REF_PATHS",
    "CompletionClassification",
    "classify_completion_change",
    "suggest_evidence_refs",
    "validate_evidence_refs",
]
