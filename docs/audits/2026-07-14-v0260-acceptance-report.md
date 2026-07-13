# Draftpaper-loop v0.26.0 验收报告

日期：2026-07-14
范围：v0.25.1-v0.26.0
结论：通过

## 验证结果

- 全量源码测试：`565 passed in 685.24s`。
- 最后变更定向回归：`28 passed in 134.80s`。
- Python 编译：`python -m compileall -q draftpaper_cli tools` 通过。
- wheel：成功构建并隔离安装 `draftpaper-cli 0.26.0`。
- wheel 内置 workflow skill：版本 `0.26.0`，源码与安装包 SHA-256 均为 `485b8e943dbdb5cc195d18142c9d2a1aa56019c24499bd2a3b022c42f69e5365`。
- workflow contract：版本 `0.26.0`，源码与安装包 SHA-256 均为 `2dd4aa5103523321e2d164122b80f7e9511ff0af03de655eb08df8be3c6690de`，并声明研究蓝图和最终稿确认属于 protected actions。
- wheel 资源：209 个插件 manifest、545 个 fixture、6 个 capability pack、vendored paper-fetch 和 6 个第三方 provenance 来源均与源码一致。
- 发布回归：scientific-image astronomy+ML、geography+ML、time-domain astronomy+ML、bioinformatics/medicine、physics/quantum 五类夹具通过。
- 对抗回归：错误 cohort、run、sample unit、split、model、metric、metric dimension、空白图、仅合同未执行插件、引用否定、数值不一致和因果方向反转均被拒绝。

## 十五项验收

| # | 验收结论 | 证据 |
|---|---|---|
| 1 | 通过 | `ProjectWorkspacePolicy` 按 CLI、环境变量、用户配置、仓库 projects 的优先级解析中央根目录；仓库外工作目录解析到本机配置的 `C:\Draftpaper_commercial\projects`。 |
| 2 | 通过 | 大型外部数据默认 `manifest_only`，绝对路径只进入忽略的 private locator，公开合同和 fingerprint 不复制原始数据。 |
| 3 | 通过 | `ArtifactOwnershipGuard` 拒绝项目根目录逃逸；临时文件和日志归入 `.draftpaper`；orphan adoption 只复制通过 project identity 与 hash 校验的文件。 |
| 4 | 通过 | slug 上限 48 字符并携带稳定 8 位 ID；创建、版本化、关键图表代码生成、LaTeX 组装和 PDF 编译均执行路径预算检查。 |
| 5 | 通过 | 未确认当前中文研究方案及精确 plan hash 时，`generate-analysis-code` 明确拒绝执行。 |
| 6 | 通过 | 主图和 panel 绑定 confirmed plan hash、claim、数据、方法和统计 ID；alignment 逐项核对研究问题、预期发现、panel label、数据角色、方法和预期内容。 |
| 7 | 通过 | 显式 research storyboard 不再追加通用学科 fallback；缺少有意义主图时返回计划修订，不以直方图、相关图或 metric summary 凑数。 |
| 8 | 通过 | `FigureCaptionContract` 检查整组图首句、所有 panel、统计定义和 claim boundary，内部路径或不完整 caption 不能进入关键结果确认。 |
| 9 | 通过 | 分类、回归、空间、时间、表征混杂、异常、生存和仿真按任务选择统计规则；规则缺口显式进入 advisory/rescue，不能静默通过。 |
| 10 | 通过 | 关键图表代码生成前执行 capability preflight；缺口按 project-local、学科插件、AcademicForge、GitHub 和 connector 顺序生成补齐任务，并保留补数据/方法与研究范围降维两条路线。 |
| 11 | 通过 | 后置 ResultSupportLoop 区分冻结现有图表后的 claim 降维，以及补数据/方法后的数据、方法、图表、证据和正文完整重跑。 |
| 12 | 通过 | “关键结果与论断支撑确认”解释研究问题、cohort、样本单位、方法 run、统计与不确定性、最大 claim 强度；不把 PNG 存在或外观正常当成科学确认。 |
| 13 | 通过 | Results 完成后执行复合学科 review rules，并优先进入语义修复；发布夹具验证完整 evidence bundle 可通过，缺失信号会产生修复任务。 |
| 14 | 通过 | 最终确认包缺少 `main.pdf`、最终 citation audit、任一独立盲评或质量报告时直接拒绝；齐全后以同一 release hash 冻结，任一产物变化都会报告 drift。 |
| 15 | 通过 | Agent 只能修复实现。确认后的 claim、cohort、sample unit、数据角色、方法、统计设计、主图或 panel 发生变化时必须显式 reopen 并重新由用户确认。 |

## 人工边界

自动测试只验证 checkpoint 和冻结合同，不能代替用户的科研判断。Draftpaper-loop 不会替用户执行 `confirm-research-plan`、关键结果确认或 `confirm-final-manuscript`。关键图表只能严格执行用户确认后的研究蓝图与可行性快照；若蓝图本身有误，必须先由用户纠错、生成新 hash 并重新确认。

## 非阻断提示

wheel 构建仍会显示 setuptools 对 `project.license` TOML table 的 2027 年弃用提示。该提示不影响 v0.26.0 构建、安装或运行，可在后续元数据维护版本中改为 SPDX 表达式。
