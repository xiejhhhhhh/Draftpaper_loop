"""Check or synchronize repository copies of the canonical workflow Skill."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def skill_copies(root: str | Path) -> tuple[Path, list[Path]]:
    base = Path(root).expanduser().resolve()
    canonical = base / "draftpaper_cli" / "resources" / "draftpaper_workflow"
    copies = [
        base / "codex_skills" / "draftpaper-workflow",
        base / ".claude" / "skills" / "draftpaper-workflow",
        base / "tools" / "claude_code_payload" / "dot_claude" / "skills" / "draftpaper-workflow",
    ]
    return canonical, copies


def sync_skill_copies(root: str | Path, *, write: bool = False) -> dict[str, object]:
    canonical, copies = skill_copies(root)
    files = ("SKILL.md", "contract.json")
    mismatches: list[dict[str, str]] = []
    for target in copies:
        for filename in files:
            source = canonical / filename
            destination = target / filename
            expected = _sha(source) if source.is_file() else None
            actual = _sha(destination) if destination.is_file() else None
            if expected != actual:
                mismatches.append({"destination": str(destination), "expected_sha256": str(expected), "actual_sha256": str(actual)})
                if write and source.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    if write and mismatches:
        return sync_skill_copies(root, write=False)
    return {
        "status": "passed" if not mismatches else "failed",
        "canonical_root": str(canonical),
        "canonical_skill_sha256": _sha(canonical / "SKILL.md") if (canonical / "SKILL.md").is_file() else None,
        "copies": [str(item) for item in copies],
        "mismatches": mismatches,
        "next_command": None if not mismatches else f'python tools/sync_workflow_skill_copies.py --root "{Path(root).resolve()}" --write',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    result = sync_skill_copies(args.root, write=args.write)
    print(result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
