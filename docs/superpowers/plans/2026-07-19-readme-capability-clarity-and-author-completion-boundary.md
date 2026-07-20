# Draftpaper-loop v0.32.1–v0.33.0 优化方案

> **目标**：不改变现有 README 的整体框架，补清版本能力与完整科研流程；同时完善最终作者补全和 Result Support，使正文、图表、指标、证据与人工决策始终属于同一版本。

---

## 1. 一页读懂本轮要做什么

本轮不重构 Draftpaper-loop，也不再增加一套新的术语体系，只处理三个用户能够直接感知的问题。

### 1.1 README 说清“现在能做什么”

保留 README 原有一级模块、顺序和主要内容，只局部补充：

- v0.30.1–v0.33.0 各版本新增了什么能力；
- 从 idea、研究蓝图、数据和方法到图表、正文与 `main.pdf` 的完整流程；
- 哪些阶段需要人工确认；
- 最终稿生成后，用户如何一次性补齐作者信息并精确修改正文；
- 哪些内容只是 fixture 或 mock，哪些内容可作为真实论文证据。

### 1.2 最终作者补全既方便又不破坏证据链

用户只填写一份 completion packet，就可以补充：

- 作者、单位、通讯信息、基金、致谢和声明；
- 数据链接、代码链接和新增参考文献；
- 按“章节 + 行号 + 上下文 + 内容 hash”定位的正文增删改。

系统在 preview 阶段自动判断这次修改只是排版或表述调整，还是改变了数据、方法、结果、论断或研究设计，并明确显示需要重新打开的阶段。

### 1.3 结果支撑不足时只保留两条清楚的路线

```text
结果能够支撑研究蓝图
  → 继续 Results 和后续全文写作

结果不足以支撑研究蓝图
  → 在一个集中人工确认点选择：
     A. 收窄论断：保留当前图表和指标，只改 claim boundary 与正文
     B. 补数据/方法：重新执行相关数据、方法、run、图表和正文链路
```

同一次 Result Support checkpoint 只执行一条路线，避免一部分论断冻结、另一部分证据重跑后混入同一稿件。

---

## 2. 哪些外部建议值得采纳

其它模型给出的建议是审阅意见，不是必须全部执行的需求。以下内容经过现有代码合同、用户操作成本和维护成本三方面核对后，保留其中七项。

### 2.1 采纳：严格分类前先做校准

completion 分类器对“普通方法说明”和“新增科学方法”确实存在灰区，直接严格拒绝可能误伤正常作者补全。

落地方式不是固定运行“一周”，而是使用可验收的校准门槛：

- 至少 60 条人工标注样例；
- 至少覆盖 3 个学科；
- 科学变化被误判为普通文字的数量为 0；
- 合法作者补全的误拦截率不高于 5%。

在达到门槛前，preview 同时显示用户声明分类和系统判断分类；分类不一致时采用影响范围更大的分类计算 stale 范围。证据引用校验始终严格。

### 2.2 采纳：自动建议 `evidence_refs`

要求普通用户手写 JSON pointer、run ID 和 hash 的操作成本过高。

preview 应从当前项目的只读材料中自动提出候选引用：

- stage code manifest；
- selected run manifest；
- result evidence registry；
- figure/result/plugin trace；
- 当前 evidence snapshot。

用户只需确认或删除候选。若正文声称某项数据处理或方法已经执行，但没有与当前 run、cohort 和 snapshot 一致的证据，则这条修改进入 `classification_refinement_required`，而不是冒充普通润色。

### 2.3 采纳：明确整单路线边界

当前版本按一个 Result Support checkpoint 为整篇稿件选择一条路线，不支持 claim A 收窄、claim B 同时补数据的混合事务。

这是当前版本主动保留的边界，不作为本轮缺陷继续扩展。系统应返回 `mixed_route_not_supported`，保持原状态，并在 README 中明确说明。

### 2.4 采纳：合并对外发布，内部仍分阶段提交

不为每个内部小步骤创建一个公开 patch 版本。代码按 M0–M3 分开开发和测试，对外合并为：

- v0.32.1：能力说明与 README 局部优化；
- v0.32.2：作者补全分类、证据引用与 Result Support v3；
- v0.33.0：严格模式、完整回归和正式发布。

这样保留可回滚的小提交，同时减少 tag、wheel 和跨平台发布验证的重复劳动。

### 2.5 采纳：CLI、Agent、文档和 wheel 同步更新

Result Support 路线命令增加 checkpoint hash 后，必须同时更新：

- CLI CommandSpec 与命令实现；
- `draftpaper-workflow` skill 和 Agent 合同；
- CLI reference、README 示例与命令风险矩阵；
- wheel 中内置的 workflow/resource 副本；
- 依赖旧参数的测试和脚本。

这可以避免 README 已使用新命令，而 Agent 仍调用旧命令。

### 2.6 部分采纳：能力真值矩阵只锁定事实

能力真值矩阵用于校验以下事实：

- capability ID；
- 已实现、实验性或规划中的状态；
- 首次出现的 minor 版本；
- 对应命令、源码、artifact 和测试；
- 中英文 README 的能力边界。

它不逐字锁定 README 的自然语言，也不参与运行时科学判断。`since` 精确到 minor 版本即可，避免形成第二套高维护文档。

### 2.7 采纳：required data role 无绑定时不得静默通过

处理规则固定为：

- active claim 或主图声明为 required 的 data role 没有任何 binding：Result Support 不得通过，进入路线选择；
- 与 active claim/figure 绑定的 pending task：进入路线选择；
- optional 且与当前研究无关的 task：只提示，不阻塞；
- scope 不完整且系统判断不了是否相关：给出明确警告并要求补齐 task binding，不静默忽略。

---

## 3. 哪些建议不纳入本轮

### 3.1 不增加 `--force-class`

该参数会形成绕过证据和 stale 传播的旁路。分类不合适时，用户可以修改 completion packet 的表述或补充证据，系统也会显示判定原因，但不提供跳过科学合同的入口。

### 3.2 不把“一周 shadow”作为验收条件

运行时间长短不能证明分类可靠。以人工标注样例、科学漏判数和合法修改误杀率作为切换严格模式的条件，更容易复现和自动验收。

### 3.3 不建立第二套 change taxonomy

所有用户表述最终映射到 `change_impact.CHANGE_CLASS_SPECS` 中已有的 canonical class。`scientific_evidence_change` 等旧名称只能作为兼容别名，必须继续解析为现有的 data、method、result、claim 或 research-plan 类别。

### 3.4 不在本轮实现多 claim 混合路线

claim 级事务需要独立的 evidence snapshot、stale graph 和合并规则，复杂度明显高于当前需求。本轮只把限制说清楚，不扩建新系统。

### 3.5 不为本轮删除或重建商业化工程

公开仓库继续聚焦科研工作流。README 只保留简短的许可和商业授权边界；SaaS、计费、多租户、许可证服务器和密钥下发等私有设计不进入公开实现。

如果已有公开文档被外部链接引用，保留简短兼容页；没有引用时再单独清理，而不是把文档删除绑进本次功能升级。

---

## 4. 用户实际操作流程

### 4.1 最终作者补全

```text
prepare-manuscript-completion
  → 用户填写一份 completion packet
  → preview-manuscript-completion
  → 查看正文 diff、预览 PDF、修改分类、证据引用和 stale 范围
  → 用户确认
  → apply-manuscript-completion
  → final citation audit
  → 两位独立盲评
  → release hash 与最终 main.pdf
```

修改类型及行为：

| 用户修改 | canonical class | 默认影响 |
|---|---|---|
| 作者、单位、基金、致谢 | `metadata_only` | 只重建稿件和 PDF |
| 不改变事实的表达优化 | `prose_only` | 只重建对应章节及下游稿件 |
| 增删或调整引用 | `citation_change` | 重跑 citation audit 和稿件发布链路 |
| 收窄已有论断 | `claim_boundary_change` | 保留已确认图表，重写受影响正文 |
| 修改结果解释 | `result_interpretation_change` | 重开 Results、Discussion 和下游审查 |
| 增加或改变数据、方法、cohort、run、metric、figure | 现有对应 scientific class | 重开对应科学链路与下游正文 |
| 改变研究问题或实验设计 | `research_plan_change` | 重开研究蓝图及其全部依赖 |

这里所说的“重新打开上游”不是无差别重写全文，而是按照 artifact DAG 把受科学修改影响的阶段标记为 stale。例如，新增未经执行的数据处理步骤会重新打开 Data、Method/run、图表和正文；只补作者单位不会触碰科研结果。

### 4.2 Result Support

```text
assess-result-support
  ├─ passed
  │    → 冻结当前证据版本，继续 Results
  └─ decision_required
       ├─ apply-result-downgrade
       │    → 保留当前图表、指标和 run，只收窄 claim 与正文
       └─ prepare-result-rescue
            → 生成数据/方法补充任务，完成后重跑相关结果
```

两条路线命令都必须携带当前 checkpoint hash：

```text
draftpaper apply-result-downgrade --project <project> --checkpoint-hash <sha256> --reason <text>
draftpaper prepare-result-rescue --project <project> --checkpoint-hash <sha256>
```

hash 过期时不修改项目，并返回最新 checkpoint；相同 hash 的重复操作必须幂等。

Results 学科审查发现纯文字错误时，优先进入 semantic repair；发现 run、cohort、metric、figure、plugin 或统计证据不一致时，重新回到同一个 Result Support checkpoint。

---

## 5. 分阶段实施方案

### M0：建立 README 能力事实来源

**目的**：README 只写已经有命令、源码、artifact 或测试支撑的能力。

**新增或修改**：

- `docs/capability_truth_matrix.json`；
- `tools/validate_capability_truth_matrix.py`；
- 中英文 README 一致性测试。

**验收**：矩阵能发现“README 写成已实现但仓库没有证据”“中英文状态不一致”“版本号与实现不一致”等问题，但不限制 README 的自然语言写法。

### M1：在原 README 框架内局部补充

保持现有 H2 标题集合和顺序，只改五处：

1. **当前版本**：按版本区间提炼新增功能，不再只写限制和文档链接；
2. **论文如何到达 main.pdf**：补一条完整科研流程；
3. **最终稿补全**：加入 completion packet、双重定位和精确 stale 规则；
4. **Quick Start**：以 minimal 安装为起点，同时提供 PowerShell 与 bash 示例；
5. **最近更新**：保留具体 patch 记录，不重复“当前版本”的能力摘要。

“当前版本”按以下范围概括：

- v0.30.1–v0.30.3：科学门控、统一退出码、canonical change taxonomy、artifact DAG；
- v0.30.4–v0.31.0：completion packet、稳定定位、diff/PDF、apply/rollback、release binding；
- v0.31.1–v0.31.5：模块拆分、CommandSpec、schema 和质量合同；
- v0.31.6–v0.31.9：安装档位、token/cost、风险矩阵和跨平台发布检查；
- v0.32.0：completion 审计、跨期刊回归和 README 框架恢复；
- v0.32.1–v0.33.0：完成本方案中的 evidence-backed completion 与 Result Support v3。

### M2：完善 completion preview

**目的**：让系统自动识别修改影响，并降低用户填写证据引用的难度。

**实施内容**：

1. 继续复用现有 `CHANGE_CLASS_SPECS`，不创建新分类系统；
2. preview 同时输出用户声明分类、系统判断分类、最终分类和 stale 范围；
3. 分类不一致时使用影响范围更大的结果；
4. 对 Data/Methods 中“已经执行”的说明自动建议 candidate `evidence_refs`；
5. apply 时重新校验 path、JSON pointer、hash、run、cohort 和 snapshot；
6. preview 之后证据发生变化时，原 preview 自动失效；
7. 达到校准门槛后再启用严格 apply gate。

**验收**：科学变化漏判为普通文字的数量为 0，合法作者补全误拦截率不高于 5%。

### M3：升级 Result Support v3

**目的**：只根据当前研究蓝图和当前 run 判断结果是否足以支撑论文。

证据读取顺序固定为：

1. current claim contract；
2. current resolved result evidence；
3. selected run manifest；
4. result validity；
5. result/figure/plugin trace；
6. required data、label、leakage、image-quality 和 statistical review artifacts；
7. current data acquisition tasks；
8. post-Results reopen request。

禁止目录泛扫后优先读取通用 `metrics.csv`。

**实施内容**：

- required role、pending task 与 active claim/figure 建立显式 binding；
- checkpoint 保存当前证据 hash；
- downgrade/rescue 命令校验 hash、保持幂等并记录 decision receipt；
- Results 学科审查与 Result Support 使用同一 evidence snapshot；
- 同步更新 CLI、workflow skill、文档、风险矩阵、测试与 wheel 内置资源。

**验收**：旧 checkpoint 不能修改新证据，未绑定 required role 不能显示为 passed，optional 无关任务不会全局阻塞。

---

## 6. 版本安排

| 版本 | 用户可见能力 | 发布条件 |
|---|---|---|
| **v0.32.1** | README 能力摘要和能力真值校验 | 中英文版本、状态、边界与实现证据一致 |
| **v0.32.2** | completion 分类预览、自动 evidence refs、Result Support v3 | 校准报告可审计；CLI、Agent 与文档命令一致 |
| **v0.33.0** | 严格分类、完整发布绑定和跨平台回归 | 达到分类门槛；全量测试、wheel、安装矩阵和 GitHub CI 通过 |

内部按 M0–M3 分提交；对外不为每个内部步骤单独发布 patch tag。

---

## 7. 测试与验收

### 7.1 README 与文档

- README 原有 H2 集合和顺序不变；
- “当前版本”能够直接回答各版本新增了什么；
- 中英文 capability ID、状态、版本和边界一致；
- Quick Start 同时覆盖 PowerShell 和 bash；
- fixture、mock 与真实论文证据的边界明确。

### 7.2 作者补全

- 普通 metadata、prose 和 citation 修改只 stale 必要下游；
- cohort、run、metric、figure、data、method 和 research-plan 变化不会被低影响分类放过；
- evidence refs 可以自动建议、人工确认并在 apply 时重新校验；
- 旧 preview 在证据或稿件变化后失效；
- rollback 能恢复 apply 前状态。

### 7.3 Result Support

- 只使用 selected run 和当前 evidence snapshot；
- 不优先读取目录中的通用 `metrics.csv`；
- required data role 无 binding 时不得 passed；
- optional 且无关的 task 只提示；
- checkpoint hash 过期时保持原状态；
- downgrade 与 rescue 重试具有幂等性；
- citation audit 必须晚于最终正文；
- 两位盲评者使用同一最终证据版本和不同 reviewer identity。

### 7.4 发布验证

```powershell
python -m pytest -q
python -m build --wheel
python tools/verify_wheel_install.py --wheel-dir dist
python tools/verify_install_matrix.py --wheel-dir dist
python tools/validate_capability_truth_matrix.py
git diff --check
```

---

## 8. 完成标准

本方案完成后应同时满足：

1. README 的大框架没有变化，但开头能够看懂版本能力和完整流程；
2. 用户可以用一份 packet 补齐论文信息并精确修改正文；
3. preview 会用通俗说明展示“修改了什么、引用了什么证据、哪些阶段会重开”；
4. 科学内容的新增或修改不会被当成普通润色直接写入终稿；
5. 结果支撑不足时，用户在一个确认点明确选择收窄论断或补数据/方法；
6. 正文、图表、指标、引用审计和盲评属于同一 evidence snapshot；
7. Agent、CLI、文档、wheel 和测试使用同一个命令合同；
8. 全量测试、wheel、安装矩阵和 GitHub CI 通过后才标记 v0.33.0 正式发布。

---

## 9. 本地 main 同步边界

`C:/Draftpaper_commercial` 的 main 同步是独立运维任务，不与上述功能开发绑成一个验收项。

同步前先区分：

- 本地独有 commit；
- tracked 修改；
- untracked 科研项目或审计文件。

独有内容先建立安全分支或生成 hash 备份；确认本地 main 可 fast-forward 时再使用 `--ff-only`。不自动执行 reset/rebase，也不把全量 `stash -u` 当作唯一备份。

---

## 10. 当前实施状态

- M0–M3 的主要实现位于 `C:/Draftpaper_worktrees/v0301-v0320`；
- 本地全量测试记录为 `1052 passed, 2 skipped`；两个 skip 是 Windows 文件 symlink 权限条件用例，目录 junction 边界测试已通过；
- v0.33.0 wheel 已完成本地构建、安装验证、安装档位矩阵、capability truth 和 release identity 检查；
- GitHub CI、合并、正式 tag 与 tag-build 验证完成后，才能把 v0.33.0 标记为正式发布。

本方案不以增加更多门控为目标，而以三个结果为判断标准：**用户更容易理解；科学修改不会漏开必要链路；每项已发布能力都有唯一实现和可核验证据。**
