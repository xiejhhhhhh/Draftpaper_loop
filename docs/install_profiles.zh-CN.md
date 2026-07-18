# Draftpaper-loop 安装档位

Draftpaper-loop 将工作流控制面与可选科研运行环境分开。只安装当前任务需要的档位，然后用 `draftpaper doctor --json` 检查当前 Python 环境。

| 档位 | 命令 | 能力边界 |
|---|---|---|
| Minimal | `python -m pip install draftpaper-cli` | 工作流控制、参考文献、PDF 检查、打包 schema/插件和内置 paper-fetch fallback |
| Plotting | `python -m pip install "draftpaper-cli[plotting]"` | NumPy/pandas 科研插件运行、Matplotlib/SciencePlots 图表、SciPy、seaborn 和 scikit-learn |
| Full text | `python -m pip install "draftpaper-cli[fulltext]"` | 增强 PDF 解析、网页正文抽取和 metadata 规范化；未安装该 extra 时仍保留内置 paper-fetch fallback |
| MCP | `python -m pip install "draftpaper-cli[mcp]"` | 本地 stdio MCP 服务和类型化 MCP transport |
| 科研工作站 | `python -m pip install "draftpaper-cli[plotting,fulltext,mcp]"` | 合并的本地科研环境 |

源码 editable 安装时，用 `-e .` 替代 `draftpaper-cli`：

```powershell
python -m pip install -e ".[plotting,fulltext,mcp]"
draftpaper doctor --json
```

Doctor 报告的 `environment.install_profiles` 会列出每个档位需要和缺失的模块、能力、准确恢复命令及可用 fallback。缺少可选档位不会让 minimal 控制面失效，但在真正执行对应科研能力前必须完成安装，不能把缺失能力报告为可用。

发布 CI 会分别验证 minimal、plotting、fulltext 和 MCP 四个独立环境，并通过 `tools/verify_install_matrix.py` 检查 wheel metadata，防止重量级绘图包再次静默进入默认依赖。
