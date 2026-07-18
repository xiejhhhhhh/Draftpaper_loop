# Draftpaper-loop

**本地优先、证据优先的科研论文工作流：先确认研究蓝图与关键结果，再自由撰写、审查并发布可追溯的 `main.pdf`。**

[English](README.md) | [安装档位](docs/install_profiles.zh-CN.md) | [CLI 命令参考](docs/cli_reference.md) | [最终论文补全](docs/manuscript_completion.zh-CN.md)

Draftpaper-loop 不是一次性论文生成器。它把文献、研究计划、真实数据与方法执行、关键图表、Results、其余章节、引用核查、学科审查、独立审稿和最终 PDF 组织为可恢复的科研 loop。Codex 保留科学推理和自然行文的自由；确定性合同负责保护证据版本、cohort、run、图表语义、公式、参考文献、插件来源、stale 状态和最终发布身份。

## 当前版本

当前版本为 **v0.31.9**。公开 CLI 的 210 个命令统一进入 `CommandSpec` 控制面，仓库包含 210 个学科插件合同和五类跨学科发布 fixture。Fixture 只能证明通用流程行为，不能冒充科研结论。真实论文仍必须使用 live-runnable 插件或经过审计的 project-local 实现，产生可验证的运行输出，并由用户确认研究蓝图、核心证据和最终 release hash。

## 论文如何到达 `main.pdf`

```text
idea 与参考文献
  -> 中英文研究蓝图与可行性人工确认
  -> 学科识别和数据/方法能力匹配
  -> 真实数据处理、方法执行和 run manifest
  -> 主图组与必要附录图
  -> 结果支撑检查点与最大论断强度选择
  -> Results 和中文结果总结
  -> Introduction、Data、Methods、Discussion
  -> 学科规则审查与语义修复
  -> 最后一次带引用正文之后执行 final citation audit
  -> 两位独立盲评者审查同一最终稿
  -> 作者信息补全与多处精准修订
  -> 编译、质量门和发布 hash 确认
  -> latex/main.pdf
```

当真实结果无法支撑计划论断时，流程只在一个集中检查点要求用户选择：收窄论断并冻结当前图表和指标，或者补充数据/方法后重跑证据链。系统不会生成一张相似图片代替研究计划中的主图后继续写作。

## 系统保证与人工控制

Draftpaper-loop 保证可追溯和失败可见，不会通过流程标签宣称科学结论天然正确。

- **证据先于正文：** 研究蓝图、可执行方法、run output、图表和结果支撑先于 Results 及其余章节。
- **保留自然写作：** 合同约束事实与论断边界，不把 Codex 行文退化为固定段落模板。
- **运行真值：** mock、fixture-only、contract-only 和 candidate 插件不能支撑论文结果；project-local 代码必须经过审计并绑定运行产物。
- **保留参考文献：** citation audit 修正表述、位置和支撑强度，但保留用户人工确认的文献，不能靠删除引用获得全绿。
- **精确 stale：** 纯作者信息只重建出版物；数据、方法、run、cohort、指标或核心图变化会重新打开必要科研阶段。
- **事务式作者修改：** metadata、参考文献和定点正文先统一预览，再通过 hash 绑定事务写入，并支持受约束 rollback。
- **人工最终权威：** 用户确认研究蓝图、核心证据、claim downgrade、插件 promotion、作者 packet 和最终 release hash。
- **本地边界：** 论文项目、私有数据 locator 和凭证默认留在本地，只有显式批准的 connector 才可访问外部环境。

## 安装

需要 Python 3.10 或更新版本。

| 档位 | 源码 editable 安装 | 能力 |
|---|---|---|
| Minimal | `python -m pip install -e .` | 控制面、参考文献、PDF/图像检查和内置 paper-fetch fallback |
| Plotting | `python -m pip install -e ".[plotting]"` | 论文图表及 NumPy/pandas 科研插件运行时 |
| Full text | `python -m pip install -e ".[fulltext]"` | 增强 PDF/网页正文抽取与 metadata 规范化 |
| MCP | `python -m pip install -e ".[mcp]"` | 本地 stdio MCP transport |
| 科研工作站 | `python -m pip install -e ".[plotting,fulltext,mcp]"` | 合并的本地科研环境 |

不要假设当前 Python 已经安装全部 extra，应直接检查：

```powershell
draftpaper doctor --json
draftpaper skill-doctor
draftpaper mcp-doctor
```

Doctor 会列出每个档位缺失的模块和准确恢复命令。缺少可选档位不会让 minimal 控制面失效，但执行对应科研阶段前必须安装，不能把缺失能力报告为可用。

## 快速开始

PowerShell：

```powershell
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
Set-Location Draftpaper_loop
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[plotting,fulltext]"
.\.venv\Scripts\draftpaper create-project --idea "你的研究 idea" --field "astronomy machine learning" --target-journal MNRAS
.\.venv\Scripts\draftpaper start --project .\projects\your-project
.\.venv\Scripts\draftpaper status --project .\projects\your-project
```

Bash：

```bash
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[plotting,fulltext]"
.venv/bin/draftpaper create-project --idea "你的研究 idea" --field "astronomy machine learning" --target-journal MNRAS
.venv/bin/draftpaper start --project ./projects/your-project
.venv/bin/draftpaper status --project ./projects/your-project
```

`status` 是下一步动作的权威来源。`continue` 会先核对当前 artifact 和 gate，再恢复有效路线；它不是无条件重写已完成章节的命令。

## 研究者常用命令

| 目的 | 命令 | 行为 |
|---|---|---|
| 启动受控 loop | `draftpaper start --project <project>` | 依据权威状态初始化或恢复流程 |
| 查看当前状态 | `draftpaper status --project <project>` | 显示下一动作、阻塞、stale 范围和人工决策 |
| 安全继续 | `draftpaper continue --project <project>` | 只执行当前合法路线 |
| 审阅检查点 | `draftpaper review --project <project>` | 生成审阅 packet，不会静默接受 |
| 精准修改正文 | `draftpaper revise --project <project> ...` | 使用稳定原文/hash 定位生成候选修改 |
| 诊断环境和项目 | `draftpaper doctor --project <project> --json` | 只读依赖、状态和恢复报告 |
| 查看 token/成本 ledger | `draftpaper token-report --project <project>` | 汇总 actual/estimate token，只显示明确记录的货币成本 |
| 生成恢复方案 | `draftpaper recover --project <project>` | 不会自动接受图表、降低 claim、删除文献或 promote 插件 |

全部 210 个命令的阶段、风险、handler 和 exit policy 由 CommandSpec 自动生成在 [CLI reference](docs/cli_reference.md)。研究者应优先服从 `status` 和上述宏命令，不需要手动拼接完整阶段顺序。

## 最终作者补全流程

科学正文和必要审查完成后，用户可以用一个 YAML packet 一次性补充作者、单位、ORCID、通讯信息、CRediT、基金、致谢、声明、数据/代码链接、补充材料、人工确认的新文献，以及多个章节中的精准修订。

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper review-final-manuscript --project <project>
draftpaper confirm-final-manuscript --project <project> --release-hash <sha256>
```

LaTeX 行号只用于展示；稳定 paragraph ID、expected text 和 hash 才是真实定位条件。Preview 会生成统一 metadata/section/BibTeX diff、影响报告和候选 PDF，不修改 canonical source。Apply 会重新核对全部 anchor 和 evidence snapshot，再把整个 packet 作为一个事务提交。科学证据变化不能伪装成语言修改，而会重新打开科研链路。完整说明见[最终论文补全指南](docs/manuscript_completion.zh-CN.md)。

## 文档入口

- [科研流程优先级指南](docs/cli_workflow_priority_guide.md)：完整 evidence-first 阶段与恢复路线。
- [CLI 命令参考](docs/cli_reference.md)：自动生成的命令、阶段、风险、handler 和退出策略。
- [安装档位](docs/install_profiles.zh-CN.md)：minimal、plotting、fulltext 和 MCP 边界。
- [Token 与成本报告](docs/token_cost_reporting.zh-CN.md)：ledger 总量、当前写作预算和金额记录边界。
- [命令风险矩阵](docs/command_risk_matrix.md)：自动生成的风险、副作用和 write-root 清单。
- [最终论文补全](docs/manuscript_completion.zh-CN.md)：metadata、双重定位、preview、apply 和 rollback。
- [DPL Schema](docs/DPL_SCHEMA.md)：artifact 与合同 schema family。
- [学科插件编写](docs/discipline_modules/codex_authoring_guide.md)：本地插件模板和 promotion 边界。
- [第三方说明](third_party/THIRD_PARTY_NOTICES.md)：借鉴、内化或保留 fallback 的来源及许可证。
- [商业能力概览](docs/commercial_overview.zh-CN.md)：许可、部署方式和当前托管服务边界。
- [发布验证流程](docs/release_process.zh-CN.md)：tag 身份、平台 smoke、wheel 和安全检查。

## 近期版本摘要

- **v0.31.1-v0.31.4：** 共享 ID/工具、插件与 Methods 职责拆分、统一 figure façade 和单一 CommandSpec 入口。
- **v0.31.5：** 热路径资源 schema 注册、CI coverage 下限 65% 和更广 Pyright 范围。
- **v0.31.6：** 真正 minimal wheel、显式 plotting/fulltext/MCP extra、Doctor 安装档位和四档 CI smoke。
- **v0.31.7：** 短中英文入口页和自动生成 CLI reference 替代超长 README 命令与历史堆叠。
- **v0.31.8：** 只读 token/成本报告、合并 research 安装档位、自动命令风险矩阵和明确商业边界。
- **v0.31.9：** macOS 控制面 smoke 和 tag 到 wheel 的身份核验，不开启公开包分发。

旧长文档保留在 `docs/archive/`，Git 历史是权威版本记录。

## 许可、来源与支持

本仓库依据 `LicenseRef-Draftpaper-NonCommercial` 允许非商业使用，商业使用需要书面授权，详见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。`third_party/registry.json` 与 notices 记录实现过程中借鉴、内化或保留 fallback 的外部项目和 skills。私有数据、凭证、论文 PDF 和项目专属脚本不能进入公开插件贡献。

维护与联系方式见[支持页面](https://xiejhhhhhh.github.io/Draftpaper_loop/support/)。
