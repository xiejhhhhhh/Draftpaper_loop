"""Validate that wheel metadata exposes one minimal core and explicit optional profiles."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any


HEAVY_PLOTTING_PACKAGES = {"matplotlib", "scienceplots", "numpy", "pandas", "seaborn"}
PROFILE_NAMES = ("minimal", "plotting", "fulltext", "mcp")


def _normalized_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    return match.group(1).lower().replace("_", "-") if match else ""


def _requirement_extra(requirement: str) -> str | None:
    match = re.search(r"\bextra\s*==\s*['\"]([^'\"]+)['\"]", requirement)
    return match.group(1) if match else None


def inspect_wheel_install_profiles(wheel: str | Path) -> dict[str, Any]:
    wheel_path = Path(wheel).resolve()
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError(f"Expected one wheel METADATA file, found {len(metadata_names)}.")
        message = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
    requirements = list(message.get_all("Requires-Dist") or [])
    profiles: dict[str, dict[str, Any]] = {
        name: {"packages": [], "requirements": []}
        for name in PROFILE_NAMES
    }
    for requirement in requirements:
        extra = _requirement_extra(requirement)
        profile = extra if extra in profiles else "minimal" if extra is None else None
        if profile is None:
            continue
        package = _normalized_name(requirement)
        profiles[profile]["requirements"].append(requirement)
        if package:
            profiles[profile]["packages"].append(package)
    for profile in profiles.values():
        profile["packages"] = sorted(set(profile["packages"]))
        profile["requirements"] = sorted(profile["requirements"])

    issues: list[str] = []
    core = set(profiles["minimal"]["packages"])
    leaked = sorted(core & HEAVY_PLOTTING_PACKAGES)
    if leaked:
        issues.append(f"plotting_packages_in_minimal:{','.join(leaked)}")
    plotting = set(profiles["plotting"]["packages"])
    missing_plotting = sorted(HEAVY_PLOTTING_PACKAGES - plotting)
    if missing_plotting:
        issues.append(f"plotting_profile_missing:{','.join(missing_plotting)}")
    if not profiles["fulltext"]["packages"]:
        issues.append("fulltext_profile_empty")
    if "mcp" not in profiles["mcp"]["packages"]:
        issues.append("mcp_profile_missing_mcp")
    return {
        "schema_version": "dpl.install_matrix_validation.v1",
        "status": "passed" if not issues else "failed",
        "wheel": str(wheel_path),
        "package_version": message.get("Version"),
        "profiles": profiles,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--wheel-dir", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    wheels = [args.wheel] if args.wheel else sorted(args.wheel_dir.glob("draftpaper_cli-*.whl"))
    if not wheels or wheels[-1] is None or not wheels[-1].is_file():
        raise SystemExit("No draftpaper-cli wheel was found.")
    report = inspect_wheel_install_profiles(wheels[-1])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
