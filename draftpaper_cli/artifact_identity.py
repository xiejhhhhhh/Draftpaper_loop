"""Stable artifact identities used by passport and drift reconciliation.

The byte digest is the exact file identity.  The semantic digest is used for
workflow decisions and ignores only fields declared volatile by the artifact
schema.  The evidence digest is the identity that can be bound to a human
checkpoint; for a bibliography it represents the retained work set rather
than formatting or publication metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPORT_VOLATILE_FIELDS = frozenset(
    {
        "generated_at",
        "updated_at",
        "rendered_at",
        "retrieved_at",
        "created_at",
        "state_revision",
        "stage_summary_sha256",
    }
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_family(relative: str, suffix: str) -> str:
    normalized = relative.replace("\\", "/").lower()
    if normalized == "references/library.bib":
        return "dpl.reference_library.v1"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".parquet", ".npz", ".pt", ".pth", ".bin"}:
        return "dpl.binary.v1"
    if normalized.startswith(("review/", "quality/", "quality_checks/", "citation_audit/", "integrity/")):
        return "dpl.report.v1"
    if suffix in {".json", ".yaml", ".yml"}:
        return "dpl.structured_artifact.v1"
    return "dpl.text_artifact.v1"


def _stable_value(value: Any, *, volatile_fields: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(item, volatile_fields=volatile_fields)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in volatile_fields
        }
    if isinstance(value, list):
        return [_stable_value(item, volatile_fields=volatile_fields) for item in value]
    if isinstance(value, tuple):
        return [_stable_value(item, volatile_fields=volatile_fields) for item in value]
    return value


def canonical_json(value: Any, *, volatile_fields: frozenset[str] = frozenset()) -> str:
    return json.dumps(
        _stable_value(value, volatile_fields=volatile_fields),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _load_structured(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError:
            return None
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError:
            return None


def _bib_fingerprint(text: str) -> dict[str, Any]:
    entries = re.findall(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", text, flags=re.S)
    citation_keys: list[str] = []
    work_ids: list[str] = []
    for key, body in entries:
        citation_keys.append(key.strip())
        doi_match = re.search(r"(?im)^\s*doi\s*=\s*[\{\"]([^}\"]+)", body)
        title_match = re.search(r"(?im)^\s*title\s*=\s*[\{\"]([^}\"]+)", body)
        if doi_match:
            doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi_match.group(1).strip(), flags=re.I).lower()
            work_ids.append(f"doi:{doi}")
        elif title_match:
            title = re.sub(r"[^a-z0-9]+", "", title_match.group(1).replace("{", "").replace("}", "").lower())
            work_ids.append(f"title:{title}")
    citation_values = sorted(set(citation_keys))
    work_values = sorted(set(work_ids))
    return {
        "kind": "reference_library",
        "citation_key_count": len(citation_values),
        "work_count": len(work_values),
        "citation_keys_sha256": sha256_bytes("\n".join(citation_values).encode("utf-8")),
        "work_ids_sha256": sha256_bytes("\n".join(work_values).encode("utf-8")),
    }


def _normalized_text(text: str, *, remove_report_timestamps: bool) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if remove_report_timestamps:
        normalized = re.sub(
            r"(?im)^\s*(?:generated_at|updated_at|rendered_at|retrieved_at|created_at|state_revision)\s*[:=].*\n?",
            "",
            normalized,
        )
    return "\n".join(line.rstrip() for line in normalized.splitlines()).strip() + "\n"


def _semantic_payload(path: Path, relative: str) -> tuple[str, str, dict[str, Any] | None]:
    suffix = path.suffix.lower()
    schema_family = _schema_family(relative, suffix)
    if relative.replace("\\", "/").lower() == "references/library.bib":
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        fingerprint = _bib_fingerprint(text)
        return _normalized_text(text, remove_report_timestamps=False), "schema:reference_library", fingerprint
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".parquet", ".npz", ".pt", ".pth", ".bin"}:
        return f"binary:{sha256_file(path)}", "schema:binary.v1", None
    if suffix in {".json", ".yaml", ".yml"}:
        payload = _load_structured(path)
        if payload is not None:
            volatile = REPORT_VOLATILE_FIELDS if schema_family == "dpl.report.v1" else frozenset()
            return canonical_json(payload, volatile_fields=volatile), f"schema:{schema_family}", None
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    remove_timestamps = schema_family == "dpl.report.v1"
    return _normalized_text(text, remove_report_timestamps=remove_timestamps), f"schema:{schema_family}", None


def compute_artifact_identity(
    path: str | Path,
    relative: str,
    *,
    writer_command: str | None = None,
    input_hashes: dict[str, str] | None = None,
    runtime_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Return portable byte, semantic and evidence identities for one artifact."""

    artifact_path = Path(path)
    semantic_payload, policy, bib_fingerprint = _semantic_payload(artifact_path, relative)
    semantic_sha256 = sha256_bytes(semantic_payload.encode("utf-8"))
    evidence_sha256 = sha256_bytes(canonical_json(bib_fingerprint).encode("utf-8")) if bib_fingerprint else semantic_sha256
    result: dict[str, Any] = {
        "byte_sha256": sha256_file(artifact_path),
        "semantic_sha256": semantic_sha256,
        "evidence_sha256": evidence_sha256,
        "schema_family": _schema_family(relative, artifact_path.suffix.lower()),
        "volatile_field_policy": policy,
    }
    if writer_command:
        result["writer_command"] = writer_command
    if input_hashes:
        result["input_sha256"] = dict(sorted(input_hashes.items()))
    if runtime_fingerprint:
        result["runtime_fingerprint"] = runtime_fingerprint
    if bib_fingerprint:
        result["semantic_fingerprint"] = bib_fingerprint
    return result


def semantic_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return bool(before.get("semantic_sha256")) and before.get("semantic_sha256") == after.get("semantic_sha256")


def evidence_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return bool(before.get("evidence_sha256")) and before.get("evidence_sha256") == after.get("evidence_sha256")
