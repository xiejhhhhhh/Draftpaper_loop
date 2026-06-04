from __future__ import annotations

from pathlib import Path

import paper_fetch.providers  # noqa: F401
from paper_fetch.providers._registry import iter_provider_bundles

from tests.unit._owner_reuse_grep import (
    OwnerReuseMatch,
    OwnerReusePattern,
    has_owner_reuse_exception,
    iter_owner_reuse_matches,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_ROOT = PROJECT_ROOT / "src/paper_fetch/providers"


def provider_names() -> tuple[str, ...]:
    return tuple(sorted(bundle.catalog.name for bundle in iter_provider_bundles()))


def provider_owner_reuse_paths(provider: str) -> tuple[Path, ...]:
    candidates = (
        PROVIDER_ROOT / f"{provider}.py",
        PROVIDER_ROOT / f"_{provider}_html.py",
    )
    return tuple(path for path in candidates if path.exists())


def format_owner_reuse_match(match: OwnerReuseMatch) -> str:
    relative_path = match.path.relative_to(PROJECT_ROOT)
    return (
        f"{relative_path}:{match.line_number}: {match.pattern.description}; "
        f"grep={match.pattern.grep_pattern!r}; line={match.line.strip()!r}"
    )


def test_provider_owner_reuse_grep_patterns_are_explained() -> None:
    matches: list[OwnerReuseMatch] = []
    for provider in provider_names():
        for path in provider_owner_reuse_paths(provider):
            matches.extend(iter_owner_reuse_matches(path, provider))

    assert not matches, (
        "Owner reuse grep hits require "
        "# OWNER_REUSE_EXCEPTION: <一句话原因> on the same or previous line:\n"
        + "\n".join(format_owner_reuse_match(match) for match in matches)
    )


def test_owner_reuse_grep_reports_uncommented_hits(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"
    path.write_text("def _header_value(response, name):\n    return None\n")

    matches = iter_owner_reuse_matches(path, "demo")

    assert [match.line_number for match in matches] == [1]
    assert matches[0].pattern.grep_pattern == "def _header_value|def _response_header"


def test_owner_reuse_grep_allows_previous_line_exception(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"
    path.write_text(
        "# OWNER_REUSE_EXCEPTION: publisher private header behavior\n"
        "def _header_value(response, name):\n"
        "    return None\n"
    )

    assert iter_owner_reuse_matches(path, "demo") == ()


def test_owner_reuse_grep_allows_same_line_exception(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"
    path.write_text(
        "def _header_value(response, name):  # OWNER_REUSE_EXCEPTION: test fixture\n"
        "    return None\n"
    )

    assert iter_owner_reuse_matches(path, "demo") == ()


def test_owner_reuse_grep_rejects_empty_exception_reason(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"
    path.write_text(
        "# OWNER_REUSE_EXCEPTION:\n"
        "def _header_value(response, name):\n"
        "    return None\n"
    )

    matches = iter_owner_reuse_matches(path, "demo")

    assert [match.line_number for match in matches] == [2]
    assert not has_owner_reuse_exception("# OWNER_REUSE_EXCEPTION:")


def test_owner_reuse_grep_expands_provider_placeholder(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"
    pattern = OwnerReusePattern(
        description="provider placeholder",
        grep_pattern="def _X_author_(meta|jsonld|dom)_fallback",
        regex_template=r"def _{provider}_author_(meta|jsonld|dom)_fallback",
    )
    path.write_text("def _demo_author_meta_fallback():\n    return []\n")

    matches = iter_owner_reuse_matches(path, "demo", patterns=(pattern,))

    assert [match.line_number for match in matches] == [1]
