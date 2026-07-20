# Draftpaper-loop v0.32.1–v0.33.0 最终优化方案

> 目标：在不改变 README 主框架、不重造运行时合同的前提下，说清版本能力，完善最终作者补全，并修正 Result Support 的证据版本与路线绑定。

---

## 1. 最终判断

其它模型提出的建议**并非全部正确**。其中一部分能减少误判和用户操作成本，值得采纳；另一部分会增加旁路、双轨分类或额外维护负担，应当排除。

本轮最终只做四件事：

1. **README 局部优化**：保留原有 H2 标题与顺序，只改“当前版本”、主流程、最终稿补全、Quick Start 和必要边界。
2. **作者补全更可靠**：用户继续填写一个 completion packet；preview 自动判断修改类型、证据引用和 stale 范围。
3. **Result Support 更一致**：只读取当前 evidence/run/checkpoint，结果不足时仍只有“收窄论断”与“补数据/方法”两条路线。
4. **文档、CLI、Agent 与 wheel 同步**：同一能力只保留一个权威合同。

不在本轮实施：

- 第二套 change taxonomy；
- `--force-class` 绕过入口；
- claim 级混合 Result Support 路线；
- 公开仓库中的商业 SaaS、计费、多租户或密钥服务。

---

## 2. 当前已有能力与真正缺口

### 2.1 继续复用的已有能力

| 能力 | 权威实现 |
|---|---|
| 修改分类与 stale 范围 | `change_impact.CHANGE_CLASS_SPECS` |
| artifact 依赖 | `artifact_dag.py` |
| completion prepare / preview / apply / rollback | `manuscript_completion.py` |
| 行号、上下文和 hash 定位 | completion locator |
| Result Support | `result_support.py` |
| 收窄论断 | `apply-result-downgrade` |
| 补数据/方法 | `prepare-result-rescue` |
| Results 学科审查 | `review-results-with-discipline-rules` |

### 2.2 本轮需要补齐的缺口

| 缺口 | 用户问题 |
|---|---|
| README“当前版本”只写限制和链接 | 看不出各版本新增了什么 |
| completion 可能接受错误的低影响分类 | 科学变化可能未重新打开必要阶段 |
| Data/Methods 科学补充缺少便捷证据引用 | 用户不会填写 `evidence_refs` |
| Result Support 信号来源优先级不明确 | 可能读错指标或混用旧证据 |
| 路线命令未绑定当前 checkpoint | 旧决定可能作用于新证据 |
| Agent skill 与 CLI 更新可能不同步 | Agent 可能继续发送旧命令 |
| 整单路线边界说明不足 | 多 claim 项目容易误解系统能力 |

---

## 3. 对外部建议的取舍

| 建议 | 取舍 | 原因与落地方式 |
|---|---|---|
| M2 先 shadow、后 strict | **采纳** | 先记录用户分类与系统分类差异；达到样例覆盖和误判门槛后再严格拒绝。 |
| shadow 必须持续“一周” | **不采纳** | 时间不能证明可靠性，改用至少 60 条人工标注样例、零科学漏判和不高于 5% 的合法补全误杀率。 |
| 增加 `--force-class` | **不采纳** | 会形成绕过证据与 stale 合同的旁路。用户应修改 packet 或接受系统计算出的较高影响分类。 |
| preview 自动建议 `evidence_refs` | **采纳** | 从本地 manifest、run output 和 evidence registry 只读提出候选，用户确认或删除。 |
| 明确不支持多 claim 分别走不同路线 | **采纳** | 当前一个 checkpoint 只选一条路线；多 claim 分治留给后续版本。 |
| 减少连续 patch 发布 | **采纳** | 内部按 M0–M3 分提交，对外只发 v0.32.1、v0.32.2、v0.33.0。 |
| `--checkpoint-hash` 同步 Agent/文档 | **采纳** | CLI、skill、contract、wheel 副本、CLI reference 和风险矩阵同批更新。 |
| 真值矩阵逐字锁定 README 文案 | **部分采纳** | 校验 capability ID、状态、版本、边界和证据，不锁死自然语言表达。 |
| 删除 `commercial_overview` | **条件采纳** | 先查引用；有旧链接时保留一份简短兼容页，无依赖时删除。 |
| required data role 无 binding 时处理 | **采纳** | Result Support 不得 passed，进入两条路线之一；无关 optional task 只 warn/skip。 |

结论：值得采纳的是**降低科学错配、减少用户手填、保证命令一致性**的建议；不采纳的是**制造旁路、双轨合同或仅增加维护成本**的建议。

---

## 4. 用户最终流程

### 4.1 最终作者补全

```text
prepare-manuscript-completion
  → 填写一个 completion packet
  → preview-manuscript-completion
  → 查看正文 diff、PDF、修改分类、evidence refs 和 stale 范围
  → apply-manuscript-completion
  → final citation audit
  → 两位独立盲评
  → release hash
```

一个 packet 可补充作者、单位、基金、致谢、声明、数据/代码链接、新参考文献，以及通过“章节 + 行号 + 上下文 + hash”定位的正文修改。

### 4.2 Result Support

```text
assess-result-support
  ├─ 支撑充分 → 继续 Results 与后续写作
  └─ 支撑不足 → 同一人工确认点二选一
       ├─ 收窄论断：冻结现有图表和指标，只改 claim boundary 与正文
       └─ 补数据/方法：重新打开 data/method/run/figure/evidence/manuscript
```

当前一个 checkpoint 作用于整篇论文。若不同 claim 需要不同路线，返回 `mixed_route_not_supported` 并保持原状态。

---

## 5. 分阶段实现

### M0：能力真值矩阵

新增：

- `docs/capability_truth_matrix.json`；
- `tools/validate_capability_truth_matrix.py`；
- 对应测试。

每条能力记录：`capability_id`、状态、minor 版本、命令、源码、artifact、测试和中英文边界。矩阵只校验文档事实，不参与运行时科研决策。

### M1：README 局部优化

保持现有 H2 集合和顺序，只改以下位置：

1. **当前版本**：按版本区间列出新增能力，不再只写限制和链接；
2. **论文如何到达 main.pdf**：用一条流程说明 idea → research plan → data/method → figures → Results → full paper；
3. **最终稿补全**：说明 completion packet、定点修改和科学内容重新打开规则；
4. **Quick Start**：minimal-first，同时给 PowerShell 与 bash 示例；
5. **最近更新**：只保留 patch 细节，不重复“当前版本”摘要。

“当前版本”按以下区间提炼：

- v0.30.1–v0.30.3：科学门控、退出码、canonical taxonomy、artifact DAG；
- v0.30.4–v0.31.0：completion packet、稳定定位、diff/PDF、apply/rollback、release binding；
- v0.31.1–v0.31.5：模块拆分、CommandSpec、schema 和 quality contract；
- v0.31.6–v0.31.9：安装档位、token/cost、风险矩阵和跨平台发布检查；
- v0.32.0：completion 审计、跨期刊回归和 README 框架恢复；
- v0.32.1–v0.33.0：只有通过 release gate 后才写成 implemented。

### M2：completion 分类与 evidence refs

不新增分类命令，全部进入现有 preview。

用户修改只映射到现有 canonical class：

- 作者、单位、基金、致谢 → `metadata_only`；
- 普通表达 → `prose_only`；
- 引用 → `citation_change`；
- 收窄已有论断 → `claim_boundary_change`；
- 结果解释 → `result_interpretation_change`；
- 数据、方法、run、metric、figure、cohort → 对应已有 scientific class；
- 研究问题或设计 → `research_plan_change`。

`scientific_evidence_change` 只作为旧名称入口，preview 必须继续解析成现有 canonical class。

当用户补写“已经执行过”的 Data/Methods 细节时：

1. preview 从固定 allowlist 自动建议证据；
2. 用户确认或删除建议；
3. apply 再检查 path、JSON pointer、hash、run、cohort 和 snapshot。

普通润色不需要 evidence refs；声称已执行科学步骤但没有有效 refs 时返回 `classification_refinement_required`，不自动降级成普通文字。

v0.32.2 先以 shadow 输出“用户分类、系统分类、有效分类、差异、stale 范围”。分类不一致时使用更保守的 stale 范围；evidence ref 完整性始终严格。达到以下门槛后，v0.33.0 才切 strict：

- 至少 60 条人工标注样例；
- 至少 3 个学科；
- 科学变化漏判为 0；
- 合法作者补全误杀率不高于 5%。

### M3：Result Support v3

证据读取优先级固定为：

1. current claim contract；
2. current resolved result evidence；
3. selected run manifest；
4. result validity；
5. result/figure/plugin trace；
6. required data/label/leakage/image-quality/statistical review artifacts；
7. current data acquisition tasks；
8. post-Results reopen request。

禁止目录泛扫后优先读取通用 `metrics.csv`。

pending task 规则：

- 绑定 active claim/figure → 进入路线选择；
- required data role 没有 binding → 生成 `unbound_required_data_task`，checkpoint 不得 passed；
- optional 且无关 → warn/skip。

路线命令必须携带当前 hash：

```text
draftpaper apply-result-downgrade --project <project> --checkpoint-hash <sha256> --reason <text>
draftpaper prepare-result-rescue --project <project> --checkpoint-hash <sha256>
```

hash 过期时保持原状态并返回当前 hash；相同 hash 重试必须幂等。

Results 学科审查发现纯文字问题时进入 semantic repair；发现 run、cohort、metric、figure、plugin 或统计证据问题时，回到同一个 Result Support checkpoint。

---

## 6. README 与公开仓库边界

README 继续保留原有总体结构。公开仓库只写：

- 当前许可边界；
- 商业授权联系方式；
- 赞助不等于商业授权。

商业 SaaS、计费、多租户、许可证服务器和密钥下发设计均留在本地私有工程，不进入本方案的公开实现。

---

## 7. 版本与发布

| 版本 | 内容 | 发布条件 |
|---|---|---|
| **v0.32.1** | 能力真值矩阵 + README 局部优化 | 中英文状态、版本、边界和实现证据一致 |
| **v0.32.2** | completion shadow + evidence refs + Result Support v3 | 分类差异可观察；checkpoint hash 和 Agent/CLI 同步 |
| **v0.33.0** | strict 分类 + 完整回归 + wheel | 达到校准门槛；全量测试、wheel、安装矩阵和 GitHub CI 通过 |

内部仍按 M0–M3 分提交，避免巨型 diff；不为每个内部阶段单独发布 patch tag。

CLI、workflow skill、contract、wheel 内置副本、CLI reference、风险矩阵和相关示例必须同一个发布批次更新。

---

## 8. 测试与完成标准

### 必须验证

- README H2 集合与顺序不变；
- 中英文 capability ID、状态、版本、边界和证据一致；
- completion 低影响误标不会漏开科学阶段；
- 合法普通补全误杀率满足门槛；
- evidence ref 的 allowlist、pointer、hash、run/cohort/snapshot 校验有效；
- preview 后证据变化会使旧 preview 失效；
- Result Support 不误读通用 `metrics.csv`；
- required data role 未绑定时 checkpoint 不得 passed；
- checkpoint hash 过期与幂等重试正确；
- Agent、CLI、contract、文档和 wheel 使用同一命令。

### 发布命令

```powershell
python -m pytest -q
python -m build --wheel
python tools/verify_wheel_install.py --wheel-dir dist
python tools/verify_install_matrix.py --wheel-dir dist
python tools/validate_capability_truth_matrix.py
git diff --check
```

### 完成定义

1. README 开头能直接说明各版本新增能力，同时原有主框架不变；
2. 用户可用一个 packet 补齐论文信息并定点修改正文；
3. preview 会显示分类、证据和精确 stale 范围；
4. 缺少证据的科学补充不会混入普通文字；
5. 结果不足时明确进入收窄论断或补数据/方法；
6. citation audit 晚于最终正文，之后完成两位独立盲评和 release hash；
7. 全量测试、wheel、安装矩阵与 GitHub CI 全部通过。

---

## 9. 本地 main 同步说明

`C:/Draftpaper_commercial` 的 main 同步是独立运维任务，不与本轮功能开发绑成一个验收项。先分类本地 commit、tracked 修改和 untracked 文件，再对独有内容建立安全分支或 hash 备份；可 fast-forward 时才执行 `--ff-only`。dirty main 不自动 reset/rebase，也不把全量 `stash -u` 作为唯一备份。

---

## 10. 当前实施状态

- M0–M3 主要实现位于 `C:/Draftpaper_worktrees/v0301-v0320`；
- 全量测试已得到 `1052 passed, 2 skipped`；两个 skip 均为当前 Windows 权限下不可创建文件 symlink 的平台条件用例，目录 junction 边界测试已通过；
- `draftpaper_cli-0.33.0-py3-none-any.whl` 已重新构建，wheel 安装验证、安装档位矩阵、capability truth 和 release identity 均已通过；
- GitHub 提交、远端 CI 和正式 `v0.33.0` tag 验证完成后，才可把 v0.33.0 标记为正式发布。

本方案的判断标准不是增加更多术语和门控，而是：**用户更容易理解，科学修改不会漏开必要链路，运行时只有一个真源，每项已发布能力都有实现证据。**
