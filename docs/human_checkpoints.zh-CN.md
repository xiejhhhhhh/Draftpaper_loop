# 分级审查点成果包

当前阶段摘要合同为 `dpl.checkpoint_summary.v4`。v1/v2 只能只读审计；v3 仍可
读取以保持旧项目兼容，但不会原地重写 hash。v4 把“证据是否健康”“谁应审查”和
“谁已经决定”拆为 `review_state`、`review_requirement` 与 `decision_status`，因此
并非每个 checkpoint 都需要用户手动点击确认。

每个 checkpoint 都会写出一个可离线审阅的阶段成果包。只有需要作者判断的 C3
科学路线、互斥选择、作者身份、许可证、第三方代码执行、最终稿与发布才会强制
停在用户面前；C0 通知型阶段会保留成果包后自动继续，C1/C2 只有在用户事先授予
有效 delegation 时才可由 Agent 审查。Agent 决定永远记为 `agent_approved`，不会
冒充 `user_confirmed`。成果包位于：

```text
review/checkpoints/<checkpoint_id>/
├── stage_summary.zh-CN.html
├── stage_summary.json
├── stage_activity_bundle.json
├── artifact_manifest.json
├── confirmation_request.json
├── change_report.json
├── unresolved_issues.json
└── agent_payload.json
```

中文 HTML 是面向用户的主入口。第一屏先用一段有收据支撑的中文说明 Agent
实际读取、分析、生成、修改、复用、验证、重试、跳过和失败了什么；随后展示
完整图表、表格、代码、报告、运行证据、相对上一快照的变化、未解决事项、审查
主体、纵向基线和恢复路线。Agent 返回中同时显示项目相对路径和当前机器绝对路径。

v4 的 `stage_summary.json` 明确登记 `identity`、`core_metrics`、`sample_flow`、
`review_state`、`review_requirement`、`decision_status`、`decision_actor_type`、
`StageActivityBundle`、`baseline_refs`、`confirmation_contract` 和恢复路线。HTML、
JSON、Agent payload 和 `stage_activity_bundle.json` 必须从同一事实层生成。`confirmable`
只表示机器合同通过，不表示用户已经确认科学含义。

checkpoint 绑定的是语义 identity 和 evidence identity，不绑定报告时间戳、
HTML 样式或机器绝对路径。数据、方法、运行、指标、cohort 或证据上游发生
变化时，旧 checkpoint 会失效，`resume` 不得继续消费。

查看和继续命令：

```powershell
python -m draftpaper_cli.cli show-checkpoint-summary --project <project>
python -m draftpaper_cli.cli resume --project <project> --checkpoint-hash <hash>
```

启用受控 Agent 审查时，先由用户显式配置一次策略和授权范围：

```powershell
python -m draftpaper_cli.cli configure-review-policy --project <project> --mode balanced
python -m draftpaper_cli.cli grant-agent-review --project <project> --scope data,methods --max-risk C1 --expires-at <ISO-8601 时间>
python -m draftpaper_cli.cli evaluate-checkpoint-authority --project <project> --checkpoint-hash <hash>
```

delegation 会绑定项目、策略 hash、运行时身份、风险等级、阶段、可选修订周期、
过期时间和允许的 change class。过期、撤销、篡改、summary hash 改变、运行时不一致、
未解决阻断项或外部副作用都会阻止 Agent 审查；撤销会写独立 receipt，不会改写原授权
文件。

Agent 必须给出摘要路径、重点产物路径、未解决事项数量、审查主体、确认含义和一条
合法命令，不能只显示“请确认”。当前版本按阶段或一次外部编辑批次生成一个原子
确认点；多 claim 独立分治仍不属于当前版本。

`blocked`、`stale`、`preview_only`、身份缺失和 `legacy_unqualified` 页面不得
提供确认命令。匿名 fixture showcase 可以同时记录 `test_mode=true` 和
`test_auto_confirmation=true` 以测试页面流程，但该标记不能进入真实项目的
确认记录、ledger 或 active pointer。

其中 `stage_activity_bundle.json` 是 Agent/CLI 活动、事务和 artifact diff 的事实汇总；
`change_report.json` 汇总本阶段生成、修改、部署、验证和失败的内容；
`unresolved_issues.json` 是未解决事项的机器可读投影；`agent_payload.json` 保存
Agent 需要展示的项目相对路径、本机绝对路径、重点产物和审查含义。它们与摘要、
artifact manifest 和 confirmation request 一起缺一不可。摘要样式、时间戳和本机
绝对路径变化不会改变科学 checkpoint hash，但上游证据变化会使旧 checkpoint 失效。

## 完整阶段产物与事务变更

HTML 中将两类信息分开显示。**完整阶段产物**是用户需要审阅的范围：
本阶段相关的全部图表、表格、文字报告、运行清单、证据文件和代码文件，
包括 checkpoint 前已经存在且本次没有发生字节变化的文件。**事务变更**只
记录相对上一份 passport 快照的新增、修改、部署、失败和未变化项。因此，
事务变更为空并不表示本阶段没有生成或交付内容。

对于 `core_evidence`，摘要会读取项目内的核心证据报告、结果有效性与论断
支撑报告、指标 CSV 的有限预览、图表元数据以及图表到绘图代码的追踪记录。
每个产物都显示项目相对路径、本地哈希、用途，并在可能时显示图像或有限行数
的表格预览。HTML 是完整产物的审阅索引，不替代原始文件；原始路径和哈希仍
是最终依据。

如果上游证据已经发生漂移，先使用只读预览命令：

```powershell
python -m draftpaper_cli.cli preview-checkpoint-summary --project <project> --checkpoint-hash <hash>
```

预览会写入派生的 `*-preview` 包，但不会修改 checkpoint ledger 或索引。预览
明确不可消费，并隐藏 resume 确认命令。应先处理漂移并生成新的 canonical
checkpoint，再请求用户进行人工确认。

## 运行时身份升级

`session-preflight` 默认会阻止旧项目继续使用不同的 wheel、源码提交、命令
注册表、schema 或 Skill。只有确认当前代码版本已经完成发布候选验证后，才可
显式接受运行时更新：

```powershell
python -m draftpaper_cli.cli session-preflight --project <project> --accept-runtime-update
```

该选项只更新 `.draftpaper/runtime_lock.json` 并写入 runtime migration receipt，
不会修改研究蓝图、passport、数据、方法、结果或任何科学 checkpoint。没有明确
接受时不要使用该选项；运行时更新完成后仍必须重新执行 `status`、
`verify-next-action` 和相应的科学证据门禁。
