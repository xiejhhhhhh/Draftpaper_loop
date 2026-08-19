# 学科感知文献检索、身份核验与全文抓取

Draftpaper-loop 将文献处理分成三个独立阶段：

1. 学科化 provider 负责发现候选；
2. Core 核验 DOI、标题、作者和年份身份；
3. vendored paper-fetch adapter 只按证据需求抓取全文。

抓取成功不等于可以引用。抓取后的真实元数据与正文必须重新通过主题、学科和用途门禁，只有 `accepted_active` 与 `accepted_context_only` 会进入活动文献快照。

## 默认流程

```text
Query Contract v3
  -> 学科化 provider 路由
  -> 抓取前主题/学科门禁
  -> shortlist 身份解析
  -> 按需全文决策
  -> paper-fetch 批量或单篇抓取
  -> 抓取后重新评分
  -> active / review_required / quarantine
  -> hash-bound literature snapshot
```

`general` 不再表示“通用且完全匹配”。信息不足时使用 `discipline_unknown`，它只能进入补充解析或复核。

## Fetch Policy

`search-literature` 默认读取 `references/literature_fetch_policy.json`，也可以在本次搜索中覆盖：

```powershell
draftpaper search-literature `
  --project <project> `
  --fetch-policy resolve_then_fetch_on_demand
```

| 模式 | 行为 |
|---|---|
| `off` | 关闭身份/全文增强，保留基础检索门禁 |
| `resolve_only` | 解析候选身份，不抓全文 |
| `resolve_then_fetch_on_demand` | 默认；先解析身份，再按证据需求抓取 |
| `fulltext_eager` | 高级模式；对合格候选尽量抓全文，成本较高 |
| `local_only` | 只使用本地身份和文档证据，不联网解析或抓取 |

Core 自动抓取固定使用 `asset_profile=none`，不下载图片和补充材料。三篇及以上目标使用批量命令；稳定身份收据按输入哈希复用，全文按 work ID 与文件哈希复用。

## 状态与引用资格

| 状态 | 含义 | 自动写作/引用 |
|---|---|---|
| `accepted_active` | 主题、学科、身份和证据通过 | 可按声明用途进入引用候选 |
| `accepted_context_only` | 用户保留或跨学科方法语境 | 只能作为背景/方法迁移语境 |
| `review_required` | 边界相关、身份不完整或 provider 降级 | 不进入自动写作上下文 |
| `rejected_topic_mismatch` | 真实内容与主题不符 | 禁止 |
| `rejected_discipline_mismatch` | 真实内容与目标学科冲突 | 禁止 |
| `rejected_identity_mismatch` | DOI/标题/作者/年份不一致 | 禁止 |
| `rejected_insufficient_evidence` | 声明需要全文但没有可用证据 | 禁止 |

显式 `method_transfer`、`comparison`、`general_methodology` 和 `statistical_method` 可以保留跨学科方法文献，但默认进入复核或 `context_only`，不会绕过科学门禁。

## 主要产物

```text
references/
├── query_contract.json
├── literature_fetch_policy.json
├── discipline_ontology_snapshot.json
├── discipline_conflict_matrix.json
├── prefetch_relevance_report.json
├── paper_identity_resolutions.jsonl
├── paper_identity_resolution_summary.json
├── fulltext_fetch_decisions.json
├── paper_fetch_manifest.json
├── postfetch_relevance_report.json
├── quarantined_literature_candidates.json
├── literature_snapshot.json
└── literature_summaries/index.html
```

双语 HTML 的 active 数量、身份状态、分数、抓取决策和 snapshot hash 来自同一数据集合。文件位于 `references/fulltext/` 并不代表它属于 active evidence。

## 完整性与历史 Orphan

先运行只读审计：

```powershell
draftpaper audit-literature-integrity --project <project>
```

历史 orphan 隔离默认只生成 preview：

```powershell
draftpaper quarantine-orphan-literature --project <project>
```

检查 preview 后，使用其精确 packet hash 执行：

```powershell
draftpaper quarantine-orphan-literature `
  --project <project> `
  --apply `
  --packet-hash <sha256:...>
```

回滚会重新核验隔离文件哈希，禁止覆盖已存在的目标文件：

```powershell
draftpaper rollback-orphan-literature --project <project>
```

provider、paper-fetch 或网络失败时，系统记录 degraded/review 状态并保留已有活动快照；不会用无关文献填满固定数量，也不会因一次失败删除已有评分或摘要。

## Core 与 Agent Skill 的边界

Core wheel 自带固定版本、可核验许可证和 upstream commit 的 vendored paper-fetch adapter，因此普通文献流程不依赖用户安装 Agent skill。外部 `paper-fetch-skill` 更适合单篇人工阅读、特殊 provider、交互式补抓和 Core 失败后的人工核验；它不能替代主题发现、相关性判断、活动快照或 quarantine 门禁。
