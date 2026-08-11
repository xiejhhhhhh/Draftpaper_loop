# 分级审查与 Agent 委托

Draftpaper-loop v0.39.0 将 checkpoint 的“是否需要提醒”“谁可以审查”和“谁已经作出决定”分开记录。`review_state` 描述证据是否可审查，`review_requirement` 描述审查权限，`decision_status` 描述实际决定。Agent 的批准永远记录为 `agent_approved`，不会伪装成 `user_confirmed`。

## 三种模式

- `manual`：所有需要决定的 checkpoint 都等待用户。
- `balanced`：通知型阶段自动继续；C1/C2 阶段在用户授予有效 delegation 后可由 Agent 审查；C3 永远等待用户。
- `delegated`：在 delegation 范围内扩大 Agent 审查，但仍不能越过 C3、阻断、stale、互斥科学路线、作者身份、许可证和最终发布。

新项目默认写入 `balanced`；旧项目没有 `.draftpaper/review_policy.json` 时按 `manual` 处理，必须显式配置或授权后才改变行为。

## 推荐操作

```powershell
draftpaper configure-review-policy --project <project> --mode balanced
draftpaper grant-agent-review --project <project> --scope data,methods --max-risk C1 --actor-id producer-agent
draftpaper review-policy-status --project <project>
draftpaper evaluate-checkpoint-authority --project <project> --checkpoint-hash <hash>
draftpaper review-checkpoint --project <project> --checkpoint-hash <hash> --actor-id reviewer-agent --reviewer-agent-id producer-agent
draftpaper revoke-agent-review --project <project> --reason "return to manual review"
```

## 授权有效性与审查边界

每份 delegation 都是不可变的受限授权，绑定项目、policy hash、runtime fingerprint、阶段范围、风险等级、可选 revision cycle、到期时间、可用 checkpoint 数量、允许的 change class，以及“不得带未解决阻塞项或外部副作用”的限制。撤销操作会向 append-only ledger 追加撤销回执，不会改写原授权文件。

Agent 每次审查前都会重新核验 v4 summary 与 summary hash、策略 hash、运行时身份、授权是否过期或已撤销、阶段与风险范围、revision-cycle 绑定、change class、未解决事项和外部副作用。策略或运行环境发生变化时，旧授权会失效；仅新增另一份授权或更新记录时间不会使原本仍有效的授权失效。

C2 除有效授权外，还必须明确允许 scientific freeze，并由与生产 Agent 不同的 reviewer Agent 审查。C3、互斥科学路线、作者身份、许可证、最终稿、发布和任何外部写操作始终只能由用户决定。`agent_approved` 只表示已完成受授权的 Agent 审查，绝不等同于 `user_confirmed`。

`grant-agent-review` 生成带 hash 的 delegation 文件。delegation 过期、撤销、revision cycle 不匹配、summary/evidence/runtime hash 改变时均不能继续使用。Agent 审查会生成 checkpoint 目录下的 `review_decision_receipt.json` 和项目级 append-only decision ledger；Agent resume 只消费 `agent_approved` receipt。

## 人工边界

研究蓝图、互斥 claim 路线、核心证据、数据补充与停止/重跑路线、第三方代码下载与 promotion、作者身份、许可证、最终稿和 release hash 仍由用户确认。静默超时不等于同意，Agent 的模型置信度也不能替代证据 gate。

阶段 HTML 会显示审查要求、决定主体、delegation 和 receipt 路径。完整阶段活动见 `stage_activity_bundle.json`；不要仅凭文件数量判断 Agent 做过什么。
