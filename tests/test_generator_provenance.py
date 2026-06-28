# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.html_utils import markdown_to_html
from draftpaper_cli.project_scaffold import _write_json


class GeneratorProvenanceTests(unittest.TestCase):
    def test_html_reports_include_generator_metadata(self) -> None:
        html = markdown_to_html("# Report\n\nBody.", title="Report")

        self.assertIn('<meta name="generator" content="Draftpaper-loop">', html)
        self.assertIn('https://github.com/xiejhhhhhh/Draftpaper_loop', html)

    def test_generated_json_reports_include_generator_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"

            _write_json(path, {"generated_at": "2026-06-23T00:00:00Z", "status": "ok"})

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["generated_by"], "Draftpaper-loop")
            self.assertEqual(payload["generator_url"], "https://github.com/xiejhhhhhh/Draftpaper_loop")
            self.assertEqual(payload["generator_contact"], "xiejinhui22@mails.ucas.ac.cn")

    def test_structural_json_without_generated_at_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"

            _write_json(path, {"status": "draft"})

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload, {"status": "draft"})


if __name__ == "__main__":
    unittest.main()
