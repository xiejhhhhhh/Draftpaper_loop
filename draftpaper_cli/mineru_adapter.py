"""Optional local MinerU adapter with a pypdf fallback.

MinerU is intentionally not a core dependency.  The adapter records exactly
which parser ran and treats extracted bibliography text as discovery material,
never as an automatically verified citation.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project
from .references import _extract_pdf_text_from_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_mineru_output(root: Path) -> Path | None:
    for name in ("content_list_v2.json", "content_list.json"):
        matches = sorted(root.rglob(name))
        if matches:
            return matches[0]
    return None


def parse_literature_document(project: str | Path, input_path: str | Path, *, use_mineru: bool = True, timeout_seconds: int = 600) -> dict[str, Any]:
    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("parse-literature-document requires an existing PDF file.")
    output_root = state.path / "references" / "document_parses" / _sha256(source)[:16]
    output_root.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "schema_version": "dpl.document_parse_receipt.v1",
        "input_sha256": _sha256(source),
        "input_name": source.name,
        "source_locator": "external_local_file",
        "status": "metadata_only",
        "parser": "none",
        "parser_version": "",
        "bibliography_auto_citation": False,
    }
    executable = os.getenv("MINERU_EXECUTABLE", "mineru").strip() or "mineru"
    if use_mineru and shutil.which(executable):
        try:
            completed = subprocess.run(
                [executable, "-p", str(source), "-o", str(output_root)],
                check=False,
                capture_output=True,
                text=True,
                timeout=max(1, timeout_seconds),
            )
            parsed = _find_mineru_output(output_root)
            if completed.returncode == 0 and parsed:
                target = output_root / parsed.name
                if parsed.resolve() != target.resolve():
                    shutil.copy2(parsed, target)
                receipt.update({"status": "parsed", "parser": "mineru", "output": target.relative_to(state.path).as_posix(), "return_code": 0})
            else:
                receipt.update({"status": "fallback", "parser": "mineru", "return_code": completed.returncode, "error_type": "missing_expected_output"})
        except subprocess.TimeoutExpired:
            receipt.update({"status": "fallback", "parser": "mineru", "error_type": "timeout"})
        except OSError as exc:
            receipt.update({"status": "fallback", "parser": "mineru", "error_type": type(exc).__name__})
    if receipt["status"] != "parsed":
        text = _extract_pdf_text_from_path(str(source), max_pages=8, max_chars=16000)
        fallback_path = output_root / "pypdf_excerpt.txt"
        fallback_path.write_text(text, encoding="utf-8")
        receipt.update({"status": "fallback" if text else "metadata_only", "parser": "pypdf", "output": fallback_path.relative_to(state.path).as_posix(), "text_chars": len(text)})
    receipt_path = output_root / "parse_receipt.json"
    _write_json(receipt_path, receipt)
    return {"status": receipt["status"], "project_path": str(state.path), "receipt": receipt, "receipt_path": receipt_path.relative_to(state.path).as_posix(), "citation_policy": "bibliography_candidates_require_identity_and_metadata_audit"}
