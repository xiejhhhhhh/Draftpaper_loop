# Draftpaper-loop 学科感知文献发现、Paper Fetch 身份核验与误召回隔离优化方案

> 日期：2026-08-20
>
> 适用范围：Draftpaper-loop Core 的主题检索、学科路由、候选筛选、论文身份解析、全文补抓、引用候选形成、Agent 文献上下文和历史全文产物治理
>
> 案例来源：`EuclidxDESI` 天文学项目中出现生态学 paper-fetch JSON 与 orphan fulltext 的历史问题
>
> 当前基线：Draftpaper-loop v0.39.0
>
> 方案性质：框架级优化方案；本文件只描述后续实现，不直接修改代码、项目状态或真实论文文献集合

## 一、核心结论

天文学项目混入生态学文献的主要原因，不是 Draftpaper-loop 没有调用 `paper-fetch-skill`，而是上游候选发现、学科识别、身份解析和抓取后复核之间缺少完整闭环。

当前 Draftpaper-loop 已经具备并默认进入 vendored paper-fetch adapter，但它只在 Data/Methods 候选少于指定数量且缺少可读摘要时补全文本。`paper-fetch-skill` 的职责是解析 DOI、标题或 URL并抓取已知论文，不负责根据研究主题发现正确论文。如果上游已经给出生态学 DOI，paper-fetch 会正确地抓回生态学论文；扩大无条件抓取范围只会更快地产生错误全文。

因此，本方案采用以下产品原则：

1. **学科化检索负责发现候选。** 根据研究主题和学科优先选择对应 provider，天文学优先 NASA ADS，并使用 OpenAlex、Crossref 等作为补充。
2. **Core 门禁负责决定候选是否可以继续。** 学科冲突、主题锚点、身份完整性和用途角色必须在抓取前检查。
3. **paper-fetch 默认用于身份解析与可读性分诊。** 对入围 shortlist 的候选默认核验 DOI、标题、作者和年份，但不默认抓取所有全文。
4. **全文只按证据需求抓取。** 缺摘要、承担关键证据角色或准备进入正文引用的候选才进入全文抓取。
5. **抓取后必须重新评分。** 根据解析后的真实标题、摘要和全文重新执行主题、学科和用途检查；抓取成功不等于引用合格。
6. **错误结果进入 quarantine。** 身份不一致、歧义未解决、跨学科误召回或与 active snapshot 不可达的文件不得进入摘要、引用池、Agent 上下文和“已阅读”统计。
7. **产品内默认依赖 vendored adapter。** Agent 侧 `paper-fetch-skill` 保留用于单篇人工阅读、特殊 provider 和交互式补抓，不能成为 Core 可用性的唯一前提。

## 二、当前实现与案例审计

### 2.1 Paper Fetch 当前已经被调用

当前在线检索路线结束后会调用：

```python
items, _manifest = enrich_with_paper_fetch(project, items)
```

对应位置：

- `draftpaper_cli/literature_search.py::search_literature_for_project()`；
- `draftpaper_cli/paper_fetch_adapter.py::enrich_with_paper_fetch()`；
- wheel 内 `_vendor/paper_fetch_skill` 作为没有外部 `paper-fetch` 命令时的运行时 fallback。

当前 adapter 的目标选择逻辑是：

- 只考虑 `data` 和 `methods` 上下文；
- 当某一上下文已有至少 5 篇可读候选时，不再抓取；
- 只抓取缺少 `abstract` 和 `pdf_text_excerpt` 的候选；
- 使用 DOI、URL 或标题作为抓取目标；
- 使用 `--no-download` 和无图片资产模式保存结构化 JSON/Markdown 结果。

因此，当前并非“完全没有 paper-fetch”，而是“paper-fetch 只承担有限补全文本职责，尚未形成候选身份核验和抓取后复核门禁”。

### 2.2 当前学科门禁不对称

`draftpaper_cli/literature_relevance.py` 当前逻辑大致为：

```text
学科相交 -> 1.0
候选或项目被识别为 general -> 1.0
其他不相交 -> 0.55
医学/生命科学项目遇到天文学/计算机候选 -> 0.0
```

这带来两个问题：

1. 生命科学项目遇到天文学候选可能被拒绝，但天文学项目遇到生命科学候选没有对称规则；
2. `general` 被解释为“通用且匹配”，实际上它通常只表示“学科无法识别”。

`general` 不应获得满分学科匹配。更合理的语义是 `discipline_unknown`，只能进入补充解析或人工复核，不能直接进入 active reference snapshot。

### 2.3 学科词典缺少生态学覆盖

`draftpaper_cli/literature_language.py` 当前生命科学标记主要包含：

- biology；
- genomic / transcriptomic；
- protein；
- 生物 / 基因 / 蛋白。

但没有系统覆盖：

- ecology / ecological；
- biodiversity；
- ecosystem；
- habitat；
- conservation；
- species richness；
- food web；
- vegetation；
- 生态、生态学、生物多样性、生态系统、栖息地、物种、保护生物学。

因此，不含 `biology` 字样的生态学论文可能被分类为 `general`，继而获得错误的满分学科匹配。

### 2.4 主题相关性阈值过宽

当前主题门禁在 `topic_relevance_score < 0.25` 时拒绝候选。对于以下跨学科共享词，该阈值容易误放行：

- population；
- classification；
- catalog / catalogue；
- diversity；
- source；
- distribution；
- survey；
- network；
- morphology；
- embedding；
- detection。

这些词本身不能证明论文属于目标学科。主题评分必须区分：

- 项目专有锚点，如 `Euclid`、`DESI`、`galaxy`、`redshift`；
- 学科锚点，如 `astronomy`、`astrophysics`；
- 通用方法词，如 `classification`、`model`；
- 近邻误召回词，如生态学中的 `population`、`diversity`、`catalogue`。

不能简单把全体 token overlap 当作等权主题证据。

### 2.5 EuclidxDESI 中的生态学文件属于历史 orphan

当前案例中，生态学 JSON 具有 paper-fetch 输出结构，并记录：

```text
resolve:doi
resolve:doi_selected
metadata:crossref_ok
fallback:metadata_only
```

这说明它们是已知 DOI/身份的抓取结果，而不是 paper-fetch 自行完成的主题发现。当前 `paper_fetch_manifest.json` 的 `attempted_count` 为 0，active 文献集合也不包含这些生态学标题；这些文件属于历史抓取产物，未被及时与 active snapshot 隔离。

这类文件必须通过以下可达性判断治理：

```text
active literature snapshot
  -> canonical work_id
  -> identity resolution receipt
  -> fetch receipt
  -> normalized document / evidence passages
```

无法从 active snapshot 到达的历史全文、缓存、摘要和 parse 结果应进入 quarantine 或 archive，不得仅因文件位于 `references/fulltext/` 就进入 Agent 上下文。

## 三、优化目标与非目标

### 3.1 必须实现的目标

1. 主题发现、身份解析和全文抓取成为三个独立但可追溯的阶段。
2. paper-fetch 默认参与 shortlist 身份核验，但不无条件抓取所有候选全文。
3. 学科冲突规则对称，并支持显式的跨学科用途，而不是单向硬编码。
4. `general` 改为“未知状态”，不得自动视为学科匹配。
5. 生态学、环境科学、农业、公共卫生等容易与现有领域混淆的学科获得独立标记。
6. 主题锚点、学科锚点和通用方法词分层计分。
7. 标题、作者、年份、DOI 解析发生歧义时，不得直接抓全文或进入 active snapshot。
8. 抓取完成后，必须基于真实元数据和可读正文重新执行门禁。
9. 只有 active snapshot 可达的全文产物才能进入文献摘要、引用核查、Agent context 和写作阶段。
10. provider 离线、paper-fetch 失败、无全文或限流时，不得破坏已有有效 snapshot。
11. HTML 中能够解释每篇论文来自哪个 provider、为何入选、是否经过身份核验、是否抓取全文以及是否被隔离。
12. 所有规则适用于天文学、医学、生命科学、社会科学、地理遥感、计算机科学等学科，不写入单项目硬编码。

### 3.2 本方案不做的事情

- 不把 paper-fetch 变成主题搜索引擎；
- 不对所有 provider 返回结果无条件下载全文；
- 不因为论文跨学科就一律拒绝；
- 不把抓取成功、引用次数、期刊分区或 provider 排名当作科学正确性证明；
- 不自动把抓取到的论文加入正文引用；
- 不要求用户额外安装 Agent skill 才能完成 Core 文献流程；
- 不在默认路线下载论文图片、补充材料或大体积资产；
- 不直接清除历史 orphan 文件，必须先生成 preview、hash 和 quarantine receipt；
- 不修改 EuclidxDESI 的真实项目状态作为框架测试手段。

## 四、目标流程

```text
研究 idea / 研究蓝图
  -> Query Contract
  -> 学科化 Provider Router
  -> Raw Candidates
  -> 抓取前主题与学科门禁
  -> Shortlist
  -> Paper Identity Resolution（默认）
  -> 身份一致性门禁
  -> Full-text Triage
  -> 按需 Paper Fetch
  -> 抓取后主题、学科与用途重评
  -> Active / Review Required / Quarantine
  -> Hash-bound Literature Snapshot
  -> BibTeX / Citation Evidence / Summary / Bilingual HTML / Agent Context
```

### 4.1 三阶段职责分离

| 阶段 | 负责内容 | 不负责内容 |
|---|---|---|
| Discovery | 主题检索、provider 路由、候选召回 | 不证明论文身份和正文相关性 |
| Identity Resolution | DOI、标题、作者、年份、落地页的一致性核验 | 不证明论文适合引用 |
| Evidence Fetch | 摘要、Markdown、PDF 或结构化全文获取 | 不自动授予 active/引用资格 |

### 4.2 默认执行策略

建议新增项目级策略：

```json
{
  "schema_version": "dpl.literature_fetch_policy.v1",
  "mode": "resolve_then_fetch_on_demand",
  "identity_resolution": "default_for_shortlist",
  "fulltext_fetch": "evidence_on_demand",
  "asset_profile": "none",
  "remote_document_classes": ["published-public"],
  "max_identity_candidates": 60,
  "max_fulltext_candidates": 12,
  "ambiguous_resolution": "review_required",
  "post_fetch_relevance_gate": true
}
```

默认行为：

- metadata/identity resolution：默认开启；
- full-text fetch：按需开启；
- 图片和补充材料：默认关闭；
- 未发表、敏感或受限文档：默认禁止远程上传；
- ambiguous：暂停该候选，不阻塞其他候选；
- provider failure：记录 degraded，不删除旧 snapshot。

## 五、学科本体与对称冲突矩阵

### 5.1 从关键词列表升级为学科本体

建议新增 `LiteratureDisciplineOntology v1`，至少包含：

- 一级学科；
- 二级学科；
- 中英文标记词；
- 高特异性标记；
- 通用词；
- 容易混淆的近邻学科；
- 允许的跨学科关系；
- 冲突判定证据。

示例：

```json
{
  "discipline_id": "ecology",
  "parent": "life_science",
  "markers": [
    "ecology",
    "ecological",
    "biodiversity",
    "ecosystem",
    "habitat",
    "conservation",
    "species richness",
    "food web",
    "生态",
    "生态学",
    "生物多样性",
    "生态系统",
    "栖息地",
    "物种"
  ],
  "high_specificity_markers": [
    "Acta Ecologica Sinica",
    "ecosystem multifunctionality",
    "conservation planning"
  ]
}
```

### 5.2 `general` 状态修正

当前 `general` 必须拆分为：

- `discipline_unknown`：信息不足，不能自动通过；
- `genuinely_multidisciplinary`：有多个学科证据；
- `general_methodology`：通用方法论文，但必须有目标用途合同；
- `general_background`：通用背景，不承担学科事实或核心论断。

只有后面三类在证据充分时才能保留；`discipline_unknown` 必须进入解析补充或人工复核。

### 5.3 对称冲突规则

冲突规则不能写成单向条件。建议按以下方式计算：

```text
project_primary_disciplines
candidate_primary_disciplines
explicit_cross_discipline_role
target_anchor_coverage
conflicting_high_specificity_markers
```

判定原则：

1. 项目和候选有学科交集：正常评分；
2. 无交集且候选有明显冲突学科标记：默认拒绝；
3. 无交集但声明了 `method_transfer`、`comparison` 或 `general_methodology`：进入 review；
4. 候选学科未知：不能获得 1.0，进入 resolve/fetch 后重评；
5. 同一 pair 的冲突规则必须满足对称属性，除非有显式、可审计的方向性用途合同。

例如：

```text
astronomy -> ecology：冲突
ecology -> astronomy：冲突
astronomy + ML method-transfer -> computer science：允许但需用途证据
medicine + statistical calibration -> statistics：允许但需方法角色证据
```

## 六、主题相关性门禁重构

### 6.1 分层词汇权重

建议把检索词分为四层：

| 词汇层 | 示例 | 作用 |
|---|---|---|
| 实体/项目锚点 | Euclid、DESI、WXT、DINOv2、数字乡村 | 高权重，至少命中一项 |
| 学科锚点 | galaxy、redshift、astrophysics、rural governance | 高权重，确认领域 |
| 数据/方法锚点 | VIS cutout、spectroscopy、grouped split | 中权重，确认用途 |
| 通用词 | population、classification、catalog、model | 低权重，不能单独通过 |

`query_contract` 应显式保存这四类词，而不是只保存 `must_preserve_terms` 和 `optional_terms`。

### 6.2 三态门禁

不建议仅把 `0.25` 调高为另一个固定值。应先用标注 fixture 校准，再采用三态输出：

```text
accepted
review_required
rejected
```

建议初始边界：

- `< 0.35`：`rejected`；
- `0.35–0.55`：`review_required`；
- `>= 0.55`：只有在学科和身份门禁同时通过时才 `accepted`。

任何仅由通用词命中的候选，最高只能进入 `review_required`。

### 6.3 负向证据

`negative_terms` 不应只由用户填写，也应由学科冲突矩阵生成。天文学项目可以自动生成生态学高特异性负向证据，但不能仅凭单个 `population` 或 `survey` 拒绝论文。

负向证据至少区分：

- hard conflict：明确属于冲突学科；
- weak conflict：存在近邻学科词，但仍可能是方法迁移；
- project exclusion：用户或研究蓝图明确排除；
- source contamination：来自错误本地目录或旧项目缓存。

## 七、Paper Fetch 默认身份解析

### 7.1 Default Resolve，不 Default Full Fetch

shortlist 形成后，对在线候选默认执行身份解析：

1. 有 DOI：使用标准化 DOI 解析；
2. 无 DOI、有标题：使用标题 + 第一作者 + 年份解析；
3. 有 URL：先识别 DOI/落地页 canonical identity；
4. 多候选或低置信：标记 `ambiguous`，禁止自动抓全文；
5. 解析成功后对比原始候选和解析结果。

身份一致性建议至少验证：

- DOI 精确一致；
- 标题规范化相似度；
- 第一作者或作者集合重叠；
- 年份一致或在允许的预印本/正式发表偏差范围内；
- 期刊、arXiv、PubMed、ADS 等版本关系；
- 解析结果学科是否与原始候选发生显著变化。

### 7.2 身份解析状态

建议新增：

```text
unresolved
resolved_exact
resolved_probable
ambiguous
mismatch
no_access
provider_degraded
```

只有 `resolved_exact` 可以默认进入全文分诊；`resolved_probable` 必须满足更严格的抓取后复核或人工确认。

### 7.3 解析收据

新增 `PaperIdentityResolutionReceipt v1`：

```json
{
  "schema_version": "dpl.paper_identity_resolution.v1",
  "candidate_id": "candidate:...",
  "input": {
    "doi": "...",
    "title": "...",
    "authors": [],
    "year": "..."
  },
  "resolved": {
    "work_id": "doi:...",
    "doi": "...",
    "title": "...",
    "authors": [],
    "year": "...",
    "provider": "..."
  },
  "status": "resolved_exact",
  "checks": {
    "doi_match": true,
    "title_similarity": 0.98,
    "author_overlap": 1.0,
    "year_delta": 0
  },
  "input_snapshot_hash": "sha256:..."
}
```

## 八、按需全文抓取策略

### 8.1 需要抓取的候选

全文抓取仅适用于：

- 缺少 abstract，无法完成主题或学科判断；
- 承担 `data_provenance`、`method_definition`、`baseline`、`evaluation_standard` 等关键角色；
- 准备进入正文引用，但只有元数据级证据；
- 主题/学科处于 `review_required`，全文能够帮助消歧；
- 用户明确要求阅读、总结或核验的论文。

### 8.2 不需要抓取的候选

- 抓取前已经 `rejected`；
- 身份为 `ambiguous` 或 `mismatch`；
- 已有经过 hash 核验的本地全文；
- active snapshot 已有相同 work_id 的可用解析结果；
- 仅用于候选数量扩充、没有明确证据角色；
- 文档敏感、受限或不允许远程上传。

### 8.3 批量策略

对于三个及以上候选，Core 应使用 vendored paper-fetch 批量路线，而不是让 Agent 逐篇执行：

- 先 batch resolve/check；
- 按 fetch decision 排序；
- 限制并发和总数量；
- 优先缓存；
- provider/browser runtime 失败最多按策略重试；
- 每篇失败独立记录，不阻断整批；
- 不因单次失败删除旧证据。

Agent 直接调用 `paper-fetch-skill` 时仍须遵守该 skill 的保存位置、图片下载和批量 CLI 选择检查点。Draftpaper-loop 内置路线通过项目级 `literature_fetch_policy.json` 预先声明保存位置、无图片和公开文献边界，避免用户在每篇论文前重复回答相同问题。

## 九、抓取后重评与引用资格

### 9.1 抓取后不是直接覆盖原记录

paper-fetch 返回内容先写入候选 evidence bundle，不直接覆盖 active canonical record。重评通过后，才由合并事务把经过核验的字段投影回 registry。

### 9.2 重评输入

抓取后重新评估：

- resolved title；
- resolved authors/year/DOI；
- abstract；
- journal/venue；
- Markdown/fulltext passages；
- figure/table caption（若已解析）；
- provider source trail；
- 项目 query contract；
- 预期 citation role。

### 9.3 重评结果

新增 `PostFetchRelevanceAssessment v1`：

```text
accepted_active
accepted_context_only
review_required
rejected_topic_mismatch
rejected_discipline_mismatch
rejected_identity_mismatch
rejected_insufficient_evidence
```

只有 `accepted_active` 和 `accepted_context_only` 可以进入 active literature snapshot。其中：

- `accepted_active` 可以承担其声明的证据角色；
- `accepted_context_only` 只能作为背景或方法迁移语境，不得支撑核心科学事实；
- 其他状态不得进入自动写作上下文。

## 十、Quarantine 与 Active Snapshot 可达性

### 10.1 隔离对象

以下对象进入 quarantine：

- 身份 mismatch；
- 解析歧义未解决；
- 抓取后学科冲突；
- 抓取后主题不相关；
- 与 active work_id 不可达的历史 fulltext；
- 另一项目遗留的 PDF、JSON、Markdown、parse cache；
- 重复 DOI 的过期版本；
- provider 输出损坏或 hash 不一致。

### 10.2 隔离规则

- 先 preview，后 apply；
- 文件移动前后记录 SHA-256；
- 生成 quarantine receipt；
- 支持 hash 校验后的 rollback；
- quarantine 内容不进入 Agent context；
- HTML 可以显示数量和原因，但不能把其内容并入 active 摘要；
- 重复运行必须幂等。

### 10.3 统计口径

以下统计只能从 active snapshot 和绑定 manifest 计算：

- 文献总数；
- 已解析文献数；
- 已抓取全文数；
- 引用候选数；
- Agent 可读文献数；
- 各学科/provider 数量。

禁止直接按 `references/fulltext/` 文件数推断“已阅读文献数”。

## 十一、Provider 路由优化

### 11.1 学科优先级

建议 provider router 读取学科配置：

| 学科 | 首选 | 补充 | 说明 |
|---|---|---|---|
| 天文学 | NASA ADS | OpenAlex、Crossref、arXiv | ADS 无凭证时明确 degraded |
| 医学 | PubMed、Europe PMC | OpenAlex、Crossref | 医学标识和文献类型优先 |
| 生命科学 | Europe PMC、OpenAlex | Crossref | 区分生态、组学、分子生物学 |
| 计算机科学 | DBLP、arXiv | OpenAlex、Crossref | 会议、预印本和正式版本关联 |
| 社会科学 | OpenAlex、Crossref | 本地/Zotero | 保留中文主题锚点与本地来源 |
| 地理遥感 | OpenAlex、Crossref | 学科插件来源 | 避免 satellite 一词误导到天文学 |

### 11.2 Provider 结果不能自动通过

provider 权威性只说明元数据来源，不说明主题正确。即使来自 NASA ADS、PubMed 或 DBLP，仍须经过主题、学科和身份门禁。

### 11.3 Provider 失败

- 首选 provider 无凭证时使用补充 provider；
- 报告 degraded 和缺失凭证，不伪装为完整检索；
- provider 全部失败时保留已有 snapshot；
- 不用无关 provider 的结果填满固定数量；
- 文献不足应显示 coverage gap，而不是降低门禁补齐数量。

## 十二、用户体验与配置

### 12.1 默认无需安装 Agent Skill

默认 wheel 应继续携带 vendored paper-fetch fallback。用户无需单独安装 `paper-fetch-skill` 才能完成：

- DOI/标题身份解析；
- 可读性分诊；
- 按需全文抓取；
- 缓存与 manifest；
- 抓取后重评。

### 12.2 Agent Skill 的适用位置

Agent 侧 `paper-fetch-skill` 适合：

- 用户临时指定一篇论文；
- 需要特殊 provider/browser runtime；
- 需要人工选择保存路径和图片资产；
- 需要阅读、翻译、比较或批判某几篇论文；
- Core 批量路线失败后的人工补抓。

它不应承担：

- 生成研究主题候选；
- 自动决定论文是否相关；
- 绕过 Core snapshot 和 quarantine；
- 直接把抓取内容注入正文。

### 12.3 可选模式

建议用户可设置：

```text
off
resolve_only
resolve_then_fetch_on_demand（默认）
fulltext_eager（高级、非默认）
local_only
```

`fulltext_eager` 必须显示网络、时间、配额、版权、隐私和磁盘成本，不作为普通用户默认值。

## 十三、输出文件与可审计合同

建议新增：

```text
references/
├── literature_fetch_policy.json
├── discipline_ontology_snapshot.json
├── discipline_conflict_matrix.json
├── prefetch_relevance_report.json
├── paper_identity_resolutions.jsonl
├── paper_identity_resolution_summary.json
├── fulltext_fetch_decisions.json
├── paper_fetch_manifest.json
├── postfetch_relevance_report.json
├── unresolved_paper_identities.json
├── quarantined_literature_candidates.json
├── literature_integrity_report.json
└── literature_output_manifest.json
```

建议新增 schema：

- `dpl.literature_fetch_policy.v1`；
- `dpl.literature_discipline_ontology.v1`；
- `dpl.discipline_conflict_matrix.v1`；
- `dpl.prefetch_relevance_assessment.v1`；
- `dpl.paper_identity_resolution.v1`；
- `dpl.fulltext_fetch_decision.v1`；
- `dpl.postfetch_relevance_assessment.v1`；
- `dpl.literature_quarantine_record.v1`。

所有输出必须绑定：

- query contract hash；
- candidate set hash；
- active literature snapshot hash；
- provider/runtime version；
- paper-fetch runtime source；
- input/output SHA-256；
- generated_at；
- policy version。

## 十四、双语 HTML 与人工核查

`references/literature_summaries/index.html` 和详情页应新增以下字段，并保持中文/英文视图数值完全一致：

- Discovery provider；
- Discovery query；
- 原始候选学科；
- 抓取前主题分数和状态；
- 身份解析状态；
- DOI/title/author/year 一致性；
- Full-text decision；
- Paper-fetch provider/runtime；
- 抓取后主题分数和状态；
- Citation eligibility；
- Active / review / quarantine；
- 隔离原因和 recovery route；
- Snapshot hash。

首屏摘要应说明：

- 本轮检索候选数；
- 抓取前拒绝数；
- 完成身份解析数；
- ambiguous/mismatch 数；
- 按需抓取全文数；
- 抓取后拒绝数；
- active 文献数；
- quarantine/orphan 数；
- provider degraded 状态；
- 是否需要用户复核。

用户应能仅查看该 HTML 就判断本轮是否检索到了正确学科的文献，而不必翻查 JSON 或终端日志。

## 十五、CLI 设计

优先扩展现有命令，避免无必要地增加大量入口：

```powershell
draftpaper search-literature `
  --project <project> `
  --fetch-policy resolve_then_fetch_on_demand

draftpaper audit-literature-integrity --project <project>

draftpaper rebuild-literature-index --project <project>
```

必要时新增：

```powershell
draftpaper resolve-literature-identities `
  --project <project> `
  --preview

draftpaper fetch-literature-evidence `
  --project <project> `
  --decision-hash <hash> `
  --apply

draftpaper review-literature-quarantine `
  --project <project>

draftpaper calibrate-literature-gates `
  --fixture-set <path>
```

命令边界：

- `search-literature` 可以联网并写入候选与解析收据；
- 身份解析失败不阻塞其他候选；
- 全文抓取必须有 fetch decision packet；
- 敏感文档或图片资产需要显式授权；
- quarantine apply 必须 hash-bound；
- 所有命令写入命令风险矩阵和 CLI reference。

## 十六、建议文件改动范围

### 16.1 现有模块

- `draftpaper_cli/literature_language.py`
  - 扩展生态学、环境科学、农业、公共卫生等学科标记；
  - 将 `general` 改为可解释的未知/通用状态。
- `draftpaper_cli/literature_relevance.py`
  - 实现对称冲突矩阵；
  - 分层主题锚点；
  - 三态门禁和抓取后重评。
- `draftpaper_cli/literature_query_contract.py`
  - 增加实体、学科、方法、通用和负向词层级。
- `draftpaper_cli/literature_providers.py`
  - 学科优先 provider 路由；
  - provider degraded 和 fallback 合同。
- `draftpaper_cli/literature_search.py`
  - 重排 discovery、prefetch gate、identity resolution、fetch triage 和 post-fetch gate。
- `draftpaper_cli/paper_fetch_adapter.py`
  - 从“缺摘要补抓”升级为 resolve/check + evidence-on-demand；
  - 批量身份解析、缓存、版本和 provider 状态；
  - 不让抓取结果直接覆盖 active canonical record。
- `draftpaper_cli/literature_integrity.py`
  - 校验身份、fetch receipt、post-fetch assessment 和 active reachability。
- `draftpaper_cli/references.py`
  - 只投影通过完整门禁的 active records。
- `draftpaper_cli/literature_html.py`
  - 增加双语身份、抓取、重评和 quarantine 展示。
- `draftpaper_cli/cli.py`
- `draftpaper_cli/command_registry.py`
- `docs/command_risk_matrix.md`
- `docs/cli_reference.md`
- `README.md`
- `README.zh-CN.md`

### 16.2 建议新增模块

- `draftpaper_cli/literature_discipline_policy.py`
- `draftpaper_cli/paper_identity_resolution.py`
- `draftpaper_cli/literature_fetch_policy.py`
- `draftpaper_cli/postfetch_relevance.py`
- `draftpaper_cli/literature_quarantine.py`

模块数量可在实现时合并，但职责边界不能重新混在一个函数中。

## 十七、测试与质量门禁

### 17.1 必须新增的测试

1. 天文学项目检索到生态学候选时，抓取前拒绝或进入 review，不进入 active。
2. 生态学项目检索到天文学候选时得到对称结果。
3. `general/unknown` 不再得到学科满分。
4. `population/classification/catalog/diversity` 单独命中不能通过。
5. `Euclid + galaxy + redshift` 等高特异性锚点能够通过。
6. 合法跨学科方法论文可通过 `method_transfer` 进入 review/active-context-only。
7. DOI 精确一致时身份解析通过。
8. 标题相似但作者或年份不一致时进入 ambiguous/mismatch。
9. ambiguous 候选不会触发全文抓取。
10. 抓取后发现生态学正文时进入 quarantine。
11. 抓取后发现正确天文学正文时进入 active。
12. paper-fetch 无运行时、无访问、限流或超时时保留旧 snapshot。
13. 三篇以上候选使用批量路线，不逐篇生成重复用户确认。
14. 默认不下载图片和补充材料。
15. 本地已有全文时不重复联网抓取。
16. orphan fulltext 不进入摘要、Agent context 或引用核查。
17. quarantine preview/apply/rollback 具有 hash 验证和幂等性。
18. 中英文 HTML 的集合、状态、分数和 hash 完全一致。
19. wheel 中包含 vendored paper-fetch runtime、schema 和许可证。
20. 五类学科 fixture 验证门禁不含天文学项目硬编码。

### 17.2 对抗性 fixture

至少建立以下近邻误召回对：

| 目标学科 | 正例 | 困难负例 |
|---|---|---|
| 天文学 | galaxy population classification | ecological population classification |
| 天文学 | source catalogue from survey | biodiversity catalogue from field survey |
| 医学 | patient survival model | stellar survival/evolution model |
| 地理遥感 | satellite land-cover imagery | astronomical satellite imaging |
| 社会科学 | rural digital governance | generic computer network governance |
| 机器学习 | representation-learning benchmark | 非目标学科中仅出现 classification/model 的论文 |

### 17.3 量化验收

在人工标注 fixture 上至少满足：

- 困难负例进入 active 的比例为 0；
- 正例召回率不低于 95%；
- 所有 ambiguous identity 均不触发自动全文抓取；
- 所有 active 全文均能追溯到 active work_id 和 snapshot；
- 所有 quarantine 文件均有原因、hash 和 rollback receipt；
- 默认 full-text 请求数不超过 evidence-on-demand decision 数；
- provider failure 不造成已有文献、评分或摘要丢失；
- 双语 HTML parity 为 100%。

## 十八、分阶段实施路线

### M0：紧急学科门禁修复

目标：立即阻止天文学/生态学等明显跨学科误召回。

实施：

- 扩展生态学和相关学科标记；
- 修正 `general` 语义；
- 实现对称冲突判断；
- 将低相关性改为 accepted/review/rejected 三态；
- 增加天文学—生态学对抗测试。

验收：

- 生态学困难负例不能进入天文学 active snapshot；
- 合法天文学正例不受影响；
- 不改变 paper-fetch 的抓取数量。

### M1：默认身份解析

目标：shortlist 中的在线候选都有可审计身份状态。

实施：

- 新增 fetch policy；
- 对 shortlist 默认执行 DOI/title/author/year resolve；
- ambiguous/mismatch 阻断全文抓取；
- 生成 identity receipt 和双语摘要。

验收：

- 所有 online active candidates 有身份收据；
- 解析失败不破坏旧 snapshot；
- 批量路线和缓存通过测试。

### M2：按需全文与抓取后重评

目标：全文只服务于证据需求，并能发现上游漏网误召回。

实施：

- fetch decision packet；
- evidence-on-demand 抓取；
- post-fetch topic/discipline/role assessment；
- active-context-only 与核心证据资格区分。

验收：

- 抓取成功但不相关的论文不会进入 active；
- 正确论文可形成 evidence passages；
- 默认无图片、无补充材料下载。

### M3：Quarantine、HTML 与历史迁移

目标：彻底隔离错误历史全文并让用户可见。

实施：

- orphan/mismatch quarantine preview/apply/rollback；
- HTML 增加 identity/fetch/post-fetch/quarantine 信息；
- EuclidxDESI 只读真实结构回归；
- 历史项目 migration。

验收：

- EuclidxDESI 历史生态学 JSON 不进入 active context；
- 真实项目不被测试直接写入；
- 重复迁移和 rebuild 幂等。

### M4：全学科校准与发布

目标：从单案例修复升级为全学科质量发布。

实施：

- 五类以上学科 fixture；
- precision/recall 和 provider degradation benchmark；
- wheel、schema、CLI、风险矩阵和文档发布验证；
- README 解释 paper-fetch 的职责边界和默认模式。

验收：

- 全量测试通过；
- wheel 独立安装通过；
- vendored paper-fetch、许可证和 provenance 可核验；
- 所有 Definition of Done 均有自动测试或真实结构证据。

版本号建议在实施完成后根据实际兼容性统一确定，不要求每个内部里程碑单独发 tag。

## 十九、主要风险与控制

### 19.1 门禁过严导致召回下降

风险：合法跨学科方法论文被拒绝。

控制：

- 使用 `method_transfer`、`comparison`、`general_methodology` 等显式角色；
- 中间区间进入 review，而不是直接拒绝；
- 用困难正例校准召回率。

### 19.2 默认身份解析增加网络延迟

风险：候选较多时请求数上升。

控制：

- 只解析 shortlist；
- 批量检查；
- 优先 DOI 和缓存；
- 设置 max candidates；
- provider degraded 时不中断整个检索。

### 19.3 全文抓取引入配额、版权和隐私问题

风险：浏览器 provider、付费墙、未公开稿件或敏感 PDF。

控制：

- 默认只处理 `published-public`；
- 默认 `asset_profile=none`；
- 未发表/敏感文档禁止远程上传；
- 特殊 provider 遵循 runtime 与凭证检查；
- 公开记录抓取状态，不伪报全文可用。

### 19.4 第三方 runtime 漂移

风险：paper-fetch 上游更新改变解析行为。

控制：

- 固定 vendored commit/version；
- 保存 runtime source 和版本；
- wheel 验证许可证与 provenance；
- 使用冻结 DOI/title/author/year fixture；
- 升级必须通过 shadow comparison。

### 19.5 历史 orphan 被误当作当前证据

风险：旧 fulltext 文件继续进入 Agent 上下文。

控制：

- 所有下游消费者只读取 active snapshot + output manifest；
- 文件存在不等于 active；
- integrity audit 在写作前检查可达性；
- orphan 只可 quarantine/archive，不可自动重新绑定。

## 二十、最终 Definition of Done

只有同时满足以下条件，才能认为该问题已从 Draftpaper-loop 框架层解决：

1. 文献发现、身份解析和全文抓取具有独立数据合同和收据；
2. paper-fetch 对 shortlist 默认执行身份解析，但全文默认按需抓取；
3. Agent 没有安装外部 skill 时，wheel 内 vendored adapter 仍可运行；
4. `general` 不再自动获得满分学科匹配；
5. 学科冲突矩阵对称，并支持显式跨学科用途；
6. 生态学、环境科学等高风险近邻学科获得完整中英文标记；
7. 通用词不能单独使候选通过主题门禁；
8. ambiguous/mismatch identity 不触发自动全文抓取；
9. 抓取后的真实元数据和正文必须重新评分；
10. 抓取成功但主题或学科错误的论文进入 quarantine；
11. 只有 active snapshot 可达的全文进入摘要、引用池和 Agent context；
12. provider/paper-fetch 失败不删除旧 snapshot 或有效评分；
13. HTML 能清楚展示 discovery、identity、fetch、post-fetch 和 quarantine 全流程；
14. EuclidxDESI 的历史生态学 JSON 被真实结构回归识别为 inactive orphan；
15. 至少五类学科 fixture 通过，包括天文学—生态学困难负例；
16. 正例召回率、困难负例 active 率和双语 parity 达到量化验收；
17. 全量测试、Ruff、schema、CLI reference、风险矩阵、wheel 和独立安装验证全部通过。

## 二十一、执行优先级

建议严格按以下顺序实施：

1. 先修正学科本体、`general` 语义和对称冲突矩阵；
2. 再重构主题锚点与三态门禁；
3. 然后把 paper-fetch 从“缺摘要补抓”升级为默认 identity resolution；
4. 接入按需全文和 post-fetch 重评；
5. 最后补齐 quarantine、HTML、历史迁移和全学科质量发布。

顺序不能倒置。否则在上游门禁仍不可靠时扩大全文抓取，只会增加错误下载、网络成本和用户困惑。
