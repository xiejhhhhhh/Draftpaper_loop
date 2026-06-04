# Manifest Discovery

`discover-manifest` 是 AI onboarding 的第一个 worker step。它必须等 `operator-access-preflight` 通过后运行，把 provider 种子转换成带证据的 `ProviderManifest`，供后续 `validate-manifest`、`capture-fixtures`、`propose-cleaning-chain`、`scaffold` 和 `implement-provider` 使用。Coordinator DAG 和状态机规则见 `onboarding/coordinator-spec.md`。

## Worker Input

Coordinator 给 discovery worker 的输入必须是 task brief，不是自然语言 onboarding 文档：

```yaml
task_id: mdpi-discover-manifest
current_step: discover-manifest
runtime: coding-agent-subagent
provider_seed:
  name: mdpi
  domain: mdpi.com
  doi_prefix_hint: null
output_manifest: onboarding/manifests/mdpi.yml
evidence_pack:
  path: .paper-fetch-runs/mdpi-onboarding/discovery/evidence-pack.json
  producer: prepare-discovery
  required_before_worker: true
  worker_should_use_as_evidence_not_manifest_source: true
contract_templates:
  route_contract: ...
  markdown_contract: ...
  asset_contract: ...
autofix_policy:
  coordinator_runs_before_validate: true
  low_confidence_candidates: record proof and rejection reasons only
access_review: onboarding/access-reviews/mdpi.yml
access_policy_constraints:
  source: onboarding/access-reviews/mdpi.yml
  operator_gate: operator-access-preflight
  worker_must_not_infer_access_policy: true
  discovery_may_only_use_review_as_constraints: true
schema: onboarding/provider-manifest.schema.json
hard_constraints: onboarding/hard-constraints.md
search_requirements:
  routing:
    - doi_prefixes
    - domains
    - domain_suffixes
    - crossref_publisher
  doi_sample_purposes:
    - structure
    - table
    - formula
    - figure
    - supplementary
    - references
    - pdf_fallback
    - abstract_only
    - access_gate
    - empty_shell
  mandatory_discovery_proof:
    purposes:
      - table
      - formula
      - supplementary
    minimum_queries_per_purpose: 3
    query_must_include:
      - provider name, provider domain, or DOI prefix
      - purpose keyword
    candidate_pool_required: true
    worker_must_search_beyond_seed_doi: true
    record_rejections_by_doi: true
    selected_doi_must_match_doi_samples: true
files_allowed_to_modify:
  - onboarding/manifests/mdpi.yml
files_must_not_modify:
  - src/
  - tests/
  - docs/providers.md
  - CHANGELOG.md
no_commit: true
```

Discovery worker 只能写 `output_manifest`。它不能写代码、fixture、tests、shared docs，也不能 commit。它只能把 access review 当作 operator 约束输入，不能自行推断自动登录、CAPTCHA 处理、challenge/paywall 绕过或临时站点策略可行。

## Coordinator Evidence Pack

`run --provider ...` 在派发 `discover-manifest` worker 之前会自动执行：

```bash
python3 scripts/onboard_from_manifests.py prepare-discovery \
  --provider <provider> \
  --domain <domain> \
  --doi-prefix <doi-prefix> \
  --output-dir .paper-fetch-runs/<provider>-onboarding \
  --browser-fallback auto
```

输出固定写入 `<output-dir>/discovery/evidence-pack.json`。需要离线或单测时加 `--no-network`，此时只写 routing seed 和 query plan，不访问 Crossref、OpenAlex、publisher 页面或 browser runtime。`--browser-fallback off` 可显式禁用 browser fallback；默认 `auto`。

Evidence pack 包含：

- routing seed evidence、provider/domain/DOI prefix identity terms。
- 每个 fixture purpose 的 query plan。
- Crossref/OpenAlex DOI metadata candidates。传入 `--doi-prefix` 时，Crossref 查询会带 `filter=prefix:<prefix>`，候选合并后还会按 DOI prefix、provider identity 和 domain seed 过滤，避免把其他 publisher 的 DOI 混入 fixture discovery。
- publisher landing page 的轻量探测信号：table、formula、figure、supplementary、references、PDF、access gate、empty shell 等。页面探测是 HTTP-first；当 HTTP request failed、401/402/403/429、challenge、empty shell，或没有当前 purpose 需要的正文/table/formula/supplementary/reference 等信号时，且 access review 允许 `browser`/`playwright`，才会按候选执行一次 browser fallback。
- 每个 candidate 的 `score`、`confidence`、`observed_signals`、`evidence_url` 和 rejection hint。全文类 purpose 的未探测候选、challenge/access/empty-shell probe 结果不能升为 high confidence；它们只能作为 rejected candidate evidence，而不能作为可收录 fixture。
- 每个 probed candidate 的路线证据：`probe.route`、`probe.browser_attempted`、`probe.fallback_from`、`probe.http_probe`、可选 `probe.browser_probe` 和 `probe.browser_failure_code`。browser 成功提取的 `body_tables`、`formula`、`figures`、`supplementary`、`references` 等信号会参与评分和 purpose 覆盖判断。

Browser fallback 只复用项目已有 browser workflow 抓取能力，不登录、不解 CAPTCHA、不绕过 paywall/challenge。若 browser 仍返回 challenge、access gate、空壳或 runtime failure，discovery 只记录失败证据，不把它当作成功全文样本；后续 fixture 写入仍由 `capture-fixtures --auto-via` 和 `scripts/capture_fixture.py` 负责。

Worker 仍是 manifest 作者。Coordinator 只把 evidence pack 摘要放进 worker prompt，并提供 contract/proof 模板，禁止把初稿完全替换成确定性脚本生成。

机器可判规则：

- `task_id` must equal `<provider>-discover-manifest`.
- `current_step` must equal `discover-manifest`.
- `runtime` must equal `coding-agent-subagent`.
- `access_review` must point to `onboarding/access-reviews/<provider>.yml`.
- `access_policy_constraints.worker_must_not_infer_access_policy` must be `true`.
- `files_allowed_to_modify` must contain exactly one path, equal to `output_manifest`.
- `files_must_not_modify` must contain `src/`, `tests/`, `docs/providers.md`, and `CHANGELOG.md`.
- `no_commit` must be `true`.
- `evidence_pack.producer` must be `prepare-discovery`.
- `autofix_policy.coordinator_runs_before_validate` must be `true`.

## Search Evidence Requirements

Discovery worker 必须为这些字段找公开证据：

- `routing.doi_prefixes`
- `routing.domains`
- `routing.domain_suffixes`
- `routing.crossref_publisher`
- `main_path`
- `route_contract`
- `markdown_contract`
- `asset_profile`
- `supplementary_scope`
- `abstract_only_strategy`
- `probe`
- `fixtures.doi_samples`

可用证据包括 publisher article pages、DOI landing pages、Crossref/OpenAlex 结果、公开 PDF/HTML 链接和页面中可观察到的 DOM/text signal。

每个 evidence 必须满足：

- `evidence_url` is an HTTP(S) URL or a stable DOI landing URL.
- `evidence_reason` explains which observed signal supports the manifest field.
- `observed_signals` is a non-empty list for every DOI sample with a DOI.
- Crossref/OpenAlex evidence must identify the publisher or DOI prefix it supports.
- Publisher article page evidence must identify whether it supports HTML structure, assets, supplementary material, references, gated access, abstract-only behavior, or PDF fallback.
- Search notes must be represented in manifest fields; do not write separate scratch files.

## Mandatory Discovery Proof

`fixtures.discovery_proof` 是 `table`、`formula`、`supplementary` 的强制候选池证明，也可用于 `abstract_only`、`access_gate`、`empty_shell` 等 optional null purpose 的 exhausted proof signoff。它不是叙述性备注；`validate-manifest` 会机器校验强制 purpose，schema 会校验所有记录的 proof entry。

每个 purpose 必须包含：

- `queries`: 实际搜索 query，至少 3 条。每条 query 必须包含 provider 名称、域名或 DOI prefix，并包含该 purpose 的关键词。
- `candidates`: 候选 DOI 列表。选择了 DOI 时必须包含 `selected_doi`；null purpose 也必须记录至少一个被拒候选，除非 schema 后续明确扩展无候选证明格式。
- `selected_doi`: 必须与 `fixtures.doi_samples.<purpose>.doi` 完全一致；sample 为 `doi: null` 时这里也必须是 `null`。
- `rejections`: 所有未选择候选 DOI 的拒绝原因，key 为 DOI。
- `exhausted`: 只有没有可用候选时为 `true`；已选择 DOI 时必须为 `false`。
- `evidence_summary`: 简短说明为什么当前选择或 null 结论成立。

`doi: null` 的 `table`、`formula`、`supplementary` 必须有 `exhausted: true`、至少 3 条 query、候选拒绝理由，且 `evidence_reason` / `evidence_summary` 不能只写“未找到样本”。Optional null purpose 若写入 `fixtures.discovery_proof`，也必须遵循同一 exhausted proof 结构。如果同一 manifest 的 non-null fixture 或 cleaning evidence 暴露了该 purpose 的强信号，worker 必须选择该 DOI，或在 `rejections` 中用同 DOI 明确说明为什么它不适合作为该 purpose fixture。

## DOI Sample Evidence

`fixtures.doi_samples` 的每个 purpose 必须是对象：

```yaml
structure:
  doi: "10.3390/membranes15030093"
  evidence_url: "https://www.mdpi.com/..."
  evidence_reason: "Landing page exposes a normal article body with headings and figures."
  observed_signals: ["html_body", "figures", "references"]
  confidence: high
```

固定 purpose 集合：

- `structure`
- `table`
- `formula`
- `figure`
- `supplementary`
- `references`
- `pdf_fallback`
- `abstract_only`
- `access_gate`
- `empty_shell`

`pdf_fallback` 样本选择必须先证明该 DOI 能稳定覆盖真实 PDF fallback：公开证据能定位 PDF 链接或 PDF payload，后续 capture 能拿到真实 PDF bytes，且不是 HTML wrapper、challenge page、access page 或错误页。多个候选都满足这些条件且证据强度接近时，可以把 legacy/archive 覆盖作为 tie-breaker，优先考虑 2000 年以前或 publisher 早期数字化文章；但不能为了年份偏好选择 OCR / 扫描文本质量差、docserver 不稳定、访问策略不确定，或不代表该 provider fallback 行为的样本。若选择这类老文章，`evidence_reason` 应说明其 legacy PDF route 价值。

`structure`、`figure`、`references` 在 draft 状态也必须有 DOI。其他 purpose 找不到样本时允许 `doi: null`，但 `evidence_reason` 必须说明搜索失败原因。
`table`、`formula`、`supplementary` 即使为 null，也必须通过 `fixtures.discovery_proof` 证明搜索充分。

## Output Schema

Discovery worker 必须写一个 `ProviderManifest` YAML 到 `output_manifest`，并且必须通过 `onboarding/provider-manifest.schema.json`。

输出必须满足：

- No `TODO`, `TBD`, or `unknown` placeholder values.
- `routing.doi_prefixes`, `routing.domains`, `routing.domain_suffixes`, and `routing.crossref_publisher` are evidence-backed.
- `fixtures.doi_samples` contains all fixed purpose keys listed above.
- `fixtures.discovery_proof` contains `table`, `formula`, and `supplementary`; optional null purposes may also appear with exhausted proof.
- `route_contract` contains every `main_path` step and describes success/rejection signals.
- `markdown_contract` contains every non-null DOI sample purpose and gives positive/negative Markdown assertions.
- Each sample object contains `doi`, `evidence_url`, `evidence_reason`, `observed_signals`, and `confidence`.
- `confidence` values are only `high`, `medium`, or `low`.
- `doi: null` for `table`, `formula`, or `supplementary` is allowed only when `discovery_proof` proves an exhausted candidate search and does not contradict local fixture or cleaning evidence.
- `structure`, `figure`, and `references` must not use `doi: null` while the manifest is draft.

## Generation Metadata

Discovery worker 必须写 `generation`：

```yaml
generation:
  generated_by: ai_discovery
  generated_at: "2026-05-14T00:00:00Z"
  source_queries:
    - "MDPI DOI prefix articles supplementary materials"
  confidence: high
```

`source_queries` 记录实际搜索 query，并且必须覆盖 `fixtures.discovery_proof.*.queries`。`confidence` 只能是 `high`、`medium`、`low`。

## Retry Rules

Discovery 阶段只使用结构化错误：

- `MANIFEST_DISCOVERY_FAILED`
- `MANIFEST_SCHEMA_INVALID`
- `MANIFEST_PROVIDER_CONFLICT`
- `UNSUITABLE_DOI_SAMPLE`

`UNSUITABLE_DOI_SAMPLE` 由后续 `capture-fixtures` 返回时，coordinator 必须重新派 discovery worker，只替换失败 purpose 的 DOI sample 和 evidence。

Retry 必须遵守：

- `MANIFEST_DISCOVERY_FAILED`: rerun discovery from the same provider seed or mark the provider blocked after retry budget is exhausted.
- `MANIFEST_SCHEMA_INVALID`: keep `output_manifest` as the only writable file and repair schema-invalid fields only.
- `MANIFEST_PROVIDER_CONFLICT`: stop before fixture capture and require coordinator review.
- `UNSUITABLE_DOI_SAMPLE`: replace only the failed `fixtures.doi_samples.<purpose>` object and keep unrelated samples unchanged.
- Retry output must still pass the same `files_allowed_to_modify`, `files_must_not_modify`, and `no_commit` checks.

## Autofix Boundary

Worker 成功后、`validate-manifest` 前，runner 会自动执行一次：

```bash
python3 scripts/onboard_from_manifests.py autofix-manifest \
  --manifest onboarding/manifests/<provider>.yml \
  --evidence-pack .paper-fetch-runs/<provider>-onboarding/discovery/evidence-pack.json \
  --write
```

如果 `validate-manifest` 仍以 `MANIFEST_SCHEMA_INVALID` 失败，runner 会再执行一次 targeted autofix，然后重跑 validate。仍失败才进入既有 blocked/retry 逻辑。

Autofix 只允许处理机器可判的 schema/proof 缺口：

- 补缺失结构性容器字段，以及空 `success_criteria` / `extraction_hints` 默认值。
- 让 `generation.source_queries` 覆盖 `fixtures.discovery_proof.*.queries`。
- 同步 `discovery_proof.selected_doi` 与 `fixtures.doi_samples.<purpose>.doi`。
- 补缺失的 `route_contract`、non-null sample 的 `markdown_contract`、`asset_contract.figures` 模板。
- 只有 evidence pack 中有 high-confidence candidate 时，才替换 null 或不合格 DOI sample。

Autofix 不会批准 access review，不会设置 `markdown_semantic_reviewed: true`，不会绕过 low-confidence DOI candidate。低置信候选只能进入 proof/rejection，留给 worker/operator 处理。

`inspect-discovery` 可用于人工分诊：

```bash
python3 scripts/onboard_from_manifests.py inspect-discovery \
  --manifest onboarding/manifests/<provider>.yml \
  --evidence-pack .paper-fetch-runs/<provider>-onboarding/discovery/evidence-pack.json
```

它输出每个 purpose 的候选摘要、低置信度 purpose 和 discovery proof 缺口。

## Acceptance

Discovery 输出完成后必须满足：

- Manifest 通过 `provider-manifest.schema.json`
- 没有 `TODO`、`TBD`、`unknown`
- 每个 DOI sample 有 evidence object
- Worker 没有修改 `files_must_not_modify`
- `scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run` 生成的 DAG 含 `discover-manifest`
- DAG 中 `operator-access-preflight` 位于 `discover-manifest` 之前
- `scripts/onboard_from_manifests.py start --provider <name> --domain <domain> --dry-run` 写 `briefs/discover-manifest.yml` 和 `briefs/implement-provider.yml`
- `scripts/onboard_from_manifests.py prepare-discovery --provider <name> --domain <domain> --doi-prefix <prefix> --output-dir <dir> --no-network` 写 `discovery/evidence-pack.json`，且 `browser_fallback.enabled=false`
- `run --provider ...` 在 worker prompt 中包含 evidence pack 摘要，并在 validate 前后自动尝试 `autofix-manifest`
- `scripts/onboard_from_manifests.py start --manifest <manifest> --dry-run` 跳过 `discover-manifest`，并从 manifest YAML 读取 provider name
