# Draftpaper-loop 框架级证据一致性与阶段确认优化执行方案

## 1. 方案定位

- 制定日期：2026-08-10
- 状态更新日期：2026-08-11
- 适用版本基线：Draftpaper-loop v0.37.0
- 目标版本：v0.37.1、v0.37.2、v0.38.0
- 适用对象：所有学科插件、所有论文项目、所有结果阶段和人工确认点
- 设计基线：[阶段总结、证据身份与人工确认框架完整优化执行方案](2026-08-07-stage-summary-html-completeness-and-hash-review-optimization.md)
- 本文性质：面向实现的执行手册，不是某一篇论文的修订方案

本方案针对一类框架级错误：同一项目中出现多个看似合理、实际上身份不同的指标、样本数、图表追踪和运行产物，最后被目录扫描或摘要生成逻辑拼成一套“完整结果”。论文项目只是回归样本，不能成为代码中的特殊分支、固定列名、固定数字或固定学科判断。

本文是 2026-08-07 方案的可执行版本：前者记录问题抽象、已完成更新和边界，本文负责按里程碑落地、验证、迁移和发布。除明确标注“工作树已实现”的项目外，其余内容都是待执行项。

## 2. 要解决的问题

### 2.1 指标一致性错误

`metrics.csv` 可能保存单个 seed 或兼容摘要，而 `result_support_checkpoint` 可能读取多 seed 汇总。两者都叫同一个指标时，用户会看到数值不一致，却无法知道它们分别对应哪一个模型、任务、cohort、验证设计、split、seed 或 reducer。

框架必须从源头规定：

- 裸 `metric,value` 文件没有主证据资格；
- 每条指标必须有完整 `MetricEvidence` 身份；
- seed、fold、重复划分和聚合结果必须是不同记录；
- 聚合必须有明确的 `AggregationContract`；
- 主指标只能由 `PrimaryMetricContract` 精确解析，不能取第一行、最大值或文件名中带有 `main` 的记录；
- 兼容 CSV 只能由 canonical evidence 单向生成。

### 2.2 样本分母错误

`source_rows=1671` 与模型 cohort 使用的 `1229` 并不必然是数值冲突。它们可能分别表示原始目录行数、去重后的实体数、建模 source group 或最终 split cohort。如果框架只保留一个 `source_rows` 字段，就会把不同分母错误地写成同一事实。

框架必须从源头规定：

- 每个计数必须声明 `entity_type`、`count_mode`、筛选合同和 cohort；
- 原始行数、唯一实体数、合格实体数、处理成功数、建模样本数和 split 数必须是不同的 typed records；
- 不同计数应通过 sample-flow 的父子关系表达，而不是互相覆盖；
- 只有完整身份完全相同而数值不同，才叫 count conflict；
- 图表、caption、结果支撑和阶段摘要必须引用明确的 CountEvidence ID。

### 2.3 图表追踪错误

旧 `figure_code_trace` 可能沿用旧运行的行数、代码映射或输入文件，而新图像已经由另一套数据和运行生成。仅记录“图号 → 脚本路径”不足以证明图表对应当前证据。

框架必须要求图表追踪同时绑定：

- 当前图像文件 hash 和 semantic hash；
- 图表 metadata/caption/panel contract hash；
- 生成代码及代码 hash；
- 输入 artifact hash；
- plan、run、cohort、snapshot 和 transaction identity；
- metric/count evidence refs；
- producer fingerprint。

任一绑定对象改变，trace 必须变为 stale，相关 checkpoint 不能确认。

### 2.4 新旧运行混合错误

一个结果目录可能同时包含新指标、旧图表、新 result support、旧 trace 和历史 summary。文件都存在不等于它们属于同一次科学运行。

框架必须以 `RunEvidenceBundle` 管理 candidate、validated、active、failed 和 superseded 状态。只有同一个经过验证的 active bundle 才能进入结果解析、checkpoint 和 HTML；失败运行不能覆盖旧 active bundle。

### 2.5 阶段摘要不完整错误

人工确认点不能只展示若干文件名和 hash。用户需要看到一段中文说明，明确本阶段完成了什么，以及图表、表格、代码、报告、运行证据、输入变化和阻断事项的完整清单。

阶段摘要必须由 canonical bundle 和 artifact manifest 确定性生成，不能由 LLM 临时概括数值，也不能让 HTML 自己决定哪个指标可信。

## 3. 现有优化的保留边界

下列能力已经在 v0.37.0 的当前工作基线中完成或具备回归记录，后续实现不得回退：

| 已完成能力 | 保留要求 |
|---|---|
| 完整成果与事务变化分离 | 阶段摘要继续同时显示 `stage_deliverables` 和 `transaction_changes`，不混为一张文件列表 |
| 中文单段阶段总结 | 从确定性 digest 生成，不允许模型自由编造结果数字 |
| 图表、表格、代码、报告和运行证据分组 | 每组都显示内容、状态、路径和 hash |
| 图像预览、caption、代码映射和统计摘要 | 预览仍是审阅辅助，不取代证据合同 |
| 大型 CSV 受限预览 | 页面不嵌入完整预测表，但要显示文件、行列摘要、hash 和可审计路径 |
| stale、blocked、preview 禁止确认 | 仅 `confirmable` 状态生成唯一 hash-bound 确认入口 |
| preview 不污染 ledger/latest pointer | 派生预览不能改变项目科学状态 |
| latest pointer 优先于目录扫描和 legacy ledger | 所有状态读取统一走受控优先级 |
| 路径逃逸和外部绝对路径防护 | 页面可展示机器绝对路径，但项目产物仍只能落在项目边界内 |
| runtime identity 迁移和只读诊断 | 运行时漂移先生成诊断和 migration receipt，不静默写入项目状态 |
| Result Support 路线可见 | Agent 展示路线和后果，但不代替用户作科学选择 |
| 全部人工确认阶段的摘要适配 | research plan、data、methods、plugin、writing、quality 等阶段使用同一摘要合同 |
| 响应式和长路径布局 | 长 hash、run ID、路径和表格不能破坏页面布局 |
| v1/v2 checkpoint 只读兼容 | 旧文件不原地改写、不静默伪升级 |

这些能力属于展示层、状态层和人工门禁基础。它们目前不能证明 MetricEvidence、CountEvidence、RunEvidenceBundle 和 FigureCodeTrace v2 已经完成，因此后续验收必须把“看得见问题”和“阻止问题进入证据链”分开计量。

### 3.1 当前工作树实施状态

本执行方案不是从零开始。当前 v0.37.0 工作树已经完成以下实现，并通过针对性回归；这些改动尚未完成最终 release 收口：

| 里程碑能力 | 当前状态 | 已验证内容 | 尚缺内容 |
|---|---|---|---|
| M0 失败模式和匿名严格 fixture | 已实现并验证 | 证据身份、分母、运行事务、trace 和 HTML 的匿名失败/通过路径；测试模式有显式标记 | 全量发布矩阵和正式 release |
| M1 MetricEvidence、AggregationContract、PrimaryMetricContract | 工作树已实现并验证 | 不同身份不可比较、同身份数值冲突、seed/fold 聚合、主指标零条/多条阻断 | 正式 v0.37.1 发布 |
| M2 CountEvidence、sample-flow | 工作树已实现并验证 | entity/count mode/cohort 缺失阻断、不同分母标记不可比较 | 全部插件 adapter 的最终复核、正式 v0.37.1 发布 |
| M3 RunEvidenceBundle | 工作树已实现并验证 | failed candidate 不覆盖 active、active/superseded 生命周期 | 完整 artifact DAG 的最终复核和正式 v0.37.2 发布 |
| M4 FigureCodeTrace v2 | 工作树已实现并验证 | 图像、metadata、代码、输入或事务变化会使 trace stale | 正式 v0.37.2 发布 |
| M5 阶段 HTML/人工确认基础 | v3 工作树已实现并验证 | 完整成果、中文总结、身份卡、sample-flow、同源 JSON/HTML/Agent、严格确认资格、真实项目不得自动确认 | 全量 CI、跨平台 wheel、正式 v0.38.0 tag/release |
| M6 旧项目审计与发布 parity | 核心能力已实现并验证 | `audit-evidence-identity`、typed evidence bridge、schema registry、Skill/wheel/Codex/Claude parity、228 条 CLI 合同和 release manifest | 全量发布验收、正式 tag/release 和跨平台验证 |

当前已执行的回归结果为：新证据身份/运行事务/图表追踪/严格 HTML 测试 `20 passed`，联合身份/运行/HTML 回归 `65 passed`，已有分组回归 A/B/C/D 分别为 `142/194/391/443 passed`；Ruff、compileall、228 条命令合同、release manifest 和安装矩阵通过。`checkpoint_summary.v3` 已生成并注册，v1/v2 只读兼容、缺字段阻断、同源 Agent payload 和匿名六阶段 showcase 已有测试。分组全量 pytest 已完成，累计 `1179 passed, 2 skipped`。重建后的 `dist/draftpaper_cli-0.37.0-py3-none-any.whl` 已在临时隔离环境中安装，五个跨学科 release fixture、反例回归和语义回归均为 `passed`；可选 OCR 依赖安装成功。含 legacy compatibility 记录的匿名 fixture 运行 `audit-evidence-identity` 时返回 `needs_review` 且保持 `read_only=true`、无写入，这是预期的安全结果。正式 release 仍必须在 CI 中完成真正的跨平台全量回归和发布验收，不能把本地发布候选验证表述为正式 tag/release。

## 4. 框架不变量

以下规则必须同时落到 schema、运行时、测试和文档中：

1. 关键指标和关键计数不是裸数字，而是带完整身份的结构化证据记录。
2. 比较先判断 identity 和 comparability，再比较 value。
3. 没有声明式 aggregation contract 时，不跨 seed、fold、split、站点、时间或验证设计自动聚合。
4. PrimaryMetricContract 必须解析为恰好一条记录；零条或多条都阻断。
5. compatibility、preview、fixture 和 historical 文件默认不能成为科学主证据。
6. 计数必须说明在数什么、如何计数、属于哪个 cohort 和筛选版本。
7. 正式证据只能来自一个经过验证的 active run bundle，除非显式声明 comparison contract。
8. 图表、HTML、写作上下文和兼容摘要都是派生产物，不能生成第二套科学真相。
9. 输入、代码、图像、metadata 或 run transaction 变化会向下游传播 stale。
10. 仅修 hash、路径、trace、HTML 或兼容展示走 derived repair；改变样本、方法、统计设计、主图语义或论断才重开科学 checkpoint。
11. 人工确认始终由用户执行；测试可以自动跳过人工门，但真实科研结果不能自动确认。
12. 核心框架使用通用实体和证据术语，学科插件通过合同声明 `entity_type`、`task`、`metric` 和 `validation_design`。

## 5. 目标架构

```text
研究蓝图 / 方法合同
        ↓
EvidenceContext + PrimaryMetricContract + CountDefinitions
        ↓
candidate RunEvidenceBundle
        ↓
canonical MetricEvidence / CountEvidence / FigureCodeTrace
        ↓
schema + hash + statistic + freshness validation
        ↓
validated active bundle
        ↓
result evidence / result support / sample-flow / comparison receipt
        ↓
checkpoint digest + 中文 stage_summary HTML
        ↓
用户一次性审阅完整阶段成果
        ↓
hash-bound confirm / refine / reject
```

### 5.1 证据层

证据层负责记录事实和身份，不负责替用户选择科学结论。核心记录包括：

- `EvidenceContext v1`：项目、蓝图、数据集、cohort、任务、样本单位、验证设计、split、分析规格和 evidence snapshot；
- `MetricEvidence v3`：指标定义、模型、任务、cohort、验证设计、replicate、aggregation、来源 artifact 和 evidence role；
- `CountEvidence v1`：计数定义、实体类型、计数方式、筛选合同、父级记录、来源 artifact 和用途；
- `AggregationContract v1`：输入记录、replicate 轴、要求的 replicate、reducer、缺失策略和权重；
- `PrimaryMetricContract v1`：唯一主指标的完整选择条件；
- `RunEvidenceBundle v1`：一次成功运行的原子输入、输出和验证收据。

### 5.2 派生层

派生层生成 result support、compatibility CSV、figure trace、sample-flow、checkpoint JSON 和 HTML。所有派生文件都必须保存 source record ID、source hash 或 bundle reference，并且只能从 canonical evidence 单向生成。

### 5.3 门禁层

门禁层负责四类判断：

- identity 完整性；
- evidence 可比性；
- freshness 和 transaction 一致性；
- 是否允许进入人工确认。

门禁层不通过时，必须返回结构化状态和对应恢复路线，不能只返回“数值不一致”。

## 6. 公共证据合同

### 6.1 EvidenceContext

最小上下文应包含：

```json
{
  "schema_version": "dpl.evidence_context.v1",
  "project_id": "...",
  "plan_hash": "...",
  "run_id": "...",
  "run_transaction_id": "...",
  "dataset_id": "...",
  "cohort_id": "...",
  "cohort_view_id": "...",
  "task_id": "...",
  "sample_unit": "...",
  "validation_design_id": "...",
  "split_id": "...",
  "analysis_spec_id": "...",
  "evidence_snapshot_id": "..."
}
```

`validation_design_id` 必须由规范化合同生成。`split`、`split_type`、`holdout_scheme` 等原始列名只能作为 provenance，不能直接当作可比性键。

### 6.2 MetricEvidence 和 AggregationContract

每条指标至少需要：

```text
metric_record_id
metric_definition_id
value
model_id
task_id
cohort_id
validation_design_id
split_id
sample_unit
replicate_axis
replicate_ids
aggregation_id
uncertainty_definition_id
source_artifact
source_sha256
producer_id
evidence_role
```

seed-level、fold-level、repeated-split 和 aggregate 记录必须区分。聚合记录必须引用输入记录，并明确缺失 replicate 的处理方式。多 split pooled 指标必须从 pooled predictions 或等价 canonical 输入重新计算，不能把各 split 指标无合同地平均。

### 6.3 PrimaryMetricContract

主指标合同由研究蓝图或方法合同提供，resolver 只做精确匹配：

- 匹配一条：允许进入主结果；
- 匹配零条：`blocked_missing_primary_metric`；
- 匹配多条：`blocked_ambiguous_primary_metric`；
- 不允许根据文件名、模型名称、第一行或最大数值推断。

### 6.4 CountEvidence 和 sample-flow

通用计数定义至少支持：

```text
catalog_row_count
catalog_unique_entity_count
identified_entity_count
eligible_entity_count
processed_entity_count
feature_complete_entity_count
model_sample_group_count
model_unique_entity_count
train_entity_count
validation_entity_count
test_entity_count
released_product_count
```

每条记录还需声明：

```text
count_record_id
entity_type
count_mode
value
context
filter_contract_id
grouping_key_id
parent_count_record_id
exclusion_reason_table_ref
source_artifact
source_sha256
evidence_role
```

阶段摘要将这些记录显示为“目录 → 去重 → 合格 → 处理 → 建模 → split”的流程。不同定义之间不作 equality comparison；只有 `count_definition + entity_type + mode + context + filter + cohort` 完全相同时，数值不同才是冲突。

### 6.5 RunEvidenceBundle

一次方法运行的生命周期：

```text
candidate → validated → active
candidate → failed
active → superseded
```

规则：

1. 输出先写入 candidate bundle；
2. 运行、schema、hash、统计合同和图表验证全部通过后才能晋升 active；
3. candidate 失败不能覆盖 active；
4. active 被替换时保留旧 bundle 和 superseded receipt；
5. checkpoint 只读取一个 active bundle，或读取显式 comparison contract 指定的多个 bundle。

### 6.6 FigureCodeTrace v2

图表 trace 必须引用：

- 图像 hash 和 semantic hash；
- figure metadata、caption 和 panel contract hash；
- producer code path/hash；
- 输入 artifact hash；
- plan、run、cohort、snapshot、transaction；
- metric/count record refs；
- 生成时间和 producer fingerprint。

旧 trace 缺少上述字段时只能标记 `legacy_unqualified`，可以展示为历史参考，但不能进入 `confirmable` checkpoint。

### 6.7 EvidenceComparisonResult

比较器至少返回：

| 状态 | 含义 | 默认处理 |
|---|---|---|
| `same_identity_same_value` | 同一身份、数值一致 | 通过 |
| `same_identity_value_conflict` | 同一身份、数值不同 | 阻断 |
| `different_identity_non_comparable` | 模型、任务、cohort、验证、split、reducer 或分母不同 | 标记不可直接比较；主论断误用时阻断 |
| `parent_aggregate_relation` | 逐 replicate 记录与声明式 aggregate | 保留关系 |
| `missing_required_identity` | 缺少主证据必要字段 | 阻断 |
| `stale_source` | hash 或 transaction 已过期 | 阻断 |
| `presentation_only_ignored` | 兼容展示文件不参与科学判断 | 忽略为主证据 |

## 7. 实施阶段

### M0：冻结基线与匿名失败夹具

目标：保留已有 HTML 能力，同时把错误抽象成跨学科 fixture。

实施：

1. 记录 v0.37.0 当前 HTML、confirmation gate、latest pointer 和 runtime migration 行为；
2. 建立匿名 fixture，覆盖单 seed/多 seed、不同模型、不同验证设计、不同分母和旧 trace；
3. fixture 只使用 `model_a`、`model_b`、`design_a`、`design_b` 和通用 `entity`，不使用真实论文路径、真实样本 ID 或学科结论；
4. 增加测试，证明现有 HTML 不因证据层重构而丢失；
5. 生成 M0 基线报告和迁移风险清单。

交付物：

- `tests/fixtures/evidence_identity/`；
- 基线 summary/HTML 快照；
- 失败模式说明和预期状态矩阵。

完成条件：基线测试可重复，且没有把 fixture 当成真实科研证据的路径。

### M1：MetricIdentity、AggregationContract 和 PrimaryMetricContract

目标版本：v0.37.1。

实施文件：

- `draftpaper_cli/result_evidence.py`；
- `draftpaper_cli/evidence_registry.py`；
- `draftpaper_cli/resources/schemas/evidence_context_v1.json`；
- `draftpaper_cli/resources/schemas/metric_evidence_v3.json`；
- `draftpaper_cli/resources/schemas/aggregation_contract_v1.json`；
- `draftpaper_cli/resources/schemas/primary_metric_contract_v1.json`；
- `draftpaper_cli/resources/schemas/evidence_comparison_result_v1.json`。

实施步骤：

1. 建立字段别名 registry，将 `validation_design`、`evaluation_design`、`holdout_scheme` 等映射到规范字段；
2. 分离 model、task、cohort、validation、split、replicate 和 aggregation 维度；
3. 禁止没有 contract 的跨 seed/fold/split 聚合；
4. 让 resolver 只返回 typed metric records；
5. 让 primary metric 只从完整合同精确匹配；
6. 将 `metrics.csv` 等兼容输出标记 `presentation_only`，并写入 canonical source record ID/hash；
7. 在 result support 中使用 record ID，删除跨模型通用指标别名的隐式猜测。

必须通过的失败测试：

- 同名指标、不同模型 → non-comparable；
- 同模型、不同验证设计 → non-comparable；
- seed row 与 seed mean → parent/aggregate relation；
- 缺少 required seed → blocked；
- 完整 identity 相同但 value 不同 → conflict；
- primary contract 零条或多条 → blocked；
- 第一行或最大值选择 → 测试失败。

### M2：CountIdentity 与 SampleFlow

目标版本：v0.37.1。

实施文件：

- `draftpaper_cli/resources/schemas/count_evidence_v1.json`；
- `draftpaper_cli/checkpoint_digest.py`；
- `draftpaper_cli/result_support_signals.py`；
- `draftpaper_cli/evidence_registry.py`。

实施步骤：

1. 禁止无定义的核心 `source_rows`、`n`、`count`；
2. 为原始行、唯一实体、合格实体、处理成功、建模 group 和 split 成员创建 typed count records；
3. 以 parent relation 和 filter contract 生成 sample-flow；
4. 让 figure trace、caption、result support 和 HTML 通过 count record ID 引用分母；
5. 发现两个不同分母时返回 non-comparable，不自动把其中一个改成另一个；
6. 如果主图或主论断没有明确分母，阻止关键图表和确认。

必须通过的失败测试：

- catalog rows 与 model group → sample-flow，不是冲突；
- unique entity 与 released product → 不可直接比较；
- 同一 CountIdentity 数值不一致 → blocked；
- 缺 entity type/count mode → blocked；
- 不同学科的 object/cutout、patient/visit、source/event、site/sample fixture 全部通过。

### M3：RunEvidenceBundle 原子运行事务

目标版本：v0.37.2。

实施文件：

- `draftpaper_cli/artifact_identity.py`；
- `draftpaper_cli/orchestrator.py`；
- `draftpaper_cli/results.py`；
- `draftpaper_cli/stage_receipts.py`；
- `draftpaper_cli/resources/schemas/run_evidence_bundle_v1.json`。

实施步骤：

1. 每次方法运行先创建 candidate transaction；
2. 所有 canonical output、metric/count records 和 figure metadata 都登记到 candidate bundle；
3. 完成 schema、hash、统计合同、输入和输出验证；
4. 通过后原子更新 active pointer；
5. 失败时只生成 failed receipt，不修改旧 active bundle；
6. active 替换时生成 superseded receipt；
7. checkpoint、result resolver 和 HTML 只消费 active bundle。

必须通过的失败测试：

- candidate 失败不覆盖 active；
- 中断运行不生成 confirmable checkpoint；
- 新 bundle 晋升后旧 bundle 不被删除；
- checkpoint 不混合两个 transaction 的普通输出；
- comparison contract 明确引用多个 bundle 时，每条证据身份仍独立。

### M4：FigureCodeTrace v2 和 stale 传播

目标版本：v0.37.2。

实施文件：

- `draftpaper_cli/code_ownership.py`；
- `draftpaper_cli/figure_plugin_trace.py`；
- `draftpaper_cli/artifact_identity.py`；
- `draftpaper_cli/checkpoint_digest.py`；
- `draftpaper_cli/resources/schemas/figure_code_trace_v2.json`。

实施步骤：

1. 追踪当前 active bundle 中生成的图像和 metadata；
2. 记录输入 artifact、代码、run、cohort、metric/count refs；
3. 图像、metadata、producer code 或输入变化时传播 stale；
4. 旧 trace 只能显示为 legacy preview；
5. 允许 `rebuild-derived` 重建 trace、HTML、兼容摘要和写作上下文；
6. derived rebuild 不得修改样本纳入规则、模型训练结果或主论断。

必须通过的失败测试：

- figure hash 变化而 trace 未更新 → stale；
- metadata hash 变化 → stale；
- producer code hash 变化 → stale；
- trace 引用不存在的 metric/count record → blocked；
- 不同分母图表未引用 CountEvidence → blocked。

### M5：Checkpoint v3 与人工确认页面

目标版本：v0.38.0。

实施文件：

- `draftpaper_cli/checkpoint_digest.py`；
- `draftpaper_cli/checkpoint_summary.py`；
- `draftpaper_cli/checkpoint_html.py`；
- `draftpaper_cli/checkpoint_confirmation.py`；
- `docs/human_checkpoints.zh-CN.md`；
- `docs/human_checkpoints.md`。

实施步骤：

1. digest 读取 active bundle 和 evidence snapshot；
2. 先执行 identity/comparability，再执行 value consistency；
3. 页面显示主指标身份卡、sample-flow、图表 trace 新鲜度和 comparison 分类；
4. 页面开头生成一段中文总结，说明本阶段目标、已完成工作、生成的完整内容和当前阻断事项；
5. 产物清单必须涵盖图表、表格、代码、文字、报告、数据产品、运行证据、输入变化、hash 和状态；
6. 页面提供项目相对路径和本机绝对路径；
7. `preview`、`blocked`、`stale`、`identity-missing` 页面不提供确认命令；
8. `confirmable` 页面只提供一个绑定当前 checkpoint hash 的确认入口；
9. Agent、CLI、JSON 和 HTML 必须从同一 digest 读取事实；
10. 测试模式可以自动跳过人工门，但必须在产物中记录 `test_auto_confirmation=true`，且不得改变真实项目状态。

### M6：旧项目审计、迁移和跨平台发布

目标版本：v0.38.0。

实施步骤：

1. 新增只读 `audit-evidence-identity` 诊断；
2. 输出缺失身份、legacy compatibility、模糊 count、stale trace、可确定迁移字段和需要重跑字段；
3. 只有能从同一 manifest、列和 hash 证明的字段才能自动迁移；
4. 不能猜测模型、cohort、分母或统计设计；
5. 生成 migration receipt，记录 before/after hash 和推导依据；
6. 旧项目身份不完整时停在 refinement/rebuild，不伪造 confirmable；
7. 执行 astronomy、machine learning、medicine、geography 和 generic tabular 匿名 fixture；
8. 验证 Windows/Linux/macOS、source/wheel、schema/Skill 和 CLI reference parity；
9. 生成迁移指南和发布说明。

## 8. 阶段摘要 HTML 的固定合同

每个人工确认点只生成一个主要阶段成果包，目录可以包含派生文件，但 Agent 必须指向同一个 summary HTML。HTML 必须按以下顺序展示：

1. 阶段名称、阶段目标、当前状态和是否允许确认；
2. 一段中文总结：本阶段围绕什么目标完成了什么工作，生成了哪些完整成果，以及目前是否存在阻断；
3. 完整成果清单：图表、表格、代码、正文/文字、报告、数据产品、运行证据和配置；
4. 每类成果的内容摘要、相对路径、绝对路径、hash、生成事务和当前状态；
5. 主指标身份卡和来源记录；
6. sample-flow 及每个 count 的实体类型和计数方式；
7. figure trace 和代码/输入绑定；
8. comparison 分类：一致、真实冲突、不可比较、缺身份、stale、presentation-only；
9. 机器验证结果、剩余问题和推荐恢复路线；
10. 用户确认的含义、确认后解锁阶段和拒绝后的唯一安全路线。

页面不能：

- 只列文件名而不解释文件内容；
- 只显示 hash 而不说明 hash 绑定了什么；
- 把内部路径当作阶段总结；
- 把不同比例、不同模型或不同验证设计写成同一结果冲突；
- 让用户在多个分散页面之间拼接本阶段成果；
- 由页面脚本自行选择“更可信”的数值。

## 9. 错误后的恢复路由

| 发现状态 | 说明 | 默认路线 | 是否重开研究蓝图 |
|---|---|---|---|
| `presentation_only_ignored` | 兼容文件与 canonical evidence 的展示差异 | 重建兼容摘要/HTML | 否 |
| `stale_source` | 图像、metadata、代码或输入已变化 | derived rebuild | 否，除非科学语义变化 |
| `missing_required_identity` | 主证据缺字段 | 补充可由 manifest 证明的身份；否则人工 refinement | 视是否改变科学合同 |
| `different_identity_non_comparable` | 两个结果属于不同模型、cohort、验证或分母 | 分开展示并修改论断绑定 | 通常否；若主论断要改则重开对应 checkpoint |
| `same_identity_value_conflict` | 同一身份、同一合同却有不同数值 | 查找来源并重建或重跑 | 若结果或方法变化则是 |
| `ambiguous_primary_metric` | 主指标匹配多条 | 修正 PrimaryMetricContract 或输出 | 若合同变化则是 |
| `failed_candidate_bundle` | 新运行失败 | 保留旧 active，修复 candidate | 否，除非改科学合同 |
| `invalid_count_relationship` | sample-flow 父子关系不成立 | 数据/筛选核验 | 若纳入规则变化则是 |

原则是：框架问题先在框架层修复，派生文件问题走 derived rebuild，只有科学输入、方法、统计设计、样本 cohort、主图语义或论断改变时才进入科学重开路线。

## 10. 文件和资源改动清单

### 10.1 核心代码

- `draftpaper_cli/result_evidence.py`：规范维度、typed metric、聚合合同和主指标解析；
- `draftpaper_cli/result_support.py`：使用 evidence IDs，隔离模型和验证设计；
- `draftpaper_cli/result_support_signals.py`：忽略 presentation-only，传播 comparison 状态；
- `draftpaper_cli/evidence_registry.py`：注册和索引 metric/count/run evidence；
- `draftpaper_cli/artifact_identity.py`：transaction、bundle、producer 和 freshness；
- `draftpaper_cli/checkpoint_digest.py`：identity-first digest、sample-flow 和完整成果；
- `draftpaper_cli/checkpoint_summary.py`：summary v3 和旧版本只读兼容；
- `draftpaper_cli/checkpoint_html.py`：中文内容、证据卡、路径和完整产物展示；
- `draftpaper_cli/code_ownership.py`、`figure_plugin_trace.py`：FigureCodeTrace v2；
- `draftpaper_cli/orchestrator.py`：active bundle gate 和恢复路线分流；
- `draftpaper_cli/doctor.py`、`runtime_handshake.py`：身份审计、漂移和迁移诊断。

### 10.2 Schema 和发布资源

- `draftpaper_cli/resources/schemas/evidence_context_v1.json`；
- `draftpaper_cli/resources/schemas/metric_evidence_v3.json`；
- `draftpaper_cli/resources/schemas/aggregation_contract_v1.json`；
- `draftpaper_cli/resources/schemas/primary_metric_contract_v1.json`；
- `draftpaper_cli/resources/schemas/count_evidence_v1.json`；
- `draftpaper_cli/resources/schemas/run_evidence_bundle_v1.json`；
- `draftpaper_cli/resources/schemas/figure_code_trace_v2.json`；
- `draftpaper_cli/resources/schemas/evidence_comparison_result_v1.json`；
- `draftpaper_cli/resources/schemas/checkpoint_summary_v3.json`；
- `draftpaper_cli/resources/schemas/schema_registry.json`；
- `draftpaper_cli/resources/release_manifest.json`。

所有新增 schema 必须注册 current/accepted/migration 状态。历史 v1/v2 可以读取，但不得原地覆盖或静默填补缺失科学语义。

### 10.3 Skill、CLI 和文档同步

以下副本必须在同一 release 中保持一致：

- `codex_skills/draftpaper-workflow/`；
- `.claude/skills/draftpaper-workflow/`；
- `draftpaper_cli/resources/draftpaper_workflow/`；
- `tools/claude_code_payload/dot_claude/skills/draftpaper-workflow/`；
- `docs/cli_reference.md`；
- `docs/human_checkpoints.zh-CN.md` 和英文版；
- command risk matrix、迁移指南和 release manifest。

所有项目状态写入必须通过权威 CLI；不得手工编辑 `project.json`、stage manifest、passport、ledger 或 active pointer 来绕过门禁。

## 11. 测试矩阵

### 11.1 证据身份

- 同名指标不同模型/任务/cohort/验证设计 → non-comparable；
- 同一完整 identity 不同值 → value conflict；
- seed mean 缺少输入 seed → blocked；
- 无 aggregation contract → 不生成 aggregate；
- primary contract 零条/多条 → blocked；
- 第一行、最大值、文件名猜测 → 必须失败；
- compatibility scalar → 不进入主证据。

### 11.2 计数和 sample-flow

- catalog row、unique entity、eligible entity、processed entity、model group、split member → 形成有向 sample-flow；
- 不同分母 → non-comparable，不报 equality conflict；
- 同一 count identity 不同值 → blocked；
- 无 entity type、count mode、filter 或 cohort → blocked；
- object/cutout、source/event、patient/visit、site/sample 等通用 fixture 全部通过。

### 11.3 运行事务和图表

- failed candidate 不覆盖 active；
- partial output 不产生 confirmable checkpoint；
- active 替换保留 superseded receipt；
- 图像、metadata、代码、输入任一 hash 改变 → trace stale；
- trace 引用缺失 evidence record → blocked；
- checkpoint 不混合不同 transaction 的普通文件。

### 11.4 HTML 和人工确认

- 开头有中文单段总结；
- 完整成果清单与事务变化分开；
- 图表、表格、代码、报告、运行证据都可定位；
- 主指标 identity 和 sample-flow 可读；
- comparison 状态语义正确；
- stale/blocked/preview 无确认；
- confirmable 只有一个 hash-bound 命令；
- Agent、JSON、CLI 和 HTML 的状态/数量一致；
- offline、UTF-8、响应式、路径 escaping 和敏感信息清理通过。

### 11.5 回归命令

```powershell
python -m pytest tests/test_metric_identity.py tests/test_count_identity.py tests/test_evidence_comparison.py -q
python -m pytest tests/test_run_evidence_bundle.py tests/test_checkpoint_digest.py tests/test_checkpoint_summary.py -q
python -m pytest tests/test_result_evidence.py tests/test_result_support.py tests/test_evidence_registry.py tests/test_artifact_identity.py -q
python -m ruff check draftpaper_cli tests
python -m compileall -q draftpaper_cli
python -m build
```

发布前必须再执行全量测试、隔离 wheel 安装、CLI smoke、schema registry 检查、Skill parity 检查和浏览器 HTML 验收。重点测试通过不能替代全量回归。

## 12. 旧项目迁移策略

迁移分为三类：

### 12.1 可确定迁移

如果字段可由同一 run manifest、输入 hash、现有列和明确的插件合同直接证明，可以写入新 identity，并生成 migration receipt。

### 12.2 只能标记 legacy

如果旧文件缺少身份，但仍可作为历史参考，可以保留为 `legacy_unqualified` 或 `presentation_only`。它们可以在 HTML 中显示，但不能进入主论断和确认门。

### 12.3 必须人工核验或重跑

如果需要猜测模型、样本分母、cohort、验证设计、reducer 或主指标，不得自动补造。项目应停在 refinement/rebuild，并明确需要用户提供的信息或重新运行的阶段。

迁移工具只读诊断优先，建议命令：

```powershell
python -m draftpaper_cli.cli audit-evidence-identity --project <project>
```

它必须输出缺失身份、可确定映射、不可确定映射、stale trace、需要派生重建的文件和需要科学重跑的文件，不直接修改科学状态。

## 13. 漂移和维护约束

为避免“修改一处、其他副本继续使用旧合同”的漂移，发布前必须执行：

1. 从唯一 source manifest 生成 CLI reference、Skill contract 和 wheel resource；
2. 检查源码、wheel、Skill、schema registry、release manifest 的版本和 hash parity；
3. Ruff 在源码、wheel 和发布副本上都必须通过；若确有历史 baseline，必须显式登记并执行 no-new-debt，不能用关闭规则掩盖告警；当前工作树的 `ruff check draftpaper_cli tests` 已通过；
4. 新增字段必须同时更新 schema、adapter、serializer、digest、HTML、tests 和文档；
5. 任何兼容适配器必须单向从 canonical evidence 生成，不允许反向污染 resolver；
6. 每个版本保存 migration receipt 和 release manifest；
7. 运行时身份变化先生成诊断，只有用户明确接受迁移后才写入项目；
8. fixture、mock 和 preview 必须带显式角色标记，不能进入真实项目的 active evidence。

## 14. 版本和发布顺序

### v0.37.1

包含 M0、M1 和 M2：指标身份、聚合合同、主指标唯一解析、计数身份和 sample-flow。目标是先阻断数值和分母误判。

### v0.37.2

包含 M3 和 M4：RunEvidenceBundle 原子发布、FigureCodeTrace v2、stale 传播和派生重建。目标是阻断新旧运行和旧图表追踪混用。

### v0.38.0

包含 M5 和 M6：checkpoint v3、完整 HTML、人工确认 UX、旧项目审计、迁移和跨平台发布。目标是让用户在一个 HTML 中看懂阶段成果，并让不可确认状态无法绕过。

每个版本必须按以下顺序执行：

```text
增加失败测试
→ 实现 schema 和核心逻辑
→ 更新派生层
→ 更新 HTML/Agent/CLI
→ 更新 Skill、wheel、文档和 manifest
→ 重点回归
→ 全量测试和构建
→ 迁移/跨学科 fixture
→ 发布验收
```

## 15. 最终放行条件

v0.38.0 只有同时满足以下条件才可标记完成：

1. 所有主指标都有完整 MetricEvidence identity；
2. 所有关键计数都有 CountEvidence identity；
3. 所有聚合都有 AggregationContract；
4. PrimaryMetricContract 不依赖第一行、最大值或名称猜测；
5. compatibility 输出不能进入主证据；
6. 不同验证设计、模型、cohort 和分母不会被隐式比较或聚合；
7. active RunEvidenceBundle 原子发布且失败不会覆盖旧结果；
8. FigureCodeTrace v2 与当前图像、代码、输入和 evidence refs 一致；
9. comparability-first 比较器能区分 conflict、non-comparable、missing 和 stale；
10. stage_summary HTML 用一段中文话说明本阶段做了什么，并列出完整生成内容；
11. HTML、JSON、CLI、Agent 和 ledger 使用同一事实来源；
12. stale、blocked、preview、legacy_unqualified 不可确认；
13. 旧项目迁移不会猜测科学语义；
14. 跨学科匿名 fixture、真实项目只读回归、全量测试、wheel、Skill/schema parity 和浏览器验收全部通过；
15. 没有任何自动化路径替用户确认研究蓝图、核心证据或科学结论。

## 16. 不在本方案范围内

- 不替论文选择模型、样本 cohort、统计口径或科学论断；
- 不把某个论文项目的路径、列名、数字、阈值或模型写入核心框架；
- 不自动删除旧指标、图表、运行或 checkpoint；
- 不要求迁移大型外部数据集；
- 不因 HTML 展示优化而重新训练模型；
- 不把 fixture、mock、preview 或兼容摘要冒充真实科研证据；
- 不在本方案中设计商业化、会员、许可证或付费插件逻辑。

## 17. 交付物

最终交付应包括：

1. 更新后的框架级设计方案；
2. 新证据 schema 和 schema registry；
3. MetricEvidence、CountEvidence、AggregationContract、PrimaryMetricContract、RunEvidenceBundle 和 FigureCodeTrace 实现；
4. result evidence、result support、checkpoint digest 和 HTML 更新；
5. 旧项目身份审计和迁移报告；
6. 跨学科匿名 fixtures 和测试；
7. 中文/英文人工确认与迁移文档；
8. CLI reference、risk matrix、Skill copies 和 release manifest；
9. 全量测试、wheel、跨平台和浏览器验收记录；
10. v0.37.1、v0.37.2 和 v0.38.0 的 release notes。

## 18. 完成判定

本方案完成的标志不是某个论文项目的页面不再显示 warning，而是 Draftpaper-loop 对任意学科、任意项目都能在证据进入 result support、图表追踪和人工确认之前识别：

- 这是同一指标还是不同 estimand；
- 这是同一分母还是不同 sample-flow 节点；
- 这是当前运行还是旧运行的派生产物；
- 这是可靠证据、兼容展示、历史参考还是测试 fixture；
- 应该重建派生文件、重新运行方法，还是重新打开科学 checkpoint。

只有在这些判断由公共 schema、运行时和测试共同保证后，阶段摘要 HTML 才真正成为可审阅的框架产物，而不是对单一论文项目的事后解释页。
