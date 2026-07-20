"""Final PDF, citation-audit, and independent-review confirmation."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .evidence_snapshot import EvidenceSnapshotMismatch, validate_citation_audit_snapshot
from .html_utils import write_html_report
from .independent_review import (
    IndependentReviewError,
    derive_independent_review_decision,
    validate_independent_review_content,
)
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


PACKET_JSON = "review/final_manuscript_confirmation_packet.json"
PACKET_HTML = "review/final_manuscript_confirmation_packet.html"
CONFIRMATION_JSON = "review/final_manuscript_confirmation.json"
ARTIFACTS = [
    "latex/main.pdf",
    "writing/manuscript_completion/active_completion_manifest.json",
    "writing/manuscript_metadata.yaml",
    "introduction/introduction.tex",
    "data/data.tex",
    "methods/methods.tex",
    "results/results.tex",
    "discussion/discussion.tex",
    "references/library.bib",
    "references/reference_registry.json",
    "citation_audit/final_citation_audit_report.json",
    "results/promoted_evidence_snapshot.json",
    "results/result_manifest.yaml",
    "results/figure_metadata.json",
    "core_evidence/core_evidence_report.json",
    "integrity/integrity_report.json",
    "quality_checks/blind_reviews/aggregate.json",
    "quality_checks/blind_reviews/submission_bundle_manifest.json",
    "quality_checks/blind_reviews/anonymous_submission_bundle.zip",
    "quality_checks/blind_reviews/reviewer_01/report.json",
    "quality_checks/blind_reviews/reviewer_01/report.md",
    "quality_checks/blind_reviews/reviewer_02/report.json",
    "quality_checks/blind_reviews/reviewer_02/report.md",
    "quality_checks/quality_report.json",
]


class FinalManuscriptConfirmationError(RuntimeError):
    """Raised when the final release packet is incomplete or stale."""


@dataclass(frozen=True)
class _ArtifactSnapshot:
    relative: str
    resolved_path: Path
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.content)


def _read_project_snapshot(
    project_path: Path,
    relative: str,
    *,
    artifact: str,
    required: bool = True,
) -> _ArtifactSnapshot | None:
    root = project_path.resolve()
    relative_path = Path(relative)
    if not relative or relative_path.is_absolute():
        raise FinalManuscriptConfirmationError(f"{artifact} path must be project-relative: {relative!r}.")
    candidate = root / relative_path
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        if not required and not candidate.exists():
            return None
        raise FinalManuscriptConfirmationError(f"{artifact} is missing or unreadable: {relative}.") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FinalManuscriptConfirmationError(f"{artifact} path escapes the project: {relative}.") from exc
    if not resolved.is_file():
        raise FinalManuscriptConfirmationError(f"{artifact} is not a regular file: {relative}.")
    try:
        content = resolved.read_bytes()
    except OSError as exc:
        raise FinalManuscriptConfirmationError(f"{artifact} is unreadable: {relative}.") from exc
    return _ArtifactSnapshot(relative=relative, resolved_path=resolved, content=content)


def _json_from_snapshot(snapshot: _ArtifactSnapshot, *, artifact: str) -> dict[str, Any]:
    try:
        value = json.loads(snapshot.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalManuscriptConfirmationError(f"{artifact} must be a structured JSON object.") from exc
    if not isinstance(value, dict):
        raise FinalManuscriptConfirmationError(f"{artifact} must be a structured JSON object.")
    return value


def _load_final_artifacts(project_path: Path) -> dict[str, _ArtifactSnapshot]:
    snapshots: dict[str, _ArtifactSnapshot] = {}
    missing: list[str] = []
    for relative in ARTIFACTS:
        snapshot = _read_project_snapshot(
            project_path,
            relative,
            artifact="Final manuscript artifact",
            required=False,
        )
        if snapshot is None:
            missing.append(relative)
            continue
        snapshots[relative] = snapshot
    if missing:
        if any(relative.startswith("quality_checks/blind_reviews/") for relative in missing):
            raise FinalManuscriptConfirmationError(
                "Final manuscript packet is incomplete; independent review submission bundle files are missing: "
                + ", ".join(missing)
            )
        raise FinalManuscriptConfirmationError("Final manuscript packet is incomplete: " + ", ".join(missing))
    return snapshots


def _checked_output_path(project_path: Path, relative: str) -> Path:
    root = project_path.resolve()
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = target.parent.resolve(strict=True)
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise FinalManuscriptConfirmationError(f"Final confirmation output path escapes the project: {relative}.") from exc
    if target.exists():
        resolved_target = target.resolve(strict=True)
        try:
            resolved_target.relative_to(root)
        except ValueError as exc:
            raise FinalManuscriptConfirmationError(
                f"Final confirmation output path escapes the project: {relative}."
            ) from exc
    return target


def _is_passing(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    decision = str(payload.get("decision") or "").lower()
    return status in {"pass", "passed", "approved"} or decision == "pass"


def _timestamp(value: Any, *, artifact: str, field: str) -> datetime:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinalManuscriptConfirmationError(
            f"{artifact} schema error: {field} must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None:
        raise FinalManuscriptConfirmationError(
            f"{artifact} schema error: {field} must include a timezone."
        )
    return parsed


def _submission_bundle_core(manifest: dict[str, Any]) -> dict[str, Any]:
    generated_fields = {"created_at", "bundle_hash", "bundle_hash_semantics", "bundle_zip"}
    return {key: value for key, value in manifest.items() if key not in generated_fields}


def _validate_frozen_artifacts(
    project_path: Path,
    manifest: dict[str, Any],
    snapshots: dict[str, _ArtifactSnapshot],
) -> None:
    frozen = manifest.get("frozen_artifacts")
    if not isinstance(frozen, dict) or not frozen:
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: frozen_artifacts must be a non-empty object."
        )
    required_groups = {"manuscript", "figures", "tables", "references", "evidence", "reproducibility"}
    missing_groups = sorted(required_groups - set(frozen))
    if missing_groups:
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: missing required groups: "
            + ", ".join(missing_groups)
            + "."
        )
    record_count = 0
    for group_name, group in frozen.items():
        if not isinstance(group_name, str) or not group_name.strip():
            raise FinalManuscriptConfirmationError(
                "Independent review submission bundle schema error: frozen artifact group names must be non-empty."
            )
        if not isinstance(group, list):
            raise FinalManuscriptConfirmationError(
                "Independent review submission bundle schema error: frozen artifact groups must be lists."
            )
        for record in group:
            record_count += 1
            if not isinstance(record, dict):
                raise FinalManuscriptConfirmationError(
                    "Independent review submission bundle schema error: frozen artifact records must be objects."
                )
            relative = record.get("path")
            expected_hash = record.get("sha256")
            size_bytes = record.get("size_bytes")
            if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
                raise FinalManuscriptConfirmationError(
                    "Independent review submission bundle schema error: frozen artifact identity path must be a non-empty project-relative string."
                )
            posix_relative = PurePosixPath(relative)
            if (
                relative == "bundle_manifest.json"
                or "\\" in relative
                or posix_relative.is_absolute()
                or posix_relative.as_posix() != relative
                or any(part in {"", ".", ".."} for part in posix_relative.parts)
            ):
                raise FinalManuscriptConfirmationError(
                    "Independent review submission bundle schema error: frozen artifact identity path must be a canonical project-relative POSIX path."
                )
            if (
                not isinstance(expected_hash, str)
                or len(expected_hash) != 64
                or any(character not in "0123456789abcdef" for character in expected_hash)
            ):
                raise FinalManuscriptConfirmationError(
                    "Independent review submission bundle schema error: frozen artifact identity sha256 must be 64 lowercase hexadecimal characters."
                )
            if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
                raise FinalManuscriptConfirmationError(
                    "Independent review submission bundle schema error: frozen artifact identity size_bytes must be a non-negative integer."
                )
            snapshot = snapshots.get(relative)
            if snapshot is None:
                snapshot = _read_project_snapshot(
                    project_path,
                    relative,
                    artifact="Independent review frozen artifact",
                )
                assert snapshot is not None
                snapshots[relative] = snapshot
            if snapshot.sha256 != expected_hash or snapshot.size_bytes != size_bytes:
                raise FinalManuscriptConfirmationError(
                    f"The current frozen submission bundle artifact does not match its recorded identity: {relative}."
                )
    if not record_count:
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: at least one frozen artifact identity is required."
        )


def _bundled_frozen_artifacts(
    manifest: dict[str, Any],
    snapshots: dict[str, _ArtifactSnapshot],
) -> dict[str, tuple[_ArtifactSnapshot, dict[str, Any]]]:
    frozen = manifest["frozen_artifacts"]
    manuscript_pdfs = [record for record in frozen["manuscript"] if PurePosixPath(record["path"]).suffix.lower() == ".pdf"]
    if len(manuscript_pdfs) != 1:
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: exactly one frozen manuscript PDF is required."
        )
    if manuscript_pdfs[0]["path"] != "latex/main.pdf":
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: the frozen manuscript PDF must be the current latex/main.pdf."
        )

    bindings: dict[str, tuple[_ArtifactSnapshot, dict[str, Any]]] = {}

    def bind(member: str, record: dict[str, Any]) -> None:
        if member in bindings:
            raise FinalManuscriptConfirmationError(
                f"Independent review submission bundle schema error: duplicate ZIP payload identity for {member}."
            )
        bindings[member] = (snapshots[record["path"]], record)

    for group in frozen.values():
        for record in group:
            bind(record["path"], record)
    return bindings


def _validate_bundle_zip(
    snapshot: _ArtifactSnapshot,
    manifest: dict[str, Any],
    snapshots: dict[str, _ArtifactSnapshot],
) -> None:
    payload_bindings = _bundled_frozen_artifacts(manifest, snapshots)
    try:
        with zipfile.ZipFile(io.BytesIO(snapshot.content)) as archive:
            listed_names = archive.namelist()
            names = set(listed_names)
            if len(names) != len(listed_names):
                raise FinalManuscriptConfirmationError(
                    "Independent review bundle ZIP contains duplicate member names."
                )
            if "bundle_manifest.json" not in names:
                raise FinalManuscriptConfirmationError(
                    "Independent review bundle ZIP is incomplete: bundle_manifest.json is missing."
                )
            expected_names = {"bundle_manifest.json", *payload_bindings}
            if names != expected_names:
                missing = sorted(expected_names - names)
                extra = sorted(names - expected_names)
                raise FinalManuscriptConfirmationError(
                    "Independent review bundle ZIP payload set does not match the frozen artifact manifest"
                    + (f"; missing: {', '.join(missing)}" if missing else "")
                    + (f"; unbound: {', '.join(extra)}" if extra else "")
                    + "."
                )
            embedded_bytes = archive.read("bundle_manifest.json")
            for member, (current_snapshot, record) in payload_bindings.items():
                payload = archive.read(member)
                payload_hash = hashlib.sha256(payload).hexdigest()
                if (
                    payload != current_snapshot.content
                    or payload_hash != record["sha256"]
                    or len(payload) != record["size_bytes"]
                ):
                    raise FinalManuscriptConfirmationError(
                        f"Independent review bundle ZIP payload does not match its frozen byte/hash/size identity: {member}."
                    )
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise FinalManuscriptConfirmationError(
                    f"Independent review bundle ZIP contains a corrupt member: {corrupt_member}."
                )
    except FinalManuscriptConfirmationError:
        raise
    except (KeyError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise FinalManuscriptConfirmationError("Independent review bundle ZIP is malformed.") from exc
    try:
        embedded = json.loads(embedded_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinalManuscriptConfirmationError(
            "Independent review bundle ZIP bundle_manifest.json is malformed."
        ) from exc
    if embedded != manifest:
        raise FinalManuscriptConfirmationError(
            "Independent review bundle ZIP does not contain the current bound bundle_manifest.json."
        )


def _validate_report_hashes(aggregate: dict[str, Any], expected_paths: list[str]) -> dict[str, str]:
    hashes = aggregate.get("reviewer_report_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(expected_paths):
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate schema error: reviewer_report_sha256 must bind both structured review JSON paths."
        )
    for relative, digest in hashes.items():
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise FinalManuscriptConfirmationError(
                f"Independent review aggregate schema error: reviewer report SHA-256 is invalid for {relative}."
            )
    return hashes


def _validate_independent_reviews(
    project_path: Path,
    *,
    citation_audit_at: datetime,
    snapshots: dict[str, _ArtifactSnapshot],
) -> dict[str, Any]:
    manifest_relative = "quality_checks/blind_reviews/submission_bundle_manifest.json"
    aggregate_relative = "quality_checks/blind_reviews/aggregate.json"
    bundle_relative = "quality_checks/blind_reviews/anonymous_submission_bundle.zip"
    manifest = _json_from_snapshot(
        snapshots[manifest_relative],
        artifact="Independent review submission bundle manifest",
    )
    if manifest.get("schema_version") != "dpl.independent_review_bundle.v1":
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: expected dpl.independent_review_bundle.v1."
        )
    bundle_hash = str(manifest.get("bundle_hash") or "")
    calculated_hash = hashlib.sha256(
        json.dumps(_submission_bundle_core(manifest), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if bundle_hash != calculated_hash:
        raise FinalManuscriptConfirmationError(
            "The independent review submission bundle hash does not match the current submission_bundle_manifest."
        )
    if manifest.get("bundle_zip") != bundle_relative:
        raise FinalManuscriptConfirmationError(
            "Independent review submission bundle schema error: bundle_zip must identify the project review bundle ZIP."
        )
    _validate_frozen_artifacts(project_path, manifest, snapshots)
    _validate_bundle_zip(snapshots[bundle_relative], manifest, snapshots)
    bundle_created_at = _timestamp(
        manifest.get("created_at"),
        artifact="Independent review submission bundle",
        field="created_at",
    )
    if bundle_created_at <= citation_audit_at:
        raise FinalManuscriptConfirmationError(
            "The independent review submission bundle must be produced after the final citation audit."
        )

    aggregate = _json_from_snapshot(
        snapshots[aggregate_relative],
        artifact="Independent review aggregate",
    )
    if aggregate.get("schema_version") != "dpl.independent_review_aggregate.v1":
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate schema error: expected dpl.independent_review_aggregate.v1."
        )
    reviewer_count = aggregate.get("reviewer_count")
    if not isinstance(reviewer_count, int) or isinstance(reviewer_count, bool):
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate schema error: reviewer_count must be the integer 2."
        )
    if reviewer_count != 2:
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate is incomplete: reviewer_count must equal 2."
        )
    if aggregate.get("frozen_submission_bundle_hash") != bundle_hash:
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate does not bind the current submission bundle hash."
        )

    expected_paths = [
        "quality_checks/blind_reviews/reviewer_01/report.json",
        "quality_checks/blind_reviews/reviewer_02/report.json",
    ]
    if list(aggregate.get("reviewer_reports") or []) != expected_paths:
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate schema error: reviewer_reports must identify both structured reviewer reports."
        )
    report_hashes = _validate_report_hashes(aggregate, expected_paths)
    reviewer_ids = []
    session_ids = []
    recorded_times = []
    reports: list[dict[str, Any]] = []
    actual_report_hashes: dict[str, str] = {}
    for index, relative in enumerate(expected_paths, start=1):
        reviewer_id = f"reviewer_{index:02d}"
        report_snapshot = snapshots[relative]
        report = _json_from_snapshot(
            report_snapshot,
            artifact=f"Independent review report {reviewer_id}",
        )
        actual_report_hashes[relative] = report_snapshot.sha256
        if report.get("schema_version") != "dpl.independent_manuscript_review.v1":
            raise FinalManuscriptConfirmationError(
                f"Independent review report schema error for {reviewer_id}: expected dpl.independent_manuscript_review.v1."
            )
        if report.get("reviewer_anonymous_id") != reviewer_id:
            raise FinalManuscriptConfirmationError(
                f"Independent review report schema error for {reviewer_id}: reviewer_anonymous_id is inconsistent."
            )
        if report.get("frozen_submission_bundle_hash") != bundle_hash:
            raise FinalManuscriptConfirmationError(
                f"Independent review report {reviewer_id} does not bind the current submission bundle hash."
            )
        if report.get("checked_real_figures") is not True or report.get("full_manuscript_reviewed") is not True:
            raise FinalManuscriptConfirmationError(
                f"Independent review report schema error for {reviewer_id}: full manuscript and real-figure checks are required."
            )
        try:
            validate_independent_review_content(report)
        except IndependentReviewError as exc:
            raise FinalManuscriptConfirmationError(
                f"Independent review content schema error for {reviewer_id}: {exc}"
            ) from exc
        session_id = str(report.get("independent_session_provider_id_hash") or "")
        if not session_id:
            raise FinalManuscriptConfirmationError(
                f"Independent review report schema error for {reviewer_id}: independent session/provider ID hash is required."
            )
        recorded_at = _timestamp(
            report.get("recorded_at"),
            artifact=f"Independent review report {reviewer_id}",
            field="recorded_at",
        )
        if recorded_at <= bundle_created_at:
            raise FinalManuscriptConfirmationError(
                f"Independent review report {reviewer_id} must be produced after the current submission bundle."
            )
        reviewer_ids.append(reviewer_id)
        session_ids.append(session_id)
        recorded_times.append(recorded_at)
        reports.append(report)
    if len(set(session_ids)) != 2:
        raise FinalManuscriptConfirmationError(
            "The two structured review reports must come from distinct independent session/provider IDs."
        )
    if report_hashes != actual_report_hashes:
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate decision surface mismatch: bound reviewer report SHA-256 identities do not match the current reports."
        )
    aggregate_at = _timestamp(
        aggregate.get("generated_at"),
        artifact="Independent review aggregate",
        field="generated_at",
    )
    if aggregate_at <= max(recorded_times):
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate must be generated after both structured review reports."
        )
    try:
        recomputed = derive_independent_review_decision(reports)
    except IndependentReviewError as exc:
        raise FinalManuscriptConfirmationError(
            f"Independent review content schema error during aggregate recomputation: {exc}"
        ) from exc
    if recomputed["release_review_status"] != "pass":
        raise FinalManuscriptConfirmationError(
            "Independent review status recomputed from the two bound reports is blocked."
        )
    decision_fields = tuple(recomputed)
    mismatched_fields = [field for field in decision_fields if aggregate.get(field) != recomputed[field]]
    if mismatched_fields:
        raise FinalManuscriptConfirmationError(
            "Independent review aggregate decision surface does not match the recomputed report decision: "
            + ", ".join(mismatched_fields)
            + "."
        )
    return {
        "submission_bundle_hash": bundle_hash,
        "independent_reviewer_ids": reviewer_ids,
    }


def _validate_release_semantics(
    project_path: Path,
    snapshots: dict[str, _ArtifactSnapshot],
) -> dict[str, Any]:
    completion = _json_from_snapshot(
        snapshots["writing/manuscript_completion/active_completion_manifest.json"],
        artifact="Final manuscript completion",
    )
    if completion.get("status") != "applied":
        raise FinalManuscriptConfirmationError("Final manuscript completion is missing, rolled back, or not applied.")
    citation_snapshot = snapshots["citation_audit/final_citation_audit_report.json"]
    citation = _json_from_snapshot(citation_snapshot, artifact="Final citation audit")
    if not _is_passing(citation):
        raise FinalManuscriptConfirmationError("Final citation audit is missing or not passing.")
    if (project_path / "citation_audit" / "stale_marker.json").is_file():
        raise FinalManuscriptConfirmationError("Final citation audit is stale after a manuscript change.")
    binding = citation.get("manuscript_snapshot")
    if not isinstance(binding, dict):
        raise FinalManuscriptConfirmationError("Final citation audit has no manuscript snapshot binding.")
    try:
        current_citation_snapshot = validate_citation_audit_snapshot(project_path, binding)
    except EvidenceSnapshotMismatch as exc:
        raise FinalManuscriptConfirmationError("Final citation audit does not cover the current manuscript.") from exc
    applied_at = _timestamp(
        completion.get("applied_at"),
        artifact="Final manuscript completion",
        field="applied_at",
    )
    audit_at = _timestamp(
        citation.get("generated_at"),
        artifact="Final citation audit",
        field="generated_at",
    )
    if audit_at <= applied_at:
        raise FinalManuscriptConfirmationError("Final citation audit must run after manuscript completion.")
    integrity = _json_from_snapshot(
        snapshots["integrity/integrity_report.json"],
        artifact="Final integrity report",
    )
    if not _is_passing(integrity):
        raise FinalManuscriptConfirmationError("Final integrity report is missing or not passing.")
    quality = _json_from_snapshot(
        snapshots["quality_checks/quality_report.json"],
        artifact="Final quality report",
    )
    if not _is_passing(quality):
        raise FinalManuscriptConfirmationError("Final quality report is missing or not passing.")
    review_context = _validate_independent_reviews(
        project_path,
        citation_audit_at=audit_at,
        snapshots=snapshots,
    )
    evidence = _json_from_snapshot(
        snapshots["results/promoted_evidence_snapshot.json"],
        artifact="Promoted evidence snapshot",
    )
    if not evidence.get("snapshot_id"):
        raise FinalManuscriptConfirmationError("Promoted evidence snapshot is missing an evidence snapshot ID.")
    if snapshots["latex/main.pdf"].size_bytes == 0:
        raise FinalManuscriptConfirmationError("Final PDF is missing or empty.")
    return {
        "completion_packet_id": completion.get("packet_id"),
        "completion_packet_hash": completion.get("packet_hash"),
        "citation_audit_snapshot_id": current_citation_snapshot.get("snapshot_id"),
        "citation_audit_sha256": citation_snapshot.sha256,
        "evidence_snapshot_id": evidence.get("snapshot_id"),
        **review_context,
    }


def _release_snapshot(project_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    snapshots = _load_final_artifacts(project_path)
    context = _validate_release_semantics(project_path, snapshots)
    records = [
        {
            "path": relative,
            "sha256": snapshots[relative].sha256,
            "size_bytes": snapshots[relative].size_bytes,
        }
        for relative in ARTIFACTS
    ]
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return context, records, hashlib.sha256(encoded).hexdigest()


def _records(project_path: Path) -> list[dict[str, Any]]:
    return _release_snapshot(project_path)[1]


def current_release_hash(project: str | Path) -> str:
    state = load_project(project)
    return _release_snapshot(state.path)[2]


def review_final_manuscript(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    context, records, release_hash = _release_snapshot(state.path)
    packet = {
        "schema_version": "dpl.final_manuscript_confirmation_packet.v1",
        "status": "ready_for_human_review",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "release_hash": release_hash,
        "artifacts": records,
        **context,
        "confirmation_semantics": "Confirm the final PDF, final citation audit, both independent blind reviews, unresolved minor findings, and publication boundary as one release.",
    }
    _write_json(_checked_output_path(state.path, PACKET_JSON), packet)
    lines = [
        "# 最终论文确认",
        "",
        "本页面集中展示最终 PDF、最终引用核查、两位独立盲评和质量报告。确认后，这些内容作为同一发布版本冻结。",
        "",
        f"Release hash: `{release_hash}`",
        "",
        "## 发布产物",
        "",
    ]
    lines.extend(f"- `{item['path']}`" for item in records)
    write_html_report(_checked_output_path(state.path, PACKET_HTML), "\n".join(lines), title="最终论文确认")
    return {"status": "ready_for_human_review", "project_path": str(state.path), "release_hash": release_hash, "review_packet": PACKET_HTML}


def confirm_final_manuscript(project: str | Path, *, release_hash: str) -> dict[str, Any]:
    state = load_project(project)
    packet_snapshot = _read_project_snapshot(
        state.path,
        PACKET_JSON,
        artifact="Final manuscript confirmation packet",
        required=False,
    )
    if packet_snapshot is None:
        raise FinalManuscriptConfirmationError("Run review-final-manuscript before confirmation.")
    packet = _json_from_snapshot(packet_snapshot, artifact="Final manuscript confirmation packet")
    try:
        current = current_release_hash(state.path)
    except FinalManuscriptConfirmationError as exc:
        raise FinalManuscriptConfirmationError(
            "The release hash cannot be confirmed because a bound final artifact changed: " + str(exc)
        ) from exc
    if release_hash != current or packet.get("release_hash") != current:
        raise FinalManuscriptConfirmationError("The supplied release hash does not match the current final manuscript packet.")
    confirmation = {
        "schema_version": "dpl.final_manuscript_confirmation.v1",
        "status": "approved",
        "confirmed_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "release_hash": current,
        "artifacts": packet.get("artifacts") or [],
    }
    _write_json(_checked_output_path(state.path, CONFIRMATION_JSON), confirmation)
    return {"status": "approved", "project_path": str(state.path), "release_hash": current, "confirmation": CONFIRMATION_JSON}


def final_confirmation_state(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    confirmation_snapshot = _read_project_snapshot(
        state.path,
        CONFIRMATION_JSON,
        artifact="Final manuscript confirmation",
        required=False,
    )
    if confirmation_snapshot is None:
        return {"status": "awaiting_confirmation", "current": False}
    confirmation = _json_from_snapshot(confirmation_snapshot, artifact="Final manuscript confirmation")
    try:
        current = current_release_hash(state.path)
    except FinalManuscriptConfirmationError as exc:
        return {"status": "incomplete", "current": False, "reason": str(exc)}
    matches = confirmation.get("release_hash") == current
    return {"status": "approved" if matches else "release_drift", "current": matches, "release_hash": current}
