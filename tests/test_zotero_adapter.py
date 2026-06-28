# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch

from draftpaper_cli.project_scaffold import create_project


class ZoteroAdapterTests(unittest.TestCase):
    def test_fetch_zotero_collection_items_maps_api_records_to_references(self) -> None:
        from draftpaper_cli.zotero_adapter import fetch_zotero_collection_items

        collections = [
            {"key": "ABC123", "data": {"name": "Flaring Sources"}},
        ]
        items = [
            {
                "key": "ITEM1",
                "data": {
                    "itemType": "journalArticle",
                    "title": "Multimodal X-ray flaring source classification",
                    "creators": [{"creatorType": "author", "firstName": "Jane", "lastName": "Smith"}],
                    "abstractNote": "A method for classifying X-ray flaring sources.",
                    "date": "2025",
                    "DOI": "10.1000/zotero.1",
                    "url": "https://example.org/zotero-1",
                    "publicationTitle": "Astrophysical Journal",
                },
            },
            {"key": "ATTACH", "data": {"itemType": "attachment", "title": "PDF"}},
        ]

        def fake_get_json_list(url: str, api_key: str, params=None, limit=None):
            return collections if url.endswith("/collections") else items

        with patch("draftpaper_cli.zotero_adapter._zotero_config", return_value=("12345", "user", "secret")):
            with patch("draftpaper_cli.zotero_adapter._get_json_list", side_effect=fake_get_json_list):
                references, manifest = fetch_zotero_collection_items("flaring", limit=50, context="all")

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["source"], "zotero_collection")
        self.assertEqual(references[0]["search_contexts"], ["idea", "data", "methods"])
        self.assertEqual(references[0]["authors"], ["Jane Smith"])
        self.assertEqual(manifest["matched_collection"], "Flaring Sources")
        self.assertEqual(manifest["usable_item_count"], 1)

    def test_search_literature_imports_zotero_collection_and_writes_manifest(self) -> None:
        from draftpaper_cli.literature_search import search_literature_for_project

        zotero_items = [
            {
                "title": "Curated Zotero reference for AGN classification",
                "authors": ["A. Curator"],
                "year": "2024",
                "doi": "10.1000/zotero.curated",
                "url": "https://example.org/curated",
                "abstract": "Curated reference about AGN classification and validation.",
                "publication": "Astrophysical Journal",
                "citation_count": 0,
                "source": "zotero_collection",
                "reference_origin": "existing_zotero",
                "search_context": "idea",
                "search_contexts": ["idea"],
                "search_query": "Zotero collection: AGN curated",
            }
        ]
        manifest = {
            "status": "loaded",
            "requested_collection": "AGN curated",
            "matched_collection": "AGN curated",
            "collection_key": "XYZ",
            "usable_item_count": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN classification", field="machine learning astronomy")
            with patch("draftpaper_cli.literature_search.fetch_zotero_collection_items", return_value=(zotero_items, manifest)):
                result = search_literature_for_project(
                    project.path,
                    zotero_collection="AGN curated",
                    zotero_context="idea",
                    zotero_supplement=False,
                )

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["zotero_imported_count"], 1)
            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            self.assertEqual(literature_items[0]["source"], "zotero_collection")
            zotero_manifest = json.loads((project.path / "references" / "zotero_collection_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(zotero_manifest["matched_collection"], "AGN curated")
            search_queries = json.loads((project.path / "references" / "search_queries.json").read_text(encoding="utf-8"))
            self.assertEqual(search_queries["zotero_collection"], "AGN curated")
            index_html = (project.path / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
            self.assertIn("zotero_collection", index_html)
            self.assertIn("AGN curated", index_html)

    def test_zotero_references_are_preserved_outside_external_ranking_limits(self) -> None:
        from draftpaper_cli.references import write_reference_outputs

        zotero_items = [
            {
                "title": "User curated Zotero paper without abstract",
                "authors": ["Curated Author"],
                "year": "1998",
                "doi": "10.1000/zotero.keep",
                "publication": "Local Zotero Library",
                "abstract": "",
                "source": "zotero_collection",
                "reference_origin": "existing_zotero",
                "zotero_collection": "My Curated Folder",
                "search_context": "idea",
                "search_query": "Zotero collection: My Curated Folder",
            },
            {
                "title": "Second user curated Zotero paper",
                "authors": ["Second Author"],
                "year": "2001",
                "url": "https://example.org/zotero-second",
                "publication": "Local Zotero Library",
                "abstract": "",
                "source": "zotero_collection",
                "reference_origin": "existing_zotero",
                "zotero_collection": "My Curated Folder",
                "search_context": "methods",
                "search_query": "Zotero collection: My Curated Folder",
            },
        ]
        external_items = [
            {
                "title": f"External ranked paper {index}",
                "authors": [f"External Author {index}"],
                "year": "2024",
                "doi": f"10.1000/external.{index}",
                "abstract": "Relevant external search paper about AGN classification and validation.",
                "publication": "Astrophysical Journal",
                "citation_count": index,
                "source": "semantic_scholar",
                "search_context": "idea",
                "search_query": "AGN classification",
            }
            for index in range(35)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN classification", field="machine learning astronomy")
            result = write_reference_outputs(project.path, [*zotero_items, *external_items], query="AGN classification")

            literature_items = json.loads((project.path / "references" / "literature_items.json").read_text(encoding="utf-8"))
            titles = [item["title"] for item in literature_items]
            self.assertEqual(result["item_count"], 32)
            self.assertIn("User curated Zotero paper without abstract", titles)
            self.assertIn("Second user curated Zotero paper", titles)
            self.assertEqual(sum(1 for item in literature_items if item["source"] == "zotero_collection"), 2)
            self.assertEqual(sum(1 for item in literature_items if item["source"] == "semantic_scholar"), 30)
            index_html = (project.path / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
            self.assertIn("User curated Zotero paper without abstract", index_html)
            self.assertIn("zotero_collection", index_html)
            self.assertIn("semantic_scholar", index_html)

    def test_search_literature_parser_accepts_zotero_collection_options(self) -> None:
        from draftpaper_cli.cli import build_parser

        args = build_parser().parse_args([
            "search-literature",
            "--project",
            "C:\\project",
            "--zotero-collection",
            "Flaring Sources",
            "--zotero-context",
            "all",
            "--no-zotero-supplement",
        ])

        self.assertEqual(args.zotero_collection, "Flaring Sources")
        self.assertEqual(args.zotero_context, "all")
        self.assertTrue(args.no_zotero_supplement)


if __name__ == "__main__":
    unittest.main()
