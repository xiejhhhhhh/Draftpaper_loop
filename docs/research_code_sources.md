# Research-Code Sources

Draftpaper-loop can enrich retained literature with metadata-only GitHub and
Zenodo code leads. This is a discovery and provenance layer, not automatic
code execution or scientific validation.

## Commands

```powershell
draftpaper enrich-literature-code-leads --project <project> --selection-mode knowledge_base
draftpaper discover-research-code --output-root <output> --discipline <discipline> --query "<query>"
draftpaper inspect-research-code-source --project <project> --candidate-id <id>
draftpaper fetch-research-code-archive --project <project> --candidate-id <id> --confirm-download
```

The enrichment command reads only retained, anchor, and user-selected works by
default. It writes `references/code_sources.json`, provenance and candidate
JSON, a source index, and a quality report. It does not clone, download,
extract, install, or execute third-party code. Public provider API calls require
the explicit `--include-online`/`--enrich-code-sources-online` option.

## Version intent

- `knowledge_base`: latest stable release is the default candidate; paper-era
  versions remain lineage records.
- `plugin_candidate`: latest compatible fixed version must pass license,
  archive, environment, and fixture checks before promotion.
- `reproduction`: the exact paper-linked release/commit is required; the latest
  version cannot substitute for an unavailable historical version.
- `historical_reference`: provenance only and never the default execution path.
- `citation_only`: metadata and links only.

“Latest” means the latest observed accessible candidate, not a claim that the
implementation is complete, optimized, or scientifically correct.

## Quality and safety

GitHub stars/forks, paper citations, software citations, Zenodo downloads,
release history, task fit, reproducibility, and maintenance are recorded as
separate signals with provider and retrieval time. Stars/forks receive an
age-adjusted per-year/log-scale auxiliary normalization when repository age is
known; paper/software citations receive the same auxiliary treatment when
publication years are known. Missing exposure time is marked as unadjusted
rather than guessed. No signal can override task relevance, license, checksum,
archive safety, or human promotion.

Only an explicitly confirmed archive download can enter the content-addressed
quarantine. ZIP Slip, absolute paths, traversal, symlinks, device files,
compression bombs, checksum mismatch, and license conflicts are rejected.
Archive code is never executed by the fetch command.
