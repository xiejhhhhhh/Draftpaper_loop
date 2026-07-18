# Token 与成本报告

`draftpaper token-report --project <project>` 读取 append-only 的 `token_ledger.jsonl`，输出：

- 输入和输出 token 总量；有 actual 记录时使用 actual，否则使用 estimate；
- 按阶段和模型汇总的 token；
- 每个论文写作任务当前最新的 packet；
- 当前写作输入与 manuscript token budget 的比较；
- 只有运行环境实际记录金额时才汇总货币成本。

Draftpaper-loop 不维护隐藏的模型价格表，也不会仅根据 token 数量推测金额。如果只有部分 receipt 带有 `recorded_cost_usd`，报告会标记为部分覆盖；完全没有金额记录时，会明确说明缺少 price contract，而不是生成虚假成本。

该命令只读，输出 schema 为 `dpl.token_cost_report.v1`。历史重试保留在 lifetime 总量中；当前 manuscript budget 只计算每个写作任务的最新 packet。
