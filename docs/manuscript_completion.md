# Final Manuscript Completion

Draftpaper-loop keeps final author metadata and precise author edits in one reviewable transaction. The completion workspace does not replace canonical section sources or the Scientific Evidence Registry.

## Workflow

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper manuscript-completion-status --project <project>
draftpaper rollback-manuscript-completion --project <project> --transaction-id <id>
```

`prepare-manuscript-completion` writes a journal-aware template and separates required, recommended, missing, placeholder and not-applicable fields. Fill one `manuscript_completion.yaml` with authors, affiliations, ORCID, funding, acknowledgments, availability statements, links, user-confirmed references and any precise section revisions.

## Stable paragraph location

Each revision must use at least one stable guard:

```yaml
section_revisions:
  - revision_key: methods-robustness-note
    target:
      section: methods
      paragraph_id: methods:p004:1a2b3c4d5e
      expected_sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
      expected_text: The current paragraph text.
      line_start_hint: 118
      line_end_hint: 126
    operation: insert_after
    mode: exact_text
    content: The author-approved addition.
```

Line numbers are display hints. `paragraph_id`, `expected_sha256`, normalized expected text and optional occurrence are the write guards. A stale, ambiguous, overlapping or conflicting target rejects the whole packet.

## Evidence-backed Data and Methods details

If a revision states that a processing, training, or analysis step was executed, add an `evidence_refs` entry from the current project manifests. Preview reads only the fixed local evidence allowlist and reports `suggested_evidence_refs`; copy only the candidate that identifies the same run, cohort, and snapshot.

```yaml
evidence_refs:
  - artifact: methods/run_manifest.yaml
    json_pointer: /steps/feature_construction
    expected_sha256: <sha256 from suggested_evidence_refs>
    run_id: <current run id>
    cohort_id: <current cohort id>
```

Missing, expired, cross-run, cross-cohort, or cross-snapshot refs produce `classification_refinement_required`. Apply repeats the ref validation after preview, so a changed manifest requires a fresh preview.

## Preview and acceptance

Preview creates a unified metadata/section/BibTeX diff, locator report, stale-impact report, candidate LaTeX and candidate PDF. It does not change canonical manuscript sources. `compile_required`, an unresolved Codex instruction or a requested data/method/run/evidence change is non-passing.

Apply requires the exact packet hash shown by preview. It rechecks the project revision, source-map hash, promoted evidence snapshot and every target before hash, then writes the accepted packet atomically. Exact author text becomes a user lock so later writers cannot silently overwrite it. Repeated apply is idempotent.

Rollback is allowed only while all after hashes still match the transaction receipt. Later author edits are never overwritten by rollback.

## Final release ordering

After completion, rebuild and compile `latex/main.pdf`, run the final citation audit, final integrity and quality gates, and two independent blind reviews. `review-final-manuscript` binds the active completion manifest, canonical manuscript, reference registry, evidence snapshot, citation audit, review reports, quality reports and PDF into one release hash.
