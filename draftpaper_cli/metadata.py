# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .provenance import PROJECT_PROVENANCE


GENERATOR_NAME = "Draftpaper-loop"
GENERATOR_URL = "https://github.com/xiejhhhhhh/Draftpaper_loop"
GENERATOR_CONTACT = "xiejinhui22@mails.ucas.ac.cn"
GENERATOR_TEX_COMMENT = (
    "% Generated with Draftpaper-loop: https://github.com/xiejhhhhhh/Draftpaper_loop\n"
    "% Commercial use requires prior written authorization: xiejinhui22@mails.ucas.ac.cn\n"
)
PYTHON_SOURCE_NOTICE = (
    "# Copyright (c) 2026 xiejhhhhhh\n"
    "# Contact: xiejinhui22@mails.ucas.ac.cn\n"
    "# Source-available for non-commercial use only; commercial use requires written authorization.\n\n"
)
GENERATOR_HTML_META = (
    '  <meta name="generator" content="Draftpaper-loop">\n'
    '  <meta name="draftpaper-loop" content="https://github.com/xiejhhhhhh/Draftpaper_loop">\n'
)


def attach_generator_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach stable provenance metadata to generated reports without mutating callers."""
    enriched = dict(payload)
    enriched.setdefault("generated_by", GENERATOR_NAME)
    enriched.setdefault("generator_url", GENERATOR_URL)
    enriched.setdefault("generator_contact", GENERATOR_CONTACT)
    enriched.setdefault("generator_license", PROJECT_PROVENANCE["license"])
    enriched.setdefault("generator_sponsorship_note", PROJECT_PROVENANCE["sponsorship_note"])
    return enriched
