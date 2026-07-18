# Draftpaper-loop v0.30.1-v0.32.0 综合优化实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按任务逐项实现，并在每项完成后运行测试和设置检查点。

**Goal:** 将最终稿作者补全、精确段落修订、安全边界、hard-gate 退出码、stale 传播、命令注册、wheel 发布和 README/DX 收敛到同一套可审计的 Draftpaper-loop 控制面，同时保持证据优先和 Codex 自由写作。

**Architecture:** 保留现有 project_passport、canonical section source、artifact DAG、evidence snapshot、ScopedProjectTransaction、WriteSetGuard 和 CommandSpec 作为唯一底层边界。新增 Manuscript Completion Workspace 只负责把作者 metadata、新文献和多个定点修订组织成候选包、预览包和原子事务，不建立第二套正文或科学事实来源。所有发布能力先经过安全与命令合同修复，再接受 completion 原型，最后通过 wheel、跨平台和真实项目回归。

**Tech Stack:** Python CLI、JSON/YAML schemas、CommandSpec registry、artifact DAG、pytest、wheel isolation、LaTeX/PDF 编译、MCP 本地服务、GitHub Actions。

---

## 0. 适用范围、现状和强制边界

### 0.1 本方案合并的来源

本方案合并以下两份文档，并以它们的风险编号和产物约定为基准：

- docs/superpowers/plans/2026-07-17-final-manuscript-completion-and-readme-opening-optimization.md
- docs/audits/2026-07-17-draftpaper-loop-code-audit-and-optimization.md

### 0.2 当前基线

审计基线是 v0.30.0。当前产品已经具备 evidence-first 研究 loop、阶段 manifest、artifact hash/stale、结果证据冻结、引用核查、学科插件合同、MCP 能力边界、WriteSetGuard、wheel isolation 和跨学科 fixture 回归。这些能力必须保留，不得用新的编辑系统、第二套 workflow DSL 或模板 writer 替换。

旧审计中的 wheel 缺失 paper-fetch、verify-methods 失败仍返回 0、shell 执行、项目路径污染和 pytest/unittest 双轨等问题已有修复记录；本方案要求在发布前重新验证，不能仅凭历史 changelog 认定它们已关闭。

### 0.3 当前工作树 WIP 不是发布能力

审计发现以下未提交改动处于实验状态：

- 修改：draftpaper_cli/__init__.py、draftpaper_cli/cli.py、draftpaper_cli/command_registry.py、draftpaper_cli/latex_assembly.py、draftpaper_cli/manuscript_revision.py
- 新增：draftpaper_cli/manuscript_completion.py、tests/test_manuscript_completion.py
- 新增方案：docs/superpowers/plans/2026-07-17-final-manuscript-completion-and-readme-opening-optimization.md

这些改动只能作为原型输入，不能在 README、release manifest、wheel 或最终报告中宣传为已发布功能。首先必须完成本方案的 P0 对账和安全测试；原型不通过时，只有两种合法处理：完成并验收，或撤出公开命令注册。禁止带着半成品命令发布。

### 0.4 不可违反的边界

1. canonical section source、manuscript metadata、BibTeX、reference registry 和 Scientific Evidence Registry 仍是权威来源；completion workspace 不是第二事实库。
2. 作者 metadata、排版、语言修订与科学证据修改必须分类处理，不能用作者补全入口静默改动已确认的 cohort、run、指标、图表或 claim contract。
3. 行号只能作为用户可读提示；真正写入必须由稳定 paragraph_id、expected text 或 hash 验证。
4. 任意 locator stale、歧义、重叠、版本漂移或写集校验失败时，整个 packet 拒绝应用，不能部分写入。
5. citation audit 必须晚于最后一次带引用的正文修订；最终 PDF、completion manifest、evidence snapshot、citation audit、审稿报告和 release hash 必须属于同一版本。
6. hard gate 的科学 decision 与进程 exit code 必须一致；任何 fail-open 都不允许进入 release。
7. 远程 URL、私有 artifact、外部命令和用户提供的路径均按不可信输入处理。
8. citation audit 的职责是保留已人工确认的参考文献并修正正文支撑关系；除非用户在文献阶段显式确认替换或撤回，audit 不得通过删除 citation、BibTeX 条目或 literature summary 来获得“全绿”。

## 1. 目标状态

### 1.1 用户可见的最终作者流程

用户在得到完整稿后可以填写一个 manuscript_completion.yaml，一次性提供：

- 标题、短标题、摘要、关键词；
- 作者、单位、ORCID、通讯作者、邮箱；
- CRediT 贡献、致谢、基金、利益冲突、伦理声明；
- 数据可用性、代码可用性、补充材料链接；
- 用户已经人工确认的新参考文献及其 DOI/URL、证据说明和使用位置；
- 多个章节、多段落的原文补充、替换、收紧 claim 或引用位置修订。

CLI 先生成统一的缺失项报告、定位报告、科学影响分类、diff 和候选 PDF；用户只在一个集中 checkpoint 接受 packet。接受后以一个事务写入 canonical source、metadata、references、ledger 和状态，再按 change class 精确重建 PDF 与必要的审查。

### 1.2 目标控制面

    User / Codex
      -> start / continue / review / revise workflow macros
      -> CommandSpec registry
      -> security + input schema + write-set preflight
      -> stage handler
      -> artifact DAG + passport + evidence snapshot + ledger
      -> gate decision and explicit exit code
      -> canonical artifacts / candidate overlay / release package

旧的 CLI 巨型 if 链、默认 always_success、与 registry 并行的 stage command 表和未使用的 ID 规范必须逐步收敛到这条控制面；不引入第二套调度框架。

## 2. 现有问题到解决方案的映射

| 审计项 | 严重度 | 综合方案中的落点 | 验收证据 |
|---|---|---|---|
| H-01 Journal URL SSRF | High | §4.3 URL policy | HTTPS、host、私网/IP、大小测试 |
| H-02 registry URL 与 file:// 读取 | High | §4.3 registry loader | allowlist、trusted root、恶意 URL 测试 |
| H-03 MCP 可读 private locator | High | §4.2 artifact policy | private artifact 拒绝与脱敏测试 |
| H-04 verify-methods 任意 argv | High | §4.4 execution policy | executable allowlist、路径 confinement |
| H-05 204/211 命令漂移和 WIP | High | §4.1 release reconciliation | registry/parser/release manifest/wheel 一致 |
| H-06 core evidence fail-open | High | §4.1 gate exit contract | pass=0，非 pass=1 |
| H-07 stale 根映射错误 | High | §5 change/stale taxonomy | DAG parity、revision E2E |
| M-01 soft gate fail-open | Medium | §4.1 gate matrix | hard gate 参数化 exit 测试 |
| M-02 write-set 事后校验 | Medium | §4.4 preflight | 写入前路径和副作用分类 |
| M-03 completion 路径逃逸 | Medium | §6.2 locator/input boundary | resolve_confined_path 对抗测试 |
| M-04 文献异常吞掉 | Medium | §4.5 provider result contract | empty 与 provider_error 分离 |
| M-05 核心依赖过重 | Medium | §9 v0.31.6、§10.5 | extras/doctor/wheel matrix |
| M-06 覆盖率与类型检查不足 | Medium | §9 v0.31.5、§10.5 | core coverage、插件 fixture、pyright |
| M-07 上帝模块与双轨 dispatch | Medium | §9 v0.31.2-v0.31.4 | legacy dispatch 逐步归零 |
| M-08 README/DX 混乱 | Medium | §8、§9 v0.31.7 | start-here、命令分层、双语一致 |
| M-09 子进程环境白名单过严 | Medium | §4.4 runtime environment | 显式允许科研 key、日志脱敏 |
| M-10 陈旧 dist wheel | Medium | §4.1 release reconciliation | dist 只保留当前版本 |
| M-11 always_success 默认与无 handler | Medium | §4.1 registry contract | hard gate 必须声明 policy/handler |
| M-12 loop_contract 与生产 ID 脱节 | Medium | §9 v0.31.1 | 单一 ID 来源或明确降级 |

低严重度的空目录、重复 IO/LaTeX/citation helper、长尾 fixture-only 插件、假依赖图、无 macOS CI、third_party/_vendor 双轨等纳入 §9 v0.31.1-v0.31.9 和 §10，不得以“功能已经很多”为由长期遗留。

## 3. 目标数据模型与目录

### 3.1 Completion Workspace

每个论文项目新增以下目录，但其内容只保存候选、预览和交易证据：

    writing/manuscript_completion/
      template.yaml
      packets/<packet_id>/
        input.yaml
        normalized_packet.json
        missing_fields.json
        locator_resolution.json
        validation_report.json
        change_classification.json
        stale_impact.json
        preview.diff
        preview.md
        preview.pdf
        preview_compile.json
        transaction_receipt.json
      active_completion_manifest.json
      completion_ledger.jsonl

权威产物仍为：

    writing/manuscript_metadata.yaml
    latex/sections/*.tex
    references/library.bib
    references/literature_items.json
    references/citation_evidence.csv
    references/reference_registry.json
    project.json / project_passport.yaml / artifact ledgers

### 3.2 dpl.manuscript_completion.v1

输入必须带 schema_version、project_id 和 target_journal。核心字段结构如下：

    schema_version: dpl.manuscript_completion.v1
    project_id: example-project-id
    target_journal: MNRAS

    metadata:
      title: "Full manuscript title"
      short_title: "Short running title"
      abstract: null
      keywords:
        - galaxy morphology
        - representation learning
      affiliations:
        - id: aff1
          name: "Department, University, City, Country"
      authors:
        - id: author-1
          name: "Author Name"
          affiliations: [aff1]
          email: "author@example.org"
          orcid: "0000-0000-0000-0000"
          corresponding: true
      credit_contributions:
        - author_id: author-1
          roles: [Conceptualization, Methodology, Writing]
      acknowledgments: null
      funding: []
      data_availability:
        statement: null
        links: []
      code_availability:
        statement: null
        links: []
      competing_interests: null
      ethics_consent: null
      supplementary_material: null

    custom_references: []
    section_revisions: []

section_revisions 必须包含稳定 revision_key、target locator、operation、mode、content/content_file 和 requested_by。字段验证必须阻止未知写入路径、绝对路径、项目根外 content_file 和隐式科学证据变更。

### 3.3 三层变更分类

1. Publication metadata：作者、单位、ORCID、致谢、基金、声明和 availability。
2. Manuscript prose/reference revision：语言、段落补充、引用位置、claim 收紧、图表解释修正。
3. Scientific evidence change request：数据、cohort、方法、run、指标、核心图表或 claim contract 的实质改变。

第三层不能由 completion apply 直接完成；系统必须输出 scientific_change_required、受影响阶段和推荐命令，要求用户回到研究蓝图、数据、方法、结果链路。

### 3.4 文件与责任边界

| 责任 | 主要实现文件 | 主要测试或发布证据 |
|---|---|---|
| Completion schema、缺失项、packet normalization | `draftpaper_cli/manuscript_completion.py`、`draftpaper_cli/resources/schemas/` | `tests/test_manuscript_completion.py`、schema registry validation |
| 稳定段落定位与用户原文锁 | `draftpaper_cli/manuscript_revision.py`、`writing/source_map.json` 生成路径 | locator drift、ambiguity、overlap、user-lock tests |
| Preview/apply/rollback 事务 | `draftpaper_cli/manuscript_completion.py`、`draftpaper_cli/command_transaction.py`、`draftpaper_cli/state_kernel.py` | fault injection、idempotency、rollback E2E |
| LaTeX metadata projection 和 PDF 回读 | `draftpaper_cli/latex_assembly.py`、journal profile 与 compile helpers | General/AAS/MNRAS completion regression |
| 变更分类、stale 和 evidence snapshot | `draftpaper_cli/change_impact.py`、`draftpaper_cli/artifact_dag.py` | taxonomy parity、revision/citation/science E2E |
| 命令、gate 和 release truth | `draftpaper_cli/command_registry.py`、`draftpaper_cli/cli.py`、`draftpaper_cli/resources/release_manifest.json` | command inventory、exit matrix、isolated wheel |
| URL、进程、MCP、路径与环境安全 | `draftpaper_cli/journal_profile.py`、plugin candidate loader、`draftpaper_cli/mcp/service.py`、method execution helpers | SSRF、private artifact、argv、path escape、redaction tests |
| README 和作者指南 | `README.md`、`README.zh-CN.md`、`docs/manuscript_completion.md` 及中文版 | command-link validation、UTF-8、双语 parity |

实现时若模块已拆包，以上路径应落到对应子模块，但公开 import、CLI 名称、schema ID 和产物路径保持稳定。

## 4. 先修控制面、安全和发布一致性

本节是 completion 正式验收的前置条件。未完成时，completion 命令不得进入 release manifest 或 wheel。

### 4.1 统一 hard-gate exit contract（H-05、H-06、M-01、M-10、M-11）

修改范围：

- draftpaper_cli/core_evidence.py
- draftpaper_cli/cli.py
- draftpaper_cli/command_registry.py
- 所有 assess-*、verify-*、audit、integrity、quality gate handler
- draftpaper_cli/resources/release_manifest.json
- tools/verify_wheel_install.py
- .github/workflows/tests.yml

合同：

- decision == pass 或命令声明的等价成功状态才返回 0；revise_required、blocked、failed 返回非零。
- 每个 hard gate 必须有真实 handler、输入 schema、写入 globs、风险级别、exit_policy 和测试；禁止依靠 DECLARED_COMMAND_NAMES 自动补出无 handler 命令。
- always_success 只能用于明确的信息查询命令，不能用于科学 gate。
- assess-core-evidence、assess-result-validity、assess-data-quality、verify-methods、citation audit、integrity 和 quality gate 使用同一 dispatch contract。
- 从 parser、registry、release manifest 和 help 文本生成或校验 command inventory；不存在 204/211 漂移。
- 清理过期 dist/*0.28.0*，wheel 版本必须与包版本和 release manifest 一致。

测试：

- pass/revise/blocked/exception 的参数化 exit matrix；
- registry 无 handler、hard gate 使用 always_success、command count 漂移时失败；
- source checkout 与 wheel 安装分别运行 command/schema/plugin/release 验证；
- python -m build --wheel 后执行 python tools/verify_wheel_install.py --wheel-dir dist。

### 4.2 MCP artifact 读边界（H-03）

在 draftpaper_cli/mcp/service.py 的 artifact_get 前执行统一 deny policy：

- 拒绝 **/*.private.json、**/*credentials*、.env、jobs.sqlite3、.draftpaper/** 和 data/external_data_locators.private.json；
- 绝对路径、Windows 用户目录、POSIX home、dataset root 等敏感 locator 必须 redaction；
- 返回结构化 denied、reason_code、safe_alternatives，不能只返回空内容；
- 低风险查询和 protected apply/rollback 分开暴露；MCP 不能绕过 human checkpoint。

新增 tests/test_mcp_private_artifacts.py，覆盖后缀变体、Windows/POSIX 路径、规范化路径和错误响应。

### 4.3 URL 与 registry 输入边界（H-01、H-02）

对 journal_profile.py 的 _fetch_text 和 plugin_candidates.py 的 _read_registry_json 采用同一 safe_fetch policy：

- 默认只允许 HTTPS；http、file://、data:// 和未知 scheme 拒绝；
- host allowlist 或显式 --allow-host，不允许任意 URL；
- DNS 解析后拒绝 loopback、RFC1918、link-local、metadata service 和其他私网地址；
- 限制响应体大小、重定向次数、超时和内容类型；
- registry 本地文件只允许显式 trusted root 下的路径，禁止通过 URL 读取任意本地文件；
- 保留 --from-html/离线输入，网络失败必须写成 provider_error，不能伪装成空检索结果。

新增 journal、registry、redirect、私网 IP、file://、超大响应和离线 fixture 测试。日志只记录 host、状态和错误类型，不写 token、私有 URL query 或响应正文。

### 4.4 外部命令、路径与环境（H-04、M-02、M-03、M-09）

- verify-methods 只允许 sys.executable、项目根内且经过 resolve_confined_path 的相对脚本；系统二进制需要显式 --allow-system-binary 并记录风险，不允许 python -c、shell operator 或隐式解释器代码。
- 所有写入命令先做 write-set preflight，再执行；项目根外路径、符号链接逃逸和未知输出路径在执行前拒绝。
- manuscript_completion 的 content_file 必须解析到项目 allowlist 根，不能读取 .ssh、环境文件或 dataset 外部敏感文件。
- Job/MCP 子进程允许科研 API key 的显式环境白名单，但输出、日志、ledger 和异常必须脱敏；密钥不能写入 project JSON。
- 高风险命令返回 side-effect class、risk level、allowed prefixes 和 rollback policy。

### 4.5 文献 provider 状态（M-04）

将文献检索结果区分为 success_with_items、success_empty、provider_error、auth_required、rate_limited 和 offline_fallback。错误写入 stage manifest、status 和 doctor；只有真正的 success_empty 才能触发“没有候选文献”的后续路线。

## 5. 统一 change classification 与 stale 传播

### 5.1 单一分类枚举

在 change_impact.py 中定义唯一的 change class，并由 artifact_dag.py、completion、revision、citation audit、orchestrator 和 release 共同使用：

    metadata_only
    presentation_only
    prose_only
    citation_change
    claim_boundary_change
    result_interpretation_change
    figure_change
    metrics_change
    run_change
    method_change
    data_change
    cohort_change
    research_plan_change

每个类必须声明 affected_stages、reopen_evidence、rerun_science、rerun_review 和 release_only 属性，禁止各模块维护同名不同义的映射。

### 5.2 stale 规则

| 变更 | 允许直接处理 | 精确影响 |
|---|---|---|
| 作者、单位、ORCID、致谢、基金、声明 | 是 | metadata projection、LaTeX、PDF、release package |
| 纯排版/不改科学语义语言修订 | 是 | 当前 section、integrity、PDF |
| 新增或移动 citation | 是 | 当前 section、final citation audit、PDF |
| 新参考文献 | 是 | reference registry、citation evidence、使用章节、final citation audit、PDF |
| claim 收紧但冻结证据 | 是 | claim boundary、相关 Results/Discussion 一致性、必要的 citation review |
| Results 数字/图表解释修复 | 仅证据 ID 完全一致时 | Results、Discussion、discipline review、citation audit、PDF |
| 数据、方法、run、cohort、核心图表替换 | 否 | reopen research/data/method/evidence/figure/manuscript 链路 |

应修复 stage_roots_for_change 与 change_impact.affected_stages 的 parity，特别覆盖 methods、discussion、results、references 和 completion。测试必须验证 revision/apply 后 project.json 和 artifact ledger 的 stale flags 与实际影响一致。

### 5.3 Evidence snapshot 规则

completion apply 前后都核对 project revision、evidence snapshot、canonical before hash 和目标 locator hash。metadata-only 不能触发科学重跑；科学变更不能通过 completion patch 伪装成 prose change。最后一次带引用或科学语义的修改完成后，citation audit 必须重新执行。

## 6. Manuscript Completion Workspace 正式实现

### 6.1 用户命令和 API

    draftpaper prepare-manuscript-completion --project <project>
    draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
    draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
    draftpaper manuscript-completion-status --project <project>
    draftpaper rollback-manuscript-completion --project <project> --transaction-id <id>

稳定 Python API 与 CLI 一一对应：

    prepare_manuscript_completion(project)
    preview_manuscript_completion(project, input_path)
    apply_manuscript_completion(project, packet_id, packet_hash)
    rollback_manuscript_completion(project, transaction_id)
    resolve_manuscript_revision_target(project, locator)

所有命令进入 CommandSpec，声明 schema、写入 globs、风险、幂等和 rollback policy。prepare/preview/status 是低风险；apply/rollback 属于 protected action，必须有明确 packet hash 和用户确认。

### 6.2 显式双重定位合同

定位优先级：

1. paragraph_id；
2. expected_sha256；
3. 规范化后的 expected_text + occurrence；
4. line_start_hint-line_end_hint 仅用于缩小候选和展示。

解析规则：

- 行号、ID、text/hash 唯一一致：正常预览；
- 行号漂移但 ID/hash 唯一一致：允许重新定位，同时报告新行号；
- 行号命中但 text/hash 不一致：stale_target，拒绝；
- text 重复且无 ID/occurrence：ambiguous_target，拒绝；
- paragraph ID 已指向变化正文：要求重建 source map；
- 禁止 Codex 按“最相似段落”猜测并自动写入。

draftpaper revise 的公开形式：

    draftpaper revise
      --project <project>
      --at latex/sections/methods.tex:118-126
      --expect-text-file target_paragraph.txt
      --instruction "在此段后补充稳健性分析，但不要改变已确认的样本边界"
      --operation insert_after
      --mode instruction_to_codex

用户提供原文时使用 --content-file 和 --mode exact_text；接受后写入 writing/user_locks.json，后续 writer 或 Scientific Editor 不能静默覆盖。

### 6.3 批量 packet 解析

preview 使用同一个 source-map/project revision：检查重复目标、重叠区间、操作冲突和 evidence snapshot；按文件和原始 offset 从后往前生成 overlay；每项记录 resolved paragraph ID、旧/新行号、before/after hash。任一项 stale、ambiguous 或 invalid，整个 packet 不可 apply。

### 6.4 Preview、Apply、Rollback

Preview 不修改 canonical source，必须完成：

- schema、期刊必填项、placeholder、作者/单位/ORCID/email/链接校验；
- metadata 与 evidence registry 的 abstract/claim 边界检查；
- section locator、批量冲突、custom reference 去重和 citation evidence 检查；
- change classification、stale impact 和统一 diff；
- metadata、sections、references 的候选 LaTeX overlay；
- 可用 TeX 时编译 preview.pdf，并回读标题、作者、致谢、availability、链接和定点正文；无 TeX 时明确 compile_required，不能报通过；
- 输出不可变 packet_hash。

Apply 使用 ScopedProjectTransaction，写入 metadata、受影响 section、BibTeX、literature items、citation evidence、reference registry、user locks、revision/completion ledgers、stage state、artifact DAG 和 LaTeX 派生产物。应用前再次核对 packet hash、canonical before hash、project revision 和 evidence snapshot；任何异常整体 rollback。

Rollback 只允许在当前 after hash 与 receipt 一致时执行，不能覆盖用户在 apply 后的新修改。

### 6.5 幂等和去重

- packet_id + normalized_packet_hash 是幂等键；重复 apply 返回原 receipt，不重复写入。
- 作者按稳定 author ID/ORCID 去重，单位按 affiliation ID 管理。
- DOI、URL、citation key、规范化题名和版本关系用于文献去重。
- revision_key + before_hash + after_hash 防止重复插入。

## 7. 最终 main.pdf 发布合同

最终流程：

    prepare template
      -> user fills one completion YAML
      -> schema/journal validation
      -> locator resolution and conflict check
      -> metadata/reference/section overlay
      -> unified diff + stale/evidence report + candidate PDF
      -> one human acceptance
      -> atomic canonical transaction
      -> precise stale propagation
      -> assemble-latex and compile main.pdf
      -> final citation and bibliography audit
      -> discipline/integrity/quality gates
      -> two independent blind reviewers when coverage is affected
      -> final release packet
      -> human confirmation of release hash

review-final-manuscript 的 release hash 必须绑定：

- active_completion_manifest.json；
- manuscript metadata 和 canonical section hash；
- reference registry/BibTeX、final citation audit snapshot；
- evidence snapshot、核心结果/图表 manifest；
- 必需的两份独立匿名审稿报告；
- latex/main.pdf hash；
- final integrity/quality report。

这样可以证明最终 PDF 包含作者最后确认的信息，而不是只证明某个旧 PDF 曾经通过。

## 8. README、命令体验和文档收敛

### 8.1 README 开头目标

README 中英文开头统一按以下顺序，控制在一屏到两屏：

1. 产品名和一句话定位；
2. 当前版本及能力边界；
3. 论文如何到达 main.pdf；
4. 系统保证什么；
5. 哪些仍由用户确认；
6. 最终作者补全与精确修订；
7. 再进入详细功能、Loop Model 和 Quick Start。

不要在开头重复完整 changelog；旧的 loop philosophy 放入 Loop Model；详细 CLI、商业说明和 AcademicForge/第三方来源迁移到 docs。

### 8.2 中文开头建议

    # Draftpaper-loop

    **本地优先、证据优先的科研论文工作流：先确认研究蓝图与关键结果，再自由撰写、审查并发布可追溯的 main.pdf。**

    Draftpaper-loop 不是一次性论文生成器。它把文献、研究计划、数据与方法执行、关键图表、Results、其余章节、引用核查、学科审查、独立审稿和最终 PDF 组织为可恢复、可追溯的科研 loop。Codex 负责开放性的研究推理和自然科研写作；确定性合同负责验证证据版本、cohort、run、图表语义、公式、引用、插件来源、stale 状态和最终发布一致性。

    ## 当前版本

    当前版本为 v0.30.0。v0.30.0 的跨学科 fixture 只验证通用流程合同；真实项目必须使用已验证的 live runnable 插件或可审计的 project-local 方法运行，mock 和 fixture 不能冒充科研证据。completion 能力在正式验收前应标记为 experimental WIP，不得写进 release 主路径。

    ## 论文如何生成

    idea 与文献 -> 中英文研究蓝图和人工确认 -> 数据/方法插件匹配与真实执行 -> 主图组/附录图 -> 结果支撑和论断强度确认 -> Results -> Introduction/Data/Methods/Discussion -> 学科规则审查 -> 最终 citation audit -> 两位独立盲评者 -> 作者补全和精确修订 -> 编译与 hash 确认 -> latex/main.pdf

    当结果不能支撑计划论断时，流程不会生成相似图或继续写作；用户必须选择收窄论断并冻结结果，或补充数据/方法后重跑证据链。

    ## 补全与修订最终稿

    用户可以通过一个 manuscript_completion.yaml 一次性补充作者、单位、ORCID、基金、致谢、数据/代码链接、声明、新参考文献和多个章节修订。行号只作为提示，paragraph ID、原文和 hash 才是写入依据。系统先生成统一 diff、影响范围和候选 PDF，用户确认后才事务式写入 canonical source。

### 8.3 命令分层与双平台示例

README 只保留研究者最常用的 start、status、continue、review、revise、doctor、recover 和 final author workflow；完整 200+ 命令进入生成式 CLI reference。每个示例提供 PowerShell 和 bash 版本，并说明 continue 是恢复 loop、revise 是产生候选修订，不是无条件重写。

Final author workflow 示例：

    draftpaper prepare-manuscript-completion --project <project>
    draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
    draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <hash>
    draftpaper review-final-manuscript --project <project>
    draftpaper confirm-final-manuscript --project <project> --release-hash <hash>

### 8.4 README 质量检查

- 中英文开头、命令和版本边界一致；
- README 中出现的命令均可在 CommandSpec registry 找到；
- 版本号、command count、插件数、fixture 范围和 release contract 来自单一版本源或 CI 校验；
- 中文文件以 UTF-8 写入并做编码回读；
- 不在 README 宣传未验收的 completion、mock、fixture-only 或深度不足的学科能力。

## 9. 分阶段实施路线

### v0.30.1：发布对账与 hard-gate 止血

- 修复 assess-core-evidence、assess-result-validity、assess-data-quality 等非 pass exit code；
- 为所有 hard gate 补齐真实 handler、exit_policy 和测试；
- 对账 parser/registry/release manifest 的 command inventory，解决 204/211 漂移；
- 处理 manuscript-completion WIP：验收后纳入，未验收则撤出公开注册；
- 清理陈旧 dist wheel，构建当前 wheel 并执行 wheel isolation；
- 拒绝 MCP private artifact 和 private locator；
- 对 completion content_file 加路径 confinement；
- 至少部署 journal/registry 的 HTTPS、host、私网 IP 和 file:// 拒绝骨架。

发布门：fail fixture 的 gate 必须 exit 1；pytest、wheel verify、secret scan、command/schema/plugin/provenance checks 全部通过。

### v0.30.2：安全策略与运行环境收口

- 完成 URL allowlist、size/timeout/redirect policy；
- 完成 verify-methods executable allowlist、shell operator 拒绝和项目内路径校验；
- write-set 由事后检查扩展为执行前 preflight；
- 子进程环境白名单加入科研 API key 并持续脱敏；
- 文献 provider error 结构化；
- 完成 gate exit-code 参数化测试和 pyright 扩展到 gates、stale 和 completion。

### v0.30.3：change classification 与 stale parity

- 建立 §5 的单一 change class 枚举；
- 重写 stage_roots_for_change，与 change_impact.affected_stages 使用同一映射；
- 为 revision、citation、completion、figure、method、data、cohort 和 claim 变化补充 E2E；
- 验证 metadata-only 不重跑科学链，科学变化必须 reopen；
- 将 evidence snapshot 版本核对接入所有写入命令。

### v0.30.4：Completion Schema 与期刊缺失项报告

- 正式实现 dpl.manuscript_completion.v1；
- 新增 prepare-manuscript-completion、manuscript-completion-status；
- 从 journal profile 输出 required/recommended/missing/placeholder/not-applicable；
- 完成 metadata、funding、availability、short title、keywords 和 custom reference schema；
- 不允许 schema 直接改科学证据。

### v0.30.5：双重定位与批量候选解析

- 支持 paragraph ID、line hint、expected text、expected hash、occurrence；
- 实现 stale/ambiguous/conflict 诊断；
- 同一个 packet 支持多章节、多段落和 custom references；
- 所有目标基于同一个 source-map/project revision；
- 扩展 revise 的 expect-text、expect-text-file 和 user lock。

### v0.30.6：Preview、原子 apply 与 rollback

- 实现 preview-manuscript-completion、apply-manuscript-completion、rollback-manuscript-completion；
- 候选 overlay 同时覆盖 metadata、sections、references、LaTeX 和 PDF；
- 输出 locator report、change/stale report、统一 diff、compile status 和 packet hash；
- 使用 ScopedProjectTransaction 全写集 rollback；
- 写入 completion ledger、revision ledger 和 user locks；
- 完成幂等、重复文献、重叠 patch、注入失败和 rollback 对抗测试。

### v0.30.7：最终发布绑定与作者文档

- active completion manifest、metadata、section、reference、evidence、citation audit、reviewer、quality 和 PDF hash 统一进入 final release packet；
- 实现 compile_required 的非通过语义；
- 完成 metadata/citation/claim/result/scientific evidence 的 precise stale；
- 新增 docs/manuscript_completion.md 和中文版；
- 按 §8 更新 README 中英文开头和 final author workflow，但在实际验收前不把 WIP 宣传为稳定能力。

### v0.31.0：Completion 全回归与 v0.31 发布

- 至少三类期刊模板执行完整补全和 PDF 验证；
- 覆盖单作者、多作者、多单位、通讯作者、ORCID、基金、链接、新文献和多段修订；
- 覆盖行号漂移、hash 不匹配、歧义文本、重叠 patch、重复 apply、事务故障、rollback 和 user lock；
- 验证最终 citation audit 晚于最后一次带引用修订；
- 验证 wheel/source checkout 的 CLI、schema、templates、README 命令一致；
- 验收后更新 release manifest 和版本文档。

### v0.31.1：共享工具与生产 ID 收口

- 统一 `io_utils`、`latex_utils` 和 citation helpers，删除重复 JSON/text/escaping 实现；
- 处理 `loop_contract.py`：接入真实 claim/evidence/artifact ID，或降级为规范文档并移除测试伪入口；
- 清理空目录、无调用依赖图和不可达辅助函数；
- 保持公开 import 与现有 artifact ID 向后兼容。

发布门：工具层回归通过；同一产物不再由两套 helper 产生不同 hash 或 escaping。

### v0.31.2：Plugin Candidate 包化

- 将 `plugin_candidates.py` 拆为 common、source loader、extractors、promotion 和 contribution 子模块；
- 保留稳定 re-export、私有 registry 扩展点和 `promote-plugin-candidate` 行为；
- 明确 fixture-only、contract-only、mock 和 live runnable 的运行真值；
- doctor 和 provenance 报告不得把候选或 fixture 说成正式科研能力。

发布门：candidate extraction/promotion/contribution 全量回归，source checkout 与 wheel registry 一致。

### v0.31.3：Methods 拆分与 Figure Contract Façade

- 将 `methods.py` 拆为 verification、formulas、writer 和 common；
- 建立统一 figure contract façade，把 gate、semantic、caption 和 confirmed-plan finding 标准化为单一 issue schema；
- 保持旧 API re-export，避免现有学科插件和项目运行失效；
- figure issue 必须保留来源、严重度、figure ID 和可执行修复信息。

发布门：Methods/figure compatibility 回归通过，同一问题不会被多套检查器重复或矛盾报告。

### v0.31.4：CommandSpec 单一控制面

- 将 `cli.py` 剩余 legacy dispatch 迁入 CommandSpec；
- 要求 `legacy_dispatch_count == 0`，兼容 namespace adapter 数量必须显式报告，不能伪装成 typed handler；
- orchestrator 的 stage command map 从 registry 生成；
- 所有命令显式声明 handler/adapter、exit policy、risk、write globs 和 rollback policy。

发布门：parser、registry、orchestrator、help、release manifest 和 wheel command inventory 完全一致。

### v0.31.5：Schema Registry 与质量门

- 为 release fixture、capability pack、command registry、release manifest、method run/formula manifest 和 figure assessment 注册稳定 schema ID；
- release fixture 只能引用已登记 schema，packaged resources 必须执行 schema validation；
- coverage 先达到 55%，再提升到至少 65%；
- pyright 扩展至 gates、stale、completion、command registry、figure façade 和 Methods 子包；Ruff 保留高信号错误门。

发布门：schema report 无未登记资源，coverage/pyright/Ruff 和 isolated wheel 全部通过。

### v0.31.6：依赖与安装矩阵

- 将 plotting、fulltext、MCP 等能力整理为清晰 extras，避免默认安装承担全部科研生态成本；
- doctor 输出缺失 extra、可用 provider、runtime source 和恢复命令；
- 验证 minimal、plotting、fulltext、MCP 和 research profile 安装矩阵；
- 始终保留 `_vendor/paper_fetch_skill` 作为 wheel fallback，`third_party/registry.json` 负责来源与许可证记录，二者不互相替代。

发布门：任一安装档位不会声称未安装能力可用，也不会因 paper-fetch 不在 PATH 静默丢失全文补充能力。

### v0.31.7：README、CLI Reference 与作者体验

- README 中英文收敛为 8-12KB 的入口文档，完整命令、插件、MCP、安全、商业和 AcademicForge 来源迁入专题文档；
- 增加 start/status/continue/review/revise/doctor/recover/final-author 的双平台示例；
- 自动生成 CLI reference，README 命令必须可在 CommandSpec registry 验证；
- 发布 `manuscript_completion` 中英文指南、期刊字段说明和失败恢复示例。

发布门：双语结构、版本、命令和能力边界一致，新用户可在两分钟内找到完整论文与最终作者修订路径。

### v0.31.8：成本、风险与产品说明

- 增加阶段 token/cost report，并为超过 manuscript budget 的运行设置人工确认；
- 输出命令风险表、side-effect class、可写路径和恢复能力；
- 增加 install matrix、researcher profile 一键检查和 commercial one-pager；
- 明确本地 CLI、MCP、本地 job 与未来托管服务的责任边界。

发布门：成本和风险报告来源于真实 ledger/CommandSpec，而不是 README 手工常量。

### v0.31.9：跨平台与发版验证

- CI 保持 Windows/Linux，条件允许时增加 macOS smoke；
- 增加 tag-build-verify，校验 tag、包版本、release manifest、wheel 和文档版本一致；
- 清理陈旧 dist，执行 source/editable/isolated-wheel 三形态验证；
- 依据许可证只提供允许的私有或授权分发流程，不默认开启公开 PyPI 发布。

发布门：三种安装形态和支持平台共享同一命令、schema、插件与 provenance truth。

### v0.32.0：稳定发布与隔离评估

- 汇总 v0.30.1-v0.31.9 的 completion、安全、stale、CommandSpec、schema、安装和文档能力；
- 完成至少三类期刊 completion 回归及既有五类跨学科流程合同回归；
- 生成 requirement-by-requirement completion audit 和 release reconciliation；
- 只提交 sandbox/container 的本地执行评估报告；在鉴权、租户隔离、出站代理和数据隔离完成前，不提供公网托管 API。

发布门：第 12 节全部验收项通过，release manifest、wheel、README、审计报告和 Git tag 指向同一版本。

## 10. 测试和验收矩阵

### 10.1 P0/P1 安全与控制面

- hard gate pass/fail/revise/blocked 的 exit code；
- command registry handler、exit policy、write globs、risk 和 command count；
- MCP private artifact 拒绝、敏感路径脱敏和 protected action；
- journal/registry 的 HTTPS、host allowlist、私网 IP、file://、大小和 redirect；
- verify-methods 系统二进制、python -c、shell operator、绝对路径和项目外路径拒绝；
- completion content path escape、符号链接 escape 和环境文件读取拒绝；
- 文献 success_empty 与 provider_error 分离。

### 10.2 Completion 定位与事务

- locator 全部一致时通过；
- 行号漂移但 ID/hash 唯一时重新定位并提示；
- 行号一致但 text/hash 不一致时 stale_target；
- 重复 text 无 occurrence/ID 时 ambiguous_target；
- 同一 packet 的重叠 patch、重复目标和冲突 operation 全部拒绝；
- metadata、正文、BibTeX、registry、state、ledger 全部成功才提交；
- 任何注入故障整体恢复；
- 重复 apply 不重复文本/引用；rollback 只接受当前 after hash；user lock 阻止后续 writer 覆盖。

### 10.3 科学边界和 stale

- 作者、致谢和纯 metadata 不 stale data/method/results/figures；
- 新 citation 使 final citation audit stale；
- Results 数字与 Evidence Registry 不一致时拒绝 completion apply；
- cohort/run/method/figure 变化生成 reopen 路线，不做正文 patch；
- claim 收紧只影响 claim boundary 与必要写作/审查，不重跑已冻结结果；
- 最后一次科学/引用修改后 citation audit 才能执行。

### 10.4 PDF 与发布

- PDF 回读标题、作者、单位、ORCID、致谢、数据/代码链接和定点正文；
- 长单位、长 URL、多作者、多语言不出现明显溢出；
- 当前 completion manifest、evidence snapshot、citation audit、review reports、quality/integrity 和 PDF hash 绑定；
- 匿名 reviewer bundle 不泄漏作者 metadata；
- 无 TeX 时是 compile_required/非 release，而不是绿灯。

### 10.5 质量与发布命令

    pip install -e ".[dev]"
    python -m pytest -q
    python -m draftpaper_cli.cli validate-command-contracts
    python -m draftpaper_cli.cli validate-template-registry
    python -m draftpaper_cli.cli validate-third-party-provenance
    python -m build --wheel
    python tools/verify_wheel_install.py --wheel-dir dist
    python tools/scan_secrets.py

CI 必须同时验证 source checkout、editable install 和 isolated wheel；版本、command inventory、schema、plugin catalog、third-party provenance 和 wheel 内 _vendor/paper_fetch_skill 一致。

## 11. 责任边界和暂不实施项

### 11.1 必须保留

- evidence-first：研究蓝图、图表/指标和人工确认先于 Results 及其余章节；
- Codex 自由写作：contracts 控事实，不把 prose 退化成模板拼接；
- 本地项目 source of truth、artifact hash/stale、ledger 和可回滚事务；
- 学科插件和 capability packs 的 runtime truth；mock/fixture 只能验证接口；
- wheel isolation、paper-fetch vendored fallback、secret scan、MCP 风险分级。

### 11.2 当前不做

1. 控制面、安全、退出码和 stale 未稳定前，不继续扩大学科引擎数量。
2. 不先引入完整 OS sandbox 或新的 workflow DSL；先完成 allowlist、path confinement 和 write-set preflight。
3. 不一次性把 coverage 拉到 80% 或全量开启严格 lint；分阶段提升以保留有效信号。
4. 许可为 NonCommercial/自定义 LicenseRef 时不直接开启公开 PyPI 自动发布。
5. 不把 command_transaction 宣传成完整 ACID；ledger 和 ScopedProjectTransaction 的职责必须分开。
6. 不删除 _vendor/paper_fetch_skill 来“统一” third_party；两者分别承担 runtime fallback 和 provenance 记录。
7. 不在未完成多租户安全、鉴权、出站代理和数据隔离前提供公网 API。
8. 不在 completion 未通过完整回归前将其写成稳定 release 卖点。

## 12. 最终验收标准

方案完成后必须同时满足：

1. 所有 hard gate 的科学失败都以非零 exit code 暴露，registry、parser、release manifest 和 wheel command inventory 一致。
2. Journal/registry SSRF、MCP private artifact、外部命令、路径逃逸和敏感环境变量均有明确阻止与测试。
3. change classification 只有一个权威来源，revision、citation、completion、data/method/figure 变化的 stale 传播与 DAG 一致。
4. 用户只填写一个 completion YAML，就能一次补齐出版 metadata、新参考文献和多项精确段落修订。
5. 每个正文目标由 paragraph ID、expected text/hash 验证；行号漂移不会误改，歧义或 stale 会拒绝整个 packet。
6. preview 能同时展示缺失项、统一 diff、stale/evidence 影响、引用警告、候选 PDF 和 compile 状态。
7. apply 是一次原子事务，重复 apply 幂等，失败整体回滚，user lock 防止静默覆盖。
8. 纯 metadata 不重跑科研链；scientific evidence change 不能伪装成 prose patch，并会生成 reopen 路线。
9. 最终 main.pdf、completion manifest、canonical sections、reference registry、citation audit、evidence snapshot、独立审稿报告和 release hash 属于同一版本。
10. README 中英文开头能在两分钟内说明研究 loop、人工确认点、作者补全方式和 mock/live 边界，所有命令示例都能在 registry 中找到。
11. source checkout、editable install、isolated wheel、Windows/Linux（并尽可能 macOS smoke）均通过同一 release 和安全门。

## 13. 推荐执行方式

严格按依赖顺序执行：

    P0 release / exit / security
      -> stale and evidence parity
      -> completion schema
      -> locator and batch preview
      -> atomic apply / rollback
      -> final PDF and release hash
      -> README / author docs
      -> modularization / schema / coverage / DX
      -> cross-platform and multi-journal regression

每个版本只承担一个可验证的控制面变化；每完成一个版本都要运行对应测试、更新 release manifest 和 README 状态，再进入下一版本。不要在安全和 release 对账未通过时继续增加新命令或学科插件。

**Recommended implementation handoff:** 先执行 v0.30.1 的 P0 清单并生成一份不包含实验性 completion 的 release 对账报告；之后逐项执行 v0.30.2-v0.31.0。v0.31.1-v0.32.0 仅在前述回归稳定后开始。
