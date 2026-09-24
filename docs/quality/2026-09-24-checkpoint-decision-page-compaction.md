# Checkpoint decision-page compaction

## Scope and failure

A core-evidence package passed every readability check except the English
visible-character budget: 20,164 characters against the existing 20,000 limit.
The Chinese page contained 17,784 characters and passed. This was a presentation
failure, not evidence that the scientific result or confirmation state was wrong.

Read-only replay of `render_checkpoint_decision_html` reproduced both counts.
The English change section contained 8,525 characters and the key-facts section
6,565. The former repeated unchanged entries in whole before/after statement
lists; the latter contained eight pairs of facts identical apart from `fact_id`.

## Changes

- `draftpaper_cli/checkpoint_html.py` coalesces a visible fact row only when all
  fields other than `fact_id` match. Labels in both languages, scientific values,
  semantic identity and evidence references must agree. All original IDs remain
  attached to the row through `data-fact-id` and `data-fact-refs`.
- Changes to the Brief's explicitly unordered statement collections are rendered
  as multiset differences. Exact unchanged entries are not repeated. Duplicate
  entries are counted rather than collapsed with a set, so an added or removed
  occurrence remains visible.
- The optimization applies only to the known `semantic_subject` statement
  collections. Unknown lists, including potentially ordered scientific steps,
  keep their full before/after order.
- A changed content identity with otherwise identical display text gets an
  explicit explanation, rather than two indistinguishable values or raw hashes.
- `tests/test_checkpoint_decision_compaction.py` exercises long bilingual pages,
  source/identity distinctions, multiplicity, order, hash-only changes, input
  immutability and rejection of genuinely oversized unique content.

No character limit, scientific fingerprint, Brief contract, evidence gate,
checkpoint schema or user-confirmation policy changes. The canonical JSON and
audit records are not deduplicated or rewritten. This is rendering-only
compaction, not truncation, hidden content or scientific reclassification.

## Read-only package replay

| Locale | Before | After | Readability |
|---|---:|---:|---|
| Chinese | 17,784 | 14,162 | All checks passed |
| English | 20,164 | 16,539 | All checks passed |

The replay wrote only isolated QA previews outside the paper project. The source
package's file hashes and the in-memory summary were unchanged. Fact and
statement coverage, decision question, claim boundaries, semantic changes and
reconfirmation conditions remained present in both languages. This is structural
and content verification, not a new browser visual acceptance or scientific
confirmation.

## Verification

- Red phase: seven targeted cases failed for the expected missing compaction
  behavior; the oversized-unique-content rejection already passed.
- An additional ordered-list regression rejected overly broad compaction; the
  production change was restricted to declared unordered statement collections.
- Focused tests: 11 passed, including the existing human-readable delta regression.
- Ruff and Python compilation passed for the changed code and tests.
- Default project Pyright with the project Python: zero errors and zero warnings.
  An additional check of the whole renderer, outside the default typing scope,
  reports the same 31 pre-existing Optional-value diagnostics on the baseline and
  modified versions. No new diagnostic messages were introduced in that check.
- Final checkpoint/continuity regression: 69 passed in 286.24 seconds, including
  bilingual decision pages, semantic deltas, digests, strict HTML, JSON audit,
  checkpoint scope and confirmation continuity.
- Capability-truth and README/CLI/product-documentation contracts: 21 passed.
- First-party secret scan and `git diff --check` passed. The unrelated full
  repository matrix was not rerun locally; GitHub Actions is not monitored here.

## Loading the fix

1. Update the source checkout or install a build containing this commit. The
   earlier published `v0.43.2` wheel alone does not include the fix.
2. Verify the actual interpreter's import path before running project commands:

   ```powershell
   python -c "from pathlib import Path; import draftpaper_cli.checkpoint_html as h; print(Path(h.__file__).resolve())"
   ```

3. Restart a long-lived Python/MCP process if it has cached the old module. A new
   CLI process imports the updated source. If an alias/junction already points to
   this checkout, no second code copy is necessary.
4. Where the runtime handshake reports a source update, accept it only under the
   project's authorization using `session-preflight --accept-runtime-update`.
   This updates runtime identity, not scientific evidence or author approval.
5. Retry the original `checkpoint --stage core_evidence` after that handshake.
   A failed package may not have been published in the active checkpoint index;
   do not manually patch its JSON, mark it approved, or lower the readability limit.
6. Review the newly generated bilingual readability reports and author pages.
   This fix does not automatically consume or grant a confirmation receipt.

No paper-method rerun, research-plan rewrite, evidence rebinding or project schema
migration is required solely for this presentation fix. Any independently stale
scientific evidence must still follow the existing workflow.
