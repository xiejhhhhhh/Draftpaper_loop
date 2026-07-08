# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.reference_usage import ensure_reference_usage_plan, missing_entries_for_section
from draftpaper_cli.references import citation_evidence_rows


class ReferenceUsagePlanTests(unittest.TestCase):
    def test_citation_evidence_rows_include_discussion_for_retained_references(self) -> None:
        rows = citation_evidence_rows([
            {
                "bibtex_key": "Retained2026",
                "title": "Retained reference",
                "abstract": "Evidence for discussion synthesis.",
                "search_contexts": ["methods"],
                "source": "fixture",
            }
        ])

        sections = {row["section"] for row in rows if row["citation_key"] == "Retained2026"}
        self.assertIn("methods", sections)
        self.assertIn("discussion", sections)

    def test_plan_refreshes_when_literature_and_bib_keys_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            refs = project / "references"
            refs.mkdir(parents=True)
            (refs / "literature_items.json").write_text(
                json.dumps([{"bibtex_key": "New2026", "title": "New retained method reference"}]),
                encoding="utf-8",
            )
            (refs / "library.bib").write_text("@article{New2026,title={New}}", encoding="utf-8")
            (refs / "citation_evidence.csv").write_text(
                "citation_key,section,claim,evidence_summary,source,doi,url\n"
                "New2026,methods,method background,New evidence,source,,\n",
                encoding="utf-8",
            )
            (refs / "reference_usage_plan.json").write_text(
                json.dumps(
                    {
                        "entries": [
                            {"citation_key": "Old2020", "required": True, "target_section": "methods", "evidence_summary": "Old evidence"}
                        ],
                        "source_literature_keys": ["Old2020"],
                        "source_bibtex_keys": ["Old2020"],
                    }
                ),
                encoding="utf-8",
            )

            plan = ensure_reference_usage_plan(project)
            entries = missing_entries_for_section(project, "methods", "")

            self.assertEqual([entry["citation_key"] for entry in plan["entries"]], ["New2026"])
            self.assertEqual([entry["citation_key"] for entry in entries], ["New2026"])


if __name__ == "__main__":
    unittest.main()
