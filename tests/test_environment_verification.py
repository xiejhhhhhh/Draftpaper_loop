from __future__ import annotations

import json
from pathlib import Path


def _passed_environment() -> dict:
    return {
        "schema_version": "dpl.core_environment_contract.v1",
        "target": "control",
        "status": "passed",
        "platform": "win32",
        "source_kind": "installed_package",
        "components": [
            {
                "capability_id": "python_import:yaml",
                "module": "yaml",
                "status": "available",
                "requirement_level": "core",
                "required_for": "control",
            },
            {
                "capability_id": "python_import:pymupdf",
                "module": "pymupdf",
                "status": "available",
                "requirement_level": "core",
                "required_for": "publication",
            },
        ],
        "missing_core": [],
        "optional_unavailable": [],
    }


def test_verify_environment_writes_machine_and_bilingual_receipts(tmp_path: Path) -> None:
    from draftpaper_cli.environment_verification import verify_environment

    report = verify_environment(
        target="control",
        compile_latex=False,
        output=tmp_path / "verification",
        environment_report=_passed_environment(),
    )

    assert report["status"] == "passed"
    assert (tmp_path / "verification" / "environment_verification.json").is_file()
    assert (tmp_path / "verification" / "environment_verification.zh-CN.html").is_file()
    assert (tmp_path / "verification" / "environment_verification.en.html").is_file()
    payload = json.loads((tmp_path / "verification" / "environment_verification.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dpl.environment_verification.v1"


def test_verify_environment_refuses_compile_when_core_environment_is_missing(tmp_path: Path) -> None:
    from draftpaper_cli.environment_verification import verify_environment

    environment = _passed_environment()
    environment["target"] = "publication"
    environment["status"] = "failed"
    environment["missing_core"] = [
        {
            "capability_id": "xelatex",
            "status": "missing",
            "requirement_level": "core",
            "required_for": "publication",
        }
    ]

    report = verify_environment(
        target="publication",
        compile_latex=True,
        output=tmp_path / "verification",
        environment_report=environment,
    )

    assert report["status"] == "failed"
    assert report["latex"]["status"] == "blocked_missing_core"
    assert not (tmp_path / "verification" / "artifacts").exists()


def test_verify_environment_uses_injected_runner_for_both_engines(tmp_path: Path) -> None:
    from draftpaper_cli.environment_verification import verify_environment

    environment = _passed_environment()
    environment["target"] = "publication"
    environment["components"].extend(
        {
            "capability_id": name,
            "status": "available",
            "path": f"C:/MiKTeX/bin/{name}.exe",
            "requirement_level": "core",
            "required_for": "publication",
        }
        for name in ("xelatex", "pdflatex", "bibtex", "kpsewhich")
    )

    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append([str(item) for item in command])

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        tool_name = Path(str(command[0])).stem
        if tool_name in {"xelatex", "pdflatex"}:
            from pypdf import PdfWriter

            pdf = Path(kwargs["cwd"]) / "main.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with pdf.open("wb") as stream:
                writer.write(stream)
        elif tool_name == "kpsewhich":
            Result.stdout = "C:/MiKTeX/tex/latex/base/plainnat.bst\n"
        return Result()

    report = verify_environment(
        target="publication",
        compile_latex=True,
        output=tmp_path / "verification",
        environment_report=environment,
        runner=runner,
    )

    assert report["status"] == "passed"
    assert report["latex"]["engines"]["xelatex"]["status"] == "passed"
    assert report["latex"]["engines"]["pdflatex"]["status"] == "passed"
    assert report["latex"]["engines"]["xelatex"]["pdf_validation"]["parsers"]["pypdf"]["status"] == "passed"
    assert report["latex"]["engines"]["xelatex"]["pdf_validation"]["parsers"]["pymupdf"]["status"] == "passed"
    assert any(Path(command[0]).stem == "bibtex" for command in calls)


def test_verify_environment_is_registered_with_explicit_compile_options() -> None:
    from draftpaper_cli.cli import build_parser
    from draftpaper_cli.command_registry import command_spec

    args = build_parser().parse_args(
        [
            "verify-environment",
            "--target",
            "publication",
            "--compile-latex",
            "--output",
            ".tmp/verification",
        ]
    )

    assert args.target == "publication"
    assert args.compile_latex is True
    assert command_spec("verify-environment") is not None


def test_package_module_entrypoint_is_available_for_documented_python_invocation() -> None:
    import draftpaper_cli.__main__ as entrypoint

    assert callable(entrypoint.main)
