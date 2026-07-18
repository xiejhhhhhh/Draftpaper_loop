from __future__ import annotations

import builtins
import importlib
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.doctor import doctor_project
from draftpaper_cli.schema_registry import schema_family
from draftpaper_cli.toml_compat import tomllib


HEAVY_PLOTTING_PACKAGES = {"matplotlib", "scienceplots", "numpy", "pandas", "seaborn"}


def _package_name(requirement: str) -> str:
    return requirement.split(";", 1)[0].split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].strip().lower()


def test_default_install_excludes_plotting_stack_and_extras_own_it() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    core = {_package_name(item) for item in pyproject["project"]["dependencies"]}
    plotting = {_package_name(item) for item in pyproject["project"]["optional-dependencies"]["plotting"]}

    assert core.isdisjoint(HEAVY_PLOTTING_PACKAGES)
    assert HEAVY_PLOTTING_PACKAGES <= plotting


def test_control_plane_imports_without_numpy() -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "numpy" or name.startswith("numpy."):
            raise ModuleNotFoundError("numpy intentionally unavailable in minimal profile")
        return original_import(name, *args, **kwargs)

    cleared = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "draftpaper_cli.scientific_plugin_runtime" or name.startswith("draftpaper_cli.discipline_modules")
    }
    for name in cleared:
        sys.modules.pop(name, None)
    try:
        with patch("builtins.__import__", side_effect=guarded_import):
            module = importlib.import_module("draftpaper_cli.discipline_modules.manifest_runtime")
            assert callable(module.dynamic_manifest_module)
    finally:
        for name in list(sys.modules):
            if name == "draftpaper_cli.scientific_plugin_runtime" or name.startswith("draftpaper_cli.discipline_modules"):
                sys.modules.pop(name, None)
        sys.modules.update(cleared)


def test_doctor_reports_install_profiles_and_recovery_commands() -> None:
    report = doctor_project()
    profiles = report["environment"]["install_profiles"]["profiles"]

    assert set(profiles) >= {"minimal", "plotting", "fulltext", "mcp"}
    assert profiles["minimal"]["status"] == "available"
    for profile in ("plotting", "fulltext", "mcp"):
        assert profiles[profile]["install_command"].endswith(f'[{profile}]"')
        assert profiles[profile]["status"] in {"available", "missing_dependencies"}


def test_install_profile_report_distinguishes_missing_modules() -> None:
    from draftpaper_cli.install_profiles import inspect_install_profiles

    available = {"yaml", "bibtexparser", "pypdf", "PIL"}
    report = inspect_install_profiles(module_available=lambda name: name in available)

    assert report["status"] == "attention"
    assert report["profiles"]["minimal"]["status"] == "available"
    assert report["profiles"]["plotting"]["status"] == "missing_dependencies"
    assert "matplotlib" in report["profiles"]["plotting"]["missing_modules"]
    assert report["profiles"]["fulltext"]["runtime_fallback"] == "vendored_paper_fetch"
    assert schema_family("dpl.install_profile_report.v1") == "install_profile_report"
    assert schema_family("dpl.install_matrix_validation.v1") == "install_matrix_validation"


def test_ci_installs_plotting_profile_explicitly() -> None:
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert '-e .[dev,plotting]' in workflow
    assert "install-profile-smoke:" in workflow
    assert "profile: [minimal, plotting, fulltext, mcp]" in workflow


def test_wheel_metadata_install_matrix_separates_core_and_extras(tmp_path: Path) -> None:
    from tools.verify_install_matrix import inspect_wheel_install_profiles

    wheel = tmp_path / "draftpaper_cli-0.0-py3-none-any.whl"
    metadata = """Metadata-Version: 2.4
Name: draftpaper-cli
Version: 0.0
Requires-Dist: Pillow>=10
Requires-Dist: PyYAML>=6
Requires-Dist: matplotlib>=3.8; extra == \"plotting\"
Requires-Dist: numpy>=1.24; extra == \"plotting\"
Requires-Dist: pandas>=2; extra == \"plotting\"
Requires-Dist: SciencePlots>=2.1; extra == \"plotting\"
Requires-Dist: seaborn>=0.13; extra == \"plotting\"
Requires-Dist: beautifulsoup4; extra == \"fulltext\"
Requires-Dist: mcp>=1.10; extra == \"mcp\"
"""
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("draftpaper_cli-0.0.dist-info/METADATA", metadata)

    report = inspect_wheel_install_profiles(wheel)

    assert report["status"] == "passed"
    assert "matplotlib" not in report["profiles"]["minimal"]["packages"]
    assert "matplotlib" in report["profiles"]["plotting"]["packages"]
    assert "beautifulsoup4" in report["profiles"]["fulltext"]["packages"]
    assert "mcp" in report["profiles"]["mcp"]["packages"]
