# Draftpaper-loop 全流程架构优化方案

日期：2026-07-16
来源：Euclid Q1 VIS + DESI 论文项目完整实跑、PDF 编译、引用核查及两轮独立盲审
适用范围：Draftpaper-loop 全部学科、交叉学科和新论文项目
性质：架构级优化方案，不是 Euclid 项目专用补丁

## 1. 总体判断

Euclid/DESI 项目证明了 Draftpaper-loop 当前已经具备一条可运行的 evidence-first 主链：研究蓝图、数据与方法能力审计、主图生成、结果确认、自由写作、引用核查、独立盲审和 PDF 编译都可以执行。最终项目也成功生成了 13 页论文，保留 24 篇引用文献，并完成六组主图和两位独立审稿人的绝对质量审查。

但实跑同时暴露出一个比“模板写作质量”更基础的问题：**研究对象、cohort、estimand、方法、运行、图表、公式和正文尚未共享同一个可执行的科学语义系统。** 当前多个模块各自保存相似信息，再通过文件名、数值、自然语言和阶段状态进行弱关联。这会产生以下后果：

- 同一科学量在不同产物中出现不同定义，例如 183-source 回归子集与 184-source 未调整图表混用。
- 实际计算的是 EXP 概率可靠性 ECE，但 Methods 一度写成 confidence-versus-accuracy ECE。
- 同一个数值存在多个候选记录时，证据绑定依赖句子措辞，而不是稳定的 estimand/run/model ID。
- 修改正文后 stale 传播过宽，或者正式释放已通过但 LaTeX 仍因某个阶段 stale 而阻塞。
- 最终质量失败可能错误地路由回 `plan-figures --use-review-tasks`，即使失败原因只是引用快照过期或盲审尚未完成。
- 匿名审稿包包含测试文件，却排除了其依赖的实现模块，同时混入与当前主任务无关的历史表格。

因此，后续不应继续单纯增加 gate 数量。核心工作应是把 Draftpaper-loop 从“文件驱动的阶段工作流”升级为：

> **以 Research Intent、Cohort View、Estimand、Executable Analysis、Run、Evidence 和 Claim 为主键的科学编译系统。**

Gate 只验证这些主键之间的可追溯关系，不再尝试从自然语言、相同数值或文件存在性猜测科学含义。

## 2. 本方案不做什么

本方案明确避免以下错误方向：

1. 不把 `DEV`、`EXP`、`MORPHTYPE`、Euclid tile 或天文学专有字段写进通用核心。
2. 不通过为 Euclid 项目增加例外规则来让当前测试变绿。
3. 不要求所有论文必须有 6 张主图；5--6 个主图组仍是完整论文的常见目标，但最终数量由已确认研究蓝图决定。
4. 不通过删除参考文献解决引用问题；citation audit 继续遵守“保留已人工确认参考文献，优先收紧或改写正文”的原则。
5. 不用更多模板句约束 Codex 写作；写作器继续自由组织科学叙事，系统只约束证据、论断边界、章节职责和可复现性。
6. 不把项目自身缺失的外部信息伪装成框架已解决。例如 catalogue 标签生成算法、上游 release 细节或不可公开数据不能由系统编造。

## 3. 已完成能力与仍然存在的缺口

### 3.1 已完成或已基本建立

- 中央 `projects` 根目录、短项目名、Windows 路径预算和外部大数据只读 locator。
- 中文研究蓝图、claim contract、figure storyboard、统计验证合同和确认 hash。
- 结果不支持研究计划时的 claim downgrade 与 data/method supplement 两条路线。
- 项目本地方法代码审计、插件充分性门和正式插件 promote 路线分离。
- 主图必须绑定研究问题、claim、数据角色、方法输出和运行产物。
- Results 先写，Introduction/Data/Methods/Discussion 后写的 evidence-first 论文顺序。
- 五个章节的自由写作候选、Scientific Editor、section acceptance 和正式安装生命周期。
- Scientific Evidence Registry、run-aware 结果解析和定量论断绑定。
- 引用保留、补充 bibliography、引用覆盖、最终引用快照绑定。
- 同一匿名稿交给两位独立审稿人的 blind-review 框架。
- 最终 PDF 编译和页面渲染检查。

### 3.2 部分完成但语义仍不充分

- stale propagation 已支持 change classification，但仍以阶段为主要传播单位，缺少 artifact/claim 级依赖图。
- Semantic Figure Contract 能检查结构和角色，但不能充分检查“面板实际计算是否等于声明的 estimand”。
- StatisticalValidationContract 能声明规则，但公式、代码、图和正文还没有由同一个可执行规范生成。
- Evidence Registry 能保存 scope，但同值多记录时仍可能出现措辞敏感的 ambiguous binding。
- review rules 已按学科组合选择，但证据角色别名和实际项目产物之间仍可能错位。
- blind-review bundle 能匿名化，但没有完成依赖闭包、任务相关性过滤和可执行 smoke test。

### 3.3 仍需架构级解决

- Research objective 与“如何完善已有数据集”之间的语义偏移。
- cohort、analysis subset、sample unit、split 和 missingness 的统一主键。
- estimand、公式、代码、图表统计量和 Methods 文案的一致生成。
- model/seed/run selection policy 的事前声明和审稿可见性。
- 章节修订的事务化提交，以及精确 stale 传播。
- 最终质量失败的原因分类和正确恢复路线。
- 匿名可复现包的代码依赖闭包、隐私脱敏和当前运行资产筛选。
- 独立审稿发现到局部修订、补分析、claim downgrade 的结构化闭环。

## 4. Euclid/DESI 实跑问题清单与通用修复

| ID | 实跑表现 | 根因 | 通用优化 | 状态 |
|---|---|---|---|---|
| EUC-01 | 最初研究蓝图围绕“完善 Euclid-DESI 数据”而不是用户 idea | idea、数据资产和工程任务没有分层 | 引入 `ResearchIntentContract`，分别保存 scientific question、target claim、available assets、engineering tasks 和 forbidden reinterpretations | 待完成 |
| EUC-02 | 研究目标在预训练、官方模型、微调、物理参数和 DEV/EXP 任务之间多次变化 | objective 变化没有先经过可行性差异解释 | 每次 objective revision 先生成 semantic diff，说明哪些 claim、cohort、method、figure 和成本会变化，再生成新 plan hash | 部分完成 |
| EUC-03 | 插件充分性发生在 Agent 补项目代码之前，形成“缺方法所以不能生成代码”的闭环 | capability discovery 与 capability execution 共用一个阻断门 | 改为 bootstrap sufficiency 和 release sufficiency 两层；bootstrap 阶段允许受审计的 project-local implementation | 部分完成 |
| EUC-04 | 项目本地代码可运行，但是否应沉淀正式插件与当前论文执行混在一起 | project-local binding 和 reusable plugin promotion 生命周期不清 | 当前论文只要求 project-local capability passport；通用化与 promote 独立异步执行 | 基本完成 |
| EUC-05 | 标签来源、上游产品版本、父样本 query 和 join 规则在正文中仍不够完整 | Data context 只有字段和值，没有 provenance completeness contract | 新增 `DataProvenanceContract` 和缺失字段声明；缺失时自动收窄 inferential population，不允许写成已知事实 | 待完成 |
| EUC-06 | 183-source reliable subset 与 184-source unadjusted display 混用 | registry 记录 count，但没有把 analysis view 作为实体 | 新增 `CohortViewRegistry`；每个表、panel、estimand 和正文句子必须绑定 `cohort_view_id` | 待完成 |
| EUC-07 | ECE 数值和图正确，但 Methods 公式定义错误 | 代码、公式计划和写作器分别生成同一统计量 | 建立 `ExecutableAnalysisSpec`，公式 AST、实现函数、图表 metadata 和 Methods 表达由同一节点派生 | 待完成 |
| EUC-08 | 0.914 是三个 seed 中的一个结果，但 primary seed 选择边界不清楚 | run manifest 缺少明确的 selection policy | 新增 `RunSelectionPolicy`，声明 primary/replicate/sensitivity/post-hoc、锁定时点和汇总方式 | 待完成 |
| EUC-09 | Figure 2c 被称为 paired gain，但误差条来自两个边际区间宽度 | 方法名称与实际 uncertainty procedure 只做字符串匹配 | `paired`、`clustered`、`bootstrap` 等术语必须绑定可执行 resampling unit 和输入对齐检查 | 待完成 |
| EUC-10 | Figure 5 图内标题写 systematic，caption 又说 selected comparison | Figure Contract 没有检查图内文字与 manuscript claim 的矛盾 | OCR/plot metadata 文本进入 semantic validation；标题、caption、Methods 和 claim boundary 做一致性检查 | 待完成 |
| EUC-11 | 多张图在 PDF 页宽下文字过小，Figure 5 panel label 发生拥挤 | 质量门只检查 PNG、坐标、图例等结构 | 新增 journal-width render QA：最小字体像素、panel overlap、裁切、颜色可辨性、caption 自包含性 | 部分完成 |
| EUC-12 | Results、Methods 局部修改需要手动执行 sync、submit、editor、accept、write 多步 | section lifecycle 面向内部状态，而不是一次用户修订事务 | 新增 `apply-section-revision` 事务命令；自动完成漂移同步、验证、editor、接受和安装，保留一次审计记录 | 待完成 |
| EUC-13 | 同一个 0.892/0.914 在多个证据记录中出现，是否能绑定取决于句子如何描述模型 | binder 先按数值找候选，再从自然语言推断 scope | 正文候选同时输出 sidecar claim map，直接绑定 evidence ID；自然语言推断只作兼容 fallback | 待完成 |
| EUC-14 | 修改 Methods/Results 后 Data context 和 Discussion 可能被重新打开；functional release 通过后 assembly 仍提示 Discussion stale | stage-level stale 与 section candidate hash、active artifact hash 不完全一致 | 迁移到 artifact DAG，按输入 hash 和 semantic dependency 精确传播；stage status 只作汇总视图 | 待完成 |
| EUC-15 | quality-check 因 stale citation/旧盲审失败后，status 推荐重新 `plan-figures --use-review-tasks` | 所有 review task 被统一解释为需要重做分析和图表 | 先分类 failure domain，再路由 citation、prose、reproducibility、render、analysis 或 figure repair | 待完成 |
| EUC-16 | 引用核查通过，但 37 处 usage 中 27 处 partial、34 处 low-confidence，平均 match score 仅 0.216 | contextual citation 与 direct evidence 使用同一汇总分数 | 按 citation intent 设置不同判定；direct claim 要求 passage-level evidence，context/provenance 允许较低语义重合但必须说明角色 | 待完成 |
| EUC-17 | 匿名包包含 tests，却缺少其导入的 `methods/src` 实现；pytest 收集失败 | reproducibility allowlist 不是依赖闭包，隐私命中时整文件排除 | 基于 AST/import 建 dependency closure；对身份和私有 locator 生成脱敏副本，而不是静默删除核心模块 | 待完成 |
| EUC-18 | blind bundle 混入旧 early/late、clustering、anomaly 等当前主任务无关表格 | 打包器递归收集整个 `results/tables` | 仅打包 promoted snapshot、selected run、figure trace 和正文实际引用资产；历史产物进入 audit archive | 待完成 |
| EUC-19 | 盲审后局部修订会使旧 bundle/report 失效，但修订路线缺少清晰分层 | review finding 没有结构化 change class | 将 finding 分类为 prose-local、caption/render、reproducibility、analysis supplement、claim downgrade 和 new evidence | 待完成 |
| EUC-20 | quality 报告提示“0.99 below 0.95 or hard check failed”，实际是 hard check 未通过 | score 与 hard checks 合并成模糊错误 | 每个失败只输出真实 predicate、artifact hash、责任阶段和精确下一命令 | 待完成 |
| EUC-21 | CLI 输出完整 binding 和 citation usage，单次输出巨大且难以判断关键问题 | 命令默认返回调试级 payload | 默认输出 summary + artifact path；`--verbose`/`--json-full` 才输出完整记录 | 待完成 |
| EUC-22 | 用户要求“跳过检查点”时，草稿 PDF、科学确认和最终 release 的含义混在一起 | 自动化模式没有区分 draft build 与 scientific approval | 明确 `draft_pdf_ready`、`review_blocked`、`release_ready` 三种状态；普通自动步骤可批处理，科学确认仍需用户 hash | 待完成 |
| EUC-23 | 项目文件名和部分中间产物曾游离在数据目录，Windows 路径过长 | 项目根、scratch、原始数据和导出目录职责混淆 | 继续执行中央 projects root、短 slug、外部 locator、项目内临时目录和 path budget | 已建立 |
| EUC-24 | `review-results-with-discipline-rules` 通过，但独立审稿仍识别出 paired uncertainty、cohort 和可复现性问题；citation audit 又重复运行通用 review rules 并误报缺少已有证据 | review rule 只看到宽泛 evidence role，没有消费具体 analysis spec、Results claim 和 panel binding；规则执行阶段边界不清 | 新增 `DisciplineReviewCompiler`，在 Results 后按插件 trace 选择规则并绑定真实 estimand/run/claim；citation audit 不再重复承担统计和图表审查 | 待完成 |
| EUC-25 | 最终稿使用 APJS/AASTeX，但目标期刊若来自默认值或旧上下文，用户不易判断是否已明确选择 | journal profile 与 research intent 分离，默认 profile 可能看起来像用户决定 | 新增 `JournalIntentContract`；未明确选择时标记 `provisional`，研究蓝图确认包必须展示期刊、模板版本和关键格式约束 | 待完成 |

## 5. 目标架构：Scientific System of Record

### 5.1 统一科学主键

所有核心产物应引用下列稳定主键，而不是复制并重新解释文本：

```text
research_intent_id
plan_snapshot_id
claim_id
data_source_id
cohort_id
cohort_view_id
estimand_id
analysis_spec_id
capability_binding_id
run_id
evidence_id
figure_id / panel_id
section_claim_id
manuscript_snapshot_id
review_bundle_hash
```

关系链为：

```text
Research Intent
  -> Claim
  -> Cohort View + Estimand
  -> Executable Analysis Spec
  -> Data/Method Capability Binding
  -> Run
  -> Evidence
  -> Figure Panel / Table
  -> Manuscript Claim
  -> Citation and Review
```

`research_plan.md`、Methods 公式、figure metadata 和正文都是该系统的不同视图，不再各自成为事实来源。

### 5.2 编译器式分层

建议把主流程拆成三个逻辑层：

1. **Scientific front end**：解析 idea、文献、数据资产和用户边界，生成 research intent、claim、cohort、estimand 和 figure story。
2. **Execution middle end**：解析能力缺口，形成 executable analysis spec，绑定插件或 project-local 实现，执行并生成 run/evidence。
3. **Manuscript back end**：从冻结 evidence 生成图表与章节，执行 citation audit、匿名审稿和最终 release。

不同学科只扩展 data connector、method template、review rule 和术语映射，不改变主流程语义。

## 6. 核心模块优化

### 6.1 ResearchIntentContract

新增：

```text
research_plan/research_intent.json
research_plan/research_intent.zh-CN.md
research_plan/research_intent_diff.json
```

必需字段：

- scientific question 与 falsifiable hypothesis。
- target population、sample unit 和目标任务。
- primary claims、secondary claims 和明确不做的 claims。
- 用户 idea、现有数据资产、外部文献和工程任务的来源分层。
- 成功、降维和终止条件。
- 允许 Agent 自主修复的 implementation boundary。

`generate-plan` 必须先证明每个主要 claim 来自 idea + literature + available evidence，而不是仅来自现有数据字段。若研究目标变化，先生成 semantic diff，用户确认后才生成新 hash。

### 6.2 两层 Plugin Sufficiency

把当前充分性门拆为：

1. `bootstrap_sufficiency`：现有插件、可审计 project-local 代码或 Agent 可实现方法是否足以继续设计。
2. `release_sufficiency`：正式运行是否已经绑定经过验证的 data/method capability、依赖和输出合同。

只有以下情况才在代码生成前阻断：

- 必需数据不可获得，且 connector/rescue 已失败。
- 必需方法没有现成插件、没有可审计项目代码、也无法从公开仓库获得或实现。
- 用户必须提供凭证、服务器结果或受限数据。

缺少正式通用插件不能阻止项目本地实现。项目完成后再由 `promote-plugin-candidate` 决定是否沉淀。

### 6.3 DataProvenanceContract 与 CohortViewRegistry

新增：

```text
data/data_provenance_contract.json
data/cohort_registry.json
data/cohort_view_registry.json
data/join_and_filter_ledger.jsonl
```

`cohort_registry` 记录：

- parent cohort、sample unit、source release、selection expression。
- join keys、match radius、duplicate policy、exclusion reason 和每步 count。
- split unit、group unit、leakage boundary。
- label source、label-generation provenance、quality/ambiguity 字段是否存在。

`cohort_view_registry` 记录每个分析视图：

```json
{
  "cohort_view_id": "heldout_reliable_measurement",
  "parent_cohort_id": "heldout_all",
  "filter_expression": "quality_flag == 0 and measurement > 0",
  "sample_unit": "source",
  "count": 183,
  "missingness_policy": "complete_case_by_outcome",
  "allowed_uses": ["adjusted_regression"],
  "forbidden_uses": ["overall_test_performance"]
}
```

图表中不同 panel 可以使用不同 view，但 caption 必须显式说明。系统验证 subset 关系、count 守恒、分组支持和 missingness，不允许把多个 cohort count 当成冲突，也不允许静默混用。

### 6.4 ExecutableAnalysisSpec

新增：

```text
methods/executable_analysis_spec.json
methods/analysis_formula_ast.json
methods/run_selection_policy.json
methods/resampling_contract.json
```

每个 `analysis_spec_id` 必须声明：

- estimand、outcome、exposure、covariates、reference direction 和 unit。
- cohort view 与 split。
- preprocessing fit scope。
- model family、hyperparameter selection 和 seed policy。
- uncertainty/resampling method、resampling unit、paired/grouped 结构。
- multiplicity family、calibration definition 和 threshold selection。
- implementation entry point、required inputs 和 declared outputs。

公式使用结构化 AST 或 SymPy 表达，代码、Methods 公式、variable explanation、table schema 和 figure metadata 从同一 spec 派生。这样可从根本上避免 ECE 公式与实际计算不一致，以及“paired”名称与非配对误差条不一致。

### 6.5 RunSelectionPolicy

对于多 seed、多 fold、多 checkpoint 和多模型项目，必须在运行前声明：

```text
selection_role: primary | replicate | sensitivity | ablation | post_hoc
selection_metric
selection_partition
selection_locked_at
test_access_policy
aggregation_policy
headline_reporting_policy
```

若无法证明某个 seed 是事前 primary，则正文只能报告全部 seed 的分布或明确说明某个数值是单次运行，不得将最大值包装成唯一 primary estimate。

### 6.6 Evidence Registry 2.0 与结构化 claim map

将证据唯一键定义为：

```text
(estimand_id, cohort_view_id, run_id, model_id, split_id, aggregation, metric_dimension)
```

数值只是该键的属性，不能作为主匹配条件。

Codex 提交章节时，同时输出：

```text
writing/claim_maps/<section>.json
```

每个 manuscript claim 记录 sentence hash、evidence IDs、rounding policy、claim strength 和 citation intent。自然语言 scope inference 只用于旧项目兼容，不再决定正式 release。

必须支持：

- 同一值属于多个模型或 cohort 时的显式消歧。
- 允许按声明精度四舍五入。
- 将 seed、版本号和 source ID 识别为 identifier，而不是 performance metric。
- 一个句子绑定多个 evidence，但每个 evidence 保留独立 scope。

### 6.7 Figure Contract 2.0

每个 panel 必须绑定：

```text
panel_id
claim_id
cohort_view_id
estimand_id
analysis_spec_id
run_id
evidence_ids
plot_grammar
visual_encodings
uncertainty_semantics
caption_fields
```

增加两级验证：

1. **Scientific semantic validation**：变量、cohort、estimand、方法输出、panel 结构和 claim boundary 一致。
2. **Publication render validation**：在目标期刊实际宽度下检查字体、重叠、裁切、色盲可辨性、图片分辨率和 caption 自包含性。

图内标题和 annotations 也进入语义检查。出现 `systematic` 与 `selected comparison`、`reliable subset` 与实际全样本等矛盾时必须修复。质量门不得只因 PNG 存在、有坐标轴和图例就判 pass。

### 6.8 Section Revision Transaction

新增提议命令：

```text
draftpaper apply-section-revision --section methods --input revised.tex
draftpaper apply-metadata-revision --input metadata.yaml
```

一次事务自动完成：

1. detect drift。
2. classify change。
3. sync stale。
4. submit candidate。
5. evidence/claim-map validation。
6. Scientific Editor。
7. 在已有用户 revision authorization 范围内安装候选。
8. 写入 transaction receipt。

这不等于 Agent 代替用户确认新科学论断。研究蓝图、核心证据、claim downgrade 和最终 release 仍需用户确认；纯措辞、公式纠正和 reviewer-local repair 可以在一次明确授权的 revision batch 内自动完成。

### 6.9 Artifact DAG 与精确 stale propagation

用 artifact dependency DAG 取代“章节改动后按固定列表重开阶段”。建议 change class：

```text
presentation_only
citation_local
prose_semantic_no_evidence_change
metadata_claim_change
cohort_definition_change
analysis_spec_change
run_output_change
figure_semantic_change
claim_contract_change
```

传播示例：

| 修改 | 应 stale | 不应 stale |
|---|---|---|
| 纠正 ECE 公式但数值不变 | Methods、LaTeX、citation audit、review/quality | Data、run、figures、core evidence |
| Results 收窄一句解释 | Results、依赖该 claim 的 Discussion、LaTeX、citation audit、review | Data、Methods、figures |
| caption 纯排版 | LaTeX、render QA、review | 数据、方法、正文 |
| 替换主图证据 | core evidence、Results、Discussion、LaTeX、citation audit、reviews | 无关数据源 |
| citation audit 局部改写 | 受影响章节、LaTeX、citation audit、reviews | research plan、run、figures |
| cohort 定义变化 | data、method execution、figures、core evidence、全部正文 | 无 |

stage manifest 只汇总 DAG 状态。`functional_quality_release=pass` 时，assembly 不能再因未被 release 计算包含的同一 section stale 而意外失败。

### 6.10 Failure Router 与 explainable status

最终失败先分为：

```text
artifact_stale
citation_support
manuscript_semantic
reproducibility_package
render_quality
scientific_analysis
figure_contract
human_review_required
```

路由规则：

- stale citation -> final citation audit。
- reviewer 指出局部文案错误 -> section revision。
- reviewer 指出匿名包缺代码 -> reproducibility package repair。
- paired uncertainty 错误 -> analysis supplement 或 claim downgrade。
- 图表不可读 -> render repair，不重跑科学分析。
- 只有 analysis/figure scientific contract 改变时才回到 `plan-figures`。

`status` 默认显示：真实失败 predicate、受影响 artifact、当前 snapshot、推荐命令和禁止执行的错误路线。`doctor --explain` 提供完整依赖图。

### 6.11 Reproducibility Bundle Builder

替换当前简单 allowlist/glob 打包：

1. 从 selected run 和 manuscript figure trace 计算任务资产集合。
2. 通过 Python AST/import、shell entry point 和 manifest 计算代码依赖闭包。
3. 排除历史 run 和未被当前 claim/figure 使用的表格。
4. 对作者身份、绝对路径、凭证和服务器 locator 生成脱敏 staging copy，不修改原文件。
5. 包含 environment lock、命令、随机种子、checkpoint 标识/hash、split ledger 和最小派生数据。
6. 在隔离临时目录执行 import、pytest collection 和最小 smoke test。
7. 只有 bundle 自洽时才标记 `reproducibility_ready=true`。

若受限数据或权重不能打包，manifest 必须明确列出缺失对象、获取方式、可复现程度和审稿边界，不能出现“测试文件存在但实现模块缺失”的假完整包。

### 6.12 Independent Review Revision Loop

每条 review finding 增加：

```text
finding_class
affected_claim_ids
affected_artifacts
requires_new_scientific_run
allowed_repair_scope
supersedes_finding_id
resolution_evidence
```

修订路线：

- `prose_local`：局部正文或 caption 修复。
- `reproducibility`：重建匿名包，不重跑研究。
- `render_only`：重绘排版，不改变 evidence。
- `analysis_supplement`：补统计、方法或数据并重开必要链路。
- `claim_downgrade`：冻结现有结果，收窄研究论断。
- `new_evidence`：重新执行并生成新 evidence snapshot。

任意 manuscript、figure 或 bundle 变化后，旧 reviewer reports 移入 `superseded/<bundle_hash>/`，不能继续参与当前 release。两位审稿人必须审核同一个最终 bundle hash。

### 6.13 Citation Audit 2.0

继续保留所有人工确认参考文献，同时按 intent 设定不同标准：

- `direct_support`：必须有精确 evidence passage、locator 和 claim alignment。
- `method_or_tool_provenance`：证明方法/工具来源即可，不要求支撑全部邻近论断。
- `comparison_context`：允许部分语义重合，但正文必须明确比较边界。
- `dataset_or_product_provenance`：必须与 Data 中对应产品或处理来源绑定。

报告同时显示 usage count、unique reference count、summaries coverage、direct-support confidence 和 contextual relevance。低置信引用进入改写队列，不通过删除文献解决。最终 audit 必须绑定 assembly 后的 manuscript snapshot。

### 6.14 DisciplineReviewCompiler

学科 review rule 的正式执行位置保持在 Results 完成之后，但输入必须从当前插件执行链和 analysis spec 编译，而不是只传递一组宽泛字符串角色。

每条适用规则接收：

```text
claim_id
results_sentence_hash
figure/panel IDs
cohort_view_id
estimand_id
analysis_spec_id
run_id
method/data plugin IDs
evidence IDs
threshold source
```

规则输出区分：

- `semantic_repair`：图或结果正确，但正文表述、caption 或术语不准确，优先自动局部修复。
- `analysis_supplement`：需要补统计或稳健性分析。
- `claim_downgrade`：现有结果只能支持更窄论断。
- `capability_missing`：必要方法完全缺失且 rescue 失败，才阻断图表生成。
- `advisory`：领域惯例或未来工作，不伪装成硬阈值。

Results 审查必须检查正文内容是否准确解释图和统计结果，而不仅检查图表是否由插件生成。citation audit 只审查引用真实性和位置，不再重复运行 baseline、power、axis unit、spatial overlap 等学科规则。最终 quality gate 可以汇总已冻结的 discipline review report，但不能在另一个阶段用不同输入重新执行同一规则。

### 6.15 JournalIntentContract

新增：

```text
journal_profile/journal_intent.json
```

记录 journal、article type、template source/version、用户选择状态、匿名审稿要求、图表宽度和 bibliography style。状态分为 `confirmed`、`provisional` 和 `unset`。只有 `confirmed` 可以在 PDF 中写入 “Submitted to ...”；其余状态生成中性 draft 标记。

### 6.16 CLI 与 token 体验

默认 CLI 只输出：

```text
status / decision
current snapshot
blocking issue count
top issues
artifact paths
verified next action
```

完整 bindings、citation usages 和 registry records 写入文件，并通过 `--verbose` 或 `--json-full` 查看。

章节 evidence packet 改为 paragraph-job retrieval：每个段落只获取相关 evidence IDs、必要摘录和 claim boundaries；不可变文献、方法和 style summaries 使用缓存。目标是降低重复上下文，同时不减少证据覆盖。

## 7. 人工确认点重新收敛

正常项目只保留三个集中确认点：

1. **研究蓝图与可行性确认**：中文 plan、claim、cohort、estimand、主图故事、统计设计和能力缺口一次展示。
2. **关键结果与论断支撑确认**：展示最终主图、支持/不支持的 claims、两条 rescue 路线和 evidence snapshot hash。
3. **最终论文确认**：展示 PDF、引用核查、两位独立审稿意见、未解决限制和 release hash。

普通 section acceptance、局部 reviewer repair、metadata merge 和编译重试不应成为用户必须逐条输入 hash 的人工点。系统必须区分：

- `draft_pdf_ready`：PDF 已生成，可供用户阅读，但未通过最终审稿。
- `review_blocked`：文件完整，但存在需要修订的审稿问题。
- `release_ready`：引用、审稿、可复现包和质量门全部通过，等待最终 release hash 确认。

## 8. 推荐实施顺序

### v0.26.1：状态机与恢复路线修复

- 修正 quality failure 分类，禁止默认回到 figure plan。
- 统一 functional release 与 LaTeX assembly 对 stale 的判断。
- 旧 blind-review hash 不得影响新 manuscript snapshot。
- 精确显示 hard-check 失败原因。
- 默认 CLI 改为摘要输出。

验收：citation stale 只推荐 citation audit；reproducibility failure 只推荐 bundle repair；局部 Methods 修订不重开 Data/figures。

### v0.26.2：Cohort/Provenance 语义核心

- 实现 DataProvenanceContract、CohortRegistry 和 CohortViewRegistry。
- 表格、panel、estimand、evidence 和正文绑定 cohort view。
- 增加 subset、count、missingness、split 和 join consistency gate。

验收：184-source display 与 183-source regression 可以共存，但没有显式 view/caption 时必须阻断。

### v0.26.3：ExecutableAnalysisSpec

- 建立 estimand、formula AST、resampling、calibration 和 run-selection schema。
- Methods 公式、代码接口、figure metadata 和 variable explanation 从同一 spec 生成。
- 对 paired/grouped/clustered 方法执行语义测试。

验收：事件概率 ECE 不可能被写成 confidence-accuracy ECE；非配对误差条不能标为 paired interval。

### v0.27.0：Capability Bootstrap 与执行闭环

- 插件充分性拆成 bootstrap/release 两层。
- project-local implementation passport 成为正式中间能力。
- GitHub/AcademicForge rescue 只在真实能力缺口时触发。

验收：全新课题可以在没有预置正式插件时先由 Agent 构建受审计方法代码，不形成充分性死锁。

### v0.27.1：Evidence/Claim/Figure 统一绑定

- Evidence Registry 2.0。
- section claim map。
- Figure Contract 2.0 和 journal-width render QA。
- DisciplineReviewCompiler 和 Results claim-level 审查。
- 图内文字、caption 和 claim boundary 一致性检查。

验收：同值多模型不再因措辞产生 ambiguous binding；selected comparison 不能在图内写 systematic。

### v0.27.2：事务化写作与精确 stale DAG

- `apply-section-revision` 和 revision receipt。
- artifact-level dependency graph。
- 精确 change class 与 section-level downstream claim dependency。

验收：公式修正、citation repair、caption 排版和主图替换分别触发不同的最小 stale 集合。

### v0.27.3：可复现包与盲审闭环

- dependency-closed、locator-safe anonymous bundle。
- selected-run 资产过滤和历史产物隔离。
- bundle smoke test。
- finding classification 与结构化修订路线。

验收：匿名包中的测试可以完成 collection；不存在导入缺失；两位审稿人只审核同一当前 bundle hash。

### v0.28.0：引用、效率和跨学科完整回归

- intent-aware citation audit。
- paragraph-job evidence retrieval 和缓存。
- 完成跨任务回归与文档发布。

## 9. 回归测试设计

不能再只验证文件存在或 JSON 字段。测试必须覆盖科学语义。

### 9.1 合成微型 fixture

至少建立：

- 分类任务：多 seed、同值不同模型、calibration、paired comparison。
- 回归任务：不同 outcome 使用不同 covariates 和 complete-case cohort。
- 空间任务：source-random 与 group-held-out、空间重叠和 acquisition group。
- 时间序列任务：source/event/observation 三种 sample unit。
- 生存或医学任务：censoring、patient-level split 和 missingness。

### 9.2 必须失败的语义测试

1. 184 与 183 被写成同一 cohort view。
2. source-level metric 被绑定到 observation-level claim。
3. ECE 定义与计算实现不一致。
4. 非 paired resampling 被标为 paired interval。
5. 最大 seed 被静默选为 primary。
6. 图内标题与 caption claim boundary 矛盾。
7. blind bundle 包含测试但缺少被导入模块。
8. 历史 run 表格进入当前审稿包。
9. citation-only 变化导致 method/figure stale。
10. quality failure 原因是 citation stale 却推荐 plan-figures。
11. Results rule 只检查 figure plugin trace，却没有检查正文对 estimand 的解释。
12. citation audit 重复运行统计或图表 review rule，并因 role adapter 错位产生新结论。
13. 未确认目标期刊却在 PDF 中写入 “Submitted to ...”。

### 9.3 必须通过的真实项目回归

- astronomy + machine learning 图像分类项目。
- astronomy + machine learning 不规则时间序列项目。
- geography/NDVI 空间回归或分类项目。
- bioinformatics/medicine patient/sample 分层项目。

真实项目用于验证通用性，不允许在核心中加入项目字段别名来“通过测试”。字段映射只能进入学科插件或 project-local contract。

## 10. 最终验收标准

完成本方案后，任意论文主张应能从最终 PDF 追溯到：

```text
manuscript claim
-> evidence ID
-> run ID
-> executable analysis spec
-> estimand + cohort view
-> data/method capability binding
-> research-plan claim
```

同时必须满足：

- cohort、sample unit、split、model、seed 和 metric dimension 无静默冲突。
- 公式与运行代码来自同一 analysis spec。
- 每个主图 panel 的统计含义和正文一致。
- 缺少外部 provenance 时明确标记 unknown，并自动收窄论断。
- 局部修订只使真正依赖它的产物 stale。
- final citation audit 晚于最后一次 manuscript assembly。
- 匿名审稿包依赖闭合、与当前 run 相关且不泄露隐私。
- 两位独立审稿人审核同一最终 bundle，不比较不存在的原稿。
- 即使最终审稿未通过，系统也能交付明确标记的完整 draft PDF；只有 release 状态被阻断。
- 所有硬失败都给出真实原因和唯一合理的下一步，不再用通用 `plan-figures` 或“重新跑全流程”兜底。

## 11. 优先级结论

最高优先级不是继续增加写作模板，而是依次完成：

1. CohortViewRegistry。
2. ExecutableAnalysisSpec。
3. Evidence Claim Map。
4. artifact-level stale DAG 和 failure router。
5. dependency-closed reproducibility bundle。

这五项解决后，Draftpaper-loop 才能稳定保证“同一份科学证据贯穿数据、方法、图表、Results、Discussion、引用核查和审稿”。Paper Narrative Engine 和 Codex 自由写作能力应建立在这套统一语义上，而不是继续依赖更多自然语言 gate 修补上游不一致。
