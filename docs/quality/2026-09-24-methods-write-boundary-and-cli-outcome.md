# 方法补充表写入与 CLI 事务结果修复

日期：2026-09-24。适用范围：v0.43.2 之后的 main 源码更新；本次不修改包版本号或创建新 tag。

## 问题与根因

项目专用方法脚本可以通过自身验证，并在结构化 stdout 的 `outputs` 中报告补充表；但原 methods 阶段写集只覆盖 methods、results 等目录，未允许 `supplementary/tables/`。外层审计因此拒绝补充表并回滚整次命令，包括其他原本合规的写入。

与此同时，CLI 在外层写集审计、passport 刷新和事务回执完成前就输出了处理器的 `status=success`。调用方会同时看到成功 JSON、写集违规报告和非零退出码。内部方法计算成功不等于该次写入已经提交。

本次只读核验确认，报告问题的项目包装脚本已经声明补充 CSV 与 TeX 输出，最近一次事务记录为 `boundary_violation_rolled_back`，内部 scientific exit code 为 0，违规项仅为两份补充表。没有执行该论文项目的脚本、迁移或状态更新。

## 框架决定

1. 沿用现有按阶段声明写集的设计，为 methods 阶段补充 `supplementary/tables/*.csv`、`*.tsv`、`*.tex` 三条规则。没有开放整个 supplementary 目录；Python 脚本等未许可类型仍会触发写集违规，路径 confinement 和 forbidden rules 继续生效。
2. 写入许可与科研证据验证分别负责不同事项。表格仍须通过 `--output`、method-code manifest 或脚本结构化 `outputs` 进入现有输出检查和哈希登记；新规则不会自动赋予表格科研有效性。
3. CLI 暂存处理器的 stdout/stderr，在外层事务处理结束后输出。正常成功和科研不通过的结果保留原有格式；事务失败时只输出外层错误，不再先发布处理器的成功结果。
4. 写集违规报告明确包含 `transaction_status`、`command_exit_code`、`handler_status`、`handler_exit_code` 和 `scientific_decision=not_committed`。完整回滚返回 4，回滚不完整返回 5；历史处理器退出码继续作为诊断保存在事务账本中。
5. Passport 刷新或事务回执写入失败返回错误，不输出提前成功声明。这类错误不等同于写集回滚；应按具体回执和实际文件状态恢复。

## 影响文件

- `draftpaper_cli/command_registry.py`：methods 补充表写入许可。
- `draftpaper_cli/cli.py`：延后输出及统一外层失败结果。
- `tests/test_methods.py`：真实 CLI、项目脚本和事务行为回归。
- `docs/command_risk_matrix.md`：由生成器同步的写集规则数量。
- 中英文 README：main 后续更新说明。

## 项目恢复步骤

在已配置的 Draftpaper 环境中，从包含此修复的源码目录运行命令。原环境若为 editable 安装，更新源码即可；若仍使用旧 wheel，须先安装包含此修复的构建或将目标环境指向该源码 checkout。仅重新安装旧 v0.43.2 wheel 不会取得此次 main 修复。

```powershell
git pull --ff-only origin main
python -c "import draftpaper_cli; print(draftpaper_cli.__file__)"
python -m draftpaper_cli.cli session-preflight --project "<project>" --accept-runtime-update
```

这里的 runtime 更新用于接受新源码与 CommandSpec 身份，不替代任何科学确认。本次没有新增项目 schema，因此不要求重建项目、重新生成 research plan 或清空历史账本。

确认旧事务为完整回滚后，重试原有项目方法命令：

```powershell
python -m draftpaper_cli.cli verify-methods --project "<project>" --command "{python} methods/scripts/<project_runner>.py" --input "data/processed/<input_bindings>.csv"
python -m draftpaper_cli.cli status --project "<project>"
```

成功验收需要退出码 0、最终 `status=success`，以及最新事务为 `committed`。如果项目原本处于延后对账模式，`committed_pending_reconciliation` 表示写入已保存但还需对账，不能视作正式发布就绪。检查 `methods/run_manifest.yaml` 的 output files/hashes 中包含预期补充表；后续证据或确认步骤按项目实际状态继续。

若旧回执是 `boundary_violation_rollback_incomplete`，先按 `unrecoverable` 列表处理未恢复文件，再重试。不要通过手工将 methods 标为 approved 来替代一次成功提交的验证。

## 验证记录

- 修复前，新回归捕获补充表回滚、passport 刷新失败后的误报，以及完整/紧凑输出下完整/不完整回滚后的误报，共 6 个失败断言（包括子测试）。
- 修复后，新增 3 项测试与 4 个子测试通过，覆盖真实子进程运行、补充表文件与输出哈希、事务回执、原文件恢复和退出码。
- Ruff、语法编译和 281 条命令合同通过；使用项目 Python 的默认 Pyright 配置为 0 errors、0 warnings。
- 另行扩大 Pyright 到整个 `cli.py` 时，修复前基线与本次版本均有相同的 15 条历史类型诊断，涉及 Optional project 参数、动态导入及 TextIO.reconfigure。本次未扩大默认类型检查范围或改动这些既有代码。

- 相关扩展回归：119 passed、1 skipped、4 subtests passed，耗时 384.74 秒；覆盖方法执行、命令合同、安全策略、MCP、事务控制、版本管理、扩展宿主、失败路由及 README/生成文档一致性。
- 7 条 warning 均为 scienceplots 调用 Matplotlib 已弃用接口的提示，不是本次测试失败。
- 本地未执行整个仓库的跨平台全量矩阵；推送后交由 GitHub Actions 执行，本次不等待或监测远端测试结果。
