# Draftpaper-loop v0.28.0 全量代码审计与优化方案

审计日期：2026-07-17
审计对象：`C:\Draftpaper_commercial`
审计分支：`main`
审计提交：`995115a67b4dc8339b4b03d03628efa875a4ce44`
提交说明：`fix: sync v0.28 wheel release contract`

## 1. 执行摘要

Draftpaper-loop 当前已经不是简单的论文模板生成器。它已经形成了较完整的 evidence-first 科研工作流，包括研究蓝图、数据与方法能力合同、可执行分析、语义图表合同、核心证据人工确认、自由写作候选、引用核查、学科审阅、独立盲审和 wheel 发布回归。

本轮审计确认，v0.22 以前最严重的 wheel 缺资源、正式流程绕过自由写作、结果证据绑定过松等问题已经得到实质修复。当前源码测试、隔离 wheel 安装和五类跨领域发布回归均通过。

但当前版本仍存在一个必须优先修复的 P0：`apply-section-revision` 并不是真正的事务。它把接受后的内容写入 `latex/sections/*.tex` 派生文件，而不是章节 canonical source；后续 `assemble-latex` 会从 canonical source 重新复制并覆盖该修订。同时，所谓 artifact stale propagation 只写一份报告，没有修改权威项目状态。结果是“命令显示修订已提交，但最终 PDF 可能恢复旧文案，且下游状态没有真正 stale”。

综合判断：

- 科学工作流方向：正确，建议保留。
- wheel 与发布回归：健康。
- 科学证据语义架构：较成熟，但仍需真实项目持续校准。
- 修订事务、状态一致性和写入边界：尚未达到稳定发布要求。
- 插件数量：基础已形成，但 manifest/runtime/fixture 的真实性合同仍不统一。
- 可维护性：203 个 CLI 命令和多个超大模块已接近继续扩展的上限。

建议将当前成熟度定义为“功能完整的 beta / release candidate”，先完成 v0.28.1-v0.28.3 的事务、插件真实性和状态权威修复，再进入 v0.29 的结构重构。不要回退 evidence-first 主链，也不要继续用更多固定写作模板掩盖底层状态问题。

## 2. 审计范围与方法

### 2.1 覆盖范围

- CLI parser、CommandSpec、调度器与 MCP 执行入口。
- 项目状态、stage manifest、passport、ledger、artifact DAG 和 stale propagation。
- research plan、数据/方法、插件、图表、Results、Citation Audit、Review、LaTeX 与 release 链。
- 学科插件 registry、manifest、fixture、runtime level 和 wheel package data。
- CI、打包元数据、依赖、第三方 provenance 和本地 Codex skill 同步状态。
- 既有架构审计中 P0/P1 问题的修复状态。

### 2.2 验证方法

1. 对源码、测试、manifest、workflow 和发布脚本进行静态审阅。
2. 运行完整测试：`python -m pytest -q`。
3. 构建 wheel：`python -m build --wheel`。
4. 在隔离环境中安装并运行 `tools/verify_wheel_install.py`。
5. 比较源码 registry 与 wheel registry 的插件、fixture、资源、skill 和第三方 provenance。
6. 检查关键事务的 canonical source、派生产物、状态写入顺序和失败恢复行为。
7. 检查本机已安装 `draftpaper-workflow` skill 与仓库 canonical skill 的 hash/version。

### 2.3 未覆盖范围

- 本轮没有重新运行一篇真实论文的完整科研流程。
- 没有调用真实外部 API、GPU、远程服务器或实验设备。
- 没有以远程 GitHub Actions 结果替代本地验证。
- 没有对科学输出做新的人工同行评审；本报告审计的是框架和代码，不是某篇论文的科学结论。

## 3. 审计基线

| 指标 | 当前值 |
| --- | ---: |
| Python 源文件 | 635 |
| Python 源码行 | 114,446 |
| 测试 Python 文件 | 117 |
| 测试代码行 | 18,147 |
| CLI 命令 | 203 |
| 学科插件 manifest | 210 |
| wheel registry fixture | 545 |
| capability packs | 6 |
| 第三方 provenance sources | 6 |

体量最大的核心模块：

| 模块 | 行数 |
| --- | ---: |
| `plugin_candidates.py` | 3,709 |
| `cli.py` | 2,319 |
| `methods.py` | 1,660 |
| `review_revision.py` | 1,356 |
| `orchestrator.py` | 1,309 |
| `research_plan.py` | 1,107 |

## 4. 验证结果

### 4.1 完整测试

```text
Python 3.13.5
658 passed in 685.83s (0:11:25)
```

这说明当前实现具备较好的结构回归覆盖，并且在 Python 3.13 上也能通过现有测试。但测试通过不代表事务语义正确；本报告的 P0 正是现有测试没有覆盖的 producer-to-consumer 行为。

### 4.2 wheel 构建与隔离安装

结果：通过。

- wheel：`draftpaper_cli-0.28.0-py3-none-any.whl`
- source/install registry：`210/210`
- source/install fixture：`545/545`
- resource counts：JSON `749`、CSV `20`、Markdown `1`
- vendored paper-fetch：可用
- third-party provenance：通过，6 个来源
- workflow skill 与 contract：版本和 hash 一致
- 五类 release fixtures：全部通过
- wrong cohort/run/unit/split/model/metric/dimension、伪空白图、contract-only plugin 和引用语义反例：全部被拒绝

构建仍产生两类警告：

- `project.license` TOML table 已被 setuptools 标记为弃用，需迁移到 SPDX 字符串与 `license-files`。
- `MANIFEST.in` 包含不存在的 Markdown glob，产生 `no files found` 警告。

### 4.3 CLI 合同一致性

运行时 parser 命令与 `COMMAND_SPECS` 均为 203，集合完全一致。这是正向结果，但两套定义仍然由人工分别维护，属于结构性重复，不是单一权威来源。

### 4.4 本地 Codex skill 同步

本机 `skill-doctor` 结果：失败。

```text
canonical_version: 0.28.0
installed_version: 0.26.0
reason: skill_hash_mismatch
```

仓库 canonical skill 位于 [SKILL.md](../../draftpaper_cli/resources/draftpaper_workflow/SKILL.md#L3)，而 `%USERPROFILE%\.codex\skills\draftpaper-workflow` 仍是 v0.26.0。CLI 代码和 Agent 操作规则因此可能不属于同一版本。

## 5. 按优先级排序的发现

### P0-01 `apply-section-revision` 会提交到错误的权威文件并丢失修订

#### 证据

1. [revision_transaction.py](../../draftpaper_cli/revision_transaction.py#L39) 把 active section 定义为 `latex/sections/<section>.tex`，并在第 64 行直接覆盖该文件。
2. 真正的章节权威输入由 [latex_assembly.py](../../draftpaper_cli/latex_assembly.py#L29) 定义为 `results/results.tex`、`methods/methods.tex` 等 canonical source。
3. [latex_assembly.py](../../draftpaper_cli/latex_assembly.py#L352) 在每次组装时重新写入 `latex/sections/*.tex`，因此会覆盖 revision transaction 的结果。
4. [artifact_dag.py](../../draftpaper_cli/artifact_dag.py#L82) 的 `record_artifact_change()` 只写 `writing/artifact_stale_report.json`，没有调用 `mark_stages_stale()`，也没有改变 `project.json`、stage manifest 或 passport。
5. [test_artifact_dag.py](../../tests/test_artifact_dag.py#L1) 只验证 stale label 集合，没有测试修订安装、重新组装和权威状态变化。
6. README 已宣称该功能是事务和最小 stale propagation，见 [README.md](../../README.md#L437) 与 [README.zh-CN.md](../../README.zh-CN.md#L353)，实现与文档合同不一致。

#### 影响

- 用户接受的 Methods/Results 等局部修订可能不会进入最终 `main.pdf`。
- 命令 receipt 可显示 `committed`，但 canonical manuscript 未改变。
- Citation Audit、独立审稿和 release 可能基于错误版本。
- 失败发生在用户最关心的人工修订阶段，属于结果正确性问题，不是一般可维护性问题。

#### 修复方案

1. 建立唯一的 `SECTION_CANONICAL_ARTIFACTS` 映射，revision 只能写入 canonical source。
2. 把 candidate validation、editor acceptance、canonical install、claim map 更新、stale propagation、receipt 和 passport refresh 纳入一个多文件事务。
3. 使用临时事务目录保存所有新文件和旧文件备份；全部校验成功后再原子替换。
4. 任一步骤失败时恢复所有旧文件，并记录 `aborted_rolled_back`，不得留下半提交 candidate、acceptance 或 derivative。
5. `record_artifact_change()` 必须返回 artifact change set，再由一个权威映射转换为真实 stage stale set并调用 `mark_stages_stale()`。
6. `latex/sections/*.tex` 明确降级为可重建派生产物，禁止任何用户修订直接写入。

#### 验收标准

- 修改 `methods` 后，`methods/methods.tex` hash 等于 accepted candidate hash。
- 连续执行 `assemble-latex` 两次后修订仍存在于 `latex/sections/methods.tex` 和 `main.pdf`。
- citation-only 修订只 stale 必要写作/引用/release 链，不 stale 数据、方法运行和图表。
- Methods 科学语义修订 stale Methods、Discussion、LaTeX、Citation Audit、Review 和 release。
- 注入 acceptance、canonical write、stale write、receipt write 任一点故障后，所有权威文件恢复到事务前 hash。

### P1-01 Artifact DAG 目前是标签表，不是可执行依赖图

#### 证据

[artifact_dag.py](../../draftpaper_cli/artifact_dag.py#L30) 使用通用标签定义 `DEFAULT_DEPENDENCIES`，没有记录真实 artifact path、当前 hash、producer、consumer、schema family 或 promoted snapshot。`stale_artifacts_for_change()` 直接返回 `CHANGE_CLASS_ROOTS` 中预列的标签，并没有遍历依赖图。该依赖集合也不同于 [project_scaffold.py](../../draftpaper_cli/project_scaffold.py#L130) 中的权威 stage dependencies。

#### 影响

- 同一个 stale 语义存在 artifact labels、stage names 和 section names 三套词汇。
- 文档声称“artifact hashes own stale propagation”，实现实际上仍是固定列表。
- 新增 artifact 或 consumer 时容易漏改 stale 列表。

#### 修复方案

- 节点必须是稳定 artifact ID，并包含 path、schema family、producer command、current hash 和 authoritative/derived 属性。
- 边必须表达实际 consumer relationship，并从 CommandSpec 的 input/output contract 生成。
- change class 只决定起始节点；下游 stale 由图遍历计算。
- stage status 继续作为摘要视图，但由 artifact state 聚合生成，不能作为第二套独立事实。

### P1-02 写入边界是事后检测，不是事务隔离或安全边界

#### 证据

1. [write_set_guard.py](../../draftpaper_cli/write_set_guard.py#L80) 在命令前 snapshot project tree，在命令后比较 changed files。
2. [cli.py](../../draftpaper_cli/cli.py#L2511) 先完整执行命令，到第 2538 行才调用 `assess()`；检测到 violation 后只返回 exit code 4，没有回滚已经发生的写入。
3. `snapshot_tree()` 只观察 project root。命令或插件写到 project root 之外时，该 guard 无法看到。
4. [mcp/service.py](../../draftpaper_cli/mcp/service.py#L97) 会启动真实 CLI 子进程；它校验 `project` 参数，却没有对其余路径参数和子进程文件系统写入做预防式约束。
5. 当前测试 [test_v025_skill_and_security.py](../../tests/test_v025_skill_and_security.py#L88) 只证明能够发现违规文件，并未断言违规文件被删除或命令回滚。

#### 影响

- “boundary_violation” 状态出现时，违规文件仍然存在。
- MCP/Agent 运行科研代码时，allowed prefixes 目前主要是审计信息，不是强制隔离。
- 事务 ledger 的 `boundary_violation` 不等于系统没有发生越界副作用。

#### 修复方案

- 对项目内写入使用 transaction workspace 或 change journal，违规时自动恢复 created/modified/deleted 文件。
- 对所有 CommandSpec 路径参数增加 `read_path`、`write_path`、`external_locator` 类型，并在执行前 resolve/validate。
- execute-science 插件使用受控工作目录和显式 output roots；禁止模板自行推断绝对输出路径。
- MCP 默认只开放 read/write-project；execute-science 需要一次有时效、绑定 command hash 的 capability token，而不是单个布尔值。
- 对不能可靠隔离的外部程序明确标记 `external_side_effect_uncontained`，禁止声称 transaction-safe。

### P1-03 插件 manifest、fixture、runtime 和 deployment truth 不一致

#### 证据

当前 210 个 manifest 的显式字段统计：

| 字段 | 分布 |
| --- | --- |
| `runtime_class` | 108 local optional、52 local pure Python、8 API、3 server、1 GPU、38 缺失 |
| `validation_level` | 160 fixture runnable、12 mock、38 缺失 |
| `maturity` | 171 foundation、1 runnable、38 缺失 |
| `deployment_state` | 51 candidate、1 live runnable、158 缺失 |

附加问题：

1. [template_registry.py](../../draftpaper_cli/template_registry.py#L41) 只把文件名以 `fixture_` 开头的文件识别为 fixture。
2. `astronomy/review_rules/sky_partition_overlap_validation` 使用 `fixture.json`，manifest 却声明 `fixture_runnable` 和 `live_runnable`；registry 实际返回 `fixtures=[]`、`runtime_level=contract_only`。
3. [template_registry.py](../../draftpaper_cli/template_registry.py#L69) 对缺失字段填默认值，后续 validation 只检查默认值是否属于允许枚举，因此 38 个缺字段 manifest 不会失败。
4. [plugin_catalog.py](../../draftpaper_cli/plugin_catalog.py#L37) 为旧 manifest 自动生成 execution contract。当前 210/210 个插件都是 `compatibility_adapter=true`，但 catalog 仍返回 `status=passed`。
5. template registry 与 plugin catalog 的 runtime level 计算并不完全一致：前者当前为 175 contract-only / 25 code-generator / 10 fixture-executed，后者为 181 / 19 / 10。

#### 影响

- 新插件可以在文档层声明 runnable，却无法进入真实运行时能力。
- 也可能反向发生：默认适配器让缺少明确 input/output contract 的插件看似通过 catalog validation。
- plugin sufficiency、review rule 和 release catalog 使用不同 runtime truth，增加误判和维护成本。

#### 修复方案

1. 发布 `dpl.plugin_manifest.v2` JSON Schema，强制显式声明 ID、discipline、kind、runtime class、validation level、maturity、deployment state、fixture list、input/output schema、side effect 和 credential policy。
2. fixture 不再依赖文件名前缀猜测；manifest 显式列 `fixtures.normal/failure/boundary/mock`。
3. registry、catalog、sufficiency、review runtime 和 wheel verifier只消费同一 normalized `PluginRecord`。
4. 默认兼容适配器只允许用于 legacy read，不能使 release validation 通过。
5. `fixture_runnable` 必须有至少一个可执行 fixture receipt；`live_runnable` 必须有 live validation event 和 output hash。
6. 提供一次显式 migration 命令补齐 210 个 manifest，但禁止把 contract-only 批量升级为 runnable。

#### 验收标准

- 210 个 release-level manifest 的 required fields 缺失数为 0。
- `sky_partition_overlap_validation` 的 fixture 能被源码和 wheel registry 同时发现并实际执行。
- registry/catalog/sufficiency 对每个 plugin 的 runtime level 完全一致。
- 删除 fixture 或修改 output schema 后，CI 必须失败。
- compatibility adapter 数量被单独报告，release-level 插件不得依赖 adapter。

### P1-04 权威项目状态仍缺少多文件事务

#### 证据

1. [state_kernel.py](../../draftpaper_cli/state_kernel.py#L40) 已提供单文件锁和原子替换，这是正向改进。
2. [project_state.py](../../draftpaper_cli/project_state.py#L116) 仍依次写 `project.json` 和 `project.yaml`，stage manifest 又在保存前后分别写入；进程中断时可以形成跨文件不一致。
3. [journal_profile.py](../../draftpaper_cli/journal_profile.py#L320) 直接修改 `state.metadata` 并写 `project.json`，绕过统一 state mutation API。
4. `command_transaction.py` 记录的是事务 receipt，不负责 commit/rollback，因此名称容易让维护者误以为已有事务保证。

#### 影响

- crash、磁盘错误或并发命令可能使 JSON、YAML、stage manifests、passport 和 ledger 属于不同状态版本。
- doctor 可以发现部分差异，但不能证明之前的命令原子提交。

#### 修复方案

- 新增 `ProjectStateTransaction`：持有 project-level lock，读取 expected revision/hash，准备全部新文件，统一 commit 或 rollback。
- 为每次状态提交分配单调 `state_revision`，写入 project JSON/YAML、stage manifests、passport 和 receipt。
- journal profile、migration、stale propagation、checkpoint 和 revision 全部改走该 API。
- ledger 保持 append-only，但 event 必须引用 committed `state_revision`。

### P1-05 仓库代码与本机 Agent workflow skill 已发生版本漂移

#### 证据

- canonical skill：v0.28.0。
- `%USERPROFILE%\.codex\skills\draftpaper-workflow`：v0.26.0。
- `skill-doctor` 正确报告 `skill_hash_mismatch` 并给出 `install-skill --force`。

#### 影响

即使 CLI 已实现 v0.26.1-v0.28.0 的新人工确认、事务、引用和 release 规则，Codex 仍可能按照旧 stage order 和旧边界操作。该问题不会被 wheel 单元测试发现，因为它发生在仓库外安装层。

#### 修复方案

- `draftpaper doctor` 增加非阻塞的 skill drift 检查，并在操作论文项目前明确显示。
- Codex skill 的安装 receipt 记录 package version、skill hash 和 install timestamp。
- 发行说明给出一次明确同步步骤；不要静默覆盖用户修改过的 skill。
- MCP server 启动时报告 canonical/installed skill mismatch。

### P2-01 CLI parser 与 CommandSpec 仍是重复权威来源

#### 证据

[cli.py](../../draftpaper_cli/cli.py#L206) 手工创建 203 个 parser command；[command_registry.py](../../draftpaper_cli/command_registry.py#L106) 又手工定义 203 个 CommandSpec。当前测试保证名称集合相同，但参数类型、required、help、risk、MCP schema 和 handler bindings 仍可能局部漂移。

#### 修复方案

- 建立单一 `CommandContract`，声明参数、handler、输出 schema、risk、read/write set、exit policy 和帮助文本。
- 由合同生成 argparse、MCP schema、dispatch、CLI reference 和 command tests。
- 逐 coordinator 迁移，避免一次性重写 203 个命令。

### P2-02 超大模块与重复 IO/异常类型抬高维护成本

#### 证据

- 6 个核心模块超过 1,000 行，`plugin_candidates.py` 达 3,709 行。
- 第一方代码中约有 50 个本地 `_read_json` 实现和 96 个自定义 `*Error` 类。
- 这些 reader 对缺失文件、JSON 错误、编码、fallback 和 strictness 的处理并不统一。

#### 修复方案

- `plugin_candidates.py` 拆为 intake/classification/promotion/provenance/contribution 五个子模块。
- `cli.py` 只保留 bootstrap，parser 和 dispatch 由 command contracts 生成。
- `methods.py` 拆为 context、execution、verification、writing install。
- 全部结构化 artifact 统一通过 schema-aware repository 读写。
- 异常收敛为 `DraftpaperError(code, severity, recovery, artifact)`，保留少量领域子类。

### P2-03 Schema version 与产品版本耦合

#### 证据

第一方代码中存在 163 处 `schema_version` 引用。多个 artifact 仍使用 `v0.16.5`、`v0.17.7`、`v0.18.4`、`v0.21.x`、`v0.22.2`、`v0.28.0` 等产品版本作为 schema ID，示例见 [claim_contract.py](../../draftpaper_cli/claim_contract.py#L116)、[results.py](../../draftpaper_cli/results.py#L387)、[paper_narrative.py](../../draftpaper_cli/paper_narrative.py#L385) 和 [manuscript_composer.py](../../draftpaper_cli/manuscript_composer.py#L746)。

#### 影响

- 无法判断两个 artifact 是产品版本不同还是结构真的不兼容。
- adapter、migration 和兼容窗口难以系统管理。

#### 修复方案

- schema 使用独立 family ID，如 `dpl.result_manifest.v3`。
- 建立 schema registry：owner、JSON Schema、current version、supported readers、adapters 和 deprecation date。
- producer 写 current schema，consumer 声明接受范围；跨版本必须显式 adapter。
- CI 运行 producer-to-consumer compatibility matrix。

### P2-04 wheel 发布合同仍依赖人工同步常量

#### 证据

[verify_wheel_install.py](../../tools/verify_wheel_install.py#L20) 手工写死 entry count `210`、fixture count `545`、package version `0.28.0` 和关键命令列表。新增插件或升级版本时必须同时修改源码与 verifier，近期已经因此发生 CI 失败。

#### 修复方案

- 生成并提交 `release_manifest.json`，记录 version、skill hash、registry hash、resource manifest 和 fixture IDs。
- verifier 只比较“源码生成的 manifest”和“wheel 内 manifest”，不在 Python 脚本中复制业务常量。
- 版本仅从 package metadata 读取，并与 release manifest 比较。

### P2-05 CI 缺少静态质量、安全和兼容性层

#### 当前优点

[tests.yml](../../.github/workflows/tests.yml#L1) 已覆盖 Ubuntu/Windows 和 Python 3.10-3.12，并包含 isolated wheel 验证。这比早期版本明显完善。

#### 当前缺口

- 没有 Ruff/格式检查。
- 没有 mypy 或 pyright。
- 没有 coverage 统计和关键模块阈值。
- 没有依赖漏洞、SBOM、secret scan 或 license policy gate。
- GitHub Actions 使用可变 major tag，没有固定到 commit SHA。
- 依赖只有宽松下界，没有 release/CI constraints lock。
- 没有 schema compatibility 和 transaction crash-injection job。

#### 修复方案

建立分层 CI：

1. `lint`: Ruff format/check、文档链接和 manifest schema。
2. `type`: pyright 或 mypy，从 state/plugin/registry 核心开始。
3. `unit`: 快速单元测试。
4. `integration`: transaction、artifact DAG、CLI/MCP boundary。
5. `scientific-regression`: 五类 fixture 与对抗样例。
6. `wheel`: isolated install、source/wheel manifest parity。
7. `security`: dependency audit、secret scan、SBOM、license/provenance。
8. `release`: 固定 action SHA，只接受全部上游 job 成功。

### P3-01 临时目录长期污染工作树

当前 `git status` 持续显示未跟踪 `tmp/`，而 [.gitignore](../../.gitignore#L1) 没有对应策略。

建议：

- 如果 `tmp/` 只包含可丢弃运行时文件，加入精确 ignore。
- 如果其中存在审计证据，迁移到有 owner 的 `docs/audits` 或项目 `.draftpaper/runtime` 后再 ignore。
- `doctor` 报告临时目录体积、文件数、保留策略和安全清理命令。

### P3-02 README 对 v0.27.2 的能力描述高于当前实现

README 将 artifact DAG、transactional revision 和 minimal stale propagation 描述为已完成。P0 修复前应把该条标记为“已引入合同，事务闭环待 v0.28.1 修正”，或在 v0.28.1 发布后再恢复完成表述。文档不能作为实现通过的替代证据。

## 6. 历史问题修复状态

| 历史问题 | 当前状态 | 审计结论 |
| --- | --- | --- |
| wheel 丢失 manifest/fixture | 已修复 | source/install 均为 210 插件、545 fixture |
| wheel 缺 vendored paper-fetch | 已修复 | 隔离安装返回 vendored runtime |
| CI 仅单平台/单 Python | 已修复 | Windows/Linux，Python 3.10-3.12 |
| 正式流程可用 deterministic fallback 写作 | 已修复 | 正式 lifecycle 要求 Agent candidate、validation、editor、acceptance |
| 数值只按值匹配，不绑定 run/cohort/unit | 大体修复 | release 对抗回归可拒绝错误 run/cohort/unit/split/model/dimension |
| Citation Audit schema consumer 不兼容 | 已修复 | adapter/release regression 通过 |
| Review rule 只检查字段存在 | 明显改善 | 已能执行 plugin evaluator 和 evidence bundle；仍需真实学科阈值校准 |
| plugin runtime truth | 部分修复 | runtime level 已引入，但 manifest 默认值、fixture 发现和 catalog 仍不统一 |
| 单文件状态写入不原子 | 已修复 | state kernel 提供 lock + atomic replace |
| 多文件项目状态事务 | 未修复 | JSON/YAML/manifests/passport 仍可能半提交 |
| artifact-level stale DAG | 未完成 | 当前是标签报告，不是 hash-aware 可执行 DAG |
| 章节修订事务 | 未完成且存在 P0 | canonical source 未安装，组装会覆盖修订 |
| 第三方来源无法追溯 | 已修复 | registry/notice/license snapshots 覆盖 6 个来源 |
| 两位独立盲审流程 | 架构已实现 | 本轮未对真实新稿重新做人类/Agent 独立审查 |

## 7. 分系统架构评价

### 7.1 科研主流程

优点：研究蓝图确认、pre-execution support、插件 rescue、核心证据确认、Results-first 写作和 citation audit 后置的顺序合理。人工确认点集中在真正改变科学合同的位置，符合当前产品目标。

风险：stage graph、artifact DAG、writing lifecycle 和 release graph 仍有重复状态表达。下一步应统一事实源，不要继续增加第五套状态文件。

### 7.2 Scientific Evidence Registry 与 Figure Contract

优点：run/cohort/unit/split/model/dimension 绑定和对抗回归是当前最强的架构资产，应继续作为正文、图表、审阅和引用链的共同语义层。

风险：release fixtures 能证明合同拒绝预置反例，不能自动证明任意新学科的 estimand、统计阈值和 review rule 已正确。应增加项目级 calibration evidence，不应通过增加固定关键词 gate 解决。

### 7.3 写作架构

优点：`prepare -> Agent free candidate -> validate -> Scientific Editor -> accept -> install` 的设计正确，能释放 Codex 自由写作，同时保留硬性科学边界。

风险：最后的 revision transaction 和 canonical install 断裂，当前是最急迫问题。不要因此退回 deterministic 模板写作。

### 7.4 插件架构

优点：discipline/data/method/review 三类插件、project-local binding、promote 和 provenance 的总体分层合理，210 个插件已形成跨学科基础。

风险：数量增长快于合同治理。下一阶段目标不应继续追求插件总数，而应把现有插件分成 contract-only、fixture-executed、project-validated 和 live-validated 的可审计层级。

### 7.5 引用与参考文献

优点：保留已人工确认参考文献、优先收窄/改写论断、区分 citation intent、在最终正文之后 audit 的原则正确。

风险：真实全文证据和目标期刊格式仍依赖外部元数据质量。发布回归应继续保留 bibliography rendering proof、intent-aware semantics 和 reference coverage 三条独立检查，不要重新合成一个“全绿分数”。

### 7.6 MCP 与安全边界

优点：artifact path confinement、敏感信息递归脱敏、环境变量 allowlist、human checkpoint 禁止经 MCP 执行、`shell=False` 和命令风险分类均是正确设计。

风险：write-set guard 是事后归因而不是隔离；execute-science 子进程仍能产生项目外副作用。MCP 文档必须准确区分“可检测”“可回滚”“被操作系统隔离”三个级别。

## 8. 版本化优化路线

### v0.28.1 Revision Atomicity and Real Stale Propagation

目标：先消除 P0，保证用户修订一定进入最终 PDF。

- 新增 canonical section map。
- 新增 `MultiArtifactTransaction` 和 rollback journal。
- 重写 `apply-section-revision`，安装 canonical artifact。
- artifact change 映射为真实 stage stale mutation。
- 增加重新 assembly、重复 assembly、故障注入和 citation-local 精确 stale 测试。
- 修正文档中 v0.27.2 的完成状态。

发布门：P0 的全部验收标准通过；否则不得发布 v0.28.1。

### v0.28.2 Plugin Manifest and Runtime Truth

目标：让 plugin 声明、registry、catalog、sufficiency、review runtime 和 wheel 完全一致。

- 发布 plugin manifest v2 schema。
- 显式 fixture inventory 和 execution receipts。
- 迁移 210 个 manifest 的 required fields。
- 修复 `fixture.json` 发现问题。
- compatibility adapter 不能满足 release validation。
- 统一 runtime level resolver 和 deployment-state 枚举。

发布门：所有插件在源码和 wheel 中得到相同 normalized record；无静默默认升级。

### v0.28.3 Authoritative State Transaction and Boundary Recovery

目标：把“原子文件写入”升级为“原子项目状态提交”。

- ProjectStateTransaction、state revision 和 project-level lock。
- journal profile、migration、checkpoint、stale、passport 全部接入。
- write-set violation 自动回滚项目内写入。
- 路径参数类型化和执行前 boundary preflight。
- MCP execute-science 使用 command-hash capability token。
- doctor 提供 transaction recovery 和 skill drift 诊断。

发布门：crash injection 后 JSON/YAML/manifests/passport revision 一致，越界写入无残留。

### v0.29.0 Artifact Graph and Schema Registry

目标：消除 stage/artifact/schema 多套事实源。

- 实际 artifact nodes、hash、producer、consumer 和 snapshot identity。
- 从 command input/output contracts 生成依赖边。
- schema family registry、JSON Schema、adapter 和兼容矩阵。
- stage status 由 artifact graph 聚合。
- doctor `--explain` 显示真实路径和 hash 链，而不是通用标签。

发布门：新增 consumer 不需要手工维护第二份 stale 列表；旧 schema 有明确迁移或拒绝结果。

### v0.29.1 Declarative CLI and Core Module Decomposition

目标：降低 203 命令和超大模块的维护成本。

- 单一 CommandContract 生成 parser、dispatch、MCP 和文档。
- 按 coordinator 逐批迁移命令。
- 拆分 plugin candidates、methods、review revision、orchestrator。
- 统一 structured artifact repository 和错误模型。
- 保持 CLI 参数向后兼容，提供 deprecation window。

发布门：parser/spec/schema 无重复手工定义；核心模块不再继续增长。

### v0.29.2 CI, Security and Release Hardening

目标：让发布质量不只依赖 pytest 绿灯。

- Ruff、type check、coverage、dependency audit、secret scan、SBOM、license gate。
- GitHub Actions 固定 commit SHA。
- CI/release constraints lock。
- 生成式 release manifest 取代 verifier 常量。
- 修复 SPDX license metadata 和 MANIFEST 警告。
- `tmp/` 生命周期和 doctor 清理策略。

发布门：wheel 可重复构建；source/wheel/release manifest hash 一致；无高危依赖或未解释 secret finding。

### v0.30.0 Cross-discipline End-to-end Acceptance

目标：验证通用架构，而不是继续为单一论文过拟合。

至少从 wheel 安装开始运行以下新项目：

- astronomy + machine learning。
- geography + machine learning。
- bioinformatics + medicine。
- physics 或 quantum science。
- scientific image representation。

每个项目必须覆盖：

1. 中文研究蓝图人工确认。
2. plugin sufficiency、project-local implementation 或 rescue。
3. executable analysis 与六组主图合同。
4. core evidence 人工确认。
5. 五章节自由写作、Results 学科审阅和 semantic repair。
6. 最终 citation audit。
7. 两位独立盲评者和必要仲裁。
8. revision transaction 后重新编译 PDF。
9. 故意注入错误 cohort/run/unit/figure/citation/plugin/transaction 的负向测试。

发布门：所有主图和关键论断能追溯到 research claim、data plugin、method plugin、run output、evidence ID 和 review rule；缺少任一环节时进入明确 rescue，而不是生成相似替代图。

## 9. 最终统一验收矩阵

| 验收项 | 必须结果 |
| --- | --- |
| 完整 pytest | 全绿 |
| isolated wheel | source/install manifest、resource、skill、provenance 一致 |
| section revision | canonical source 与最终 PDF 保留修订 |
| transaction failure | 无半提交文件，状态可恢复 |
| stale propagation | 由真实 artifact graph 计算并写入权威 state |
| plugin truth | manifest/fixture/runtime/deployment 无矛盾 |
| write boundary | 越界尝试被预防或完整回滚 |
| schema compatibility | producer/consumer matrix 全绿 |
| citation audit | 晚于最终正文，保留已确认参考文献，弱支撑优先改写 |
| independent review | 两位 reviewer 独立，critical/major 处理明确 |
| skill deployment | installed skill version/hash 与 package canonical 一致 |
| documentation | README 声明与可执行验收证据一致 |

## 10. 不建议采用的修复方式

- 不回退 evidence-first、Results-first 和核心证据人工确认主链。
- 不用更多固定段落模板解决事务、证据或插件问题。
- 不把 `658 passed` 当作真实论文科学质量已经自动达标的证明。
- 不把 210 个插件批量标记为 runnable 来消除 sufficiency 警告。
- 不通过复制旧项目的 project.json、stage manifest、snapshot 或 audit report 解决兼容性。
- 不允许业务模块继续直接写 `project.json`。
- 不让 write-set guard 只报错但保留违规副作用。
- 不在 P0 未修复时继续宣传 `apply-section-revision` 为完整事务。

## 11. 建议执行顺序

1. 立即完成 v0.28.1，先保证人工修订不会丢失。
2. 完成 v0.28.2，冻结插件真实性合同，再继续扩展插件数量。
3. 完成 v0.28.3，统一项目状态事务和 MCP 写入边界。
4. 再开展 v0.29.0 的 artifact/schema 单一事实源。
5. 在稳定合同上完成 CLI 和大模块重构。
6. 最后以 v0.30.0 新项目全流程回归验收，不使用旧论文原稿作为相对评分基准。

## 12. 最终结论

Draftpaper-loop 的主要科学设计已经走在正确方向，当前最需要的不是继续增加工作流阶段、质量分数或写作模板，而是兑现已有合同：修订必须真正事务化，stale 必须真正写入权威状态，插件“可运行”必须由 fixture/run receipt 证明，MCP 写入边界必须能预防或回滚。

完成 v0.28.1-v0.28.3 后，项目会从“功能丰富但关键状态仍可能失真”进入“用户修订、科学证据和发布状态一致”的稳定阶段；完成 v0.29-v0.30 后，才适合把跨学科扩展和长期公共插件生态作为主要增长方向。
