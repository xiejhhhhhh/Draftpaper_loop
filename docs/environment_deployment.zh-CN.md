# Draftpaper-loop 环境部署

本手册定义完整的本地论文生产与编译环境。Python 安装档位只是其中一层，不会安装 TeX 发行版、Visual C++ 运行库或系统 Git。

## 支持的目标

| 目标 | 用途 | 核心检查 |
|---|---|---|
| `control` | CLI、项目状态和配置 | Python 包及控制面导入 |
| `research` | 文献、数据、方法和证据工作 | `control` 加绘图和全文导入 |
| `publication` | 完整论文生产 | `research` 加 XeLaTeX、pdfLaTeX、BibTeX、`kpsewhich`；源码 checkout 还需系统 Git |
| `agent` | Agent/MCP 操作 | 所选目标加 MCP bridge 和 workflow Skill |

`control` 和 `research` 不代表能够编译 PDF。开始最终论文运行前，应使用 `publication` 目标完成检查。

浏览器抓取是可选增强档位，不是新的核心目标；需要时在已完成 `research` 安装的 Python 3.11/3.12 环境中额外安装 `browser`，并显式安装 Playwright 浏览器资产。

## Windows 标准路线

推荐的默认组合是：当前用户私有安装 MiKTeX 25.12、系统 Git for Windows 和 Microsoft Visual C++ x64 运行库。如果系统有 `uv`，引导脚本会优先使用可观察的 `uv python install 3.11` 路线安装 Python；否则回退到官方 winget 安装包。不要求为 MiKTeX 使用管理员权限，也不会安装 MinerU、CUDA、Node.js、Java 或学科库。

### 1. 创建 Python 环境

在源码 checkout 中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -c requirements\runtime-constraints.txt -e ".[plotting,fulltext]"
```

`control/minimal` 和 `plotting` 支持 Python 3.10、3.11、3.12；`fulltext`、`research`、`publication`、`agent` 和 `browser` 支持 Python 3.11、3.12，因为 vendored paper-fetch 与 PDF Markdown 运行时从 Python 3.11 起支持。`fulltext` 会安装 `imagesize`、PyMuPDF 和 `pymupdf4llm`，并由验收命令真实导入 vendored paper-fetch CLI。MinerU 仍是可选的外部 endpoint 或 Agent connector，不属于核心安装。

交接或重新部署时应始终使用 `requirements/runtime-constraints.txt`；它提供跨平台的兼容范围，防止同一份源码在不同日期解析出不兼容的大版本组合。可选 provider 的变量名见 `config/environment.example`，真实凭证只能放在用户级环境变量或本机私有配置中。

### 2. 检查并安装系统前置环境

先执行只读检查：

```powershell
.\tools\bootstrap_windows_environment.ps1 -Mode Check
```

显式的核心安装命令只允许请求 WinGet 安装以下组件：

```powershell
.\tools\bootstrap_windows_environment.ps1 -Mode InstallCore
```

它检查或安装：

- Microsoft Visual C++ 2015+ x64 运行库，供 PyMuPDF 等原生 Python wheel 使用；
- 普通系统或当前用户安装的 Git for Windows，而不是 Codex 私有 runtime 中的 Git；
- 私有/当前用户范围的 MiKTeX 25.12。

安装后重新打开 PowerShell，再执行一次 `-Mode Check`。该脚本不是通用工作站安装器；可选的 `gh`、Node.js、Java、MinerU、CUDA 和学科依赖应按项目需要单独部署。

### 3. 配置 MiKTeX

MiKTeX Basic 是精简的 TeX 安装。允许自动安装缺失宏包并刷新文件名数据库：

```powershell
initexmf --set-config-value=[MPM]AutoInstall=yes
initexmf --update-fndb
```

第一次真实编译可能下载缺失的 TeX 宏包。这是明确的联网边界：Basic MiKTeX 加自动补包不能宣称为完全离线复现环境。离线环境应在联网机器预热所需宏包，或自行维护 TeX Live/MiKTeX 镜像。

### 4. 运行确定性诊断

`doctor` 是只读的，不会安装宏包或改写项目：

```powershell
.\.venv\Scripts\python -m draftpaper_cli doctor --target publication --json
```

报告会区分模块缺失、原生 DLL 导入失败、TeX 可执行文件缺失、工具来源错误和 TeX 资源缺失。来自 Codex 私有 runtime 的 Git 不能满足源码 checkout 的 publication 要求。

### 5. 运行完整隔离验收

显式验收命令只写入用户指定的输出目录。它会真实读取 PDF，并运行 XeLaTeX、pdfLaTeX、BibTeX 以及 `kpsewhich plainnat.bst`：

```powershell
.\.venv\Scripts\python -m draftpaper_cli verify-environment `
  --target publication `
  --compile-latex `
  --output .tmp\environment-verification
```

输出包括：

- `environment_verification.json`：机器可读回执；
- `environment_verification.zh-CN.html` 和 `environment_verification.en.html`：可读报告；
- `artifacts/` 下隔离生成的 XeLaTeX、pdfLaTeX PDF 和编译日志。

如果核心组件缺失、PDF 为空或不可读、TeX 运行出现致命错误，或最后一轮仍存在未解析引用，命令会失败。第一次 TeX 运行产生的普通 warning 不会被误当作最终证据；系统会在 BibTeX 和重复编译之后检查最后一轮结果。

### 6. 通过 Draftpaper 编译

独立 fixture 只能验收工具链。还必须在临时项目中通过 Draftpaper 正式的 LaTeX assemble/compile 入口完成一次 smoke test。不要在真实论文目录运行环境验收；临时项目输出应置于 Git 之外，并比较编译前后的受保护项目状态哈希。

## 跨平台替代路线

Ubuntu 或 Debian 可以通过系统包管理器安装 TeX，例如 `texlive-xetex`、`texlive-latex-extra` 和 `texlive-bibtex-extra`，再安装 Draftpaper 并执行同一个 `verify-environment` 命令。Linux 和 macOS 支持 TeX Live；MiKTeX 25.12 私有安装是 Windows 默认路线，不是其他平台的硬性要求。

`publication` 合同要求源码 checkout 使用可独立发现的系统 Git。wheel 安装在 `control` 或 `research` 目标下可以不依赖 Git，但本地 LaTeX 编译仍然需要四个 TeX 工具。

## 故障排查

| 发现 | 含义 | 恢复方式 |
|---|---|---|
| Python 模块 `missing` | 当前档位没有安装 | 安装 Doctor 建议的档位 |
| 带 DLL 信息的 `import_failed` | 原生扩展无法加载 | 修复 Visual C++ x64 并重装对应 wheel |
| 缺少 `xelatex`/`pdflatex`/`bibtex` | publication 工具链不完整 | 安装 MiKTeX 或 TeX Live，并重新打开 shell |
| `kpsewhich plainnat.bst` 为空 | 找不到参考文献资源 | 刷新文件名数据库并安装对应宏包 |
| Git 来自 Codex runtime | 源码 checkout 未使用独立系统 Git | 安装 Git for Windows，检查 `where.exe git` |
| 第一次编译要求安装宏包 | MiKTeX 正常按需补包 | 允许补包，或为离线运行预热宏包 |
| vendored paper-fetch 导入失败 | `fulltext/research` 依赖不完整或 Python 版本不符合 | 使用 Python 3.11/3.12，按约束文件重新安装 `fulltext`，再运行 `verify-environment` |
| MinerU 不可用 | 可选增强 PDF 路径未配置 | 继续使用 pypdf/PyMuPDF，或配置用户自建 MinerU endpoint |

## 不应提交的内容

不要提交 `.venv`、MiKTeX 或 Git 二进制、下载的 TeX 宏包、本机验收回执、项目数据、API key、token、用户目录绝对路径或真实论文产物。仓库只保留环境合同、schema、测试、文档和部署脚本。
