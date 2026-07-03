# Draftpaper-loop 代码审计报告

**日期**: 2026-07-02  
**目标仓库**: https://github.com/xiejhhhhhh/Draftpaper_loop  
**审计快照**: `main` · `02d9ed34d46588e88e1aa115c5587faa6a8ca96b` · 2026-07-02T12:42:18Z · `Add strict figure contract repair loop`  
**本地范围**: `/Users/nullin/codexM/Draftpaper_loop-main/`  
**审计口径**: 参考用户提供的样例报告，重点审计零运行时引用、重复实现、预测性架构、过度分层、配置/发布双轨、测试真实性与可删减风险；同时补充命令执行、凭据和打包发布边界。

---

## 一、项目库存

| 类别 | 数量/规模 | 说明 |
|---|---:|---|
| 全仓文件 | 1551 | 含文档、fixtures、第三方 vendored 源码 |
| `draftpaper_cli/` Python | 122 文件 · 24,276 行 | 可发布核心包 |
| 核心顶层模块 | 45 文件 | `cli.py`、阶段 gate、写作器、引用、LaTeX、review 等 |
| 学科模块 | 65 Python · 3,599 行 | `discipline_modules/`，含 42 个 `template.py` |
| Review engines | 10 Python · 912 行 | 学科审稿规则 |
| Tests | 45 Python · 8,039 行 | CI 用 `unittest` |
| `third_party/paper-fetch-skill/` | 1299 文件 · 451 Python | 源码树内 vendored，但不进入 wheel |

---

## 二、最高优先级问题

### 2.1 wheel 发布包缺失 `paper-fetch` vendored fallback

`draftpaper_cli/paper_fetch_adapter.py` 在没有系统 `paper-fetch` 命令时，会查找源码树根目录下的 `third_party/paper-fetch-skill/src`：

| 文件 | 行号 | 问题 |
|---|---:|---|
| `draftpaper_cli/paper_fetch_adapter.py` | 24-30 | `_repo_root()` 取 `draftpaper_cli` 的上级目录，再找 `third_party/paper-fetch-skill/src` |
| `draftpaper_cli/paper_fetch_adapter.py` | 40-47 | 找不到 PATH 命令时才使用 vendored fallback |
| `pyproject.toml` | 46-48 | setuptools 只包含 `draftpaper_cli*`，显式排除 `third_party*` |

我用 `pip wheel . --no-deps` 构建验证：生成的 wheel 只有约 348KB，`third_party entries = 0`。因此：

- 源码 checkout / editable install 可用 vendored fallback。
- wheel / 普通 site-packages 安装大概率没有 `third_party/paper-fetch-skill/src`。
- `paper-fetch` 不在 PATH 时，`resolve_paper_fetch_command()` 会返回 `runtime_source="missing"`，文献全文补充能力退化。

**建议**: 选一个权威方案，不要双轨漂移。

1. 若 `paper-fetch` 是运行时依赖，发布成正式 dependency 或 extra。
2. 若必须 vendored，则用 package data 包进 wheel，并把 `_vendored_source()` 改为 `importlib.resources`。
3. 若只支持源码树模式，则 README/CLI manifest 明确写 `vendored` 仅在源码 checkout 可用。

### 2.2 `verify-methods` 失败时 CLI 仍返回 0

`verify_methods()` 会把失败写入 manifest：

| 文件 | 行号 | 说明 |
|---|---:|---|
| `draftpaper_cli/methods.py` | 126-132 | 执行命令后，根据 returncode、缺失输出、figure quality、review coverage 计算 `status` |
| `draftpaper_cli/methods.py` | 151-154 | `status=failed` 时更新 `methods` 阶段为 failed |
| `draftpaper_cli/cli.py` | 702-712 | `verify-methods` 打印结果后无条件 `return 0` |

这会导致 shell/CI/自动化误判方法验证已经通过。当前同一个 CLI 文件里 `quality-check`、`audit-citations`、`run-integrity-gate` 会按状态返回非零，退出码语义不一致。

**建议**: `verify-methods` 改为：

```python
return 0 if result.get("status") == "success" else 1
```

同时审一遍 `assess-result-validity`、`assess-core-evidence` 这类 gate 命令，决定它们是“信息命令”还是“硬 gate”；若是硬 gate，应按 `decision` 返回非零。

### 2.3 `verify_methods()` 使用 `shell=True`

| 文件 | 行号 | 问题 |
|---|---:|---|
| `draftpaper_cli/methods.py` | 108-127 | `verify_methods(..., command: str)` 直接 `subprocess.run(command, shell=True, cwd=state.path, ...)` |

这是本地研究工作流里的有意能力，但边界必须非常清楚：用户传入的命令会被 shell 解释执行。它不适合接收来自网页、远程任务、LLM 自动拼接或未确认项目文件的命令字符串。

**建议**:

- CLI 层保留显式 `--command` 但文档写清“本地 shell 执行，必须人工确认”。
- 内部生成的 `verify_command` 可改成 argv list 或用 `shlex.split()` 后 `shell=False`。
- `run_manifest.yaml` 继续记录命令，但避免把环境变量、token、绝对私有路径写入 stdout/stderr。

### 2.4 每个新项目都会写入开发者本机历史路径

| 文件 | 行号 | 问题 |
|---|---:|---|
| `draftpaper_cli/project_scaffold.py` | 241-244 | `source_mvp.path = "D:\\DraftAI_agent"` 写入每个新项目的 `project.json` |

文档中提到旧 MVP 路径可以作为历史说明；但 `create_project()` 写入生成项目元数据，会把不可用的 Windows 本机路径传播给用户项目，降低可移植性，也会污染后续 provenance。

**建议**: 删除 `source_mvp.path`，或改为中性字段，例如 `source_mvp_reference="legacy MVP design notes"`；如果确实需要路径，应由本地配置或环境变量注入，不进入默认项目 JSON。

---

## 三、零运行时引用 / 非 import 资产

### 3.1 核心死代码候选

| 文件 | 行数 | 运行时引用 | 测试引用 | 判断 |
|---|---:|---:|---:|---|
| `draftpaper_cli/loop_contract.py` | 78 | 0 | 1 | DPL 稳定 ID 工具未接入生产路径 |

`loop_contract.py` 定义 `DPL_LOOP_EVENTS`、`DPL_ERROR_PREFIXES`、`stable_claim_id()`、`stable_evidence_id()`，但实际 DPL 元数据走 `provenance.py`。目前只有 `tests/test_dpl_contract.py` 引用它。

**建议**: 要么把 claim/evidence ID 生成接入引用、claim trace、citation audit；要么把它移到 docs/spec 或删除测试-only 代码。

### 3.2 不应误判为死代码的资产

以下文件没有普通 import 入边，但不是死代码：

| 资产 | 规模 | 使用方式 |
|---|---:|---|
| `draftpaper_cli/plotting/scientific_svg.py` | 661 行 | `analysis_code.py` 通过 `read_text()` 复制为项目本地 `methods/src/scientific_plotting.py` |
| 学科 `template.py` | 42 文件 | 由 `DataConnectorSpec.template_paths` / `MethodTemplateSpec.template_path` 作为模板资产登记 |
| 学科 `manifest.json` | 38 文件 | 插件/模板元数据 |
| fixture 文件 | 24 文件 | 模板测试和示例输入 |

**维护风险**: 这些属于“资源型运行时代码”，引用关系不能被普通 import 扫描发现。建议把模板读取集中到一个 `template_registry`，并在测试中校验每个 declared template path 都存在、能导入或能按约定执行。

---

## 四、严重重复实现

### 4.1 LaTeX 转义函数重复

同构 `_safe_latex_text` 至少 4 份完全重复：

| 文件 | 行号 |
|---|---:|
| `draftpaper_cli/results.py` | 36 |
| `draftpaper_cli/latex_assembly.py` | 77 |
| `draftpaper_cli/introduction.py` | 66 |
| `draftpaper_cli/discussion.py` | 71 |

另外 `methods.py`、`data_feasibility.py` 也有相近版本。建议提取到 `latex_utils.py`，避免后续支持反斜杠、Unicode 或命令白名单时多处漂移。

### 4.2 JSON/text 读取重复

精确重复扫描结果：

| 重复函数族 | 复制数 | 典型文件 |
|---|---:|---|
| `_read_json` / `read_json` 8 行版 | 6 | `review_revision.py`、`discipline.py`、`results.py`、`result_validity.py`、`data_acquisition.py`、`review_engines/base.py` |
| `_read_json` 7 行版 | 5 | `figure_plan.py`、`method_plan.py`、`methods.py`、`method_blueprint.py`、`plugin_candidates.py` |
| `_read_text` 5 行版 | 4 | `review_revision.py`、`citation_audit.py`、`citation_repair.py`、`integrity_gate.py` |

建议提取 `io_utils.read_json(path, default)` / `read_text(path, default="", errors="replace")`，并统一 JSON decode 失败时是吞掉还是抛出 gate error。

### 4.3 citation key 解析重复

`_bibtex_keys` / `_latex_citation_keys` 在 `latex_assembly.py`、`integrity_gate.py`、`quality_gate.py`、`introduction.py`、`discussion.py` 中重复。引用校验是论文系统核心 gate，应有单一解析实现和一组共享测试。

---

## 五、过度分层与双轨

### 5.1 `cli.py` 单文件注册与分发过大

`draftpaper_cli/cli.py` 约 1215 行，`build_parser()` 注册大量子命令，`main()` 里约 70 个 `if args.command == ...` 分支。错误处理、JSON 输出、退出码策略散落在每个分支里。

风险：

- 新命令容易漏掉退出码策略。
- 分发分支重复，测试很难覆盖所有 CLI 语义。
- `verify-methods` 这类状态失败但 exit 0 的问题就是这种结构的直接后果。

建议：

- 用命令表：`CommandSpec(name, add_args, handler, success_predicate, handled_errors)`。
- 提供统一 `print_json_result()` / `print_json_error()`。
- 把 gate 命令的成功判断集中配置。

### 5.2 阶段目录与产物目录交叉

`method_plan` 阶段 manifest 位于 `method_plan/stage_manifest.json`，但输出写入 `methods/method_plan.md` 和 `methods/method_requirements.json`。`analysis_code.py` 又同时写 canonical `methods/` 和 compatibility `code/` 两套副本：

| 文件 | 行号 | 说明 |
|---|---:|---|
| `draftpaper_cli/method_plan.py` | 22-25 | `METHOD_PLAN_OUTPUTS` 指向 `methods/...` |
| `draftpaper_cli/method_plan.py` | 161-166 | 更新 `method_plan/stage_manifest.json` |
| `draftpaper_cli/method_plan.py` | 205-221 | 实际写入 `methods/`，然后更新 `method_plan` 状态 |
| `draftpaper_cli/analysis_code.py` | 878-893 | 同一生成代码写入 `methods/src` 和 `code/src` 两套 |

这不是立即 bug，但属于长期维护风险：stage ownership 与文件 ownership 分离，兼容副本增加 drift 面。

建议：明确 canonical artifacts 和 compatibility artifacts：

- `method_plan` 阶段若继续写 `methods/`，在 manifest 中标注 `owner_stage="method_plan"`。
- `code/` 兼容副本增加废弃期限或同步校验。
- 下游只读 canonical 路径，compatibility 路径只作为 CLI alias。

### 5.3 测试配置双轨

| 文件 | 行号 | 说明 |
|---|---:|---|
| `.github/workflows/tests.yml` | 18-21 | CI 安装后跑 `python -m unittest discover -s tests` |
| `pyproject.toml` | 50-52 | 配置了 `tool.pytest.ini_options` |

仓库没有声明 `pytest` 依赖，CI 也不跑 pytest。保留 pytest 配置会让本地贡献者误判测试入口。

建议：删除 pytest 配置，或把 CI 和依赖切到 pytest；二选一。

---

## 六、模板模块维护风险

学科模块已经从“普通业务代码”变成了一个模板系统：

| 子系统 | 文件/行数 | 风险 |
|---|---:|---|
| `discipline_modules/` | 65 Python · 3,599 行 | 模块、模板、fixture、manifest 混放 |
| `machine_learning/module.py` | 506 行 | 多个 connector/method template 全部内联在单文件 |
| `geography/module.py` | 256 行 | 同上 |
| `astronomy/module.py` | 231 行 | 同上 |

目前可接受，但增长后会出现三类问题：

1. 模板路径字符串与真实文件路径漂移。
2. `module.py` 变成手写 registry 大表。
3. 模板 `template.py` 的运行质量依赖零散测试。

建议把每个模板的 manifest 作为权威来源，通过加载 manifest 生成 `DataConnectorSpec` / `MethodTemplateSpec`，减少在 `module.py` 里重复写路径、fixture、genericity rules。

---

## 七、资源泄漏与小型代码质量问题

本地跑 `python -m unittest discover -s tests` 时，多处模板出现 `ResourceWarning: unclosed file`。典型模式是：

```python
rows = list(csv.DictReader(input_csv.open("r", encoding="utf-8-sig", newline="")))
```

涉及的模板包括：

- `astronomy/method_templates/event_level_transformer_input_builder/template.py`
- `astronomy/method_templates/long_term_light_curve_feature_extraction/template.py`
- `astronomy/data_connectors/remote_fits_zip_stream/template.py`
- `machine_learning/method_templates/embedding_extraction_health_diagnostics/template.py`
- `machine_learning/method_templates/embedding_similarity_retrieval/template.py`
- `machine_learning/data_connectors/vision_catalog_image/template.py`
- `geography/method_templates/monthly_remote_sensing_index_summary/template.py`
- `geography/method_templates/ndvi_cluster_statistical_diagnostics/template.py`
- `geography/method_templates/ndvi_temporal_kmeans_zoning/template.py`
- `geography/method_templates/phenology_curve_smoothing/template.py`

建议统一改为：

```python
with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))
```

---

## 八、依赖与安装面

`pyproject.toml` 把 `matplotlib`、`SciencePlots`、`numpy`、`pandas`、`seaborn` 放进 mandatory dependencies，同时又定义了 `plotting` / `plotting-full` extras。

观察：

- 未安装绘图库时，`python -m draftpaper_cli.cli --help` 可以正常运行。
- 生成代码有 stdlib PNG fallback，但 `verify_methods()` 的 figure quality gate 会要求 publication backend。
- 这导致“核心 CLI 可启动”和“方法验证可通过”的依赖边界不一致。

建议：

1. 核心依赖只保留真正 import 必需项。
2. 绘图和科学计算依赖移到 extras。
3. CLI 在 `generate-analysis-code` 或 `verify-methods` 前主动检查 publication plotting extras，给出明确错误，而不是生成 fallback 后再被 gate 判失败。

---

## 九、验证结果

| 验证项 | 结果 |
|---|---|
| `python -m compileall -q draftpaper_cli tests` | 通过 |
| `python -m draftpaper_cli.cli --help` | 通过，列出完整命令 |
| `python -m unittest discover -s tests` | 209 tests，2 failures，1 error |
| `pip wheel . --no-deps` | 通过，wheel 约 348KB |
| wheel 内容检查 | `third_party entries = 0`，`scientific_svg.py` 和 42 个 discipline `template.py` 会进入包 |
| 临时 venv `pip install -e .` | PyPI 下载 matplotlib 超时，未完成全依赖复测 |

unittest 的 2F/1E 集中在生成分析代码后的验证链路：

- `test_generate_analysis_code_writes_manifest_and_runnable_code`
- `test_generate_analysis_code_prefers_user_named_processed_table`
- `test_generated_method_artifacts_feed_result_manifest_and_results_text`

复现显示生成脚本 returncode 为 0，声明输出均存在；失败来自本地环境缺少 matplotlib/SciencePlots 等 publication plotting backend，导致 `figure_quality_report.json` 非 passed，`verify_methods()` 返回 `status=failed`。

因此这不是语法错误，也不一定代表 CI 全依赖环境失败；但它暴露了 fallback 绘图和 strict figure gate 的契约不一致。

---

## 十、汇总与建议优先级

| 优先级 | 项目 | 建议 |
|---|---|---|
| P0 | wheel 缺 `third_party/paper-fetch-skill` fallback | 决定依赖/包数据/源码树限定三选一 |
| P0 | `verify-methods` 失败仍 exit 0 | 按 `result["status"]` 返回退出码 |
| P1 | `verify_methods(shell=True)` | 明确本地执行边界，内部生成命令尽量改 argv |
| P1 | `source_mvp.path = D:\\DraftAI_agent` | 从生成项目 JSON 删除或改为中性说明 |
| P1 | `cli.py` 70 个分支 | 改命令表和统一 exit predicate |
| P2 | helper 重复 | 提取 `io_utils`、`latex_utils`、`citation_utils` |
| P2 | stage/产物目录交叉 | 标注 owner stage，减少 `methods/` 与 `code/` 双副本 |
| P2 | pytest/unittest 双轨 | 删除无用 pytest 配置或切 CI |
| P2 | 模板 ResourceWarning | 批量改 context manager |

可直接删除的代码不多。这个仓库的主要问题不是“大量死代码”，而是**发布边界不一致、CLI gate 退出码不可靠、模板资产引用方式隐式、以及阶段/兼容副本带来的漂移风险**。

---

## 十一、维护者补充判断与 v0.15.3 处理状态

本节是在 v0.15.3 修复后追加的维护者判断，用于后续版本实施时区分“已经确认的 bug”“需要产品决策的架构边界”和“暂不应机械照搬的审计建议”。

### 11.1 方法验证与结果图表生成的关系

我的判断是：**方法验证应当与结果图表生成强耦合，但二者不是同一个阶段概念**。

当前实现中，`generate-analysis-code` 的职责是根据 `results/figure_plan.json`、`results/figure_contracts.json`、方法蓝图和数据清单生成项目专属分析代码，并写入 `methods/scripts/run_analysis.py`、`methods/src/generated_pipeline.py`、`methods/method_code_manifest.json`，同时给出 `verify_command`。它本身不应被视为“方法已经验证通过”。

`verify-methods` 的职责是执行这条方法命令，并验证声明产物是否真实存在。由于当前研究结果的核心证据就是主图、表格、figure metadata 和 figure quality report，因此 `verify-methods` 在执行方法代码时也会触发结果图表生成，并检查：

- `methods/run_manifest.yaml` 是否记录执行状态；
- `results/figures/*` 等声明图表是否存在；
- `results/figure_metadata.json` 是否覆盖生成图表；
- `results/figure_quality_report.json` 是否为 `passed`；
- review task coverage 是否满足修订任务要求。

因此，更准确的表述是：

> 图表生成是方法执行的核心产物；`verify-methods` 是执行方法并验证图表、表格、metadata 和 run manifest 的 hard gate。`assess-result-validity` 和 `assess-core-evidence` 则在此基础上继续判断这些图表是否足以支撑研究结果和人工确认。

这也意味着后续优化不应把“方法验证”简化成只检查 Python 脚本 returncode。对于 Draftpaper-loop，方法是否通过必须同时看代码是否跑通、主图是否生成、图表 metadata 是否完整、结果质量是否达到 contract。

### 11.2 v0.15.3 已处理项

| 审计项 | 维护者判断 | v0.15.3 状态 |
|---|---|---|
| `verify-methods` 失败仍 exit 0 | 这是 hard gate 语义 bug，会误导 shell、CI 和 Codex 自动化 | 已修复：失败时返回非零退出码，同时保留 JSON 输出 |
| 新建项目写入开发者本机历史路径 | 这是可迁移性和公开示例污染问题，不应进入默认 `project.json` | 已修复：移除 `source_mvp.path`，改为中性 `legacy_mvp_reference` |
| README 论文生成逻辑过时 | 旧表述容易误导用户先写 Introduction/Data/Methods，再生成结果 | 已修复：README 改为 evidence-first，正文写作后置到核心图表和结果证据之后 |
| 相关测试 | 需要把审计发现固化为回归测试 | 已补充：覆盖失败 `verify-methods` 退出码和 portable project metadata |

### 11.3 仍需用户确认或后续版本实施的判断

| 审计项 | 我的判断 | 建议版本 |
|---|---|---|
| wheel 缺 `paper-fetch` vendored fallback | 不建议把 `third_party/paper-fetch-skill` 直接塞进核心 wheel。更稳的路线是保留源码 checkout 的 vendored fallback，同时提供 `paper-fetch` 可选依赖或明确安装步骤。这样能减少 wheel 体积、许可证传播和第三方更新风险。 | v0.15.4 |
| `verify_methods(shell=True)` | 不应直接删除，因为用户本地研究环境确实需要手动 shell 命令。但内部自动生成的 `verify_command` 应逐步迁移到 argv/shell-free runner；用户显式 `--command` 保留为“人工确认的本地 shell 执行”。 | v0.15.5 |
| `cli.py` 单文件分支过大 | 判断成立，但不建议一次性大拆。应先引入 `CommandSpec`，优先迁移 gate 类命令，统一 JSON 输出和退出码；普通信息命令后迁移。 | v0.15.6 |
| `methods/` 与 `code/` 双轨 | `methods/` 应作为 canonical code location，`code/` 只保留兼容 launcher/shared runtime。暂不建议删除 `code/`，但应增加同步校验和废弃路线。 | v0.15.6-v0.15.7 |
| helper 重复 | 判断成立，适合低风险重构。建议先抽 `io_utils`、`latex_utils`、`citation_utils`，并用现有测试防止行为漂移。 | v0.15.7 |
| pytest/unittest 双轨 | 当前测试文件仍是 `unittest` 风格，但本地和 Codex 开发实际使用 `pytest` 更方便。建议 CI 切到 `pytest`，测试代码保持 unittest-compatible，避免贡献者困惑。 | v0.15.7 |
| 模板 `ResourceWarning` | 判断成立，属于小型质量债。可批量改为 context manager，但应和 `template_registry` 测试一起做，避免只修表象。 | v0.15.8 |
| `loop_contract.py` 零运行时引用 | 暂不建议删除。它更像 DPL/claim/evidence 稳定 ID 规范的候选入口，后续应接入 citation audit、claim trace 或移动到 docs/spec。 | v0.15.8+ |

### 11.4 后续实施路线确认点

我建议后续继续按以下顺序推进：

1. `v0.15.4`：处理 `paper-fetch` 发布边界，优先采用 optional dependency/明确安装策略，而不是把第三方源码打入核心 wheel。
2. `v0.15.5`：加固方法执行边界，区分“用户确认 shell command”和“内部生成 argv command”，并对 run manifest 做敏感信息脱敏。
3. `v0.15.6`：引入 `CommandSpec`，先迁移 hard gate 命令，统一 exit predicate。
4. `v0.15.7`：抽取公共工具函数，统一 JSON/text/LaTeX/citation parsing。
5. `v0.15.8`：建立 `template_registry`，校验 discipline manifest、template path、fixture 和模板执行契约，同时修复 `ResourceWarning`。

以上判断如果得到确认，后续遇到修改细节疑问时，应优先读取本审计报告和本节维护者补充；如果报告仍无法回答，再向用户确认。

---

## 十二、v0.15.4-v0.15.9 实施记录

本节记录根据审计报告继续完成的结构优化，作为后续维护和复查依据。

| 版本 | 状态 | 实施内容 |
|---|---|---|
| v0.15.4 | 已完成 | 将 paper-fetch runtime 打包到 `draftpaper_cli/_vendor/paper_fetch_skill`，使普通 wheel 安装也能保留 fallback 源码；新增 `fulltext` optional extra，用于安装更重的全文解析依赖。 |
| v0.15.5 | 已完成 | `verify-methods` 支持直接读取 `methods/method_code_manifest.json` 中的 `verify_command` 和 `declared_outputs`，并把 `results/figure_contracts.json` 的主图合同纳入方法验证门。 |
| v0.15.6 | 已完成 | 新增 `io_utils`、`latex_utils`、`citation_utils`，迁移论文 writer、LaTeX assembly 和 quality gate 中高风险重复实现。 |
| v0.15.7 | 已完成 | 为公共工具补充单测，并保持 `\cite{}`、`\citep{}` 等常见 LaTeX 引用命令兼容。 |
| v0.15.8 | 已完成 | 新增 `template_registry.py` 与 `validate-template-registry` CLI，用于校验学科插件 manifest、template、fixture 和插件 ID。 |
| v0.15.9 | 已完成 | GitHub Actions 改为安装 `.[dev]` 并运行 `python -m pytest`；修复多个学科模板中的未关闭 CSV 文件句柄。 |

验证记录：

- `python -m pytest`：219 passed。
- `python -m pip wheel . --no-deps`：通过，wheel 中包含 `draftpaper_cli/_vendor/paper_fetch_skill/paper_fetch/cli.py` 和 `draftpaper_cli/_vendor/paper_fetch_skill/LICENSE`。
