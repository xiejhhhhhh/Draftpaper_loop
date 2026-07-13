# Draftpaper-loop 全流程优化方案

日期：2026-07-13

适用基线：Draftpaper-loop v0.23.0 之后

本次确认：

- 两位独立盲评者只审查同一份冻结、匿名的生成论文，用于发现论文自身尚存的科学、证据、方法、图表、引用、叙事和排版问题；不提供原稿，不进行 A/B 对比，也不计算相对原稿的质量比例。
- Doctor、Recovery 和统一命令合同属于 Draftpaper-loop 必须直接实现的原生修复。gbrain doctor 只在开发阶段作为“输出是否覆盖问题分类、影响、可执行修复和恢复后复验”的一次性完整性参考，不提供 schema、字段、命令或运行时依赖。
- 首个陌生课题真实回归使用 Euclid Q1 VIS 与 DESI catalogue。形态学分析 DOCX 仅提供 idea seed 和数据语义，当前数据目录保持只读；既有正文、结论和图表不作为目标稿、标准答案或 reviewer 输入。

## 1. 方案范围

本方案以 Draftpaper-loop 当前流程、代码和真实项目问题为唯一主线。默认采用直接、常规、可维护的工程修复，不要求实现遵循 gbrain，也不把 gbrain 作为运行依赖。

只有满足以下条件时才选择性参考 gbrain：

1. gbrain 已经为同类问题提供了明显更完整的合同、评估或恢复闭环。
2. 参考该机制比 Draftpaper-loop 自行增加零散规则更容易验证和长期维护。
3. 该机制可以适配现有 evidence-first 科研边界，不引入不必要的数据库、检索服务或多 Agent 复杂度。
4. 引入后的收益可以用真实项目回归、路由指标、token 或恢复测试证明。

采用方式分为三类：

| 类型 | 适用内容 | 本方案处理 |
| --- | --- | --- |
| 直接修复 | 状态事务、旧项目版本化、参考文献格式、第三方来源、用户定点修改 | 按 Draftpaper-loop 自身需求实现 |
| 选择性参考 | capability pack 路由评估、按任务证据检索、capture/replay | 仅借鉴 gbrain 中显著成熟的合同形式 |
| 不引入 | gbrain 数据库、全量向量/图检索、通用多 Agent 运行时 | 不作为本路线组成部分 |

方案同时复核了 astronomy v0.23.0 全流程实跑、论文生成、token 统计和 59 项问题审计。历史开发阶段曾使用原稿对比定位流程缺陷，但该做法只属于框架研发诊断，不进入真实用户的论文生成、质量评估或发布验收流程。结论是：

> 天文项目最终完成了图表、正文、引用核查和 PDF，但审计问题没有全部闭环。部分修复只在该项目或单元测试中通过，部分仍为 observed，双独立盲评尚未执行，参考文献的“引用支撑正确”也不等于“出版格式正确”。

## 2. Astronomy 全流程问题复核

### 2.1 当前不能认定为完整解决

审计采用五种生命周期：

- observed：已复现，尚未形成完整修复。
- protected：下游 gate 能挡住错误，但上游生产逻辑仍未修好。
- corrected_in_worktree：代码修复存在，但项目级或一般性验证不足。
- verified_in_project：天文项目通过，但其他学科回归仍可能缺失。
- pending_general_regression：还没有证明对所有用户成立。

因此，“最终 PDF 成功生成”和“框架问题全部解决”是两件事。

### 2.2 审计状态总表

| 状态 | 审计项 | 当前判断 |
| --- | --- | --- |
| 天文项目已验证，但仍需一般性回归 | ASTR-001、033、034、036-047、049、052 | 项目可继续运行，但不能视为跨学科闭环 |
| 已有代码修复，审计未记录完整项目验证 | ASTR-002、003、008-011、013-015、017、035、055 | 需要 capture/replay 和跨项目验证 |
| 仅在测试中验证 | ASTR-057、058、059 | 需要真实完整项目重放 |
| 已在当前天文项目完整闭环 | ASTR-050 | 最终 citation audit 已绑定最后正文和 BibTeX hash |
| 部分解决 | ASTR-001、007、034、051 | 分别仍缺新项目 rescue 路由、运行等级展示、进一步 token 降本和双独立单稿盲评 |
| 尚未解决或仍为 observed | ASTR-004-006、012、016、018-032、048、053、054、056 | 必须纳入后续架构改造 |

### 2.3 未闭环问题的实际影响

| 问题组 | 审计项 | 对用户的影响 |
| --- | --- | --- |
| 插件充分性与代码生成闭环 | ASTR-001、007、023、024 | 新课题可能因“缺方法代码”被阻塞，却无法进入 Agent 补方法代码的阶段 |
| 历史 artifact 被当成当前证据 | ASTR-004、005、018-025、030-032 | 旧计划、旧插件报告、旧图表、旧 Results review 或旧 inventory 污染新运行 |
| 命令事务与 stale 状态不一致 | ASTR-017、021、025、026、029 | 官方命令刚写完文件，status 就把它识别为外部漂移或错误地把上游标 stale |
| 图表和结果解析选择错误证据 | ASTR-006、012、016、028、048、053 | 可能选择 generic metrics、错误模型、错误数据表，或用诊断图替代更有说服力的直接科学证据 |
| 路由给出不可执行命令 | ASTR-018、027 | 用户照着 status 的推荐执行仍会立刻失败 |
| 证据 registry 或 section 前置条件不足 | ASTR-019、030、031 | 正文可能从空 registry、stale manifest 或不完整 evidence snapshot 开始生成 |
| 上下文成本仍高 | ASTR-034、046、054 | 五节写作输入 122,238 tokens，输出只有 5,716 tokens，约为 21.4:1 |
| 双独立单稿盲评未完成 | ASTR-051 | 自动评分 0.9825 不能替代两位独立 reviewer 对同一份冻结生成稿的问题发现 |
| 参考文献角色判定不完整 | ASTR-055、056 | natbib 兼容判断曾误报，Data 中 provenance 与背景文献仍未区分 |
| 修复缺少跨学科重放 | 多个 pending_general_regression 项 | 天文项目修好不代表 geography、medicine 或陌生课题不会复发 |

以下优化工作包按 Draftpaper-loop 自身问题组织。每项会明确说明是否需要参考 gbrain；没有显著优势时直接修改。

### 2.4 旧项目到 _v1 的版本化迭代策略

#### 2.4.1 推荐结论

如果研究计划、数据、方法、核心图表或 evidence snapshot 将发生实质变化，推荐：

> 先创建一个全新的、空状态的 原项目名_v1 项目骨架，再通过受控导入清单选择性迁移可复用资产，最后在新项目中修改和重建。旧项目全程保持只读。

不推荐：

- 先修改旧项目，再把修改后的内容复制到 _v1。这样会破坏原始基线，无法判断资产究竟来自旧版本还是修改过程，也削弱回滚能力。
- 先复制整个旧项目，再逐项删除旧报告。这样最容易把旧 figure metadata、sufficiency report、project-local audit、passport、stage manifest 和 evidence snapshot 一起带入新版本。
- 依赖文件名中的 _v1 作为唯一版本依据。目录名便于人理解，但系统必须另外记录稳定 lineage metadata。

三种路线对比：

| 路线 | 优点 | 主要风险 | 判断 |
| --- | --- | --- | --- |
| 先改旧项目，再复制 | 操作直观 | 原基线被污染、难以回滚、来源不可分 | 拒绝 |
| 整目录复制，再在新目录修改 | 快速保留全部文件 | 历史状态和派生报告一起污染新版本 | 仅可用于人工备份，不作为正式流程 |
| 新建 _v1，再选择性导入 | 状态干净、来源清楚、可精确重验证 | 需要资产分类和导入合同 | 推荐 |

#### 2.4.2 什么时候需要新项目版本

需要创建 _v1：

- research idea 或主要 research questions 改变；
- claim contract 的核心推论改变；
- 数据来源、主要 cohort、sample unit 或 split 改变；
- 方法、模型或关键统计流程改变；
- 任意主图被替换或重新运行；
- 需要重新打开已经人工确认的 core evidence；
- 旧项目来自明显不同的 Draftpaper schema，原地迁移风险较高；
- 用户明确希望保留旧论文作为可比较基线。

不需要创建 _v1：

- citation audit 后局部收紧 claim；
- 不改变事实和引用的语言润色；
- 作者、单位、ORCID、致谢、基金、数据链接或代码链接修改；
- 排版、图注措辞或非科学 metadata 修正；
- 用户对单个段落进行受控补充，且没有改变数据、方法或结果证据。

这些局部修改使用当前项目内的 revision snapshot 和精确 stale propagation。

#### 2.4.3 新项目 lineage

新项目目录可命名为：

~~~text
<original-project-name>_v1
~~~

若已存在，则递增为 _v2、_v3。系统同时创建 project_lineage.json：

~~~json
{
  "project_id": "new-stable-project-id",
  "display_name": "original-project-name_v1",
  "parent_project_id": "old-stable-project-id",
  "parent_project_path": "../original-project-name",
  "parent_snapshot_id": "approved-or-latest-source-snapshot",
  "version_label": "v1",
  "fork_reason": "research_plan_change",
  "created_from_sha256_manifest": "lineage/source_asset_hashes.json",
  "old_project_mutated": false
}
~~~

项目 ID 必须重新生成，不能只复用旧 project_id。parent_project_path 只是本地提示，真正绑定以 project ID、snapshot ID 和 asset hashes 为准。

#### 2.4.4 旧资产分类

资产迁移不能使用“复制全部文件”规则，而应按下表处理。

| 资产类型 | 示例 | 新版本处理 |
| --- | --- | --- |
| 原始用户输入 | idea notes、用户约束、授权数据说明 | 复制为 imported source，并记录 hash |
| 大型原始数据 | FITS、CSV、影像、服务器导出 | 优先复用只读 locator/content-addressed storage；必要时复制并校验 hash |
| 文献原始信息 | DOI、URL、PDF locator、检索记录、人工确认结果 | 导入 reference source，重新构建 reference registry 和 library.bib |
| stage-owned 数据/方法代码 | data scripts、methods/src、测试 | 导入到 lineage/imported_code 或候选 stage 目录，标记 requires_revalidation |
| 处理后数据 | processed tables、features | 只有原始数据 hash、转换代码 hash、参数和环境均兼容时才可复用 |
| 人工确认主图 | approved figures | 保存为 baseline comparison asset；只有重新通过新 figure contract 才能成为 active evidence |
| 已接受正文 | accepted sections、旧 main.pdf | 保存为只读 legacy manuscript 或 style reference，不直接成为新版本 active manuscript，也不进入盲评输入 |
| 项目配置 | journal target、作者偏好、写作偏好 | 选择性复制，并重新验证当前 schema |
| 外部凭证 | API token、服务器账号 | 不复制；新项目要求用户重新授权 |

以下派生或运行状态默认禁止迁移为 active：

- project_passport.yaml；
- stage_manifest.json；
- artifact/checkpoint/integrity ledgers；
- figure_metadata.json；
- plugin_sufficiency_report.json；
- project_local_capability_audit.json；
- evidence registry 和 promoted snapshot；
- result_manifest、result validity 和 result support reports；
- section packets、outline、editor tasks；
- result discipline review；
- citation audit reports；
- quality reports；
- LaTeX aux、bbl、blg、log；
- caches、locks、temporary files。

如需保留这些内容，只能复制到 lineage/legacy_reports 供审计查看，不能被当前 status、resolver 或 gate 读取。

#### 2.4.5 推荐执行顺序

~~~mermaid
flowchart TD
    A["Freeze old project as read-only source"] --> B["Inspect assets and generate migration plan"]
    B --> C["Create clean project_name_v1 scaffold"]
    C --> D["Initialize new project ID, stage state and passport"]
    D --> E["Import allowlisted source assets with hashes"]
    E --> F["Place old figures, manuscript and reports under lineage baseline only"]
    F --> G["Apply new idea/research-plan changes in v1"]
    G --> H["Rebuild derived artifacts in dependency order"]
    H --> I["Revalidate data, methods, figures, writing and citations"]
    I --> J["Activate v1 after human confirmation"]
~~~

关键顺序是“先新建，再导入，再修改”，不是“先修改旧资产”。

#### 2.4.6 资产导入合同

新增 asset_import_plan.json：

- source project ID；
- source snapshot ID；
- source relative path；
- source SHA-256；
- target relative path；
- asset class；
- import mode：copy、read_only_reference、content_addressed_link、baseline_only；
- owner stage；
- compatibility checks；
- requires_revalidation；
- activation policy；
- privacy class；
- user confirmation。

推荐命令：

~~~text
draftpaper plan-project-version \
  --project <old-project> \
  --version v1 \
  --change-request <change.md>

draftpaper create-project-version \
  --plan <asset_import_plan.json>

draftpaper import-version-assets \
  --project <new-project> \
  --plan <asset_import_plan.json>

draftpaper validate-project-version \
  --project <new-project>
~~~

plan-project-version 必须只读。create-project-version 只创建新目录，不修改旧项目。import-version-assets 只能读取 old project 并写入 new project。

现有 migrate-project 继续只负责“同一项目原目录内的 schema、目录和 stage metadata 升级”，不能承担科学版本 fork。两条路线必须在 CLI help 和 doctor 中明确区分：

- migrate-project：科学内容不变，只升级 Draftpaper 项目结构。
- create-project-version：科学链或 approved evidence 变化，创建独立 _v1。

#### 2.4.7 兼容性判断

| 变化 | 可直接复用 | 必须重建或重验证 |
| --- | --- | --- |
| 只改标题或作者 metadata | 数据、方法、图表、正文证据 | LaTeX 和 final quality |
| 改 Introduction 问题表述但不改 claim | 数据、方法、图表 | Introduction、cross-section、citation audit |
| 改 research plan claim | 原始数据和文献来源 | capability、method/figure contracts、正文和全部派生报告 |
| 改数据 cohort/unit | 原始文件中未变化部分 | processed data、methods、figures、Results 和 Discussion |
| 改方法或模型 | 原始数据和已确认文献 | method run、figures、Results、Methods、Discussion |
| 替换主图 | 可复用未变化的 run outputs | figure metadata、core evidence、Results/Discussion 和 final audit |
| 仅更新参考文献 metadata | 数据、方法、图表 | library.bib、affected sections、citation/bibliography audits |

#### 2.4.8 版本化验收

- old project 在整个 fork 过程中 hash 不变。
- new project 启动时没有继承任何旧 stage status 或 passport baseline。
- 旧 figure metadata、sufficiency report 和 project-local audit 不能进入 active artifact graph。
- 每个导入资产可追溯到 source project、snapshot 和 SHA-256。
- 大型数据允许零复制复用，但必须是只读 locator 且 hash 可验证。
- baseline figures/manuscript 可以比较，但不能绕过新合同成为 active evidence。
- v1 创建失败时，旧项目不受影响。
- status 能明确显示 imported、revalidated、baseline_only 和 active 四种状态。

## 3. 优化一：项目状态权威层与可重建派生状态

### 3.1 采用方式：直接修复

这是 Draftpaper-loop 状态管理本身的问题，使用常规 artifact ownership、事务、hash 和派生状态设计即可解决，不需要依赖 gbrain。

gbrain 的 system-of-record 文档只作为设计检查表，帮助确认权威来源、派生状态、运行缓存和用户内容没有混在一起；它不是本项实现前提。

### 3.2 要解决的问题

该机制直接针对：

- ASTR-004：复制项目后 passport baseline 不正确。
- ASTR-005：旧 figure metadata 污染新合同。
- ASTR-018：下一条命令与 stage precondition 不一致。
- ASTR-019：上游 stale 时仍可确认 core evidence。
- ASTR-020：历史 Results review 覆盖新 snapshot。
- ASTR-021：官方命令写入被识别为外部 drift。
- ASTR-022：仅凭文件存在跳过当前 blueprint。
- ASTR-023：旧 sufficiency report 被新 capability contract 复用。
- ASTR-024：旧 project-local audit 跳过当前缺口审计。
- ASTR-025：research plan 改变后旧 promoted snapshot 仍保持激活。
- ASTR-026：只读语义复查错误地使 producer stages stale。
- ASTR-029：科学 gate 返回非零时，合法报告写入没有进入事务 baseline。
- ASTR-030：stale result manifest 进入写作 packet。
- ASTR-031：section preparation 可能生成空 evidence registry。
- ASTR-032：panel contract 可能读取历史宽泛 figure groups。
- ASTR-048：top-level integrity 仍展示历史 cohort。
- ASTR-050：citation audit 与最后正文版本绑定问题，当前项目已修复但需要纳入统一合同。

### 3.3 Draftpaper-loop 落地

新增 project_system_of_record.json，所有项目 artifact 分为五类：

| 类别 | 典型内容 | 规则 |
| --- | --- | --- |
| canonical_decision | idea、人工确认 research plan、claim route、接受的 section draft、核心证据确认、用户修订 | 只能由明确用户决定或受保护命令修改 |
| scientific_source | 数据定位符与 hash、stage-owned code、plugin manifest、run outputs、reference source | 可产生证据，但不得被派生报告覆盖 |
| approved_evidence | promoted evidence snapshot、已接受 figure/run/metric binding | 变化前必须显式 reopen |
| derived_rebuildable | registry、inventory、HTML report、section packet、status summary | 必须声明输入 hash，可安全重建 |
| runtime_private | cache、锁、临时下载、凭证、真实 eval capture | 默认不进入公开仓库 |

每个受管 artifact 增加：

- artifact_id
- category
- owner_stage
- writer_command
- input_artifact_ids
- input_sha256
- schema_version
- generator_version
- evidence_snapshot_id
- run_id
- privacy_class
- rebuild_command

所有 mutating CLI 命令使用统一事务：

1. 读取干净 baseline。
2. 声明预期写入列表。
3. 完成文件和 stage manifest 写入。
4. 无论科学 decision 是 pass、fail 还是 human_action_required，都提交合法受管写入。
5. 将 scientific_exit_code 与 transaction_status 分开记录。
6. 只有进程异常或越界写入才回滚事务。

新增命令：

~~~text
draftpaper inspect-system-of-record --project <project>
draftpaper rebuild-derived --project <project> --dry-run
draftpaper rebase-project-passport --project <project> --from <origin>
draftpaper verify-next-action --project <project>
~~~

status 和 run-pipeline 不再检查“文件是否存在”，而检查：

- owning stage 是否 current；
- artifact 输入 hash 是否匹配；
- run 和 snapshot 是否匹配；
- schema 是否兼容；
- 推荐命令的 precondition 是否可以立即满足。

### 3.4 验收

- 每一条 status 推荐命令都通过 dry-run precondition。
- mutating command 后立即运行 status，不出现 external drift。
- 旧 artifact 即使仍在磁盘，也不能进入当前 inventory、review 或 writing packet。
- 上游科学阶段 stale 时，core evidence confirmation 必须拒绝。
- 非零科学 decision 产生的报告和状态可被下一次 status 正确识别。
- canonical/source artifacts 可以重建全部 declared derived artifacts。
- ASTR-004、005、018-032、048 的最小重放全部通过。

## 4. 优化二：科研能力包与可测插件路由

### 4.1 采用方式：选择性参考 gbrain

当前插件数量已经较多，继续为每个插件零散增加匹配规则会快速失控。gbrain 的 skillpack 与 routing eval 在这里显著优于只改几个 if/alias，因此选择性参考以下结构：

- 主框架保留为稳定路由与执行壳；
- 专业判断、失败模式和适用条件放入能力 recipe；
- 每个能力包附带 manifest、routing eval、测试、runbook、changelog 和 license；
- resolver 只加载当前任务需要的能力。

### 4.2 要解决的问题

该机制直接针对：

- ASTR-001：插件充分性发生在 Agent 补代码之前。
- ASTR-003：project-local capability alias 不完整。
- ASTR-007：plan-only 插件被选中但没有真实科学输出。
- ASTR-023、024：当前 capability contract 与历史 sufficiency/audit 没有强绑定。
- ASTR-027：没有 eligible claim 却推荐 downgrade。
- 当前 209 个 manifest 和 213 个 template.py 只能证明“有插件”，不能证明“会选对插件”。
- 交叉学科项目尚缺 held-out routing precision/recall 证据。

### 4.3 Draftpaper-loop 落地

在现有 data_connector、method_template、review_rule 之上增加 Research Capability Pack。它不是第四类插件，而是组合和治理现有三类插件。

每个 pack 包含：

- pack_id、version、owner_discipline 和 secondary_disciplines；
- capability family 与 authoritative owner；
- data/method/review plugin IDs；
- input roles、output roles、scientific unit 和 claim boundary；
- minimum runtime level；
- routing triggers 和 forbidden triggers；
- project_local、registry、AcademicForge、GitHub rescue 优先级；
- failure modes；
- bootstrap runbook；
- routing_eval.jsonl；
- unit、E2E 和可选 LLM eval；
- changelog、license 和 provenance；
- supersedes、compatibility 和 migration_from。

插件充分性不再只有 sufficient/insufficient，而使用：

| 状态 | 后续路线 |
| --- | --- |
| ready_from_registry | 执行正式插件 |
| project_local_implementation_found | hash 绑定项目现有代码，再允许当前项目运行 |
| project_method_implementation_required | 打开受限 Agent 代码生成任务 |
| rescue_required | 依次查 registry、AcademicForge 和 GitHub 科研代码 |
| external_runtime_required | 生成 API/server/GPU task contract |
| unavailable_after_exhaustive_rescue | 只有该状态才真正阻断图表生成 |

每个 callable capability 至少准备五类 routing case：

- 典型正例；
- 同义表达；
- 相邻学科歧义；
- 明确负例；
- 交叉学科组合；
- 运行等级不足；
- project_local 与 formal plugin 冲突。

评估指标：

- top-1 accuracy
- precision
- recall
- critical capability miss
- wrong-discipline selection
- forbidden-plugin selection
- rescue success
- runtime-level violation

### 4.4 对新课题的正确流程

~~~mermaid
flowchart LR
    A["Research capability gap"] --> B["Audit project-local code/data"]
    B -->|found| C["Bounded project_local binding"]
    B -->|not found| D["Search formal registry"]
    D -->|not found| E["Search AcademicForge provenance registry"]
    E -->|not found| F["Search GitHub research repositories"]
    F -->|method identified| G["Agent generalizes or implements project method"]
    G --> H["Execute and validate outputs"]
    F -->|exhausted| I["Block with human checkpoint"]
~~~

这能解除“缺方法所以不能生成代码，但不生成代码又无法补方法”的闭环。

### 4.5 验收

- 新课题缺方法时必须先进入 project_method_implementation_required，而不是直接阻断。
- 只有四条 rescue 路线全部留下审计记录后，才允许 unavailable_after_exhaustive_rescue。
- plan-only、fixture-runnable、project-validated 和 live-runnable 分开显示。
- capability contract hash 改变后，旧 sufficiency report 自动失效。
- sufficiency assessment generation ID 改变后，旧 project-local audit 自动失效。
- synthetic held-out top-1 accuracy 不低于 95%。
- critical wrong-discipline selection 为 0。
- ASTR-001、003、007、023、024、027 在陌生项目 replay 中通过。

## 5. 优化三：面向任务的 Evidence Resolver 与 token budget

### 5.1 采用方式：常规 resolver 实现，选择性参考评估方法

Draftpaper-loop 已有结构化 evidence IDs，直接实现确定性 resolver 即可，不需要引入 gbrain 的数据库或完整检索栈。

gbrain 的 retrieval 文档只在以下方面具有明显参考价值：

- 按任务意图选择来源；
- 不把全部知识一次性装入；
- 每个来源独立排序；
- 保留 evidence metadata；
- 强制 token budget；
- 每个检索阶段可独立测试和替换。

第一阶段应优先利用 claim、run、figure、formula、citation 和 cohort 的显式关系。

### 5.2 要解决的问题

该机制直接针对：

- ASTR-006：一个宽泛表被多个异质 figure group 共用。
- ASTR-012：generic metrics 和 identifier 图通过结构检查。
- ASTR-016：不同模型的指标被平均成一个 scalar。
- ASTR-028：result support 复用历史 generic F1。
- ASTR-030-034：stale/oversized evidence 进入写作 packet。
- ASTR-044、046：literature 和 method ledger 曾被漏掉或过量嵌入。
- ASTR-053：合同有效的 cohort diagnostic 替代了更直接的观测信号示例。
- ASTR-054：122,238 输入 tokens 对应 5,716 输出 tokens。

### 5.3 Draftpaper-loop 落地

新增两类 resolver。

#### Figure Evidence Resolver

每张 panel 从 semantic figure contract 出发，按以下顺序解析：

1. scientific question
2. required data roles
3. scientific unit
4. cohort/split/model/run
5. required method output
6. metric dimension
7. approved output table
8. rendered figure metadata

禁止：

- 选择目录中最大或第一个可读表；
- generic metrics 覆盖 model-qualified evidence；
- 跨模型平均 primary metric；
- 用 identifier-versus-identifier 代替科学变量；
- 用 cohort diagnostic 静默替代 direct scientific signal。

Figure narrative recipe 为每个项目动态识别：

- direct scientific signal；
- study/cohort boundary；
- pre-model structure；
- primary comparison；
- ablation/component attribution；
- uncertainty/error/boundary；
- supporting diagnostics。

这些是角色，不是固定六图模板。一个 multi-panel group 可以同时承担多个相邻角色。

#### Paragraph Evidence Resolver

写作上下文分为：

- section_context_index.json：章节允许使用的 evidence IDs 和边界；
- paragraph_evidence_slice.json：当前 paragraph job 的完整证据切片。

每个 slice 只包含：

- selected evidence IDs；
- compact excerpts；
- bound numbers；
- relevant figure/table/formula；
- citation roles；
- allowed interpretations；
- forbidden moves；
- omitted candidates and reasons；
- token count；
- source hashes。

完整 ledger 继续留在磁盘，只通过 artifact ID 和 hash 引用。

每节设置 hard budget：

| Section | 强制保留 | 可压缩内容 |
| --- | --- | --- |
| Results | 当前 run 数字、figure findings、comparison、uncertainty、claim boundary | 重复合同说明 |
| Introduction | problem/gap/hypothesis、role-specific literature | 方法运行 ledger |
| Data | provenance、cohort、unit、coverage、missingness | 性能结果 |
| Methods | stage code、formula、variables、validation、ablation | 重复插件事件 |
| Discussion | current findings、comparison literature、limitations | 完整原始 registry |

### 5.4 验收

- 五节 observable input tokens 从 122,238 降到不高于 73,343。
- Results 输入从 38,245 至少下降 40%。
- 所有 bound number、claim、figure、formula、citation role 和 boundary 召回率为 100%。
- resolver 选择正确的 0.8667、0.8486、0.8053 和 0.8205 model-qualified evidence。
- 不允许 generic 0.5002 指标覆盖当前 run。
- direct scientific signal 与 cohort diagnostic 同时需要时，使用 multi-panel 或 supporting role，不互相替代。
- ASTR-006、012、016、028、030-034、044、046、053、054 replay 通过。

## 6. 优化四：参考文献与期刊格式合同

### 6.1 采用方式：直接修复

这是明确的 BibTeX metadata、模板渲染和期刊适配问题。应直接实现 Journal and Bibliography Contract，不需要先抽象成 gbrain 风格的 schema pack。

合同仍需版本化，并采用 detect -> suggest -> human review -> apply，是因为参考文献版本合并和期刊格式选择本身需要审计，而不是因为要遵循 gbrain。

### 6.2 当前天文项目确认的问题

当前 citation audit 已证明：

- 12/12 retained references 均被引用；
- 25 个 citation usages 中没有 unsupported 或 blocking；
- audit 绑定最后正文和 BibTeX hash。

但这只证明“引用支撑关系正确”，没有证明“参考文献出版格式正确”。

实际检查发现：

1. journal_profile.json 声明 bibliography_style 为 aasjournalv7，但 latex/template/main.tex 硬编码 aasjournal，最终 main.tex 和 main.bbl 实际使用旧 aasjournal.bst。
2. 同一 Dillmann 2024 工作同时保留期刊版与 arXiv 版，生成 2024a/2024b，看起来像两篇不同研究。
3. 多数预印本用 journal = arXiv 或 arXiv.org，而没有规范 eprint、archivePrefix 和 primaryClass。
4. 已发表论文缺少 volume、issue、pages/article number 等字段。
5. 一些 URL 指向 Semantic Scholar 页面，而不是 DOI 或出版社 canonical URL。
6. FALCO、GECAM、XRT、X-rays、Time2Vec 等大小写需要 BibTeX braces 保护，否则 bst 会改成 Falco、Gecam 或 xrt。
7. 作者信息来自不同聚合源，可能出现全名、缩写和姓氏结构不一致。
8. citation audit 当前使用正则读取 BibTeX，适合 key/字段存在性检查，但不适合作为完整 BibTeX parser 和 metadata validator。
9. ASTR-055 的 AASTeX/natbib 误报虽已修正代码，但 focused quality-gate verification 尚未记录完成。
10. ASTR-056 的 Data provenance、instrument definition、processing support 和 background 引用角色仍未完整区分。

PDF 中的 References 可读，但元数据不够 publication-ready，长 URL、重复工作和大小写丢失会降低专业度。

### 6.3 Draftpaper-loop 落地

新增 reference_registry.json 作为规范化元数据来源，library.bib 变为可重建派生 artifact。

每条 reference record 包含：

- canonical_work_id
- citation_key
- work_type
- structured_authors
- title_original
- title_bibtex_protected
- year
- journal
- volume
- issue
- pages_or_article_number
- publisher
- doi_normalized
- canonical_url
- arxiv_id
- eprint
- archive_prefix
- primary_class
- publication_status
- related_versions
- preferred_citable_version
- metadata_sources
- field_confidence
- user_confirmed

新增 bibliography_contract.json：

- target journal；
- document class；
- bibliography style；
- bst source、version 和 SHA-256；
- BibTeX/Biber engine；
- required fields by entry type；
- name formatting；
- DOI/URL policy；
- preprint policy；
- title capitalization policy；
- duplicate/version policy；
- hyperlink policy。

编译前流程：

~~~text
import metadata
  -> normalize DOI/arXiv/authors/title
  -> detect duplicate works and related versions
  -> suggest preferred citable version
  -> human confirm
  -> render library.bib
  -> enforce journal bibliography style in main.tex
  -> compile
  -> inspect bbl/log/rendered reference pages
  -> bibliography quality report
~~~

关键实现规则：

- 使用结构化 BibTeX parser，不再依赖正则完成元数据规范化。
- journal profile 是 bibliography style 的唯一来源。
- 即使模板硬编码旧 style，也必须由 assembler 规范化为当前 pack style。
- bibliography style 必须写在 bibliography data command 前，并与实际 aux/bbl 一致。
- published article 默认优先于 preprint，但合并或保留版本必须由用户在写作前确认。
- citation audit 阶段仍坚持不删 retained references；去重和版本选择发生在文献元数据确认阶段。
- background 文献可以在 Introduction/Discussion 满足 coverage；dataset provenance、instrument/product definition 和 processing-method support 才要求在 Data 精确引用。
- DOI 和 URL 在 HTML 报告中为超链接，PDF 中遵循目标期刊 bst。

新增命令：

~~~text
draftpaper build-reference-registry --project <project>
draftpaper inspect-reference-duplicates --project <project>
draftpaper resolve-reference-version --project <project> --work <id>
draftpaper validate-bibliography --project <project>
draftpaper render-reference-proof --project <project>
~~~

### 6.4 验收

- APJS 项目实际使用 aasjournalv7，profile、main.tex、aux、bbl 和 compile manifest 五处一致。
- 同一 work 不会在没有明确用户决定时生成伪 2024a/2024b。
- arXiv、期刊、会议和数据集条目分别满足 required fields。
- DOI 统一为裸 DOI 值，URL 使用 canonical HTTPS。
- 缩写和专名大小写在最终 PDF 中保持正确。
- BibTeX parser 能处理嵌套 braces、LaTeX accents 和多行字段。
- bibliography quality report 同时检查 metadata、duplicate、style、compile warnings、URL/DOI 和页面渲染。
- citation support audit 与 bibliography format audit 分开显示。
- ASTR-055、056 完成项目级和跨期刊 fixture 验证。

## 7. 优化五：第三方来源与递归 provenance 注册表

### 7.1 采用方式：直接修复

这是正常的开源许可证、署名和供应链治理要求。直接建立 third_party registry、notice 和 plugin provenance 即可。

gbrain 自身作为被参考的开源项目，也应像 AcademicForge 和其他来源一样进入该注册表，但不需要采用 gbrain 的目录结构。

### 7.2 当前问题

当前 third_party 中只有 paper-fetch-skill 的完整快照。

正式 discipline plugin manifests 中没有显式记录 AcademicForge 或 HughYau。多数批量基础插件只写：

> First-party foundation distilled from publicly documented local scientific Python capabilities; no upstream source code is copied.

这能说明没有直接复制源码，但不能回答：

- 哪个插件受哪个 skill 或项目启发；
- 当时参考的上游 commit；
- 是复制、改写、分类借鉴还是只参考 API 文档；
- 上游许可证是否允许该种使用；
- AcademicForge 中的 skill 实际来自哪个原始仓库；
- 上游更新后是否需要重新审查。

AcademicForge 本身是聚合层。其 root LICENSE 对 forge 结构使用 MIT，但明确要求 individual skills 继续遵循各自原始许可证。因此只记录 AcademicForge 不够，必须递归追溯原始 skill repository。

### 7.3 Draftpaper-loop 落地

新增 third_party/registry.json，记录所有 vendored、adapted、inspired 和 runtime dependency 来源。

建议目录：

~~~text
third_party/
  registry.json
  THIRD_PARTY_NOTICES.md
  paper-fetch-skill/
  academicforge/
    UPSTREAM.json
    LICENSE.snapshot
    ATTRIBUTION.snapshot.md
    INFLUENCE_MAP.json
  gbrain/
    UPSTREAM.json
    LICENSE
    INFLUENCE_MAP.md
  upstream-skills/
    <owner>__<repo>/
      UPSTREAM.json
      LICENSE.snapshot
      MAPPING.json
~~~

不要求完整 clone 每个项目。根据使用方式选择：

| use_mode | third_party 留存方式 |
| --- | --- |
| vendored_code | 代码快照、LICENSE、commit、修改记录 |
| adapted_code | 来源路径、commit、license、diff/改写说明 |
| derived_template | 上游 skill 路径、抽象映射、未复制源码声明 |
| taxonomy_inspiration | URL、commit、影响范围和设计映射 |
| documentation_reference | 文档 URL、访问版本、用于哪些字段 |
| runtime_dependency | package name/version/license/SBOM，不复制源码 |

AcademicForge 的 provenance 必须形成递归图：

~~~text
Draftpaper plugin
  -> AcademicForge catalog entry
  -> original skill repository
  -> exact skill path
  -> upstream commit
  -> original license
  -> Draftpaper transformation type
  -> generated manifest/template/review rule paths
~~~

plugin manifest 增加：

- upstream_refs
- catalog_ref
- original_repository
- original_skill_path
- upstream_commit
- license_spdx_or_expression
- license_file
- derivation_kind
- copied_code
- copied_text
- transformed_fields
- attribution_required
- provenance_reviewed_at

promote-plugin-candidate --write 必须：

1. 解析 source skill 的直接和传递来源。
2. 检查 license 是否明确。
3. 生成 provenance record。
4. 将 record ID 写入正式 plugin manifest。
5. 更新 THIRD_PARTY_NOTICES.md。
6. 若许可证不明确，只允许 candidate/local，不允许正式 promote。

当前从 gbrain 借鉴本方案时，也应在 third_party/gbrain 下保留最小来源指针、MIT LICENSE 和 influence map，而不需要复制 gbrain 全仓库。

### 7.4 验收

- 所有非纯 first-party 插件都能追溯到直接上游和原始上游。
- AcademicForge catalog 不能成为 provenance 链的终点。
- third_party registry 中的 commit、URL 和 license 文件可验证。
- 每个 formal plugin 的 upstream_refs 在 registry 中存在。
- wheel/sdist 包含 THIRD_PARTY_NOTICES 和所需许可证。
- CI 阻止 license unknown 的候选进入 formal registry。
- CI 阻止 copied_code=true 但缺少 source path、commit 或 license 的提交。
- public repo 不包含不必要的第三方完整源码、私有文件或凭证。

## 8. 优化六：Eval Capture、Replay、Calibration 与两位独立盲评者

### 8.1 采用方式：选择性参考 gbrain

当前大量问题只记录在 Markdown 审计中，缺少可重放状态。gbrain 的 capture -> baseline -> replay -> gate 闭环在这里明显优于继续手写回归描述，因此参考其分层方式：

- capture；
- baseline；
- replay；
- correctness gate；
- regression gate；
- quality calibration；
- 本地真实 capture 与公共合成 baseline 分离。

这里的 baseline 只表示软件回归基线，即 schema、artifact topology、命令结果和科学不变量的期望状态；它不是原稿、人工稿、目标文风稿或用于计算论文质量比例的 manuscript baseline。任何原始论文均不得因为 eval capture/replay 被带入 reviewer 输入。

### 8.2 要解决的问题

该机制直接针对：

- 大量 corrected_in_worktree 或 pending_general_regression 项没有完整重放。
- ASTR-051 仍为 protected，双独立盲评未完成。
- 自动 0.9825 分数不能代替两位独立 reviewer 对完整稿件的实际问题发现。
- 当前 blind_quality.py 仍围绕 generated/baseline quality ratio 设计，不符合真实科研中通常没有“一模一样原稿”可比较的场景。
- 当前流程只生成 JSON 模板并导入结果，没有生成单稿盲审包、两个独立报告和修订闭环。
- 同一会话连续生成两份评价不能证明 reviewer independence。
- 审计问题主要保存在 Markdown，无法自动证明后续版本没有复发。

### 8.3 Local Eval Capture

新增：

~~~text
draftpaper eval capture --project <project> --case <id>
draftpaper eval baseline --capture <path>
draftpaper eval replay --baseline <path>
draftpaper eval gate --report <path>
~~~

capture 默认只保存：

- artifact topology；
- schema/version；
- content hash；
- stage state；
- command sequence；
- route decision；
- expected invariant；
- failure class；
- redaction report。

真实正文、数据、凭证、服务器地址和完整私有提示默认不保存。公共仓库只保留合成或去标识 fixture。

gate 分开：

- structural regression；
- scientific semantic correctness；
- plugin routing；
- bibliography format；
- citation support；
- manuscript writing quality；
- token/cost；
- latency/retry。

### 8.4 两位独立盲评者完整流程

#### 8.4.1 不可变评审边界

两位独立盲评者承担的是**生成论文质量审计**，不是模板稿与原稿的相似度或优劣比较。该边界属于产品合同，而不只是本次测试约定：

- 输入只有同一份匿名、冻结的 Draftpaper-loop 生成稿及其正式图表、表格和参考文献页面；
- 不向 reviewer 提供原稿、历史稿、DOCX 内容、baseline manuscript、自动评分或其他 reviewer 的结论；
- 不计算“达到原稿百分之多少”、文本相似度、A/B 胜率或相对原稿质量比例；
- reviewer 只判断论文自身是否科学正确、证据一致、方法可复现、图表与正文相符、引用合理、叙事完整且排版达到学术要求；
- 两份独立报告用于发现剩余问题、确认共同风险，并生成后续 revision queue。

历史原稿对比只允许作为 Draftpaper-loop 开发阶段定位框架缺陷的离线诊断工具，不能进入真实用户工作流、盲评 bundle、发布 gate 或质量分数。

目的不是比较 Draftpaper 生成稿与某份原稿，而是回答：

1. 当前生成论文是否达到可继续投稿或人工精修的质量。
2. 是否存在自动 gate 尚未发现的科学、方法、图表、引用、叙事或排版问题。
3. 两位独立 reviewer 是否对关键风险形成一致判断。
4. 哪些发现必须进入后续 revision queue。

本阶段采用“单稿、双 reviewer、独立盲审”合同。真实使用时通常不存在同题原稿，因此论文质量只依据当前冻结生成稿的科学正确性、证据一致性、方法可复现性、图表解释、引用、叙事和排版进行绝对评价。历史上用于开发流程的原稿对比到此终止，不属于产品工作流，也不属于发布验收。

新增 prepare-independent-manuscript-review：

1. 冻结当前生成稿 main.pdf、LaTeX sections、figures、tables、reference registry 和 evidence snapshot 的 SHA-256。
2. 移除作者身份、开发者标记、内部路径、自动质量分数、既有审计结论和其他会暗示生成过程的内容。
3. 生成一份匿名 submission bundle；不存在 Manuscript A/B，也不存在原稿或 baseline manuscript。
4. reviewer 1 和 reviewer 2 分别在独立 task/session 中读取同一个冻结 bundle。
5. 两位 reviewer 不能看到对方报告、自动 gate 分数或上一轮修订建议。
6. 两位 reviewer 必须检查完整正文、真实 figures、tables 和 References 页面。

评审输入合同必须显式拒绝原稿、baseline manuscript、A/B 映射、历史质量比例和任何可用于反推“模板稿是否接近原稿”的材料。盲评的对象始终是当前冻结生成稿本身；历史稿件即使存在，也只能留在 lineage/baseline_assets，不能进入 reviewer bundle 或评分提示。

每位 reviewer 单独输出：

~~~text
quality_checks/blind_reviews/reviewer_01/report.json
quality_checks/blind_reviews/reviewer_01/report.md
quality_checks/blind_reviews/reviewer_02/report.json
quality_checks/blind_reviews/reviewer_02/report.md
~~~

每份报告包含：

- reviewer anonymous ID；
- independent session/provider ID hash；
- frozen submission bundle hash；
- overall recommendation：accept_for_revision、minor_revision、major_revision、not_ready；
- scientific correctness score；
- critical、major、minor 和 advisory findings；
- page/section/figure grounded findings；
- 数字、cohort、sample unit、split、model 和 claim consistency；
- 图表是否回答 research questions；
- Data/Methods 是否可复现；
- citation support 与 bibliography format；
- strengths；
- weaknesses；
- required revisions；
- confidence；
- 是否完整检查真实 figures。

评分维度继续使用：

- scientific story and main-figure narrative；
- Results interpretation and comparison；
- reproducible Data/Methods；
- Introduction problem/gap/contribution；
- Discussion comparison/mechanism/limitation/innovation；
- figure readability/panel logic/captions；
- prose naturalness/cross-section coherence。

新增聚合产物：

~~~text
quality_checks/blind_reviews/aggregate.json
quality_checks/blind_reviews/aggregate.md
quality_checks/blind_manuscript_evaluation.json
~~~

schema 调整：

- manuscripts_blinded 改为 submission_anonymized；
- full_manuscript_compared 改为 full_manuscript_reviewed；
- real_figures_compared 改为 real_figures_reviewed；
- overall_quality_ratio 改为 absolute_quality_score；
- quality_claim_eligible 改为 release_review_status；
- 删除 baseline hash、A/B mapping 和 relative ratio 字段；
- 增加 finding severity、artifact locator、required action 和 resolution status。

删除面向 Manuscript A/B 和 generated/baseline ratio 的旧运行入口。新项目统一使用 prepare-independent-manuscript-review、record-independent-manuscript-review 和 assess-manuscript-quality-release。若需要读取历史报告，只允许离线迁移工具提取可复用 finding；历史 baseline hash、A/B mapping、relative ratio 和 parity 结论不得进入新 review schema、release gate 或 reviewer prompt。

若两位 reviewer：

- 关键科学结论冲突；
- overall recommendation 相差两个以上等级；
- 一位报告 critical error；

则进入 adjudication_required，而不是简单平均。可以邀请第三位独立 reviewer。

聚合报告只总结当前论文的质量和问题，不计算 generated/baseline ratio，也不再发布“达到某原稿 95%”的结论。

release decision 建议使用：

- critical findings = 0；
- unresolved major findings = 0；
- scientific correctness 达到项目硬门；
- 两位 reviewer 都确认完整检查；
- reviewer disagreement 已解决；
- 所有必须修改项都有 accepted、rejected_with_reason 或 deferred_with_boundary 状态。

如项目希望保留 0.95 数值，它只能表示当前稿件的绝对质量阈值，不再表示相对某份原稿的比例，而且必须预先声明 rubric 与计算方式。

独立性规则：

- 同一对话上下文重复两次不算独立。
- reviewer 不能读取另一份报告。
- reviewer 不参与待评稿件生成。
- Agent reviewer 需要独立 task/session；也支持真实人类 reviewer 导入。
- 报告必须引用可核查页面或图表，不能只给分数。
- 不需要准备或提供原始人工稿件。

### 8.5 验收

- 当前完整生成稿产生一份冻结、匿名的 submission bundle。
- 两位独立 reviewer 分别给出 Markdown 和 JSON 审稿报告。
- 两份报告均检查完整 PDF 和真实 figures。
- 两位 reviewer 均未读取自动评分、既有审计结论或对方报告。
- 每条 finding 有严重级别、页面/章节证据和修订建议。
- scientific correctness 必须满足项目硬门。
- aggregate report 明确共同问题、分歧和 revision queue。
- 不再要求原稿、A/B 映射、解盲或稿件质量比例。
- ASTR-051 从 protected 变为 verified_in_project。
- 所有 pending_general_regression 修复都至少在一个陌生主题 replay。

## 9. 优化七：Doctor、Recovery 与统一命令合同

### 9.1 采用方式：直接修复

结论明确为：这是 Draftpaper-loop 的直接修复，不采用 gbrain doctor 作为实现结构，也不继承其输出字段合同。

换言之，`doctor` 和 `recover` 都是需要直接开发、测试并发布的 Draftpaper-loop 原生命令，不是只写一份诊断报告，也不是把 gbrain Doctor 包一层。gbrain Doctor 仅在开发阶段充当一次性的字段完整性检查参考，用来提醒维护者是否遗漏“问题分类、影响、可执行修复、恢复后复验”等基本信息；最终字段、状态语义、恢复动作和退出码全部由 Draftpaper-loop 自身的项目状态机和科研工作流决定。

| 判断项 | 最终决定 |
| --- | --- |
| 是否直接修改 Draftpaper-loop | 是。实现原生 `doctor`、`recover`、`CommandSpec`、事务和可执行修复命令 |
| 是否复制或适配 gbrain doctor | 否。命令、schema、字段名和运行时均不继承 |
| gbrain doctor 的唯一用途 | 开发期人工检查输出是否覆盖“问题分层、可执行建议、恢复后复验”三类完整性 |
| 是否形成运行依赖 | 否。移除 gbrain 后 Draftpaper-loop Doctor 仍须完整工作并通过测试 |

直接基于 Draftpaper-loop 自身的 stage、stale、evidence snapshot、plugin sufficiency、CommandSpec 和 transaction 语义，统一 precondition、finding schema、恢复建议与退出策略。Doctor 的字段由 Draftpaper-loop 实际故障模型推导；gbrain 文档至多作为开发时的一次性完整性检查清单，不进入代码合同、字段来源、运行依赖、版本路线或验收标准，也不需要因为 Doctor 单独建立 gbrain-derived 模块。

因此本项的实施判断是：

- 直接修复 Draftpaper-loop 的 status、doctor、recovery、CLI parser、CommandSpec 和 transaction 行为；
- Doctor 输出字段必须来自 Draftpaper-loop 自身可计算的项目状态，不能为了对齐外部项目而增加无事实来源的字段；
- gbrain doctor 只可用于开发期人工复核“错误是否被分层、建议是否可执行、恢复后是否可复验”，不复制其命令、schema、字段名或运行时；
- 即使 gbrain 不可访问或被移除，Draftpaper-loop Doctor 的实现、测试和文档也必须完整成立。

### 9.2 要解决的问题

该机制直接针对：

- ASTR-018：status 推荐不可执行命令。
- ASTR-021：正常写入被识别为 drift。
- ASTR-025：需要 reopen snapshot 却晚到 codegen 才报错。
- ASTR-027：没有 downgrade target 却推荐 downgrade。
- ASTR-029：科学失败与事务失败混为一谈。
- 当前约 134 个 parser 只有 12 个 CommandSpec。
- 用户难以区分环境问题、插件问题、证据问题和人工科学决策。

### 9.3 Draftpaper-loop 落地

增加 draftpaper doctor --json，检查：

- environment；
- project system of record；
- stage/stale；
- evidence snapshot；
- plugin sufficiency；
- plugin routing ambiguity；
- project-local code；
- external API/server/GPU；
- figure/run binding；
- reference metadata；
- citation support；
- blind review；
- PDF toolchain；
- token budget；
- revision state。

每个 finding 包含：

- finding_id
- category
- severity
- cause
- impact
- confidence
- affected_artifacts
- automatic_or_manual
- next_command
- precondition_check
- estimated_stale_scope

普通用户入口收敛为：

~~~text
draftpaper start
draftpaper continue
draftpaper doctor
draftpaper review
draftpaper recover
draftpaper revise
~~~

专家命令继续保留，但 parser、help、handler、transaction、stage ownership、exit policy 和 stale effects 必须进入同一 CommandSpec registry。

### 9.4 验收

- doctor 完全只读。
- 相同状态连续执行 doctor 输出一致。
- 每条 next_command 均可通过 precondition dry-run。
- 新增 parser 未注册时 CI 失败。
- 用户不需要通过审计日志猜测下一步。
- doctor 不自动接受图表、降低 claim、删除参考文献或 promote 插件。

## 10. 优化八：用户定点修订与受保护版本历史

### 10.1 采用方式：直接实现，迁移保护可选择性参考

用户修订主要通过 source map、revision ledger、change classification 和 preview/rollback 直接实现。

只有以下迁移保护模式可选择性参考 gbrain 的 pack upgrade：

- migration preview；
- protected/manual-only migrations；
- lock；
- pre/post state verification；
- audit log；
- rollback metadata；
- downgrade/recovery。

这些模式本身也属于常规版本化设计。Manuscript Revision Workspace 不依赖 gbrain。

### 10.2 当前问题

当前已有 section draft submit/accept 和 review revision，但缺少一个面向最终作者的完整修改窗口：

- 用户不能稳定按 LaTeX 行号或段落定位提交修改。
- 行号会随修改漂移。
- 作者、单位、ORCID、致谢、基金、数据链接和代码链接仍可能是 placeholder 或框架默认值。
- 新增参考文献缺少统一 metadata -> summary -> citation -> audit 流程。
- 用户自定义段落可能被后续 writer 重写。
- 审稿意见不能直接转换为可跟踪 revision tasks。
- 修改后缺少最小 stale propagation 和最终 main.pdf 复核链。

### 10.3 Manuscript Source Map

生成 latex/manuscript_source_map.json：

- file；
- section；
- paragraph_id；
- line_start；
- line_end；
- LaTeX environment；
- figure/table/equation/citation anchors；
- before_hash；
- evidence IDs；
- origin：generated、user、reviewer_revision；
- locked_by_user。

用户可以使用行号：

~~~text
draftpaper revise --project <project> \
  --at latex/sections/discussion.tex:42-48 \
  --instruction "在此段后补充与某研究的比较，并保持现有结论边界"
~~~

系统同时把行号解析为 stable paragraph_id 和 before_hash。后续行号变化时：

- paragraph_id 与 context hash 一致则继续定位；
- 只匹配到上下文则提出重新定位预览；
- 无法唯一定位则停止，不猜测修改位置。

### 10.4 用户 metadata

新增 manuscript_metadata.yaml，独立管理：

- title；
- authors；
- affiliations；
- corresponding author；
- email；
- ORCID；
- CRediT contributions；
- acknowledgments；
- funding；
- data availability；
- code availability；
- competing interests；
- ethics/consent；
- supplementary material；
- repository and DOI links。

LaTeX assembler 从该文件渲染，不再把 placeholder 或固定 Draftpaper acknowledgment 当成最终内容。

### 10.5 Revision Request

每次修改生成 revision_request.json：

- revision_id；
- target file/line/paragraph；
- operation：insert_before、insert_after、replace、delete、metadata_update；
- user instruction；
- exact user text；
- expected before hash；
- affected claims；
- added references；
- change class；
- required gates；
- preview status；
- user acceptance。

支持两种模式：

1. exact_text：用户提供的原文必须原样保留，Codex 只处理 LaTeX escaping 和位置。
2. instruction_to_codex：Codex 根据指令提出 patch，但用户必须先看 diff 和 PDF preview。

用户锁定的 exact_text 不允许后续 writer 静默覆盖。

### 10.6 Change Classification

| 修改类型 | stale 范围 |
| --- | --- |
| 作者、单位、ORCID、致谢、基金 | metadata、LaTeX、PDF、final quality |
| 数据/代码 availability 链接 | metadata、link check、LaTeX、PDF |
| 纯语言润色且不改 claim/citation | 当前 section、integrity、PDF |
| 新增或移动 citation | 当前 section、citation audit、PDF |
| 新增 reference | reference registry、literature evidence、当前 section、citation audit、PDF |
| 收紧 claim | 当前 section、cross-section consistency、citation audit、PDF |
| 改 Results 数字或图表解释 | Results/Discussion、discipline review、citation audit、PDF |
| 替换数据、方法、run 或核心图表 | reopen evidence，重新打开对应科学链 |

这使 citation audit 修订不会无意义地 stale 全文，也防止核心证据变化后只改一段文字。

### 10.7 审稿意见到 revision queue

两位独立盲评报告完成后：

~~~text
draftpaper import-review-findings --review <report.md>
draftpaper list-revision-tasks --project <project>
draftpaper prepare-revision --task <id>
draftpaper preview-revision --revision <id>
draftpaper accept-revision --revision <id>
~~~

review finding 只生成候选任务，不自动改正文。

### 10.8 最终输出

每次 preview 生成：

- unified diff；
- change classification；
- stale impact；
- evidence/citation warnings；
- revision_preview.pdf；
- rollback point。

用户 accept 后：

1. 写入 revision ledger。
2. 运行最小必要 gates。
3. 重新 assemble LaTeX。
4. 对最后正文运行 citation audit。
5. 运行 bibliography format audit。
6. 运行 final quality。
7. 输出最终 latex/main.pdf。

任何后续修改都会使先前 final citation audit 和 blind-review snapshot stale。是否需要重新盲评由修改类型决定：

- metadata/presentation-only 不重跑科学盲评；
- 局部语言修订只重跑受影响维度；
- 科学 claim、图表、数据或方法变化必须重新进行相应审查。

### 10.9 验收

- 用户可按 file:line-range 或 stable paragraph ID 精确修改。
- 行号漂移时不会误改其他段落。
- 作者、致谢、数据链接和代码链接可结构化加入。
- 新参考文献进入 reference registry、literature evidence 和 citation audit。
- exact user text 不被 writer 覆盖。
- 每次修改有 before/after hash、diff、stale scope 和 rollback。
- 最终 main.pdf 展示用户确认的内容。
- final citation audit 一定晚于最后一次 citation-bearing revision。

## 11. 版本实施顺序

### v0.23.1 Project Versioning, State Isolation and Transaction Replay

实现：

- plan-project-version、create-project-version 和 import-version-assets；
- project_lineage.json 和 asset_import_plan.json；
- 新项目先建空 scaffold，再导入 allowlisted source assets；
- 旧 reports、metadata、passport 和 ledgers 只能 baseline_only，不进入 active graph；
- project_system_of_record.json；
- artifact category、writer、input hash 和 rebuild contract；
- scientific decision 与 transaction status 分离；
- next-action precondition verifier；
- astronomy 未闭环状态问题的 local capture/replay。

优先关闭：

- ASTR-004、005、018-032、048。

### v0.23.2 Research Capability Pack and Routing Eval

实现：

- capability pack；
- ownership map；
- routing_eval.jsonl；
- project_method_implementation_required；
- 完整 rescue 顺序；
- runtime-level truth。

优先关闭：

- ASTR-001、003、007、023、024、027。

### v0.23.3 Figure/Paragraph Evidence Resolver and Token Budget

实现：

- run-aware figure evidence resolver；
- direct signal versus diagnostic story roles；
- paragraph evidence slices；
- stage receipts 和 token budget。

优先关闭：

- ASTR-006、012、016、028、030-034、044、046、053、054。

### v0.23.4 Journal and Bibliography Contract

实现：

- reference registry；
- bibliography contract；
- duplicate/version resolver；
- journal style single source of truth；
- structured BibTeX parser；
- rendered reference proof。

优先关闭：

- 新发现的 bibliography format 问题；
- ASTR-055、056。

### v0.23.5 Third-party Provenance Registry

实现：

- third_party/registry.json；
- AcademicForge 和传递上游来源；
- gbrain influence record；
- THIRD_PARTY_NOTICES；
- promote provenance gate；
- package license inclusion。

### v0.23.6 Doctor, Recovery and Declarative Command Registry

实现：

- 直接修复并发布 Draftpaper-loop 原生 Doctor/Recovery；gbrain doctor 仅作为开发期输出完整性检查表，不复制其 schema、字段、命令或运行时；
- doctor --json；
- start/continue/review/recover 宏命令；
- CommandSpec 覆盖全部 parser；
- paste-ready remediation；
- protected/manual-only actions。

### v0.23.7 Two Independent Blind Reviews

实现并实际执行：

- 单一生成稿的匿名 frozen submission bundle；
- reviewer 1 独立报告；
- reviewer 2 独立报告；
- reviewer agreement 和 disagreement resolution；
- aggregate report；
- 必要时第三 reviewer adjudication。

不再需要：

- 原稿或 baseline manuscript；
- Manuscript A/B；
- generated/baseline ratio；
- 解盲映射。

关闭：

- ASTR-051。

### v0.23.8 Post-review Manuscript Revision Workspace

实现：

- source map；
- line/paragraph anchors；
- manuscript metadata；
- revision request/preview/accept/rollback；
- review findings queue；
- custom references；
- 最终 main.pdf。

### v0.24.0 Full General Regression

至少运行：

- astronomy + machine learning；
- geography + machine learning；
- bioinformatics + medicine；
- 一个未参与设计的新学科课题；
- source checkout；
- editable install；
- wheel clean install；
- full PDF；
- bibliography proof；
- token ledger；
- two-reviewer independent manuscript audit；
- user revision smoke workflow。

#### 首个新课题真实回归：Euclid Q1 VIS × DESI BGS_BRIGHT

使用用户提供的本地 Euclid/DESI 形态学分析 DOCX 提取 idea，使用同目录下的数据作为只读科研数据源。

维护者本地将 `DRAFTPAPER_EUCLID_IDEA_DOCX` 映射到用户指定的形态学分析报告，将 `DRAFTPAPER_EUCLID_DATA_ROOT` 映射到对应的 Euclid/DESI catalogue 根目录。绝对路径只存在于本地回归配置，不进入公开代码、README、fixture、日志、review bundle 或 Git 历史。

本地路径不写入公共仓库，使用 maintainer-local 环境变量：

~~~text
DRAFTPAPER_EUCLID_IDEA_DOCX
DRAFTPAPER_EUCLID_DATA_ROOT
~~~

这两个变量在维护者本地分别映射到 idea DOCX 和只读 catalogue 数据根目录；具体目录名不进入公开仓库。

该映射只存在于维护者本地测试环境。公开 README、fixture、日志、capture、review bundle 和提交历史不得写入绝对路径；运行报告只记录经过脱敏的逻辑数据角色、内容 hash、cohort 和只读访问方式。

建议 research idea：

> 检验固定的 DINOv2 ViT-S/14 表征对 Euclid Q1 VIS 星系切图所编码的信息：在控制红移、亮度、样本选择、类别不平衡和 tile 相关性后，该表征能否预测 catalogue profile type，并提供超出已测 catalogue covariates 的增量信息；同时评估其用于表征探索、分类和异常候选发现时的有效边界。

该 idea 不预设 DINOv2 的训练来源为 ImageNet，也不直接接受“DINOv2 已证明捕获真实星系形态”的结论。模型来源应由 model provenance 明确记录；MORPHTYPE 只能解释为 catalogue profile-model target，不能冒充独立专家形态标签。

已知本地数据角色：

| 数据角色 | 当前可用内容 |
| --- | --- |
| crossmatch catalog | 经过质量筛选的 DESI 光谱源 catalogue |
| VIS coverage | 与 catalogue 匹配的本地 VIS cutouts 及覆盖状态 |
| valid image cohort | 经过全零图像和图像质量筛选的有效 cutouts |
| visual representation | 与有效图像 cohort 对齐的固定宽度 DINOv2 embeddings 和 target IDs |
| spectroscopy | DESI SPECTYPE、Z、ZERR、ZWARN、DELTACHI2 |
| photometry | Legacy Survey g/r/z 与 WISE W1/W2 |
| morphology-related fields | MORPHTYPE catalogue profile-model target、VIS image content、derived labels |
| reusable local outputs | morphology catalog、analysis tables 和 plots，仅作 baseline/candidate |

DOCX 使用边界：

- 只提取研究主题、数据来源、已知处理步骤和需要重新验证的问题。
- DOCX 只承担 idea seed 与 data semantics 输入，不承担目标论文、标准答案、文风样本或质量基线角色。
- DOCX 的 Results、Discussion、Conclusion 和现有图表解释不进入 writer context。
- 现有六张图、analysis_report 和已有结果数字只能进入 lineage/baseline_assets。
- 新流程必须从当前数据、代码和 run outputs 生成 active evidence。
- 不把 DOCX 当作原稿，也不进行生成稿与 DOCX 的质量比例比较。

该回归的成功标准不是“复现 DOCX 文案”，而是检验一个此前未参与框架设计的新课题能否独立完成：学科识别、插件充分性与 rescue、数据语义审计、方法实现、科学图表、证据绑定、自由写作、引用与 bibliography 检查、双独立单稿盲评、revision queue 和最终 PDF。若新结果与 DOCX 中的既有结论不同，应以当前可追溯的 active evidence 为准，并在 Discussion 中解释边界，而不是为了贴近旧报告改写结果。

该课题必须重点检验以下风险：

1. quiescent、star_forming、green_valley 和 AGN 标签使用 g-r、M_r、W1-W2 构建，不能再把同一变量与标签的相关性描述为独立验证。
2. MORPHTYPE 表示 catalogue profile-model selection；DEV、EXP、REX、SER 和 PSF 不是独立专家形态标签。物理活动状态标签也不应未经外部证据支持就等同于视觉 morphology class。
3. 随机 StratifiedKFold 可能忽略 tile、空间邻近、重复观测或相关样本，需比较 group/tile-held-out validation。
4. 类别支持明显不均衡，少数类样本有限，必须报告类别不平衡、置信区间和小样本边界。
5. 红移、亮度、颜色和 BGS_BRIGHT 选择效应可能驱动 embedding 分离，需要 confounder baseline 和 ablation。
6. DINOv2 预训练域与 Euclid VIS 观测域之间的 domain shift、单通道复制、百分位裁剪和 resize 可能影响形态信息；预训练数据来源必须从模型 provenance 获取，不能由 writer 猜测。
7. 缺失 cutouts 和全零图像剔除可能造成非随机样本偏差。
8. UMAP 与 K-means 只能展示或探索结构，不能单独证明物理类别有效。
9. training balanced accuracy 与 cross-validation balanced accuracy 的差距必须解释为泛化风险。
10. LOF 异常体的并合、低面亮度或 AGN 解释必须标为候选，除非有外部证据确认。

期望 Draftpaper-loop 自动识别：

- disciplines：astronomy + machine_learning；
- data plugins：FITS/catalog、VIS cutout、embedding matrix、spectroscopy/photometry join；
- method plugins：fixed DINOv2 representation loading、UMAP、K-means、linear probe、group-aware validation、LOF、confounder ablation；
- review rules：label leakage、class imbalance、group leakage、selection effect、domain shift、uncertainty、candidate interpretation boundary。

建议 figure story roles，不强制固定文件数：

- sample construction、coverage 和 missingness；
- representative VIS morphology examples；
- embedding structure 与 label/confounder 对照；
- group-aware classification 与 transparent baselines；
- selection-effect/confounder ablation；
- anomaly candidates 与 image-quality boundary；
- 额外稳定性、类别支持和敏感性图进入 supporting figures。

真实回归验收：

- 从干净新项目开始，不复制 astronomy 项目的旧状态。
- 不使用现成 morphology report 的正文质量、结论或图表作为比较目标；验收对象是 Draftpaper-loop 能否从 idea seed、只读数据和重新生成的 active evidence 独立完成科研闭环。
- 本地数据目录保持只读，导入 artifact 记录 locator 和 SHA-256。
- 正确区分 source catalogue、VIS coverage cohort 和 image-quality-filtered analysis cohort，且所有数字只保留在私有运行证据中。
- research plan 明确“关联、预测、独立验证和因果解释”的不同强度。
- plugin sufficiency 能先识别本地 embeddings 和分析表，不强制重新调用 GPU。
- 如果需要重算 DINOv2，GPU 作为可选 execution route，不作为无条件阻塞。
- Results 不把 photometry-derived label correlation 写成独立形态学验证。
- discipline review 能识别 leakage、selection effect、class imbalance 和异常解释越界。
- 两位独立 reviewer 分别审查最终单稿并输出问题报告。
- 记录完整 token ledger 和 revision loop。
- DOCX、原始数据和本地绝对路径不进入公共 fixture；公共测试只保留去标识 schema、hash 和合成样本。

发布前，审计中的 observed、protected、corrected_in_worktree 和 pending_general_regression 必须全部转换为：

- verified_in_project；
- verified_cross_discipline；
- 或有明确保留理由的 advisory。

## 12. 最终验收清单

### 项目版本化

- 科学链变化时创建干净的 _v1，不在旧项目中原地修改。
- old project 全程 hash 不变。
- 新项目具有独立 project ID、passport 和 stage state。
- 旧派生报告只能 baseline_only，不能进入 active artifact graph。
- 大型数据可通过只读 locator 复用，但必须验证 hash。
- 每个导入资产记录来源、导入模式和 revalidation 状态。

### 状态与证据

- 旧文件不能伪装成当前 artifact。
- 每条 next command 可执行。
- 非零科学 gate 的合法写入不会制造 drift。
- approved snapshot 只能显式 reopen。

### 插件

- 新课题不会陷入插件/代码生成闭环。
- 所有 rescue 路线可审计。
- routing top-1 >= 95%。
- critical wrong-discipline selection = 0。

### 图表与写作

- 每张图绑定正确 run/table/model/unit。
- direct signal 不被一般诊断图替换。
- bound evidence 召回率 100%。
- observable writing input tokens <= 73,343。

### 参考文献

- citation support 与 bibliography format 分开通过。
- journal profile 和实际 bst 一致。
- duplicate work、大小写、DOI、URL、作者和出版字段通过。
- retained reference 不在 citation audit 中被删除。

### 第三方来源

- AcademicForge 及其原始 skill repo 可递归追溯。
- gbrain 架构借鉴有来源记录。
- 每个来源有 commit、license、use mode 和影响路径。

### 双独立单稿盲评

- 两位独立 reviewer 分别输出完整 Markdown/JSON 报告。
- 两位 reviewer 只审查同一份冻结生成稿，不需要原稿或 A/B 对比。
- 两位 reviewer 看不到自动评分、既有审计结论和对方结果。
- scientific correctness 达到项目硬门。
- critical 和 unresolved major findings 均为 0 才允许 release。
- aggregate report 形成明确 revision queue，不生成相对原稿质量比例。

### 用户修订

- 支持行号和稳定段落 ID。
- 支持作者、致谢、数据/代码链接和自定义段落。
- 支持新增参考文献。
- 修改可预览、接受、回滚和精确 stale。
- 最终 main.pdf 与最后接受的 revision snapshot 一致。

## 13. 可选择性参考的 gbrain 文档

以下文档仅用于 capability routing、context budget、eval replay 和迁移保护的设计复核。Draftpaper-loop 的实现不以 gbrain 为依赖，也不要求逐项采用。

- [Thin Harness, Fat Skills](https://github.com/garrytan/gbrain/blob/master/docs/ethos/THIN_HARNESS_FAT_SKILLS.md)
- [Retrieval Architecture](https://github.com/garrytan/gbrain/blob/master/docs/architecture/RETRIEVAL.md)
- [Eval Bench](https://github.com/garrytan/gbrain/blob/master/docs/eval-bench.md)
- [Calibration Quality Gate](https://github.com/garrytan/gbrain/blob/master/docs/architecture/calibration-quality-gate-spec.md)
- [Skillpack Anatomy](https://github.com/garrytan/gbrain/blob/master/docs/skillpack-anatomy.md)
- [Pack Upgrade Mechanism](https://github.com/garrytan/gbrain/blob/master/docs/architecture/pack-upgrade-mechanism.md)

## 14. 最终判断

Draftpaper-loop 后续优化应以自身科研流程为中心：

1. 科学链发生实质变化时，先创建干净的 _v1，再选择性迁移旧资产。
2. 旧项目始终只读，不在旧目录中先改后复制。
3. figure metadata、sufficiency report、project-local audit、passport 和其他派生状态不迁移为 active。
4. 状态事务、参考文献、第三方来源、doctor 和用户修订直接按正常工程方式修复。
5. 只有 capability routing、按任务 context budget、capture/replay 和迁移保护确有成熟优势时，才选择性参考 gbrain。

这条路线可以同时解决：

- 历史 artifact、stale 和事务循环；
- 新旧项目版本隔离及可控资产复用；
- 新课题插件补齐与动态代码生成闭环；
- 图表/写作证据选择和 token 成本；
- 参考文献格式与第三方来源；
- 双独立盲评；
- 作者最终定点修订和 main.pdf 输出。

关键不是让 Draftpaper-loop 变得更像 gbrain，而是让 Draftpaper-loop 的 loop、项目版本、证据和最终作者控制权变得更清楚。
