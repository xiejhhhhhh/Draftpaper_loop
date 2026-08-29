# Draftpaper-loop 安装档位

Draftpaper-loop 将工作流控制面与可选科研运行环境分开。只安装当前任务需要的档位，然后用 `draftpaper doctor --json` 检查当前 Python 环境。

| 档位 | 命令 | 能力边界 |
|---|---|---|
| Minimal | `python -m pip install draftpaper-cli` | 工作流控制、参考文献、PDF 检查、打包 schema/插件和内置 paper-fetch fallback |
| Plotting | `python -m pip install "draftpaper-cli[plotting]"` | NumPy/pandas 科研插件运行、Matplotlib/SciencePlots 图表、SciPy、seaborn、scikit-learn 和输出图表的 OCR 质量检查 |
| Full text | `python -m pip install "draftpaper-cli[fulltext]"` | 增强 PDF 解析、网页正文抽取和 metadata 规范化；未安装该 extra 时仍保留内置 paper-fetch fallback |
| MinerU Agent | `python -m pip install "draftpaper-cli[mineru-agent]"` | 兼容性档位；官方 Agent connector 已在 core 中，该档位不安装本地模型或 GPU 运行时 |
| MCP | `python -m pip install "draftpaper-cli[mcp]"` | 本地 stdio MCP 服务和类型化 MCP transport |
| 科研工作站 | `python -m pip install "draftpaper-cli[plotting,fulltext,mcp]"` | 合并的本地科研环境 |

源码 editable 安装时，用 `-e .` 替代 `draftpaper-cli`：

```powershell
python -m pip install -e ".[plotting,fulltext,mcp]"
draftpaper doctor --json
```

Doctor 报告的 `environment.install_profiles` 会列出每个档位需要和缺失的模块、能力、准确恢复命令及可用 fallback。缺少可选档位不会让 minimal 控制面失效，但在真正执行对应科研能力前必须完成安装，不能把缺失能力报告为可用。

Python 档位不等于完整的论文生产环境。本地编译最终稿还需要可用的 TeX 发行版及 `xelatex`、`pdflatex`、`bibtex`、`kpsewhich`；源码 checkout 还需要可独立发现的系统 Git。Windows 的 MiKTeX 25.12 私有安装、Visual C++ x64 运行库、只读诊断和隔离编译验收见[完整环境部署手册](environment_deployment.zh-CN.md)。

发布 CI 会分别验证 minimal、plotting、fulltext 和 MCP 独立环境。`mineru-agent` 是不增加依赖的 connector 档位。通过 `tools/verify_install_matrix.py` 检查 wheel metadata，防止重量级绘图或 GPU 包静默进入默认依赖。自建 MinerU 属于用户自行维护的外部 endpoint，不是安装档位。
