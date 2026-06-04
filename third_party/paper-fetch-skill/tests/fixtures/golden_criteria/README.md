This directory is the canonical home for extraction rule-test assets and their documentation links.

Conventions:

- DOI-backed samples live under `tests/fixtures/golden_criteria/<doi_slug>/`.
- Minimal non-DOI rule scenarios live under `tests/fixtures/golden_criteria/_scenarios/<scenario_slug>/`.
- The DOI slug uses `/` replaced with `_`.
- Canonical roles use stable names such as `original.html`, `original.xml`, `expected.json`, `abstract.html`, `commentary.html`, `extracted.md`, `markdown-quality-prompt.md`, `markdown-quality.json`, `article.html`, and `table1.html`.
- Rule coverage, sample ownership, and replay support files such as `body_assets/*` are registered in `tests/fixtures/golden_criteria/manifest.json`.

Contract:

- Rule tests should read positive article-content fixtures from this directory, and negative article-content fixtures from `tests/fixtures/block/`, not from scattered top-level files, `live-downloads/`, or `md_for_lc_body/`.
- `docs/extraction-rules.md` links should point here.
- Provider review fixtures keep four generated artifacts side by side: `expected.json` for summary expectations, `extracted.md` as the only human-reviewed golden Markdown baseline, `markdown-quality-prompt.md` for the agent review instructions, and `markdown-quality.json` for the agent-authored pass/fail quality report.
- Samples included in the golden corpus regression keep canonical raw HTML/XML/PDF or `article.html` replay assets plus `expected.json`; fixture-only replay assets may omit `expected.json`.
