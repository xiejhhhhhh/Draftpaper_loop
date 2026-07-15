# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.project_scaffold import create_project


class PaperFetchAdapterTests(unittest.TestCase):
    def test_fulltext_cache_stem_is_bounded_for_windows_path_budget(self) -> None:
        from draftpaper_cli.paper_fetch_adapter import _safe_stem

        stem = _safe_stem("A " + "very long scientific paper title " * 10, "paper")
        self.assertLessEqual(len(stem), 48)

    def test_adapter_enriches_weak_context_items_from_paper_fetch_output(self) -> None:
        from draftpaper_cli.paper_fetch_adapter import enrich_with_paper_fetch

        calls = []

        def fake_runner(command, *, cwd, env, timeout):
            calls.append(command)
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text(
                json.dumps({
                    "markdown": "# CNN classification of X-ray light curves\n\n"
                    "This paper evaluates 1D CNN and ResNet models for astronomical X-ray light curve classification.",
                    "article": {
                        "metadata": {
                            "title": "CNN classification of X-ray light curves",
                            "abstract": "This paper evaluates 1D CNN and ResNet models for astronomical X-ray light curve classification.",
                            "year": "2025",
                            "doi": "10.1000/cnn",
                        }
                    },
                }),
                encoding="utf-8",
            )
            return {"returncode": 0, "stdout": "", "stderr": ""}

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray source classification", field="machine learning astronomy")
            items = [
                {
                    "title": "CNN classification of X-ray light curves",
                    "authors": ["A. Author"],
                    "year": "2025",
                    "doi": "10.1000/cnn",
                    "abstract": "",
                    "publication": "arXiv",
                    "source": "semantic_scholar",
                    "search_context": "methods",
                    "search_query": "machine learning astronomy 1D CNN ResNet",
                }
            ]

            enriched, manifest = enrich_with_paper_fetch(project.path, items, runner=fake_runner)

            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["attempted_count"], 1)
            self.assertEqual(enriched[0]["abstract"], "This paper evaluates 1D CNN and ResNet models for astronomical X-ray light curve classification.")
            self.assertTrue(enriched[0]["paper_fetch_markdown_path"].endswith(".json"))
            self.assertTrue((project.path / "references" / "paper_fetch_queries.txt").exists())
            self.assertTrue(calls)

    def test_adapter_skips_when_no_runtime_is_available(self) -> None:
        from draftpaper_cli.paper_fetch_adapter import enrich_with_paper_fetch

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="X-ray source classification", field="machine learning astronomy")
            items = [
                {
                    "title": "Weak method candidate",
                    "authors": ["A. Author"],
                    "year": "2025",
                    "abstract": "",
                    "source": "semantic_scholar",
                    "search_context": "methods",
                }
            ]

            enriched, manifest = enrich_with_paper_fetch(project.path, items, command=["missing-paper-fetch-command"])

            self.assertEqual(enriched, items)
            self.assertEqual(manifest["status"], "unavailable")
            self.assertTrue((project.path / "references" / "paper_fetch_manifest.json").exists())

    def test_resolve_uses_packaged_vendored_runtime_when_path_command_is_missing(self) -> None:
        from draftpaper_cli.paper_fetch_adapter import resolve_paper_fetch_command

        with patch("draftpaper_cli.paper_fetch_adapter.shutil.which", return_value=None):
            command, env, runtime_source = resolve_paper_fetch_command()

        self.assertEqual(runtime_source, "vendored")
        self.assertIsNotNone(command)
        self.assertIn("PYTHONPATH", env)
        self.assertIn("_vendor", env["PYTHONPATH"])
        self.assertTrue((Path(env["PYTHONPATH"]) / "paper_fetch" / "cli.py").exists())


if __name__ == "__main__":
    unittest.main()
