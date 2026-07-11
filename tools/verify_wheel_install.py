"""Verify that a built wheel preserves the source discipline-plugin registry."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


RESOURCE_PATTERNS = ("*.json", "*.csv", "*.md")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ENTRY_COUNT = 209
EXPECTED_FIXTURE_COUNT = 545


def _resource_counts(root: Path) -> dict[str, int]:
    return {pattern: len(list(root.rglob(pattern))) for pattern in RESOURCE_PATTERNS}


def _fixture_count(entries: list[dict[str, object]]) -> int:
    return sum(len(entry.get("fixtures") or []) for entry in entries)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    args = parser.parse_args()

    wheels = [args.wheel] if args.wheel else sorted((args.wheel_dir or Path("dist")).glob("draftpaper_cli-*.whl"))
    if not wheels or wheels[-1] is None or not wheels[-1].is_file():
        raise SystemExit("No draftpaper-cli wheel was found.")
    wheel = wheels[-1].resolve()

    sys.path.insert(0, str(REPOSITORY_ROOT))
    from draftpaper_cli.template_registry import discover_template_registry

    source = discover_template_registry()
    if not Path(source["root"]).resolve().is_relative_to(REPOSITORY_ROOT):
        raise SystemExit(f"Source registry resolved outside the checkout: {source['root']}")
    source_root = Path(source["root"])
    source_summary = {
        "entry_count": source["entry_count"],
        "fixture_count": _fixture_count(source["entries"]),
        "resource_counts": _resource_counts(source_root),
    }

    if source_summary["entry_count"] != EXPECTED_ENTRY_COUNT or source_summary["fixture_count"] != EXPECTED_FIXTURE_COUNT:
        raise SystemExit(
            f"Source registry contract changed: expected {EXPECTED_ENTRY_COUNT}/{EXPECTED_FIXTURE_COUNT}, "
            f"got {source_summary['entry_count']}/{source_summary['fixture_count']}."
        )

    with tempfile.TemporaryDirectory(prefix="draftpaper-wheel-") as temp:
        temp_root = Path(temp)
        environment = temp_root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheel)],
            check=True,
        )
        probe = """
import json
from pathlib import Path
from draftpaper_cli.template_registry import discover_template_registry
r = discover_template_registry()
root = Path(r['root'])
print(json.dumps({
    'entry_count': r['entry_count'],
    'fixture_count': sum(len(e.get('fixtures') or []) for e in r['entries']),
    'resource_counts': {p: len(list(root.rglob(p))) for p in ('*.json', '*.csv', '*.md')},
}))
"""
        completed = subprocess.run(
            [str(python), "-c", probe],
            check=True,
            cwd=temp_root,
            capture_output=True,
            text=True,
        )
        installed_summary = json.loads(completed.stdout.strip().splitlines()[-1])
        regression_root = temp_root / "release-regressions"
        release_completed = subprocess.run(
            [str(python), "-m", "draftpaper_cli.release_regression", "--output", str(regression_root)],
            check=True,
            cwd=temp_root,
            capture_output=True,
            text=True,
        )
        release_report = json.loads(release_completed.stdout)

    report = {
        "wheel": str(wheel),
        "source": source_summary,
        "installed": installed_summary,
        "matched": source_summary == installed_summary,
        "release_regressions": {
            "status": release_report.get("status"),
            "domain_fixture_ids": [item.get("fixture_id") for item in release_report.get("domain_regressions") or []],
            "adversarial_checks": (release_report.get("adversarial_regressions") or {}).get("checks") or {},
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    release_passed = (
        report["release_regressions"]["status"] == "passed"
        and len(report["release_regressions"]["domain_fixture_ids"]) == 3
        and all(report["release_regressions"]["adversarial_checks"].values())
    )
    return 0 if report["matched"] and release_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
