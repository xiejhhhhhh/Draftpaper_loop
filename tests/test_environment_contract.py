from __future__ import annotations

from pathlib import Path


def test_probe_python_import_reports_native_loader_failure() -> None:
    from draftpaper_cli.environment_contract import probe_python_import

    def fail_import(_: str):
        raise ImportError("DLL load failed while importing _extra: MSVCP140.dll")

    report = probe_python_import("pymupdf", importer=fail_import)

    assert report["status"] == "import_failed"
    assert report["error_type"] == "ImportError"
    assert "Visual C++" in report["remediation_en"]


def test_probe_python_import_distinguishes_missing_module() -> None:
    from draftpaper_cli.environment_contract import probe_python_import

    def fail_import(_: str):
        raise ModuleNotFoundError("No module named 'missing_for_draftpaper_test'")

    report = probe_python_import("missing_for_draftpaper_test", importer=fail_import)

    assert report["status"] == "missing"
    assert report["error_type"] == "ModuleNotFoundError"


def test_probe_executable_reports_path_and_version() -> None:
    from draftpaper_cli.environment_contract import probe_executable

    report = probe_executable(
        "git",
        ("git",),
        which=lambda _: "C:/Program Files/Git/cmd/git.exe",
    )

    assert report["status"] == "available"
    assert report["path"].endswith("git.exe")
    assert report["capability_id"] == "git"


def test_publication_environment_marks_missing_latex_as_core() -> None:
    from draftpaper_cli.environment_contract import inspect_core_environment

    def importer(name: str):
        if name in {"yaml", "bibtexparser", "pypdf", "PIL", "pymupdf"}:
            return object()
        raise ModuleNotFoundError(name)

    report = inspect_core_environment(
        target="publication",
        source_kind="source_checkout",
        platform_name="win32",
        importer=importer,
        which=lambda _: None,
    )

    assert report["status"] == "failed"
    assert {"xelatex", "pdflatex", "bibtex", "kpsewhich"}.issubset(
        {item["capability_id"] for item in report["missing_core"]}
    )


def test_control_environment_does_not_require_latex() -> None:
    from draftpaper_cli.environment_contract import inspect_core_environment

    report = inspect_core_environment(
        target="control",
        source_kind="installed_package",
        platform_name="linux",
        importer=lambda _: object(),
        which=lambda _: None,
    )

    assert report["status"] == "passed"
    assert report["missing_core"] == []


def test_profile_probe_reports_import_failed_separately() -> None:
    from draftpaper_cli.install_profiles import inspect_install_profiles

    def importer(name: str):
        if name in {"fitz", "pymupdf"}:
            raise ImportError("DLL load failed")
        return object()

    report = inspect_install_profiles(importer=importer, python_version=(3, 11, 0))

    fulltext = report["profiles"]["fulltext"]
    assert fulltext["status"] == "import_failed"
    assert "fitz" in fulltext["failed_modules"] or "pymupdf" in fulltext["failed_modules"]


def test_environment_contract_has_safe_project_independent_report(tmp_path: Path) -> None:
    from draftpaper_cli.environment_contract import inspect_core_environment

    report = inspect_core_environment(
        target="control",
        source_kind="installed_package",
        platform_name="linux",
        importer=lambda _: object(),
        which=lambda _: None,
    )

    assert str(tmp_path) not in str(report)
    assert report["schema_version"] == "dpl.core_environment_contract.v1"


def test_doctor_accepts_an_explicit_environment_target() -> None:
    from draftpaper_cli.doctor import doctor_project

    report = doctor_project(target="control")

    assert report["environment"]["core_environment"]["target"] == "control"


def test_doctor_publication_target_exposes_core_missing_components(monkeypatch) -> None:
    from draftpaper_cli import doctor
    from draftpaper_cli.doctor import doctor_project
    from draftpaper_cli.environment_contract import inspect_core_environment

    environment = doctor._environment(target="publication")
    environment["core_environment"] = inspect_core_environment(
        target="publication",
        source_kind="source_checkout",
        platform_name="win32",
        importer=lambda name: object(),
        which=lambda _: None,
    )
    monkeypatch.setattr(doctor, "_environment", lambda *, target="control": environment)

    report = doctor_project(target="publication")

    assert report["environment"]["core_environment"]["target"] == "publication"
    assert report["environment"]["core_environment"]["missing_core"]
