# Draftpaper-loop 整体架构与代码审计

审计日期：2026-07-12
审计版本：v0.22.0

## 总体判断

Draftpaper-loop 的 evidence-first 方向、结果人工确认点、引用保留原则、学科插件合同和自由写作设计是正确的，但 v0.22.0 目前属于“功能入口完整，运行闭环尚未完成”。现有 394 项测试通过，但不足以证明 wheel 用户、真实论文项目和 95% 质量目标已经达标。

## 关键问题

### [P0] 普通安装后的学科插件实际不可用

构建 wheel 后有 213 个 `template.py`，但学科 `manifest.json=0`、fixture `=0`，安装后的 registry entry 也是 0。运行时恰好依赖 manifest 扫描，见 [pyproject.toml](../../pyproject.toml#L65) 和 [template_registry.py](../../draftpaper_cli/template_registry.py#L36)。源码 editable install 能用，普通 `pip install` 会静默退化。

### [P0] v0.22 自由写作架构没有真正接入主状态机

`run-pipeline` 仍直接推荐 `write-results`、`write-introduction`、`write-data`、`write-methods` 和 `write-discussion`，见 [orchestrator.py](../../draftpaper_cli/orchestrator.py#L32)。没有候选稿时这些命令会使用 deterministic fallback，见 [manuscript_composer.py](../../draftpaper_cli/manuscript_composer.py#L163)。最终 parity 又是条件触发，见 [quality_gate.py](../../draftpaper_cli/quality_gate.py#L672)，所以正式流程并未强制 `codex_free_candidate`。

### [P0] citation audit 与 parity 使用了不兼容的 schema

真实报告输出 `status="passed"`、`summary.blocking_issue_count` 和 `coverage_status`，见 [citation_audit.py](../../draftpaper_cli/citation_audit.py#L588)；parity 却读取 `decision="pass"`、顶层 `blocking_issue_count` 和 `coverage_ratio`，见 [paper_quality_parity.py](../../draftpaper_cli/paper_quality_parity.py#L121)。测试使用的是人为构造的错误 schema，见 [test_manuscript_architecture_cross_discipline.py](../../tests/test_manuscript_architecture_cross_discipline.py#L84)。真实报告目前无法按预期通过 parity。

### [P1] 数字核验仍然缺少语义角色

[section_contracts.py](../../draftpaper_cli/section_contracts.py#L26) 把 registry 中所有数值放进一个全局列表，只比较数值是否出现，不检查 `run/cohort/split/model/unit/evidence_id`；并且直接豁免 0、1、100，见 [section_contracts.py](../../draftpaper_cli/section_contracts.py#L117)。这仍可能放过 source 数、observation 数、样本数和指标之间的错配。

### [P1] Plugin Sufficiency 高估了插件能力

只要本地存在模板或声明 `fixture_runnable` 就可判定 covered，见 [research_capabilities.py](../../draftpaper_cli/research_capabilities.py#L277)。审计的 213 个模板中有 120 个只是调用统一 plan/fixture wrapper，并不执行 SHAP、Astropy、Qiskit 等科学方法。插件验证对非 review 插件也主要是文件存在性，见 [plugin_candidates.py](../../draftpaper_cli/plugin_candidates.py#L3093)。

### [P1] review rules 还不能真正审查结果异常

当前 runtime 主要检查“证据角色是否存在”和“是否出现冲突 token”，见 [review_rule_runtime.py](../../draftpaper_cli/review_rule_runtime.py#L529)，不会执行各插件的 `evaluate_rule`，也不比较真实阈值、量纲、cohort、split、baseline 或不确定性。因此它能确认“有 F1 指标”，但不能可靠判断“这个 F1 是否属于正确测试集、是否达到学科要求”。

### [P1] 95% 评分仍可被关键词和 metadata 轻易满足

Results 评分依赖 baseline、ablation、error、uncertainty 等词是否出现，见 [manuscript_quality.py](../../draftpaper_cli/manuscript_quality.py#L171)；图表评分主要信任 PNG 尺寸和自行声明的 metadata，见 [scientific_figure_quality.py](../../draftpaper_cli/scientific_figure_quality.py#L83)；parity 的多个维度只判断文件或矩阵是否存在。因此当前 0.95 不能等同于“达到原稿 95%”。

### [P1] 引用核查仍是词汇重叠，不是严格语义核查

[citation_audit.py](../../draftpaper_cli/citation_audit.py#L202) 使用 token overlap 和固定阈值，无法可靠识别否定、因果方向、数值范围、研究对象和结论强度。自动修复又可能直接用 evidence summary 替换原句，见 [citation_repair.py](../../draftpaper_cli/citation_repair.py#L43)，容易损失文章本身的论证关系。

### [P2] 状态读取存在隐式写入和并发风险

`load_project` 会自动迁移并写回旧项目，见 [project_state.py](../../draftpaper_cli/project_state.py#L47)；`status` 会刷新 passport 并追加全量 artifact ledger，见 [orchestrator.py](../../draftpaper_cli/orchestrator.py#L719)；ledger 写入采用整文件读写，没有锁和原子替换，见 [passport.py](../../draftpaper_cli/passport.py#L58)。

### [P2] 模块边界和测试体系已接近维护极限

当前有 129 个 CLI 命令、128 段手写 dispatch、39 套 `_read_json`、多个 800-4000 行模块。CI 只在 Python 3.11 上做 editable install，见 [tests.yml](../../.github/workflows/tests.yml#L14)，没有 wheel、Python 3.10、Windows、真实 PDF/图像或真实 producer-to-consumer schema 测试。Codex skill 的阶段顺序也尚未包含新的 Narrative/Editor 链路，见 [SKILL.md](../../codex_skills/draftpaper-workflow/SKILL.md#L35)。

## 最终优化路线

1. **v0.22.1 发布修复**：补齐 wheel 中全部 manifest、fixture、JSON/CSV 资源；增加“构建 wheel -> 隔离安装 -> registry 数量与源码一致”的 CI。同步修复 citation/parity schema。
2. **v0.22.2 主流程接线**：正式增加 narrative preparation、section candidate、Scientific Editor、section acceptance、quality release 阶段。正式模式禁止 deterministic fallback 进入下游。
3. **v0.22.3 Evidence Binding v2**：所有数字和 claim 必须绑定 `evidence_id + run_id + cohort_id + sample_unit + split + model_id + metric_dimension`；删除 0/1/100 特殊豁免。
4. **v0.22.4 Plugin Runtime Truth**：重新定义 `contract_only / code_generator / fixture_executed / project_validated / live_validated`。只有实际执行科学函数并产生声明输出的插件才可满足 sufficiency。
5. **v0.22.5 Reviewer Engine v2**：让 review rule 接收标准化 EvidenceBundle 并真正执行阈值、量纲、泄漏、baseline、ablation、置信区间和 cohort 检查；语义问题优先生成局部 Results 修复任务。
6. **v0.22.6 Figure and Citation Semantics**：图表检查读取实际像素、面板、坐标、图例和底层表格；引用核查升级为来源 passage 检索、数值核验、intent-aware NLI/LLM 判断与段落级修复。
7. **v0.22.7 State Kernel**：`status/load` 改为只读；迁移改成显式命令；JSON 使用 schema validation、原子写入和文件锁；ledger 只追加变化事件。
8. **v0.22.8 结构重构**：拆分 CLI command registry、artifact repository、schema adapters、plugin runtime、writing coordinator 和 release coordinator，消除重复 IO 与多个互相矛盾的质量入口。
9. **v0.23.0 真实发布回归**：使用脱敏后的 geography+ML、astronomy+ML、bioinformatics/medicine 三类完整项目，从 wheel 安装开始运行全流程；加入错误 cohort、错误 metric、伪 metadata、缺失插件和引用反向支持等对抗测试。

## 最终验收标准

- wheel 与源码 registry 都能发现相同的 209 个插件及 fixture。
- `run-pipeline` 不允许任何 deterministic fallback 进入正式质量发布。
- 实际 citation audit 产物可被 parity 正确读取。
- 错误 `run/cohort/unit/split` 的数值必须阻塞，哪怕数值本身存在。
- plan-only 插件不能满足关键图表能力。
- review rule 能发现预置科学异常，而不仅是缺字段。
- `status` 执行前后项目文件哈希不变。
- CI 覆盖 Python 3.10-3.12、Linux/Windows、wheel 安装和三类完整科研回归。
- 科学正确性保持 100%；95% 质量由盲评 rubric、真实图表和完整稿件对比共同确认，而不是由关键词分数单独宣称。

## v0.22.1-v0.23.0 实施结果

实施日期：2026-07-12
发布版本：v0.23.0

| 路线 | 状态 | 权威实现或证据 |
| --- | --- | --- |
| v0.22.1 Wheel 与 schema 修复 | 完成 | `MANIFEST.in`、`pyproject.toml`、`tools/verify_wheel_install.py`；citation producer 经 `schema_adapters.normalize_citation_audit` 进入 parity |
| v0.22.2 正式自由写作状态机 | 完成 | `writing_coordinator.py`、`manuscript_composer.py`、`orchestrator.py`；fallback 只保留诊断资格 |
| v0.22.3 Evidence Binding v2 | 完成 | `section_contracts.py` 与 `writing/claim_bindings/<section>.json`；绑定 run/cohort/unit/split/model/metric/dimension，删除魔法数字豁免 |
| v0.22.4 Plugin Runtime Truth | 完成 | `plugin_runtime.py` 与 `research_capabilities.py`；只有带输出哈希的 project/live 运行可满足核心能力 |
| v0.22.5 Reviewer Engine v2 | 完成 | `review_rule_runtime.py`；标准 EvidenceBundle、阈值、量纲、baseline、ablation、不确定性及插件 evaluator |
| v0.22.6 Figure/Citation Semantics | 完成 | `scientific_figure_quality.py` 读取像素与底层表格；citation audit 检查 passage、数值、否定、因果方向和论断强度 |
| v0.22.7 State Kernel | 完成 | `state_kernel.py`、显式 migration 命令、原子写入、跨平台锁、只读 `status/load` |
| v0.22.8 结构重构 | 完成 | command registry、artifact repository、schema adapters、plugin/writing/release coordinators 已接线；旧 orchestrator 写作副本已删除 |
| v0.23.0 安装态发布回归 | 完成 | wheel 内置三个领域中性 fixture；`release_regression.py` 在普通安装环境运行完整科学证据链与对抗检查 |

## 最终验收证据

- 最终完整测试：`419 passed in 347.44s`。
- 构建产物：`draftpaper_cli-0.23.0-py3-none-any.whl` 构建成功。
- 最终 wheel SHA256：`F9F9390CE5EAF7564AC058FD0D1BD93F4BE8AA2F73FAF31C6EB86B11B62C4A29`。
- 隔离普通安装：成功安装 wheel 及声明依赖，不依赖 editable checkout。
- Registry 一致性：源码与安装包均发现 `209` 个插件和 `545` 个 fixture；JSON/CSV/Markdown 资源计数均为 `747/20/1`。
- 三领域安装态回归：`geography_ml`、`astronomy_ml`、`bioinformatics_medicine` 全部通过插件充分性、项目运行证据、图表追踪、像素/底层表格、Evidence Registry、Results 绑定、review rules 与真实 final citation audit。
- 对抗回归：错误 run、cohort、sample unit、split、model、metric、量纲、空白 PNG + 伪 metadata、contract-only 插件、引用否定冲突、引用数值不符和因果反转全部被拒绝。
- 状态只读：三类安装态项目均验证 `status` 前后所有项目文件哈希不变。
- 正式写作：安装态回归确认没有自由候选稿时只返回 packet/Agent 生命周期动作，不允许 deterministic fallback 进入正式发布。
- Citation schema：三类项目都由真实 `audit_citations(final=True)` 产生报告，再由 parity adapter 正确消费并确认引用覆盖。
- 质量声明：新增 `prepare-blind-quality-evaluation` 与 `record-blind-quality-evaluation`。自动分数不能授权 95%；parity 要求至少两位独立盲评者比较完整稿件和真实图表、科学正确性为 `1.0`、平均质量比例不低于 `0.95`。没有该证据时发布保持 `repair_required`。
- CI 定义：`.github/workflows/tests.yml` 覆盖 Python 3.10-3.12、Ubuntu/Windows，并包含 wheel 普通安装和三领域/对抗回归任务。远端 CI 状态需在提交或推送后由 GitHub Actions 给出，本地验收不伪造远端结果。

## 结论

审计列出的 v0.22.1-v0.23.0 实装路线已经完成，并通过源码测试与普通 wheel 安装态回归。这里的“95%”仍是受控质量声明，不是自动生成稿的自我评分；任何真实稿件只有提交独立盲评证据后才可能通过最终 parity。
