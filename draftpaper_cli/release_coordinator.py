"""One release entry point for accepted prose, parity, and hard correctness."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def assess_release_bundle(project: str | Path) -> dict[str, Any]:
    from .paper_quality_parity import assess_paper_quality_parity
    from .writing_architecture import assess_functional_quality_release

    functional = assess_functional_quality_release(project)
    parity = assess_paper_quality_parity(project)
    return {
        "schema_version": "dpl.release_status.v2",
        "decision": "pass" if functional.get("decision") == "pass" and parity.get("decision") == "pass" else "blocked",
        "functional_quality_release": functional,
        "paper_quality_parity": parity,
    }
