"""Deterministic installation-profile diagnostics for local and wheel runtimes."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from typing import Any

PROFILE_MODULES: dict[str, tuple[str, ...]] = {
    "minimal": ("yaml", "bibtexparser", "pypdf", "PIL"),
    "plotting": ("numpy", "pandas", "matplotlib", "scienceplots", "scipy", "seaborn", "sklearn", "rapidocr_onnxruntime"),
    "fulltext": (
        "bs4",
        "cachetools",
        "filelock",
        "filetype",
        "imagesize",
        "idutils",
        "lxml",
        "platformdirs",
        "pydantic",
        "pymupdf",
        "pymupdf4llm",
        "dotenv",
        "rapidfuzz",
        "trafilatura",
        "typing_extensions",
        "urllib3",
    ),
    "browser": ("cloakbrowser", "playwright.sync_api"),
    "mineru-agent": (),
    "mcp": ("mcp", "pydantic"),
}


PROFILE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "minimal": ("workflow_control", "bibliography", "pdf_inspection", "paper_identity_resolution"),
    "plotting": ("publication_figures", "scientific_plugin_runtime", "statistical_plotting"),
    "fulltext": (
        "enhanced_pdf_parsing",
        "pdf_markdown_fallback",
        "vendored_paper_fetch_cli",
        "web_article_extraction",
        "metadata_normalization",
    ),
    "browser": ("publisher_browser_fallback", "playwright_document_fetch"),
    "mineru-agent": ("official_mineru_agent_connector", "conditional_remote_document_parse"),
    "mcp": ("local_stdio_mcp",),
}


PROFILE_PYTHON_RANGES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "minimal": ((3, 10), (3, 13)),
    "plotting": ((3, 10), (3, 13)),
    # The vendored paper-fetch 2.x runtime is supported upstream on 3.11+.
    "fulltext": ((3, 11), (3, 13)),
    "browser": ((3, 11), (3, 13)),
    "mineru-agent": ((3, 10), (3, 13)),
    "mcp": ((3, 10), (3, 13)),
    "research": ((3, 11), (3, 13)),
}


def _python_report(profile: str, version: tuple[int, int, int]) -> dict[str, Any]:
    minimum, maximum = PROFILE_PYTHON_RANGES[profile]
    current = version[:2]
    supported = minimum <= current < maximum
    return {
        "status": "supported" if supported else "unsupported",
        "current": ".".join(str(item) for item in version),
        "minimum": f"{minimum[0]}.{minimum[1]}",
        "maximum_exclusive": f"{maximum[0]}.{maximum[1]}",
    }


def _module_probe(name: str, *, importer: Callable[[str], Any] = importlib.import_module) -> dict[str, Any]:
    try:
        importer(name)
    except ModuleNotFoundError as exc:
        return {
            "status": "missing",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    except ImportError as exc:
        return {
            "status": "import_failed",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - profile probes must classify import failures.
        return {
            "status": "import_failed",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    return {"status": "available", "error_type": None, "error_message": None}


def _module_available(name: str) -> bool:
    return _module_probe(name)["status"] == "available"


def inspect_install_profiles(
    *,
    module_available: Callable[[str], bool] | None = None,
    importer: Callable[[str], Any] = importlib.import_module,
    python_version: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    """Report which documented install profiles are usable in this interpreter."""

    runtime_version = python_version or (
        sys.version_info[0],
        sys.version_info[1],
        sys.version_info[2],
    )

    def probe(name: str) -> dict[str, Any]:
        if module_available is not None:
            return {
                "status": "available" if module_available(name) else "missing",
                "error_type": None,
                "error_message": None,
            }
        return _module_probe(name, importer=importer)

    profiles: dict[str, dict[str, Any]] = {}
    for profile, modules in PROFILE_MODULES.items():
        python = _python_report(profile, runtime_version)
        module_statuses = {name: probe(name) for name in modules}
        missing = [name for name, item in module_statuses.items() if item["status"] == "missing"]
        failed = [name for name, item in module_statuses.items() if item["status"] == "import_failed"]
        extra = None if profile == "minimal" else profile
        install_target = "draftpaper-cli" if extra is None else f"draftpaper-cli[{extra}]"
        profiles[profile] = {
            "status": (
                "unsupported_python"
                if python["status"] != "supported"
                else "import_failed"
                if failed
                else "missing_dependencies"
                if missing
                else "available"
            ),
            "extra": extra,
            "python": python,
            "required_modules": list(modules),
            "missing_modules": missing,
            "failed_modules": failed,
            "module_statuses": module_statuses,
            "capabilities": list(PROFILE_CAPABILITIES[profile]),
            "install_command": f'python -m pip install "{install_target}"',
            "runtime_fallback": "vendored_paper_fetch" if profile == "fulltext" else None,
        }
    research_modules = tuple(dict.fromkeys(
        module
        for profile in ("plotting", "fulltext")
        for module in PROFILE_MODULES[profile]
    ))
    research_statuses = {name: probe(name) for name in research_modules}
    research_missing = [name for name, item in research_statuses.items() if item["status"] == "missing"]
    research_failed = [name for name, item in research_statuses.items() if item["status"] == "import_failed"]
    research_python = _python_report("research", runtime_version)
    profiles["research"] = {
        "status": (
            "unsupported_python"
            if research_python["status"] != "supported"
            else "import_failed"
            if research_failed
            else "missing_dependencies"
            if research_missing
            else "available"
        ),
        "extra": "plotting,fulltext",
        "python": research_python,
        "required_modules": list(research_modules),
        "missing_modules": research_missing,
        "failed_modules": research_failed,
        "module_statuses": research_statuses,
        "capabilities": sorted({
            capability
            for profile in ("plotting", "fulltext")
            for capability in PROFILE_CAPABILITIES[profile]
        }),
        "install_command": 'python -m pip install "draftpaper-cli[plotting,fulltext]"',
        "runtime_fallback": "vendored_paper_fetch",
        "composed_from": ["plotting", "fulltext"],
    }
    missing_optional = [
        name for name in ("plotting", "fulltext", "browser", "mcp")
        if profiles[name]["status"] != "available"
    ]
    return {
        "schema_version": "dpl.install_profile_report.v1",
        "status": "attention" if missing_optional else "passed",
        "profiles": profiles,
        "missing_optional_profiles": missing_optional,
        "boundary": "Missing optional profiles disable only their declared capabilities; they do not invalidate the minimal control plane.",
    }
