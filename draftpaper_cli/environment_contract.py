"""Read-only probes for the core Draftpaper-loop publication environment."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from .install_profiles import PROFILE_MODULES, inspect_install_profiles

CORE_ENVIRONMENT_SCHEMA = "dpl.core_environment_contract.v1"
ENVIRONMENT_TARGETS = {"control", "research", "publication", "agent"}

_CONTROL_MODULES = ("yaml", "bibtexparser", "pypdf", "PIL")
_RESEARCH_PROFILES = ("plotting", "fulltext")
_LATEX_EXECUTABLES = ("xelatex", "pdflatex", "bibtex", "kpsewhich")


def _import_failure_remediation(name: str, message: str) -> tuple[str, str]:
    lower = message.lower()
    if name in {"fitz", "pymupdf"} and ("dll" in lower or "load failed" in lower):
        return (
            "修复 Visual C++ x64 运行库后重新安装 PyMuPDF，并再次运行环境验收。",
            "Repair the Microsoft Visual C++ x64 runtime, reinstall PyMuPDF, and rerun environment verification.",
        )
    return (
        f"检查 {name} 的安装版本和依赖后重新安装对应 Draftpaper profile。",
        f"Check the installation and dependencies for {name}, then reinstall the corresponding Draftpaper profile.",
    )


def probe_python_import(
    name: str,
    *,
    importer: Callable[[str], ModuleType] = importlib.import_module,
) -> dict[str, Any]:
    """Import a module so native-loader failures are not reported as available."""

    try:
        importer(name)
    except ModuleNotFoundError as exc:
        message = str(exc)
        missing_name = getattr(exc, "name", None)
        status = "missing" if missing_name in {None, name} or f"No module named '{name}'" in message else "import_failed"
        remediation_zh, remediation_en = _import_failure_remediation(name, message)
        return {
            "module": name,
            "status": status,
            "error_type": type(exc).__name__,
            "error_message": message,
            "remediation_zh": remediation_zh,
            "remediation_en": remediation_en,
        }
    except ImportError as exc:
        message = str(exc)
        remediation_zh, remediation_en = _import_failure_remediation(name, message)
        return {
            "module": name,
            "status": "import_failed",
            "error_type": type(exc).__name__,
            "error_message": message,
            "remediation_zh": remediation_zh,
            "remediation_en": remediation_en,
        }
    except Exception as exc:  # noqa: BLE001 - import probes must classify loader failures.
        message = str(exc)
        remediation_zh, remediation_en = _import_failure_remediation(name, message)
        return {
            "module": name,
            "status": "import_failed",
            "error_type": type(exc).__name__,
            "error_message": message,
            "remediation_zh": remediation_zh,
            "remediation_en": remediation_en,
        }
    return {
        "module": name,
        "status": "available",
        "error_type": None,
        "error_message": None,
        "remediation_zh": None,
        "remediation_en": None,
    }


def _private_runtime_git(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    return "/.cache/codex-runtimes/" in normalized or "/codex-runtimes/" in normalized


def probe_executable(
    capability_id: str,
    candidates: tuple[str, ...],
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Resolve an executable without running it; execution belongs to smoke tests."""

    path = None
    for candidate in candidates:
        path = which(candidate)
        if path:
            break
    if not path:
        return {
            "capability_id": capability_id,
            "status": "missing",
            "path": None,
            "candidates": list(candidates),
            "error_type": "ExecutableNotFound",
            "error_message": f"None of {', '.join(candidates)} was found on PATH.",
            "remediation_zh": f"安装并加入 PATH：{capability_id}。",
            "remediation_en": f"Install {capability_id} and add it to PATH.",
        }
    if capability_id == "git" and _private_runtime_git(path):
        return {
            "capability_id": capability_id,
            "status": "non_standalone_tool",
            "path": path,
            "candidates": list(candidates),
            "error_type": "PrivateRuntimeExecutable",
            "error_message": "The resolved Git executable belongs to a Codex private runtime.",
            "remediation_zh": "安装系统 Git for Windows，并在新的 shell 中重新检查 PATH。",
            "remediation_en": "Install system Git for Windows and recheck PATH in a new shell.",
        }
    return {
        "capability_id": capability_id,
        "status": "available",
        "path": path,
        "candidates": list(candidates),
        "error_type": None,
        "error_message": None,
        "remediation_zh": None,
        "remediation_en": None,
    }


def _standard_executable_paths(capability_id: str) -> tuple[str, ...]:
    """Return conventional Windows install locations before inherited PATH."""

    if sys.platform != "win32":
        return ()
    local_appdata = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    paths: list[Path] = []
    if capability_id == "git":
        paths.extend(
            [
                Path(program_files) / "Git" / "cmd" / "git.exe",
                Path(program_files) / "Git" / "bin" / "git.exe",
            ]
        )
        if local_appdata:
            paths.append(Path(local_appdata) / "Programs" / "Git" / "cmd" / "git.exe")
    elif capability_id in _LATEX_EXECUTABLES:
        if local_appdata:
            paths.append(
                Path(local_appdata)
                / "Programs"
                / "MiKTeX"
                / "miktex"
                / "bin"
                / "x64"
                / f"{capability_id}.exe"
            )
        paths.append(
            Path(program_files)
            / "MiKTeX"
            / "miktex"
            / "bin"
            / "x64"
            / f"{capability_id}.exe"
        )
    return tuple(str(path) for path in paths if path.is_file())


def _probe_environment_executable(
    capability_id: str,
    candidates: tuple[str, ...],
    *,
    which: Callable[[str], str | None],
) -> dict[str, Any]:
    if which is shutil.which:
        standard = _standard_executable_paths(capability_id)
        if standard:
            return probe_executable(capability_id, standard, which=lambda _: standard[0])
    return probe_executable(capability_id, candidates, which=which)


def _module_names(target: str) -> tuple[str, ...]:
    names = list(_CONTROL_MODULES)
    if target in {"research", "publication", "agent"}:
        for profile in _RESEARCH_PROFILES:
            names.extend(PROFILE_MODULES[profile])
    if target == "agent":
        names.extend(PROFILE_MODULES["mcp"])
    return tuple(dict.fromkeys(names))


def _profile_module_report(
    name: str,
    *,
    importer: Callable[[str], ModuleType],
) -> dict[str, Any]:
    return probe_python_import(name, importer=importer)


def inspect_core_environment(
    *,
    target: str,
    source_kind: str,
    platform_name: str | None = None,
    importer: Callable[[str], ModuleType] = importlib.import_module,
    which: Callable[[str], str | None] = shutil.which,
    profile_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic capability report for one environment target."""

    if target not in ENVIRONMENT_TARGETS:
        raise ValueError(f"Unknown environment target: {target}")
    platform_name = platform_name or sys.platform
    components: list[dict[str, Any]] = []
    for name in _module_names(target):
        component = _profile_module_report(name, importer=importer)
        component.update({
            "capability_id": f"python_import:{name}",
            "requirement_level": "core",
            "required_for": target,
        })
        components.append(component)

    if target == "publication":
        for capability_id in _LATEX_EXECUTABLES:
            component = _probe_environment_executable(
                capability_id,
                (capability_id, f"{capability_id}.exe"),
                which=which,
            )
            component.update({"requirement_level": "core", "required_for": target})
            components.append(component)
        if source_kind == "source_checkout":
            component = _probe_environment_executable("git", ("git", "git.exe"), which=which)
            component.update({"requirement_level": "core", "required_for": "source_checkout"})
            components.append(component)

    if target == "agent":
        component = _probe_environment_executable("git", ("git", "git.exe"), which=which)
        component.update({"requirement_level": "conditional", "required_for": "agent"})
        components.append(component)

    unavailable = [item for item in components if item["status"] != "available"]
    missing_core = [
        item for item in unavailable
        if item.get("requirement_level") == "core"
    ]
    optional_unavailable = [
        item for item in unavailable
        if item.get("requirement_level") != "core"
    ]
    profile_report = profile_report or inspect_install_profiles(importer=importer)
    return {
        "schema_version": CORE_ENVIRONMENT_SCHEMA,
        "target": target,
        "status": "failed" if missing_core else "attention" if optional_unavailable else "passed",
        "platform": platform_name,
        "source_kind": source_kind,
        "components": components,
        "missing_core": missing_core,
        "optional_unavailable": optional_unavailable,
        "profile_report": profile_report,
        "environment_variables": {
            "localappdata_present": bool(os.environ.get("LOCALAPPDATA")) if platform_name == "win32" else None,
        },
    }
