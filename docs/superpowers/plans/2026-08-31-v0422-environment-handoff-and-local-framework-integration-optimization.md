# Draftpaper-loop v0.42.2 -> v0.43.0 环境交接与本地框架改动整合优化方案

> 本文件是环境交接、框架改动整合、验证和发布的执行手册，不是已经完成发布的证明。除非后文的验收证据已经产生，否则“待完成”“待验证”状态不得在 README、Release note 或用户回复中写成“已完成”。

## 0. 本版状态校正

以下状态以 2026-08-31 当前本地检查结果为准：

| 项目 | 当前状态 | 处理原则 |
|---|---|---|
| 当前分支 | 本地 `main` 与 `origin/main` 共同指向 `53569a5` | 直接在本地 `main` 上形成后续增量提交，不再创建无必要的合并分支 |
| v0.42.2 | 远端已有正式 tag，指向 `c0a3840d163f107cd5fecdf31cec4cada467e2d8` | tag、Release 和发布提交保持不可变，不允许 force-push 或移动 tag |
| 本地框架改动 | 已重新应用到 `main` 基线，但仍在工作树中，尚未形成最终提交 | 先按功能边界拆分、测试和审查，再纳入新版本 |
| 环境补漏改动 | 已写入工作树，包含依赖、profile、Doctor、验证器、bootstrap、文档和 CI 调整 | 以 clean install、wheel 和 fresh clone 验证为准，不以当前机器可导入为准 |
| v0.43.0 | 尚未完成最终发布闭环 | 完成所有门禁后再创建 tag、Release、wheel 和远端归档 |
| 本机虚拟环境 | 仅用于发现缺口，不能作为交接物 | 不上传 `.venv`、`.uv-venv`、系统安装包、缓存或凭证 |

当前工作树中还存在论文项目、商业文档、临时目录和其他未跟踪文件。它们不属于本次 Draftpaper-loop 框架发布范围，必须通过显式 allowlist 暂存，禁止使用 `git add .`。

## 1. 文档定位

- 日期：2026-08-31
- 当前本地分支：`main`
- 当前本地与 `origin/main` 共同指针：`53569a5`
- 远端已发布版本：`v0.42.2 - Complete publication environment deployment`
- 远端 `v0.42.2` 标签解析到发布提交：`c0a3840d163f107cd5fecdf31cec4cada467e2d8`
- 当前 `main` 的 `53569a5` 是发布提交之后的环境测试隔离修正，不属于对 `v0.42.2` 标签的改写
- GitHub Release：<https://github.com/xiejhhhhhh/Draftpaper_loop/releases/tag/v0.42.2>
- 目标：在不覆盖 GitHub v0.42.2 既有内容、不丢失本地未提交框架改动的前提下，补齐可迁移部署环境，完成框架整合、验证、提交、推送和设备交接
- 方案性质：仓库级框架与部署方案，不修改任何论文项目的 `project.json`、passport、ledger、证据快照、确认 receipt、论文正文或 PDF

## 2. 核心结论

1. GitHub v0.42.2 已经正式发布，必须保持远端 tag、Release 和发布提交 `c0a3840` 不可变，后续不能覆盖或强推该版本。当前 `main` 已在该发布提交之后，所有新增功能都必须通过新的提交和新版本发布。
2. 本地未提交内容确实是 Draftpaper-loop 公共框架改动，不是某篇论文的项目特判，主要包括：
   - 科学证据注册表补强；
   - checkpoint 科学语义归一化与可读页修正；
   - 图表多格式去重和 claim/evidence 绑定稳定化；
   - 文献候选正式准入包、显式激活和教学 corpus 连续性；
   - 对应 CLI、命令注册表与测试。
3. 本地框架改动与 v0.42.2 环境部署改动只有 `draftpaper_cli/cli.py` 和 `draftpaper_cli/command_registry.py` 两处文件级重叠，当前工作树已经在 `main` 基线上保留了环境验收命令和文献准入命令；但它们尚未提交，必须通过 command contract、写集和回归测试后才能宣称整合完成。
4. v0.42.2 已覆盖 MiKTeX/TeX Live、XeLaTeX、pdfLaTeX、BibTeX、`kpsewhich`、系统 Git、Visual C++、环境 Doctor 和隔离编译验收，但仍未形成真正可交接的完整环境，至少还缺：
   - 新设备上的独立 Python 3.11 引导；
   - Python 支持范围与 full-text runtime 的一致性；
   - vendored paper-fetch 的 `imagesize` 和 PDF Markdown runtime；
   - 可选 publisher browser runtime；
   - 凭证变量模板和不泄密的配置检查；
   - 运行时约束文件与 fresh-clone 验收；
   - 对 vendored paper-fetch CLI 的真实导入 smoke，而不只是逐个模块存在性检查。
5. “把环境上传到 GitHub”不能理解为上传 `.venv`、MiKTeX、Python、CUDA 或本机二进制。正确交接物是：
   - 依赖声明和约束；
   - 安装/检查脚本；
   - 环境 schema 和 Doctor；
   - CI 与 clean-clone 验收；
   - 中英文操作手册；
   - wheel、校验和与 Release。
6. 由于本地还包含新增 CLI 与框架能力，最终整合版本建议为 `v0.43.0`。如果交接时间非常紧，只先发布环境补漏，则发布 `v0.42.3`，随后再将框架能力发布为 `v0.43.0`。

## 3. 当前真实状态

### 3.1 GitHub 已有内容

远端 `v0.42.2` 发布提交 `c0a3840` 已包含：

- `doctor --target control|research|publication|agent`；
- `verify-environment` 隔离验收；
- Windows `bootstrap_windows_environment.ps1`；
- Windows MiKTeX 25.12 当前用户安装路线；
- Visual C++ x64 runtime 与系统 Git 检查；
- XeLaTeX、pdfLaTeX、BibTeX 和 `kpsewhich` 双引擎验证；
- pypdf/PyMuPDF PDF 可读性验证；
- Linux/Windows publication smoke workflow；
- 中英文环境部署手册、schema、release manifest 和测试。

当前 `origin/main` 在发布 tag 之后还有提交 `53569a5`，用于隔离不同 CI 平台的环境检查。它属于当前主线的后续修正，不能把它误写成 `v0.42.2` 标签内容。本地已经同步了 `v0.42.2` tag；正式发布前仍应执行 `git fetch --tags origin` 并核验 tag 指向，不能仅凭本地分支名称判断标签状态。

### 3.2 已兼容回本地但尚未提交的框架改动

当前工作区约有 1,700 行框架代码和测试改动；其中原始改动在 `stash@{0}` 保留了一份恢复快照，当前工作树已经重新应用到 `main`/`53569a5` 基线上。它们仍是未提交改动，不能在验证前直接作为设备交接版本。

| 方向 | 主要文件 | 目标 |
|---|---|---|
| 证据注册表扩展 | `evidence_registry.py`、`result_evidence.py`、`run_evidence_bundle.py`、`methods/verification.py` | 从计数、指标、异常、阈值敏感性和图表绑定表中生成更完整的规范证据记录 |
| checkpoint 语义稳定 | `checkpoint_fingerprint.py`、`confirmation_continuity.py`、`checkpoint_brief.py`、`checkpoint_html.py` | 排除派生 ID、路径和格式投影造成的假科学变化，同时保留真实 cohort/method/claim/figure 变化 |
| 图表可读性与绑定 | `figure_claim_map.py`、`scientific_figure_quality.py`、`checkpoint_summary.py` | PNG/PDF 等同一科学图不重复占用确认页面，英文页具备可读 fallback，图表 claim/evidence 保持一致 |
| 研究计划与审阅包 | `human_review_packet.py`、`research_plan_brief.py`、`research_plan_confirmation_v42.py` | 加强审阅包语义、refs 和连续确认 |
| 文献正式准入 | 新增 `literature_admission.py`、`tests/test_literature_admission.py` | 候选文献必须逐条 `accept/exclude/defer`，门禁拒绝项需要显式 override 才能激活 |
| 文献 corpus 连续性 | `literature_teaching_corpus.py`、`literature_confirmation.py` | 派生索引重建不应作废科学上未变化的文献确认；成员、角色或 work identity 变化仍必须重确认 |
| CLI 与写集 | `cli.py`、`command_registry.py` | 同时保留 v0.42.2 的 `verify-environment` 和本地的 `prepare-literature-admission`、`activate-literature-corpus` |

### 3.3 已完成实现、尚待提交的环境补漏

以下改动已经写入本地工作树并通过当前设备的核心验收；在最终交接前仍必须完成分层暂存、提交、推送、CI 和 clean clone 验收：

- `pyproject.toml`：已限制 Python 上界，并补充 full-text/browser 依赖；
- `install_profiles.py`：已增加 full-text 真实依赖、browser 档位和 profile Python 范围；
- `environment_contract.py`：已增加 Python target 检查、可选工具与凭证配置状态；
- `environment_verification.py`：已增加 vendored paper-fetch runtime smoke；
- `bootstrap_windows_environment.ps1`：已增加独立 Python 3.11 检查和安装入口；
- `requirements/runtime-constraints.txt`、`config/environment.example`、双语环境文档、CI 和 wheel 验证工具：已加入工作树并完成一致性核对。

因此当前可以说“本地实现和核心环境验收已完成，等待形成公开提交”，不能说“v0.43.0 已发布”或“新设备已经验收通过”。

### 3.4 已完成的本机验证

以下结果以当前工作树和已验证的 Python 3.11 环境为准：

- 全量 pytest：`1351 passed, 2 skipped, 47 warnings, 26 subtests passed`；
- Ruff 高信号规则：通过；Pyright：`0 errors, 0 warnings, 0 informations`；
- Python compileall、command contract、schema registry、third-party provenance、secret-free handoff 检查：通过；
- release manifest：通过，当前版本 `0.43.0`、230 个 plugin、601 个 fixture、273 个 CLI command；
- wheel 隔离安装：通过，wheel 内资源、vendored paper-fetch 导入和五个跨学科 release regression 全部通过；
- wheel 安装矩阵：通过，minimal/plotting/fulltext/mcp/browser/mineru-agent 元数据边界正确；
- publication 环境 smoke：通过，包含 XeLaTeX、pdfLaTeX、BibTeX、`kpsewhich`、pypdf/PyMuPDF 双解析器和非空 PDF；
- 当前 publication Doctor 的 `attention` 仅表示 browser 可选 profile 尚未安装；不影响 core、research 或 publication 的已验证路径；
- 环境编译报告保存在 `.tmp/environment-publication-final/`，wheel 保存在 `.tmp/release-dist-verified/`；这两个目录仅用于本机验收，禁止上传。

### 3.5 v0.42.2 与本地改动的整合方式

本次不应把 `v0.42.2` 旧 tag 合并回 `main`，也不应把本地工作树直接覆盖到远端。正确关系是：`v0.42.2` 作为不可变发布基线，`53569a5` 作为其后的主线修正，本地框架和环境改动作为新的增量提交进入 `main`。

发布前先重新核对基线：

```powershell
git fetch origin main --tags
git rev-parse origin/main
git rev-parse v0.42.2^{commit}
git merge-base --is-ancestor v0.42.2 origin/main
git diff --stat v0.42.2..origin/main
```

最后一条祖先检查必须成功。若失败，先停止提交并分析远端分叉；不得用 `merge -s ours`、`reset --hard` 或 force-push 掩盖差异。祖先关系成立时，不需要额外创建“合并 v0.42.2”的提交，只需将当前工作树按环境、文献/CLI、证据语义和生成文档分层提交。

每次暂存前使用发布 allowlist，只允许本方案列出的源码、测试、配置模板、文档、CI 和生成合同进入提交；以下内容即使位于仓库目录内也必须排除：论文项目、PDF、真实数据、模型、日志、缓存、虚拟环境、系统安装包、私有商业材料、`.env` 和任何 token。

## 4. 本机环境与 v0.42.2 合同的差异

本机只用于发现缺口，不作为未来设备的可复现基线。审计结果应只记录能力状态，不把用户名、绝对路径或凭证提交到仓库。

| 能力 | 本机观察 | v0.42.2 合同 | 结论 |
|---|---|---|---|
| Python | 两套主要 venv 均为 3.11 | 文档称 3.10-3.12 全支持 | control 可支持 3.10；包含 vendored paper-fetch 的 research/publication/agent 应明确为 3.11-3.12 |
| Plotting | 一套环境完整，另一套缺失 | plotting extra 已声明 | 需要用 profile/fresh install 验证，不依赖某个旧 venv |
| Full text | `imagesize` 在一套环境缺失，`pymupdf4llm` 两套均缺失 | fulltext extra 未声明二者 | 确定性缺口；vendored paper-fetch 在缺少 `imagesize` 时连 CLI 导入都会失败 |
| MCP | 两套检查环境均未安装 | mcp extra 已声明 | 不是 core 缺陷，但 agent target 必须明确检查并提供安装命令 |
| Browser fetch | Playwright/CloakBrowser 未安装 | v0.42.2 明确排除，但没有正式 profile | 应成为可选 browser 档位，不进入默认安装 |
| TeX | XeLaTeX、pdfLaTeX、BibTeX、`kpsewhich` 可用 | 已覆盖 | 保留，并增加 clean-clone 验收 |
| Git/GitHub | 独立 Git 与 `gh` 可用 | Git 为 publication core，`gh` 仅 Doctor 侧可见 | Git 保持 core；`gh` 作为 optional enhancement，不应阻断论文编译 |
| VC++ | x64 runtime 可用 | 已覆盖 | 保留 |
| Node/Java | 本机可用 | 明确不默认安装 | 只用于可选公式/browser 路线，不升级为 core |
| Ghostscript/ImageMagick | 本机未发现 | 未列入 core | 当前 Draftpaper 正式编译链未直接依赖，不作为交接阻断项 |
| MinerU/CUDA | 未纳入默认本机合同 | 明确不默认安装 | 继续保持 endpoint/用户自建路线，不随核心环境部署 |

## 5. 目标环境分层

### 5.1 Control

用途：CLI、项目状态、schema、基础 BibTeX/PDF 检查。

要求：

- Python 3.10-3.12；
- core wheel 依赖；
- 不要求 TeX、MCP、浏览器、MinerU、GPU。

### 5.2 Research

用途：绘图、统计、本地全文解析、vendored paper-fetch 和科研插件。

要求：

- Python 3.11-3.12；
- `plotting` + `fulltext`；
- `fulltext` 必须能真实导入 vendored paper-fetch CLI；
- `imagesize`、PyMuPDF、`pymupdf4llm` 和 metadata/full-text 依赖完整。

### 5.3 Publication

用途：完整论文生产和 PDF 交付。

要求：

- Research 全部能力；
- 独立系统 Git；
- Windows 使用当前用户 MiKTeX，Linux/macOS 使用 TeX Live 或等价发行版；
- XeLaTeX、pdfLaTeX、BibTeX、`kpsewhich`；
- 真实双引擎编译、引用收敛和 PDF 双解析器检查。

### 5.4 Agent

用途：Codex/Claude Code/MCP 工作流。

要求：

- Python 3.11-3.12；
- Research + MCP；
- source checkout 下独立 Git 为 core；
- `gh` 为推荐可选项；
- workflow Skill 与 package resource 版本一致。

### 5.5 Browser Enhancement

用途：只有在出版社网页确实需要浏览器回退时启用。

要求：

- Python 3.11-3.12；
- `browser` extra；
- Playwright/CloakBrowser Python runtime；
- 显式安装所需浏览器资产；
- 不进入默认 research/publication，避免体积和下载压力。

### 5.6 Optional Integrations

只检查“是否配置”，绝不记录值：

- Zotero：`ZOTERO_LIBRARY_ID`、`ZOTERO_API_KEY`、可选 `ZOTERO_LIBRARY_TYPE`；
- NASA ADS：`NASA_ADS_API_TOKEN`；
- Semantic Scholar：`SEMANTIC_SCHOLAR_API_KEY`；
- GitHub：`GITHUB_TOKEN` / `GH_TOKEN` 或 `gh` 登录态；
- Crossref/OpenAlex polite pool：`CROSSREF_MAILTO`、`OPENALEX_MAILTO`；
- MinerU：`DRAFTPAPER_MINERU_ENDPOINT`、`MINERU_AGENT_ENDPOINT` 或 `MINERU_EXECUTABLE`。

## 6. 环境补齐实施范围

### P0：交接前必须完成

1. Windows bootstrap 增加独立 Python 3.11 检查和 WinGet 当前用户安装路线。
2. 文档顺序改为“先检查/安装 Python 与系统组件，再创建 venv”，确保真正空白设备可以开始。
3. `pyproject.toml` 与文档统一：
   - package 支持范围 `>=3.10,<3.13`；
   - control/plotting 支持 3.10-3.12；
   - fulltext/research/publication/agent 支持 3.11-3.12。
4. fulltext extra 增加并约束：
   - `imagesize`；
   - `pymupdf4llm`；
   - `typing-extensions`；
   - 与 vendored paper-fetch 2.x 兼容的 BeautifulSoup、cachetools、filelock、lxml、PyMuPDF、Pydantic 等版本范围。
5. 新增 `browser` extra，但不加入默认 research/publication。
6. Doctor 和 `verify-environment` 增加：
   - Python target 兼容性；
   - vendored paper-fetch CLI 真实导入；
   - 可选工具与 integration 是否配置；
   - 仅输出布尔状态和变量名，不输出凭证值。
7. 增加无秘密值的环境变量模板，例如 `config/environment.example`；不使用带真实值的 `.env`。
8. 增加受支持运行时约束文件，例如 `requirements/runtime-constraints.txt`，用于 CI 和交接安装，避免同一天安装得到不兼容的大版本组合。
9. 更新环境 schema、release manifest、wheel install matrix 和中英文文档。
10. 在 fresh venv 中分别验证 minimal、plotting、fulltext、mcp 和 browser。

### P1：建议在同一版本完成

1. Linux 提供明确的 apt 路线和检测命令。
2. macOS 提供 Homebrew/MacTeX 路线和 control/research smoke；若 publication CI 成本过高，文档必须明确未在 CI 中自动安装完整 MacTeX。
3. GitHub Actions 的 fulltext profile 不只运行 Doctor，还必须导入 vendored paper-fetch CLI。
4. 将环境验收 JSON/HTML 作为 CI artifact 保存，便于新设备失败时下载诊断。
5. 增加 clean-clone source install 和 isolated wheel 两种验收，防止 editable install 隐藏漏打包文件。

### 明确不默认部署

- 自建 MinerU 模型、CUDA、GPU driver；
- Node.js、Java 和公式转换器；
- 浏览器二进制；
- 学科专用深度学习框架；
- API key、token 和 Zotero 私密配置；
- 项目数据、模型、PDF 文献库和论文产物。

这些能力可以提供 profile、接口、检查和部署说明，但不能静默进入 core。

## 7. 本地框架改动整合要求

### 7.1 文献正式准入必须形成完整闭环

必须同时完成：

1. `prepare-literature-admission` 生成 hash-bound 候选包；
2. 每篇候选必须显式 `accept`、`exclude` 或 `defer`；
3. 门禁拒绝项只有在提供明确 reason 和 `gate_override=true` 时才能 accept；
4. `activate-literature-corpus` 只写入被明确接受且具有 canonical work identity 和项目角色的文献；
5. activation receipt 与 packet hash、decision hash、source binding 绑定；
6. activation 之后仍必须经过 coverage review 和 corpus confirmation；
7. excluded/deferred 文献不得进入 active snapshot、教学 corpus 或 Agent 默认上下文；
8. CLI reference、Skill、风险矩阵和写集合同同步。

### 7.2 文献确认连续性不能放宽科学边界

允许 continuity 的情况：

- 仅索引 HTML 重建；
- `library.bib` 派生投影重建；
- registry snapshot marker 或生成时间变化；
- accepted citation keys、usage roles、active source 和 canonical work identities 均未变化。

必须重新确认的情况：

- 文献成员变化；
- citation key 与 work identity 映射变化；
- 项目角色或 usage plan 变化；
- active source 或来源 hash 变化；
- 无法证明只是派生投影变化。

### 7.3 checkpoint 语义归一化必须双向测试

不得触发新 C3：

- fact ID、snapshot ID 或派生路径重建；
- 同一图表 PNG/PDF 格式投影；
- HTML、英文 fallback、时间戳或排序变化。

必须触发新 C3：

- cohort、split、metric、method、threshold 或 uncertainty 变化；
- figure panel/claim 绑定变化；
- claim 边界扩张或收窄；
- canonical evidence value 或 denominator 变化；
- 无法分类的 unknown drift。

### 7.4 证据注册表扩展必须保持跨项目通用

- 不写入具体论文名称、图号、样本数或领域特判；
- 以 schema、列名、metric/count identity 和 figure binding 驱动；
- 缺少 model/cohort/split/denominator 时阻断或降级，不猜测；
- 新证据记录必须具备来源路径、selector、hash 和适用 claim；
- 旧证据 schema 保持只读兼容。

## 8. 推荐执行顺序

### M0：冻结与备份

当前已完成：

- 本地 `main` 与 `origin/main` 均指向 `53569a5`；
- 已通过远端 refs 核验 `v0.42.2` 存在且指向发布提交 `c0a3840`；
- 当前工作树中的本地框架改动已基于主线重新应用；
- `stash@{0}` 保留整合前恢复快照；
- 未跟踪的商业文档、项目资料、临时目录和 `uv.lock` 未被纳入 stash 或远端提交。

后续要求：

- 不删除 `stash@{0}`，直到 GitHub push、CI 和 clean-clone 验收全部通过；
- 不使用 `git add .`；
- 不提交无关未跟踪文件；
- 每次提交前使用显式 allowlist。

### M1：完成环境补漏

1. 完成当前五个半成品环境文件；
2. 添加环境变量模板、runtime constraints 和 browser profile；
3. 补齐环境 schema、Doctor、verification、Windows bootstrap；
4. 更新中英文环境和安装文档；
5. 增加 fulltext runtime、Python range、browser 和凭证脱敏测试；
6. 先运行环境定向测试，不混入框架功能提交。

### M2：完成本地框架改动

1. 核对新增 literature admission schema 是否需要注册；
2. 为新 CLI 增加 command contract、risk policy、Skill 和 CLI reference；
3. 补足 evidence registry 新 extractor 的专门测试；
4. 建立 semantic continuity 正例与反例矩阵；
5. 运行真实项目只读 shadow，确保不修改项目状态；
6. 修复所有 lint、schema、write-set 和 release contract 问题。

### M3：生成文件与版本同步

按仓库工具生成，不手工只改副本：

```powershell
python tools/sync_workflow_skill_copies.py --root C:\Draftpaper_commercial --write
python tools/generate_cli_reference.py --output docs\cli_reference.md
python tools/generate_product_docs.py --risk-output docs\command_risk_matrix.md
python -m draftpaper_cli.release_contract --root C:\Draftpaper_commercial --write
```

同步范围：

- canonical workflow Skill；
- Codex Skill；
- Claude Code Skill；
- wheel 内 resource；
- CLI reference；
- command risk matrix；
- schema registry；
- release manifest；
- README 中英文。

### M4：验证矩阵

#### 静态和合同验证

- `git diff --check`；
- Ruff；
- Python compileall；
- command contracts；
- protected-action policy；
- schema registry；
- release manifest；
- Skill copy parity；
- secret scan；
- package data/wheel resource 验证。

#### 单元与回归

- 全量 pytest；
- literature admission 正反例；
- teaching corpus 派生重建 continuity；
- checkpoint scientific fingerprint mutation matrix；
- evidence registry 新来源解析；
- v0.42.2 environment contract 原有测试全部保留。

#### 安装档位

| 档位 | Python | 验收 |
|---|---|---|
| minimal/control | 3.10、3.11、3.12 | core imports、CLI、schema |
| plotting | 3.10、3.11、3.12 | NumPy/pandas/Matplotlib/SciencePlots/OCR import 与最小绘图 |
| fulltext/research | 3.11、3.12 | vendored paper-fetch CLI、PyMuPDF、pymupdf4llm、imagesize、本地 PDF parse |
| mcp/agent | 3.11、3.12 | MCP import、stdio smoke、Skill identity |
| browser | 3.11、3.12 | Python runtime import；浏览器资产下载保持显式步骤 |
| publication | 3.11、3.12 | 双引擎 LaTeX/BibTeX、引用收敛、PDF 双解析器 |

#### 设备交接验收

必须在当前工作目录之外做一次 clean clone：

1. 从 GitHub 克隆目标 tag；
2. 运行 Windows `-Mode Check`；
3. 必要时运行 `-Mode InstallCore`；
4. 新建 Python 3.11 venv；
5. 从源码安装 `[plotting,fulltext]`，若需要 Agent/MCP 再额外安装 `[mcp]`；
6. 从构建 wheel 再做一次独立安装；
7. 运行 publication Doctor；
8. 运行 `verify-environment --compile-latex`；
9. 在临时 Draftpaper 项目中通过正式 compile 入口生成 PDF；
10. 比较验证前后项目保护状态 hash，必须无变化。

### M5：提交分层

严禁把约 30 个文件一次性混成无法审计的大提交。建议顺序：

1. `fix(env): complete reproducible workstation bootstrap`
   - Python bootstrap；
   - fulltext/browser 依赖；
   - environment contract/verification；
   - constraints、schema、tests、docs。
2. `feat(literature): add explicit corpus admission gate`
   - literature admission 模块；
   - CLI/registry；
   - corpus continuity；
   - tests。
3. `fix(evidence): stabilize checkpoint and evidence semantics`
   - evidence registry；
   - checkpoint/figure semantics；
   - research-plan/brief continuity；
   - tests。
4. `docs(release): synchronize v0.43.0 contracts and handoff guidance`
   - README；
   - generated docs；
   - Skill copies；
   - release manifest。

每次提交前：

```powershell
git diff --cached --check
git diff --cached --name-status
git diff --cached --stat
```

### M6：版本与发布

由于 v0.42.2 已发布：

- 不移动或删除 `v0.42.2`；
- 不 force-push；
- 不把本地新增功能塞进旧 tag；
- 完整整合版本使用 `v0.43.0`；
- 如果必须先交付环境补漏，可先发 `v0.42.3`，但 v0.43.0 仍需单独发布框架能力。

Release 必须包含：

- tag 与 commit SHA；
- wheel；
- wheel SHA-256；
- 环境支持矩阵；
- Windows bootstrap 命令；
- clean-clone 验收结果；
- 已知可选能力边界；
- 从 v0.42.2 升级说明。

## 9. 新设备标准恢复手册

### 9.1 系统环境

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\tools\bootstrap_windows_environment.ps1 -Mode Check
.\tools\bootstrap_windows_environment.ps1 -Mode InstallCore
```

重新打开 PowerShell 后再次执行 `-Mode Check`。

### 9.2 Python 环境

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -c requirements\runtime-constraints.txt -e ".[plotting,fulltext]"
```

需要 publisher browser 回退时单独执行：

```powershell
.\.venv\Scripts\python -m pip install -c requirements\runtime-constraints.txt -e ".[browser]"
.\.venv\Scripts\python -m playwright install chromium
```

### 9.3 环境验收

```powershell
.\.venv\Scripts\python -m draftpaper_cli doctor --target publication --json
.\.venv\Scripts\python -m draftpaper_cli verify-environment `
  --target publication `
  --compile-latex `
  --output .tmp\environment-verification
```

### 9.4 可选凭证

- 只从 `config/environment.example` 复制变量名；
- 真实值放在新设备用户级环境变量或未跟踪的私有配置中；
- 不把 `.env`、token、API key、Zotero 凭证或 private endpoint 上传 GitHub；
- Doctor 只显示 `configured/not_configured`。

## 10. 安全与仓库边界

### 可以上传 GitHub

- `pyproject.toml`；
- runtime constraints；
- bootstrap/check scripts；
- schema；
- CI workflow；
- `.example` 配置；
- README/环境手册；
- wheel 构建配置；
- fixtures 和 tests；
- release manifest 与 checksums。

### 禁止上传 GitHub

- `.venv`；
- Python、MiKTeX、Git、浏览器、CUDA 二进制；
- TeX package cache；
- Playwright browser cache；
- API key、token、cookies；
- Zotero 私密库信息；
- 用户目录绝对路径；
- 本地验收 receipt；
- 真实项目数据、模型、日志、PDF 和论文产物；
- 商业私有实现和许可证签发材料。

## 11. 回滚与恢复

1. 在最终 push 前，`stash@{0}` 是本地框架改动的恢复副本，不得删除。
2. 环境、文献准入和证据语义使用独立 commit，任何一层都可以单独 revert。
3. v0.42.2 tag 永远保留为已验证环境基线。
4. 如果框架测试失败，可先只发布环境补丁 v0.42.3，不强行捆绑 v0.43.0。
5. 如果 clean clone 无法恢复，发布必须阻断；不能因为当前设备已有历史包就宣称环境完整。
6. 只有以下条件都满足后，才删除保留 stash：
   - 本地 commits 可见；
   - 远端 main 可见；
   - Release/tag 可见；
   - CI 全绿；
   - clean clone 验收通过；
   - stash 与已提交框架能力的差异已人工核对。

## 12. Definition of Done

只有以下条件全部满足，设备交接和框架整合才算完成：

1. 本地 `main` 以 GitHub v0.42.2 为祖先，没有覆盖或改写远端历史；
2. v0.42.2 tag 和 Release 保持不可变；
3. 本地全部框架级改动已分类、补测并以独立 commit 提交；
4. `verify-environment`、`prepare-literature-admission` 和 `activate-literature-corpus` 同时存在且 command contract 通过；
5. 文献准入、教学 corpus 确认与 checkpoint continuity 的边界测试全部通过；
6. Windows 空白设备可以从 Check 开始安装独立 Python 3.11、VC++、Git 和 MiKTeX；
7. `pyproject.toml`、Doctor、文档和 CI 对 Python 支持范围表达一致；
8. fresh fulltext 安装能够导入 vendored paper-fetch CLI，不再依赖历史环境中偶然存在的 `imagesize`；
9. PDF fallback 所需 PyMuPDF/pymupdf4llm 被安装和验证；
10. browser runtime 是明确可选档位，不进入默认 core；
11. MCP、Zotero、NASA ADS、GitHub、MinerU 等可选能力有不泄密的配置检查和恢复说明；
12. runtime constraints、bootstrap、schema、CI、双语文档和配置模板全部已上传 GitHub；
13. `.venv`、二进制、缓存、凭证、绝对路径和真实论文资料没有进入提交；
14. minimal、plotting、fulltext、mcp、browser、publication 安装矩阵通过；
15. 全量 pytest、Ruff、compileall、schema、command、risk、Skill、release 和 wheel 验证通过；
16. Windows/Linux CI 通过，macOS control/research smoke 通过；
17. 当前目录之外的 clean clone 能从文档独立恢复并生成有效测试 PDF；
18. wheel 与目标 tag 一致，Release 提供 SHA-256 和环境支持矩阵；
19. 远端 `main` 包含所有交接所需的可复现定义；
20. 只有在上述远端证据可核验后，才交接设备并删除本地恢复 stash。

## 13. 最终发布建议

推荐采用一条发布线：

```text
v0.42.2（已发布、不可变环境基线）
    -> 环境补漏 commit
    -> 文献正式准入 commit
    -> 证据/checkpoint 语义稳定 commit
    -> 文档与生成合同同步 commit
    -> v0.43.0（设备交接与框架整合版）
```

这样既保留 v0.42.2 的清晰历史，又能确保即使当前设备不再可用，后续设备仍可只依赖 GitHub、Release 和部署手册恢复完整的 Draftpaper-loop 科研与论文生产环境。
