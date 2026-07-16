"""Fail CI on likely first-party credentials while excluding vendored fixtures."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNED_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".toml", ".ps1", ".sh"}
EXCLUDED_PREFIXES = ("third_party/", "draftpaper_cli/_vendor/", "tests/", "docs/", "tmp/")
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "credential_assignment": re.compile(
        r"(?i)(?:api[_-]?key|password|passwd|secret|authorization|bearer)\s*[:=]\s*[\"']([^\"']{12,})[\"']"
    ),
}
PLACEHOLDERS = ("example", "placeholder", "redacted", "your_", "dummy", "test-only", "fixture")


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / raw.decode("utf-8") for raw in completed.stdout.split(b"\0") if raw]


def scan() -> list[str]:
    findings: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(EXCLUDED_PREFIXES) or path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            for name, pattern in PATTERNS.items():
                match = pattern.search(line)
                if not match:
                    continue
                value = match.group(1).lower() if match.lastindex else ""
                if value and any(token in value for token in PLACEHOLDERS):
                    continue
                findings.append(f"{relative}:{line_number}:{name}")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("Potential first-party secrets detected:")
        print("\n".join(findings))
        return 1
    print("No likely first-party credentials detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
