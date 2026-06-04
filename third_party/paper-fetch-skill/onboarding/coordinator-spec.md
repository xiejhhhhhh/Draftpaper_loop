# Coordinator Spec

本文定义 S14 coordinator 的机器可验证编排规则。

## Invocation

`/onboard <name>` 对应的本地入口是：

```bash
python3 scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run --output-dir <dir>
python3 scripts/onboard_from_manifests.py start --manifest onboarding/manifests/<name>.yml --dry-run --output-dir <dir>
python3 scripts/onboard_from_manifests.py run --provider <name> --domain <domain> --output-dir <dir>
python3 scripts/onboard_from_manifests.py run --manifest onboarding/manifests/<name>.yml --until merge-ready
python3 scripts/onboard_from_manifests.py diagnose --state onboarding/onboarding-state.json
python3 scripts/onboard_from_manifests.py resume-blocked --provider <name> --dry-run
python3 scripts/onboard_from_manifests.py resume-blocked --provider <name> --until provider-local-acceptance
python3 scripts/onboard_from_manifests.py summarize --provider <name> --format markdown --output <path>
python3 scripts/onboard_from_manifests.py next --provider <name>
python3 scripts/onboard_from_manifests.py verify --provider <name> --task <task-id>
python3 scripts/onboard_from_manifests.py run-checks --provider <name> --task <task-id>
python3 scripts/onboard_from_manifests.py run-checks --provider <name> --all-local
python3 scripts/onboard_from_manifests.py repair-markdown-quality --provider <name> --doi <doi>
python3 scripts/onboard_from_manifests.py advance --provider <name> --task <task-id>
```

Worker dispatch defaults to the local Codex CLI: `codex exec --cd <repo-root> --sandbox workspace-write -c approval_policy="never" -`. `PROVIDER_ONBOARDING_AGENT_CLI` records an operator-selected override when set. `start` only writes task DAG, task brief, verification plan, and coordinator state. `run` may call the resolved local CLI through subprocess with prompt stdin, but must not call an LLM SDK or vendor client.

## Runtime

- Coordinator is one long-running coding agent CLI session.
- Worker is one child agent task with isolated context and no commit right.
- Worker dispatch uses the resolved coding agent CLI; `run` uses local `codex exec` by default, or `PROVIDER_ONBOARDING_AGENT_CLI` when the operator sets it, and stores prompt/stdout/stderr logs under `<output-dir>/workers/`.
- The script must not call any LLM SDK or vendor client.
- The script must not run a GitHub Actions matrix.
- Provider onboarding is serial across providers.
- Task execution is serial inside one provider.
- One coordinator state file may contain at most one provider with `status: in_progress`.
- Worker output remains in the workspace; coordinator owns verification, shared-file updates, and commit preparation.
- Markdown quality fresh review and repair use the same resolved dispatcher; fresh review logs are written under `.paper-fetch-runs/<provider>-markdown-quality-audit/<doi-slug>/attempt-N/`, and repair prompts/stdout/stderr/changed-path snapshots/briefs/command logs are written under `<output-dir>/markdown-quality/<doi-slug>/attempt-N/`.

## Task DAG

The provider DAG is ordered:

1. `operator-access-preflight`
2. `discover-manifest`
3. `validate-manifest`
4. `capture-fixtures`
5. `propose-cleaning-chain`
6. `scaffold`
7. `implement-provider`
8. `shared-integration`
9. `snapshot-expected`
10. `manifest-sync-back`
11. `provider-local-acceptance`
12. `global-lint`
13. `merge-ready`

`operator-access-preflight` validates `onboarding/access-reviews/<provider>.yml` against `onboarding/access-review.schema.json`. Required operator decisions are legal access mode, allowed runtime, forbidden behaviors, CAPTCHA/challenge policy, temporary site policy, and `may_continue: true`. Missing, blocked, or schema-invalid access review prevents discovery worker dispatch.

`start --provider` includes all 13 tasks and writes `briefs/discover-manifest.yml` plus `briefs/implement-provider.yml`.

`start --manifest` skips `discover-manifest`, reads the provider name from the manifest YAML, and writes `briefs/implement-provider.yml`; it does not skip `operator-access-preflight`.

## Task Ownership

- `operator-access-preflight`: operator writes and approves `onboarding/access-reviews/<provider>.yml`; coordinator validates it before discovery.
- `discover-manifest`: coordinator dispatches discovery worker with the access review as constraints only.
- `validate-manifest`: coordinator validates schema, known-provider conflict, draft state, and DOI sample evidence.
- `capture-fixtures`: coordinator runs `scripts/capture_fixture.py --from-manifest <manifest> --all --auto-via --fail-fast`.
- `propose-cleaning-chain`: coordinator runs `scripts/propose_cleaning_chain.py --provider <provider> --write`, producing compact `onboarding/cleaning-chain-proposals/<provider>.yml` and full evidence `<provider>.evidence.yml`. This task dispatches no worker and must use only committed fixture evidence.
- `scaffold`: coordinator runs `scripts/scaffold_provider.py --from-manifest --merge-existing=safe`; existing outputs are reused when safe, otherwise produce a merge plan JSON instead of deleting user work.
- `implement-provider`: coordinator dispatches implementation worker with access review constraints.
- `shared-integration`: coordinator integrates shared surfaces after provider-owned implementation, including `provider_catalog`, MCP status/instructions/schema, golden/live review, benchmark samples, shared renderer/workflow gaps, shared docs, and changelog entries. Each shared edit must trace to manifest facts, bundle sync-back, fixture replay, or provider-local test evidence.
- `snapshot-expected`: coordinator enumerates every non-null manifest DOI sample and `extra_fixtures[].doi`, runs `scripts/snapshot_expected.py --doi <doi> --review`, runs `scripts/snapshot_expected.py --doi <doi>`, checks fixture directory, `expected.json`, `extracted.md`, `markdown-quality-prompt.md`, agent-authored `markdown-quality.json` pass status, non-pending `expected_outcome`, and dispatches a fresh Markdown quality review that rereads current `extracted.md`.
- `manifest-sync-back`: coordinator runs `scripts/manifest_sync_back.py --sync-docs`.
- `provider-local-acceptance`: coordinator first checks compact proposal fixture digest freshness, then runs `scripts/propose_cleaning_chain.py --provider <provider> --check-contract`, provider-local pytest, review artifact validation, hard-constraint grep, and one provider subset live assets review for future providers by default. Existing legacy non-risk providers may be exempt.
- `global-lint`: coordinator runs manifest sync, owner reuse, bundle completeness, import boundary, and docs validation checks.
- `merge-ready`: coordinator updates manifest readiness, known provider index, shared docs, and PR summary.

## State Machine

State file path defaults to `onboarding/onboarding-state.json`. The schema is `onboarding/onboarding-state.schema.json`.

Provider status values:

- `in_progress`
- `blocked`
- `merge_ready`
- `completed`

Task status values:

- `pending`
- `in_progress`
- `completed`
- `failed`
- `blocked`

Rules:

- `next` initializes missing provider state and marks the first pending task `in_progress`.
- `verify` writes a dry-run verification plan under `verifications.<task-id>` and does not modify provider code or docs.
- `run-checks --task` executes the same local command plan for one task and records result details under `runs.<task-id>`.
- `run-checks --all-local` runs access review, manifest, review/provider-local acceptance, shared integration, and global lint gates without triggering GitHub CI or the live review command.
- `verify --task operator-access-preflight` and `verify --task discover-manifest` require an approved access review.
- `advance` marks the requested task `completed` and moves exactly one next task to `in_progress`.
- `advance --task operator-access-preflight` validates access review approval before moving to `discover-manifest`.
- Completing the final task clears `active_provider` and sets provider status to `merge_ready`.
- A second provider cannot become `in_progress` while another provider is active.
- Retry counters are stored per task.
- `run --until <task>` executes the same DAG inclusively through `<task>` and leaves the next task in state for continuation.
- `repair-markdown-quality` accepts registered DOI fixtures after running a fresh Markdown quality review. A fresh blocking issue can trigger repair even when the persistent `markdown-quality.json` says pass; if the fresh review passes but the persistent report is pending/fail, repair refreshes the persistent report path through the quality-review worker. Each attempt writes `repairs.markdown_quality[]` summary entries with provider, DOI, attempts, issue IDs, changed paths, verification commands, quality status, and run directory.
- `diagnose` reads state only and emits stable JSON containing provider status, current step, latest failure code, retryable flag, failure-recovery action, access review state, and whether operator action is required.
- `resume-blocked --dry-run` reads state only and emits the next task plus blockers. Non dry-run only resumes one provider when the latest failure is retryable, access review is approved, and no operator-only blocker remains.
- `summarize` reads state plus manifest/access/review artifacts and renders JSON or Markdown without fabricating pass results for commands that are not recorded in state.

## Retry

- Worker retry limit is 3.
- `WORKER_MODIFIED_FORBIDDEN_FILE` requires coordinator to discard or revert forbidden-path changes before retry.
- `UNSUITABLE_DOI_SAMPLE` from fixture capture routes back to `discover-manifest` and only replaces the failed `fixtures.doi_samples.<purpose>` object.
- `resume-blocked` does not auto-resume `UNSUITABLE_DOI_SAMPLE`, `WORKER_MODIFIED_FORBIDDEN_FILE`, `BROWSER_RUNTIME_REQUIRED`, access review failures, challenge/CAPTCHA, or retry exhaustion; these require operator/coordinator action first.
- Provider-local acceptance failure routes back to `implement-provider`.
- `MARKDOWN_CONTRACT_DRIFT` is retryable. Digest-stale details name `propose-cleaning-chain` as the immediate refresh task; contract drift routes resume planning back to `implement-provider`.
- `MARKDOWN_QUALITY_REPAIR_FAILED` means all Markdown quality repair attempts completed but the fresh review, persistent quality review, or check-snapshot did not pass.
- Retry count 3 sets provider status to `blocked` and stops the pipeline.

## Worker Isolation

Worker brief must include:

- `files_allowed_to_modify`
- `files_must_not_modify`
- `no_commit: true`

Shared files are coordinator-only at `shared-integration` or `merge-ready`:

- `onboarding/known-providers.yml`
- `docs/providers.md`
- `docs/extraction-rules.md`
- `CHANGELOG.md`

Forbidden central provider logic files for implementation worker:

- `src/paper_fetch/provider_catalog.py`
- `src/paper_fetch/extraction/html/provider_rules.py`
- `src/paper_fetch/quality/html_signals.py`
- `src/paper_fetch/quality/html_availability.py`

## Worker Prompt Input

Discovery worker prompt must inline:

- discovery brief YAML
- approved access review YAML
- `onboarding/provider-manifest.schema.json`
- `onboarding/hard-constraints.md`

Implementation worker prompt must inline:

- implementation brief YAML
- approved access review YAML
- `onboarding/hard-constraints.md`
- current provider manifest YAML
- compact cleaning proposal YAML from `onboarding/cleaning-chain-proposals/<provider>.yml`; the full `.evidence.yml` remains a coordinator/operator artifact and is not inlined.

Worker must not read README, audit documents, or chat history as provider behavior input.

`run` checks git changed paths before and after each worker attempt. A new changed path matching `files_must_not_modify` fails the task with `WORKER_MODIFIED_FORBIDDEN_FILE`.
