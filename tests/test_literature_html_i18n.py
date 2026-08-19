from __future__ import annotations

import json

from draftpaper_cli.literature_merge import rebuild_literature_index
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs


def test_core_literature_html_has_offline_bilingual_switch_and_shared_values(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Bilingual literature", field="science").path
    write_reference_outputs(
        project,
        [{
            "title": "A bilingual source",
            "authors": ["A. Author"],
            "year": "2024",
            "doi": "10.1000/bilingual",
            "abstract": "A source with a stable numeric score and local evidence.",
            "publication": "Test Journal",
            "citation_count": 10,
            "source": "openalex",
        }],
        query="Bilingual literature",
    )
    result = rebuild_literature_index(project)
    index = (project / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
    details = [path for path in (project / "references" / "literature_summaries").glob("*.html") if path.name != "index.html"]
    detail = details[0].read_text(encoding="utf-8")

    assert result["status"] == "rebuilt"
    assert "中文" in index and "English" in index
    assert "data-i18n=\"citation_weight\"" in index
    assert "DPL_LOCALES" in index
    assert "localStorage" in index
    assert "中文" in detail and "English" in detail
    assert "10.1000/bilingual" in detail
    assert json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))[0]["work_id"] == "doi:10.1000/bilingual"
