# Windows 全局安装与新会话验证

本指南使用 editable mode 安装源码 checkout，使 `draftpaper` 能在新的 Windows 终端中通过 `PATH` 直接调用；同时安装仓库内置的 Codex workflow skill，使新建 Codex 任务能够发现与当前软件版本一致的工作流合同。

## 验收目标

- 在仓库目录之外启动新进程，仍能解析并运行 `draftpaper`。
- Python 导入指向预期的源码 checkout。
- 真实论文项目常用的 plotting 档位可用。
- 已安装 Codex workflow skill 的版本和哈希与 Python 包一致。
- 可以通过全局命令创建、校验并读取一个测试项目。

editable install 持续依赖源码 checkout。请把仓库保留在稳定路径；如果移动仓库，必须从新路径重新执行安装。

## 1. 检查前置条件

Draftpaper-loop 需要 Python 3.10 或更高版本以及 Git。在 PowerShell 中运行：

```powershell
python --version
python -c "import sys; print(sys.executable)"
git --version
```

## 2. 克隆到稳定路径并安装

以下示例使用 `D:\Draftpaper_loop`：

```powershell
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git D:\Draftpaper_loop
Set-Location D:\Draftpaper_loop
python -m pip install -U pip
python -m pip install -e ".[plotting]"
```

如果仓库已经存在，用 fast-forward 方式更新，不改写本地历史：

```powershell
Set-Location D:\Draftpaper_loop
git pull --ff-only origin main
python -m pip install -e ".[plotting]"
```

安装会在当前 Python 解释器的 Scripts 目录中创建 `draftpaper` 启动器。检查已安装的 distribution 和命令位置：

```powershell
python -m pip show draftpaper-cli
where.exe draftpaper
```

## 3. 安装 Codex workflow skill

安装与当前软件包版本一致的内置 skill：

```powershell
draftpaper install-skill --destination "$HOME\.codex\skills\draftpaper-workflow" --force
draftpaper doctor --json
```

Doctor JSON 中的 `environment.workflow_skill.status` 应为 `passed`。安装完成后新建一个 Codex 任务，使 skill discovery 从更新后的目录启动。

`doctor` 仍可能报告 `fulltext` 等可选档位缺失。这不会使 minimal 控制面或已安装的 plotting 档位失效。仅在确实需要相应能力时安装可选档位，例如：

```powershell
Set-Location D:\Draftpaper_loop
python -m pip install -e ".[plotting,fulltext]"
```

## 4. 在仓库外的新进程中验证

在 `%TEMP%` 中启动无 profile 的新进程，解析可执行文件并运行 Doctor：

```powershell
cmd.exe /d /c "cd /d %TEMP% && where draftpaper && draftpaper doctor --json"
```

这可以证明成功调用不依赖“当前目录恰好是源码仓库”，也不依赖 PowerShell profile。

## 5. 创建并校验测试项目

建议把论文项目和研究数据保存在源码仓库之外。当 `--root` 指向配置项目根目录以外的位置时，必须用 `--allow-external-project-root` 明确确认该边界。当前版本会在目录名后追加稳定的短 project ID，因此应从 JSON 输出读取真实 `project_path`，不要自行猜测目录名。

```powershell
$ProjectsRoot = "D:\Draftpaper_projects"

$Created = draftpaper create-project `
  --root $ProjectsRoot `
  --allow-external-project-root `
  --idea "Global install smoke test" `
  --field "workflow validation" `
  --target-journal MNRAS | ConvertFrom-Json

$Project = $Created.project_path
draftpaper validate-project --project $Project
draftpaper status --project $Project
```

验收标准：

- `create-project` 返回 `status: created` 和具体的 `project_path`。
- `validate-project` 返回 `status: passed`、`error_count: 0`、`warning_count: 0`。
- `status` 返回 `pipeline_state: ready` 和结构化 `next_action`。

后续应跟随系统返回的 next action，而不是写死阶段顺序：

```powershell
draftpaper run-pipeline --project $Project
draftpaper status --project $Project
```

## 6. 运行仓库完整测试

开发或提交改动前，从源码 checkout 安装开发档位并运行完整测试：

```powershell
Set-Location D:\Draftpaper_loop
python -m pip install -e ".[dev,plotting]"
python -m pytest -q
```

完整套件包含 subprocess、LaTeX/PDF、wheel、合同和科研流程回归，在 Windows 上可能明显慢于普通小型单元测试。

## 常见问题

### 系统提示无法识别 `draftpaper`

查找启动器目录：

```powershell
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

通过 Windows“环境变量”把输出目录加入当前用户的 `PATH`，重新打开终端，再运行 `where.exe draftpaper`。不要手工复制启动器，也不要因此更换系统 Python。

### Python 导入指向了另一个 checkout

运行：

```powershell
draftpaper doctor --json
```

检查 `environment.runtime_source`。如果路径已经过期，请在目标 checkout 中重新执行 `python -m pip install -e ".[plotting]"`。

### 仓库被移动到新路径

editable install 保存了源码 checkout 的链接。移动后应从新位置重装并刷新 skill：

```powershell
Set-Location <new-repository-path>
python -m pip install -e ".[plotting]"
draftpaper install-skill --destination "$HOME\.codex\skills\draftpaper-workflow" --force
draftpaper doctor --json
```

### 卸载命令

```powershell
python -m pip uninstall draftpaper-cli
```

卸载 Python distribution 不会删除源码 checkout 或已生成的论文项目。
