"""Validate the README-bound capability truth matrix without driving runtime stages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPOSITORY_ROOT / "docs" / "capability_truth_matrix.json"
README_PATHS = (REPOSITORY_ROOT / "README.md", REPOSITORY_ROOT / "README.zh-CN.md")
MATRIX_SCHEMA = "dpl.capability_truth_matrix.v1"
MINOR_VERSION = re.compile(r"^\d+\.\d+$")
REQUIRED_RECORD_FIELDS = {
    "capability_id",
    "status",
    "since",
    "readme_anchor",
    "claim_zh",
    "claim_en",
    "commands",
    "source_files",
    "tests",
    "artifacts",
    "boundary_zh",
    "boundary_en",
}

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from draftpaper_cli.command_registry import COMMAND_SPECS


def normalize_whitespace(text: str) -> str:
    """Collapse Markdown line wrapping and indentation for stable claim comparison."""

    return re.sub(r"\s+", " ", text).strip()


def load_matrix(path: str | Path = MATRIX_PATH) -> dict[str, Any]:
    """Load one JSON matrix and leave semantic checks to :func:`validate_matrix`."""

    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("matrix root must be an object")
    return payload


def _relative_paths_exist(paths: Any, root: Path, label: str, errors: list[str]) -> None:
    if not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path.strip() for path in paths):
        errors.append(f"{label} must be a non-empty list of relative paths")
        return
    for path in paths:
        candidate = root / path
        if Path(path).is_absolute() or not candidate.is_file():
            errors.append(f"{label} references missing repository file: {path}")


def _artifact_has_production_evidence(record: dict[str, Any], artifact: str, root: Path) -> bool:
    normalized_artifact = re.sub(r"<[^>]+>", "artifact-id", artifact)
    for command in record.get("commands", []):
        spec = COMMAND_SPECS.get(command)
        if spec is None:
            continue
        if any(fnmatchcase(normalized_artifact, pattern) for pattern in spec.allowed_write_globs):
            return True

    source_text = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in record.get("source_files", [])
        if isinstance(path, str) and (root / path).is_file()
    )
    if artifact in source_text:
        return True
    literal_segments = [segment for segment in re.split(r"<[^>]+>", artifact) if segment]
    return len(literal_segments) > 1 and all(segment in source_text for segment in literal_segments)


def _validate_readme_binding(record: dict[str, Any], text: str, language: str, errors: list[str]) -> None:
    anchor = record["readme_anchor"]
    opening = f"<!-- {anchor} -->"
    closing = f"<!-- /{anchor} -->"
    if text.count(opening) != 1 or text.count(closing) != 1:
        errors.append(f"{language}: missing anchor pair for {record['capability_id']}")
        return
    bounded = text.split(opening, 1)[1].split(closing, 1)[0]
    if not normalize_whitespace(bounded):
        errors.append(f"{language}: capability anchor is empty for {record['capability_id']}")


def _validate_status_table(records: list[dict[str, Any]], text: str, language: str, errors: list[str]) -> None:
    heading = "## Implementation Status" if language == "en" else "## 当前实现状态"
    expected_header = (
        ["Capability ID", "Status / Since", "Evidence", "Boundary"]
        if language == "en"
        else ["能力 ID", "状态 / Since", "证据", "边界"]
    )
    if heading not in text:
        errors.append(f"{language}: missing implementation status heading")
        return
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    if len(lines) < 3:
        errors.append(f"{language}: implementation status must contain a four-column table")
        return
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    if header != expected_header:
        errors.append(f"{language}: implementation status table header does not match")
    rows: dict[str, list[str]] = {}
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 4:
            errors.append(f"{language}: implementation status rows must have four columns")
            continue
        rows[cells[0].strip("`")] = cells
    expected_ids = {record["capability_id"] for record in records}
    if set(rows) != expected_ids:
        errors.append(f"{language}: implementation status capability IDs do not match the matrix")
    for record in records:
        row = rows.get(record["capability_id"])
        if row is None:
            continue
        if row[1] != f"{record['status']} / {record['since']}":
            errors.append(f"{language}: status/since mismatch for {record['capability_id']}")
        if not row[2]:
            errors.append(f"{language}: missing evidence for {record['capability_id']}")
        boundary = record["boundary_en"] if language == "en" else record["boundary_zh"]
        if normalize_whitespace(row[3]) != normalize_whitespace(boundary):
            errors.append(f"{language}: boundary mismatch for {record['capability_id']}")


def validate_matrix(payload: dict[str, Any], root: str | Path = REPOSITORY_ROOT) -> list[str]:
    """Return deterministic validation errors for a loaded matrix."""

    repository_root = Path(root)
    errors: list[str] = []
    if payload.get("schema_version") != MATRIX_SCHEMA:
        errors.append(f"schema_version must be {MATRIX_SCHEMA}")
    if "commercial" in json.dumps(payload, ensure_ascii=False).lower():
        errors.append("matrix must not contain commercial product information")

    records = payload.get("capabilities")
    if not isinstance(records, list) or not records:
        return errors + ["capabilities must be a non-empty list"]

    ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"capabilities[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = REQUIRED_RECORD_FIELDS - set(record)
        errors.extend(f"{prefix} missing {field}" for field in sorted(missing))
        capability_id = record.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id.strip():
            errors.append(f"{prefix}.capability_id must be a non-empty string")
            continue
        if capability_id in ids:
            errors.append(f"duplicate capability_id: {capability_id}")
        ids.add(capability_id)
        if record.get("status") not in {"implemented", "partial", "shadow", "planned"}:
            errors.append(f"{capability_id}: unsupported status")
        if not isinstance(record.get("since"), str) or not MINOR_VERSION.fullmatch(record["since"]):
            errors.append(f"{capability_id}: since must be a minor version such as 0.32")
        expected_anchor = f"capability:{capability_id}"
        if record.get("readme_anchor") != expected_anchor:
            errors.append(f"{capability_id}: readme_anchor must be {expected_anchor}")
        for field in ("claim_zh", "claim_en", "boundary_zh", "boundary_en"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append(f"{capability_id}: {field} must be non-empty text")

        commands = record.get("commands")
        if not isinstance(commands, list) or not all(isinstance(command, str) for command in commands):
            errors.append(f"{capability_id}: commands must be a list")
        else:
            missing_commands = sorted(set(commands) - set(COMMAND_SPECS))
            errors.extend(f"{capability_id}: command is not registered: {command}" for command in missing_commands)
        _relative_paths_exist(record.get("source_files"), repository_root, f"{capability_id}.source_files", errors)
        _relative_paths_exist(record.get("tests"), repository_root, f"{capability_id}.tests", errors)
        artifacts = record.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts or not all(isinstance(artifact, str) and artifact.strip() for artifact in artifacts):
            errors.append(f"{capability_id}: artifacts must be a non-empty list of strings")
        else:
            for artifact in artifacts:
                if not _artifact_has_production_evidence(record, artifact, repository_root):
                    errors.append(f"{capability_id}: artifact lacks supported glob or production-constant evidence: {artifact}")
        if record.get("status") in {"partial", "shadow"}:
            for field in ("gap_zh", "gap_en"):
                if not str(record.get(field, "")).strip():
                    errors.append(f"{capability_id}: partial records need {field}")

    readme_paths = (repository_root / "README.md", repository_root / "README.zh-CN.md")
    for readme_path in readme_paths:
        if not readme_path.is_file():
            errors.append(f"missing README: {readme_path}")
            continue
        text = readme_path.read_text(encoding="utf-8")
        language = "zh" if readme_path.name.endswith("zh-CN.md") else "en"
        for record in records:
            if isinstance(record, dict) and REQUIRED_RECORD_FIELDS <= set(record):
                _validate_readme_binding(record, text, language, errors)
        valid_records = [record for record in records if isinstance(record, dict) and REQUIRED_RECORD_FIELDS <= set(record)]
        _validate_status_table(valid_records, text, language, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    args = parser.parse_args(argv)
    try:
        payload = load_matrix(args.matrix)
        errors = validate_matrix(payload, args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"capability truth matrix validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("capability truth matrix validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"validated {len(payload['capabilities'])} capability truth records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
