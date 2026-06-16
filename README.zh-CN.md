<div align="center">

[![AI Research Loop](https://img.shields.io/badge/AI-Research%20Loop-5C4D7D?style=flat-square)](#功能概览)
[![Loop Engineering](https://img.shields.io/badge/Loop-Engineering-1D7874?style=flat-square)](#loop-模型)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#核心特性)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#核心特性)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#快速开始)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#许可证商业使用和联系方式)

# Draftpaper-loop

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
- Results 禁止文献引用，且必须绑定真实图表或表格。
- LaTeX 组装和可选本地 PDF 编译。
- 独立 integrity gate 和 review-revise-re-review 闭环。
- Codex skill wrapper 仅作为调用层，核心能力仍是 Python package + CLI + 本地项目结构。

## 项目结构

```text
draftpaper_cli/                 # 核心 Python package 和 CLI
codex_skills/draftpaper-workflow # 可选 Codex skill wrapper
docs/                           # workflow 设计和优先级指南
tests/                          # 单元测试
third_party/paper-fetch-skill/   # vendored MIT paper-fetch runtime
github_submit/                  # GitHub 提交资料和说明
```

生成的论文项目通常位于本地 `projects/` 下，并默认不提交到 git，避免上传研究数据、生成草稿、全文文献缓存和结果图表。

## 快速开始

### 通过 Codex 使用

推荐方式是让 Codex 读取本仓库并替你调用 Draftpaper-loop CLI。克隆仓库后，在 Codex 中指向仓库目录，然后用自然语言提出任务，例如：

```text
使用 C:\Draftpaper-loop 中的 Draftpaper-loop，为这个 idea 创建论文项目，检索文献，写 research plan，并告诉我当前 loop 卡在哪个阶段。
```

Codex 应先调用 orchestrator：

```powershell
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli diagnose-gate-failures --project C:\DraftPaper_CLI\projects\your_project
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
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --zotero-collection "My Paper References" --zotero-context all --zotero-min-items 20
```

`list-zotero-collections` 只返回 collection 名称和 key，不会输出 API key。`search-literature --zotero-collection` 只读取用户指定的 collection，并写入 `references/zotero_collection_manifest.json`。从 Zotero 导入的文献会被视为用户精选证据：即使缺少 abstract/PDF、不满足近年文献偏好，或超过外部检索默认 30 篇 ranking 上限，也会完整保留。系统仍会把这些文献写入与检索文献相同的输出，包括 `references/library.bib`、`references/literature_items.json`、`references/citation_evidence.csv`、`references/literature_review_notes.html`、每篇文献的 HTML summary，以及 `references/literature_summaries/index.html`。这部分文献会标记 `source=zotero_collection`、`reference_origin=existing_zotero` 和 `selection_policy=zotero_collection_preserved`，方便后续审阅时区分 Zotero 精选文献和外部检索排名文献。如果该 collection 中可用文献少于 `--zotero-min-items`，系统会按 MVP 的 Zotero-first 逻辑用免费外部检索补充，除非显式使用 `--no-zotero-supplement`。在 Codex 对话中可以这样说：“调用 Draftpaper-loop，先列出我的 Zotero collections，然后用 `My Paper References` 这个 collection 为当前项目检索文献。”

## 当前实现状态

当前版本已经包含核心 loop primitives：orchestrator、checkpoint/resume、artifact drift 检测、文献检索、期刊模板解析、research plan、Introduction、observation 记录、Data writing context、Data 写作、data inventory 和 feasibility、method plan、figure plan、figure-plan-driven analysis code generation、method verification、Methods writing context、Methods 写作、result validity、result inventory、Results、Discussion、LaTeX assembly、PDF compilation、integrity gate、review/revision routing 和 final quality check。

每个项目都有 `project_passport.yaml`，以及 append-only 的 `artifact_ledger.jsonl`、`checkpoint_ledger.jsonl` 和 `integrity_ledger.jsonl`。这些文件记录项目 artifact、hash、用户确认点和完整性事件，方便跨电脑迁移和后续审计。

`plan-figures` 会观察当前 idea、research plan、target journal、data inventory、method requirements、literature metadata 和用户已经提供的本地图表，生成 `results/figure_plan.json` 与 `results/figure_plan.html`。`generate-analysis-code` 只根据这份 figure plan 生成代码，不再固定输出某几张通用流程图。如果原始数据在服务器/API/云端，或由于隐私和体量无法下载到本地，可以只提供本地处理后表格、结果图或结果表，再通过 `inventory-results` 和 `write-results` 继续写作，但 claim 必须限制在这些可访问 artifact 支持的范围内。

`record-observation` 用于把 Codex 已经展示给用户的阶段性分析摘要保存到 `observations/observations.jsonl`，不会保存隐藏推理链。`build-data-context` 和 `build-method-context` 会把这些 observation、数据清单、可行性门、方法计划和验证结果合成为面向论文写作的 context。`write-data` 和 `write-methods` 只根据这些 context 写作，因此 Data 和 Methods 会描述数据来源、数据内容、变量组、处理流程、方法设计、验证和 claim boundary，而不是把本地文件名、路径、命令或 manifest 字段写进论文。

## Paper Fetch 集成

本仓库将 [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) vendored 到 `third_party/paper-fetch-skill`。adapter 会优先使用 `PATH` 中的 `paper-fetch` 命令；如果不可用，则可使用 vendored runtime source。

第三方 runtime 使用 MIT License，二次分发时请保留其 license notice。

## 最近更新

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

如需商业授权，请联系：[xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn)。

个人主页：[https://xiejhhhhhh.github.io/Jinhui_profile/](https://xiejhhhhhh.github.io/Jinhui_profile/)

第三方组件保留各自许可证。
