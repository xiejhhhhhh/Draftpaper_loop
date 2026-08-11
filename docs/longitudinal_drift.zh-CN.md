# 纵向基线与多轮漂移治理

多轮返修不能把当前 passport 快照当作唯一真值。v0.39.0 使用三类不可变记录：

- `ScientificBaselineBundle`：冻结一次合法审查后的 plan、claim、data/cohort/split、method、run、evidence、figure trace、参考文献集合和产物 hash。
- `RevisionCycle`：声明本轮返修原因、允许的 change class、保护事实和预期产物，并绑定父 baseline。
- `CanonicalFactRegistry v2`：用稳定 `fact_id` 保存跨章节、跨表格、跨图和跨修订周期共享的事实及其 identity。

旧 baseline 只允许被 supersede，不允许原地覆盖。passport 仍可刷新当前文件 inventory，但必须同时写出 `review/drift/<id>/drift_reconciliation.json`，记录比较所用 baseline、外部写入主体、before/after identity、影响的事实与恢复路线。

## 推荐操作

```powershell
draftpaper begin-revision-cycle --project <project> --reason review_round --requested-change "revise methods" --allowed-change-class method_change
draftpaper begin-managed-change --project <project> --intent "bounded prose update" --change-class prose_only --path writing/section.tex --content-file patch.txt
draftpaper apply-managed-change --project <project> --packet-id <id> --packet-hash <hash>
draftpaper sync-artifact-stale --project <project>
draftpaper reconcile-project-drift --project <project> --route rebuild_derived_artifacts
draftpaper audit-longitudinal-consistency --project <project>
```

## 漂移处理与返修周期约束

`sync-artifact-stale` 发现语义或未分类漂移时，会写入待处理的 `dpl.drift_reconciliation.v2` 包，但不会刷新 passport。因此项目会保持 drift 状态，直到使用 `reconcile-project-drift` 显式选择并完成一条合法路线：`rebuild_derived_artifacts` 仅适用于非科学语义变更；`adopt_as_expected_change` 必须存在开启中的 revision cycle，且变更类别属于该轮已声明范围；`reopen_scientific_stage` 则明确重新打开受影响的科学上游。没有 reconciliation 不能用刷新 passport 掩盖漂移。

`begin-managed-change` 和 `apply-managed-change` 用于受管编辑。编辑包会绑定修改前 identity、活动 scientific baseline 与 revision cycle；目标文件被外部修改、baseline 已改变或 revision cycle 已关闭时，旧包都会被拒绝。这样同一论文反复返修时不会把不同轮次的文字、数字或证据静默混用。

`audit-longitudinal-consistency` 不仅比较当前注册表，也比较父基线的事实、正文/图表/表格中的 fact ID、受保护事实、已撤回或已 supersede 的事实，以及 allowed-consumer 约束。受保护事实发生变化，或父版本中已不再活动的事实仍被正文引用，都会阻塞后续推进并给出具体消费者路径。

`byte_only`、presentation-only 和 metadata-only 变化可只重建派生产物；同一 fact identity 的值冲突、cohort/split/run/metric identity 变化会阻断并要求重新打开科学阶段。不同 identity 的数值是 `non_comparable`，不能误报为冲突。

## 返修规则

Agent 或外部编辑器不能直接绕过受管编辑入口修改科学源文件后再刷新 passport 隐藏历史。受管修改必须先生成 before hash 和 change class；外部修改进入 reconciliation；超出本轮 scope 或触及 protected fact 时，必须重新审查并生成新的 baseline。`audit-longitudinal-consistency` 同时检查 fact registry、章节、caption、table、abstract、当前 run bundle 和 revision cycle 的绑定关系。
