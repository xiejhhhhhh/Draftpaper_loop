# 科研代码来源

Draftpaper-loop 可以在保留文献的基础上补充 GitHub 和 Zenodo 的
metadata-only 科研代码线索。这一层负责发现和 provenance，不代表代码已
运行，也不代表论文结果已经复现或科学结论已经验证。

## 命令

```powershell
draftpaper enrich-literature-code-leads --project <project> --selection-mode knowledge_base
draftpaper discover-research-code --output-root <output> --discipline <discipline> --query "<query>"
draftpaper inspect-research-code-source --project <project> --candidate-id <id>
draftpaper fetch-research-code-archive --project <project> --candidate-id <id> --confirm-download
```

默认只处理保留文献、学科锚点文献和用户精选文献，生成
`references/code_sources.json`、provenance、候选 JSON、来源索引和质量报告。
检索阶段不会 clone、下载、解压、安装或执行第三方代码。只有显式加入
`--include-online` 或 `--enrich-code-sources-online` 才访问公开 provider API。

## 版本意图

- `knowledge_base`：默认选择最新稳定 release，同时保留论文时期版本谱系。
- `plugin_candidate`：选择环境兼容且已固定的版本，完成许可证、归档、环境和
  fixture 检查后才能晋升。
- `reproduction`：必须找到论文关联的精确 release/commit，不能用最新版冒充。
- `historical_reference`：仅作历史 provenance，不进入默认执行路径。
- `citation_only`：只保留元数据和链接。

“最新”只表示本次检索看到的最新可访问候选，不表示代码完整、最优或科学正确。

## 质量与安全

GitHub stars/forks、论文被引量、软件引用量、Zenodo 下载量、release 历史、
任务相关性、可复现性和维护状态分别记录，并带 provider 与检索时间。stars/forks
按仓库可用年限进行每年率与对数尺度辅助归一化；论文和软件引用按可识别的
发表年限进行每年率辅助归一化；缺失年限时明确标记为未调整，不补猜数值。任何
热度或被引信号都不能越过任务相关性、许可证、checksum、归档安全和人工晋升门禁。

只有人工明确确认后，归档才允许下载到 content-addressed quarantine。ZIP Slip、
绝对路径、路径逃逸、符号链接、设备文件、压缩炸弹、checksum 不一致和许可证
冲突都会被拒绝。下载命令不会执行归档中的代码。
