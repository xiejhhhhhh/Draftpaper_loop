<div align="center">

[![AI Research Loop](https://img.shields.io/badge/AI-Research%20Loop-5C4D7D?style=flat-square)](#功能概览)
[![Loop Engineering](https://img.shields.io/badge/Loop-Engineering-1D7874?style=flat-square)](#loop-模型)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#核心特性)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#核心特性)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#快速开始)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#许可证商业使用和联系方式)

# Draftpaper-loop

**阿里巴巴希望天下没有难做的生意，而 Draftpaper-loop 希望天下没有难写的论文。**

**本地优先的科研论文 loop 引擎，用于生成可审计、可追溯的论文初稿。**

[English](./README.md) | [中文](./README.zh-CN.md)

</div>

Draftpaper-loop 是一个本地优先的科研论文 loop 引擎。它不是一次性 draft 生成器，也不仅仅是命令行工具。CLI 是稳定的工具调用面，而产品概念是一个可重复执行的 loop：读取项目状态、检索证据、规划论文、运行方法、验证结果、组装 LaTeX、诊断失败、标记 stale 阶段，并只回退重跑必要的上游工作，直到论文初稿具备可审阅和可追溯性。

这个项目更接近 loop engineering，而不是传统 CLI workflow。对于科研论文而言，文献、数据、方法、结果、目标期刊和审稿意见会互相改变。Draftpaper-loop 把这些改变视为项目状态事件，而不是依赖一次聊天上下文或一次性生成。

## 功能概览

Draftpaper-loop 将单篇论文组织为一个本地项目目录，并通过显式、可重跑的阶段推进：项目创建、文献检索、目标期刊模板解析、research plan、Introduction、Data、Methods、Results、Discussion、LaTeX 组装、PDF 审阅、完整性检查、审稿式 revision routing 和最终 quality gate。

文献流程优先使用免费检索源，包括 Semantic Scholar、arXiv、Crossref 和可选 SerpApi。输出包括 BibTeX、citation evidence、文献综述笔记、HTML 单篇文献摘要，以及面向 Introduction/Data/Methods 的上下文证据。对于缺少 abstract 的数据或方法文献，可以通过项目内的 `paper_fetch_adapter.py` 调用 vendored `paper-fetch-skill` 运行时补全文献证据。

## Loop 模型

Draftpaper-loop 的外层逻辑是：

```text
观察项目状态
  -> 判断下一步安全行动
  -> 执行阶段命令
  -> 验证产物和 gate
  -> 记录 artifact、hash 和决策
  -> 当输入变化时标记下游阶段 stale
  -> 诊断失败并回退修订
  -> 重复直到初稿可审阅
```

确定性约束由 CLI 处理，例如 BibTeX 引用存在性、citation evidence 可追溯性、Results 禁止引用、结果 claim 必须绑定真实图表、stage stale 传播和 artifact hash 检测。开放性任务，例如研究计划、方法设计、图表规划和 revision 判断，可以由 Codex 或其他 Agent 辅助，但 Agent 应该调用同一套本地 loop，而不是绕过项目状态直接写文件。

## 核心特性

- 单篇论文项目目录模型和 stage manifest。
- `status`、`run-pipeline`、`checkpoint`、`resume` 等 orchestrator 命令。
- 基于 artifact hash 的 stale 检测和回退。
- 面向 `idea`、`data`、`methods` 的上下文文献检索。
- 支持从指定 Zotero collection 导入用户已经整理好的参考文献。
- 可追溯的 `citation_evidence.csv`。
- 目标期刊模板和 LaTeX 约束解析。
- Data feasibility gate。
- `plan-figures` 项目专属科研图表规划。
- `generate-analysis-code` 按 `results/figure_plan.json` 生成分析代码，不再固定输出通用流程图。
- Methods hard gate，要求本地方法代码成功运行。
- Result validity gate，结果不支撑结论时回退 data/method/research plan。
- Results 禁止文献引用，且必须绑定真实图表或表格；结果正文会显式引用 `Figure~\ref{...}` 和 `Table~\ref{...}`。
- LaTeX 组装和可选本地 PDF 编译。
- 默认在致谢中说明本研究使用 Draftpaper-loop 辅助生成，并附项目仓库链接。
- 独立 integrity gate 和 review-revise-re-review 闭环。
- 论文写作质量门会检查章节篇幅、自然段结构、引用位置、Methods 公式、Results 图表数量以及是否使用自然正文而非列表式文本。
- 审稿人式投稿就绪度评估，输出目标期刊适配风险、投稿就绪度评分、统计增强修订方案和 claim-evidence matrix，并支持 geography、astronomy、machine_learning 与 default fallback 的审稿工程分支。
- Codex skill wrapper 仅作为调用层，核心能力仍是 Python package + CLI + 本地项目结构。

## 项目结构

```text
draftpaper_cli/                 # 核心 Python package 和 CLI
codex_skills/draftpaper-workflow # 可选 Codex skill wrapper
docs/                           # workflow 设计和优先级指南
tests/                          # 单元测试
third_party/paper-fetch-skill/   # vendored MIT paper-fetch runtime
```

生成的单篇论文项目采用阶段归属代码结构：`data/scripts/` 保存数据收集、API/服务器 manifest、预处理和清洗代码；`methods/scripts/` 与 `methods/src/` 保存模型、统计、空间分析、验证和科研绘图代码；`results/` 只保存已经生成的图表、表格和 metadata。旧版 `code/` 目录保留为兼容 launcher 和共享 runtime 过渡层。

生成的论文项目通常位于本地 `projects/` 下，并默认不提交到 git，避免上传研究数据、生成草稿、全文文献缓存和结果图表。

## 快速开始

### 教程

基础教学视频：[Bilibili](https://www.bilibili.com/video/BV1LKjS6gEh4/?spm_id_from=333.1387.homepage.video_card.click&vd_source=463ffa8de6f1dbe750355ef3225fa45a)

### 通过 Codex 使用

推荐方式是让 Codex 读取本仓库并替你调用 Draftpaper-loop CLI。克隆仓库后，在 Codex 中指向仓库目录，然后用自然语言提出任务，例如：

```text
使用 <repo> 中的 Draftpaper-loop，为这个 idea 创建论文项目，检索文献，写 research plan，并告诉我当前 loop 卡在哪个阶段。
```

Codex 应先调用 orchestrator：

```powershell
python -m draftpaper_cli.cli status --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project <repo>\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project <repo>\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project <repo>\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project <repo>\projects\your_project
python -m draftpaper_cli.cli diagnose-gate-failures --project <repo>\projects\your_project
python -m draftpaper_cli.cli assess-publication-readiness --project <repo>\projects\your_project
python -m draftpaper_cli.cli discover-review-workflow-gaps --project <repo>\projects\your_project
python -m draftpaper_cli.cli propose-review-engineering-plan --project <repo>\projects\your_project
python -m draftpaper_cli.cli recommend-statistical-revision --project <repo>\projects\your_project
```

### 本地一键安装

```powershell
powershell -ExecutionPolicy Bypass -Command "git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git; cd Draftpaper_loop; py -3 -m venv .venv; .\.venv\Scripts\python -m pip install -U pip; .\.venv\Scripts\python -m pip install -e .[plotting]; .\.venv\Scripts\draftpaper --help"
```

可选安装全文抓取运行时：

```powershell
.\.venv\Scripts\python -m pip install -e third_party\paper-fetch-skill
```

底层 CLI 示例：

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper status --project .\projects\your_project
.\.venv\Scripts\draftpaper run-pipeline --project .\projects\your_project
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --query "topic keywords"
.\.venv\Scripts\draftpaper record-observation --project .\projects\your_project --stage data --kind agent_analysis --text "Codex 已展示给用户的数据分析摘要..."
.\.venv\Scripts\draftpaper build-data-context --project .\projects\your_project
.\.venv\Scripts\draftpaper write-data --project .\projects\your_project
.\.venv\Scripts\draftpaper list-zotero-collections
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --zotero-collection "Your Zotero Collection" --zotero-context all
.\.venv\Scripts\draftpaper prepare-method-blueprint --project .\projects\your_project
.\.venv\Scripts\draftpaper plan-figures --project .\projects\your_project
.\.venv\Scripts\draftpaper generate-analysis-code --project .\projects\your_project
.\.venv\Scripts\draftpaper record-observation --project .\projects\your_project --stage methods --kind method_rationale --text "Codex 已展示给用户的方法设计摘要..."
.\.venv\Scripts\draftpaper build-method-context --project .\projects\your_project
.\.venv\Scripts\draftpaper validate-project --project .\projects\your_project
```

运行测试：

```powershell
python -m unittest discover -s tests
```

### 通过 Codex 调用 Zotero collection

Draftpaper-loop 可以在文献检索阶段读取指定 Zotero collection 中的参考文献。先在同一个 PowerShell 或 Codex terminal session 中配置环境变量：

```powershell
$env:ZOTERO_LIBRARY_ID="your_zotero_library_id"
$env:ZOTERO_LIBRARY_TYPE="user"   # 或 "group"
$env:ZOTERO_API_KEY="your_zotero_api_key"
```

然后可以让 Codex 调用 loop，或直接运行：

```powershell
python -m draftpaper_cli.cli list-zotero-collections
python -m draftpaper_cli.cli search-literature --project <repo>\projects\your_project --zotero-collection "My Paper References" --zotero-context all --zotero-min-items 20
```

`list-zotero-collections` 只返回 collection 名称和 key，不会输出 API key。`search-literature --zotero-collection` 只读取用户指定的 collection，并写入 `references/zotero_collection_manifest.json`。从 Zotero 导入的文献会被视为用户精选证据：即使缺少 abstract/PDF、不满足近年文献偏好，或超过外部检索默认 30 篇 ranking 上限，也会完整保留。系统仍会把这些文献写入与检索文献相同的输出，包括 `references/library.bib`、`references/literature_items.json`、`references/citation_evidence.csv`、`references/literature_review_notes.html`、每篇文献的 HTML summary，以及 `references/literature_summaries/index.html`。这部分文献会标记 `source=zotero_collection`、`reference_origin=existing_zotero` 和 `selection_policy=zotero_collection_preserved`，方便后续审阅时区分 Zotero 精选文献和外部检索排名文献。如果该 collection 中可用文献少于 `--zotero-min-items`，系统会按 MVP 的 Zotero-first 逻辑用免费外部检索补充，除非显式使用 `--no-zotero-supplement`。在 Codex 对话中可以这样说：“调用 Draftpaper-loop，先列出我的 Zotero collections，然后用 `My Paper References` 这个 collection 为当前项目检索文献。”

## 当前实现状态

当前版本已经包含核心 loop primitives：orchestrator、checkpoint/resume、artifact drift 检测、文献检索、期刊模板解析、research plan、Introduction、observation 记录、Data writing context、Data 写作、data inventory 和 feasibility、method plan、figure plan、figure-plan-driven analysis code generation、method verification、Methods writing context、Methods 写作、result validity、result inventory、Results、Discussion、LaTeX assembly、PDF compilation、integrity gate、review/revision routing、publication readiness assessment、statistical rescue planning 和 final quality check。

每个项目都有 `project_passport.yaml`，以及 append-only 的 `artifact_ledger.jsonl`、`checkpoint_ledger.jsonl` 和 `integrity_ledger.jsonl`。这些文件记录项目 artifact、hash、用户确认点和完整性事件，方便跨电脑迁移和后续审计。

`plan-figures` 会观察当前 idea、research plan、target journal、data inventory、method requirements、literature metadata 和用户已经提供的本地图表，生成 `results/figure_plan.json` 与 `results/figure_plan.html`。使用 `--use-review-tasks` 时，它会把 executable/partial 的审稿救援任务转成修订图表计划，同时跳过 blocked 任务。`generate-analysis-code` 只根据这份 figure plan 生成代码，不再固定输出某几张通用流程图；使用 `--use-review-tasks` 时还会输出 `results/tables/review_task_coverage.csv` 和 `results/tables/review_task_metrics.csv`，用于记录清洗/QC、特征重构、baseline/ablation 和验证覆盖情况。如果原始数据在服务器/API/云端，或由于隐私和体量无法下载到本地，可以只提供本地处理后表格、结果图或结果表，再通过 `inventory-results` 和 `write-results` 继续写作，但 claim 必须限制在这些可访问 artifact 支持的范围内。

`record-observation` 用于把 Codex 已经展示给用户的阶段性分析摘要保存到 `observations/observations.jsonl`，不会保存隐藏推理链。`build-data-context` 和 `build-method-context` 会把这些 observation、数据清单、可行性门、方法计划和验证结果合成为面向论文写作的 context。`write-data` 和 `write-methods` 只根据这些 context 写作，因此 Data 和 Methods 会描述数据来源、数据内容、变量组、处理流程、方法设计、验证和 claim boundary，而不是把本地文件名、路径、命令或 manifest 字段写进论文。

`write-results` 现在会在结果正文中通过 LaTeX 标签显式指向对应图表，例如 `Figure~\ref{...}` 和 `Table~\ref{...}`。内部 loop 术语、本地路径约束、gate 名称、manifest 信息和项目管理式措辞不会写入论文正文，而是保留在日志、报告或致谢中。`assemble-latex` 会在参考文献之前默认加入致谢，说明 Draftpaper-loop 参与了分阶段文献组织、分析可追溯性、图表清单和论文初稿生成。

## Paper Fetch 集成

本仓库将 [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) vendored 到 `third_party/paper-fetch-skill`。adapter 会优先使用 `PATH` 中的 `paper-fetch` 命令；如果不可用，则可使用 vendored runtime source。

第三方 runtime 使用 MIT License，二次分发时请保留其 license notice。

## 最近更新

### v0.14.4 (2026-06-25) -- public wording and license positioning

- 保留当前 source-available non-commercial 自定义许可，没有切换为 Apache-2.0 或其它标准 SPDX 许可证，因为商业授权边界需要非标准条款才能表达清楚。
- 清理公开更新日志中的具体项目来源表述，后续公开 README 默认用可复用能力描述插件 seed，而不是暴露内部项目名、私有验证目标或具体研究方向。
- 明确后续公开 changelog 应避免写入本地验证文件夹、私有数据集、项目级样本选择、真实项目名称或过细的研究场景来源。

### v0.14.3 (2026-06-25) -- composite discipline modules

- 新增 runtime composite discipline modules，用于交叉学科论文；loop 现在会记录 `primary_discipline`、`secondary_disciplines`、`discipline_scores` 和有序 `discipline_modules`。
- `get_discipline_module` 现在可以合并 `default`、主学科和辅学科，并按稳定 id 去重 data connectors、method templates 和 review rules。
- geography + machine learning、astronomy + machine learning 等交叉项目可以在 `prepare-method-blueprint`、`prepare-data-acquisition` 和 `plan-figures` 中同时暴露领域插件与 ML 建模/审稿插件。
- 插件候选 manifest 现在会记录主学科和辅学科，但稳定可复用能力仍然归入其对应 home module，避免按论文方向拆永久分支。

### v0.14.2 (2026-06-24) -- geography and tabular-ML plugin seeds

- 新增 geography 数据 connector：Earth Engine 降水导出规划、NetCDF-to-GeoTIFF 转换规划、栅格文本转 raster、ArcGIS/project-bound 分区统计 manifest。
- 新增 geography 方法模板：月尺度遥感指数汇总、物候曲线平滑、NDVI 时序 K-means 分区、聚类统计诊断。
- 新增 machine-learning 数据/模型 seed：表格环境数据 profile、脱敏 saved-model manifest、RF/XGBoost/GBDT/Stacking 回归计划、observed-predicted 诊断、feature importance、PDP/ICE、SHAP plan，以及模型统计有效性 reviewer gate。
- 这些 seed 均保持 fixture-backed 与 dependency-light：可复用插件代码保持通用，项目路径、API 账号、数据窗口和模型二进制文件只留在本地项目绑定中。

### v0.14.1 (2026-06-24) -- astronomy and deep-learning plugin sedimentation

- 新增 astronomy connector 和 method seed，覆盖 photon/event 数据访问规划、观测产品 manifest、长时标光变特征提取和事件级序列输入构建。
- 新增 machine-learning/deep-learning connector 和 method seed，覆盖视觉目录对齐、预训练 backbone 元数据、自监督训练规划、checkpoint 兼容性诊断、embedding 健康检查、少标签评估和相似性检索。
- 为这些学科插件补充 fixture-backed tests，使其不依赖私有数据、API 凭证、大模型 checkpoint 或 GPU 训练即可完成基础验证。
- 通用插件模板不保存项目私有路径、账号凭证、checkpoint 二进制文件或固定样本选择；真实项目中的具体路径和参数由 Draftpaper-loop 项目本地绑定。

### v0.14.0 (2026-06-24) -- discipline plugin contribution workflow

- 新增完整的 `DataConnectorSpec` 和 `MethodTemplateSpec` schema。
- 将学科模块推进为三层结构：`data_connectors/`、`method_templates/` 和 `review_rules/`。
- 新增 geography 方法模板：`remote_sensing_feature_reconstruction` 和 `spatial_block_validation`。
- 新增 machine_learning 方法模板：`baseline_model`、`ablation_study` 和 `train_validation_test_split_check`。
- 新增插件贡献 preflight 命令：`summarize-plugin-candidates`、`generalize-plugin-candidate`、`validate-plugin-candidate`、`package-plugin-contribution` 和 `write-github-contribution-guide`。
- 明确 fork/PR 规则：fork 和 branch 只是临时贡献通道；稳定通用能力必须在隐私、通用性、overlap、fixture 和 validation 检查后合并进 `main` 对应学科模块。

### v0.13.1 (2026-06-24) -- discipline figure policy and data connector catalog

- 升级 `plan-figures`：学科模块可以声明 `minimum_main_figures`、`target_main_figures` 和 `required_figure_groups`，在数据可用时默认初稿会尽量规划至少 5 张 generated 主图。
- 扩展学科模块的数据获取 connector catalog，记录 package、import module、API/下载路径、凭证要求、可获取数据格式和本地 feasibility 状态。
- 新增 `ecology` 和 `bioinformatics` 学科模块骨架，并与 `default`、`geography`、`astronomy`、`machine_learning` 一起接入 registry。
- 补充 geography/agriculture、astronomy、ecology/environment、machine_learning 和 bioinformatics 的数据获取路线，用于 research plan 阶段的数据补充建议和 reviewer/rescue 缺失数据回退。

### v0.13.0 (2026-06-24) -- stage-owned method code and discipline modules

- 新增阶段归属代码结构：数据获取和预处理代码进入 `data/scripts`，模型、统计、空间分析、验证和科研绘图代码进入 `methods/scripts` 与 `methods/src`，`results` 只保存图表、表格和 metadata。
- 新增 `prepare-method-blueprint`，输出 `methods/method_blueprint.json`、`methods/method_data_contract.json`、`methods/method_code_plan.json` 和 `methods/method_formula_plan.json`。
- 新增 `discipline_modules` 框架，并预留 default、geography、astronomy 和 machine_learning 四类模块骨架，用于共享数据角色、方法族、图表族、公式族和审稿约束。
- 升级 `generate-analysis-code`：主生成代码默认保存到 `methods/`，`code/` 仅作为旧流程兼容入口。
- 新增 `docs/discipline_modules/`，用于说明后续不同学科模块如何由 Codex 总结、测试并接入。

### v0.12.1 (2026-06-24) -- reviewer/rescue data acquisition tasks

- 将 reviewer/rescue 中的缺失数据建议接入 `prepare-data-acquisition`。
- `prepare-data-acquisition` 现在会读取 `review/actionable_analysis_tasks.json`、`review/review_engineering_plan.json`、`review/statistical_rescue_plan.json`、`review/revision_plan.json` 和 `review/gate_failure_diagnosis.json`。
- 新增 `data/data_acquisition_tasks.json` 和 `data/data_acquisition_tasks.html`，把 blocked analysis task 转换成明确的缺失数据请求，记录 `needed_data`、`optional_data`、`suggested_connectors` 和需要用户确认的问题。
- 升级 `status` 和 `run-pipeline`，让 review/rescue 执行链在 `prepare-analysis-revision` 之后、`plan-figures --use-review-tasks` 之前自动推荐 `prepare-data-acquisition`。

### v0.12.0 (2026-06-23) -- pluggable data acquisition planning

- 新增共享学科推断层，供数据获取规划和审稿工程共同使用，避免 Data 插件和 review/rescue 插件各自重复判断学科。
- 新增 `classify-data-access`、`prepare-data-acquisition` 和 `inventory-data-sources`，用于在正式数据清点前生成 plan-first 的数据获取规划。
- 新增通用 connector profile：`local_files`、`api_access` 和 `remote_server`。这些 connector 只识别数据获取模式，不下载外部数据，不写入凭证，也不把天文学、地理学等领域专用包硬编码进核心 Data 阶段。
- 新增数据获取产物：`data/data_access_profile.json`、`data/data_acquisition_plan.json`、`data/data_acquisition_plan.html`、`data/data_source_manifest.csv`、`data/data_access_log.csv`、`data/data_provenance.json` 和 `data/data_completeness_report.html`。
- 新增设计文档和实施计划，保存在 `docs/superpowers/specs/` 和 `docs/superpowers/plans/`。
- 已用本地 cross-discipline 源目录验证通用层，同时检测到 local files、API access 和 remote server 三类数据获取模式；公开文档不记录私有路径或具体项目标识。

### v0.11.1 (2026-06-23) -- source-available protection and generator provenance

- 新增仓库级保护文件：`NOTICE`、`COMMERCIAL_LICENSE.md` 和 `TRADEMARK.md`。
- 将 `LICENSE` 中较早的 DraftPaper CLI 表述更新为 Draftpaper-loop，并补充 API 服务、论文生产服务、付费课程捆绑等商业使用示例。
- 为一方 Python 文件补充版权声明和联系邮箱，同时保持 `third_party/` 等第三方文件不变。
- 在生成的 LaTeX、HTML 报告、生成式 Python 脚本，以及包含 `generated_at` 的 JSON 报告中加入稳定的 Draftpaper-loop generator provenance。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：130 tests

### v0.11.0 (2026-06-21) -- publication-readiness reviewer and statistical rescue planning

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

### v0.10.0 (2026-06-18) -- manuscript-quality gates and clean Results/acknowledgment writing

- 新增论文写作质量门：检查章节最低篇幅、实质性自然段数量、禁止列表式正文、避免随意加粗、Introduction/Discussion 引用存在性、Methods 公式存在性，以及 Results 主图数量要求。
- 升级 `write-results`，结果段落会用 LaTeX 标签引用对应图表，例如 `Figure~\ref{...}` 和 `Table~\ref{...}`。
- 清理 Results 和 Discussion 的论文正文表达，避免把内部 loop 术语、gate 名称、本地文件保护规则、manifest 引用和 Draftpaper-loop 实现说明写进科学正文。
- LaTeX 组装默认加入致谢，说明本研究使用 Draftpaper-loop 辅助完成分阶段文献组织、分析可追溯性、图表清单和论文初稿生成，并附项目链接 `https://github.com/xiejhhhhhh/Draftpaper_loop`。
- 强化 Methods 输出，新增公式清单和 `methods/method_formulas.tex`，并接入 quality gate，防止 Methods 初稿缺少数学表达。
- 强化科研图验证，生成图必须提供 PNG/出版级 metadata、坐标轴标签、文字元素、统计量、解释摘要和 publication-ready 后端证据。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：111 tests

### v0.9.0 (2026-06-16) -- scientific figure loop and plotting dependencies

- 新增绘图依赖分层：真实科研项目推荐使用 `.[plotting]`，高级图像和报告场景可使用 `.[plotting-full]`。
- 新增项目本地科研绘图 runtime，`generate-analysis-code` 会把 `scientific_plotting.py` 写入单篇论文项目的 `code/src/`，方便迁移和复现。
- 升级 `plan-figures`，图像规划不再只是图名和类型，而是包含 `figure_type`、变量、统计变换、后端偏好和 `no_flowchart_fallback` 的 FigureSpec。
- 升级 `generate-analysis-code`，生成的分析流程会输出真实科研 SVG 图、`results/figure_metadata.json` 和 `results/figure_quality_report.json`。
- 新增 numpy/stdlib 兼容的科研 SVG 图：散点回归图、直方分布图、类别支持图、相关热图和指标汇总图。
- 升级 `inventory-results` 和 `write-results`，结果段落优先使用图像 metadata 中的样本量、相关方向、R/R2、类别支持和指标摘要，而不是泛泛复述 artifact。
- 升级 quality gate，生成式经验结果图必须具备科学 metadata、坐标/尺度证据和解释摘要，workflow 图不能再静默替代 Results 里的科研图。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：103 tests

### v0.8.0 (2026-06-15) -- observation-driven Data and Methods loop

- 新增 `record-observation`，用于保存 Codex/用户已公开确认的分析摘要，不保存隐藏推理链。
- 新增 `build-data-context` 和 `write-data`，让 Data 部分从数据来源、内容、处理和 claim boundary context 写作，而不是从文件路径写作。
- 新增 `build-method-context`，并升级 `write-methods`，让 Methods 从方法意图、数据角色、验证摘要和 claim boundary 写作，而不是直接写命令或 manifest。
- 升级 `run-pipeline`，Data 和 Methods 这类多子步骤 stage 只有在 context 和 manuscript 输出都存在后才会被视为完成。
- 升级 quality gate，如果 Data/Methods 正文包含本地文件名、路径、执行命令或 manifest 式输出文本，会直接失败。

### v0.7.1 (2026-06-15) -- preserved Zotero evidence in literature summaries

- 将 Zotero 导入文献作为用户精选证据完整保留，不再受外部检索 ranking、近年文献偏好、abstract/PDF 过滤和默认 30 篇外部文献上限约束。
- 在 literature review notes、每篇文献 HTML summary 和 `references/literature_summaries/index.html` 中加入 Zotero source、origin、collection 和 selection policy 信息。
- 增加测试，确认 Zotero 文献会与检索文献一起出现在 HTML index 中，同时保持来源可区分。

### v0.7.0 (2026-06-15) -- Zotero collection import for references

- 新增 `list-zotero-collections`，方便 Codex 或本地 CLI 查看 Zotero collection 名称。
- 新增 `search-literature --zotero-collection`，允许单篇论文项目从用户指定的 Zotero collection 导入参考文献。
- 新增 `--zotero-context`、`--zotero-min-items` 和 `--no-zotero-supplement`，用于控制 citation evidence 章节归属和 Zotero-first 外部补充逻辑。
- 新增 `references/zotero_collection_manifest.json`，记录请求的 collection、实际匹配的 collection、collection key、可用条目数量和补充文献数量。
- 在 README 中补充 Codex 如何调用 Zotero collection 的方法，并说明 `ZOTERO_LIBRARY_ID`、`ZOTERO_LIBRARY_TYPE` 和 `ZOTERO_API_KEY` 只通过环境变量读取，不会在输出中暴露。

### v0.6.0 (2026-06-11) -- renamed and reframed as Draftpaper-loop

- 将项目从 CLI-first 论文生成工具重新定位为 loop-engineered 科研论文系统。
- README 名称从 DraftPaper CLI 改为 Draftpaper-loop，同时保留 `draftpaper` 作为稳定 CLI 接口。
- 增加 observe、decide、run、verify、persist state、mark stale、diagnose failure、rerun 的 loop 模型。
- 新增 `plan-figures`，在生成分析代码前先规划项目专属科研图表。
- `generate-analysis-code` 改为读取 `results/figure_plan.json`，不再生成固定 workflow 图。
- 增加远程/服务器/API 数据和用户提供 processed/result artifacts 的支持，并对 claim strength 做 conditional pass 限制。
- summary 类文档增加 HTML 主产物，例如 research plan、research questions、novelty report、figure plan 和 literature review notes，同时保留 Markdown 兼容文件。
- 联系方式、商业使用条款和个人主页移动到 README 末尾。

### v0.5.0 (2026-06-09) -- review routing and gate-failure diagnosis

- 新增 `diagnose-gate-failures`、`review-draft`、`generate-revision-plan`、`apply-revision` 和 `re-review`。
- 新增统一 revision issue schema。
- 新增 `review/commitment_ledger.csv`，用于追踪多轮修订中的用户决策。
- `status` 和 `run-pipeline` 在 integrity/quality 失败后推荐 `diagnose-gate-failures`。
- 本地验证：`python -m unittest discover -s tests`。
- 当前测试规模：95 tests。

### v0.4.0 (2026-06-09) -- integrity gate and artifact traceability

- 新增 `run-integrity-gate`。
- 新增 `integrity/integrity_report.json` 和 `integrity/integrity_report.md`。
- 检查 BibTeX 引用存在性、`citation_evidence.csv` 可追溯性、Results 禁引用规则和 result claim artifact binding。

### v0.3.0 (2026-06-09) -- passport, stale sync, and staged orchestration

- 新增 DraftPaper Passport：`project_passport.yaml`、`artifact_ledger.jsonl`、`checkpoint_ledger.jsonl` 和 `integrity_ledger.jsonl`。
- 新增 `status`、`checkpoint`、`resume` 和 `run-pipeline`。
- 新增 `detect-artifact-drift` 和 `sync-artifact-stale`。
- 增加早期本地方法/结果 artifact 检查能力。

### v0.2.0 (2026-06-09) -- Methods, Results, Discussion, and LaTeX hard gates

- 新增 `collect-method-plan`。
- 新增 `generate-analysis-code`、`verify-methods` 和 `methods/run_manifest.yaml`。
- 新增 `assess-result-validity`。
- 新增 `inventory-results` 和 `write-results`，Results 只根据真实图表写作并禁止文献引用。
- 新增 `write-discussion`、`assemble-latex`、`compile-latex-pdf` 和 `quality-check`。

### v0.1.0 (2026-06-09) -- project model, references, journal profile, and first writers

- 新增单篇论文项目目录模型。
- 新增 `create-project`、`load-project`、`validate-project`、`update-stage-status` 和 `mark-stage-stale`。
- 新增免费文献检索路线：Semantic Scholar、arXiv、Crossref 和可选 SerpApi。
- 标准化 reference outputs：`library.bib`、`literature_items.json`、`citation_evidence.csv` 和 Markdown/HTML literature review notes。
- 新增 `resolve-journal-template` 和 literature-informed `generate-plan`。
- 新增可追溯 Introduction writer。

## 许可证、商业使用和联系方式

Draftpaper-loop 以 source-available 形式开放给非商业科研、评估、教学和个人论文工作流使用。商业使用、付费服务、SaaS 部署、企业部署、转售，或集成到商业产品中，需要事先获得项目开发者的书面授权。

当前非商业 source-available 条款、归属声明、商业授权范围和项目名称/商标政策见 [`LICENSE`](./LICENSE)、[`NOTICE`](./NOTICE)、[`COMMERCIAL_LICENSE.md`](./COMMERCIAL_LICENSE.md) 和 [`TRADEMARK.md`](./TRADEMARK.md)。

如需商业授权，请联系：[xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn)。

个人主页：[https://xiejhhhhhh.github.io/Jinhui_profile/](https://xiejhhhhhh.github.io/Jinhui_profile/)

第三方组件保留各自许可证。
