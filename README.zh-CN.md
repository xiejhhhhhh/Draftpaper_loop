<div align="center">

[![AI Research Loop](https://img.shields.io/badge/AI-Research%20Loop-5C4D7D?style=flat-square)](#核心科研能力)
[![Loop Engineering](https://img.shields.io/badge/Loop-Engineering-1D7874?style=flat-square)](#完整科研工作流)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#文献引用与独立审稿)
[![Discipline Plugins](https://img.shields.io/badge/Discipline-Plugins-6A994E?style=flat-square)](#学科插件与科研能力扩展)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#快速开始)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#贡献者许可证商业使用和联系方式)

# Draftpaper-loop

**阿里巴巴希望天下没有难做的生意，而 Draftpaper-loop 希望天下没有难写的论文。**

**从研究 idea、学科方法和真实数据出发，生成可审计科研图表、完整论文与可追溯 `main.pdf` 的本地科研工作流。**

[English](./README.md) | [中文](./README.zh-CN.md)

</div>

Draftpaper-loop 把论文写作组织成证据优先的科研 loop：先确认研究问题和可行性，再匹配或补齐数据与方法能力，执行分析并确认图表是否支撑论断，随后基于同一证据版本完成正文、引用核查、学科审查、独立盲评和 PDF 发布。

## 项目定位与当前版本

### 用户可以用它完成什么

- 从研究 idea、已有数据、参考文献或项目代码创建结构化论文项目。
- 生成中英文研究蓝图、claim contract、统计验证要求和主图故事板，并集中交由用户确认。
- 识别单一或交叉学科，匹配 `data_connector`、`method_template` 和 `review_rule`，调用真实项目代码完成数据处理、模型训练、统计分析和科研制图。
- 在能力不足时审计 project-local 代码，并从现有插件、AcademicForge metadata 或公开科研代码仓库形成可追溯的补齐任务。
- 让主图追溯到 research-plan claim、cohort、data plugin、method plugin、run output、evidence ID 和学科审稿规则。
- 按 Results → Introduction → Data → Methods → Discussion 的证据顺序生成正文，并从阶段代码、公式、图表和参考文献重建科学叙事。
- 在正文完成后核查引用支撑、参考文献格式、学科统计标准、结果表述和复现材料，再交给两位独立盲评者。
- 一次补齐作者、单位、ORCID、基金、致谢、数据/代码链接、新文献和定点段落修订，预览候选 PDF 后发布同一 hash 绑定的 `main.pdf`。

**当前版本：v0.33.0。** 当前 release 强化了 Result Support v3、证据绑定的作者补全、Agent/CLI 合同同步和严格修改分类。完整版本记录见[最近更新](#最近更新)；项目能力按科研任务组织在下文。

## 核心科研能力

| 科研环节 | 主要能力 | 关键产物 |
|---|---|---|
| 研究设计 | idea 解析、期刊画像、中英文研究蓝图、claim/statistical/figure contracts 和人工确认 | confirmed plan hash、claims、figure storyboard |
| 学科能力 | 单学科/交叉学科识别，数据、方法和审稿插件匹配，project-local 审计和能力补齐 | discipline/capability contracts、plugin bindings |
| 数据与方法 | 数据清单、可行性、阶段归属代码、真实方法运行、公式和变量提取 | data/method manifests、run/formula manifests |
| 图表与证据 | 语义 figure/panel contract、figure-code trace、结果有效性和 Result Support | 主图组、附录图、result manifest、evidence registry |
| 科学写作 | Paper Narrative Engine、章节证据包、Codex 自由写作、Scientific Editor | Results、Introduction、Data、Methods、Discussion |
| 文献与引用 | 检索、Zotero、BibTeX、PDF/摘要证据、引用意图、citation audit | `library.bib`、citation evidence、final audit |
| 审稿与发布 | Results 后学科审查、两位独立盲评、作者补全事务、编译和 release hash | reviewer reports、completion packet、`main.pdf` |

### 从早期版本到当前框架

- **v0.1-v0.13：论文项目与科研阶段地基。** 建立参考文献、期刊画像、research plan、方法/结果/讨论写作、artifact 追踪、Zotero、数据观察、科研绘图和阶段归属代码。
- **v0.14-v0.20：学科插件与结果支撑链。** 引入数据连接器、方法模板、review rules、插件充分性、AcademicForge/GitHub 候选补齐、跨学科执行账本和 Results 后学科审查。
- **v0.21-v0.28：科学叙事与证据语义。** 引入 Paper Narrative Engine、章节证据包、自由写作与 Scientific Editor、run/cohort/estimand 绑定、语义图表合同、独立盲审和可复现审稿包。
- **v0.28.1-v0.33：事务、发布与精确恢复。** 完成 artifact DAG、统一 CommandSpec、科学非零退出状态、作者补全事务、稳定段落定位、跨期刊/跨平台 wheel 回归、Result Support v3 和 release hash 绑定。

版本号用于解释能力来源；日常使用由当前研究问题和项目状态驱动，`status`、`doctor` 和 `run-pipeline` 会给出下一步。

## 快速开始

### 1. 安装真实论文常用的绘图档位

PowerShell：

```powershell
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[plotting]"
.\.venv\Scripts\draftpaper doctor --json
```

bash/macOS/Linux：

```bash
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[plotting]"
draftpaper doctor --json
```

### 2. 让 Codex 驱动工作流

在 Codex 中打开仓库目录，并说明 idea、数据位置、目标期刊和已有代码：

```text
使用当前仓库中的 Draftpaper-loop 为这个 idea 创建论文项目。
先读取 idea、数据和已有代码，识别学科与能力缺口，生成中文版研究蓝图给我确认；
确认后按项目状态执行数据、方法、图表、论文写作、引用核查、两位独立盲评和 PDF 编译。
```

Codex 负责科研推理和自然行文；阶段状态、证据绑定、写入范围与人工确认由 Draftpaper-loop CLI 合同记录。

### 3. 最短 CLI 路径

```powershell
draftpaper create-project --idea "Your research idea" --field "astronomy machine learning" --target-journal MNRAS
draftpaper status --project .\projects\<project>
draftpaper run-pipeline --project .\projects\<project>
```

`run-pipeline` 会在研究蓝图、结果支撑路线和最终发布检查点停下并推荐下一条命令。论文项目默认位于 `projects/<project>/`，成稿位于 `projects/<project>/latex/main.pdf`。

基础教学视频：[Bilibili](https://www.bilibili.com/video/BV1LKjS6gEh4/)

## 完整科研工作流

```text
idea、已有数据、项目代码与文献
  -> 创建独立论文项目
  -> 识别学科与目标期刊
  -> 检索/导入文献并建立引用证据
  -> 生成中英文研究蓝图、claims、统计合同和主图故事板
  -> 用户集中确认研究蓝图
  -> 评估插件充分性并审计 project-local 能力
  -> 执行数据插件、方法插件和真实项目代码
  -> 生成主图组、支撑图、结果表与证据注册表
  -> 验证结果是否支撑研究论断
  -> 接受证据、收窄论断或补充数据/方法
  -> Results -> Introduction -> Data -> Methods -> Discussion
  -> Results 后复合学科 review-rule 审查与语义修复
  -> 最终作者补全和定点修订
  -> 最终 citation audit
  -> 两位独立盲评者
  -> 完整性、期刊格式和 PDF 编译验证
  -> 确认 release hash
  -> latex/main.pdf
```

### Loop 和人工控制

```text
读取项目状态
  -> 选择当前阶段动作
  -> 执行并生成结构化产物
  -> 验证科学合同和文件 hash
  -> 记录 artifact、run、evidence 和人工决策
  -> 输入变化时精确标记下游 stale
  -> 诊断失败并回到对应阶段
  -> 重复直到成稿可发布
```

确定性合同负责项目状态、cohort/run 身份、插件来源、图表语义、公式、引用、stale 传播、写集和 release hash。Codex 或其他 Agent 负责开放性的文献理解、方法设计、科研推理和自然写作。

三个集中人工确认点是：

1. **研究蓝图确认**：一起查看研究问题、claims、cohort、数据/方法需求、统计标准、主图组和可行性边界。
2. **关键结果与论断支撑确认**：一起查看真实运行、核心图表、指标、不确定性和最大可支持论断，并决定后续路线。
3. **最终稿与发布确认**：一起查看作者补全 packet、候选 PDF、最终引用审计、两位盲评意见和 release hash。

### 结果支撑不足时的两条路线

<!-- capability:result_support_two_routes -->
<!-- capability-meta: id=result_support_two_routes; status=implemented; since=0.18 -->
- **论断收窄路线**：冻结已确认图表和指标，下调 claim 强度并重新生成受影响正文。
- **数据/方法补强路线**：补充数据角色、清洗、方法实现或验证，随后重跑相应的证据、图表和正文链。
当前按整份 result-support checkpoint 选择一条路线，多 claim 独立分治列为后续能力。
<!-- /capability:result_support_two_routes -->

<!-- capability:result_support_checkpoint_v3 -->
<!-- capability-meta: id=result_support_checkpoint_v3; status=implemented; since=0.32 -->
Result Support v3 优先读取当前 resolved evidence，其次读取 selected run manifest 和明确 run-bound 的结果表。路线绑定当前 checkpoint hash；Results 后发现的 cohort、指标或图表证据问题会回流到同一个 checkpoint，保持正文与证据版本一致。
<!-- /capability:result_support_checkpoint_v3 -->

## 学科插件与科研能力扩展

### 数据、方法和审稿规则

`draftpaper_cli/discipline_modules/<discipline>/` 注册三类正式科研插件：

- **`data_connectors`**：数据访问、读取、解析、清洗、标准化、cohort 构建和质量检查。
- **`method_templates`**：统计分析、特征工程、模型训练、验证、消融、不确定性估计和科研制图。
- **`review_rules`**：按学科和方法核验统计标准、baseline、split/leakage、拟合或分类质量、校准、稳健性、图表-论断一致性与复现要求。

插件 manifest 声明运行等级、验证等级、依赖、输入输出、fixture 和 provenance。合同、mock 和 fixture 用于验证接口；主图证据要求经过真实项目或 live 运行验证的输出及 hash。

research plan 生成 discipline/capability contracts，将每个 claim 和 figure requirement 分配给主学科、次学科及相应 data/method/review 能力。能力缺口按以下顺序补齐：

1. 审计项目现有数据/方法代码和运行产物，形成受限 `project_local` binding。
2. 搜索当前 registry 中可复用的插件。
3. 从 AcademicForge 等 registry metadata 提取候选能力。
4. 审计公开科研代码仓库的许可证、结构、复现性和输入输出。
5. 由 Codex 生成项目专属实现并在当前项目验证。
6. 通用能力另行经过 generalize、fixture、overlap、license 和人工确认后 promote。

数据与方法补齐路线都有可审计结果、且关键输入或实现仍缺失时，图表阶段才形成明确阻塞诊断。

### 主图可追溯链

```text
research-plan claim
  -> data requirement -> data plugin/project-local binding
  -> method requirement -> method plugin/project-local binding
  -> verified run output
  -> evidence ID and cohort view
  -> figure/panel contract
  -> Results claim
  -> applicable discipline review rules
```

数据和方法插件生成真实图表输入与方法输出；匹配的 `review_rule` 在 `review-results-with-discipline-rules` 阶段核验图表和 Results 表述。

### 外部能力如何进入插件体系

公开科研代码和 AcademicForge 采用 metadata-first 的候选流程，保留 repository、commit、license、依赖、输入输出、运行等级和来源记录。候选通过 `generalize-plugin-candidate`、`validate-plugin-candidate`、`package-plugin-contribution`、`preflight-plugin-contribution`、`review-plugin-contribution` 和人工确认的 `promote-plugin-candidate` 后进入正式学科模块。

`workflow_recipe`、`paper_contract` 和 `shared_capability` 留在支撑层；其中可验证的统计、baseline、ablation、split/leakage、引用支撑和复现条件可以回流为 `review_rule_candidate`。全部命令见[CLI 命令参考](docs/cli_reference.md)。

本仓库在 `third_party/` 保存上游快照、来源指针、固定 commit 和许可证说明；随 wheel 运行的 paper-fetch fallback 位于 `draftpaper_cli/_vendor/paper_fetch_skill`。

## 图表、证据与科学写作

### 从确认蓝图生成图表

`plan-figures` 读取已确认的 research plan、claims、cohort、data/method requirements、统计合同和已有证据，生成主图组、supporting/appendix 图和 caption 合同。每组图的首句概括整体科学结论，后续句子逐一解释 panel、cohort、估计量、不确定性和 claim boundary。

`generate-analysis-code` 依据 figure contract 和已绑定能力生成阶段归属代码。执行失败写入 `figure_execution_diagnosis.json/.html`，区分数据缺口、方法缺口、依赖问题、运行错误、结果质量不足和需要用户确认，并推荐对应修复命令。

### 同一证据版本驱动正文

Paper Narrative Engine 读取 Scientific Evidence Registry、result manifest、figure story arc、文献比较矩阵、阶段代码和公式 trace，生成章节证据包与段落目标。Codex 在证据边界内自由写作；写后合同核验数字、cohort、run、模型、指标量纲、引用角色、内部路径和论断强度。

- **Results**：解释主图组和关键表格，并用支撑/附录图完成稳健性、不确定性和边界说明。
- **Introduction**：根据研究问题、研究意义、文献证据和 Results 已确定的贡献组织研究空白。
- **Data**：从 data connector、data inventory、cohort registry 和阶段代码重建来源、样本、变量、预处理和缺失性。
- **Methods**：从 method plugin、真实实现、run manifest、公式 AST 和 figure-code trace 提炼方法阶段，解释核心公式、变量、假设及其与结果图表的关系。
- **Discussion**：将本研究结果与比较文献证据对应，分析机制、创新、不足、外推边界和后续工作。

`record-observation` 只保存已经展示给用户的阶段分析摘要。路径、命令、凭证、manifest 字段和本地文件名留在内部 context。

### 精确 stale 和恢复

<!-- capability:scientific_gates_and_artifact_dag -->
<!-- capability-meta: id=scientific_gates_and_artifact_dag; status=implemented; since=0.30 -->
科学门控、非零退出状态、统一 change taxonomy 和 artifact DAG 共同决定项目可继续的状态。数据、cohort、方法、run、指标、主图或 claim 变化会重开对应科学链；引用局部修订、作者 metadata 和纯展示修改采用更窄的 stale 范围。
<!-- /capability:scientific_gates_and_artifact_dag -->

项目通过 `project_passport.yaml`、`artifact_ledger.jsonl`、`checkpoint_ledger.jsonl`、`integrity_ledger.jsonl` 和 artifact hash 记录阶段、输入、输出、人工确认与恢复理由。`doctor --explain` 和 `diagnose-gate-failures` 用于解释当前状态及下一步。

## 文献、引用与独立审稿

文献阶段保存 BibTeX、reference registry、citation evidence、阅读笔记、单篇摘要和可用 PDF/全文证据。检索结果、用户提供文献和 Zotero collection 都保留来源与选择策略，写作时按 direct support、方法 provenance、数据来源、比较语境和背景分配引用角色。

Zotero 示例：

```powershell
$env:ZOTERO_LIBRARY_ID="your_zotero_library_id"
$env:ZOTERO_LIBRARY_TYPE="user"
$env:ZOTERO_API_KEY="your_zotero_api_key"
draftpaper list-zotero-collections
draftpaper search-literature --project <project> --zotero-collection "My Paper References" --zotero-context all --zotero-min-items 20
```

citation audit 位于最终章节和作者补全之后、独立盲评之前。它逐条比较正文 claim、BibTeX metadata、citation evidence、passage、数值、否定和因果方向，指出支撑弱、位置不合适或表述过强的引用。修复优先收紧或重写正文，并保留人工确认的参考文献与 reference coverage。

`review-results-with-discipline-rules` 读取 Results、figure/plugin trace、run output、evidence ID 和复合学科规则，检查指标陈述、样本边界、baseline、ablation、统计量纲、不确定性、拟合/分类标准和图表解释。语义问题进入局部 Results 修订；真实能力缺口回到 result-support 路线。

<!-- capability:completion_audit_and_readme_framework -->
<!-- capability-meta: id=completion_audit_and_readme_framework; status=implemented; since=0.32 -->
最终稿通过 citation audit 后生成冻结的匿名单稿审查包，由两位相互独立的 reviewer 分别检查科学正确性、证据充分性、结构、表达、图表、引用和复现材料。两份报告绑定同一个 manuscript/evidence/bundle hash；critical 或 major finding 进入修订和复审，最终确认绑定最新报告和编译 PDF。
<!-- /capability:completion_audit_and_readme_framework -->

## 最终稿补全、定点修订与发布

一个 `manuscript_completion.yaml` 可以一次补充作者、单位、ORCID、通讯作者、基金、致谢、关键词、短标题、数据/代码可用性、用户确认的新文献和多处章节修订。

<!-- capability:stable_locator -->
<!-- capability-meta: id=stable_locator; status=implemented; since=0.30 -->
LaTeX 行号用于用户定位提示；实际写入同时校验稳定 `paragraph_id`、expected text、occurrence 和 SHA-256。章节重排后可以重新定位，歧义、重复目标或 stale hash 会让整个 packet 回到预览。
<!-- /capability:stable_locator -->

<!-- capability:completion_change_classification -->
<!-- capability-meta: id=completion_change_classification; status=implemented; since=0.32 -->
preview 同时展示用户声明的 change class、系统推断类别、candidate evidence refs 和精确 stale 范围。作者信息、致谢和纯文字润色保持在下游；新增数据来源、已执行方法、科学指标、claim 或图表解释依据当前 evidence refs 重开相应科研或写作阶段。
<!-- /capability:completion_change_classification -->

<!-- capability:manuscript_completion_transaction -->
<!-- capability-meta: id=manuscript_completion_transaction; status=implemented; since=0.30 -->
补全流程先生成统一 diff、候选 LaTeX 和候选 PDF；用户接受后原子 apply。Apply 重新核验 packet、project revision、source map、evidence snapshot 和 before hash，并写入 rollback receipt 与 exact-text user lock。
<!-- /capability:manuscript_completion_transaction -->

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper review-final-manuscript --project <project>
draftpaper confirm-final-manuscript --project <project> --release-hash <sha256>
```

发布顺序为：作者补全与定点修订 → 最终 citation audit → 两位独立盲评 → 完整性与编译验证 → release hash 确认。完整格式见[最终论文信息补全与精确修订](docs/manuscript_completion.zh-CN.md)。

## 安装、Agent 与日常操作

### 安装档位

<!-- capability:minimal_install_cost_risk_release -->
<!-- capability-meta: id=minimal_install_cost_risk_release; status=implemented; since=0.31 -->
- `pip install -e .`：minimal 控制面、项目状态、参考文献和基础 PDF/图像检查。
- `pip install -e ".[plotting]"`：真实论文常用的 NumPy、pandas、Matplotlib 等绘图与分析入口。
- `pip install -e ".[fulltext]"`：增强 PDF/全文提取。
- `pip install -e ".[mcp]"`：本地 stdio MCP。
- `draftpaper doctor --json`：识别当前档位、缺失模块和恢复命令。
- `draftpaper token-report --project <project>`：汇总已有 token/cost receipt。
<!-- /capability:minimal_install_cost_risk_release -->

复杂图表后端使用 `.[plotting-full]`。日常任务优先让 Agent 读取 `status` 并调用 `run-pipeline`；调试和恢复常用：

```powershell
draftpaper status --project <project>
draftpaper doctor --project <project> --explain
draftpaper run-pipeline --project <project>
draftpaper detect-artifact-drift --project <project>
draftpaper sync-artifact-stale --project <project>
draftpaper diagnose-gate-failures --project <project>
draftpaper run-integrity-gate --project <project>
draftpaper audit-citations --project <project> --final
draftpaper assess-publication-readiness --project <project>
```

Python API 提供与 CLI 相同的证据语义入口，包括 `resolve_result_evidence`、`build_scientific_evidence_registry`、`validate_figure_semantics`、`create_evidence_snapshot` 和 `submit_section_draft`。MCP 是 CommandSpec/CLI handler 的受控投影，用于本地 Agent 集成。

<!-- capability:command_schema_quality_contracts -->
<!-- capability-meta: id=command_schema_quality_contracts; status=implemented; since=0.31 -->
CommandSpec、schema registry 和质量合同构成统一命令控制面，声明风险、输入、输出、写入范围、联网行为和人工检查点。自动生成的参考文档来自同一 registry，README 只保留用户常用路径。
<!-- /capability:command_schema_quality_contracts -->

| 需要了解的内容 | 文档 |
|---|---|
| 命令、参数、输入输出和风险 | [CLI 命令参考](docs/cli_reference.md) |
| minimal、plotting、fulltext、MCP | [安装档位说明](docs/install_profiles.zh-CN.md) |
| 写入、联网和人工确认边界 | [命令风险矩阵](docs/command_risk_matrix.md) |
| 项目 token 与费用 receipt | [Token 与费用报告](docs/token_cost_reporting.zh-CN.md) |
| 最终作者补全和段落定位 | [最终论文补全指南](docs/manuscript_completion.zh-CN.md) |
| DPL schema、项目状态和 artifacts | [DPL Schema](docs/DPL_SCHEMA.md) |

## 项目目录、证据合同与工程边界

```text
draftpaper_cli/                    核心 Python package、CLI、状态与证据合同
draftpaper_cli/discipline_modules/ data connectors、method templates、review rules
draftpaper_cli/_vendor/            wheel 内运行时后备
codex_skills/draftpaper-workflow/  Codex workflow skill 与 Agent 合同
docs/                              使用指南、schema、审计和自动生成参考
tests/                             单元、对抗、wheel、跨平台和发布回归
third_party/                       上游快照、来源指针、许可证和 provenance
projects/                          本地论文项目，默认由 git 忽略
```

单篇项目中，数据收集、清洗和 cohort 构建代码归 `data/`；模型、统计、验证和制图代码归 `methods/`；`results/` 保存图表、表格和 metadata；`writing/`、`citation_audit/`、`review/` 和 `latex/` 保存正文、核查、审稿和最终 PDF。大型数据集可以保留在原位置，通过私有 locator、只读指纹和 manifest 连接，流程产物继续归属论文项目。

每个写入命令在执行前后核对声明写集，并通过 state revision、项目锁、artifact hash 和 transaction receipt 保护项目。MCP capability token、程序白名单、路径限制、网络策略和日志脱敏用于约束应用层行为。公网多租户隔离、账号系统和托管计费属于独立产品工程边界。

运行基础验证：

```powershell
python tools/validate_capability_truth_matrix.py
python -m pytest tests/test_capability_truth_matrix.py
python -m pytest
python -m build
```

## 贡献者、许可证、商业使用和联系方式

Draftpaper-loop 欢迎可复用的学科模块贡献，尤其是数据 connector、方法模板、审稿规则、fixture，以及可以从真实项目中泛化出来的工作流经验。贡献内容不应包含私有路径、账号凭证、原始数据或项目专属结论。

当前贡献者：

- 谢锦晖：负责 Draftpaper-loop 整体框架构建，包括参考文献、数据方法审核、结果输出等审核机制、回退机制，以及深度学习、天文学、地理科学的学科模块贡献。
- 陈维：天文学科模块的补充和相关验证生成。

Draftpaper-loop 以 source-available 形式开放给非商业科研、评估、教学和个人论文工作流使用。商业使用、付费服务、SaaS 部署、企业部署、转售，或集成到商业产品中，需要事先获得项目开发者的书面授权。

赞助或打赏只用于支持项目维护，不自动授予商业使用权。商业使用仍然需要单独获得事先书面授权。

Draftpaper-loop 使用 DPL schema family 表示本地优先论文 loop 状态，包括 project passport、stage manifest、citation evidence、run manifest、result manifest、artifact hash、claim trace 和 loop event。

当前非商业 source-available 条款、归属声明、商业授权范围、项目名称/商标政策、公开 schema 身份和合规边界见 [`LICENSE`](./LICENSE)、[`NOTICE`](./NOTICE)、[`COMMERCIAL_LICENSE.md`](./COMMERCIAL_LICENSE.md)、[`TRADEMARK.md`](./TRADEMARK.md)、[`COMPLIANCE.md`](./COMPLIANCE.md)、[`docs/DPL_SCHEMA.md`](./docs/DPL_SCHEMA.md) 和 [`docs/FORENSIC_FINGERPRINTING.md`](./docs/FORENSIC_FINGERPRINTING.md)。

如需商业授权，请联系：[xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn)。

个人主页：[https://xiejhhhhhh.github.io/Jinhui_profile/](https://xiejhhhhhh.github.io/Jinhui_profile/)

第三方组件保留各自许可证。

## 打赏

开发不易，赞助点tokens费吧！！！

<p align="center">
  <a href="https://xiejhhhhhh.github.io/Draftpaper_loop/support/"><strong>打开交互式支持页 / Open the interactive support page</strong></a>
</p>

<table align="center">
  <tr>
    <td align="center">
      <img src="./docs/assets/donate_wechat_clean.png" alt="微信支付二维码" width="190"><br>
      <strong>WeChat Pay</strong><br>
      微信支付
    </td>
    <td align="center">
      <img src="./docs/assets/donate_alipay_clean.png" alt="支付宝二维码" width="190"><br>
      <strong>Alipay</strong><br>
      支付宝
    </td>
    <td align="center">
      <img src="./docs/assets/donate_paypal_clean.png" alt="PayPal 二维码" width="190"><br>
      <strong>PayPal</strong><br>
      国际支持
    </td>
  </tr>
</table>

打赏只支持项目维护，不代表商业授权。

## Star History

<a href="https://www.star-history.com/?repos=xiejhhhhhh%2FDraftpaper_loop&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=xiejhhhhhh/Draftpaper_loop&type=date&theme=dark&legend=top-left&sealed_token=dN1CtctMslTFeZ1LeZWQ4_T83BRMc0kIUoiQ8p6ZkXn9NrCTuVJtGVUApL1pW3_Po3Lc8-veuyauYcxHsTO3w1sjrU9MLHTHApw9K__MRIyYH-5imlH7KQ" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=xiejhhhhhh/Draftpaper_loop&type=date&legend=top-left&sealed_token=dN1CtctMslTFeZ1LeZWQ4_T83BRMc0kIUoiQ8p6ZkXn9NrCTuVJtGVUApL1pW3_Po3Lc8-veuyauYcxHsTO3w1sjrU9MLHTHApw9K__MRIyYH-5imlH7KQ" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=xiejhhhhhh/Draftpaper_loop&type=date&legend=top-left&sealed_token=dN1CtctMslTFeZ1LeZWQ4_T83BRMc0kIUoiQ8p6ZkXn9NrCTuVJtGVUApL1pW3_Po3Lc8-veuyauYcxHsTO3w1sjrU9MLHTHApw9K__MRIyYH-5imlH7KQ" />
 </picture>
</a>

图表由 [star-history/star-history](https://github.com/star-history/star-history) 提供。

## 最近更新
### v0.33.0（2026-07-19）-- Strict 作者补全与 Hash 绑定 Result Support

- Completion 分类在 60 条、三个学科族校准 fixture 通过后默认启用 strict。Preview 同时保留用户声明类别、系统推断类别、computed stale scope、证据校验和 suggested evidence refs；Apply 会在 preview 后重新核验所有引用 manifest。
- Result Support v3 从当前 resolved evidence、selected run manifest 或明确 run-bound 的结果表选择指标；downgrade/rescue 决策绑定同一个 checkpoint hash；未绑定的 required data role 会进入路线选择；post-Results 证据问题回到同一 checkpoint。
- 源码与 wheel 内置 workflow skill、contract、CLI reference、命令风险矩阵、schema registry、release manifest、中英文 README 和 package identity 统一为 v0.33.0 合同。

### v0.32.1-v0.32.2（2026-07-19）-- 能力真值、README 清晰度与 Shadow 校准

- v0.32.1 新增 capability truth matrix，在保持 README 既有 H2 结构的同时，明确当前版本能力、最终作者补全、发布顺序和实现证据。
- v0.32.2 新增 canonical completion classification、本地 evidence-ref 建议、Result Support signal adapters、checkpoint-hash 路线握手、整单路线边界和同步的 Agent 命令示例，并保留 shadow 校准阶段。

### v0.31.1-v0.32.0（2026-07-18）-- 架构整理、发布文档、跨平台发布身份及完成审计

- `v0.32.0` 完成 `H-01-H-07`、`M-01-M-12` 与 `R01-R11` 的发布对账，验证源码、editable install 和隔离 wheel 共用一套 210 命令控制面；完成 General/AAS/MNRAS 三期刊作者补全回归和五领域对抗发布回归；恢复 Python 3.10 TOML 兼容性，强化可选 bibliography 工具查找，并发布完成审计与沙箱边界评估。这些回归验证的是流程合同，不代表科研结论或生产托管隔离已经得到验证。
- `v0.31.9` 将 package metadata、release manifest、README、Git tag 与指定 wheel 绑定为同一发布身份。CI 覆盖 Windows 和 Linux 的 Python 3.10-3.12，并增加 macOS 控制面 smoke test；发布检查会拒绝过期 dist，并分别验证 minimal、plotting、full-text 和 MCP 安装档位。
- `v0.31.8` 新增只读 `token-report`，区分实际记录的 token/费用 receipt 与估算值，同时自动生成命令风险矩阵，并明确本地产品、许可证和托管服务边界。缺少供应商 receipt 或显式价格表时不会推测货币费用。
- `v0.31.7` 从权威 `CommandSpec` registry 自动生成完整 CLI 参考，命令名称、handler、风险等级和人工检查点 metadata 不再由 README 手工重复维护。中英文 README 保留原有的完整项目指南框架，只将完整命令清单链接到自动生成文档，而不是再次整体压缩 README。

- `v0.31.6` 将默认 wheel 限定为工作流、参考文献和 PDF/图像检查所需的 minimal runtime，不再静默安装 NumPy、pandas 或 Matplotlib。绘图、增强全文抽取和 MCP 使用独立 extra；科研插件延迟导入 NumPy，Doctor 会报告档位可用性和恢复命令，CI 分别安装验证 minimal/plotting/fulltext/MCP 环境。wheel metadata verifier 会防止可选运行栈重新漂入核心依赖，同时 minimal 安装仍保留打包的 paper-fetch fallback。

- `v0.31.5` 为 release fixture、capability pack、命令合同、release manifest、方法运行/公式 manifest 和图表评估注册 schema family。发布验证会检查 wheel 内资源的 schema，不再仅凭 JSON 结构看似合理就放行。CI 的第一方 coverage 门从 45% 提升到 65%，Pyright 范围扩展至命令控制面、completion/stale 路径、figure façade 和拆分后的 Methods 模块。

- `v0.31.4` 让当时全部 209 个 CLI 命令先进入 `CommandSpec`；`legacy_dispatch_count` 归零，`cli.py` 不再保留命令专用 fallback 链。尚未拆为 typed handler 的命令进入显式 namespace compatibility adapter，其数量继续公开而不是伪装成迁移完成。Pipeline stage 命令由 registry metadata 生成，`assess-figure-contracts` 也改用统一 figure façade。

- `v0.31.3` 将方法执行验证、公式提取和 Methods 正文写作拆为独立职责模块，并继续通过稳定的 `draftpaper_cli.methods` API 对外提供。figure contract façade 将 gate、语义、人工确认蓝图和 caption 检查统一为确定性的 `{source, code, severity, message}` issue list；旧 run manifest 字符串字段继续兼容，新调用方读取 `normalized_issues`。

- `v0.31.2` 将原先超过 3700 行的 plugin candidate 单体文件拆为 skill source 读取、能力提取、受控 promotion 和 contribution 审核四个模块。既有 `draftpaper_cli.plugin_candidates` 导入路径及受审计 registry hook 保持兼容；专门的包结构测试禁止单体文件回归，并持续验证提取、AcademicForge metadata、provenance、promotion、fixture 和 contribution 行为不变。

- `v0.31.1` 将 DPL 稳定 claim/evidence ID 接入真实的 claim contract 和 Scientific Evidence Registry fallback，不再只是测试辅助函数；项目显式 ID 仍保持权威。当前 claim、evidence、reference 与 Data 写作热路径统一使用共享 JSON/文本 IO、引用解析和 LaTeX 转义，同时从 artifact DAG 删除了未参与运行的并行假依赖图。

### v0.30.1-v0.31.0（2026-07-18）-- 发布门、精确 stale 传播与作者补全事务

- `v0.30.1` 在不公开实验性 manuscript completion 原型的前提下，对齐公开命令清单和 release manifest。core evidence、data quality、result validity、method verification 和 integrity gate 的非通过科学判定现在都会返回非零进程状态。MCP artifact 读取拒绝私有 locator 和凭证类文件；期刊及 registry metadata 抓取统一经过 HTTPS、host、DNS 与响应大小策略。
- `v0.30.2` 让 manifest 和 CLI method verification 使用同一个项目内 runner 合同，拒绝 inline Python 与 shell runner，限制声明的输入/输出路径，记录显式 system binary 例外，只向子进程传递白名单科研环境变量并在日志落盘前脱敏。写入命令在 handler 运行前检查声明写入根，运行后仍核对真实写集。文献检索会在 stage manifest、`status` 和 `doctor` 中区分 `success_with_items`、`success_empty`、`provider_error`、`auth_required`、`rate_limited` 和 `offline_fallback`。
- `v0.30.3` 用唯一的 13 类 change taxonomy 取代三套相互冲突的 revision/stale 词表。artifact DAG、外部漂移同步、章节修订、作者修订和审稿修复现在统一输出 canonical 名称，并从同一个合同推导 stale 范围。Methods 与 Discussion 修改会从真实章节阶段开始，证据变化必须重新打开科学链；revision preview/apply 还会绑定同一个 promoted evidence snapshot。
- `v0.30.4` 注册 `dpl.manuscript_completion.v1`，并新增 `prepare-manuscript-completion` 和只读的 `manuscript-completion-status`。生成的作者模板覆盖结构化 metadata、基金、数据/代码可用性、短标题、关键词和用户确认文献；期刊报告明确区分 required、recommended、missing、placeholder 与 not-applicable。Completion 输入不能直接替换科学证据、指标、论断或图表，后续 preview/apply 命令在事务门通过前仍不公开。
- `v0.30.5` 使用稳定 paragraph ID、expected text/hash 和可选 occurrence 定位作者修改，LaTeX 行号只作为非权威提示。只有稳定锚点仍一致时才允许报告并重新定位行号漂移；stale、歧义、重复 revision key 和重复目标会让整个 packet 被拒绝。一个 packet 可以在同一 source-map/project revision 上解析多章节与用户确认文献，项目修订命令也不再允许读取项目目录外的内容文件。
- `v0.30.6` 将 completion preview、apply 与 rollback 串成同一个 hash 绑定事务。Preview 在不触碰 canonical source 的情况下生成 metadata/section/BibTeX 统一 diff、候选 LaTeX 与候选 PDF。Apply 会重新核对 packet、project revision、source map、evidence snapshot 和 before hash，再原子写入 metadata、文献、章节、stale 状态、ledger 与 exact-text user lock。重复 apply 保持幂等，注入故障会恢复完整写集，rollback 不会覆盖 completion 后又被修改的产物；`compile_required`、未生成的 Codex patch 和科学证据变更均明确为非通过状态。
- `v0.30.7` 将已应用的 completion manifest、论文 metadata、全部 canonical section、BibTeX/reference registry、promoted evidence、result/figure manifest、最终 citation-audit snapshot、integrity/quality 报告、两份独立盲审和 `main.pdf` 绑定为同一个 release hash。任何非通过或 stale 的绑定产物都会阻止 review 与 confirmation。README 开头现已直接说明当前 evidence-first 路径和最终作者确认点，并在 `docs/` 中提供完整中英文 completion 指南。
- `v0.31.0` 完成最终作者工作区的多期刊回归，覆盖通用 article、AAS 和 MNRAS 的 frontmatter 语义，并实际编译 XeLaTeX 候选稿。发布测试包含单/多作者、单/多单位、ORCID、通讯作者、基金、数据与代码链接、用户确认文献、多段原子修订、回滚、用户锁和最终发布绑定，同时验证源码 checkout 与隔离 wheel 安装行为一致。

### v0.28.1-v0.30.0（2026-07-17）-- 事务化证据架构与跨学科发布合同

- `v0.28.1` 将章节修订升级为真正的多产物事务。通过审阅的修改写入章节权威源文件，重复组装 LaTeX 后仍会保留，并触发真实的下游 stale 状态；注入故障时 canonical、candidate 与项目状态会一起回滚。这一版本真正完成了 `v0.27.2` 最初提出的事务保证。
- `v0.28.2` 将 210 个学科插件全部迁移到显式 manifest v2 合同。运行类型、验证等级、成熟度、部署状态、fixture 清单和执行策略不再静默推断；源码与 wheel registry 统一为 546 个 fixture，并明确区分 175 个 contract-only、25 个 code-generator 和 10 个 fixture-executed 记录。
- `v0.28.3` 为 `project.json`、YAML 镜像和全部 stage manifest 增加统一 state revision、项目级锁与回滚。write-set 越界会尽可能恢复项目内改动；MCP 科研或网络执行必须使用绑定具体项目、命令和参数的短期 HMAC capability token。
- `v0.29.0` 将 artifact dependency model 升级为包含真实路径、hash、owner、producer/consumer 边和 authoritative/derived 角色的依赖图。第一方 schema ID 不再混用产品版本号，统一进入独立的 schema family registry。
- `v0.29.1` 为 204 个 CLI 命令建立统一的 normalized runtime command contract，并将其作为一致性校验、MCP schema 和 doctor 诊断的权威视图。迁移边界会明确报告为 80 个注册 handler 与 124 个兼容 dispatch，后续拆分进度不再被隐藏。
- `v0.29.2` 新增针对性 Ruff 与 pyright、覆盖率、项目依赖图漏洞审计与 CycloneDX SBOM、敏感信息扫描、固定 GitHub Action commit SHA、可复现 CI 工具约束、源码/wheel 发布身份、SPDX 风格许可证元数据和无警告 wheel manifest。
- `v0.30.0` 将 wheel 安装回归扩展到科学图像+机器学习、地理+机器学习、天文+机器学习、生物信息+医学和物理/量子五类项目。每个夹具的六组主图都必须追溯到 research claim、data plugin、method plugin、项目 run output、evidence ID 与 review rule；错误 cohort/run/unit/model/metric/dimension、空白图、插件冒充和引用语义反例仍必须被拒绝。

发布检查：

```powershell
draftpaper validate-command-contracts
python -m draftpaper_cli.release_contract
python -m draftpaper_cli.release_regression --output tmp/release-v0300
```

### v0.26.1-v0.28.0（2026-07-16）-- 可执行科研语义与精确恢复

- `v0.26.1` 将失败明确分为产物 stale、引用支撑、正文语义、可复现包、渲染质量、科学分析、图表合同和人工审阅八类。引用或匿名包失败不再兜底返回 `plan-figures`；质量报告会给出真实失败 predicate、受影响产物和唯一合理命令。交互终端默认摘要输出，重定向/API 保留完整 JSON，也可用 `--compact` 与 `--json-full` 显式选择。
- `v0.26.2` 新增领域无关的 `DataProvenanceContract`、`CohortRegistry`、`CohortViewRegistry` 和追加式 join/filter ledger。每个分析视图声明父 cohort、样本单位、数量、缺失策略、split、允许用途和论断边界。展示子集与回归子集可以不同，但禁止静默混用数量或样本单位。
- `v0.26.3` 新增 `ExecutableAnalysisSpec`、公式 AST、重采样合同和事前运行选择策略。estimand、cohort view、split、预处理拟合范围、实现入口、不确定性语义、校准定义、公式和变量解释来自同一合同。ECE 定义漂移、伪 paired/grouped 区间以及事后挑最佳 seed 作为主结果都会被阻断。
- `v0.27.0` 将插件充分性拆为 bootstrap 与 release 两层。全新课题可以先使用受审计的 project-local 实现继续设计，不再形成“缺插件所以不能生成代码”的死锁；正式发布仍要求已验证的数据/方法绑定、输入输出 hash、执行范围和 capability passport。AcademicForge/GitHub rescue 只在真实能力缺口时启动。
- `v0.27.1` 将 Scientific Evidence Registry 主键升级为 estimand/cohort-view/analysis-spec/run/model/split/aggregation/dimension，并为章节生成带句子 hash 和 evidence ID 的 claim map。Figure Contract v2 绑定 claim、panel、cohort view、estimand、analysis spec、run、evidence 和图内文字；期刊宽度 QA 记录字体、重叠、裁切、配色与 caption。Results 后的学科规则读取编译后的 claim-level 证据，不再依赖宽泛角色字符串。
- `v0.27.2` 新增 artifact dependency DAG 与事务命令 `apply-section-revision`。引用局部、纯排版、正文语义、cohort、analysis、run、figure 和 claim contract 修改分别触发不同的最小 stale 集合。已通过且候选 hash 一致的功能发布不会被可选 manifest 回填意外重开。
- `v0.27.3` 匿名审稿包只收当前 selected run、正文引用图表及 Python import 依赖闭包，排除无关历史图表，并在发布前编译 smoke test。manuscript/evidence/bundle hash 变化后，旧 reviewer 报告按旧 bundle hash 归档。finding 结构化区分局部文案、渲染、可复现性、补分析、论断降维和新证据。
- `v0.28.0` 统一 direct support、方法/工具 provenance、比较语境和数据集/产品 provenance 四类引用意图，继续保留全部已确认参考文献并优先修改正文。段落证据保持内容寻址、delta 缓存。五类跨学科发布夹具和 cohort、校准、run selection、图表、插件、引用对抗回归共同保护通用架构。
- 新增 `JournalIntentContract`：只有已确认期刊才能显示投稿标签，provisional/unset 项目保持中性 draft。状态明确区分 `draft_pdf_ready`、`review_blocked`、`release_ready`；`doctor --explain` 以只读方式展示 artifact DAG 和恢复理由。

关键命令：

```powershell
draftpaper doctor --project <project> --explain
draftpaper apply-section-revision --project <project> --section methods --input revised_methods.tex
draftpaper prepare-independent-manuscript-review --project <project>
draftpaper status --project <project> --compact
```

### v0.25.1-v0.26.0（2026-07-14）-- 人工确认研究蓝图、任务感知统计验证与项目工作区隔离

- 新论文默认统一创建在配置的中央 `projects` 根目录，不再跟随 idea 或数据集所在位置。可通过 `DRAFTPAPER_PROJECTS_ROOT`、用户配置或 `--projects-root` 设置根目录；自动 slug 最长 48 个字符，并附带稳定的 8 位 project ID。干净的 `_vN` 子项目也采用同一短路径规则。
- 新增 `ProjectWorkspacePolicy`、`ArtifactOwnershipGuard`、`path-budget-check`、`doctor-project-layout` 和带 hash 校验的 `adopt-orphan-artifacts`。除显式 export 外，流程产物、日志和临时文件都必须留在对应论文项目内部。
- 大型数据集默认保持原位只读。公开数据源合同与指纹只保存逻辑 ID 和相对 locator；本机绝对路径进入默认忽略的 `external_data_locators.private.json`，复制策略默认为 `manifest_only`。
- 新增任务感知的 `StatisticalValidationContract` 和 `review_rule_coverage_report`。分类、回归/拟合、分组或时间验证、空间分析、表征混杂、异常稳定性、生存分析和仿真收敛分别获得不同的证据要求。除非来源是用户/期刊要求、有引用的领域规范或已验证学科插件，否则禁止使用跨项目通用的 F1、R2、p 值或拟合精度阈值。
- 中文优先的研究方案包成为真正的人工确认点。`review-research-plan` 集中展示研究方案、claims、图表故事板、panel 结构、数据/方法需求、统计合同、插件预检和可行性限制；`confirm-research-plan` 冻结其精确 hash。任何科学合同变化都必须先执行 `reopen-research-plan`。
- 关键图表代码只能读取当前已确认的研究蓝图。每张主图和 panel 都携带 confirmed plan hash、claim、数据与方法 requirement ID 和统计验证 ID；`validate-confirmed-figure-alignment` 会拒绝缺失、替代、额外或语义已经变化的主图。
- 显式 research storyboard 不再追加学科通用 fallback 图。主图数量不能再由普通直方图、相关图或 metric summary 凑足；科学故事角色不足时必须返回 research plan 修订。
- 新增结构化图组 caption 合同。第一完整句概括整组图且不能由逗号短句串联；后续逐一解释所有 panel、cohort、估计量、不确定性和 claim boundary。图像路径采用 `fig_01.png` 等短名称，完整科学标题保存在 metadata 中。
- 新增关键图表执行前的 support loop。能力缺口先生成 project-local、学科插件、AcademicForge、GitHub 和 connector 救援任务；仍不足时，由用户在补数据/方法与研究范围降维之间选择。结果生成后的 claim 降维仍是独立路线，并冻结已有图表和指标。
- 面向用户的 core evidence 页面改为“关键结果与论断支撑确认”，明确展示被确认的研究问题、cohort、方法运行、统计证据、不确定性和最大 claim 强度。最终发布另设同一 hash 绑定的确认包，包含 `main.pdf`、最终 citation audit、两位独立盲评报告和质量报告。
- wheel 回归扩展为 scientific-image astronomy+ML、geography+ML、time-domain astronomy+ML、bioinformatics/medicine 和 physics/quantum 五类场景，并验证任务感知统计合同和规则缺口显式报告。当前源码验证为 `565 passed`；完整的 15 项验收证据见 [`docs/audits/2026-07-14-v0260-acceptance-report.md`](docs/audits/2026-07-14-v0260-acceptance-report.md)。

新增关键命令：

```powershell
draftpaper create-project --idea "Your research idea" --field "astronomy machine learning"
draftpaper review-research-plan --project <project>
draftpaper confirm-research-plan --project <project> --plan-hash <hash>
draftpaper path-budget-check --project <project>
draftpaper doctor-project-layout --project <project>
```

### v0.24.1-v0.25.0（2026-07-13）-- 安全科研运行时、真实可运行插件与薄型 MCP

- 将 canonical `draftpaper-workflow` skill 打入 wheel，并新增 `install-skill` / `skill-doctor`。Agent 不再手写和记忆完整阶段顺序，而是服从 `status`、`verify-next-action` 和 `continue`，避免用户目录中的旧 skill 用过时流程驱动新版 CLI。
- 将 186 条公开命令升级为 CommandSpec v2：声明风险等级、读写 glob、禁止路径、资源类型、超时、幂等性、确认策略和输入/输出 schema。项目修改命令会核对真实 write set；父目录逃逸、UNC/device path、symlink/reparse 越界、受保护人工动作、任意 shell/raw write、SQL、Git push 和凭证泄露均不会进入 MCP 公共接口。
- 新增 Plugin Execution Contract v2 和确定性的 `plugin_catalog_snapshot.json`。209 个插件 manifest 均获得显式合同或兼容适配合同；全局 `catalog_hash` 与单插件 contract hash 贯穿充分性、绑定、执行、图表 trace 和学科审阅。contract/fixture-only 以及 mock API/GPU/server 插件仍不能支撑科研结果。
- 通过显式 runnable profile registry 晋级 22 个高频本地 data/method 能力和 10 条 review rule。每个晋级能力都执行真实确定性算法，并包含 minimal、failure、boundary fixture；review rule 声明适用边界和阈值来源。其余 foundation rule 继续 advisory，外部合同在真实验证前继续 mock-only。
- research plan 现在显式声明主图 story role；正式写作移除 first-eight evidence fallback，改用 claim/run/cohort/model/figure/citation role 检索。段落证据采用内容寻址缓存和 delta packet；held-out 重复证据回归在保留全部 evidence ID 的同时，将真实段落输入减少至少 35%。
- 新增 Citation Role Contract v2：`dataset_provenance`、仪器/产品定义、处理方法支持、方法/工具背景、既有结果比较、机制/解释和一般背景。角色在写作前分配，citation audit 在写作后核验，继续坚持“先收紧或改写 claim，不以删参考文献换全绿”。
- Integrity 优先读取 promoted、run-aware Scientific Evidence Registry 的 cohort 数字；未绑定当前 run 的旧 `sample_composition.csv` 仅作为兼容来源。主图叙事显式保留 direct signal、comparison、mechanism/ablation 和 uncertainty/boundary 位置，诊断图不能占满主图故事。
- 新增 `workflow_trace.jsonl` 与 `audit-workflow-runtime`，记录 run/command ID、attempt、耗时、输入 hash，以及 process/command/scientific/transaction 四维结果，并诊断循环、重复高成本运行和超大 packet。新增 SQLite 持久任务 `submit-job`、`job-status`、`job-cancel`、`job-notifications`、`recover-jobs`；worker 可跨终端存活，丢失后标记 `orphaned`，不会静默重试科学失败。
- 新增 10 工具的本地 stdio Draftpaper MCP（`python -m draftpaper_cli.mcp.server`），并提供可移植 `mcp-install` 和确定性 `mcp-doctor`。MCP 只是 CommandSpec 与 CLI handler 的薄投影，支持有上限的 artifact selector，不能直接执行人工 checkpoint 或破坏性管理动作。
- wheel 内 held-out 发布回归扩展为 astronomy+ML、Euclid 语境 geography+ML、bioinformatics+medicine，以及此前未作为发布夹具的 physics+quantum，并保留 scope、图表、插件 runtime 和 citation 对抗检查。机器可读闭环账本见 [`docs/audits/v025_issue_ledger.json`](docs/audits/v025_issue_ledger.json)；41 条 AcademicForge 集合级 placeholder 继续标记 `requires_source_inspection`，不会进入插件充分性。
- 最终源码验证为全部 `555` 项测试通过，其中包含明确的四领域 wheel 验证器合同回归。package compile、隔离安装 v0.25.0 wheel、canonical skill hash、209 插件 catalog、32 个 runnable profile、10 工具 MCP stdio 握手、4 类 held-out 学科回归及全部对抗发布检查均通过。

关键安装与诊断命令：

```powershell
python -m pip install -e .[mcp]
draftpaper install-skill --force
draftpaper skill-doctor
draftpaper mcp-doctor
draftpaper mcp-install --output .mcp.json
```

### v0.23.1-v0.24.0（2026-07-13）-- 项目隔离、原生恢复与独立单稿审查

- 新增干净的 `_vN` 项目版本化。旧项目始终只读，只按白名单导入可复用资产并记录 hash 与 lineage receipt；passport、stage manifest、插件充分性报告、figure metadata、审计报告和 evidence snapshot 等派生状态不得作为 active evidence 复制到新项目。
- 新增项目 system of record、命令事务、stage receipt、精确 stale 传播和派生产物重建计划。Results 发生变化时必须先重建当前 result manifest，再执行学科审阅，避免旧 review 套用到新正文或新证据。
- 新增科研能力包、路由评估、所有权检查、project-local 数据/方法审计和项目方法实现合同。正式插件缺失不再形成“没有方法所以不能生成代码”的死循环；只有数据与方法 rescue 都已穷尽时才允许阻断科研图表生成。
- 新增 run-aware Figure/Paragraph Evidence Resolver 和任务 token budget。Doctor 只用每个写作任务最新的 packet 判断当前上下文是否超限，同时单独保留 lifetime token 成本，历史重试不再造成永久误报。
- 新增规范化 reference registry、同一 work 的版本去重决策、目标期刊 bibliography 合同和 References 渲染 proof。参考文献格式检查与 claim-level citation support 分离，citation repair 仍坚持保留已确认参考文献。
- 新增递归第三方 provenance，覆盖 paper-fetch-skill、AcademicForge、上游科研 skills、Gbrain 设计影响和 Superpowers 计划影响，记录固定 commit、license、use mode 和影响路径；Gbrain 只作为可选设计参考。
- 新增 Draftpaper-loop 原生 `doctor`、`recover`、`start`、`continue`、`review` 和 `revise`，所有 CLI parser 进入统一 `CommandSpec` 合同。Doctor 可重复、只读；Recovery 不会静默确认图表、下调 claim、删除参考文献或 promote 插件。
- 用独立单稿审查替代 Manuscript A/B 和相对原稿质量比例。两位 reviewer 在独立会话中审查同一份冻结匿名生成稿及真实图表；只有未解决 critical/major 均为 0 才可发布，重大分歧进入仲裁而不是简单平均分数。
- 新增审稿后 manuscript revision workspace，支持稳定段落 ID、LaTeX 行号、结构化 metadata、自定义参考文献、diff/PDF 预览、hash 校验接受、回滚和精确 stale。
- 匿名审稿包新增定位安全的可复现补充材料：source/model provenance、经过隐私筛选的阶段代码与测试，以及无需额外依赖的冻结结果 replay；私有路径、凭证和身份信息不会进入审稿包。图注修正可通过结构化 metadata 完成，不会改写科研图表证据。
- 章节证据包新增模型比较语义。只有预处理与模型嵌套关系经过验证时，正文才允许写“增量”或“条件贡献”；否则必须写成精确的 pipeline 性能差异，并区分 fold mean、pooled 和 resampling estimand。
- 完成 astronomy+ML、geography+ML、bioinformatics+medicine 的通用能力链回归，并用只读本地数据完成一个陌生 scientific-image 课题的 core evidence 人工确认、最终正文、PDF、完整性、参考文献格式与引用核查。最终 citation audit 保留全部 17 篇参考文献和 30 处引用，`unsupported=0`、`unverifiable=0`。
- 两个全新独立会话在不知道原稿和历史报告的前提下审查同一份冻结匿名最终稿。两位 reviewer 都只给出 minor revision，科学正确性分别为 0.95 和 0.91，未解决 critical/major 均为 0，无需仲裁，发布门通过；minor 建议继续保留在 revision queue，不会被静默标记为已解决。
- 最终验证为 `537 passed`，package/tests compile 通过；隔离安装的 v0.24.0 wheel 与源码一致，包含 209 个插件、545 个 fixture、6 个 capability pack 和 6 条第三方来源链；三类领域回归及全部对抗检查通过。GitHub Actions 的 wheel 安装以及 Linux/Windows Python 3.10-3.12 完整矩阵全部通过。Eval capture/replay 只验证脱敏的软件结构，不把已有论文当作质量基线。

### v0.23.0（2026-07-12）-- Wheel 发布回归与可验证质量声明

- 新增随 wheel 发布的 geography+machine learning、astronomy+machine learning、bioinformatics+medicine 三类脱敏回归合同。普通 `pip install` 后会实际运行插件充分性、项目级执行证据、图表追踪、像素与底层表格核验、Scientific Evidence Registry、Results 数字绑定、复合学科 review rules 和最终 citation audit。
- 新增对抗回归，强制拒绝错误 run/cohort/unit/split/model、错误 metric/量纲、伪 metadata 空白图、仅有合同或 fixture 的插件，以及引用中的否定冲突、数值不符和因果反转。`status` 还必须保持项目文件哈希不变。
- 自动关键词、metadata 和文件存在性评分不再有权单独声明论文质量。v0.23.0 的临时比较协议已被 v0.24.0 的独立单稿审查合同取代；当前项目不需要也不会向 reviewer 提供原稿。
- wheel 隔离安装会核对源码与安装包都发现 209 个插件、545 个 fixture，并在安装环境中运行三领域与对抗回归。CI 同时覆盖 Python 3.10-3.12、Linux 和 Windows。
- 完成一次 astronomy+machine learning 的 evidence-first 全流程实跑，覆盖研究合同、项目本地能力补齐、六组科研主图、五个章节的自由撰写与 Scientific Editor 生命周期、最终 PDF 组装和引用复核。最终快照保留全部 12 篇总结文献，共形成 25 处引用，`unsupported=0`、阻断项为 0。
- PDF 技术对比确认自动稿保留了已验证的 cohort、baseline/Transformer 指标、消融方向、不确定性边界和六图叙事。Introduction 与 Discussion 的结构和文献整合已达到可比或更好水平；直接观测示例以及 Data/Methods/Results 的细节仍少于参考稿。自动功能评分为 0.9825，但在缺少两位独立盲评者之前不宣称正式达到 95%。
- 使用 `tiktoken` `o200k_base` 统计可观察写作消耗：章节证据包输入 122,238 tokens，接受稿输出 5,716 tokens，共 127,954 tokens；Results 40,075、Introduction 15,691、Data 17,139、Methods 22,920、Discussion 32,129。确定性 CLI 阶段不消耗模型 tokens，隐藏推理与平台开销不作估算。完整问题链与统计见 [`docs/audits/2026-07-12-astronomy-v0230-full-run.md`](docs/audits/2026-07-12-astronomy-v0230-full-run.md)。
- 全流程完成后的本地测试为 `441 passed`。最终质量门已没有未解决的科学、写作、图表、证据快照、PDF 或引用错误；在两位独立盲评者的完整稿件对比尚未录入前，系统仍会按设计拒绝正式发布。

### v0.22.1-v0.22.8（2026-07-12）-- 证据语义、运行真值与状态内核

- 修复 wheel 资源打包和 citation audit/parity schema，正式写作流程接入“章节证据包 -> Codex 自由撰写 -> 候选验证 -> Scientific Editor -> 显式接受 -> 发布”；deterministic fallback 仅用于诊断。
- Evidence Binding v2 要求数字与论断绑定 `evidence_id/run/cohort/sample_unit/split/model/metric_dimension`，并校验指标名称与量纲；错误范围或同值异义会阻断写作。
- 插件运行等级拆分为 `contract_only`、`code_generator`、`fixture_executed`、`project_validated` 和 `live_validated`。只有带输出哈希的真实项目或 live 运行可以满足主图能力。
- Reviewer Engine v2 读取标准 EvidenceBundle，执行真实阈值、量纲、baseline、ablation、不确定性与插件 `evaluate_rule`；科学异常优先进入 Results 局部语义修复。
- 图表核验读取真实像素、坐标/文字区域、面板和底层表格；citation audit 增加 passage、数值、否定、因果方向和论断强度检查，修复任务保留参考文献并要求段落级重写。
- 新增只读状态内核、显式迁移、原子 JSON/JSONL 写入与跨平台锁，并拆分 command registry、artifact repository、schema adapters、plugin runtime、writing coordinator 和 release coordinator。

### v0.21.1-v0.22.0（2026-07-12）-- 论文叙事与科学写作架构

- 新增领域无关的 Paper Narrative Engine。它读取真实 YAML/JSON 研究产物，生成 `paper_brief.json`、`figure_story_arc.json`、`manuscript_argument_map.json` 和 `section_claim_allocation.json`；主图与附录/支撑图按研究发现组合，每组明确科学问题、证据、比较关系和论断边界。
- 新增章节证据包、段落提纲和 Results synthesis plan。Introduction 与 Discussion 使用研究空白/文献比较矩阵，Data 与 Methods 根据数据清单、阶段归属代码、插件执行账本、公式和 figure-code trace 重建科研生命周期。指标只允许通过 evidence、run 或 artifact 标识绑定，不再根据图题字符串猜测。
- 新增语义 panel contract 与 `prepare-panel-repair`。每个 panel 都要声明问题、数据子集、科学单位、数据角色、方法输出、比较关系、统计检查、图形语法、预期结论和论断边界；修复仅影响失败 panel 的证据链，禁止用更弱或仅仅相似的图替代。
- 新增期刊写作合同与功能型风格画像，只学习章节顺序、信息密度、图注密度、语态、数字报告、术语定义和推理功能，不复制参考稿件措辞。
- 新增最多三轮、可审计的段落级 Scientific Editor。它记录段落哈希，拒绝大范围整章改写，保留证据与引用，并禁止为了通过 citation audit 而删除参考文献。
- 用校准后的科学维度替换关键词计数式质量评分。正式发布要求所有核心章节都是已验证的 `codex_free_candidate`、共用同一证据快照、Results 与图表质量通过、无阻断性证据冲突、参考文献覆盖完整，并且 citation audit 晚于最终章节验证。科学正确性是硬要求，功能质量必须达到 0.95 以上。
- 新增 geography+machine learning、astronomy+machine learning、bioinformatics/medicine 三类交叉学科架构回归，确保通用代码不会写入测试项目专属的模型、指标、图表数量或论文措辞。

### v0.21.0 (2026-07-11) -- 图表与文稿 95% 质量合同

- 新增 `results_narrative_contract.json`，把每张主图区分为研究边界、建模前信号、模型对比、组件归因、误差与不确定性等独立叙事角色，并绑定同一运行中的指标、科学问题和论断边界。Codex 仍自由撰写，但不能再用同一段模板解释所有图。
- 新增 `prepare-section-writing` 与 `assess-manuscript-quality`。Results 按证据真实性、叙事覆盖、科学推理、论断校准和行文多样性评分；正式候选稿最低要求为 0.95，错误指标或重复模板会进入修复路线。
- 新增 `assess-figure-publication-quality`。PNG 存在不再等于合格，主图还必须满足语义合同、数据/方法插件运行追溯、面板完整性、统计解释、像素尺寸与可读性要求。
- 通用绘图器不再把未知主图类型静默替换成数据概览图；主图缺少对应方法输出时进入插件补齐，只有明确的 supporting 图才允许使用通用诊断视图。
- 新增 `prepare-results-semantic-repair` 和 `assess-paper-quality-parity`。前者只修错误论断片段并保留已验证的六图叙事，后者汇总图表、Results、Introduction、Data、Methods、Discussion 与 citation audit；总分未达到 0.95 时最终 `quality-check` 不能通过。

### v0.20.2 (2026-07-11) -- Results 后置学科审查与能力救援边界

- 制图前的 figure contract 不再运行 `review_rule`。数据和方法插件负责产生图表；只有这些插件实际参与生成的图表，才会在 `review-results-with-discipline-rules` 阶段激活匹配的学科审稿规则。
- Results 中无法追溯的指标、内部路径式表达、错误引用位置和图表解释缺失现在进入 `repair_required`，优先重写或收紧论断，不再被误判为图表生成失败。
- 插件缺口先进入 `rescue_required`，依次审计项目本地资产、现有注册表、AcademicForge 和 GitHub 科研代码。新增 `record-plugin-rescue-outcome`；只有四条路线都有可审计检索记录且仍找不到必要数据/方法能力时，才进入 `blocked_unavailable` 并提示用户无法生成对应图表。

### v0.20.1 (2026-07-11) -- 项目本地能力审计与 Results 语义核查

- 在插件充分性门与外部救援之间新增 `audit-project-capabilities`。该命令会审计阶段归属的数据和方法资产，记录隐私安全的相对证据路径及哈希；只有当前项目可验证的实现才会形成受限 `covered_project_local` 绑定，不会修改全局学科模块，也不会绕过 candidate 验证和明确 promote。
- Results 学科审查现在不仅检查图表，还会核查正文语义：无法追溯的指标主张、内部 artifact 表达、把引用当作结果证据、缺少图表解释、插件/运行追溯不完整和 review-rule 证据冲突都会被报告。
- Data 与 Methods 写作上下文会读取清洗后的数据/方法绑定角色，使可复用插件和经过审计的项目本地实现能够改善科研表述，同时不暴露路径、命令、manifest 或凭证。

### v0.18.9-v0.20.0 (2026-07-11) -- 能力驱动的复合学科执行链

- 在 research plan 完成后新增 `discipline_contract.json` 和 `research_capability_contract.json`。它们会声明主学科、次学科、跨学科的数据/方法/review 归属，以及每个计划主张和主图对应的稳定能力需求。
- 新增 `assess-plugin-sufficiency`。该门控会按数据角色、方法族、输出合同、运行等级、验证等级、aliases 和学科兼容性，结构化匹配已注册的 `data_connector`、`method_template` 和 `review_rule`。mock、plan-only 或外部合同不能被当作主图的可执行支撑。
- 新增 `prepare-plugin-rescue`。能力缺口会形成范围明确的补齐路线：现有插件、AcademicForge 候选处理、许可证感知的公开科研代码检索、泛化、验证、去重，以及经人工确认后的 `promote-plugin-candidate --write`。项目专属或许可证不明确的代码保持在项目本地。
- 新增 `execute-data-plugins`、`execute-method-plugins` 和阶段归属的 `plugin_execution_ledger.jsonl`。账本记录 manifest/template 哈希、参数、运行状态、输入/输出哈希，以及 fixture 与真实项目结果的区别；fixture 运行不会被误认为科研证据。
- 新增 `results/figure_plugin_trace_report.json/.html`。每张主图在进入 Results 证据前都必须追溯到 research-plan claim、已覆盖的 data plugin、已覆盖的 method plugin、review-rule 路线和已验证的项目运行产物。代码生成只允许基于明确的运行前绑定链；缺少环节时进入插件补齐路线，不会生成相似替代图。
- 在 `write-results` 后新增 `review-results-with-discipline-rules`。该审查结合 Results 正文、完整图表追溯、插件绑定、已验证运行产物和复合学科 review rules。只有成熟、已 promote 且完成证据绑定的规则可以在科学层面阻断；任何图表追溯缺口都会停止后续正文流程。
- `status` 和 `run-pipeline` 新增 `plugin_sufficiency_required`、`plugin_gap_detected` 状态。跨学科回归夹具覆盖 geography+machine learning、astronomy+machine learning 和 bioinformatics+medicine。

### v0.18.8 (2026-07-11) -- 本地 Skill 地基扩展与外部 mock 合同

- 第一方本地 foundation catalog 已扩展到 159 个参数化插件，覆盖统计、实验设计、经典机器学习、表格/数组处理、科研可视化、地理、天文、生物信息、医学、化学、材料、物理和量子科学。所有插件只部署在对应学科的 `data_connectors`、`method_templates` 或 `review_rules` 目录中。
- 原先合并的能力已拆成可独立选择的合同，包括 statistical analysis/power/design、Polars、Vaex、Dask local mode、Zarr、Matplotlib、Seaborn、NetworkX、GeoMaster 风格的本地坐标操作、Astropy FITS/WCS/Time/units/coordinates、生物信息 CPU 工作流、Pydicom/BIDS/NeuroKit2/survival、Molfeat、FluidSim CPU 和 Cirq 本地模拟。
- 新增 12 个 API、远程服务器和 GPU 外部 foundation 合同。它们只使用 `mock_validated` fixture 和明确的 `task_contract`；全部记录 `live_execution_performed: false`，不会抓取数据或连接外部服务，并把所需凭证明确列为用户确认输入。
- 真实外部验证严格按论文项目进行：只有用户授权的项目确实需要某个 API、SSH 服务器或 GPU 模型时才验证它，并带 provenance 升级该单个插件的 validation level，而不会把任何外部能力泛化为全局 live capability。

### v0.18.7 (2026-07-11) -- Manifest 驱动的本地学科插件地基

- 学科插件 manifest 已接入运行时模块注册。在 `discipline_modules/<discipline>/{data_connectors,method_templates,review_rules}/<plugin>/` 下新增合法目录后，会自动扩展该学科的 `DisciplineModuleSpec`；只有 manifest 的新学科也可被调用，不再必须新增静态 `module.py`。
- 新增插件运行等级：`runtime_class` 用于区分 `local_pure_python`、`local_optional_dependency`、`remote_api`、`remote_server`、`gpu_model`、`laboratory_hardware` 和 `support_only`；`validation_level` 用于区分 `plan_only`、`mock_validated`、`fixture_runnable` 和 `live_validated`。本地模板不会把未安装 package、远程服务、集群或 GPU 作业伪装为已运行。
- 新增 80 个第一方、参数化的基础插件，每个包含 `template.py`、manifest 以及正常/失败/边界 fixture，覆盖本地统计与经典机器学习、表格和数组处理、科研可视化、Astropy 的 FITS/WCS/Time/units/coordinates、GeoPandas 的矢量与 CRS 工作流，以及 chemistry、materials_science、physics、quantum_science、neuroscience 五个新学科地基。
- 每个新学科先提供 3 个本地 data connector、5 个 method template 和 5 条证据绑定的 advisory review rule。review rule 在具备学科证据、fixture 和明确 promote 前保持 contextual candidate，不会直接成为硬阈值。
- candidate promote 现在会在 `template.py`、fixture 和 provenance 旁边写入统一的 `manifest.json`，该 manifest 会立即被运行时自动注册器读取；与已有插件高重合的 candidate 会成为 `augment_existing` overlay，合并 aliases、variants、fixture refs 和 provenance，而不会静默生成重复的插件合同。

### v0.18.6 (2026-07-11) -- 第三方 skills 到学科插件与运行时 review rule 门控

- 新增 metadata-only 的第三方 skills 转换链路：`snapshot-skill-source`、`inspect-skill-source`、`index-skill-source`、`classify-skill-source`、`map-skill-capabilities`、`extract-skill-capabilities` 和 `compile-skill-source`，用于把 AcademicForge 类 skill catalog、个人科研 skills 或本地项目中沉淀出的技能转为候选报告，而不是复制源码或直接安装插件。
- AcademicForge 集合记录会根据公开分类 metadata 展开，并与各集合声明的 skill 数量核对。详细记录和待进一步读取来源的 placeholder 都进入索引，同时显式报告静默丢失数量；当前 live metadata-only 验证已对齐 340 条声明，其中 299 条已有 registry/classification 明细，41 条保留为待 source inspection 的 placeholder。
- 明确正式学科模块只接受 `data_connector`、`method_template` 和 `review_rule` 三类可 promote 子插件；`workflow_recipe`、`paper_contract` 和 `shared_capability` 保留为支撑层候选，不直接写入 `discipline_modules/<discipline>/`。
- 新增 `review_rule_signal_scan` 和支撑层回流记录，使 workflow、paper contract 和 shared capability 中的统计验证、模型 baseline/ablation、split/leakage、图表-论断一致性、引用支撑、data/code availability 和可复现性条件可以沉淀为学科化 `review_rule_candidate`。
- 扩展 `ReviewRuleSpec`：review rule 现在是证据绑定的科研质量门，必须声明适用学科、方法族、数据角色、证据绑定、规则类型、阈值模式、阈值验证状态、支撑层信号来源、fixture refs、aliases/variants、回流来源、阈值来源、失败路由、成熟度和人工确认状态；模型精度、拟合优度和统计显著性阈值在缺少期刊规范、领域共识、公共 benchmark 或用户确认时默认只能作为 contextual/comparative/human_confirmed 规则。
- 新增运行时 review-rule gate。`prepare-method-blueprint`、Semantic Figure Contract 核查、`assess-result-validity`、`assess-result-support` 和 citation audit 都会写入 review-rule gate 报告，使已 promote、达到 runnable/mature 且完成证据绑定的规则可以阻断弱证据或不充分论断，而 candidate/foundation 规则仍保持 advisory。
- 运行时 gate 现在会读取 `evidence_binding.required_fields` 和 `evidence_binding.forbidden_conflicts`，因此已 promote 的规则可以基于缺失证据或 train/test leakage 等证据冲突阻断写作；支撑层和 candidate 规则在人工审阅前仍不会自动变成硬门槛。
- Review-rule gate 报告现在会写出 `rescue_tasks` 和 `recommended_next_commands`，把失败规则路由到补数据、补方法、结果降论断、正文修复、引用修复或人工确认，而不是只停留在普通审稿建议文本。
- 新增 `assess-review-rules`，可直接检查当前学科模块在 `method_plan`、`assess_result_validity`、`result_support_checkpoint`、`citation_audit` 等阶段会启用哪些 review rules。
- 新增 package/preflight/provenance 防护：贡献包只允许包含泛化模板、fixture、验证报告和 provenance/backflow 摘要；支撑层候选不能直接作为正式学科插件提交，必须提交其回流出的、已泛化并通过测试的正式三类候选。
- 泛化模板现在只保留来源标识和命中的信号元数据，不再把候选审阅用的源文本片段嵌回 Python 模板。review-rule 验证会检查正反 synthetic fixture 合同；正式 promote 还必须满足 runnable 或更高成熟度，并获得明确人工确认。
- 新增 `review-plugin-contribution` 维护者只读审阅助手，用于汇总贡献包 preflight 状态、metadata-only 来源策略、支撑层回流规则族、阈值与人工确认策略、需要审阅的文件，以及在 promote 前是否已准备好进入人工审阅。

### v0.18.1-v0.18.5 (2026-07-10) -- 结果支撑、主张合同与补救路线

- 新增 `research_plan/claim_contract.json`，在 research plan 阶段同步生成。它会记录 planned claim、active claim、主张强度、关联图表、证据角色和 claim boundary，避免后续写作在图表证据较弱时静默写出过强结论。
- 新增 `apply-result-downgrade`。当当前图表和指标本身可用、但不足以支撑原始强主张时，该命令会把现有结果冻结到 `results/result_evidence_freeze.json` 和版本化的 `results/evidence_snapshots/result_freeze_*.json`，只降低 active claim boundary，不重新跑数据、方法、图表或指标。
- 新增 `prepare-result-rescue`。当用户希望保留更强研究主张时，该路线会通过学科插件生成 connector-aware 的数据补充任务、方法补充任务和开源科研代码库检索任务，然后重新打开 data/method/figure/evidence/manuscript 链路，等待补充证据后重新生成和验证结果。
- 新增 decision-aware stale propagation。降维路线只 stale 正文和 claim boundary 的消费者，并保留当前结果证据；补充路线会 stale 数据、方法计划、图表合同、代码、方法验证、结果有效性、核心证据、结果和下游正文阶段。
- 升级 `status` 和 `run-pipeline`：当 result support 失败时，流程会明确停在人工决策点，并给出两条可执行路线 `apply-result-downgrade` 或 `prepare-result-rescue`，而不是继续进入正文写作或盲目 quality check。

- 新增 `assess-result-support`，放在 `assess-result-validity` 和 `assess-core-evidence` 之间。`assess-result-validity` 继续检查运行产物、指标和图表执行质量，而结果支撑检查点专门判断当前证据是否真的能支撑研究计划中的核心主张。
- 新增 `results/result_support_checkpoint.json/.md/.html`。当图表或指标只能部分支撑研究计划时，报告会停止正文写作，并给出两条人工路线：把研究主张降维到当前证据能够支撑的范围，或者继续补充数据和方法后重新生成核心图表。
- 更新阶段管线：`status` 和 `run-pipeline` 会在 result support 失败时停在路线选择点；如果已有失败的 result support checkpoint，`write-results` 也会拒绝继续写作，避免把较弱或矛盾的证据硬写成论文结论。

### v0.17.0-v0.17.7 (2026-07-08 至 2026-07-10) -- 证据语义论文保护层与更自由的正文写作

- 用领域无关的 Scientific Evidence Registry 替代宽松的事实账本写作路径。每条证据记录角色、cohort、样本单位、数据划分、运行、模型、来源与置信度；同一 cohort 内的矛盾事实会阻塞写作，而不是被写成幻觉。
- 新增 run-aware 结果证据解析。指标只从已验证的方法运行及具有明确锚点的关联表中选择，不再任意读取通用 `metrics.csv`；Results、Methods、有效性检查和图表 metadata 共用证据 ID 与来源。
- 新增 Semantic Figure Contract。主图必须声明科学问题、变量角色、禁止角色、方法输出、面板结构、图形语法、指标量纲和预期论断。identifier 对 identifier、混合量纲坐标、缺少方法输出或面板不完整的图表会在 core evidence 确认前被拒绝。
- 新增精确 change classification 与 stale 传播。citation 局部修改和纯展示修改不再使证据生成失效；数据、方法、结果、主图和研究设计修改会重新打开必要的科学链路。
- 新增人工确认后的证据快照与显式 reopen 机制。写作器、LaTeX 组装和最终 citation audit 都不能静默混用已变化的图、指标或正文与旧的证据确认。
- 使用章节证据包与写后合同，在不放松 Results 无引用、证据覆盖、公式解释、内部语言和结果泄漏限制的前提下保留 Codex 的自由写作能力。
- 新增 `submit-figure-semantic-annotations`，用于提交旧图表的显式、可审计语义映射；系统不会从旧 PNG 猜测科学含义。v0.18.0 的跨项目完整回归仍是后续独立验证步骤。

- 新增 `writing/scientific_fact_ledger.json`，作为所有正文写作阶段共享的科研事实账本，用于保存必须保留的样本规模、类别平衡、token 覆盖、stress-test 边界和结果指标等关键信息。
- 将科研事实账本接入 Data/Methods writing brief、Data/Methods 正文、Discussion 对比分析和最终 quality gate，避免在清洗路径、字段名和内部 artifact 表达时把关键科研事实一起删掉。
- 新增 `results/figure_interpretation_blueprint.json`，让 Results 写作围绕主图组、科学问题、主指标、claim boundary 和 appendix diagnostics 展开，而不是泛泛总结图表文件。
- 为 Introduction、Data 和 Discussion 的引用插入增加相关性过滤，避免同属一个大学科但与当前 idea/data/method 弱相关的文献被写进不合适的正文位置。
- 扩展 quality-check，新增 must-preserve scientific fact coverage 检查；并用当前天文学回归项目对比 `main.pdf`，确认 v0.17.0 保持 Results 无引用、无小标题，增强公式和图表引用覆盖，清除了路径/原始字段污染，并保留当前证据账本中的关键数据事实。

### v0.16.1-v0.16.9 (2026-07-07 至 2026-07-08) -- 正文写作、图表合同与回归加固

- 新增 `learn-writing-style-from-draft` 路径和 `writing_style.py` 风格画像，让已经人工认可的文稿提供非逐字复用的写作风格信号，同时不削弱证据门控。
- 使用本地 time-aware flaring-source 天文学项目完成完整回归：重新刷新 research plan、data、method、figure、methods verification、APJS/AAS PDF 编译、integrity gate 和最终 quality gate。
- 回归结果确认 6/6 个主图合同满足、13 张实际渲染科研图进入证据清单、4 张未渲染 supporting 图被排除在 result manifest 外、12/12 条 BibTeX 文献被正文覆盖，并且 Results 保持无引用、无小标题。

- 重写 Discussion 生成逻辑，禁止文件路径、图表路径、表格路径、manifest 名称和 Draftpaper-loop 实现语言进入论文正文。
- 增加 Discussion 比较文献准备和 citation evidence 覆盖，让讨论部分可以对比结果与已有研究，同时延续“引用核查只修 claim 和引用位置，不删除已确认参考文献”的原则。
- 新增 Discussion artifact sanitizer 和引用证据扩展的回归测试。

- 升级 Data 写作：保留样本角色、类别平衡、token 覆盖、模态可用性和 claim boundary 等科研细节，同时避免路径、文件名、脚本名和原始字段堆砌进入正文。
- 升级 Methods 写作：读取阶段代码 manifest、公式提取、公式变量解释和 figure-code trace，使方法部分围绕样本构建、特征/token 构建、模型逻辑、验证设计、指标和 ablation 证据展开。
- 增加 AASTeX 友好的 LaTeX 装配 fallback，包括作者信息占位、表格渲染和本地缺失 bibliography style 的回退，保证本地 review PDF 更稳定编译。

- 将 Results 生成改为围绕 `results/result_manifest.yaml`、figure metadata、metrics、caption、scientific question 和 claim boundary 展开，而不是泛化总结 artifact。
- Results 现在会按角色引用主图和附录诊断图，不生成文献引用，不生成小标题，并把 `row_count`、`source_id` 等内部标识转换为面向论文的科学表达。
- 保留 Results 幂等写作：当结果证据没有变化时，后续 Introduction/Data/Methods/Discussion 重跑不会再次改写已经确认的 Results。

- 升级 `inventory-results`，写出 v0.16.5 结构化 result manifest，包含 `main_figures`、`appendix_figures`、`supporting_links`、`claim_boundaries`、内部表格和 figure-code trace。
- 修复旧图污染问题：计划内但本轮没有渲染成功的 generated figures 会进入 `excluded_unrendered_figures`，不会因为磁盘上残留旧 PNG 就被写入 Results 或质量门。
- 新增回归测试，确保未渲染的 supporting/appendix 图保留在诊断和修复语境中，但不会进入正式科学结果清单。

- 扩展 Data Role aliases，覆盖 event-level samples、sample groups、current-observation tokens、historical sequence tokens、modality availability、feature matrices、天文学观测产品和模型评估字段。
- 强化 figure contract validation：5-6 个主图组与 supporting/appendix diagnostics 分开检查，计划中的主结果图不能被验证图或中间诊断图静默替代。
- 打通 method feasibility、figure execution diagnosis、result validity 和 core evidence 检查；缺数据或缺方法时先进入 repair 路线，再进入人工确认。

- 将图表硬性合同从“最多生成 5-6 张 PNG”调整为“默认 5-6 个主图组”。每个主图组可以由多个 panel 或多个生成图像构成，因此 `generated_figure_count > 6` 本身不再被视为失败。
- 在 `figure_plan.json` 和 `figure_contracts.json` 中增加主图组、支撑图和附录图统计。支撑性诊断图不会替代主结果图，但如果它们对故事完整性、可靠性验证或模型诊断有帮助，可以作为 Appendix Figure 被 Results 和 Discussion 引用。
- 升级 `assess-figure-contracts`：现在检查主图组数量是否满足学科最低要求，同时分别报告 generated、supporting 和 appendix 图表数量，允许多面板和附录诊断图存在。
- 将 figure-contract 失败接入 `repair-figure-data` 和 `repair-figure-method`，让缺失数据或缺失方法先生成可执行的数据获取、方法检索或方法补全任务，而不是直接进入人工确认或用降级图表替代。
- 强化天文学与机器学习项目的 Data/Methods 写作：新增角色化数字证据、规范天文观测产品术语、按项目方法类型生成 Methods 小节结构，并过滤“Describe/Define”这类 prompt 残留。
- 升级最终 `quality-check`：当 citation audit 的 reference coverage 失败时，最终质量门会失败，继续坚持“不删已确认参考文献，而是让正文覆盖、收窄和修复引用”的原则。
- 新增回归测试覆盖主图组统计、合同失败修复任务、Results 中的附录图引用、引用覆盖质量门，以及 astronomy Methods 正文清洗。

- 根据本地代码审计结果加固 `verify-methods`：方法验证命令会先解析为 argv 列表，再以 `shell=False` 执行；shell 操作符和显式 shell runner 会被拒绝，`methods/run_manifest.yaml` 会记录 `shell_used=false`。
- 新增 `verify_command_argv` 与 `{python}` 占位符，生成的 method-code manifest 不再固化开发机器上的 Python 绝对路径；旧版 `verify_command` 字符串仅作为兼容字段保留。
- 将完整 stdout/stderr 写入项目本地 `methods/run_logs/`，run manifest 只保存截断摘要、日志路径和长度信息，避免 manifest 过大。
- 收敛 analysis-code 输出契约：正式生成代码以 `methods/` 为 canonical location，`code/` 仅作为旧流程兼容副本。
- 去除测试中的重复 core-evidence helper，并新增回归测试覆盖 manifest argv 执行、shell 拒绝、run log manifest 和 canonical/compatibility 输出分离。

- 新增 Data/Methods writing brief 层。`build-data-context` 和 `build-method-context` 会在生成正文前写出 `data/data_writing_brief.json/.html` 与 `methods/method_writing_brief.json/.html`。
- 重构 Data 和 Methods 写作逻辑：正文由证据角色、方法阶段、公式、图表 trace 和 claim boundary 引导，而不是机械拼接 context 字段。
- 新增 research feasibility 与 research-plan feasibility gate，在后续数据、方法和图表代码生成前先判断研究设想是否具备必要的数据角色、方法意图和图表故事板证据。
- 新增 data role coverage、method feasibility、method repair 和 method degradation 报告，让缺失数据或缺失方法能力先被诊断，再进入图表和代码执行。
- `prepare-data-acquisition` 现在会读取 data role coverage 与 research-plan feasibility 中的数据缺口，把缺失数据角色转换成带 connector 建议的数据补充任务，而不是等到后续审稿 loop 才发现。
- 新增 figure contract gate。`generate-analysis-code` 在主图合同被阻断时会拒绝继续执行，避免用验证图、诊断图或降级占位图静默替代研究计划中的核心结果图。
- `revise-research-plan` 现在会在 `research_plan/` 下写出可人工阅读的修订建议包，明确先补数据、补方法，再考虑收窄研究问题和重新生成研究计划。
- `assess-result-validity` 现在会读取 figure contracts、figure contract gate 与 figure execution diagnosis；即使表格指标通过，只要计划主图被阻断或缺失，也会回到数据/方法/图表修复路线。
- `status` 与 `run-pipeline` 已接入 repair-first 路线：优先补数据、补方法或修订 research plan，再考虑收窄科学问题。
- 同步更新内置 Draftpaper workflow skill 与命令参考，使其遵循新的 preflight、research-plan feasibility、method feasibility 和 figure-contract 阶段顺序。
- 修复 data role 归一化：`ra` 这类短别名不再误伤 spectral 或 remote-sensing features 等较长角色名称。
- 收紧 composite discipline method blueprint：完整插件目录仍然保留，但当前论文的 method data contract 会优先基于 research plan、figure storyboard、method requirements 和 review tasks 选中的模板生成。
- 升级 integrity gate：新增 writing brief 覆盖检查、Methods 公式渲染检查和公式变量解释检查，同时保留 Codex 写出自然科研段落的空间。
- 本地验证：`python -m pytest tests/test_cli_feasibility_commands.py tests/test_research_feasibility.py tests/test_research_plan_feasibility_gate.py tests/test_method_feasibility.py tests/test_figure_contract_gate.py tests/test_orchestrator_research_feasibility_routing.py`
- 本地验证：`python -m pytest tests/test_data_feasibility.py tests/test_methods.py tests/test_integrity_gate.py tests/test_composite_discipline_modules.py tests/test_method_blueprint.py`
- 全量验证：`python -m pytest`，241 tests passed。

### v0.15.1-v0.15.12 (2026-07-01 至 2026-07-06) -- 证据优先 loop、引用核查与 CLI 加固

- 加强 Data/Methods 正文生成逻辑：本地路径、文件名、workflow 产物、仅用于实现的脚本名称和内部 manifest 语言，会在进入论文正文前被清理成面向论文的科学表述。
- 增加天文观测数据产品的正文表达转换：光谱、响应矩阵、光变曲线、事件、图像和曝光等数据产品会被写成可读的数据描述，避免把 PHA、ARF、RMF、LC 等字段名生硬写进论文。
- 扩展方法公式提取：面向 time-aware classification 工作流补充 Time2Vec 式时间编码、序列位置编码、masked pooling、多模态分类 logits、交叉熵、macro-F1、ROC-AUC、混淆矩阵、ablation delta、相关性和拟合优度等公式，并为公式变量补充解释和对应图表关联。
- 升级 integrity gate：新增正文语言 lint 和 Data/Results 样本数量一致性检查，会读取 `results/tables/sample_composition.csv`，防止 Data 与 Results 中事件数、样本数或源数量不一致时静默通过。
- 重新定位 citation audit：它现在是正文完成后的引用论断收紧 loop，不作为参考文献质量过滤器。已确认文献会被保留，弱支撑或位置不合适的引用会通过收窄 claim、移动引用位置或补充证据 metadata 来修复；repair 阶段不再删除已确认参考文献，也不删除带引用的正文句子。
- 本地验证：`python -m pytest`
- 当前测试规模：228 tests

- 修复 `write-results`：当 `results/result_manifest.yaml` 和生成正文没有变化时，重复调用不会再重写 `results/results.tex` 或 `results/results_summary_zh.md`。
- 避免核心图表与 Results 已经确认后，后续 Introduction、Data、Methods、Discussion、LaTeX 和 quality 阶段因为一次无变化的 `write-results` 被重新标记为 stale。
- 新增回归测试，覆盖“先确认 Results，再继续写 Introduction/Data/Methods/Discussion”的 evidence-first 写作顺序。
- 本地验证：`python -m pytest`
- 当前测试规模：224 tests

- 新增 `classify-code-ownership`、`route-stage-code`、`build-code-provenance`、`extract-method-formulas` 和 `trace-figures-to-code`，用于把项目专属或历史遗留的 `code/` 脚本归属到 `data/scripts/`、`methods/scripts/`、`methods/src/` 和 `methods/plotting/`。
- 新增 `data/data_code_manifest.json`，扩展 `methods/method_code_manifest.json`，并新增 `methods/method_formula_manifest.json`、`methods/method_formulas.tex` 和 `results/figure_code_trace.json`，用于记录数据代码、方法代码、公式来源和图表代码溯源。
- 升级 `build-data-context` 和 `build-method-context`，让 Data 和 Methods 写作读取阶段归属代码 manifest、公式提取结果和 figure-code trace，而不是把 `code/` 当成混杂脚本目录。
- 新增 `prepare-discussion-comparison`，在 `write-discussion` 前生成比较文献矩阵、HTML 证据笔记和创新/不足写作提示。
- 在 astronomy、geography 和 machine_learning 学科模块中补充阶段归属代码布局、公式提取和图表代码追踪约束。
- 已用本地 astronomy 项目验证迁移链路：旧 `code/` 脚本完成分类、路由、公式扫描和结果图表追踪；在 artifact drift 同步后，Methods context 因上游 method-plan stale 被正确拦截，没有绕过状态机。

- GitHub Actions 改为安装 `.[dev]` 并运行 `python -m pytest`，与本地开发验证路径保持一致。
- 修复内置学科模板中的 `csv.DictReader(path.open(...))` 直接打开文件模式，统一改为 context manager，避免 ResourceWarning。
- 本地验证：`python -m pytest`
- 当前测试规模：219 tests。

- 新增 `draftpaper_cli/template_registry.py` 和 `draftpaper validate-template-registry`，用于检查内置学科插件 manifest、template 文件、fixture、插件 ID 和成熟度元数据。
- 新增测试，方便后续外部贡献的学科插件在合并前先完成结构检查。

- 新增 `io_utils`、`latex_utils` 和 `citation_utils`，减少 JSON/text 读取、LaTeX 转义、BibTeX 解析和 citation key 解析的重复实现。
- 将 Methods、Results、Introduction、Discussion、LaTeX assembly 和 quality gate 等高风险模块迁移到共享 helper。
- 保留 `\cite{}`、`\citep{}` 等常见 LaTeX 引用命令兼容。

- 新增公共工具层测试，并让 gate 行为围绕统一解析 helper 对齐。
- 继续保持 `methods/` 作为生成分析代码的 canonical location，`code/` 仅作为兼容输出保留。

- `verify-methods` 在未传入 `--command` 时会读取 `methods/method_code_manifest.json`，使用生成的验证 metadata、declared outputs 和 selected input data 完成验证。
- 方法验证现在检查 `results/figure_contracts.json`；缺失、占位或 metadata 不匹配的主结果图会导致 hard gate 失败。
- `generate-analysis-code` 会把 manifest-driven 的验证和绘图安装 metadata 写入 manifest，并推荐更短的 manifest-driven verification command。

- 将 paper-fetch runtime 打包到 `draftpaper_cli/_vendor/paper_fetch_skill`，使 wheel 安装也能保留 fallback source，而不是只依赖源码目录中的 `third_party/` 路径。
- 新增 `fulltext` optional extra，用于安装更重的文章/PDF 全文解析依赖，同时保持默认安装相对轻量。
- 已用 `python -m pip wheel . --no-deps` 验证 wheel 中包含 vendored paper-fetch CLI 和第三方 license。

- 修复 `verify-methods` 的 CLI 退出码语义：当方法验证写入 `status=failed` 时，命令会返回非零退出码，同时继续输出 run manifest JSON，避免 shell、Codex 自动化或 CI 把失败的方法验证误判为成功。
- 移除新建项目 `project.json` 中的开发者本机历史路径，改为中性的 `legacy_mvp_reference` 说明字段，提升项目在不同电脑、公开示例和 fork 环境中的可迁移性。
- 新增回归测试，覆盖失败的 `verify-methods` 退出码和新项目元数据不包含本机私有路径。
- 刷新 README 中的论文生成流程说明，强调当前主流程是 evidence-first：文献和 research plan 之后先完成数据/方法执行、主图生成、result validity 和 core evidence 审阅，再进入 Results、Introduction、Data、Methods 和 Discussion 写作。

- 升级 `plan-figures`：research plan 中的 figure storyboard 会被视为严格的主结果图合同，并写入 `results/figure_contracts.json` 与 `results/storyboard_alignment_report.json`。
- 升级 `generate-analysis-code`：生成流程会输出 `results/figure_execution_diagnosis.json` 和 `.html`；当主图缺少数据或缺少方法代码时，系统会明确诊断原因，而不是静默生成验证图、流程图或辅助图来替代主图。
- 新增 `diagnose-figure-execution`、`repair-figure-data` 和 `repair-figure-method`。这些命令会根据现有数据连接器、公开数据库/API、远端服务器流程、学科插件、公开科研代码仓库、文献实现仓库或 Codex 生成的项目专属方法代码，形成数据或方法修复计划。
- 升级 `assess-core-evidence`、`status`、`run-pipeline` 和最终 quality path：如果研究计划中的主图合同未满足，流程会优先推荐数据/方法修复；只有自动修复仍无法产出核心图表时，才进入人工 core evidence 确认。

- 调整主论文流程：文献调研和 research plan 之后，先完成数据补充与整合、方法代码运行、核心图表生成、result validity 和 core evidence gate，再进入正文写作。
- 新增 `assess-core-evidence`，输出 `core_evidence/core_evidence_report.json` 和 `.html`，用于检查数据补充、数据整合、方法分析、图表生成、figure metadata 和结果有效性，并保留人工确认核心图表的检查点。
- 将执行阶段和正文写作阶段拆开：`data` 和 `methods` 负责证明数据与方法可用，`data_writing` 和 `methods_writing` 在 Results 证据明确之后再生成 `data.tex` 和 `methods.tex`。
- Results 写作改为连续自然段，不再默认按每张图拆小节，并新增 `results/results_summary_zh.md`，用于中文概括结果部分和图表解释，方便人工审图。
- 同步更新 orchestrator、LaTeX assembly、quality gate、review routing 和 Codex skill wrapper，使其遵循 evidence-first loop。

### v0.14.0-v0.14.13 (2026-06-24 至 2026-07-01) -- 学科插件、引用修复、IP 保护与数据连接器

- 新增 astronomy 学科模块的 `remote_fits_zip_stream` 数据连接器，用于大型 FITS/ZIP 观测产品保留在远端服务器或仪器归档中的场景；Draftpaper-loop 本地只保留 compact manifest、processed tables、parse-status reports 和 provenance records。
- 新增公开通用模板，支持 event-product manifest 构建、ZIP 成员可用性检查、密集观测窗口选择和 streaming data contract 输出；模板不写死私有服务器地址、用户名、密码、真实源 ID 或项目专属类别标签。
- 将训练冒烟验证拆到方法模板层：astronomy 模块新增 `source_holdout_stream_smoke_test`，machine learning 模块新增 `group_holdout_training_smoke_test`，从而让 event-random 指标只作为泄漏风险对照，source/group-held-out 指标在可行时作为主要验证路径。
- 升级 `prepare-data-acquisition`，可以识别 `fits_zip_stream` 数据访问模式，并将 astronomy 缺失数据任务路由到更合适的远端流式数据连接器。

- 每篇文献 summary HTML 中的 DOI 和 URL 现在会渲染为可点击链接，方便人工复查文献来源。
- 调整文献检索 query plan：先从 idea/title 中抽取方法、仪器、数据和任务相关的短关键词，再与 data/method query 组合检索。
- 避免把完整研究题目或整句 idea 反复塞进每一条检索 query，同时保留 high-energy time-domain astronomy、X-ray transient classification 等学科锚点。
- 已用 astronomy 项目重新运行 `search-literature -> generate-plan` 验证：新的 query plan 不再重复完整 idea，同时保留 12 篇参考文献、6 张计划主图和 1 个核心表格。

- 调整 `generate-plan`：面向用户阅读的 research plan 只生成 `research_plan/research_plan.md` 和 `research_plan/research_plan.zh-CN.md`，不再额外生成 `research_plan.html` 和单独的 `research_questions.*` 文件。
- 将研究问题、figure storyboard、method-plan contract、预期表格、风险检查和文献综述索引链接直接合并进 research plan Markdown，减少用户需要打开的分散文件。
- 升级中文 research plan 渲染器：中文版不再只是翻译标题，而是基于同一份 blueprint 生成更自然的中文研究方案说明。
- 升级文献检索 query plan：每条检索记录都会带有 context、query ID、组合层级、学科锚点和 query components，用于区分 introduction/data/method/target-journal 检索来源。
- 为天文学等项目增加低数量自动补检，并把 query provenance 写入 `references/search_queries.json`、`references/literature_items.json` 和每篇文献的 HTML summary。
- 已用本地 astronomy 项目重新运行 `search-literature -> generate-plan` 验证：当前项目保留 12 篇参考文献、30 条 citation-evidence rows、6 张计划主图和 1 个核心表格。

- 为 claim-level 引用核查记录补充 citation intent、support status、topic relevance score、claim-alignment score、blocking status 和 repair hints。
- 升级 citation repair plan：对于语义相关、方法/工具背景相关、部分支持或不贴切的引用，保留已确认参考文献，并优先收窄和改写正文 claim，使其符合文献证据；引用核查阶段不再规划删除参考文献或删除带引用的正文句子。
- 新增 `references/reference_usage_plan.json`，把 retained literature summaries 分配到对应正文章节，并要求每篇保留文献都必须在 Results 之外至少引用一次。
- 新增 `citation_audit/reference_coverage_report.json` 和 `citation_audit/reference_coverage_report.html`，用于对比 `references/literature_summaries/` 中保留的文献和正文中实际去重引用的文献；summary 中存在但正文未引用的文献现在会导致 citation audit 阻塞失败，不再允许最终参考文献数量被静默缩小。
- 新增回归测试，覆盖方法/工具/背景类引用保留、上下文相关引用改写，以及 reference coverage gap 与 unsupported citation 的分离报告。

- 新增公开合规文档，明确非商业 source-available 边界、商业授权要求、赞助不等于授权规则，以及禁止使用隐藏 payload、遥测、设备指纹、远程许可证检查或破坏性检查等反滥用机制。
- 新增公开 DPL schema family 文档，并在项目 metadata、stage manifest 和 project passport 中写入可审计的项目 provenance 信息。
- 新增稳定的公开 contract helper，用于生成 claim ID 和 evidence ID，并补充测试验证 DPL 标识符和项目生成 metadata 的确定性。
- 新增公开 forensic fingerprinting 高层说明。
- 更新商业许可和商标说明，明确 Draftpaper-loop、DPL loop engine、project passport、claim trace 和 evidence binding 等项目术语不得被用于暗示商业授权或官方背书。

- 新增独立的引用核查与修复 loop：`audit-citations`、`generate-citation-repair-plan`、`apply-citation-repair`、`re-audit-citations` 和 `run-citation-repair-loop`。
- 新增 claim-level 本地引用支持度核查：将论文正文中的引用论断与 BibTeX 和 `references/citation_evidence.csv` 对比，并在 `citation_audit/iterations/` 保存中间 HTML 审查报告，通过后生成 `citation_audit/final_citation_audit_report.html`。
- 升级 `status` 和 `run-pipeline`：integrity gate 通过后不会直接进入 `quality-check`，而是先要求最终引用核查通过；如果审查失败，会推荐进入 citation repair loop。
- 升级 `quality-check`：直接调用时也要求 `citation_audit/final_citation_audit_report.json` 的 `status=passed`，防止跳过参考文献来源与论断一致性核查。

- 新增学科模块成熟度字段，以 `foundation`、`runnable` 和 `mature` 作为后续演进层级。
- 新增 `capture-discipline-learning`，可以从 observations、methods、review、data context、result metadata 和 rescue plan 等项目归档中总结可复用经验，写入 `plugin_candidates/from_loop/...`，不会复制原始数据或隐藏推理。
- 新增 `classify-plugin-reusability`，用于在晋升前区分通用方法/审稿/数据能力和项目专属标识、本地路径、凭证、固定区域等不可泛化内容。
- 将 finance、medicine、biology 和 engineering 从 foundation-only spec 升级为 runnable foundation module，每个学科先补充一条标准库兼容、fixture-backed 的可运行方法模板。
- 新增 finance、medicine、biology 和 engineering 的 foundation reviewer engines，使这些学科不再直接回退到 default 审稿路线。

- 新增 `inspect-research-repo`，只读取候选仓库 checkout 的结构、docs 和 package metadata，并输出 `repository_structure.json`、`file_inventory.csv`、`package_manifest.json` 和 HTML 检查报告，不复制源码。
- 新增 `map-repository-workflow`，把仓库文件角色映射为 data connector、preprocessing、method、figure、validation、review、environment 和 documentation 等候选能力。
- 新增 `bootstrap-discipline-foundation`，根据 workflow map 生成候选级学科基座建议；默认只写 candidate，不直接修改正式学科模块。
- 新增 finance、medicine、biology 和 engineering 四个基础学科模块，每个模块都先内置数据 connector spec、方法 template spec 和 reviewer-rule groups。

- 新增最小版公开科研代码挖掘链路：`discover-research-repos`、`score-research-repos` 和 `extract-plugin-candidates`。
- 新流程会在 `research_code_mining/` 下生成元数据级 JSON/HTML 报告，并根据许可证安全性、可复现性元数据、论文关联信号、工作流完整性和可复用能力提示对仓库排序。
- 候选抽取会生成 `candidate_manifest.json`、`candidate_report.html` 和候选索引报告，同时明确避免 clone 仓库、复制第三方源码或直接安装插件。
- 这为后续学科模块扩展提供了更安全的入口：公开代码只能启发通用 data/method/figure/review 模板，真正合并前仍需经过许可证、隐私、overlap、fixture 和维护者审阅。

- 保留当前 source-available non-commercial 自定义许可，没有切换为 Apache-2.0 或其它标准 SPDX 许可证，因为商业授权边界需要非标准条款才能表达清楚。
- 清理公开更新日志中的具体项目来源表述，后续公开 README 默认用可复用能力描述插件 seed，而不是暴露内部项目名、私有验证目标或具体研究方向。
- 明确后续公开 changelog 应避免写入本地验证文件夹、私有数据集、项目级样本选择、真实项目名称或过细的研究场景来源。

- 新增 runtime composite discipline modules，用于交叉学科论文；loop 现在会记录 `primary_discipline`、`secondary_disciplines`、`discipline_scores` 和有序 `discipline_modules`。
- `get_discipline_module` 现在可以合并 `default`、主学科和辅学科，并按稳定 id 去重 data connectors、method templates 和 review rules。
- geography + machine learning、astronomy + machine learning 等交叉项目可以在 `prepare-method-blueprint`、`prepare-data-acquisition` 和 `plan-figures` 中同时暴露领域插件与 ML 建模/审稿插件。
- 插件候选 manifest 现在会记录主学科和辅学科，但稳定可复用能力仍然归入其对应 home module，避免按论文方向拆永久分支。

- 新增 geography 数据 connector：Earth Engine 降水导出规划、NetCDF-to-GeoTIFF 转换规划、栅格文本转 raster、ArcGIS/project-bound 分区统计 manifest。
- 新增 geography 方法模板：月尺度遥感指数汇总、物候曲线平滑、NDVI 时序 K-means 分区、聚类统计诊断。
- 新增 machine-learning 数据/模型 seed：表格环境数据 profile、脱敏 saved-model manifest、RF/XGBoost/GBDT/Stacking 回归计划、observed-predicted 诊断、feature importance、PDP/ICE、SHAP plan，以及模型统计有效性 reviewer gate。
- 这些 seed 均保持 fixture-backed 与 dependency-light：可复用插件代码保持通用，项目路径、API 账号、数据窗口和模型二进制文件只留在本地项目绑定中。

- 新增 astronomy connector 和 method seed，覆盖 photon/event 数据访问规划、观测产品 manifest、长时标光变特征提取和事件级序列输入构建。
- 新增 machine-learning/deep-learning connector 和 method seed，覆盖视觉目录对齐、预训练 backbone 元数据、自监督训练规划、checkpoint 兼容性诊断、embedding 健康检查、少标签评估和相似性检索。
- 为这些学科插件补充 fixture-backed tests，使其不依赖私有数据、API 凭证、大模型 checkpoint 或 GPU 训练即可完成基础验证。
- 通用插件模板不保存项目私有路径、账号凭证、checkpoint 二进制文件或固定样本选择；真实项目中的具体路径和参数由 Draftpaper-loop 项目本地绑定。

- 新增完整的 `DataConnectorSpec` 和 `MethodTemplateSpec` schema。
- 将学科模块推进为三层结构：`data_connectors/`、`method_templates/` 和 `review_rules/`。
- 新增 geography 方法模板：`remote_sensing_feature_reconstruction` 和 `spatial_block_validation`。
- 新增 machine_learning 方法模板：`baseline_model`、`ablation_study` 和 `train_validation_test_split_check`。
- 新增插件贡献 preflight 命令：`summarize-plugin-candidates`、`generalize-plugin-candidate`、`validate-plugin-candidate`、`package-plugin-contribution` 和 `write-github-contribution-guide`。
- 明确 fork/PR 规则：fork 和 branch 只是临时贡献通道；稳定通用能力必须在隐私、通用性、overlap、fixture 和 validation 检查后合并进 `main` 对应学科模块。

### v0.13.0-v0.13.1 (2026-06-24) -- 阶段归属方法代码与学科图表策略

- 升级 `plan-figures`：学科模块可以声明 `minimum_main_figures`、`target_main_figures` 和 `required_figure_groups`，在数据可用时默认初稿会尽量规划至少 5 张 generated 主图。
- 扩展学科模块的数据获取 connector catalog，记录 package、import module、API/下载路径、凭证要求、可获取数据格式和本地 feasibility 状态。
- 新增 `ecology` 和 `bioinformatics` 学科模块骨架，并与 `default`、`geography`、`astronomy`、`machine_learning` 一起接入 registry。
- 补充 geography/agriculture、astronomy、ecology/environment、machine_learning 和 bioinformatics 的数据获取路线，用于 research plan 阶段的数据补充建议和 reviewer/rescue 缺失数据回退。

- 新增阶段归属代码结构：数据获取和预处理代码进入 `data/scripts`，模型、统计、空间分析、验证和科研绘图代码进入 `methods/scripts` 与 `methods/src`，`results` 只保存图表、表格和 metadata。
- 新增 `prepare-method-blueprint`，输出 `methods/method_blueprint.json`、`methods/method_data_contract.json`、`methods/method_code_plan.json` 和 `methods/method_formula_plan.json`。
- 新增 `discipline_modules` 框架，并预留 default、geography、astronomy 和 machine_learning 四类模块骨架，用于共享数据角色、方法族、图表族、公式族和审稿约束。
- 升级 `generate-analysis-code`：主生成代码默认保存到 `methods/`，`code/` 仅作为旧流程兼容入口。
- 新增 `docs/discipline_modules/`，用于说明后续不同学科模块如何由 Codex 总结、测试并接入。

### v0.12.0-v0.12.1 (2026-06-23 至 2026-06-24) -- 可插拔数据获取与审稿救援任务

- 将 reviewer/rescue 中的缺失数据建议接入 `prepare-data-acquisition`。
- `prepare-data-acquisition` 现在会读取 `review/actionable_analysis_tasks.json`、`review/review_engineering_plan.json`、`review/statistical_rescue_plan.json`、`review/revision_plan.json` 和 `review/gate_failure_diagnosis.json`。
- 新增 `data/data_acquisition_tasks.json` 和 `data/data_acquisition_tasks.html`，把 blocked analysis task 转换成明确的缺失数据请求，记录 `needed_data`、`optional_data`、`suggested_connectors` 和需要用户确认的问题。
- 升级 `status` 和 `run-pipeline`，让 review/rescue 执行链在 `prepare-analysis-revision` 之后、`plan-figures --use-review-tasks` 之前自动推荐 `prepare-data-acquisition`。

- 新增共享学科推断层，供数据获取规划和审稿工程共同使用，避免 Data 插件和 review/rescue 插件各自重复判断学科。
- 新增 `classify-data-access`、`prepare-data-acquisition` 和 `inventory-data-sources`，用于在正式数据清点前生成 plan-first 的数据获取规划。
- 新增通用 connector profile：`local_files`、`api_access` 和 `remote_server`。这些 connector 只识别数据获取模式，不下载外部数据，不写入凭证，也不把天文学、地理学等领域专用包硬编码进核心 Data 阶段。
- 新增数据获取产物：`data/data_access_profile.json`、`data/data_acquisition_plan.json`、`data/data_acquisition_plan.html`、`data/data_source_manifest.csv`、`data/data_access_log.csv`、`data/data_provenance.json` 和 `data/data_completeness_report.html`。
- 新增设计文档和实施计划，保存在 `docs/superpowers/specs/` 和 `docs/superpowers/plans/`。
- 已用本地 cross-discipline 源目录验证通用层，同时检测到 local files、API access 和 remote server 三类数据获取模式；公开文档不记录私有路径或具体项目标识。

### v0.11.0-v0.11.1 (2026-06-21 至 2026-06-23) -- 发表就绪度、统计救援与源码可见保护

- 新增仓库级保护文件：`NOTICE`、`COMMERCIAL_LICENSE.md` 和 `TRADEMARK.md`。
- 将 `LICENSE` 中较早的 DraftPaper CLI 表述更新为 Draftpaper-loop，并补充 API 服务、论文生产服务、付费课程捆绑等商业使用示例。
- 为一方 Python 文件补充版权声明和联系邮箱，同时保持 `third_party/` 等第三方文件不变。
- 在生成的 LaTeX、HTML 报告、生成式 Python 脚本，以及包含 `generated_at` 的 JSON 报告中加入稳定的 Draftpaper-loop generator provenance。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：130 tests

- 新增 `discover-review-workflow-gaps` 和 `propose-review-engineering-plan`，用于学科分支审稿工程。第一版确定性 engine 是 geography，覆盖遥感、农业地理、空间尺度匹配、遥感质量控制、空间自相关、分层异质性和弱拟合回退；同时预留并实装 astronomy 与 machine_learning 的基础审稿规则，分别覆盖天文目录交叉匹配、光变曲线采样、源分类验证，以及机器学习数据泄漏、baseline/ablation、验证拆分、校准和类别不平衡；无法识别学科时使用 default fallback。
- 新增审稿工程输出：`review/review_discipline_profile.json`、`review/review_workflow_gap_report.json`、`review/review_workflow_gap_report.html`、`review/review_engineering_plan.json`、`review/review_engineering_plan.html` 和 `review/user_confirmation_requests.json`。`codex_enhancement_context` 作为 C 层接口，供 Codex 基于文献、学科和已写稿件补充差异化审稿建议。
- 新增 `prepare-analysis-revision`，把 reviewer/rescue 建议转换成统一的可执行分析任务，先检查目标变量、预测变量、时间、空间分组/坐标、质量标记等数据角色是否完备，再输出 `review/actionable_analysis_tasks.json`、`review/analysis_revision_feasibility.json`、`review/analysis_revision_feasibility.html`、`methods/analysis_revision_requirements.json` 和 `results/revision_figure_plan_delta.json`。
- 接入 `plan-figures --use-review-tasks` 和 `generate-analysis-code --use-review-tasks`，让 executable/partial 审稿任务自动进入修订图表计划、review task coverage 表和 review task metrics 表；blocked 任务继续作为缺失数据提示，不生成假代码。
- 新增 `assess-publication-readiness`，根据 data feasibility、method verification、result validity、figure metadata、integrity、quality 和 journal profile 等本地归档产物评估目标期刊投稿就绪度。
- 新增 `recommend-statistical-revision`，当数据质量较弱或结果不足以支撑结论时，生成统计增强修订方案，包括稳健统计、缺失值分析、方法重构、显式成功阈值、领域化特征重构、空间验证、模型验证检查和 claim reframing。
- 新增审稿输出：`review/publication_readiness_report.json`、`review/publication_readiness_report.html`、`review/codex_archive_review_context.json`、`review/codex_archive_review_context.html`、`review/statistical_rescue_plan.json`、`review/statistical_rescue_plan.html`、`review/journal_fit_report.html` 和 `review/claim_evidence_matrix.csv`。
- 新增项目归档审稿上下文层，让 publication readiness report 可以基于 research plan、文献、数据、方法、结果、图表、期刊、integrity 和 quality 等本地归档产物生成更接近真实审稿意见的自然语言评审。
- 新增学科化统计增强路线，当项目归档中出现农业遥感、空间/生态、天文时间序列或机器学习验证信号时，自动给出更贴近对应学科的特征工程、分层验证、外部验证和重绘建议。
- 新增统计指标语义识别：p-value 按 alpha 阈值如 0.05 判断显著性，R2 按拟合优度/解释度判断，相关系数按效应量判断；当方法和图表实际产生这些统计输出时，低 R2 或弱相关会触发数据质量、代理变量、异常值、空间对齐和方法重构建议，而不会再把 R2=0.05 误当成显著性阈值。
- 升级 `status`、`run-pipeline`、`generate-revision-plan` 和 `re-review`，让 quality/integrity 失败后依次进入 gate diagnosis、reviewer pass、publication readiness、statistical rescue 和统一 stale-stage 回退路径。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：127 tests

### v0.10.0 (2026-06-18) -- 论文质量门控与清洁结果/致谢写作

- 新增论文写作质量门：检查章节最低篇幅、实质性自然段数量、禁止列表式正文、避免随意加粗、Introduction/Discussion 引用存在性、Methods 公式存在性，以及 Results 主图数量要求。
- 升级 `write-results`，结果段落会用 LaTeX 标签引用对应图表，例如 `Figure~\ref{...}` 和 `Table~\ref{...}`。
- 清理 Results 和 Discussion 的论文正文表达，避免把内部 loop 术语、gate 名称、本地文件保护规则、manifest 引用和 Draftpaper-loop 实现说明写进科学正文。
- LaTeX 组装默认加入致谢，说明本研究使用 Draftpaper-loop 辅助完成分阶段文献组织、分析可追溯性、图表清单和论文初稿生成，并附项目链接 `https://github.com/xiejhhhhhh/Draftpaper_loop`。
- 强化 Methods 输出，新增公式清单和 `methods/method_formulas.tex`，并接入 quality gate，防止 Methods 初稿缺少数学表达。
- 强化科研图验证，生成图必须提供 PNG/出版级 metadata、坐标轴标签、文字元素、统计量、解释摘要和 publication-ready 后端证据。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：111 tests

### v0.9.0 (2026-06-16) -- 科研绘图循环与绘图依赖

- 新增绘图依赖分层：真实科研项目推荐使用 `.[plotting]`，高级图像和报告场景可使用 `.[plotting-full]`。
- 新增项目本地科研绘图 runtime，`generate-analysis-code` 会把 `scientific_plotting.py` 写入单篇论文项目的 `code/src/`，方便迁移和复现。
- 升级 `plan-figures`，图像规划不再只是图名和类型，而是包含 `figure_type`、变量、统计变换、后端偏好和 `no_flowchart_fallback` 的 FigureSpec。
- 升级 `generate-analysis-code`，生成的分析流程会输出真实科研 SVG 图、`results/figure_metadata.json` 和 `results/figure_quality_report.json`。
- 新增 numpy/stdlib 兼容的科研 SVG 图：散点回归图、直方分布图、类别支持图、相关热图和指标汇总图。
- 升级 `inventory-results` 和 `write-results`，结果段落优先使用图像 metadata 中的样本量、相关方向、R/R2、类别支持和指标摘要，而不是泛泛复述 artifact。
- 升级 quality gate，生成式经验结果图必须具备科学 metadata、坐标/尺度证据和解释摘要，workflow 图不能再静默替代 Results 里的科研图。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：103 tests

### v0.8.0 (2026-06-15) -- 观察记录驱动的数据与方法循环

- 新增 `record-observation`，用于保存 Codex/用户已公开确认的分析摘要，不保存隐藏推理链。
- 新增 `build-data-context` 和 `write-data`，让 Data 部分从数据来源、内容、处理和 claim boundary context 写作，而不是从文件路径写作。
- 新增 `build-method-context`，并升级 `write-methods`，让 Methods 从方法意图、数据角色、验证摘要和 claim boundary 写作，而不是直接写命令或 manifest。
- 升级 `run-pipeline`，Data 和 Methods 这类多子步骤 stage 只有在 context 和 manuscript 输出都存在后才会被视为完成。
- 升级 quality gate，如果 Data/Methods 正文包含本地文件名、路径、执行命令或 manifest 式输出文本，会直接失败。

### v0.7.0-v0.7.1 (2026-06-15) -- Zotero 文献导入与文献证据保留

- 将 Zotero 导入文献作为用户精选证据完整保留，不再受外部检索 ranking、近年文献偏好、abstract/PDF 过滤和默认 30 篇外部文献上限约束。
- 在 literature review notes、每篇文献 HTML summary 和 `references/literature_summaries/index.html` 中加入 Zotero source、origin、collection 和 selection policy 信息。
- 增加测试，确认 Zotero 文献会与检索文献一起出现在 HTML index 中，同时保持来源可区分。

- 新增 `list-zotero-collections`，方便 Codex 或本地 CLI 查看 Zotero collection 名称。
- 新增 `search-literature --zotero-collection`，允许单篇论文项目从用户指定的 Zotero collection 导入参考文献。
- 新增 `--zotero-context`、`--zotero-min-items` 和 `--no-zotero-supplement`，用于控制 citation evidence 章节归属和 Zotero-first 外部补充逻辑。
- 新增 `references/zotero_collection_manifest.json`，记录请求的 collection、实际匹配的 collection、collection key、可用条目数量和补充文献数量。
- 在 README 中补充 Codex 如何调用 Zotero collection 的方法，并说明 `ZOTERO_LIBRARY_ID`、`ZOTERO_LIBRARY_TYPE` 和 `ZOTERO_API_KEY` 只通过环境变量读取，不会在输出中暴露。

### v0.6.0 (2026-06-11) -- 更名并重构为 Draftpaper-loop

- 将项目从 CLI-first 论文生成工具重新定位为 loop-engineered 科研论文系统。
- README 名称从 DraftPaper CLI 改为 Draftpaper-loop，同时保留 `draftpaper` 作为稳定 CLI 接口。
- 增加 observe、decide、run、verify、persist state、mark stale、diagnose failure、rerun 的 loop 模型。
- 新增 `plan-figures`，在生成分析代码前先规划项目专属科研图表。
- `generate-analysis-code` 改为读取 `results/figure_plan.json`，不再生成固定 workflow 图。
- 增加远程/服务器/API 数据和用户提供 processed/result artifacts 的支持，并对 claim strength 做 conditional pass 限制。
- report 类产物曾补充 HTML 输出，例如 novelty report、figure plan 和 literature review notes；后续版本已将 research plan 调整回 Markdown-first，方便直接审阅和修改。
- 联系方式、商业使用条款和个人主页移动到 README 末尾。

### v0.5.0 (2026-06-09) -- 审稿路由与门控失败诊断

- 新增 `diagnose-gate-failures`、`review-draft`、`generate-revision-plan`、`apply-revision` 和 `re-review`。
- 新增统一 revision issue schema。
- 新增 `review/commitment_ledger.csv`，用于追踪多轮修订中的用户决策。
- `status` 和 `run-pipeline` 在 integrity/quality 失败后推荐 `diagnose-gate-failures`。
- 本地验证：`python -m unittest discover -s tests`。
- 当前测试规模：95 tests。

### v0.4.0 (2026-06-09) -- 完整性门控与 artifact 可追溯性

- 新增 `run-integrity-gate`。
- 新增 `integrity/integrity_report.json` 和 `integrity/integrity_report.md`。
- 检查 BibTeX 引用存在性、`citation_evidence.csv` 可追溯性、Results 禁引用规则和 result claim artifact binding。

### v0.3.0 (2026-06-09) -- 项目护照、陈旧状态同步与分阶段编排

- 新增 DraftPaper Passport：`project_passport.yaml`、`artifact_ledger.jsonl`、`checkpoint_ledger.jsonl` 和 `integrity_ledger.jsonl`。
- 新增 `status`、`checkpoint`、`resume` 和 `run-pipeline`。
- 新增 `detect-artifact-drift` 和 `sync-artifact-stale`。
- 增加早期本地方法/结果 artifact 检查能力。

### v0.2.0 (2026-06-09) -- 方法、结果、讨论与 LaTeX 硬门控

- 新增 `collect-method-plan`。
- 新增 `generate-analysis-code`、`verify-methods` 和 `methods/run_manifest.yaml`。
- 新增 `assess-result-validity`。
- 新增 `inventory-results` 和 `write-results`，Results 只根据真实图表写作并禁止文献引用。
- 新增 `write-discussion`、`assemble-latex`、`compile-latex-pdf` 和 `quality-check`。

### v0.1.0 (2026-06-09) -- 项目模型、参考文献、期刊画像与首批写作器

- 新增单篇论文项目目录模型。
- 新增 `create-project`、`load-project`、`validate-project`、`update-stage-status` 和 `mark-stage-stale`。
- 新增免费文献检索路线：Semantic Scholar、arXiv、Crossref 和可选 SerpApi。
- 标准化 reference outputs：`library.bib`、`literature_items.json`、`citation_evidence.csv` 和 Markdown/HTML literature review notes。
- 新增 `resolve-journal-template` 和 literature-informed `generate-plan`。
- 新增可追溯 Introduction writer。
