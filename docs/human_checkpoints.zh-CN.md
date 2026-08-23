# 人工确认点成果包

新建 checkpoint 使用 `dpl.checkpoint_summary.v5`。v1/v2 为只读历史记录；v3/v4
仍可阅读以兼容旧项目，但不会被原地改写，也不会被静默当作 v5 科学决定。

## 作者首先打开什么

每个 v5 checkpoint 都会在 `review/checkpoints/<checkpoint_id>/` 写出一个可携带、
可离线阅读的成果包：

```text
stage_summary.zh-CN.html              # 面向作者的可读决定页
stage_summary.en.html                 # 同一决定的英文渲染页
stage_audit.zh-CN.html                # 完整技术审计页
stage_summary.json                    # v5 成果包合同
human_decision_brief_v1.json          # 作者看到的事实与决定陈述
scientific_decision_fingerprint_v1.json
checkpoint_audit_fingerprint_v1.json
checkpoint_presentation_fingerprint_v1.json
stage_activity_bundle.json
artifact_manifest.json
figure_claim_map_v1.json
confirmation_request.json
agent_payload.json
checkpoint_readability_report.json
```

应先打开 `stage_summary.zh-CN.html`。它是正式、hash-bound 的作者决定页，不是
Agent 在项目外临时制作的简化 sidecar。作者应能在约一分钟内看清：

- 这次究竟要确认什么科学决定；
- 相对上次有效确认真正改变了什么；
- 样本、验证设计、主结果、主图和论断边界；
- 哪些内容明确不属于本次确认；
- 什么变化会重新打开科学确认；
- 本轮可阅读交付物与确认后的下一步。

`stage_audit.zh-CN.html` 保留完整技术信息：当前活动窗口、产物清单、事务变化、
验证表、证据身份、hash 和恢复细节。决定页会链接到它，但用户不需要先读完整审计
才能理解自己将要确认的科学内容。

## 决定身份与连续确认

v5 将三种身份分开记录：

| 身份 | 覆盖内容 | 变化后的行为 |
|---|---|---|
| `scientific_decision_sha256` | 数据/cohort/split/样本单位、可执行分析规格、方法合同与 run、指标与不确定性、图表语义、论断边界 | 重新触发 C3 作者确认 |
| `audit_bundle_sha256` | artifact manifest、活动收据、验证报告和技术审计 | 仅刷新审计 |
| `presentation_sha256` | 决定页渲染与本地化 | 仅重建页面 |

confirmation request 绑定的是科学决定 hash 和 DecisionBrief 的语义 hash，不再绑定整份
审计页或重新编译后的 PDF。若最近一次有效用户 receipt 与当前科学身份、决定陈述身份
完全一致，且不存在 missing、stale、conflict 或无法分类的证据，系统会写入
`confirmation_continuity_receipt.json`。新 checkpoint 变为通知型阶段并可继续，用户无需
再次输入 C3 hash。这表示沿用旧的用户科学决定，绝不表示系统或 Agent 替用户做了新的
科学判断。

只要指标数值或定义、不确定性、cohort、split、样本单位、可执行分析规格、方法合同、
声明实现入口、run 身份、主图语义系列或论断边界发生变化，就必须生成新的语义差异并
要求作者重新确认。核心证据缺少可执行分析规格或方法合同身份时严格阻断，不能使用
continuity。

## 有界范围与审查主体

`StageActivityBundle v2` 从上一个合法 checkpoint 边界之后开始，只记录当前窗口，
不会把历史 checkpoint、resume 或无关重试重新叙述为本轮工作。artifact selection 遵循
manifest-first 和有界 stage discovery：旧的 `review/checkpoints/`、缓存、lineage 和
历史结果目录不会仅因文件存在就进入当前决定包。

决定页属于 `author_decision`。内部 ledger、trace、package hash 与审计附件属于
`internal_audit`；独立稿件审查只能读取 `reviewer_visible` 的材料。`FigureClaimMap`
将主图与决定陈述绑定；当图表元数据、caption 元数据和当前证据身份中已声明的
cohort/split 不一致时，系统会阻断确认。

C0 通知型阶段可以记录 `system_acknowledged`；C1/C2 仅在有效的 scoped Agent delegation
下可由 Agent 审查；C3 科学路线仍由用户确认，除非 continuity receipt 证明用户已经确认了
完全相同的科学决定。Agent 只能写入 `agent_approved`，不能冒充 `user_confirmed`。

## 命令

```powershell
draftpaper show-checkpoint-summary --project <project> --view decision
draftpaper show-checkpoint-summary --project <project> --view decision --language en
draftpaper show-checkpoint-audit --project <project> --checkpoint-package-id <id>
draftpaper compare-checkpoint-decision --project <project> --against latest-confirmed
draftpaper explain-reconfirmation --project <project> --checkpoint-package-id <id>
draftpaper validate-checkpoint-readability --project <project> --checkpoint-package-id <id>
draftpaper validate-checkpoint-readability --project <project> --checkpoint-package-id <id> --language en
draftpaper show-confirmation-continuity --project <project> --checkpoint-type core_evidence
draftpaper rebuild-checkpoint-presentation --project <project> --checkpoint-package-id <id>
draftpaper audit-checkpoint-v5-migration --project <project> --checkpoint-hash <hash>
draftpaper shadow-checkpoint-v5 --project <project> --output-root <项目目录外的输出目录>
draftpaper resume --project <project> --checkpoint-hash <hash>
```

`compare-checkpoint-decision`、`explain-reconfirmation` 和
`validate-checkpoint-readability` 为只读命令。重建 presentation 只会重写两个 HTML
与可读性报告，不会改变科学决定指纹，也不会制造新的确认义务。

`blocked`、`stale`、`preview_only`、身份缺失、legacy 或 conflict 的成果包都不能显示
作者确认命令。`preview-checkpoint-summary` 仍只生成不可消费的派生包。匿名 fixture 可使用
`test_auto_confirmation=true`，但该标记绝不能确认真实项目。

## 旧包迁移与 shadow 核验

`audit-checkpoint-v5-migration` 只读取历史成果包并报告下一步。它绝不改写历史 summary、
转移用户 receipt，也不会把旧包 hash 当作当前 v5 科学决定。v1-v4 包最多可投影为比较预览；
较早生成、尚未将 `FigureClaimMap` 纳入 scientific fingerprint 的 v5 包同样保持只读。较早
核心证据 v5 包若尚未绑定可执行分析规格和方法合同，同样只能只读；除非已存在经核验的
等价当前合同决定，否则流程仍需要一次新的 v5 C3 作者确认。

`shadow-checkpoint-v5` 用于现有项目的回归核验。`--output-root` 必须位于项目目录外。该命令
会记录 passport、ledger、promoted snapshot、checkpoint 记录和稿件 PDF 的前后 hash，再将 JSON
与 HTML 报告写在项目外。未变化状态核验失败会直接阻断，不能在 shadow 审计过程中修复项目证据。

## 运行时身份升级

当 wheel、源码提交、命令注册表、schema registry 或 workflow Skill 与项目中记录的
runtime 不一致时，`session-preflight` 会阻止旧项目继续。完成发布候选验证后，才能显式
接受该 runtime migration：

```powershell
python -m draftpaper_cli.cli session-preflight --project <project> --accept-runtime-update
```

该命令只更新 `.draftpaper/runtime_lock.json` 并写入 migration receipt，不会改写研究证据、
科学决定或 checkpoint 成果包。
