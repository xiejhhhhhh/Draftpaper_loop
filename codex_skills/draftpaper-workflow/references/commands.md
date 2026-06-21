# Draftpaper-loop Commands

Run commands from the active Draftpaper-loop repository unless the package is installed into the active Python environment.

## Project

```powershell
python -m draftpaper_cli.cli create-project --root <repo>\projects --idea "..." --field "..." --target-journal "General Academic Journal"
python -m draftpaper_cli.cli load-project --project <repo>\projects\my_project
python -m draftpaper_cli.cli validate-project --project <repo>\projects\my_project
python -m draftpaper_cli.cli status --project <repo>\projects\my_project
python -m draftpaper_cli.cli run-pipeline --project <repo>\projects\my_project
python -m draftpaper_cli.cli detect-artifact-drift --project <repo>\projects\my_project
python -m draftpaper_cli.cli sync-artifact-stale --project <repo>\projects\my_project
python -m draftpaper_cli.cli checkpoint --project <repo>\projects\my_project --stage research_plan --note "User approved the research plan"
python -m draftpaper_cli.cli resume --project <repo>\projects\my_project --checkpoint-hash abc123def456
python -m draftpaper_cli.cli mark-stage-stale --project <repo>\projects\my_project --stage references
python -m draftpaper_cli.cli update-stage-status --project <repo>\projects\my_project --stage data --status draft
```

`status` and `run-pipeline` are the orchestrator layer. They inspect `project.json`, stage manifests, `project_passport.yaml`, and append-only ledgers to report the next safe action. If `status` returns `pipeline_state=drift_detected`, run `sync-artifact-stale` before any downstream stage. If integrity or final quality reports failed at the final gate, the next action becomes `diagnose-gate-failures`. `detect-artifact-drift` is read-only; `sync-artifact-stale` maps hash drift to downstream stale stages, writes an integrity ledger event, and refreshes the passport baseline. `checkpoint` records an explicit human confirmation boundary in `checkpoint_ledger.jsonl`; `resume` consumes it by appending a resume event, never by deleting or rewriting the checkpoint.

## Literature and Plan

```powershell
python -m draftpaper_cli.cli search-literature --project <repo>\projects\my_project --query "topic keywords"
python -m draftpaper_cli.cli search-literature --project <repo>\projects\my_project --from-json C:\path\literature_items.json
python -m draftpaper_cli.cli list-zotero-collections
python -m draftpaper_cli.cli search-literature --project <repo>\projects\my_project --zotero-collection "My Paper References" --zotero-context all --zotero-min-items 20
python -m draftpaper_cli.cli resolve-journal-template --project <repo>\projects\my_project --target-journal APJS
python -m draftpaper_cli.cli resolve-journal-template --project <repo>\projects\my_project --overleaf-url "https://www.overleaf.com/latex/templates/..."
python -m draftpaper_cli.cli resolve-journal-template --project <repo>\projects\my_project --guideline-url "https://journal.example/author-guidelines"
python -m draftpaper_cli.cli generate-plan --project <repo>\projects\my_project
python -m draftpaper_cli.cli generate-plan --project <repo>\projects\my_project --allow-high-similarity
```

`search-literature` builds separate `idea`, `data`, and `methods` search queries, writes them to `references/search_queries.json`, and tags each retained paper with `search_context` and `search_query`. Data and methods use three to five precise queries crossed with the discipline/field name, not necessarily the full research direction or target journal. Methods queries should preserve user-provided method phrases such as `1D CNN / ResNet`, `Transformer`, `Temporal Convolutional Network`, multimodal networks, and contrastive/self-supervised learning instead of collapsing them into one broad keyword string. Each data/methods query fetches only one to two top records, then the context is ranked separately by query relevance, citation authority, and journal authority before the final set is assembled.

The command writes `references/literature_summaries/index.html` plus one HTML summary per retained paper. Each summary records the search context, search query, recommended manuscript section, ranking scores, metadata, and structured reading notes. The ranking fields in `references/literature_items.json` are `relevance_score`, `authority_score`, `citation_authority_score`, `journal_score`, and `citation_weight`; high `citation_weight` papers should be preferred by the matching writing stage.

`citation_evidence.csv` maps context to manuscript section: idea -> introduction, data -> data, methods -> methods. If later Data or Methods drafts do not cite any evidence keys from their matching context, `quality-check` reports a context-reference warning. Literature candidates without abstracts are first sent through DraftPaper's project-level `paper_fetch_adapter` when data/methods usable evidence is below five. The adapter writes `references/paper_fetch_queries.txt`, `references/paper_fetch_manifest.json`, and fetched files under `references/fulltext/`. If paper-fetch cannot recover readable evidence, keep the usable data/methods references that exist and let idea-context papers fill the remaining reference budget.

`generate-plan` also writes target-journal anchor papers and a novelty-overlap report. If it returns `blocked_high_similarity`, stop and ask the user whether to continue, revise, or abandon the current framing before rerunning with `--allow-high-similarity`.

## Writing Stages

```powershell
python -m draftpaper_cli.cli write-introduction --project <repo>\projects\my_project
python -m draftpaper_cli.cli inventory-data --project <repo>\projects\my_project
python -m draftpaper_cli.cli assess-data-quality --project <repo>\projects\my_project --required-column id --required-column target
python -m draftpaper_cli.cli assess-data-feasibility --project <repo>\projects\my_project --min-rows 30
python -m draftpaper_cli.cli collect-method-plan --project <repo>\projects\my_project --method-note "Use a multimodal classifier" --primary-metric f1 --minimum-primary-metric 0.75
python -m draftpaper_cli.cli plan-figures --project <repo>\projects\my_project
python -m draftpaper_cli.cli generate-analysis-code --project <repo>\projects\my_project
python -m draftpaper_cli.cli verify-methods --project <repo>\projects\my_project --command "python code/scripts/run_analysis.py" --output results/tables/metrics.csv --output results/tables/analysis_summary.csv --output results/figure_metadata.json --output results/figure_quality_report.json --output <figure-path-from-results-figure_plan-json>
python -m draftpaper_cli.cli write-methods --project <repo>\projects\my_project
python -m draftpaper_cli.cli assess-result-validity --project <repo>\projects\my_project
python -m draftpaper_cli.cli inventory-results --project <repo>\projects\my_project
python -m draftpaper_cli.cli write-results --project <repo>\projects\my_project
python -m draftpaper_cli.cli write-discussion --project <repo>\projects\my_project
```

`generate-analysis-code` writes a project-local plotting runtime to `code/src/scientific_plotting.py`. Generated empirical figures should produce `results/figure_metadata.json` and `results/figure_quality_report.json`; pass those files to `verify-methods` as declared outputs. `inventory-results` uses the metadata to turn real plot statistics into result claims. If a planned generated figure cannot produce metadata or falls back to a placeholder/workflow diagram, rerun from `plan-figures` or revise the data/method plan instead of writing Results.

## Assembly and Review

```powershell
python -m draftpaper_cli.cli assemble-latex --project <repo>\projects\my_project
python -m draftpaper_cli.cli assemble-latex --project <repo>\projects\my_project --compile-pdf
python -m draftpaper_cli.cli compile-latex-pdf --project <repo>\projects\my_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\my_project
python -m draftpaper_cli.cli quality-check --project <repo>\projects\my_project
python -m draftpaper_cli.cli diagnose-gate-failures --project <repo>\projects\my_project
python -m draftpaper_cli.cli review-draft --project <repo>\projects\my_project
python -m draftpaper_cli.cli assess-publication-readiness --project <repo>\projects\my_project
python -m draftpaper_cli.cli recommend-statistical-revision --project <repo>\projects\my_project
python -m draftpaper_cli.cli generate-revision-plan --project <repo>\projects\my_project
python -m draftpaper_cli.cli apply-revision --project <repo>\projects\my_project
python -m draftpaper_cli.cli re-review --project <repo>\projects\my_project
```

`run-integrity-gate` returns exit code `0` for passed and `1` for failed. It writes `integrity/integrity_report.json`, `integrity/integrity_report.md`, and appends an `integrity_gate` event to `integrity_ledger.jsonl`. Run it before `quality-check` to catch missing BibTeX keys, missing citation evidence, Results citations, missing result artifacts, and unbound result claims.

`quality-check` returns exit code `0` for passed and `1` for failed. It still writes `quality_checks/quality_report.json` on failure.

`diagnose-gate-failures` writes `review/gate_failure_diagnosis.json` and `.md`. `review-draft` writes `review/review_report.md` and `review/reviewer_issues.json`. `assess-publication-readiness` writes `review/publication_readiness_report.json`, `review/publication_readiness_report.html`, `review/journal_fit_report.html`, and `review/claim_evidence_matrix.csv`. `recommend-statistical-revision` writes `review/statistical_rescue_plan.json` and `.html`, then updates the claim-evidence matrix. `generate-revision-plan` merges gate, reviewer, publication-readiness, and statistical-rescue issues into `review/revision_plan.json`, `review/revision_plan.md`, and `review/commitment_ledger.csv`. `apply-revision` marks affected stages stale but does not rewrite scientific content. `re-review` reruns diagnosis, review, readiness, statistical rescue, and planning and writes `review/re_review_report.md`.
