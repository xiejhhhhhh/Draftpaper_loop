from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.citation_utils import bibtex_keys_in_text, citation_keys_in_text, has_citation_command
from draftpaper_cli.io_utils import read_json, read_text
from draftpaper_cli.latex_utils import safe_latex_text


class CommonUtilsTests(unittest.TestCase):
    def test_read_json_and_text_return_defaults_for_missing_or_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(read_json(root / "missing.json", {"fallback": True}), {"fallback": True})
            (root / "broken.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(read_json(root / "broken.json", []), [])
            (root / "note.txt").write_text("abcdef", encoding="utf-8")
            self.assertEqual(read_text(root / "note.txt", limit=3), "abc")

    def test_latex_escape_is_shared(self) -> None:
        self.assertEqual(safe_latex_text("A&B_50%"), r"A\&B\_50\%")

    def test_citation_and_bibtex_key_parsing(self) -> None:
        text = r"Prior work \citep{Smith2024, Doe2025} and \citet[see][p. 1]{Wang2026}."
        self.assertTrue(has_citation_command(text))
        self.assertEqual(citation_keys_in_text(text), {"Smith2024", "Doe2025", "Wang2026"})
        self.assertEqual(
            bibtex_keys_in_text("@article{Smith2024,\n title={x}}\n@misc{Doe2025, title={y}}"),
            {"Smith2024", "Doe2025"},
        )

    def test_read_json_preserves_non_dict_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "items.json"
            path.write_text(json.dumps([{"id": 1}]), encoding="utf-8")
            self.assertEqual(read_json(path, []), [{"id": 1}])


if __name__ == "__main__":
    unittest.main()
