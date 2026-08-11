# Draftpaper-loop 框架级证据一致性与阶段审阅完整优化执行方案

## 1. 方案定位

- 基线：Draftpaper-loop v0.37.0 工作树
- 目标：把阶段摘要不完整、指标口径漂移、样本分母混淆、旧运行与新图表混用等问题，固化为适用于所有学科和所有论文项目的公共约束
- 来源：2026-08-07 阶段摘要与证据身份方案，以及当前工作树已经完成的证据身份、运行事务、图表追踪和匿名 HTML showcase 实现
- 适用对象：核心 CLI、schema、evidence resolver、artifact DAG、checkpoint、Agent payload、HTML、Skill 副本、测试和发布合同
- 非目标：不修复某一篇论文的科学内容，不修改任何真实项目的指标、图表、列名、样本、模型或论断

本方案解决的是“框架为什么会允许这种错误出现，以及如何让错误在进入阶段摘要、Result Support 和人工确认点之前被阻断”。真实论文项目只能作为只读回归材料；公共测试和默认框架规则必须使用匿名、跨学科的最小 fixture。

## 2. 必须先明确的框架边界

### 2.1 真实项目问题不能直接变成核心代码特判

从某个论文项目观察到的数字不一致，只能先归纳为通用问题类别：

| 项目中看到的现象 | 通用问题类别 | 框架应该约束什么 |
|---|---|---|
| `metrics.csv` 与 result-support 中指标不一致 | 多 seed、单 seed、兼容输出和正式结果没有身份区分 | `MetricEvidence`、`AggregationContract`、`PrimaryMetricContract` |
| trace 中的 `source_rows` 与当前建模样本不同 | 不同实体类型、去重阶段和 cohort 共用裸分母 | `CountEvidence`、sample-flow 和 count identity |
| 阶段页面只列出少数文件 | 阶段作用域发现不完整或把目录存在误当成阶段成果 | stage-owned scope、完整产物清单和 deterministic digest |
| 旧 trace 与当前图像、代码或输入混用 | 图表不是当前运行的原子产物 | `FigureCodeTrace v2`、run transaction 和 stale gate |

核心框架不得写入真实论文的绝对路径、模型名、列名、数字、图号、学科阈值、真实对象 ID 或科学结论。需要处理学科差异时，必须通过学科插件或 project-local adapter 声明合同，由公共框架验证合同，而不是由核心代码猜测语义。

### 2.2 失败模式晋升规则

任何新问题进入框架开发前，必须经过以下流程：

1. 从真实项目中抽取“错误类别”，删除项目路径、真实 ID、领域词汇和科学数字；
2. 用 `model_a/model_b`、`design_a/design_b`、`entity` 等匿名字段构造最小 fixture；
3. 为 fixture 定义预期状态：`confirmable`、`blocked`、`preview`、`stale`、`legacy_unqualified` 或 `non_comparable`；
4. 先增加失败测试，再修改公共 schema、resolver 或 gate；
5. 用至少两个不同学科语义的 fixture 验证规则没有绑定某一学科；
6. 只有匿名测试通过，才允许用真实项目执行只读回归；
7. 真实项目回归不得反向写入公共默认值，也不得成为自动确认依据。

如果一个问题只能靠“识别某个项目名”“匹配某个模型名”或“看到某个固定数字”才能修复，它不是公共框架规则，应退回到插件合同或项目级适配层。

### 2.3 展示样例与真实科研结果隔离

阶段 HTML showcase 只用于检查用户是否能看懂页面和确认门禁是否正确：

- 在临时匿名项目中生成；
- 不读取真实论文项目路径、数据、模型或日志；
- 所有摘要、图像和结果均是测试 fixture；
- 记录 `test_auto_confirmation=true`，明确测试代码跳过了人工动作；
- 不写入真实 project ledger、passport、active pointer、checkpoint 或确认记录；
- 任何 showcase 通过，都不能推出真实项目的科学结果已确认。

## 3. 当前工作树已经完成的通用优化

以下内容已经存在于工作树，并已通过针对性回归。它们代表“代码已实现”，不代表正式 release、跨平台 CI 和真实项目人工确认已经完成。

### 3.1 阶段摘要和产物完整性

- `checkpoint_digest.py` 使用统一的 `STAGE_SCOPE_PREFIXES`，只收集当前 stage-owned 的产物；
- 排除 `review/checkpoints`、历史页面、缓存和递归生成目录，避免旧页面或其他阶段文件混入；
- 对 Markdown、JSON、YAML、CSV、Python、TeX、PNG、PDF 等阶段级小型产物建立实际相对路径清单；
- 中文阶段摘要由确定性 digest 生成，不能由模型自由编造数字；
- 阶段摘要将本阶段生成、修改、验证、阻断和未解决事项区分开；
- HTML 同时展示图表、表格、代码、报告、运行证据、身份卡、sample-flow、hash 和状态；
- 大型 CSV 只提供受限预览、行列摘要、来源和 hash，不把完整预测表嵌入 HTML；
- Agent payload、`stage_summary.json` 和 HTML 使用同一事实来源，避免页面和 Agent 口径漂移。

### 3.2 证据身份和比较门禁

- `MetricEvidence` 记录指标定义、模型、任务、cohort、验证设计、split、replicate、聚合、来源 artifact 和 evidence role；
- `AggregationContract` 明确 seed/fold/repeated split 的输入、reducer、缺失策略和聚合结果；
- `PrimaryMetricContract` 只允许精确匹配一条主指标，不再取第一行、最高值或文件名推断；
- `CountEvidence` 区分 entity type、count mode、cohort、filter contract、父子计数关系和来源；
- `EvidenceComparisonResult` 先判断 identity 和 comparability，再比较数值；
- 不同模型、任务、验证设计、split、cohort 或分母返回 `non_comparable`，不冒充数值冲突；
- 同一完整 identity 的不同值返回 `same_identity_value_conflict` 并阻断；
- presentation-only、compatibility、legacy 和 fixture 产物不能成为科学主证据。

### 3.3 运行事务和图表追踪

- `RunEvidenceBundle` 支持 `candidate → validated → active` 和失败、替代生命周期；
- failed candidate 不覆盖 active bundle；
- `FigureCodeTrace v2` 绑定图像、metadata、caption/panel contract、代码、输入、run transaction、cohort、metric refs 和 count refs；
- 输入、代码、图像、metadata 或运行事务变化会传播 `stale`；
- 仅修复 hash、路径、排序、HTML 或派生兼容文件时，走 derived rebuild；
- 改变样本、方法、统计设计、主图语义或论断时，才重新打开科学 checkpoint。

### 3.4 人工确认和匿名 showcase

当前已经生成匿名六阶段 showcase，覆盖：

- `research_plan`：展示研究蓝图和可行性产物；
- `data`：展示数据合同、筛选和数据产物；
- `methods`：展示方法、运行身份和方法代码；
- `result_support`：展示两条互斥路线并保持 `blocked`，不替用户选择；
- `core_evidence`：展示主指标、身份卡、sample-flow、图表和代码；
- `quality_checks`：展示质量检查和发布前状态。

页面状态、路径、hash 和测试标记已经完成浏览器检查，桌面端无横向溢出。该 showcase 是框架 UX 和状态门禁测试，不是论文结果。

### 3.5 当前验证状态

- 证据身份、运行事务、图表追踪和严格 HTML 重点测试：`20 passed`；
- 联合身份、运行、checkpoint、HTML、Result Support 和 runtime 回归：`65 passed`；
- 已完成分组回归 A/B/C/D：分别为 `142/194/391/443 passed`；
- Ruff、compileall、228 条 CLI contract、release manifest 和安装矩阵：通过；
- wheel 已构建，系统依赖隔离安装后的五域 release fixture、反例回归和语义回归：通过；
- legacy fixture 的 `audit-evidence-identity` 返回 `needs_review`、`read_only=true`、无写入：符合预期；
- 分组全量 pytest 已完成：`1179 passed, 2 skipped`；此前单进程超时仅记录为执行方式限制；
- `checkpoint_summary_v3.json` 已实现并注册为当前生产 summary 合同，v1/v2 仅保留只读 legacy 兼容；
- 重建后的 wheel 已完成临时隔离安装、五域 release fixture、反例和语义回归；正式 tag/release、跨平台发布验收和最终 CI 发布回归仍未完成。

## 4. 目标架构和事实流

```text
研究蓝图 / 方法合同 / 插件合同
        ↓
EvidenceContext + PrimaryMetricContract + CountDefinitions
        ↓
candidate RunEvidenceBundle
        ↓
MetricEvidence / CountEvidence / FigureCodeTrace v2
        ↓
schema + identity + statistic + hash + freshness validation
        ↓
validated active bundle
        ↓
result evidence / result support / sample-flow / comparison receipt
        ↓
stage-owned deterministic digest
        ↓
stage_summary.json + stage_summary.zh-CN.html + Agent payload
        ↓
confirmable / blocked / stale / preview / refinement_required
        ↓
用户 hash-bound 确认或选择恢复路线
```

关键原则：只有上游 canonical evidence 可以生成下游摘要；摘要、HTML、Agent payload 和 compatibility 输出永远不能反向改变 scientific truth。

## 5. 框架级约束的具体落点

### 5.1 阶段作用域约束

实现要求：

1. 用公共 `STAGE_SCOPE_PREFIXES` 定义每个 stage 的输入范围；
2. 用 checkpoint manifest 和 artifact manifest 记录阶段产物；
3. 扫描时排除 checkpoint 页面、历史目录、缓存和失败 candidate；
4. 同名文件必须保留其 stage、run、bundle 和来源身份；
5. 不允许“项目目录里最新的文件”自动晋升为当前结果；
6. 发现跨 stage 或跨 bundle 文件时返回 `legacy_unqualified` 或 `stale`，不能静默合并。

验收要求：匿名 fixture 必须同时包含同名的旧文件、新文件、历史页面和另一个阶段文件，并证明摘要只列当前作用域内的产物。

### 5.2 指标一致性约束

所有正式指标至少包含：

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
source_artifact
source_sha256
evidence_role
```

resolver 不得从 `metric,value` 两列推断主结果。任何兼容格式必须从 canonical record 单向生成，并默认标记 `presentation_only`。

### 5.3 计数和 sample-flow 约束

所有计数必须说明“数的是什么、如何数、属于哪个 cohort、由哪个筛选合同产生”。至少支持目录行数、唯一实体数、合格实体数、处理实体数、特征完整数、建模组数和 split 成员数等通用节点。

不同 count identity 之间只建立父子或派生关系，不做直接 equality comparison。只有计数定义、实体类型、计数方式、cohort、筛选合同和来源身份全部相同，数值不同才是冲突。

### 5.4 图表和运行事务约束

图表必须来自当前 active bundle，且 trace 同时指向当前图像、代码、输入、metadata、metric/count evidence 和 transaction。任何一个身份变化都必须让下游 trace 和 checkpoint 进入 stale，防止“旧图 + 新代码”或“新图 + 旧指标”进入确认页。

### 5.5 HTML 和人工确认约束

每个人工确认点只生成一个可消费的阶段包，至少包含：

- 中文单段总结：本阶段围绕什么目标，生成/修改/验证了什么，留下什么问题；
- 完整产物清单：图表、表格、文字、代码、报告、运行证据和受限数据预览；
- 项目相对路径、本机绝对路径、类型、状态和 hash；
- active run、primary metric、sample-flow、figure trace 和 comparison 状态；
- `confirmable`、`blocked`、`stale`、`preview` 或 `refinement_required` 的原因；
- 确认后冻结的身份，以及拒绝后的唯一恢复路线。

`blocked`、`stale`、`preview`、身份缺失和 legacy 页面不能提供确认命令。真正科研项目的确认必须由用户执行。

## 6. 从当前工作树到正式发布的执行阶段

### M0：建立框架作用域和匿名回归门

目标：让所有后续修复不再围绕单篇论文目录进行。

执行：

1. 保留当前匿名六阶段 showcase 和失败 fixture；
2. 为 fixture 增加同名跨阶段文件、旧 bundle、失败 candidate、裸指标和裸计数；
3. 增加框架范围检查，拒绝核心代码和默认 schema 中出现用户专属绝对路径、真实项目 ID、科学数字和领域特判；
4. 记录 fixture 的预期状态矩阵；
5. 将真实项目只读回归与公共 fixture 测试分开报告。

交付：匿名 fixture、scope policy、反硬编码测试、状态矩阵和基线报告。

### M1：发布证据身份合同

目标版本：v0.37.1。

执行：

1. 确认 `EvidenceContext`、`MetricEvidence`、`CountEvidence`、`AggregationContract` 和 `PrimaryMetricContract` 的 schema；
2. 统一 `validation_design`、`evaluation_design`、`holdout_scheme` 等字段的 provenance 和 canonical identity 区分；
3. 确认 seed、fold、repeated split 和 pooled prediction 的 replicate contract；
4. 让 result resolver 只消费完整 identity 的正式记录；
5. 为兼容 CSV 生成单向 presentation adapter；
6. 对缺失、冲突、多主指标和不可比较状态增加反例测试。

交付：schema registry 更新、evidence resolver、comparison receipt、Result Support gate 和 v0.37.1 release candidate。

### M2：固定阶段摘要的完整性合同

目标版本：v0.37.1 同步收口。

执行：

1. 将 `STAGE_SCOPE_PREFIXES` 纳入公共资源或可验证注册表；
2. 让 `checkpoint_digest` 只读取当前阶段和当前 active bundle；
3. 让摘要叙述、完整清单、统计摘要和路径均由同一 digest 生成；
4. 对每个阶段验证“生成、修改、验证、失败、未解决”五类信息；
5. 将大文件从页面正文中降级为受限预览，但保留路径、列摘要、hash 和来源；
6. 让 Agent 只输出摘要生成器返回的路径和状态，不自行重述事实。

交付：stage summary contract v2 的稳定实现、HTML/JSON/Agent parity 测试和六阶段匿名页面。

### M3：原子运行和图表 trace 发布

目标版本：v0.37.2。

执行：

1. candidate 运行先写入隔离 bundle；
2. 通过 schema、输入 hash、统计合同、代码 trace 和输出完整性检查后才晋升 active；
3. 失败 candidate 只能产生诊断，不得覆盖旧 active；
4. 图表 trace 绑定当前运行事务、输入、代码、图像和 evidence refs；
5. 让 stale 状态传播到 result support、摘要和人工门禁；
6. 为 derived rebuild 和 scientific reopen 分别生成结构化恢复建议。

交付：RunEvidenceBundle v1、FigureCodeTrace v2、stale propagation 和 v0.37.2 release candidate。

### M4：Checkpoint summary v3 和同源人工确认包

目标版本：v0.38.0。

执行：

1. 新增 `checkpoint_summary_v3.json`，严格包含阶段叙述、完整产物、身份卡、sample-flow、comparison、review state、确认资格和恢复路线；
2. `checkpoint_summary.py` 默认生成 v3，同时对 v1/v2 只读兼容；缺少身份时标记 `legacy_unqualified`，不能静默补齐；
3. HTML、JSON、Agent payload 和 confirmation request 使用同一 semantic payload；
4. 对 `confirmable` 只生成一个 hash-bound 确认入口；
5. 对 `preview`、`blocked`、`stale`、身份缺失和测试 showcase 禁止确认；
6. 在英文/中文人工确认文档中写清一阶段一条原子路线、多 claim 整单处理和后续恢复边界。

交付：summary v3 schema、v1/v2 只读兼容、人工确认文档、Agent contract、浏览器验收和 v0.38.0 release candidate。

### M5：跨副本发布与正式放行

执行：

1. 同步源码、wheel 资源、Codex/Claude Skill、schema registry、CLI reference、release manifest 和文档；
2. 运行反硬编码审计、schema parity、CLI contract、Ruff、compileall 和全量 pytest；
3. 在干净、无项目依赖污染的 CI 环境中构建并安装 wheel；
4. 运行五域 release fixture、失败 fixture、迁移 fixture 和六阶段 HTML 浏览器检查；
5. 记录跨平台结果和可复现的 release manifest；
6. 只有全部证据满足放行条件，才创建正式 tag/release。

## 7. 错误后的统一恢复路由

| 状态 | 框架含义 | 默认恢复动作 | 是否重新打开科学 checkpoint |
|---|---|---|---|
| `presentation_only` | 兼容展示文件 | 从 canonical evidence 重建 | 否 |
| `legacy_unqualified` | 旧文件缺少完整身份 | 只读审计，等待用户补充或重跑 | 通常是 |
| `same_identity_value_conflict` | 同一身份确有不同值 | 核对来源、重建或重跑 | 若结果/方法变化则是 |
| `different_identity_non_comparable` | 不同模型、任务、cohort、验证或分母 | 拆分展示，禁止直接排名 | 主论断涉及时是 |
| `missing_required_identity` | 主证据缺字段 | 修复 adapter 或重新生成 evidence | 可能是 |
| `stale_source` | 输入、代码、图像或 run 已变化 | derived rebuild 或回到 active bundle | 改变科学合同时是 |
| `failed_candidate_bundle` | 新运行失败 | 保留旧 active，修复 candidate | 否，除非科学合同变化 |
| `blocked` | 证据不足或路线未选 | 按页面给出的唯一恢复路线处理 | 依状态决定 |

框架不能用“让页面变绿”代替恢复。恢复动作必须说明修改的是派生产物、运行证据、数据/方法合同还是研究蓝图。

## 8. 文件和资源实施清单

### 8.1 已有核心实现

- `draftpaper_cli/checkpoint_digest.py`：阶段作用域、完整产物、identity-first 摘要和 sample-flow；
- `draftpaper_cli/checkpoint_summary.py`：阶段 summary、preview 和旧版本读取；
- `draftpaper_cli/checkpoint_html.py`：中文 HTML、身份卡、路径、状态和产物展示；
- `draftpaper_cli/result_evidence.py`、`result_support.py`、`result_support_signals.py`：指标身份、比较和 gate；
- `draftpaper_cli/evidence_registry.py`、`evidence_identity.py`、`evidence_audit.py`：typed bridge 和只读审计；
- `draftpaper_cli/run_evidence_bundle.py`：运行事务生命周期；
- `draftpaper_cli/code_ownership.py`：FigureCodeTrace v2；
- `draftpaper_cli/orchestrator.py`、`doctor.py`、`runtime_handshake.py`：门禁、诊断和漂移处理；
- `tools/generate_checkpoint_html_showcase.py`：匿名六阶段 showcase；
- `tests/test_checkpoint_html_showcase.py`：showcase 状态和内容回归。

### 8.2 下一步新增或升级

- `draftpaper_cli/resources/schemas/checkpoint_summary_v3.json`；
- `draftpaper_cli/resources/schemas/schema_registry.json`：current/accepted/migration 状态；
- `draftpaper_cli/release_contract.py`、`resources/release_manifest.json`：版本和资源 parity；
- `docs/human_checkpoints.zh-CN.md` 与英文版：完整阶段包和人工确认边界；
- `docs/cli_reference.md`、`docs/command_risk_matrix.md`：新命令、读写风险和确认资格；
- 匿名 scope/反硬编码测试、v3 summary 测试、clean wheel 安装测试和浏览器验收记录。

禁止通过手工修改 `project.json`、stage manifest、passport、ledger、active pointer 或 evidence snapshot 绕过上述流程。

## 9. 测试和发布验收矩阵

### 9.1 必测反例

- 同一指标身份但数值不同：`same_identity_value_conflict`；
- 同名指标但模型、任务、验证设计或 cohort 不同：`non_comparable`；
- 多 seed 没有聚合合同：阻断；
- primary metric 为空或匹配多条：阻断；
- catalog rows、unique entities、processed entities 和 model groups：形成不同 CountEvidence 节点；
- 同名旧图、当前图、缓存图和历史 HTML：只收当前 stage-owned 当前 bundle；
- 代码、输入或图像 hash 变化：trace stale；
- 缺少身份的 v1/v2 文件：只读 legacy，不得确认；
- `result_support` 有互斥路线但用户未选：blocked；
- 测试 showcase 有 `test_auto_confirmation=true`：不能污染真实状态。

### 9.2 发布前命令

```powershell
python -m ruff check draftpaper_cli tests
python -m compileall -q draftpaper_cli
python -m pytest tests/test_metric_identity.py tests/test_count_identity.py tests/test_evidence_comparison.py -q
python -m pytest tests/test_run_evidence_bundle.py tests/test_checkpoint_digest.py tests/test_checkpoint_summary.py -q
python -m pytest tests/test_checkpoint_html_showcase.py tests/test_strict_checkpoint_html.py -q
python -m build
```

随后还必须在 CI 中执行：

- 全量 `pytest` 并保留最终汇总；
- 干净环境 wheel 安装和 CLI smoke；
- schema registry、release manifest、Skill 副本和 CLI reference parity；
- 匿名五域 release fixture、迁移 fixture 和反例回归；
- 六阶段 HTML 的离线、UTF-8、长路径、响应式和敏感信息检查；
- 正式 tag/release 的跨平台验收。

重点测试通过不能代替全量回归；系统依赖隔离安装通过也不能代替 CI 中真正无外部依赖污染的 wheel 安装。

## 10. 人工确认点设计

每个阶段只保留一个主要确认点，进入确认点之前机器必须完成证据审计并生成完整阶段包：

```text
机器生成/运行
→ evidence identity audit
→ artifact、trace、hash 和 freshness validation
→ 中文 stage_summary HTML
→ Agent 返回项目相对路径和本机绝对路径
→ 用户一次性审阅本阶段完整成果
→ hash-bound confirm / refine / reject
```

Agent 必须用一段中文话说明本阶段做了什么，再列出完整产物和未解决问题。不能只输出一个 hash，也不能把内部路径当作内容摘要。`confirmable` 只表示机器合同通过，不表示用户已经确认科学含义。

真实科研项目的人工确认必须由用户完成；匿名 fixture 可以在测试模式下跳过人工动作，但任何自动化路径都不得把测试标记复制到真实项目。

## 11. 最终放行条件

Draftpaper-loop 框架级优化只有同时满足下列条件才可宣布完成：

1. 真实项目观察已全部转化为匿名、跨学科的公共失败模式；
2. 核心代码和默认 schema 没有论文项目特判；
3. 所有正式指标、计数、运行和图表都有可验证身份；
4. 所有聚合和比较都由声明式合同控制；
5. 阶段摘要只读取当前 stage-owned active bundle，并列出完整生成内容；
6. HTML、JSON、Agent payload、CLI 和 ledger 同源；
7. `blocked`、`stale`、`preview`、`legacy_unqualified` 和身份缺失状态不能确认；
8. 旧项目迁移只做可证明的映射，不能猜测科学语义；
9. 匿名 fixture、真实项目只读回归、全量 pytest、干净 wheel 安装、Skill/schema parity 和浏览器验收全部有记录；
10. 正式 tag/release 已由发布清单锁定；
11. 没有任何自动化路径替用户确认研究蓝图、核心证据、最终稿件或科学结论。

## 12. 不在本方案范围内

- 不修改具体论文项目的科学结果、图表和正文；
- 不自动选择多条科学路线；
- 不为某个学科写入核心默认字段、阈值或模型名称；
- 不把真实项目数据、日志、对象 ID 或私有路径提交到公共测试；
- 不因摘要页面改进而重新训练模型或重新生成真实论文图表；
- 不设计商业化、许可证、会员或付费插件；
- 不以 fixture、mock、preview、compatibility 或历史文件冒充正式科研证据。

## 13. 推荐执行顺序和交付物

执行顺序固定为：

```text
确认框架范围与匿名 fixture
→ 发布 M0 反特判测试
→ 收口 v0.37.1 证据身份和计数合同
→ 收口 v0.37.2 运行事务和图表 trace
→ 实现 checkpoint summary v3
→ 同步 HTML、Agent、CLI、Skill、schema 和 manifest
→ 全量测试与干净 wheel 安装
→ 跨平台和浏览器验收
→ 创建正式 tag/release
```

最终交付物：

1. 更新后的框架级方案和边界说明；
2. 证据身份、计数、聚合、运行、图表和 comparison schema；
3. identity-first resolver、active bundle gate、stage digest 和 summary v3；
4. 中文/英文人工确认文档和恢复路线文档；
5. 匿名跨学科 fixture、六阶段 HTML showcase 和测试报告；
6. schema/Skill/wheel/CLI/release manifest parity 报告；
7. 全量 pytest、CI wheel、跨平台和浏览器验收记录；
8. v0.37.1、v0.37.2 和 v0.38.0 release notes。

这份方案的完成标准不是某一篇论文的页面不再报警，而是任何学科、任何项目都必须在证据进入 Result Support、图表追踪和人工确认之前，明确判断：它是否是同一指标、同一分母、同一运行、同一图表来源，以及应当走派生重建、方法重跑、数据修复还是重新打开科学 checkpoint。
