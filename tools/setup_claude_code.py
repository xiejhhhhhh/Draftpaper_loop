"""Materialize the Claude Code project surface from tools/claude_code_payload/.

Remote file bridges refuse to write `.claude/`, `.mcp.json`, and GitHub
workflow files directly (a sensible security boundary). This script copies the
committed payload into place locally, so the repository can carry those files.

Usage (from the repository root):

    python tools/setup_claude_code.py          # copy payload into place
    python tools/setup_claude_code.py --check  # verify payload and targets match
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_ROOT = REPO_ROOT / "tools" / "claude_code_payload"


def _target_relative(relative: Path) -> Path:
    """Map payload names to real targets: a leading `dot_` becomes a dot.

    Payload files are stored dot-free (`dot_claude/...`, `dot_mcp.json`,
    `dot_github/...`) so they can be transferred by tools that refuse to write
    dotted configuration paths directly.
    """

    first, *rest = relative.parts
    if first.startswith("dot_"):
        first = "." + first[len("dot_"):]
    return Path(first, *rest)


def _targets() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for source in sorted(PAYLOAD_ROOT.rglob("*")):
        if source.is_file():
            relative = source.relative_to(PAYLOAD_ROOT)
            pairs.append((source, REPO_ROOT / _target_relative(relative)))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify targets match the payload without writing.")
    args = parser.parse_args(argv)
    pairs = _targets()
    if not pairs:
        print("No payload files found under tools/claude_code_payload/.", file=sys.stderr)
        return 1
    stale = []
    for source, target in pairs:
        if args.check:
            if not target.is_file() or not filecmp.cmp(source, target, shallow=False):
                stale.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(f"wrote {target.relative_to(REPO_ROOT)}")
    if args.check:
        if stale:
            print("Out of date targets:", *[str(path.relative_to(REPO_ROOT)) for path in stale], sep="\n  ", file=sys.stderr)
            return 1
        print(f"All {len(pairs)} Claude Code files match the payload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
