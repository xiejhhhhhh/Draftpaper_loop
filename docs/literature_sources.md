# Multi-Source Literature Workflow

Draftpaper-loop treats literature discovery, local library import, metadata resolution, and citation support as separate steps. The project reference registry is the source ledger; `library.bib`, HTML summaries, and `citation_evidence.csv` are derived outputs.

## Source Types

| Source type | Input | Preservation | Automatic citation |
|---|---|---|---|
| `online_search` | OpenAlex, PubMed, Europe PMC, DBLP, NASA ADS, Semantic Scholar, arXiv, Crossref, optional SerpApi | Query, provider status, identifiers, metadata provenance | Only after evidence and citation audit |
| `zotero` | One user-selected Zotero collection | Full curated record, Zotero key, collection, source record | No |
| `local_import` | PDF folder or local BibTeX/RIS/JSON file | File hash, logical locator, parser receipt, field provenance | No |
| `manual` | User-supplied JSON or manually curated record | Import locator and user selection policy | No |

GitHub and Zenodo are separate `code_source` providers rather than citation
origins. After retained, anchor, or user-selected works are written, the
workflow can record metadata-only repository and version-archive leads. These
records retain the paper `work_id`, source URL/DOI, version identity, license,
checksum hints, provider and retrieval time. See
[`research_code_sources.md`](research_code_sources.md).

## Commands

```powershell
python -m draftpaper_cli.cli add-literature-source --project <project> --type local-folder --path <pdf-folder> --context all
python -m draftpaper_cli.cli add-literature-source --project <project> --type structured-file --path <library.bib> --context all
python -m draftpaper_cli.cli list-literature-sources --project <project>
python -m draftpaper_cli.cli collect-literature --project <project>
python -m draftpaper_cli.cli reconcile-literature --project <project>
python -m draftpaper_cli.cli search-literature --project <project> --zotero-collection "My Collection" --include-online
python -m draftpaper_cli.cli review-literature-coverage --project <project>
python -m draftpaper_cli.cli enrich-literature-code-leads --project <project> --selection-mode knowledge_base
```

`search-literature` can aggregate explicit JSON, Zotero, registered local sources, and online providers. Existing tests and offline runs can use `--no-online`; an explicit JSON import does not trigger network search unless `--include-online` is supplied. A missing provider credential or a provider timeout is recorded as degraded and does not erase other sources.

`enrich-literature-code-leads` is metadata-only. It does not clone, download,
extract, install, or execute a repository. `knowledge_base` prefers the latest
stable release and keeps paper-era lineage; `reproduction` requires an exact
paper-linked version. Stars, forks, paper citations, and software citations are
recorded as separate signals, not as scientific validity proofs.

## Local Files

Local files are read in place by default. Absolute paths are not written into public HTML summaries; the registry stores a logical locator and SHA-256 file ID. Attachment copying is intentionally not the default because large PDF libraries should remain outside the paper project. A local record is retained for review, but its presence does not prove that it supports a manuscript claim.

Use `--copy-attachments` only when a self-contained project copy is required. Copies are written below `references/local_attachments/`, addressed by the source hash, and the original logical locator and hash remain in the record. The option does not grant permission to copy a source library into a public repository.

PDF quick reading uses the core `pypdf` path. The core wheel also contains an official MinerU Agent connector, but it is called only after a project-scoped consent, document-class, size, and page-limit check. A user-provided custom endpoint takes precedence over the official route. The legacy `mineru` extra is a no-op compatibility alias; it does not install local models. For a connector-compatible install and a parse run:

```powershell
python -m pip install -e ".[mineru-agent]"
python -m draftpaper_cli.cli parse-literature-document --project <project> --input <paper.pdf>
```

The adapter records the input hash, parser, route, consent decision, parser output, fallback state, cache state, normalized document, bounded evidence passages, and whether the parser was available. `record-remote-parser-consent` stores only a service label and allowed document classes; it never stores API keys or cookies. MinerU is a document parser, not a literature index or reasoning model. Extracted bibliography strings are discovery candidates and require identifier resolution, metadata validation, and citation evidence before they can enter a manuscript citation plan.

The search stage writes `references/literature_confirmation_packet.json` and its Chinese Markdown view. Review that packet once before research-plan confirmation to retain/exclude candidates, assign ambiguous roles, accept literature gaps, and decide whether complex PDFs may be upgraded. `references/document_parse_cost_report.json` records parse routes and downstream context estimates; raw MinerU JSON is not sent to an LLM context by default.

## Coverage Review

`review-literature-coverage` reports coverage by problem/gap, data provenance, method, evaluation standard, baseline, and limitations, together with source counts and provider status. Missing roles are review tasks rather than automatic failure or a reason to fabricate references. The report is a decision aid before research-plan confirmation.
