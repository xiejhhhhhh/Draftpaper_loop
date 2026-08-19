# Discipline-aware literature discovery, identity, and full text

Draftpaper-loop separates literature handling into three contracts:

1. discipline-routed providers discover candidates;
2. Core resolves DOI, title, author, and year identity;
3. the vendored paper-fetch adapter retrieves full text only when evidence requires it.

A successful fetch does not grant citation eligibility. Resolved metadata and text pass topic, discipline, and role gates again; only `accepted_active` and `accepted_context_only` enter the active literature snapshot.

## Default flow

```text
Query Contract v3
  -> discipline provider routing
  -> pre-fetch topic/discipline gate
  -> shortlist identity resolution
  -> evidence-on-demand fetch decision
  -> batch or single paper-fetch
  -> post-fetch reassessment
  -> active / review_required / quarantine
  -> hash-bound literature snapshot
```

`general` no longer means a perfect universal match. Insufficient evidence becomes `discipline_unknown`, which requires resolution or review.

## Fetch policy

`search-literature` reads `references/literature_fetch_policy.json` and accepts a one-run override:

```powershell
draftpaper search-literature `
  --project <project> `
  --fetch-policy resolve_then_fetch_on_demand
```

| Mode | Behavior |
|---|---|
| `off` | Disable identity/full-text enrichment while keeping the base relevance gate |
| `resolve_only` | Resolve candidate identity without fetching full text |
| `resolve_then_fetch_on_demand` | Default; resolve first, then fetch only required evidence |
| `fulltext_eager` | Advanced, higher-cost attempt to fetch every eligible candidate |
| `local_only` | Use only local identity and document evidence |

Automatic Core fetches always use `asset_profile=none`; images and supplements are not downloaded. Three or more targets use one batch command. Stable identities are cached by input hash and full text by work ID plus file hash.

## Status and citation eligibility

| Status | Meaning | Automatic writing/citation |
|---|---|---|
| `accepted_active` | Topic, discipline, identity, and evidence pass | Eligible for its declared role |
| `accepted_context_only` | Curated or cross-discipline context | Background/method-transfer context only |
| `review_required` | Borderline relevance, incomplete identity, or degraded provider | Excluded from automatic writing context |
| `rejected_topic_mismatch` | Resolved content misses the topic | Forbidden |
| `rejected_discipline_mismatch` | Resolved content conflicts with the target discipline | Forbidden |
| `rejected_identity_mismatch` | DOI/title/author/year identity conflict | Forbidden |
| `rejected_insufficient_evidence` | Declared full-text evidence is unavailable | Forbidden |

Explicit `method_transfer`, `comparison`, `general_methodology`, and `statistical_method` roles keep legitimate cross-discipline methods reviewable or context-only; they do not bypass scientific gates.

## Main artifacts

```text
references/
├── query_contract.json
├── literature_fetch_policy.json
├── discipline_ontology_snapshot.json
├── discipline_conflict_matrix.json
├── prefetch_relevance_report.json
├── paper_identity_resolutions.jsonl
├── paper_identity_resolution_summary.json
├── fulltext_fetch_decisions.json
├── paper_fetch_manifest.json
├── postfetch_relevance_report.json
├── quarantined_literature_candidates.json
├── literature_snapshot.json
└── literature_summaries/index.html
```

The bilingual HTML views share one active set, identity state, scores, fetch decisions, and snapshot hash. A file merely existing under `references/fulltext/` is not active evidence.

## Integrity and historical orphans

Run the read-only audit first:

```powershell
draftpaper audit-literature-integrity --project <project>
```

Historical orphan quarantine defaults to preview:

```powershell
draftpaper quarantine-orphan-literature --project <project>
```

After inspection, apply the exact packet hash:

```powershell
draftpaper quarantine-orphan-literature `
  --project <project> `
  --apply `
  --packet-hash <sha256:...>
```

Rollback revalidates hashes and refuses to overwrite an existing target:

```powershell
draftpaper rollback-orphan-literature --project <project>
```

Provider, network, or paper-fetch failures become degraded/review states and preserve the previous active snapshot. The workflow does not lower gates to fill a fixed count or delete existing scores and summaries after one failed request.

## Core versus Agent skill

The Core wheel includes a pinned vendored paper-fetch adapter with license and upstream-commit provenance, so ordinary projects do not require an Agent skill installation. The external `paper-fetch-skill` remains useful for interactive single-paper reading, special providers, manual recovery, and human verification. It cannot replace topic discovery, relevance decisions, the active snapshot, or quarantine gates.
