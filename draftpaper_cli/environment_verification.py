"""Explicit, isolated verification of the Draftpaper-loop runtime."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .environment_contract import inspect_core_environment

ENVIRONMENT_VERIFICATION_SCHEMA = "dpl.environment_verification.v1"

_XELATEX_SOURCE = r"""\documentclass{article}
\usepackage{fontspec}
\usepackage{graphicx}
\usepackage{natbib}
\usepackage{hyperref}
\usepackage{xurl}
\usepackage{booktabs}
\usepackage{amsmath}
\begin{document}
Draftpaper-loop Unicode smoke test.
\[
  E = mc^2
\]
This sentence cites a known entry \citep{draftpaper2026}.
\bibliographystyle{plainnat}
\bibliography{library}
\end{document}
"""

_PDFLATEX_SOURCE = r"""\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}
\usepackage{natbib}
\usepackage{hyperref}
\usepackage{xurl}
\usepackage{booktabs}
\usepackage{amsmath}
\begin{document}
Draftpaper-loop ASCII fallback smoke test.
\[
  E = mc^2
\]
This sentence cites a known entry \citep{draftpaper2026}.
\bibliographystyle{plainnat}
\bibliography{library}
\end{document}
"""

_BIB_SOURCE = r"""@misc{draftpaper2026,
  author = {Draftpaper Loop},
  title = {Environment verification fixture},
  year = {2026},
  note = {Local test record}
}
"""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _component(report: dict[str, Any], capability_id: str) -> dict[str, Any] | None:
    for item in report.get("components") or []:
        if isinstance(item, dict) and item.get("capability_id") == capability_id:
            return item
    return None


def _tool_path(report: dict[str, Any], capability_id: str) -> str | None:
    item = _component(report, capability_id)
    if item and item.get("status") == "available" and item.get("path"):
        return str(item["path"])
    return shutil.which(capability_id)


def _run(
    command: list[str],
    directory: Path,
    *,
    runner: Callable[..., Any],
) -> dict[str, Any]:
    try:
        result = runner(
            command,
            cwd=directory,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=180,
        )
    except Exception as exc:  # noqa: BLE001 - verification must report tool failures.
        return {
            "status": "failed",
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "error_type": type(exc).__name__,
        }
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "command": command,
        "returncode": result.returncode,
        "stdout": str(getattr(result, "stdout", "") or ""),
        "stderr": str(getattr(result, "stderr", "") or ""),
        "error_type": None,
    }


def _validate_pdf(path: Path) -> dict[str, Any]:
    """Validate the generated artifact with both packaged PDF readers."""

    if not path.is_file() or path.stat().st_size == 0:
        return {
            "status": "failed",
            "page_count": 0,
            "error_type": "PdfMissing",
            "error_message": "The LaTeX command did not produce a non-empty PDF.",
        }
    parsers: dict[str, dict[str, Any]] = {}
    try:
        from pypdf import PdfReader

        page_count = len(PdfReader(str(path)).pages)
    except Exception as exc:  # noqa: BLE001 - the receipt must classify parser failures.
        parsers["pypdf"] = {
            "status": "failed",
            "page_count": 0,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    else:
        parsers["pypdf"] = {
            "status": "passed" if page_count > 0 else "failed",
            "page_count": page_count,
            "error_type": None if page_count > 0 else "PdfEmpty",
            "error_message": None if page_count > 0 else "The generated PDF contains no pages.",
        }
    try:
        import pymupdf

        document = pymupdf.open(str(path))
        pymupdf_page_count = len(document)
        document.close()
    except Exception as exc:  # noqa: BLE001 - native parser failures belong in the receipt.
        parsers["pymupdf"] = {
            "status": "failed",
            "page_count": 0,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    else:
        parsers["pymupdf"] = {
            "status": "passed" if pymupdf_page_count > 0 else "failed",
            "page_count": pymupdf_page_count,
            "error_type": None if pymupdf_page_count > 0 else "PdfEmpty",
            "error_message": None if pymupdf_page_count > 0 else "The generated PDF contains no pages.",
        }
    page_counts = {item["page_count"] for item in parsers.values() if item["status"] == "passed"}
    return {
        "status": "passed" if all(item["status"] == "passed" for item in parsers.values()) and len(page_counts) == 1 else "failed",
        "page_count": next(iter(page_counts), 0),
        "parsers": parsers,
        "error_type": None,
        "error_message": None,
    }


def _probe_vendored_paper_fetch_runtime() -> dict[str, Any]:
    """Probe the vendored CLI with the same import path used by the adapter.

    The upstream package uses absolute ``paper_fetch`` imports.  Running an
    isolated child process with the vendored source on ``PYTHONPATH`` therefore
    tests the actual fallback command and avoids leaking a temporary top-level
    module into the verifier process.
    """

    package_root = Path(__file__).resolve().parent / "_vendor" / "paper_fetch_skill"
    source_root = package_root if (package_root / "paper_fetch" / "cli.py").is_file() else None
    if source_root is None:
        source_root = Path(__file__).resolve().parents[1] / "third_party" / "paper-fetch-skill" / "src"
    if not (source_root / "paper_fetch" / "cli.py").is_file():
        return {
            "status": "failed",
            "module": "paper_fetch.cli",
            "error_type": "VendoredRuntimeMissing",
            "error_message": "The vendored paper-fetch CLI source is not present.",
        }

    environment = os.environ.copy()
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(source_root) + (
        os.pathsep + existing_path if existing_path else ""
    )
    command = [
        sys.executable,
        "-c",
        "from paper_fetch import cli; raise SystemExit(0 if callable(cli.main) else 2)",
    ]
    try:
        completed = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - the verifier must classify runtime failures.
        return {
            "status": "failed",
            "module": "paper_fetch.cli",
            "source": str(source_root),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "module": "paper_fetch.cli",
        "source": str(source_root),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-1000:],
        "stderr": completed.stderr[-2000:],
        "error_type": None if completed.returncode == 0 else "PaperFetchImportFailed",
        "error_message": None if completed.returncode == 0 else "The vendored paper-fetch CLI could not be imported in its adapter environment.",
    }


def _compile_engine(
    *,
    engine_name: str,
    engine_path: str,
    bibtex_path: str,
    directory: Path,
    source: str,
    runner: Callable[..., Any],
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.tex").write_text(source, encoding="utf-8")
    (directory / "library.bib").write_text(_BIB_SOURCE, encoding="utf-8")
    commands = [
        [engine_path, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
        [bibtex_path, "main"],
        [engine_path, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
        [engine_path, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
    ]
    reports = [_run(command, directory, runner=runner) for command in commands]
    pdf = directory / "main.pdf"
    log_text = "\n\n".join(
        f"$ {' '.join(item['command'])}\n{item['stdout']}\n{item['stderr']}"
        for item in reports
    )
    (directory / "compile.log").write_text(log_text, encoding="utf-8")
    normalized_log = log_text.lower()
    fatal = "fatal error" in normalized_log or "! emergency stop" in normalized_log
    final_log = "\n".join(
        [str(reports[-1].get("stdout") or ""), str(reports[-1].get("stderr") or "")]
    )
    final_normalized_log = final_log.lower()
    unresolved_references = bool(
        re.search(r"(?:citation|reference).*?undefined", final_normalized_log)
    ) or "??" in final_log
    pdf_validation = _validate_pdf(pdf)
    status = "passed" if (
        all(item["status"] == "passed" for item in reports)
        and pdf_validation["status"] == "passed"
        and not fatal
        and not unresolved_references
    ) else "failed"
    return {
        "status": status,
        "engine": engine_name,
        "engine_path": engine_path,
        "bibtex_path": bibtex_path,
        "commands": reports,
        "pdf": str(pdf) if pdf.is_file() else None,
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.is_file() else None,
        "log": str(directory / "compile.log"),
        "pdf_validation": pdf_validation,
        "fatal_log_marker": fatal,
        "unresolved_references": unresolved_references,
    }


def _render_html(payload: dict[str, Any], *, language: str) -> str:
    chinese = language == "zh-CN"
    title = "Draftpaper-loop 环境验收报告" if chinese else "Draftpaper-loop Environment Verification"
    status = html.escape(str(payload.get("status") or "unknown"))
    target = html.escape(str(payload.get("target") or ""))
    intro = (
        "本报告由显式环境验收命令生成。所有编译产物均位于本次验收输出目录，不代表任何真实论文项目已被修改。"
        if chinese
        else "This report was produced by the explicit environment verifier. All compilation artifacts are confined to this verification output and no real paper project was modified."
    )
    rows: list[str] = []
    for item in payload.get("environment", {}).get("components") or []:
        if not isinstance(item, dict):
            continue
        label = html.escape(str(item.get("capability_id") or item.get("module") or ""))
        item_status = html.escape(str(item.get("status") or ""))
        observed = html.escape(str(item.get("path") or item.get("module") or ""))
        rows.append(f"<tr><td>{label}</td><td>{item_status}</td><td>{observed}</td></tr>")
    table_title = "能力明细" if chinese else "Capability details"
    return f"""<!doctype html>
<html lang="{language}">
<meta charset="utf-8">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;line-height:1.5}} table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #bbb;padding:.4rem;text-align:left}} .status{{font-weight:700}}</style>
<h1>{title}</h1>
<p class="status">Status: {status} | Target: {target}</p>
<p>{intro}</p>
<h2>{table_title}</h2>
<table><thead><tr><th>Capability</th><th>Status</th><th>Observed</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    <pre>{html.escape(json.dumps({"literature_runtime": payload.get("literature_runtime") or {}, "latex": payload.get("latex") or {}}, ensure_ascii=False, indent=2))}</pre>
</html>
"""


def verify_environment(
    *,
    target: str,
    compile_latex: bool,
    output: str | Path,
    environment_report: dict[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    literature_probe: Callable[[], dict[str, Any]] = _probe_vendored_paper_fetch_runtime,
) -> dict[str, Any]:
    """Verify one target and optionally compile both local LaTeX engine fixtures."""

    environment = environment_report or inspect_core_environment(
        target=target,
        source_kind="source_checkout",
    )
    output_path = Path(output).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": ENVIRONMENT_VERIFICATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "status": environment.get("status", "failed"),
        "environment": environment,
        "literature_runtime": {"status": "not_required"},
        "latex": {"status": "not_requested"},
    }

    if target in {"research", "publication", "agent"}:
        if environment.get("status") == "failed" or environment.get("missing_core"):
            payload["literature_runtime"] = {
                "status": "blocked_missing_core",
                "reason": "The research/full-text environment is incomplete.",
            }
        else:
            payload["literature_runtime"] = literature_probe()
            if payload["literature_runtime"].get("status") != "passed":
                payload["status"] = "failed"

    if compile_latex:
        if environment.get("status") == "failed" or environment.get("missing_core"):
            payload["status"] = "failed"
            payload["latex"] = {
                "status": "blocked_missing_core",
                "reason": "Publication core environment is incomplete.",
            }
        else:
            xelatex = _tool_path(environment, "xelatex")
            pdflatex = _tool_path(environment, "pdflatex")
            bibtex = _tool_path(environment, "bibtex")
            kpsewhich = _tool_path(environment, "kpsewhich")
            if not all((xelatex, pdflatex, bibtex, kpsewhich)):
                payload["status"] = "failed"
                payload["latex"] = {
                    "status": "blocked_missing_core",
                    "reason": "XeLaTeX, pdfLaTeX, BibTeX, and kpsewhich are required for complete verification.",
                }
            else:
                kpsewhich_report = _run([kpsewhich, "plainnat.bst"], output_path, runner=runner)
                if kpsewhich_report["status"] == "passed" and not kpsewhich_report["stdout"].strip():
                    kpsewhich_report.update(
                        status="failed",
                        error_type="ResourceNotResolved",
                        error_message="kpsewhich returned no path for plainnat.bst.",
                    )
                engines = {
                    "xelatex": _compile_engine(
                        engine_name="xelatex",
                        engine_path=xelatex,
                        bibtex_path=bibtex,
                        directory=output_path / "artifacts" / "xelatex",
                        source=_XELATEX_SOURCE,
                        runner=runner,
                    ),
                    "pdflatex": _compile_engine(
                        engine_name="pdflatex",
                        engine_path=pdflatex,
                        bibtex_path=bibtex,
                        directory=output_path / "artifacts" / "pdflatex",
                        source=_PDFLATEX_SOURCE,
                        runner=runner,
                    ),
                }
                payload["latex"] = {
                    "status": "passed" if all(item["status"] == "passed" for item in engines.values()) and kpsewhich_report["status"] == "passed" else "failed",
                    "engines": engines,
                    "kpsewhich": kpsewhich_report,
                }
                payload["status"] = "passed" if (
                    payload["latex"]["status"] == "passed"
                    and environment.get("status") == "passed"
                    and payload["literature_runtime"].get("status") == "passed"
                ) else "failed"

    _write_json(output_path / "environment_verification.json", payload)
    (output_path / "environment_verification.zh-CN.html").write_text(_render_html(payload, language="zh-CN"), encoding="utf-8")
    (output_path / "environment_verification.en.html").write_text(_render_html(payload, language="en"), encoding="utf-8")
    return {
        **payload,
        "output": str(output_path),
        "json": str(output_path / "environment_verification.json"),
        "html_zh": str(output_path / "environment_verification.zh-CN.html"),
        "html_en": str(output_path / "environment_verification.en.html"),
    }
