# v0.30.1 P0 Release 对账报告

日期：2026-07-18  
基线提交：`09b7021` (`main`)  处理分支：`codex/v0301-v0320`

## 1. 对账范围

本报告只覆盖综合方案中的 v0.30.1 P0：hard-gate 退出码、CommandSpec 绑定、MCP 私有 artifact 保护、URL/registry 输入边界、release manifest 对账、secret scan 和 wheel isolation。

当前分支从干净的 v0.30.0 `main` 建立。主工作树中存在的 `manuscript_completion` 原型未复制到本分支，因此本报告明确证明：**v0.30.1 P0 release 对账不包含实验性 completion 功能。**

## 2. 已完成修复

### 2.1 Hard gate 与命令合同

- `assess-core-evidence` 绑定 `gate_handlers.assess_core_evidence_gate`，使用 `decision_pass`。
- `assess-result-validity` 绑定 `gate_handlers.assess_result_validity_gate`，使用 `decision_pass`。
- `assess-data-quality` 绑定 `gate_handlers.assess_data_quality_gate`，使用 `quality_pass`。
- `verify-methods` 绑定 `gate_handlers.verify_methods_gate`，使用 `status_success`。
- `run-integrity-gate` 绑定 `gate_handlers.run_integrity_gate`，使用 `decision_pass`。
- Command contract 校验对 hard gate 缺失 handler 或 `always_success` 报错。
- registry 的 dispatch 支持 `quality_pass` 和 `status_success`，保留现有 legacy dispatch 作为后续 v0.31 单轨迁移范围。

### 2.2 安全边界

- MCP `artifact_get` 拒绝 `*.private.json`、private locator、credentials、secret、password、token 和 API key 命名的 artifact。
- 新增 `safe_fetch`，对 journal 和 skill registry metadata 统一执行 HTTPS、host allowlist、DNS 地址阻断、响应大小限制和危险 scheme 拒绝。
- `journal_profile._fetch_text` 仅允许 Overleaf host；skill registry metadata 仅允许 GitHub raw/API host。
- 现有 `revise --content-file` 的项目外临时文件兼容行为未在 v0.30.1 改变；completion 专用路径 confinement 留待 v0.30.4 纳入实验原型时实现，避免破坏已有 revision API。

## 3. 当前 release inventory

由 `build_command_contracts()` 生成：

| 字段 | 值 |
|---|---:|
| status | `passed` |
| command_count | `204` |
| registered_handler_count | `85` |
| legacy_dispatch_count | `119` |
| contract issues | `[]` |

`legacy_dispatch_count=119` 是已知的后续 v0.31.1-v0.32.0 架构债，不作为 v0.30.1 P0 的假修复；v0.30.1 的强制条件是 hard gate 不再缺 handler、不再使用 `always_success`，而不是提前完成全部 CLI 单轨迁移。

由 `validate_release_manifest()` 生成：

| 字段 | 值 |
|---|---|
| status | `passed` |
| changed_fields | `[]`（在写入当前版本 manifest 前） |
| security_issues | `[]` |
| formal plugin count | `210` |
| fixture count | `546` |
| third-party source count | `6` |

## 4. 实验性 completion 排除证明

本分支不包含以下文件和命令：

- `draftpaper_cli/manuscript_completion.py`
- `tests/test_manuscript_completion.py`
- `prepare-manuscript-completion`
- `preview-manuscript-completion`
- `apply-manuscript-completion`
- `manuscript-completion-status`
- `rollback-manuscript-completion`

因此 v0.30.1 的 release manifest 和 wheel 不应宣称 Manuscript Completion Workspace 已发布。后续 v0.30.4-v0.30.7 必须先审阅并迁移原型，再更新 command inventory 和 release manifest。

## 5. P0 测试证据

### 5.1 基线

```text
python -m pytest -q
679 passed in 11:43
```

### 5.2 P0 相关回归

```text
python -m pytest -q tests/test_v0301_p0_contracts.py tests/test_v025_skill_and_security.py tests/test_command_contracts_v029.py tests/test_doctor_and_command_contract.py tests/test_methods.py tests/test_data_feasibility.py tests/test_method_plan_and_result_validity.py tests/test_manuscript_revision.py

78 passed in 80.51s
```

新增 `tests/test_v0301_p0_contracts.py` 覆盖：

- hard gate handler 和 exit policy；
- 非通过 payload 返回非零 exit code；
- MCP private locator/credential artifact 拒绝；
- `file://`、`data://`、HTTP 私网 URL 拒绝。

### 5.3 其他 P0 检查

```text
python -m draftpaper_cli.cli validate-command-contracts
status=passed, command_count=204, issues=[]

python -m draftpaper_cli.cli validate-third-party-provenance
status=passed, source_count=6, formal_plugin_count=210, issues=[]

python tools/scan_secrets.py
No likely first-party credentials detected.
```

## 6. Wheel isolation 最终证据

```text
python -m build --wheel
Successfully built draftpaper_cli-0.30.1-py3-none-any.whl

python tools/verify_wheel_install.py --wheel-dir dist
matched: true
package_version: 0.30.1
entry_count: 210
fixture_count: 546
capability_pack_count: 6
vendored_paper_fetch_present: true
third_party_provenance_status: passed
release_regressions.status: passed
```

wheel isolation 同时通过 release regression adversarial checks：wrong cohort、run、unit、split、model、metric、dimension、blank figure、contract-only plugin、citation negation、numeric mismatch 和 causal reversal 均被拒绝。

## 7. 仍待执行

以下不应伪装成 v0.30.1 P0 已完成：

1. v0.30.2 的完整 URL redirect/size/content-type policy、verify-methods executable allowlist、write-set preflight 和子进程环境白名单。
2. v0.30.3 的统一 change classification 与 stale/DAG parity。
3. v0.30.4-v0.30.7 的 completion schema、双重 locator、原子 preview/apply/rollback 和 final release hash 绑定。
4. v0.31.1-v0.32.0 的 CLI 单轨迁移、plugin_candidates 包化、coverage/pyright、依赖瘦身和文档站点。
5. wheel isolation 和 GitHub Actions 全矩阵需要在当前版本 manifest 写入后再次执行并记录最终结果。

## 8. P0 结论

P0 代码和单元/合同测试达到进入 wheel 构建的条件；release 对账在写入 v0.30.1 manifest 后必须重新执行。实验性 completion 已被隔离，不能随 v0.30.1 发布。只有 wheel isolation、当前版本 manifest 对账和 CI 兼容性验证通过后，才允许开始 v0.30.2。
