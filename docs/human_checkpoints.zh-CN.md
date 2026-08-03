# 人工确认点成果包

Draftpaper-loop 只有在写出一个可离线审阅的阶段成果包后，才会要求用户
做人工确认。成果包位于：

```text
review/checkpoints/<checkpoint_id>/
├── stage_summary.zh-CN.html
├── stage_summary.json
├── artifact_manifest.json
├── confirmation_request.json
├── change_report.json
├── unresolved_issues.json
└── agent_payload.json
```

中文 HTML 是面向用户的主入口，必须说明：阶段目的、科研总结、新生成的
文件、被修改的文件、部署与绑定、验证结果、失败事项、未解决事项、重点
检查文件、确认意味着什么、拒绝后的修复路线和唯一确认命令。Agent 返回
中同时显示项目相对路径和当前机器绝对路径。

checkpoint 绑定的是语义 identity 和 evidence identity，不绑定报告时间戳、
HTML 样式或机器绝对路径。数据、方法、运行、指标、cohort 或证据上游发生
变化时，旧 checkpoint 会失效，`resume` 不得继续消费。

查看和继续命令：

```powershell
python -m draftpaper_cli.cli show-checkpoint-summary --project <project>
python -m draftpaper_cli.cli resume --project <project> --checkpoint-hash <hash>
```

Agent 必须给出摘要路径、重点产物路径、未解决事项数量、确认含义和一条
命令，不能只显示“请确认”。当前版本按阶段或一次外部编辑批次生成一个
原子确认点；多 claim 分治暂不属于当前版本。

其中 `change_report.json` 汇总本阶段生成、修改、部署、验证和失败的内容；
`unresolved_issues.json` 是未解决事项的机器可读投影；`agent_payload.json`
保存 Agent 需要展示的项目相对路径、本机绝对路径、重点产物和确认含义。它们
与摘要、artifact manifest 和 confirmation request 一起缺一不可。摘要样式、
时间戳和本机绝对路径变化不会改变科学 checkpoint hash，但上游证据变化会使
旧 checkpoint 失效。
