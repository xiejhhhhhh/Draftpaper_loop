# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import re


CITATION_KEY_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}",
    re.IGNORECASE,
)

CITATION_COMMAND_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{",
    re.IGNORECASE,
)

BIBTEX_KEY_PATTERN = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.IGNORECASE)


def citation_keys_in_text(text: str) -> set[str]:
    keys: set[str] = set()
    for match in CITATION_KEY_PATTERN.finditer(text or ""):
        keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def bibtex_keys_in_text(text: str) -> set[str]:
    return {match.group(1).strip() for match in BIBTEX_KEY_PATTERN.finditer(text or "") if match.group(1).strip()}


def has_citation_command(text: str) -> bool:
    return bool(CITATION_COMMAND_PATTERN.search(text or ""))
