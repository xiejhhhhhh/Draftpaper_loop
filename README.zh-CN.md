# DraftPaper CLI

[![AI Research Workflow](https://img.shields.io/badge/AI-Research%20Workflow-5C4D7D?style=flat-square)](#)
[![Literature Analysis](https://img.shields.io/badge/Literature-Analysis-1D7874?style=flat-square)](#)
[![Citation Evidence](https://img.shields.io/badge/Citation-Evidence-4C956C?style=flat-square)](#)
[![BibTeX](https://img.shields.io/badge/BibTeX-Reference%20Library-3A506B?style=flat-square)](#)
[![Local First](https://img.shields.io/badge/Local-First-E07A5F?style=flat-square)](#)
[![Python CLI](https://img.shields.io/badge/Python-CLI-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![Source Available](https://img.shields.io/badge/Source-Available-8A5A44?style=flat-square)](#许可证和商业使用)

联系方式：[xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn)

中文 | [English](README.md)

DraftPaper CLI 是一个本地优先的科研论文流程化写作引擎。它把研究 idea、本地数据、已验证的方法代码、结果图表和可追溯文献证据组织成分阶段的 LaTeX 论文初稿。核心能力是 Python package + CLI；Codex skills、桌面端、Web UI、未来 API/SaaS 都应该调用同一套核心能力，而不是重复实现业务逻辑。

本仓库现在作为开放科研与研发项目发布。你可以在仓库许可证约束下查看、学习，并用于非商业科研、教学、评估和个人论文工作流。如果希望把 DraftPaper CLI 或其衍生工作流用于商业用途，请联系项目开发者获取书面授权。

## 它能做什么

DraftPaper CLI 把一篇论文拆成一个本地项目目录，并通过明确阶段推进：创建项目、文献检索、目标期刊模板理解、research plan、Introduction、Data、Methods、Results、Discussion、LaTeX 组装、PDF 审阅、完整性门槛、审稿式修订路由和最终质量门槛。

文献流程优先使用免费检索源，包括 Semantic Scholar、arXiv、Crossref 和可选 SerpApi。系统会输出 BibTeX、citation evidence、文献综述笔记、HTML 文献摘要，并按 `idea`、`data`、`methods` 标记每篇文献支持的论文章节。当 data/methods 文献缺少可读 abstract 时，DraftPaper 可通过 `paper_fetch_adapter.py` 调用项目内 vendored 的 `paper-fetch-skill`，尝试抓取全文 Markdown/JSON 作为证据。

## 核心能力

- 单篇论文本地项目目录模型和 staged manifests。
- 阶段状态机、回退重跑、stale 标记和项目验证。
- 面向 `idea`、`data`、`methods` 的上下文文献检索。
- 用 `citation_evidence.csv` 追踪每个引用支持的论断。
- 目标期刊 profile 阶段，用于约束 LaTeX 模板和写作规范。
- Data feasibility gate：在方法规划前判断数据能否支撑当前研究目标。
- Methods 硬门槛：必须先跑通本地方法代码。
- Result validity gate：结果不支撑结论时回退 data/method/research plan。
- Results 禁止文献引用，并绑定真实 figure/table。
- LaTeX 组装和可选本地 PDF 编译。
- 独立 integrity gate，用于检查 BibTeX、citation evidence 和结果产物绑定。
- Review-revise-re-review 闭环，包含 gate failure routing 和 commitment ledger。
- Quality gate 检查引用、结果文件、stale 阶段和期刊模板。
- Codex skill wrapper 只是调用层，不承载核心业务逻辑。

## 项目结构

```text
draftpaper_cli/                 # 核心 Python package 和 CLI 阶段
codex_skills/draftpaper-workflow # 可选 Codex skill wrapper
docs/                           # 工作流设计和优先级指南
tests/                          # 单元测试
third_party/paper-fetch-skill/   # vendored MIT paper-fetch runtime
github_submit/                  # GitHub 提交材料和说明
```

本地生成的论文项目默认放在 `projects/`，并被 git 忽略，避免把研究数据、生成稿件、全文缓存和结果文件上传到仓库。

## 快速开始

### 在 Codex 中使用

推荐使用方式不是让用户手动敲每一条 CLI 命令，而是让 Codex 读取该仓库并替你调用 DraftPaper CLI。克隆仓库后，在 Codex 中打开或指向该目录，然后直接用自然语言提出任务，例如：

```text
请使用 C:\Draftpaper_CLI 里的 DraftPaper CLI，基于我的 idea 创建论文项目、检索文献、生成 research plan，并告诉我哪些阶段被阻塞。
```

Codex 应负责运行对应 CLI、读取本地项目文件并报告下一步。下面的 `draftpaper` 命令是底层接口，主要用于调试、自动化脚本或不通过 Codex 使用时。

分阶段工作时，Codex 应先调用总控层：

```powershell
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli detect-artifact-drift --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli sync-artifact-stale --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli diagnose-gate-failures --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli generate-revision-plan --project C:\DraftPaper_CLI\projects\your_project
```

### 一键本地安装

在你希望保存项目的目录中运行下面命令。它会克隆仓库、创建本地虚拟环境、安装 DraftPaper CLI，并打印 CLI 帮助信息。`paper-fetch-skill` 已经 vendored 在 `third_party/paper-fetch-skill`，只有需要全文抓取时再单独安装。

```powershell
powershell -ExecutionPolicy Bypass -Command "git clone https://github.com/xiejhhhhhh/Draftpaper_CLI.git; cd Draftpaper_CLI; py -3 -m venv .venv; .\.venv\Scripts\python -m pip install -U pip; .\.venv\Scripts\python -m pip install -e .; .\.venv\Scripts\draftpaper --help"
```

可选安装全文抓取 runtime：

```powershell
.\.venv\Scripts\python -m pip install -e third_party\paper-fetch-skill
```

安装后，也可以在仓库根目录中直接使用 `draftpaper` 命令：

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper status --project .\projects\your_project
.\.venv\Scripts\draftpaper run-pipeline --project .\projects\your_project
.\.venv\Scripts\draftpaper search-literature --project .\projects\your_project --query "topic keywords"
.\.venv\Scripts\draftpaper validate-project --project .\projects\your_project
```

如果只想快速确认 CLI 能运行，不进行联网文献检索，可以执行：

```powershell
.\.venv\Scripts\draftpaper create-project --root .\projects --idea "X-ray flaring source classification" --field "machine learning astronomy" --target-journal APJS
.\.venv\Scripts\draftpaper validate-project --project .\projects\x-ray-flaring-source-classification
```

### 开发模式安装

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli generate-analysis-code --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-integrity-gate --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

运行测试：

```powershell
python -m unittest discover -s tests
```

## 当前实现状态

CLI 已实装总控层命令（`status`、`checkpoint`、`resume`、`run-pipeline`）、基于 hash 的 stale 同步命令（`detect-artifact-drift`、`sync-artifact-stale`），以及项目状态、文献检索、目标期刊 profile、research plan、Introduction、数据清单和可行性检查、method plan 收集、文献与方法描述驱动的 baseline 分析代码生成、方法代码运行验证、Methods 写作、结果有效性检查、结果清单、Results 写作、Discussion、LaTeX 组装、PDF 编译、独立完整性检查、review/revision routing 和最终质量检查等阶段命令。

每个项目都带有 DraftPaper Passport：`project_passport.yaml`，以及 append-only 的 `artifact_ledger.jsonl`、`checkpoint_ledger.jsonl`、`integrity_ledger.jsonl`。这些文件记录项目 artifact、hash、人工 checkpoint 和 integrity event，方便换电脑迁移，也避免依赖 Codex 对话记忆判断项目状态。

当被追踪 artifact 的 hash 发生变化时，`status` 返回 `pipeline_state=drift_detected`，并建议先运行 `sync-artifact-stale`。该命令会把变化文件映射回来源阶段，自动把下游依赖阶段标记为 stale，把 drift 写入 `integrity_ledger.jsonl`，并刷新 passport 的 hash 基线。

`generate-analysis-code` 会读取已检索文献、`methods/method_requirements.json`、`methods/method_plan.md` 和 `data/data_inventory.json`，在项目 `code/` 目录下生成可审阅、可运行的 Python baseline 分析代码，并写入 `methods/analysis_code_manifest.json`。默认输出包括两张表和四张 SVG 图：数据分析流程、数据处理流程、方法分析流程、数据喂入方法后的输出流程。该阶段不是最终科学模型生成器，而是可复现代码脚手架；后续仍需由 `verify-methods` 运行命令、记录 `methods/run_manifest.yaml`，并确认所有声明输出存在后才能继续写 Methods。

`run-integrity-gate` 会写入 `integrity/integrity_report.json` 和 `integrity/integrity_report.md`，并向 `integrity_ledger.jsonl` 追加 `integrity_gate` event。它检查 manuscript citations 是否存在于 BibTeX、Introduction/Data/Methods/Discussion 引用是否可追溯到 `references/citation_evidence.csv`、Results 是否包含 citation commands，以及 `results/result_manifest.yaml` 中每个 result claim 是否绑定真实本地图表。

`diagnose-gate-failures`、`review-draft`、`generate-revision-plan`、`apply-revision` 和 `re-review` 构成 review-revise-re-review 闭环。Gate failures 会被转换成统一 revision issues，记录 target stage、需要检查的文件、所需用户决策和建议重跑命令。当 integrity 或最终 quality 报告失败时，`status` 和 `run-pipeline` 会自动推荐 `diagnose-gate-failures`。

## Paper Fetch 集成

本仓库把 [`Dictation354/paper-fetch-skill`](https://github.com/Dictation354/paper-fetch-skill) vendored 到 `third_party/paper-fetch-skill`。Adapter 优先使用 PATH 中的 `paper-fetch` 命令；如果没有，也可以使用项目内 vendored runtime source。建议在独立虚拟环境中安装：

```powershell
python -m pip install -e third_party\paper-fetch-skill
```

该第三方 runtime 使用 MIT License，二次分发时需要保留其 license notice。

## 许可证和商业使用

DraftPaper CLI 以 source-available 形式开放给非商业科研、评估、教学和个人论文工作流使用。商业使用、付费服务、SaaS 部署、企业部署、转售，或集成到商业产品中，需要事先获得项目开发者的书面授权。

如需商业授权，请联系：[xiejinhui22@mails.ucas.ac.cn](mailto:xiejinhui22@mails.ucas.ac.cn)。

第三方组件保留各自许可证。

## 最近更新

### v0.5.0 (2026-06-09) -- review routing and gate-failure diagnosis

这一版完成第一轮 review-revise-re-review 闭环，并把失败的最终门槛接回可执行的修订路由。

更新重点：

- 新增 `diagnose-gate-failures`、`review-draft`、`generate-revision-plan`、`apply-revision` 和 `re-review`。
- 新增统一 revision issue schema，记录 `source`、`target_stage`、`files_to_add_or_edit`、`required_user_input` 和 `recommended_commands`。
- 新增 `review/commitment_ledger.csv`，用于追踪用户在多轮修订中的决策和承诺。
- 将 `status` 和 `run-pipeline` 接入失败的 integrity/quality 报告，使其推荐 `diagnose-gate-failures`，而不是盲目重复运行失败 gate。
- `apply-revision` 保持保守：只标记相关阶段 stale，不自动改写科学内容。
- 本地验证：`python -m unittest discover -s tests`
- 当前测试规模：91 tests

### v0.4.0 (2026-06-09) -- integrity gate and artifact traceability

- 新增 `run-integrity-gate`。
- 新增 `integrity/integrity_report.json` 和 `integrity/integrity_report.md`。
- 检查 BibTeX 引用是否存在、`citation_evidence.csv` 是否可追溯、Results 是否禁用文献引用、result claim 是否绑定真实图表文件。
- 将 `status` 和 `run-pipeline` 接入 integrity gate，使最终质量检查必须等待完整性报告通过。

### v0.3.0 (2026-06-09) -- passport, stale sync, and staged orchestration

- 新增 DraftPaper Passport：`project_passport.yaml`、`artifact_ledger.jsonl`、`checkpoint_ledger.jsonl` 和 `integrity_ledger.jsonl`。
- 新增 `status`、`checkpoint`、`resume` 和 `run-pipeline`。
- 新增基于 hash 的 artifact drift 检测：`detect-artifact-drift` 和 `sync-artifact-stale`。
- 新增文献驱动的分析代码生成，并默认生成方法/结果流程图和表格，方便本地 smoke test。

### v0.2.0 (2026-06-09) -- Methods, Results, Discussion, and LaTeX hard gates

- 新增 `collect-method-plan`，将用户方法描述和文献方法归纳转换为 `methods/method_requirements.json`。
- 新增 `generate-analysis-code`，根据文献、数据清单和方法需求生成可审阅的本地 baseline 分析代码。
- 新增 `verify-methods` 和 `methods/run_manifest.yaml`；Methods 写作必须建立在成功运行的方法代码之上。
- 新增 `assess-result-validity`，当结果无法支撑预期结论时回退到 data、methods 或 research plan。
- 新增 `inventory-results` 和 `write-results`；Results 只能根据真实图表和表格写作，并禁止文献引用。
- 新增 `write-discussion`、`assemble-latex`、`compile-latex-pdf` 和 `quality-check`。

### v0.1.0 (2026-06-09) -- project model, references, journal profile, and first writers

- 新增单篇论文项目目录模型：`idea/`、`references/`、`research_plan/`、`introduction/`、`data/`、`methods/`、`results/`、`discussion/`、`latex/` 等。
- 新增 `create-project`、`load-project`、`validate-project`、`update-stage-status` 和 `mark-stage-stale`。
- 新增免费文献检索路线：Semantic Scholar、arXiv、Crossref、可选 SerpApi。
- 固定输出 `references/library.bib`、`references/literature_items.json`、`references/citation_evidence.csv` 和 `references/literature_review_notes.md`。
- 新增基于目标期刊的 `resolve-journal-template` 和文献驱动 `generate-plan`。
- 新增可追溯 Introduction writer，引用必须同时存在于 BibTeX 和 citation evidence。
