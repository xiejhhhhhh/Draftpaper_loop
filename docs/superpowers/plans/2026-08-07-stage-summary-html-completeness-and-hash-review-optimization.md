# Draftpaper-loop 阶段总结、证据身份与人工确认框架完整优化执行方案

## 1. 文档定位

- 初版日期：2026-08-07
- 框架级修订日期：2026-08-11
- 当前实现基线：Draftpaper-loop v0.37.0
- 适用范围：全部学科、全部论文项目、全部人工确认阶段
- 目标版本：v0.37.1 完成证据身份正确性热修，v0.37.2 完成运行事务与图表追踪，v0.38.0 完成全流程严格发布
- 重点回归材料：匿名跨学科 fixture 加一个只读真实项目回归案例
- 回归材料角色：只用于复现失败模式和验证迁移路径，不作为框架逻辑、字段名、阈值、样本数或学科结论的硬编码来源
- 本文性质：Draftpaper-loop 通用架构优化、实施顺序、测试合同和发布验收标准

本方案取代此前“主要围绕单篇论文修复 HTML”的理解。单篇论文暴露的问题只用于提炼通用约束；正式实现必须作用于 Draftpaper-loop 的 schema、证据解析、运行事务、artifact DAG、checkpoint、Agent 和 HTML 合同。

## 2. 核心结论

当前阶段摘要 HTML 的信息完整性、可读性和人工门禁已经得到明显改善，工作树也已经开始把错误阻断前移到证据层，但框架尚未完成正式发布。v0.37.0 基线以及旧项目产物曾允许以下错误进入证据链；本方案把它们定义为必须由公共合同阻断的失败模式：

1. 单个 seed 指标与多 seed 均值使用同一个指标名称；
2. 不同模型、任务、验证设计和 split 的指标被聚合或互相比较；
3. 原始目录行数、唯一对象数、合格样本数和建模样本数统一写成 `source_rows`；
4. 图表、指标、数据绑定和 result support 来自不同生成事务，却被目录扫描汇总到同一 checkpoint；
5. 兼容输出被误当成正式科研证据；
6. 旧 figure trace 没有绑定当前图像 hash、run、cohort 和数据分母；
7. 摘要比较器只按裸字段名比较数值，没有先判断两个证据是否可比。

因此，后续优化重点必须从“HTML 展示更多内容”升级为“证据在进入 HTML 前已经具备严格身份”。HTML 继续作为用户审阅视图，但不能承担修复上游证据语义的职责。

### 2.1 本轮问题的框架级约束映射

下面的映射用于防止本方案再次被误读为“修复某个论文项目的几个文件”。回归项目只提供失败样本；约束必须进入 Draftpaper-loop 的公共 schema、resolver、运行事务、checkpoint gate 和跨学科测试。

| 已观察到的现象 | 框架层面的错误 | 必须增加的公共约束 | 最早阻断位置 | 允许的恢复路线 |
|---|---|---|---|---|
| `metrics.csv` 与 `result_support_checkpoint` 指标不一致 | 兼容 CSV、单 seed 记录和多 seed 汇总被当成同一主指标 | `MetricEvidence` 完整身份、`AggregationContract`、`PrimaryMetricContract`；兼容输出只能单向派生且默认 `presentation_only` | result-evidence resolver / result-support gate | 若 canonical 结果已有，重建派生文件；若统计设计或训练结果变化，重跑方法阶段 |
| `figure_code_trace.source_rows=1671`，当前建模数据为 1229 | 不同实体类型、去重状态和 cohort 分母共用一个裸字段 | `CountEvidence` 声明 `entity_type`、`count_mode`、filter/cohort、parent relation；sample-flow 显式展示各分母 | count identity audit / figure trace validator | 已有事实可证明时重建 count/trace；无法证明时数据核验或重新生成 cohort |
| 旧 figure trace 与新图像、代码或输入混用 | 图表追踪不是当前运行的原子产物 | `FigureCodeTrace v2` 绑定图像、metadata、代码、输入、run、cohort、metric/count refs 和 transaction hash | active bundle / stale propagation gate | derived rebuild；涉及图义、样本或论断时重开科学 checkpoint |
| 新旧指标、图表和 result support 被目录扫描拼在一起 | 文件存在被错误当成同一科学运行 | `RunEvidenceBundle` 的 candidate/active/superseded 生命周期与原子 active pointer | run bundle promotion gate | 失败 candidate 丢弃或修复，不覆盖 active bundle |
| 页面能列出文件却不能说明本阶段做了什么 | 展示层缺少确定性成果清单和用户语义 | stage digest 从 active bundle 生成中文单段总结、完整产物清单、hash/状态/边界和恢复建议 | stage-summary generation gate | 重建摘要 HTML，不改变科学证据 |
| Agent 或用户把“不可比较”当成数值冲突 | 比较器先比数值、后补语义 | `EvidenceComparisonResult` 先判 identity，再判 value；区分 conflict、non-comparable、missing、stale | checkpoint comparison gate | 依据状态选择派生修复、方法重跑或科学确认 |

这些约束不允许写入任何单篇论文的路径、模型名、样本数、列名或学科阈值。学科插件只能通过公共 adapter 声明其实体类型、验证设计、指标定义和聚合合同；核心框架负责验证身份、可比性、事务完整性和确认资格。

### 2.3 框架层面禁止项目特判与论文项目反向驱动

本轮问题来自某个论文项目的阶段页面和结果文件，但修复对象只能是
Draftpaper-loop 的公共框架。为防止“把论文项目修好”再次被误写成“框架已经修好”，所有后续实现必须同时满足以下边界：

1. **项目事实与框架规则分离**：真实项目中的路径、模型名、列名、样本量、阈值、图号和科学论断只能进入 project-local adapter、运行 manifest 或匿名 fixture，不能进入核心 resolver、schema 默认值、HTML 模板或 CLI 分支。
2. **匿名 fixture 先行**：每个来自真实项目的失败模式都必须先被压缩为最小匿名 fixture，例如 `model_a`、`design_a`、`entity` 和通用指标；只有匿名 fixture 能稳定复现并被跨学科测试覆盖后，才允许修改公共代码。
3. **学科差异走插件合同**：天文、医学、社会科学等领域的实体、样本单位、标签和统计口径由插件声明，核心只验证声明是否完整、身份是否一致和结果是否可比；核心代码不得导入某一学科的字段词汇来绕过缺失合同。
4. **阶段作用域由公共注册表控制**：阶段摘要只读取当前 stage-owned 的目录和已登记的产物，不对整个项目目录递归猜测“最新文件”，也不把 `review/checkpoints`、历史页面、缓存或失败 candidate 误收进当前阶段。
5. **HTML 不创造科学事实**：HTML、Agent payload、compatibility CSV 和写作上下文只能从 canonical evidence 和确定性 digest 单向派生；模型不能凭文件名、第一行、最大值或自然语言补全缺失的指标、分母和运行身份。
6. **展示测试不触碰真实项目**：HTML showcase 必须在临时匿名项目中生成，并带有 `test_auto_confirmation=true`；该标志只允许测试代码跳过人工动作，不能写入真实项目、ledger、active pointer 或确认记录。
7. **问题晋升有证据门槛**：无法被匿名 fixture 复现的项目特例，不能直接变成核心规则；只能记录为项目级适配请求，等待通用合同定义或明确拒绝进入核心。
8. **发布前做反硬编码审计**：静态检查、schema parity 和跨学科 fixture 必须验证核心代码、资源、Skill 副本和文档没有用户专属绝对路径、真实项目标识、科学数字或项目专用阈值。

因此，本文件中出现的失败现象只代表“框架应当能够阻断的匿名化问题类型”。它们不授权后续工作直接编辑任何真实论文项目，也不代表真实项目的结果、图表或科学论断已经被框架确认。

### 2.2 已完成能力与尚未完成能力的边界

当前工作树已经把 Metric、Count、Run 和 Figure 的身份检查前移到结果解析、result support 和 checkpoint digest，并通过匿名严格 fixture 验证了主要阻断路径；这些改动仍属于未发布的 v0.37.x 工作树，不能等同于已经完成正式版本发布。阶段 HTML 也已经能够展示身份卡、sample-flow、完整产物和阻断状态，但它仍是证据审阅视图，不负责从多个来源中选择“更可信”的数字。

本轮框架实现已经覆盖 typed evidence bridge、`evidence_identity_audit_v1` schema、只读 `audit-evidence-identity` CLI、RunEvidenceBundle、FigureCodeTrace v2、严格阶段 HTML、测试模式标记、四份 workflow Skill/contract 副本同步、228 条 CLI 合同和 release manifest。分组全量 pytest 已稳定完成，累计 `1179 passed, 2 skipped`；wheel 安装矩阵、重建后的隔离 wheel 安装、五域 release fixture、反例和语义回归也已通过。尚未完成的是正式版本 tag/release、CI 中的跨平台发布验收和最终发布回归。当前准确表述应是“框架级证据身份和严格 HTML 已在工作树实现并通过重点、分组全量及发布候选验证，仍待正式 release 放行”。

## 3. 优化目标

### 3.1 用户目标

用户打开一个 `stage_summary.zh-CN.html` 后，应当在 30 秒内了解：

1. 本阶段围绕什么科研目标完成了哪些工作；
2. 形成了哪些图表、文字、代码、数据表、运行证据和审查报告；
3. 当前主结果属于哪个任务、模型、cohort、验证设计和统计汇总口径；
4. 页面中的每个样本数究竟在数什么；
5. 哪些差异是真冲突，哪些只是不同口径而不能直接比较；
6. 哪些验证已通过，哪些问题会阻止哈希确认；
7. 确认将冻结什么证据身份并解锁哪个下游阶段。

### 3.2 框架目标

Draftpaper-loop 必须做到：

- 先构建结构化证据身份，再生成摘要和正文；
- 只有完整身份相同的指标或计数才能进行一致性比较；
- 所有聚合都由预先声明的统计合同控制，禁止隐式求均值；
- 一次科学运行的正式产物以原子证据包发布；
- compatibility、preview、fixture 和历史文件不能冒充正式证据；
- stale、blocked、identity-missing 和 preview 页面不能用于确认；
- 框架修复与科学合同变更使用不同恢复路线，避免无意义地重开研究蓝图；
- 所有规则跨学科成立，不依赖 astronomy、AGN/XRB、source 或 F1 等项目词汇。

## 4. 当前已完成的框架级优化

以下状态针对 Draftpaper-loop 工作树，而不是任何一篇论文项目。状态“工作树已实现”表示代码和针对性测试已经存在，但尚未代表新的正式 release；后续发布必须再次通过全量测试、wheel 安装和资源副本一致性检查。

| 能力 | 当前状态 | 主要实现或证据 |
|---|---|---|
| 完整成果与事务变化分离 | 已完成 | `checkpoint_digest.py` 的 `stage_deliverables` 与 `transaction_changes` |
| 中文单段阶段总结 | 已完成 | 确定性 digest，不允许 LLM 自由编造数值 |
| 图表、表格、代码、报告、运行证据分组 | 已完成 | summary 与 HTML renderer |
| 图像缩略图、caption、解释和代码映射 | 已完成 | `checkpoint_html.py` 与通用图表上下文 |
| CSV 受限预览 | 已完成 | 页面不嵌入完整大型预测表 |
| stale/blocked/preview 隐藏确认命令 | 已完成 | `review_state` 与 confirmation gate |
| preview 不污染 ledger/latest pointer | 已完成 | `preview-checkpoint-summary` 派生包 |
| latest pointer 优先级 | 已完成 | latest pointer → index → legacy ledger |
| 路径逃逸和外部绝对路径拒绝 | 已完成 | project-root relative path 约束 |
| runtime identity 受控迁移 | 已完成 | `session-preflight --accept-runtime-update` 与 migration receipt |
| 只读诊断无副作用 | 已完成 | `verify-next-action` 不再创建 checkpoint |
| Result Support 双路线展示 | 已完成 | 路线可见但不替用户选择 |
| 全部人工确认阶段通用摘要适配 | 已完成 | research plan、data、methods、plugin、writing、quality 等 |
| 桌面与移动端布局 | 已完成 | 长路径、hash、run ID 和表格不再撑破容器 |
| v1/v2 checkpoint 只读兼容 | 已完成 | 不覆盖旧 hash 和历史记录 |
| `MetricEvidence` 与 evidence context | 已实现（待 release） | `evidence_identity.py`、`result_evidence.py`、typed evidence bridge 和 `metric_evidence_v3` |
| `AggregationContract` 与唯一主指标解析 | 已实现（待 release） | 禁止无合同跨 seed/fold 聚合；primary 不再取第一行或最大值 |
| `CountEvidence` 与 sample-flow | 已实现（待 release） | 分离实体类型、计数方式、cohort 和父子关系 |
| `RunEvidenceBundle` 生命周期 | 已实现（待 release） | candidate/validated/active/failed/superseded；失败运行不覆盖 active |
| `FigureCodeTrace v2` | 已实现（待 release） | 图像、metadata、代码、输入、run transaction 和 metric/count refs 绑定 |
| identity-first 比较与 result-support 阻断 | 已实现（待 release） | 区分 conflict、non-comparable、missing identity 和 stale |
| 阶段作用域与完整产物发现 | 已完成（待 release） | `checkpoint_digest.py` 的统一 `STAGE_SCOPE_PREFIXES`；排除 checkpoint、历史页面和递归产物，按阶段列出实际相对路径 |
| 严格阶段 HTML fixture | 已实现（待 release） | 20 条证据/HTML/v3 合同测试通过，含完整产物、身份卡、sample-flow、阻断路线和测试模式警告 |
| 六阶段匿名 HTML showcase | 已生成并通过浏览器验收（待 release） | `tools/generate_checkpoint_html_showcase.py`；仅使用匿名 fixture，覆盖 research plan、data、methods、result support、core evidence 和 quality checks |
| `checkpoint_summary.v3` 与同源确认包 | 工作树已实现（待 release） | v3 schema、v1/v2 只读 legacy、缺字段阻断、HTML/JSON/Agent 同源和 confirmation contract |

当前工作树验证结果：

- 新增证据身份、运行事务、图表追踪、严格 HTML 和 v3 合同重点测试：`20 passed`；
- 证据身份、运行事务、checkpoint、HTML、result support 和 runtime 联合回归：`65 passed`；
- 已完成的分组回归还包括 A 组 `142 passed`、B 组 `194 passed`、C 组 `391 passed`、D 组 `443 passed`；
- `python -m ruff check draftpaper_cli tests`、`python -m compileall -q draftpaper_cli`、`validate-command-contracts` 和 `release_contract --write`：通过；
- wheel `dist/draftpaper_cli-0.37.0-py3-none-any.whl` 已构建；安装矩阵通过；使用系统依赖隔离环境安装 wheel 后，五个跨学科 release fixture、反例回归和语义回归均为 `passed`；
- `audit-evidence-identity` 对含 legacy compatibility 记录的匿名 fixture 返回 `needs_review`、`read_only=true`、`writes_performed=[]`，这是预期的安全结果，不是自动迁移或确认；
- 匿名六阶段 showcase 已验证：`research_plan`、`data`、`methods`、`core_evidence` 和 `quality_checks` 为 `confirmable` 展示，`result_support` 因两条互斥路线而为 `blocked`；所有页面均显式记录 `test_auto_confirmation=true`，不改变真实科研状态；
- 分组全量 pytest 已完成：`1179 passed, 2 skipped`，总耗时约 18 分钟；此前单进程超时仅作为执行方式限制保留在临时日志中，不再作为测试结论。
- 重建后的 `dist/draftpaper_cli-0.37.0-py3-none-any.whl` 已在临时隔离环境中安装，并完成五个跨学科 release fixture、身份反例、图表/引用语义反例回归；`verify_wheel_install.py` 返回通过。可选 OCR 依赖的安装已成功，不再构成本轮 wheel 验证阻塞。

仍未在本轮最终放行中完成的项目是：CI 中的跨平台 wheel/源码发布验收、正式 release/tag 和跨平台发布回归。`checkpoint_summary.v3` 已是当前生产工作树合同，v1/v2 仅保留为只读 legacy；typed evidence registry、`audit-evidence-identity`、阶段作用域发现、匿名 showcase、Skill/wheel/Claude/Codex 副本 parity 和 release manifest 均已进入工作树并完成验证，不应再列为“尚未实现”。

## 5. 失败模式与框架级根因

本节记录的是从回归材料中抽象出的“修复前失败模式”和对应的公共约束。文中的“当前/原有实现”指 v0.37.0 基线或旧项目遗留产物，不表示本轮工作树已经完成正式发布。任何修复都必须进入公共 resolver、schema、运行事务、checkpoint gate 和跨学科测试，不能通过为某个项目增加特判来消除页面上的报错。

### 5.1 compatibility 指标输出错误折叠重复运行

项目级分析代码可能把多行模型结果压缩成一个兼容 `metrics.csv`。当前已观察到的通用失败模式是：筛选某个模型后直接取第一行，导致第一 seed 被写成“主指标”。

框架问题不在具体数值，而在于 compatibility 文件没有声明：

- 模型；
- validation design；
- split；
- seed/fold/repetition；
- reducer；
- metric definition；
- run 和 cohort。

只包含 `metric,value` 的文件不得继续拥有正式证据资格。

### 5.2 evidence resolver 对统计维度识别不完整

当前 `result_evidence.py` 只识别 `split` 和 `split_type`，不能把常见的 `validation_design`、`evaluation_design`、`holdout_scheme` 等字段归一化为验证维度。seed、fold、重复划分和外部测试集也没有统一 replicate contract。

结果是不同验证设计可能被放入同一分组并自动求均值。此类均值在数学上可计算，但没有对应的科学 estimand，不能作为论文结果。

### 5.3 primary metric 选择仍带推断和数值排序

当 `primary_model_id` 或完整上下文缺失时，解析器可能从“full、main、primary、proposed”等名称推断模型，随后按优先级和数值选择记录。

正式主指标必须来自研究蓝图和 method requirements 的精确合同，不得通过模型名称猜测，更不得因为某个数值更高而成为 primary。

### 5.4 裸计数字段没有分母身份

`source_rows`、`sample_count`、`n` 等名称无法区分：

- 原始目录行数；
- 去重后的唯一实体数；
- 质量筛选后的合格实体数；
- 特征构建成功数；
- 建模 sample group 数；
- train/validation/test 数；
- event、visit、cutout、patient、site、tile 或 object 数。

两个不同分母的数值不应该被判定为互相矛盾，但也不能在正文中互换。

### 5.5 图表追踪不是当前运行的强绑定产物

当前 `figure_code_trace.json` 可以列出图表和代码，但未强制包含：

- 当前 figure byte/semantic hash；
- figure metadata hash；
- producer code hash；
- run、cohort、plan 和 snapshot；
- metric identity refs；
- count identity refs；
- input artifact hashes；
- generation transaction ID。

因此，重画图表或重跑模型后，旧 trace 仍可能存在并被摘要层读取。

### 5.6 文件生成不是原子科学事务

同一个 `results/` 目录中可能同时存在：

- 新指标；
- 旧 compatibility summary；
- 新 figure metadata；
- 旧 figure trace；
- 新 result support；
- 更早的 resolved evidence。

目录存在不等于这些文件属于同一科学运行。当前 artifact DAG 和 run manifest 尚未形成“只有完整事务成功后才切换 active evidence set”的强约束。

### 5.7 checkpoint 比较器先比较数值，后补语义

当前摘要层会按 `metric_name` 或 `source_rows` 查找交集并比较第一条数值。正确顺序应当是：

1. 解析双方完整 identity；
2. 判定是否属于同一 estimand；
3. 只有 identity 相同时才比较数值；
4. identity 不同时标记 `non_comparable`，而不是 `conflict`；
5. identity 缺失且该证据参与主论断时，标记 `blocked_missing_identity`。

### 5.8 schema 只约束顶层存在，未约束科学语义

当前 checkpoint v2 schema 主要要求顶层数组存在，并允许大量 `additionalProperties`。它尚未对 metric、count、figure trace 和 confirmation identity 的嵌套字段进行严格验证。

因此，JSON 可以通过 schema，却仍然缺少足以判断科学可比性的字段。

## 6. 框架不变量

后续实现必须把以下规则写入 schema、运行时和测试，而不是只写进文档。

1. **证据不是裸数值**：任何主指标和关键样本数都必须是带完整 identity 的结构化记录。
2. **先判定可比性**：只有 comparability key 完全匹配时才允许比较数值。
3. **禁止隐式聚合**：没有 aggregation contract 时，不得跨 seed、fold、时间、站点、split 或 validation design 求均值。
4. **主指标唯一解析**：primary metric contract 必须解析为恰好一条正式记录；零条或多条都阻断。
5. **兼容输出只做展示**：compatibility 文件默认 `evidence_role=presentation_only`，不能进入 result support、claim support 或 checkpoint 主结论。
6. **计数必须声明分母**：`source_rows`、`n`、`count` 等无限定字段不能直接晋升为核心证据。
7. **一次运行一个 active evidence set**：正式证据必须属于同一成功运行事务。
8. **派生产物必须可重建**：figure trace、HTML、compatibility summary 和写作上下文不能成为第二套科学真相。
9. **过期即阻断**：任何输入、代码、图像或 metadata hash 变化都使依赖 trace 和 checkpoint stale。
10. **修框架不等于改科学合同**：只修身份字段、derived trace 或展示逻辑时走 derived rebuild；只有数据纳入规则、方法、统计设计、主图或论断变化才重开研究蓝图。
11. **人工确认不可代理**：机器验证通过后才出现唯一 hash-bound 确认命令，Agent 不替用户确认。
12. **跨学科中立**：实体可以是 source、galaxy、patient、site、plot、document 或 sample；框架不得硬编码单一学科术语。

## 7. 目标证据合同

### 7.1 公共 `EvidenceContext v1`

所有 metric、count、figure 和 claim evidence 共享以下上下文：

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

`validation_design_id` 由 normalized contract 产生，原始列名只能作为 provenance，不能直接成为比较键。

### 7.2 `MetricEvidence v3`

```json
{
  "schema_version": "dpl.metric_evidence.v3",
  "metric_record_id": "...",
  "metric_definition_id": "macro_f1:binary:macro",
  "metric_family": "f1",
  "value": 0.0,
  "direction": "higher_is_better",
  "model_id": "...",
  "target_id": "...",
  "context": {},
  "replicate_axis": "seed | fold | repeated_split | site | none",
  "replicate_ids": [],
  "aggregation_id": "none | arithmetic_mean | median | pooled_prediction | declared_custom",
  "aggregation_source_refs": [],
  "n_replicates": 1,
  "uncertainty_definition_id": "...",
  "lower": null,
  "upper": null,
  "source_artifact": "...",
  "source_sha256": "...",
  "producer_id": "...",
  "producer_version": "...",
  "evidence_role": "primary | secondary | sensitivity | presentation_only"
}
```

Metric comparability key 至少包含：

```text
plan_hash
run_id
dataset_id
cohort_id
task_id
sample_unit
model_id
target_id
validation_design_id
split_id
metric_definition_id
aggregation_id
uncertainty_definition_id
```

seed-level 记录与 seed-mean 记录不是同一 identity。它们可以建立 parent/aggregate 关系，但不得被当成两个来源对同一数值的重复证明。

### 7.3 `AggregationContract v1`

```json
{
  "schema_version": "dpl.aggregation_contract.v1",
  "aggregation_id": "...",
  "input_record_selector": {},
  "replicate_axis": "seed",
  "required_replicate_ids": [101, 202, 303],
  "reducer": "arithmetic_mean",
  "missing_replicate_policy": "block",
  "weighting": "uniform",
  "output_metric_definition_id": "..."
}
```

要求：

- validation design、model、task、cohort 和 split 不得作为隐式 replicate 轴；
- 多个 split 的 pooled 结果必须从 pooled predictions 重新计算，不能简单平均；
- fold mean、seed mean、重复划分 mean 和跨站点 meta-analysis 必须使用不同 aggregation ID；
- reducer 缺失时保留逐条记录，不自动生成 aggregate。

### 7.4 `PrimaryMetricContract v1`

研究蓝图和 method requirements 必须明确：

```json
{
  "metric_definition_id": "...",
  "model_id": "...",
  "task_id": "...",
  "cohort_id": "...",
  "validation_design_id": "...",
  "split_id": "...",
  "sample_unit": "...",
  "aggregation_id": "...",
  "uncertainty_definition_id": "..."
}
```

resolver 必须精确匹配该合同：

- 恰好一条：通过；
- 零条：`blocked_missing_primary_metric`；
- 多条：`blocked_ambiguous_primary_metric`；
- 禁止通过模型名称、文件名或最大数值自动选择。

### 7.5 `CountEvidence v1`

```json
{
  "schema_version": "dpl.count_evidence.v1",
  "count_record_id": "...",
  "count_definition_id": "...",
  "entity_type": "source | object | patient | visit | event | cutout | tile | site | row | sample_group",
  "count_mode": "rows | unique_entities | eligible_entities | successful_entities | split_members",
  "value": 0,
  "context": {},
  "filter_contract_id": "...",
  "grouping_key_id": "...",
  "parent_count_record_id": null,
  "exclusion_reason_table_ref": null,
  "source_artifact": "...",
  "source_sha256": "...",
  "evidence_role": "sample_flow | model_cohort | split_count | presentation_only"
}
```

建议的通用 count definitions：

- `catalog_row_count`；
- `catalog_unique_entity_count`；
- `identified_entity_count`；
- `eligible_entity_count`；
- `processed_entity_count`；
- `feature_complete_entity_count`；
- `model_sample_group_count`；
- `model_unique_entity_count`；
- `train_entity_count`；
- `validation_entity_count`；
- `test_entity_count`；
- `event_count`；
- `successful_fit_count`；
- `released_product_count`。

不同 count definition 的数值进入 sample-flow 关系，不进入 equality conflict。只有完整 CountIdentity 相同而 value 不同时才是冲突。

### 7.6 `RunEvidenceBundle v1`

一次正式运行完成后生成：

```json
{
  "schema_version": "dpl.run_evidence_bundle.v1",
  "run_transaction_id": "...",
  "run_id": "...",
  "status": "candidate | validated | active | failed | superseded",
  "context": {},
  "producer_fingerprint": {},
  "input_artifacts": [],
  "output_artifacts": [],
  "metric_record_refs": [],
  "count_record_refs": [],
  "figure_trace_refs": [],
  "validation_receipts": [],
  "bundle_sha256": "..."
}
```

运行事务规则：

1. 所有输出先写入 candidate bundle；
2. 运行、schema、hash、统计合同和图表验证全部通过后，原子切换 active bundle pointer；
3. 失败或中断时不得部分覆盖 active bundle；
4. 旧 bundle 保留为 superseded，不删除、不混入新 checkpoint；
5. checkpoint 只能消费一个 active bundle 或明确声明的多 bundle comparison contract。

### 7.7 `FigureCodeTrace v2`

每个主图必须记录：

- figure ID、PNG/PDF hash 和 semantic hash；
- figure metadata hash；
- producer code paths 和 code hashes；
- input artifact hashes；
- run/plan/cohort/snapshot/transaction identity；
- metric record refs；
- count record refs；
- caption contract 和 panel contract refs；
- generated_at 和 producer fingerprint。

任意 figure hash、metadata hash 或 producer hash 变化时，trace 自动 stale。摘要层不得回退读取无 identity 的旧 trace 并把它显示为当前证据。

### 7.8 `EvidenceComparisonResult v1`

比较结果必须区分：

| 状态 | 含义 | 是否阻断 |
|---|---|---:|
| `same_identity_same_value` | 同一证据身份且数值一致 | 否 |
| `same_identity_value_conflict` | 同一身份但数值不同 | 是 |
| `different_identity_non_comparable` | 模型、cohort、split、reducer 或分母不同 | 默认否，主结论误用时阻断 |
| `parent_aggregate_relation` | seed/fold 与其声明式 aggregate | 否 |
| `missing_required_identity` | 主证据缺少必要身份字段 | 是 |
| `stale_source` | 来源 hash 或 run transaction 已过期 | 是 |
| `presentation_only_ignored` | 兼容输出不参与科学判断 | 否 |

比较器不得再返回模糊的“两个数值不一致”而不说明两者是否本应相等。

## 8. 框架处理流程

### 8.1 数据与方法执行前

1. 研究蓝图冻结 PrimaryMetricContract、CountDefinitions 和必要 sample-flow；
2. method blueprint 冻结 validation design、split、replicate axis 和 aggregation；
3. executable analysis spec 绑定 task、target、model 和 cohort；
4. 缺少任何主证据身份字段时，不允许进入关键图表执行。

### 8.2 方法运行和结果生成

1. 创建 candidate RunEvidenceBundle；
2. 方法代码只能向该 candidate bundle 注册输出；
3. metric adapter 规范化列名，但不猜测缺失的科学语义；
4. count adapter 生成 sample-flow records；
5. aggregation engine 只执行已确认合同；
6. figure generator 引用 metric/count record IDs；
7. bundle 验证成功后原子晋升为 active。

### 8.3 Result Evidence 与 Result Support

`resolve-result-evidence` 应当：

- 只读取 active RunEvidenceBundle；
- 识别 `validation_design` 等标准别名并写入规范 ID；
- 不跨 validation design 聚合；
- 不把 seed 当 fold，也不把 split 当 seed；
- 不读取 `presentation_only` compatibility 文件；
- 按 PrimaryMetricContract 精确解析唯一主指标；
- 输出 typed metric/count records 和 comparison receipts。

`assess-result-support` 应当：

- 使用 metric record ID，而不是从大字典中猜 key；
- 每条 claim 显式绑定 metric/count/figure evidence refs；
- 不生成跨模型的通用 `primary_macro_f1` 别名；
- 不用最高分指标替换预先声明的主模型；
- 将不同验证设计作为独立 evidence view 展示。

### 8.4 图表追踪与派生产物

`trace-figures-to-code` 应在当前 active bundle 和当前图像生成完成后运行，输出 v2 trace。`rebuild-derived` 可以重建 trace、HTML、compatibility summary 和写作上下文，但不得修改科学数据和主指标。

如果只发生以下变化，不应强制重开研究蓝图：

- 补充缺失的 hash；
- 将 `source_rows` 改名为已有事实对应的 typed count；
- 重建 stale figure trace；
- 修复 HTML、路径、排序或展示；
- 从 canonical metric 重新生成 compatibility summary。

如果发生以下变化，必须重开研究蓝图或对应科学 checkpoint：

- 改变样本纳入/排除规则；
- 改变 entity 或 sample unit；
- 改变 validation design、split 或 aggregation；
- 改变 primary model/metric；
- 改变主图语义、panel 或 claim；
- 为解决冲突而重新训练或补充数据。

### 8.5 Checkpoint digest

digest 层按以下顺序工作：

1. 读取 active bundle 和 checkpoint-bound evidence snapshot；
2. 构建完整 stage deliverables；
3. 建立 metric/count/figure typed indexes；
4. 运行 comparability，再运行 value consistency；
5. 区分 conflict、non-comparable、missing identity 和 stale；
6. 只从 PrimaryMetricContract 指向的 record 生成主结果文字；
7. 通过 sample-flow records 描述多个样本数；
8. 当前生成 v2 summary 和 HTML；v3 summary 作为发布阶段升级项，不得在 v2 产物中冒充已完成。

不得继续使用以下逻辑：

- 取 CSV 第一行作为主指标；
- 取同名 metric record 的第一条进行比较；
- 只按 `source_rows` 比较计数；
- 从目录中任意选择最新时间文件；
- 由 HTML 端决定哪个数字更可信。

### 8.6 人工确认页面

现有 30 秒确认区保留，并增加：

- 主指标身份卡：task、model、cohort、validation、split、reducer、sample unit；
- sample-flow：目录 → 去重 → 合格 → processed → model → split；
- comparison 状态：真冲突、不同口径、聚合关系、缺失身份；
- active run bundle ID 和 hash；
- figure trace freshness；
- compatibility/presentation-only 文件明确降级显示；
- 每个阻断问题对应唯一恢复层级：derived rebuild、methods rerun、data repair 或 research plan reopen。

只有以下条件同时满足时页面为 `confirmable`：

1. active bundle 完整且 validated；
2. primary metric 精确解析为一条；
3. 所有 claim-bound evidence identity 完整；
4. 无 same-identity value conflict；
5. 所有主图 trace 当前有效；
6. 数据、方法、图表和 checkpoint hash 一致；
7. 无上游 semantic drift；
8. 页面来源 JSON 与 Agent payload 一致。

阶段摘要的输入作用域必须来自公共 `STAGE_SCOPE_PREFIXES` 和当前 checkpoint 的产物登记，不得通过扫描整个项目树来推断本阶段成果。阶段目录下的文档、代码、表格、图像、PDF 和小型运行报告应列出项目相对路径、类型、状态和 hash；大型数据只显示受限预览和可审计 locator。任何位于历史 checkpoint、缓存、失败 candidate 或其他 stage-owned 目录的文件，都必须保留其原始身份，不得仅因文件名相似而晋升为当前阶段产物。

## 9. Schema 与版本策略

新增或升级：

- `evidence_context_v1.json`；
- `metric_evidence_v3.json`；
- `aggregation_contract_v1.json`；
- `primary_metric_contract_v1.json`；
- `count_evidence_v1.json`；
- `run_evidence_bundle_v1.json`；
- `figure_code_trace_v2.json`；
- `evidence_comparison_result_v1.json`；
- `checkpoint_summary_v3.json`；
- 视实现需要升级 `result_support_checkpoint` 至 v4。

Schema 要求：

- 核心 identity 对象使用严格 required fields；
- 核心证据记录不允许任意 `additionalProperties`；
- 扩展字段进入显式 `extensions` namespace；
- schema registry 同时接受历史 v1/v2，只对新生成证据写 v3；
- 不原地改写旧 checkpoint 或旧科学 hash；
- v2 记录缺少 identity 时标记 `legacy_unqualified`，不得自动补造。

## 10. Compatibility 与旧项目迁移

### 10.1 compatibility 输出规则

`metrics.csv`、`analysis_summary.csv` 等旧接口保留，但必须满足：

- 从 canonical typed records 单向生成；
- 写入 `source_record_id` 和 canonical source hash；
- 默认 `evidence_role=presentation_only`；
- 不能被 result resolver、result support 或 checkpoint gate 反向读取为主证据；
- 多 seed、多 fold 或多 validation design 时不得压成一行而不声明 reducer；
- 外部脚本依赖旧列时通过 versioned adapter 兼容。

### 10.2 旧项目迁移

新增只读身份审计，建议命令：

```powershell
python -m draftpaper_cli.cli audit-evidence-identity --project <project>
```

输出：

- legacy metric candidates；
- 缺失的 model/split/validation/reducer；
- ambiguous count fields；
- stale figure traces；
- 可自动从现有 manifest 证明的映射；
- 需要重跑或人工确认的映射；
- 不修改项目的 migration plan。

迁移原则：

- 可由同一 run manifest 和现有列直接证明的字段可以确定性迁移；
- 需要猜测模型、cohort、分母或统计设计的字段不得自动迁移；
- 主证据无法补齐时，旧项目停在 refinement/rebuild，而不是伪造 confirmable；
- migration receipt 记录 before/after hash 和推导依据；
- fixture/mock 仍不能晋升为真实论文证据。

## 11. 实现文件范围

### 11.1 核心逻辑

- `draftpaper_cli/evidence_identity.py`
  - 公共 EvidenceContext、MetricEvidence、CountEvidence、AggregationContract、PrimaryMetricContract 和比较结果；
  - 身份优先比较和 legacy/presentation-only 标记。
- `draftpaper_cli/result_evidence.py`
  - 标准维度别名；
  - typed metric records；
  - 声明式 aggregation；
  - primary metric 精确解析；
  - 删除数值驱动的主指标推断。
- `draftpaper_cli/result_support.py`
  - 使用 evidence record IDs；
  - 区分模型和验证设计；
  - 阻止非严格 identity 和非 active bundle 进入结果支撑。
- `draftpaper_cli/result_support_signals.py`
  - 兼容新 comparison 状态；
  - 不把 presentation-only 指标当 signal。
- `draftpaper_cli/evidence_registry.py`
  - 现有 registry 兼容旧证据；
  - 完全读取 typed evidence 的接入列为后续任务，不得在发布前假设已经完成。
- `draftpaper_cli/run_evidence_bundle.py`
  - 管理 candidate/validated/active/failed/superseded 生命周期；
  - 失败运行不覆盖 active bundle。
- `draftpaper_cli/artifact_identity.py`
  - 增加 run transaction 和 producer fingerprint；
  - 维护 active/superseded bundle 关系。
- `draftpaper_cli/code_ownership.py`
  - 生成 FigureCodeTrace v2；
  - 绑定图像、metadata、代码和输入 hashes。
- `draftpaper_cli/checkpoint_digest.py`
  - 替换裸 metric/count 比较；
  - 生成 comparability 和 sample-flow；
  - 使用 canonical primary record。
- `draftpaper_cli/checkpoint_summary.py`
  - 当前继续生成 v2 summary；
  - v3 summary schema 和完整迁移仍是后续任务，保留 v1/v2 只读兼容和 preview 语义。
- `draftpaper_cli/checkpoint_html.py`
  - 展示 identity、sample-flow 和 comparison 分类；
  - 不承担科学选择。
- `draftpaper_cli/orchestrator.py`
  - active bundle gate；
  - derived repair 与 scientific reopen 分流。
- `draftpaper_cli/doctor.py`、`runtime_handshake.py`
  - 身份审计和旧项目迁移诊断。

### 11.2 Schema 和资源

- `draftpaper_cli/resources/schemas/`：已新增 evidence context、metric/count、aggregation、primary metric、run bundle、figure trace 和 comparison schema；
- `checkpoint_summary_v3.json`：已生成并注册，当前工作树生产 summary 为 v3；v1/v2 仅作只读 legacy，正式 release 前仍需完成 CI 跨平台验收；
- `schema_registry.json`：注册 current/accepted/migration；
- `release_manifest.json`：已按当前 package、schema、228 条命令和 Skill parity 重新生成并通过校验；正式 tag/release 仍待完成；
- workflow Skill 的源码、wheel 资源、Codex/Claude 安装副本：已同步并通过副本 parity，跨平台发布回归仍待完成。

### 11.3 文档

- `docs/human_checkpoints.zh-CN.md` 与英文版；
- CLI reference；
- command risk matrix；
- evidence identity 和 aggregation 专题文档；
- README 最近更新只提炼用户可见能力，不写入单项目结论。

## 12. 实施里程碑

### M0：冻结失败模式与当前基线

状态：基础与严格匿名 fixture 已完成；发布前仍需把 fixture、真实项目只读回归和全量发布测试统一收口。

1. 保留现有 HTML 空洞摘要失败样本；
2. 保留 seed-first-row、跨 validation aggregation、裸 `source_rows` 和 stale trace 四类匿名 fixture；
3. 将真实项目数据替换为最小合成记录；
4. 记录当前 v2 行为，防止重构破坏已有 HTML 能力。

### M1：MetricIdentity 与 AggregationContract

目标版本：v0.37.1；当前状态：工作树已实现，针对性测试通过，尚未形成正式 release。

1. 实现 EvidenceContext、MetricEvidence 和 AggregationContract；
2. 识别 `validation_design` 等标准别名；
3. seed/fold/repeated split 分轴；
4. 禁止无合同聚合；
5. compatibility 文件降级；
6. primary metric 精确匹配。

### M2：CountIdentity 与 SampleFlow

目标版本：v0.37.1；当前状态：工作树已实现，针对性测试通过，尚未形成正式 release。

1. 实现 CountEvidence；
2. 禁止无限定核心 `source_rows`；
3. 生成目录、唯一实体、合格、processed、model 和 split 流程；
4. 不同分母标记 non-comparable，不误报冲突；
5. 同一 CountIdentity 数值不同才阻断。

### M3：RunEvidenceBundle 原子发布

目标版本：v0.37.2；当前状态：工作树已实现并通过候选/失败/active 回归，仍需接入完整 artifact DAG 和发布验收。

1. candidate/active/superseded bundle；
2. 成功后原子切换 active pointer；
3. 失败输出隔离；
4. active bundle 进入 artifact DAG 和 snapshot；
5. result resolver 只消费 active bundle。

### M4：FigureCodeTrace v2 与 stale 传播

目标版本：v0.37.2；当前状态：工作树已实现并通过严格 trace 回归，Skill、wheel 资源和跨平台发布副本已同步，仍需跨平台发布回归。

1. 图像、metadata、代码和输入 hash 强绑定；
2. metric/count refs；
3. run transaction identity；
4. derived rebuild；
5. trace stale 阻断 checkpoint。

### M5：Checkpoint v3 与人工确认 UX

目标版本：v0.38.0；当前状态：阶段摘要/HTML v3、同源发布合同和匿名确认 UX 已在工作树实现并通过重点及分组全量回归，正式 release 和 CI 跨平台验收尚未完成。

1. comparability-first consistency engine；
2. identity card、sample-flow 和 conflict 分类；
3. Agent/CLI/JSON/HTML 同源；
4. derived repair 与 scientific reopen 分流；
5. confirmable 严格门禁。

### M6：旧项目迁移与跨学科发布

目标版本：v0.38.0；当前状态：工作树已实现核心能力并完成分组全量及发布候选验证，正式 release 仍待 CI 跨平台放行。

1. read-only identity audit；
2. deterministic migration receipt；
3. astronomy、machine learning、medicine、geography 和 generic tabular fixtures；
4. Windows/Linux/macOS、source/wheel、schema/Skill parity；
5. 完整发布说明和迁移指南；
6. 当前已完成 CLI/schema/Skill/release manifest parity 和 wheel release regression，待正式发布流程再次复核。

## 13. 测试矩阵

### 13.1 指标身份测试

- 同一 metric name、不同 model → `different_identity_non_comparable`；
- 同一 model、不同 validation design → non-comparable；
- 同一 model/design、不同 split → non-comparable，除非合同声明 pooled；
- seed row 与 seed mean → `parent_aggregate_relation`；
- 三 seed 缺一且 policy=block → blocked；
- 同一完整 identity、不同 value → `same_identity_value_conflict`；
- primary contract 匹配零条或多条 → blocked；
- compatibility scalar → ignored；
- resolver 不得跨 source-held-out/time-forward/sky-held-out 求均值；
- 任何主指标不得通过最大值或第一行选择。

### 13.2 计数身份测试

- catalog rows 与 unique entities → sample-flow，不冲突；
- eligible entities 与 model sample groups → sample-flow，不冲突；
- 同一 count definition/filter/cohort 数值不同 → blocked；
- 缺 entity type 或 count mode 的主计数 → blocked；
- patient/visit、object/cutout、source/event、site/sample 等跨学科 fixture 通过；
- train + validation + test 与 model cohort 的关系按 split contract 校验。

### 13.3 运行事务测试

- candidate 运行失败不覆盖 active bundle；
- 部分输出更新不产生 confirmable checkpoint；
- 新 bundle 晋升后旧 bundle superseded；
- checkpoint 不混合两个 transaction 的普通产物；
- 显式 comparison contract 可引用多个 bundle，但每个证据身份保持独立；
- active pointer、ledger 和 snapshot 一致。

### 13.4 图表追踪测试

- figure hash 变化而 trace 未变 → stale；
- metadata hash 变化 → stale；
- producer code hash 变化 → stale；
- trace metric/count refs 必须存在于 active bundle；
- 图表展示不同分母时 caption 必须引用对应 CountEvidence；
- 旧无身份 trace 只能 legacy preview，不能确认。

### 13.5 Checkpoint 与 HTML 测试

- 完整成果与事务变化继续分离；
- 页面一段话只引用 canonical primary metric；
- 不同口径显示“不可直接比较”，不显示“同一结果冲突”；
- 真冲突显示双方完整 identity 和来源；
- sample-flow 显示每一步 count definition；
- stale/blocked/preview 无确认命令；
- confirmable 只有一个 hash-bound 命令；
- HTML、JSON、Agent payload 和 CLI 数量/状态一致；
- 离线、UTF-8、响应式、路径 escaping 和敏感信息清理继续通过。

### 13.6 回归与发布测试

重点测试文件：

```text
tests/test_result_evidence.py
tests/test_result_support.py
tests/test_result_support_signals.py
tests/test_evidence_registry.py
tests/test_artifact_identity.py
tests/test_checkpoint_digest.py
tests/test_checkpoint_summary.py
tests/test_figure_plugin_trace.py
新增 tests/test_metric_identity.py
新增 tests/test_count_identity.py
新增 tests/test_run_evidence_bundle.py
新增 tests/test_evidence_comparison.py
```

验证命令：

```powershell
python -m pytest tests/test_metric_identity.py tests/test_count_identity.py tests/test_evidence_comparison.py -q
python -m pytest tests/test_result_evidence.py tests/test_result_support.py tests/test_evidence_registry.py -q
python -m pytest tests/test_checkpoint_digest.py tests/test_checkpoint_summary.py tests/test_artifact_identity.py -q
python -m ruff check draftpaper_cli tests
python -m compileall -q draftpaper_cli
python -m build
```

发布前还必须执行全量测试和隔离 wheel 安装，不以重点测试替代全量回归。

## 14. 真实项目回归案例的正确使用方式

一个真实项目回归案例仅用于验证以下通用失败模式；项目路径、对象记录和科学结论不进入公共框架：

1. compatibility summary 取第一 seed，而 canonical 主指标需要声明式多 seed 汇总；
2. resolver 未识别 validation design，导致多个验证设计混合；
3. 不同模型的同名指标被暴露为通用 primary 别名；
4. 原始目录行数与建模 sample-group 数使用相同 `source_rows`；
5. figure trace 与当前 run transaction 缺少强绑定；
6. HTML 能发现问题并停止确认，但错误应在更早的 evidence gate 被拦截。

公开测试不得包含：

- 论文项目绝对路径；
- 真实对象记录；
- 项目专属模型名或数字；
- 论文科学结论；
- 私有数据 locator。

测试应使用匿名模型 `model_a/model_b`、验证设计 `design_a/design_b` 和实体 `entity`，证明框架逻辑跨学科成立。

真实项目只读回归只能验证“框架能识别并阻断该类问题”，不得把真实项目的文件、数值、路径或领域术语复制到公共测试、默认 schema 或展示样例中。若需要展示用户体验，必须使用 `generate_checkpoint_html_showcase.py` 生成匿名六阶段页面，并在报告中明确其为测试可视化，不是科研证据。

## 15. 人工确认点设计

不新增分散的人工作业。每个阶段仍只保留一个主要确认入口：

```text
机器生成/运行
→ evidence identity audit
→ artifact/trace/hash validation
→ 中文 stage_summary.zh-CN.html
→ 用户一次性审阅完整成果与边界
→ hash-bound confirm/refine/reject
```

进入人工确认点时，Agent 必须给出：

- 本阶段生成内容的一段中文总结；
- HTML 项目相对路径和本机绝对路径；
- 主图、主表、代码、报告和 active bundle；
- primary metric identity；
- sample-flow；
- conflict/non-comparable/missing/stale 分类；
- 确认含义和拒绝后的唯一安全路线。

Agent 不得：

- 只说“请确认 hash”；
- 用内部文件路径代替内容归纳；
- 把 non-comparable 误写成数值冲突；
- 把框架派生文件重建误写成科学合同变更；
- 替用户选择结果路线或确认 checkpoint。

## 16. 验收标准

v0.38.0 只有同时满足以下条件才可发布：

1. 所有主指标都有完整 MetricIdentity；
2. 所有关键样本数都有 CountIdentity；
3. 所有聚合都有 AggregationContract；
4. PrimaryMetricContract 唯一解析，不使用第一行、最大值或名称猜测；
5. compatibility 输出不能进入科学证据门；
6. result evidence 不跨 validation design 隐式求均值；
7. active RunEvidenceBundle 原子发布；
8. FigureCodeTrace v2 与当前图像、代码、数据和 run hash 一致；
9. checkpoint 比较器先判断 identity，再比较 value；
10. catalog/model/split 等不同分母正确显示为 sample-flow；
11. same-identity conflict、missing identity 和 stale 均阻止确认；
12. non-comparable 记录不会被误判为同一结果冲突；
13. HTML 完整展示阶段成果、证据身份、边界和恢复路线；
14. Agent、CLI、JSON、HTML 和 ledger 使用同一事实来源；
15. 旧 v1/v2 checkpoint 可读但不会被静默升级；
16. 框架修复和科学合同变更具有不同状态机路线；
17. 跨学科 fixture、真实项目回归、全量测试、wheel 和 Skill parity 全部通过；
18. 不自动替用户执行任何科学确认。

## 17. 风险与控制

| 风险 | 控制措施 |
|---|---|
| schema 变严格导致旧项目大量 blocked | v1/v2 只读兼容、read-only audit、分阶段迁移 |
| 误把合法多视角结果当冲突 | comparability-first，different identity 明确 non-comparable |
| 过度宽松导致真正冲突漏过 | same identity 使用来源 hash、定义 ID 和声明容差严格核对 |
| 自动迁移编造科学语义 | 只迁移可由结构化来源证明的字段，其余 refinement required |
| 原子 bundle 增加磁盘占用 | 复用 content-addressed artifact，旧 bundle 保存引用而非复制大数据 |
| 外部脚本依赖旧 `metrics.csv` | versioned compatibility adapter，单向从 canonical 生成 |
| 人工确认点过多 | 身份验证在机器 gate 完成，不新增零散用户确认 |
| framework repair 误触研究蓝图重开 | derived/scientific change classifier 与回归测试 |
| 学科插件输出字段多样 | alias registry 只做语法归一化，科学语义仍由插件合同声明 |

## 18. 推荐执行顺序

```text
冻结现有 v2 行为和四类匿名失败 fixture
→ MetricIdentity / AggregationContract / PrimaryMetricContract
→ CountIdentity / SampleFlow
→ compatibility 输出降级
→ result evidence 与 result support 严格解析
→ RunEvidenceBundle 原子发布
→ FigureCodeTrace v2 与 stale 传播
→ comparability-first checkpoint v3
→ HTML identity/sample-flow UX
→ 旧项目 read-only audit 与迁移
→ 跨学科 fixture
→ 真实项目只读回归
→ 全量测试、wheel、Skill/schema parity
→ v0.38.0 发布
```

每个里程碑先增加失败测试，再实现代码，再执行针对性回归。不得为了让旧项目页面变绿而硬编码某个模型、seed、样本数或论文路径。

## 19. 当前完成度判断

### 已完成

- 阶段摘要 v3 和完整成果模型；
- 中文 HTML、图表预览、表格预览、代码映射和响应式布局；
- preview、stale、blocked 和确认命令隔离；
- latest pointer、路径安全、runtime migration 和只读诊断修复；
- Result Support 路线展示；
- 全部人工确认阶段的通用摘要适配；
- EvidenceContext、MetricEvidence、CountEvidence、AggregationContract 和 PrimaryMetricContract 的工作树实现；
- RunEvidenceBundle 的生命周期和失败 candidate 隔离；
- FigureCodeTrace v2 的当前图像、代码、输入、运行事务和 metric/count 绑定；
- identity-first 比较、sample-flow、active bundle 和严格 result-support 阻断；
- 匿名严格 fixture 的 HTML 人工确认资格验证；
- typed evidence bridge、`evidence_identity_audit_v1` schema、只读 `audit-evidence-identity` CLI；
- 四份 workflow Skill/contract 副本同步、228 条 CLI contract、schema registry 和 release manifest parity；
- 当前重点回归：证据/HTML `20 passed`，联合身份/运行/HTML 回归 `65 passed`，已有分组回归 A/B/C/D 分别为 `142/194/391/443 passed`；
- wheel 构建、安装矩阵、wheel 安装后五域 release regression、反例回归和语义回归通过；
- 当前工作树 Ruff 和 compileall 通过。

- 分组全量 pytest 通过：`1179 passed, 2 skipped`；
- 重建后的 v0.37.0 wheel 隔离安装和 release regression 通过。

### 尚未完成

- 最终 CI 隔离 wheel/源码发布回归、正式版本 tag/release 和跨平台发布验收；
- 迁移文档和 derived repair/scientific reopen 操作手册的最终发布收口。

因此，当前应把状态表述为“框架级证据身份修复已在工作树落地，尚待发布收口”，不能把某个真实论文项目的 HTML 变绿、重点测试通过或兼容输出一致当成整个框架优化完成。真正完成的标志是：这些错误在生成 result support 和人工确认页之前已被结构化证据合同阻止，确认页只负责清楚地向用户解释经过机器验证的结果和剩余科学判断。

在本轮新增阶段 HTML showcase 后，完成度还必须区分三层：

- **框架实现**：公共代码、schema、CLI 和 HTML 合同已经存在；
- **匿名合同验证**：跨学科 fixture 能覆盖 `confirmable`、`blocked`、`preview`、`stale` 和身份缺失状态；
- **发布与真实项目使用**：全量 CI、wheel 隔离安装、跨平台验收、正式 tag/release 和真实项目由用户完成的人工确认仍然独立计算。

前两层通过，不能自动推出第三层通过。

## 20. 不在本方案范围内

- 不替任何论文决定应该采用哪个模型、样本 cohort 或科学论断；
- 不自动删除历史指标、图表或 checkpoint；
- 不通过自由文本推断缺失的 scientific identity；
- 不把真实项目数据提交到公共仓库；
- 不要求迁移大型外部数据集；
- 不增加与证据身份无关的商业化、会员或许可证工程；
- 不因框架优化自动确认研究蓝图、核心证据或最终稿件。

## 21. 最终交付物

1. 本文档更新后的框架执行方案；
2. 新证据 schema 与 schema registry；
3. metric/count/aggregation/run bundle/figure trace 实现；
4. result evidence、result support、checkpoint 和 HTML 重构；
5. 旧项目身份审计和迁移报告；
6. 跨学科匿名 fixtures；
7. 中文/英文人工确认和迁移文档；
8. CLI reference、risk matrix、Skill copies 和 release manifest；
9. 全量测试、wheel 安装、跨平台和浏览器验收记录；
10. v0.38.0 发布说明。

本方案的最终目的不是让某一篇论文的 warning 消失，而是确保 Draftpaper-loop 对任何学科、任何项目都不会把不同模型、不同统计汇总、不同验证设计或不同样本分母伪装成同一证据。
