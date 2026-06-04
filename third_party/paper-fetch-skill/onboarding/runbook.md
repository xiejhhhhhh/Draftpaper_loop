# Provider Onboarding Runbook

本文是 provider onboarding 的用户/agent 入口和三阶段 operator runbook，负责说明 agent 对话入口、用户可复制 prompt、高自动化阶段入口和人类审核点。权威输入仍是 `onboarding/` 下的 schema、manifest、access review、provider review、hard constraints、failure recovery 和 acceptance 文档；本文不替代这些文件，也不新增 coordinator 或 worker 合约。

## 使用原则

Provider onboarding 以两个人工 gate 推进：先审核 access/waterfall 预案，再审核最终 Markdown 质量。中间的 discovery、purpose 覆盖、fixture capture、cleaning proposal、implementation、snapshot、fresh Markdown quality review、repair loop、sync-back 和 local acceptance 都应由 AI/coordinator 尽量自动完成；人类不再逐 fixture 编辑 review artifact。

第一个 gate 是 `waterfall-preflight-review`：AI 用 `prepare-human-preflight` 汇总合法访问、allowed runtime、waterfall 顺序、route success/rejection 条件、purpose coverage 和 null proof；人类只批准 access review 与 waterfall/purpose 预案。第二个 gate 是 `final-markdown-quality-review`：AI 完成所有机器 gate 后，人类只阅读当前 `extracted.md`、`markdown-quality.json`、fresh review 摘要和 purpose 覆盖表；确认后运行 `finalize-review-artifact --confirmed-final-quality`，由脚本机械写入 `onboarding/reviews/<provider>.yml` 中每个 fixture 的最终 signoff。

## Agent 对话入口

本节是普通用户在 agent 对话里自助添加 provider 的入口。用户不需要学习 runner DAG、state JSON 或 worker prompt；agent 负责把一句自然语言请求转成项目内 onboarding 流程，并在必须人工判断时停下，给出文件、确认事项和下一句可回复的话。

对 agent 来说，权威输入仍是 `onboarding/` 下的 schema、manifest、access review、provider review、hard constraints、failure recovery 和 acceptance 文档。执行后端必须使用项目代码和项目脚本，不能用 Agent 自带的 paper-fetch MCP、Skill 或外部环境 CLI 替代项目实现。`scripts/provider_agent.py` 只是 agent-facing 包装层：它不维护独立 DAG、不维护独立 state、不替代 `onboard_from_manifests.py` 或 `onboarding/`。

### 用户对话模型

agent 应支持这些自然语言入口：

```text
添加 foo provider，domain 是 foo.org
添加 foo provider，domain 是 foo.org，DOI prefix 是 10.xxxx
添加 foo provider，domain 是 foo.org，目标 merge-ready
继续 foo provider
继续 foo provider 到 merge-ready
查看 foo provider 状态
诊断 foo provider 为什么卡住
```

首次发起时按下列规则抽取字段：

| 输入字段 | 规则 |
|---|---|
| provider 名称 | 从用户请求中抽取；无法确定时追问。 |
| domain | 如果用户提供则使用；如果已有 manifest 可从 manifest 继续；否则追问。 |
| DOI prefix | 用户提供则作为 discovery seed；缺失时不追问，交给 discovery。 |
| 目标档位 | 用户明确说 `merge-ready` 才使用 `merge-ready`；否则默认 `local-ready`。 |
| 页面类型 | 默认不追问；如用户主动说明 HTML/XML/browser/PDF，可作为 discovery hint。 |

首轮确认应短而具体：

```text
我会按 onboarding/instruction.md 添加 foo provider，默认目标 local-ready。
我会先检查 access review、manifest 和当前 state；如果需要你确认访问策略，我会停下并指出要改哪个文件。
```

当用户说“继续”时，agent 必须优先从现有 state、manifest、access review、review artifact 和 run logs 恢复，不重新开始。只有当前 state 与用户目标冲突，或无法确定 provider 身份时，才追问。

### Agent-facing 命令

```bash
PYTHONPATH=src python3 scripts/provider_agent.py add --provider foo --domain foo.org
PYTHONPATH=src python3 scripts/provider_agent.py continue --provider foo
PYTHONPATH=src python3 scripts/provider_agent.py status --provider foo
PYTHONPATH=src python3 scripts/provider_agent.py doctor --provider foo
```

默认目标是 `local-ready`，即跑到 `provider-local-acceptance` 后停止并提示“不等于 merge-ready”；用户明确要求“继续到 merge-ready”时再传 `--target merge-ready`。

两个面向用户的简洁检查命令：

```bash
python3 scripts/onboard_from_manifests.py prepare-human-preflight --provider foo --domain foo.org
python3 scripts/onboard_from_manifests.py finalize-review-artifact --provider foo --confirmed-final-quality
```

### 用户可见状态

agent 对用户展示简化状态，不直接展示 runner task DAG：

| 状态 | 进入条件 | agent 行为 | 用户可见结果 |
|---|---|---|---|
| `intake` | 收到添加、继续、状态或诊断请求 | 抽取 provider、domain、DOI prefix、目标档位 | 确认目标或追问缺失必需信息 |
| `preflight` | 已确定 provider，准备读取仓库状态 | 检查 git 状态、onboarding 文档、manifest、access review、state | 告知将使用项目脚本推进 |
| `running` | 没有人工 gate，且存在可自动推进步骤 | 调用项目脚本推进、诊断、修复、重试 | 输出进度摘要或继续到下一状态 |
| `user-gate` | 到达 waterfall/access preflight 或最终 Markdown semantic review | 停止自动推进，列出人工确认项 | 给出文件、确认事项和用户下一句话 |
| `blocked` | non-retryable failure、retry exhausted、缺少新事实或越界写入 | 翻译 failure code，保留 artifact 路径 | 给出阻塞原因和可执行下一步 |
| `local-ready` | 主路径本地可用，最小 provider-owned 验证通过 | 停止默认目标，提示升级路径 | 明确“不等于 merge-ready” |
| `merge-ready` | 完整 acceptance 和人工签字完成 | 输出完成摘要、验证命令和剩余风险 | 可以宣称达到合入标准 |

状态转换原则：

- `intake` 缺 domain 且没有现成 manifest 时，停下追问 domain。
- `preflight` 发现 access review 未批准时，进入 `user-gate`。
- `running` 遇到 retryable failure 时，先按 [`failure-recovery.md`](./failure-recovery.md) 自动恢复；只有需要人工事实或预算耗尽时才进入 `blocked`。
- `running` 达到默认目标时进入 `local-ready`，不继续追求完整 acceptance。
- 用户明确要求“继续到 merge-ready”时，从 `local-ready` 或当前 state 进入 `running`，直到 `merge-ready`、`user-gate` 或 `blocked`。

`local-ready` 表示 access review 已人工批准，manifest 已生成并通过当前阶段需要的 schema/proof 校验，至少一个主路径 DOI sample 可本地抓取或 replay，provider-owned skeleton/implementation 已生成，且最小 provider-local 验证通过。它不能承诺 shared docs、完整 fixture coverage、review artifact 人工签字、expected snapshots、global lint 或完整 acceptance。

`merge-ready` 表示 manifest、fixture、route、asset、Markdown contract、provider review gate、expected snapshots、manifest sync-back、provider-local acceptance、shared integration、global lint、docs drift 和 extraction rules validation 均通过；`onboarding/reviews/<provider>.yml` 已由人工完成语义审查，shared docs、changelog 和 `onboarding/known-providers.yml` 已同步。

达到默认目标后，agent 应这样停下：

```text
foo 已达到 local-ready：主路径本地可用，最小 provider-local 验证通过。
这还不是 merge-ready；如果要继续做到完整合入标准，请告诉我：继续 foo provider 到 merge-ready。
```

### 人工 Gate 输出

用户只需要理解两个强制人工 gate：waterfall/access 预检和最终 Markdown 批量语义审查。其他失败应由 agent 先自动诊断、修复或翻译成具体行动；不要把用户拉进逐 fixture YAML 签字。

停在 waterfall/access preflight 时输出：

```text
当前卡在: waterfall/access preflight

你需要改:
onboarding/access-reviews/foo.yml

你需要看:
- python3 scripts/onboard_from_manifests.py prepare-human-preflight --provider foo

你需要确认:
- 合法访问来源是否允许继续
- allowed_runtimes 是否允许当前路线
- challenge/CAPTCHA/paywall 策略是否可接受
- waterfall 顺序、route 成功/拒绝条件和 purpose coverage 计划是否合理
- status 和 may_continue 是否应由你批准

确认后对我说:
继续 foo provider

相关文件:
- onboarding/access-reviews/foo.yml
- onboarding/onboarding-state.json
```

停在 Markdown semantic review 时输出：

```text
当前卡在: Markdown semantic review

你需要看:
- tests/fixtures/.../extracted.md
- tests/fixtures/.../markdown-quality.json
- onboarding/reviews/foo.yml

你需要确认:
- Markdown 是否保留正文结构、references、figure/table/formula 等语义
- 是否没有站点 chrome、access noise、重复 boilerplate 或错误页内容
- persistent/fresh quality 是否均为 pass 且无 blocking issue
- 是否可以运行 finalize-review-artifact 写入最终 signoff

确认后对我说:
已确认最终 Markdown 质量，继续 foo provider 到 merge-ready
```

如果 fresh review 仍有 blocking issue，agent 必须继续 repair 或明确阻塞，不能提示用户用人工签字绕过机器可判缺陷。

### 输出协议

agent 对用户的回复分为进度、人工 gate、自动失败、`local-ready`、`merge-ready`。所有回复都应短、具体、面向下一步。

普通进度：

```text
当前状态:
- provider: foo
- 目标: local-ready
- 阶段: running

已完成:
- access review 已批准
- manifest 已生成并通过 schema
- fixture capture 正在推进

我接下来会做:
- 继续运行项目 runner 到下一个人工 gate 或 local-ready

相关文件:
- onboarding/manifests/foo.yml
- .paper-fetch-runs/foo-onboarding/
```

人工 gate：

```text
当前状态:
- provider: foo
- 目标: local-ready
- 阶段: user-gate

为什么停:
- access review 还没有人工批准，agent 不能替你批准合法访问策略

你需要做:
- 打开 onboarding/access-reviews/foo.yml
- 确认 allowed_runtimes、challenge_policy、status、may_continue

确认后对我说:
- 继续 foo provider

相关文件:
- onboarding/access-reviews/foo.yml
- onboarding/onboarding-state.json
```

自动失败：

```text
当前状态:
- provider: foo
- 目标: local-ready
- 阶段: blocked

为什么停:
- 当前 DOI 样本不适合 figure purpose
- failure code: UNSUITABLE_DOI_SAMPLE

我接下来会做:
- 只替换 fixtures.doi_samples.figure
- 重新 capture figure fixture

如果需要你提供新事实:
- 请提供一个包含正文图片的 foo DOI

相关文件:
- onboarding/manifests/foo.yml
- .paper-fetch-runs/foo-onboarding/
```

`local-ready`：

```text
当前状态:
- provider: foo
- 目标: local-ready
- 阶段: local-ready

已完成:
- 主路径 DOI 可本地抓取或 replay
- provider-owned implementation 已生成
- 最小 provider-local 验证通过

尚未承诺:
- 完整 fixture coverage
- Markdown semantic review
- expected snapshots
- shared docs / changelog
- global lint / merge-ready acceptance

下一步:
- 如需完整合入标准，请告诉我：继续 foo provider 到 merge-ready
```

`merge-ready`：

```text
当前状态:
- provider: foo
- 目标: merge-ready
- 阶段: merge-ready

已完成:
- provider-local acceptance 通过
- global lint / docs drift / manifest sync-back 通过
- Markdown semantic review 已人工签字

运行过的验证:
- <列出关键本地命令和结果>

剩余风险:
- <如无剩余风险，写“未发现未解决风险”>
```

### 状态与失败翻译

agent 应把 runner failure code 翻译成用户行动，不把未解释 traceback、raw JSON state 或完整 DAG 直接交给普通用户：

| Failure code | Agent 对用户的表达 |
|---|---|
| `ACCESS_REVIEW_NOT_FOUND` | 我需要生成或定位 access review 草稿；你稍后只需确认访问策略。 |
| `ACCESS_REVIEW_NOT_APPROVED` | 我停在访问批准点；请人工确认 access review 后告诉我继续。 |
| `ACCESS_REVIEW_SCHEMA_INVALID` | access review 文件结构不合法；我会指出字段，用户只需确认真实访问策略。 |
| `BROWSER_RUNTIME_REQUIRED` | 当前路线需要 browser runtime；请决定是否允许，不能默认绕过。 |
| `HTTP_FORBIDDEN` | 当前样本被拒绝；若 access review 允许 browser 我会重试，否则我会换 DOI 或停下说明。 |
| `HTTP_RATE_LIMITED` / `NETWORK_TRANSIENT` | 这是暂态或限流；我会按 retry budget 重试，耗尽后给出等待或换样本建议。 |
| `CHALLENGE_DETECTED` | 遇到 challenge/CAPTCHA；我不会绕过，只能按 access review 重试或换样本。 |
| `UNSUITABLE_DOI_SAMPLE` | 这个 DOI 不适合当前 purpose；我会只替换这个 purpose 的样本。 |
| `NON_PDF_FALLBACK_CONTENT` | PDF fallback 样本不是 PDF；我会重新找 `pdf_fallback` 样本。 |
| `ACCESS_GATE_CAPTURED` / `EMPTY_ARTICLE_SHELL` | 样本捕获到 access gate 或空文章壳；我会替换失败 purpose 的 DOI。 |
| `MARKDOWN_CONTRACT_DRIFT` | Markdown contract 与当前 fixture 不一致；我会先刷新 cleaning proposal 或回到实现修复。 |
| `MARKDOWN_QUALITY_FAILED` | 当前 Markdown 还有 blocking issue；我会运行 repair loop，失败后给出具体 artifact。 |
| `MARKDOWN_QUALITY_REPAIR_FAILED` | 自动修复预算耗尽；需要人工看最后一轮 quality report 和 repair logs。 |
| `PROVIDER_LOCAL_ACCEPTANCE_FAILED` | provider-local 验证失败；我会修 provider-owned 实现或测试，并汇报失败命令。 |
| `SHARED_INTEGRATION_FAILED` | shared integration 验证失败；我会只修有 manifest/fixture/test 证据支持的 shared surface。 |
| `GLOBAL_LINT_FAILED` | 全局本地检查失败；我只修当前 provider 引入的问题。 |
| `WORKER_MODIFIED_FORBIDDEN_FILE` | worker 修改了不该改的文件；我会停下保护工作区并说明越界路径。 |
| `DISCOVERY_RETRY_EXHAUSTED` / `TASK_RETRY_EXHAUSTED` | 自动重试耗尽；我会列出失败 task、最近命令、artifact 路径和需要的新事实。 |

### 样本候选展示

fixture discovery 和 sample review 应以用户可读表格展示：

```text
样本候选:
- structure: 10.xxxx/aaaa confidence=high，证据: landing + article body
- figure: 10.xxxx/bbbb confidence=high，证据: body image/caption
- table: 10.xxxx/cccc confidence=medium，证据: table caption
- formula: null，原因: 候选检索已耗尽，未找到稳定公式样本
```

展示规则：

- 高置信样本默认继续 capture。
- DOI prefix 缺失时不追问用户，先让 discovery 自行寻找候选。
- 低置信、互相矛盾、访问异常或 null 证据不足时，agent 先自动诊断和建议替换。
- 只有需要真实判断或新事实时，agent 才停下请用户确认。
- 替换样本时，只替换失败 purpose 的 `fixtures.doi_samples.<purpose>`，不能因为一个 DOI 失败重写无关 purpose。

### 用户可复制 Prompt

普通用户只需要在 agent 对话中使用本节 prompt。下面的 `<provider>`、`<domain>`、`<doi-prefix>` 按实际值替换；不知道 DOI prefix 时可以删掉该句。agent 收到这些 prompt 后，应调用上面的项目脚本和 coordinator 流程，不要求用户逐 fixture 检查或编辑 review YAML。

#### 新增 provider，默认做到 local-ready

```text
请帮我新增 provider：<provider>，domain 是 <domain>，DOI prefix 是 <doi-prefix>。
按 onboarding agent 流程执行：先跑到 access/waterfall/purpose preflight，让我检查 access review、waterfall 和 purpose coverage；我确认后继续自动完成 discovery、fixture、实现、snapshot、Markdown quality repair 和 local acceptance。中间不要让我逐 fixture 签字。最终只在 final Markdown quality review 停下，让我批量检查当前 extracted.md / markdown-quality.json / fresh review。默认先做到 local-ready，不触发 GitHub CI，不提交 commit。
```

#### 新增 provider，但直接要求完整合入标准

```text
请帮我新增 provider：<provider>，domain 是 <domain>，DOI prefix 是 <doi-prefix>。
按 onboarding agent 流程推进到 merge-ready：先停在 access/waterfall/purpose preflight 等我确认；确认后自动完成中间链路；最后停在 final Markdown quality review 等我批量确认，再写入 review artifact 并继续 merge-ready 检查。不要让我逐 fixture 编辑 review YAML，不触发 GitHub CI，不提交 commit。
```

#### 人工确认 preflight 通过

```text
我已检查 access review、waterfall 顺序、route success/rejection 条件、allowed runtime、challenge/paywall 策略和 purpose coverage，preflight 合理。请继续自动完成后续 discovery、fixture、实现、snapshot、Markdown quality repair 和 local acceptance；只在 final Markdown quality review 再停下。
```

#### 人工要求修改 preflight

```text
preflight 需要修改：<写清楚要改的 access/waterfall/purpose/null proof/asset contract 问题>。
请先更新对应 manifest/access review/预检摘要，然后重新生成 preflight 给我复核；不要进入 fixture 或实现阶段。
```

#### 继续已有 provider

```text
请继续 <provider> provider 的 onboarding，从当前 state 恢复执行。默认目标 local-ready；如果遇到 access/waterfall preflight 或 final Markdown quality review，请停下并告诉我要看哪些文件、确认后应该回复哪句话。
```

#### 查看当前状态

```text
请查看 <provider> provider 当前 onboarding 状态，用用户可读摘要说明：当前阶段、目标档位、最近执行的项目命令、是否卡在人工 gate、需要我看的文件、下一步我应该回复什么。
```

#### 诊断卡住原因

```text
请诊断 <provider> provider 为什么卡住。不要只贴 traceback；请把 failure code、涉及文件、可自动修复项、需要我提供判断的事项和建议下一句 prompt 汇总出来。
```

#### 用户补充信息后恢复

```text
我已补充或修正阻塞信息：<写清楚已批准、已改文件、已提供 DOI、已确认访问策略或其他事实>。
请从当前 state 继续执行；能自动修复的继续自动修复，仍需要人工判断时再停下。
```

#### 最终 Markdown 质量确认通过

```text
我已批量检查 <provider> 当前所有 non-null fixture 和 extra_fixtures 的 extracted.md、markdown-quality.json、fresh review 摘要、purpose 覆盖和 asset contract，最终 Markdown 质量人工确认通过。请运行 final review artifact 写入流程，把 markdown_semantic_reviewed 写入真实 signoff，然后继续到目标档位。
```

#### local-ready 后升级到 merge-ready

```text
<provider> 已达到 local-ready。请继续推进到 merge-ready；如果最终 Markdown quality review 还没有人工 signoff，请先停在那里等我确认，不要伪造签字。
```

#### 暂停但保留上下文

```text
请暂停 <provider> provider onboarding，并输出当前 state、已完成事项、未完成 gate、下次恢复应使用的 prompt 和不应重复执行的步骤。
```

## 1. 准入与启动

### 目标

让 AI/coordinator 自动准备 provider onboarding 的启动上下文、access review 草稿或状态诊断、worker 边界、waterfall/purpose 预案和可继续计划；人类只审核合法访问、allowed runtime、challenge/CAPTCHA/paywall 策略、临时站点策略、waterfall 顺序和 purpose coverage 计划，并在确认后批准 access review。

### `/goal` 提示词

```text
/goal 按 onboarding/ 权威输入尽量自动启动 provider <provider> 的 onboarding。

目标：使用项目脚本自动完成准入准备、启动上下文、worker 边界检查和可继续计划；若 access review 已由 operator 批准，则继续启动 runner 到当前阶段可达的最远点。人类只负责审核 access review、访问策略和阻塞摘要。

自动化要求：
- 读取 onboarding/README.md、coordinator-spec.md、hard-constraints.md、failure-recovery.md、acceptance.md、automation-roadmap.md 和相关 schema，确认当前 DAG、state、worker 边界和 operator-only gate。
- 检查 onboarding/access-reviews/<provider>.yml；若缺失或 blocked，优先用项目脚本生成/更新 blocked 草稿和 operator digest，列出建议的合法访问模式、allowed runtime、禁止行为、challenge/CAPTCHA/paywall 策略和临时站点策略，等待人类审核。
- 若 manifest 已存在，运行 `python3 scripts/onboard_from_manifests.py prepare-human-preflight --provider <provider>`，把 main_path、route_contract、route_sources、asset_contract、purpose coverage、mandatory discovery proof 和 null reason 汇总成人类可读预检。
- 若 access review 已符合 schema、status: approved 且 may_continue: true，使用项目 runner/verify/run-checks 自动生成 task DAG、brief、discovery evidence pack 或继续已有 manifest，并推进到下一个需要人类审核或结构化 blocker 的位置。
- 对 ACCESS_REVIEW_NOT_FOUND、ACCESS_REVIEW_NOT_APPROVED、BROWSER_RUNTIME_REQUIRED、CHALLENGE_DETECTED、HTTP_FORBIDDEN、HTTP_RATE_LIMITED 等 operator-only 阻塞，运行 diagnose 或 resume-blocked --dry-run 形成可审计摘要，不靠自然语言豁免继续。

边界：
- 可以生成草稿、摘要、dry-run artifact、state、brief 和诊断；不能在未获人类批准时把 access review 改成 approved 或把 may_continue 当作 true。
- 不自动登录、不处理 CAPTCHA、不绕过 challenge/paywall，不发明临时站点策略。
- 不触发 GitHub CI，不提交 commit。

完成后输出：已执行的项目命令或 dry-run 计划、access review 当前状态、waterfall/purpose 预检摘要、是否已经允许进入自动 fixture/implementation 阶段、自动推进到的 task、结构化阻塞原因，以及需要人类审核/批准的具体字段。
```

### 人类审核点

- `onboarding/access-reviews/<provider>.yml` 是否存在、符合 schema，且 `status` 与 `may_continue` 是人类审核后的真实批准结果。
- AI 生成的合法访问模式、allowed runtime、登录需求、challenge/CAPTCHA/paywall 风险、限流风险和允许抓取方式是否可接受。
- `onboarding/hard-constraints.md` 中的 worker scope 是否能约束后续自动任务，尤其是不得绕过访问控制、不得写 secrets、不得触碰禁止路径。
- provider 名称、domain、DOI prefix 或已有 manifest 是否与启动目标一致，避免把一个 provider 的批准用于另一个 provider。
- `prepare-human-preflight` 输出的 waterfall 顺序、route success/rejection 条件、asset contract 和 purpose coverage 计划是否合理。

### 通过标准

- access review 已由人类审核批准，且没有未解释的访问异常。
- AI 已生成或更新可审计的 state、brief、diagnosis/summary，后续 worker 的输入范围、可写路径和停止条件清楚。
- 若未批准、低信任或访问状态不明，AI 已停在 operator gate，并明确列出人类需要决定的字段。

## 2. 自动 Fixture / Purpose 闭环

### 目标

让 AI 自动生成或验证 manifest fixture 覆盖、discovery proof、本地 fixture 和 cleaning evidence。该阶段不再设置单独人工审核点；低置信、矛盾、不可用或证据不足的样本应由 AI 自动替换、写入具体 rejection，或以 structured blocker 停下。

### `/goal` 提示词

```text
/goal 自动检测并补齐 provider <provider> 的 fixture 覆盖与代表性证据。

目标：根据 onboarding/manifests/<provider>.yml、discovery evidence pack、fixture 目录和 cleaning proposal，尽量自动完成 manifest discovery/validate/autofix、fixture capture、cleaning proposal、inspect-discovery 和本地 fixture gate；不要把用户拉入逐 fixture 检查，除非出现需要新事实的 structured blocker。

自动化要求：
- 若没有 manifest 且 access review 已批准，派 discover-manifest worker 生成 onboarding/manifests/<provider>.yml；若已有 manifest，则从现有 manifest 继续。
- 运行或规划 validate-manifest，并使用允许的 autofix 补齐机器可判 schema/proof/contract 缺口；低置信 DOI candidate 只能记录 proof/rejection，不能静默替换为通过结论。
- 自动捕获所有 non-null DOI sample 和 extra_fixtures，按 failure-recovery 处理 UNSUITABLE_DOI_SAMPLE、ACCESS_GATE_CAPTURED、EMPTY_ARTICLE_SHELL、NON_PDF_FALLBACK_CONTENT、NETWORK_TRANSIENT 等结构化错误。
- 自动生成/校验 cleaning-chain proposal，并用 inspect-discovery 或 summary 汇总每个 fixture purpose 的 DOI、confidence、observed_signals、evidence_url、evidence_reason、本地 fixture 路径和 proof 状态。
- 对 table、formula、supplementary 的 discovery_proof，自动检查 queries、candidates、selected_doi、rejections、exhausted 和 evidence_summary 是否能证明选择或 null 结论；对 optional null purpose，可用同样 proof 结构记录 exhausted signoff。

边界：
- 不把低置信、样本不可用、proof 与本地 fixture/cleaning evidence 矛盾、null purpose 解释不足的情况自动标成已通过；必须输出为人类审核项或回到 discovery 替换样本。
- 不提前签署 markdown_semantic_reviewed: true；Markdown 语义终审留到实现收口阶段。
- 不触发 GitHub CI，不提交 commit。

完成后输出：自动执行/规划的命令、每个 fixture purpose 的 DOI 与 confidence、capture/cleaning/manifest gate 结果、缺失或矛盾证据、已自动修复或替换样本动作，以及仍需要新事实才能继续的 blocker。
```

### 机器验收点

- `fixtures.doi_samples` 覆盖所有固定 purpose；`structure`、`figure`、`references` 为非空 DOI。
- 每个非空 DOI 有可审计的 `evidence_url`、`evidence_reason`、`observed_signals`、本地 fixture 路径和可信的 `confidence`。
- `fixtures.discovery_proof` 对 `table`、`formula`、`supplementary` 记录足够查询、候选、拒绝理由和选择依据；optional null purpose 若需要关闭人工 proof 状态，也记录 exhausted proof。
- `doi: null` 的 optional purpose 有 exhausted proof；若本地 fixture 或 cleaning evidence 已显示相关强信号，必须提升 DOI 或写具体 rejection。
- 本地 fixture 路径与 manifest DOI 和 purpose 对应，且样本不是 access gate、空壳或错误页伪装成正文。

### 通过标准

- AI 已自动完成或明确规划 manifest validate/autofix、fixture capture、cleaning proposal 和 fixture gate，所有失败都有 structured code 或可审计原因。
- 每个必需 fixture purpose 都有明确、可追溯、与本地证据一致的结论。
- 低置信样本已由 AI 按 failure recovery 替换为更可靠样本，或以 structured blocker 要求用户提供新事实。
- null purpose 有充分 exhausted proof，且没有与本地证据矛盾。
- Fixture 阶段只给出进入实现的许可，不给出 Markdown 语义终审许可。

## 3. 剩余实现与 Markdown 终审

### 目标

让 AI 自动完成 provider 实现收口、本地验收、snapshot、fresh Markdown quality review、repair loop、manifest sync-back、shared integration 和 operator digest；人类只基于当前 `extracted.md`、真实 `markdown-quality.json`、`onboarding/reviews/<provider>.yml` 和 run records 审核最终 Markdown 语义签字。

### `/goal` 提示词

```text
/goal 尽量自动收口 provider <provider> 的剩余实现并准备 Markdown 终审。

目标：根据 onboarding/manifests/<provider>.yml、onboarding/reviews/<provider>.yml、当前 fixture extracted.md、真实 markdown-quality.json、cleaning proposal 和 acceptance 文档，自动推进 implement-provider、shared-integration、snapshot-expected、manifest-sync-back、provider-local-acceptance、global-lint 和 merge-ready 前检查；人类只审核最终 artifact 和 operator-only 语义结论。

自动化要求：
- 以 manifest 的 route_contract、markdown_contract、asset_contract、probe、main_path 和 hard constraints 为唯一 provider 行为输入，自动派 implement-provider worker 或继续已有实现。
- 自动把 route_contract 和 markdown_contract 固化为 provider-local route/Markdown 正负断言；每个修复必须先有 provider-local 测试或明确的 shared renderer/workflow 证据。
- 自动生成/刷新 expected snapshots、extracted.md、markdown-quality-prompt.md 和 agent-authored markdown-quality.json；运行 fresh Markdown quality review，发现 blocking issue 时进入最多 3 轮 repair-markdown-quality 闭环。
- 自动校验 figure asset contract：正文内联位置、本地文件落盘、字节数、asset result state 和最终 Markdown 本地路径 rewrite；不满足时回到实现或 manifest 修复。
- 自动执行 manifest-sync-back、provider-local acceptance、review/provider contract、bundle completeness、owner reuse、docs validation 和可用的 local runner gate，并生成 operator summary。

边界：
- 不能只信旧 markdown-quality.json、worker 总结或 bootstrap 草稿；必须回到当前 extracted.md、fresh review 和 run records。
- 存在 fresh blocking issue、pending/fail quality report、缺少 provider-local 断言、asset contract 不满足或 review artifact 不一致时，不得通过。
- 可以准备或更新 review artifact 中可由证据支持的字段；`markdown_semantic_reviewed: true` 只能在用户完成最终批量质量审核后，通过 `finalize-review-artifact --confirmed-final-quality` 机械写入。
- 不触发 GitHub CI，不提交 commit。

完成后输出：自动执行的实现/验收/repair/sync-back 结果、剩余失败或 structured blocker、每个 fixture 的 Markdown 质量结论、figure asset 结论、review artifact 与当前 extracted.md/markdown-quality.json 是否一致，以及一条最终命令：`python3 scripts/onboard_from_manifests.py finalize-review-artifact --provider <provider> --confirmed-final-quality`。
```

### 人类审核点

- provider-local 测试是否覆盖每个非空 fixture purpose、每个 `route_contract` step，以及 `markdown_contract` 的正向和负向断言。
- 当前 `extracted.md` 是否包含预期正文、结构、引用、表格、公式、图片或补充材料信号，并排除站点 chrome、access noise、重复 boilerplate 和错误页内容。
- `pdf_fallback` fixture 的 Markdown 是否来自 shared `pymupdf4llm` text-only 转换；provider 不应另加 PDF Markdown cleanup、front matter reconstruction、水印移除或 reference extraction。
- `markdown-quality.json` 与 fresh review 是否对应当前 `extracted.md`，且没有 blocking issue。
- `finalize-review-artifact` 是否能在当前文件上通过：每个非空 fixture 和 `extra_fixtures` 都有路径、sha256、review notes、assertions、`sample_representative: true` 和 `markdown_semantic_reviewed: true`。
- `asset_contract.figures.inline: body` 时，正文中的 Markdown 图片是否位于 References/Figures/Supplementary 等尾部 section 之前。
- `asset_contract.figures.download: required` 时，provider-local 断言是否覆盖本地文件路径、字节数、asset result state 和最终 Markdown 链接重写。

### 终审通过标准

- AI 已自动完成或明确阻塞在 implement-provider、shared-integration、snapshot-expected、manifest-sync-back、provider-local-acceptance、global-lint 或 merge-ready 前检查，并提供 run records。
- 实现只修改允许的 provider-owned 文件、review artifact 和可追溯的 shared integration 文件，没有触碰禁止路径或中心 provider-specific 逻辑。
- 本地验收通过，且失败、跳过或 warning 都有明确解释。
- 当前 `extracted.md`、`markdown-quality.json`、fresh review 和 `onboarding/reviews/<provider>.yml` 四者一致。
- 每个非空 fixture 和 `extra_fixtures` 都完成人类审核后的真实语义审查；没有 TODO、TBD、unknown 或 bootstrap 占位。
- figure asset contract 满足 manifest 要求；不满足时必须阻塞并说明原因。

## 最大自动化边界

- AI 可以生成草稿、运行项目脚本、派 worker、修复机器可判缺口、替换不合适样本、刷新 snapshot/quality/report，并生成 operator digest。
- Access approval 不能由脚本伪造；`status: approved` 和 `may_continue: true` 只能在人类审核合法访问、runtime、challenge/CAPTCHA/paywall 和临时站点策略后成立。
- AI 不自动登录、不处理 CAPTCHA、不绕过 challenge 或 paywall，也不发明临时站点策略。
- AI 不能把 `markdown_semantic_reviewed: true` 当作纯机器结论；最终语义签字必须基于人类对当前 `extracted.md`、真实 `markdown-quality.json`、fresh review 和 review artifact 的批量审核，并通过 `finalize-review-artifact --confirmed-final-quality` 写入。
- 不触发 GitHub CI；验收以本地、repo-owned artifact 和 acceptance 文档为准。
- 低置信 fixture、样本不可用、null purpose 证据不足、访问异常、retry exhaustion 或 blocked state 必须由 AI 先自动诊断/汇总，再交给人类审核或按 failure recovery 返回前序自动步骤。
- Worker 回复和临时日志只能作为辅助材料；最终判断以 manifest、fixture、quality report、review artifact、state run records 和本地验收结果为准。
