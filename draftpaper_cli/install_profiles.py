"""Deterministic installation-profile diagnostics for local and wheel runtimes."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any


PROFILE_MODULES: dict[str, tuple[str, ...]] = {
    "minimal": ("yaml", "bibtexparser", "pypdf", "PIL"),
    "plotting": ("numpy", "pandas", "matplotlib", "scienceplots", "scipy", "seaborn", "sklearn"),
    "fulltext": (
        "bs4",
        "cachetools",
        "filelock",
        "filetype",
        "idutils",
        "lxml",
        "platformdirs",
        "pydantic",
        "fitz",
        "dotenv",
        "rapidfuzz",
        "trafilatura",
        "urllib3",
    ),
    "mcp": ("mcp", "pydantic"),
}


PROFILE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "minimal": ("workflow_control", "bibliography", "pdf_inspection", "vendored_paper_fetch"),
    "plotting": ("publication_figures", "scientific_plugin_runtime", "statistical_plotting"),
    "fulltext": ("enhanced_pdf_parsing", "web_article_extraction", "metadata_normalization"),
    "mcp": ("local_stdio_mcp",),
}


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def inspect_install_profiles(
    *,
    module_available: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Report which documented install profiles are usable in this interpreter."""

    available = module_available or _module_available
    profiles: dict[str, dict[str, Any]] = {}
    for profile, modules in PROFILE_MODULES.items():
        missing = [name for name in modules if not available(name)]
        extra = None if profile == "minimal" else profile
        install_target = "draftpaper-cli" if extra is None else f"draftpaper-cli[{extra}]"
        profiles[profile] = {
            "status": "available" if not missing else "missing_dependencies",
            "extra": extra,
            "required_modules": list(modules),
            "missing_modules": missing,
            "capabilities": list(PROFILE_CAPABILITIES[profile]),
            "install_command": f'python -m pip install "{install_target}"',
            "runtime_fallback": "vendored_paper_fetch" if profile == "fulltext" else None,
        }
    missing_optional = [name for name in ("plotting", "fulltext", "mcp") if profiles[name]["missing_modules"]]
    return {
        "schema_version": "dpl.install_profile_report.v1",
        "status": "attention" if missing_optional else "passed",
        "profiles": profiles,
        "missing_optional_profiles": missing_optional,
        "boundary": "Missing optional profiles disable only their declared capabilities; they do not invalidate the minimal control plane.",
    }
