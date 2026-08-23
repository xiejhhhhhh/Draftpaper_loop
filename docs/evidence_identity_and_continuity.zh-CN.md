# 证据身份与确认连续性

Draftpaper-loop v0.41.0 将作者确认的科学决定与用于追溯该决定的技术审计包分开。

## 三类身份

- `scientific_decision_sha256`：科学输入与边界，覆盖数据/cohort/split/样本单位、
  方法/run、主指标与不确定性、主图语义证据和论断边界。
- `audit_bundle_sha256`：活动收据、artifact manifest、验证报告和技术审计细节。
- `presentation_sha256`：决定页的渲染和本地化。

只有第一类身份决定是否需要新的作者科学确认。HTML/CSS、路径、时间戳、JSON 排序、
派生报告重建、引用映射和 PDF 编译本身不会重新打开 core evidence；第二、三类变化仍会
在审计包中保留。

## continuity 规则

v5 成果包只有同时满足以下条件才可沿用旧的用户确认：

1. 旧 receipt 属于同一项目和同一 checkpoint family；
2. 科学决定 hash 与 DecisionBrief 语义 hash 都完全一致；
3. 当前包可确认，且所需证据身份完整；
4. 不存在 missing、stale、conflict 或无法分类的变化。

满足条件后会生成不可变的 `confirmation_continuity_receipt.json`，记录旧用户 receipt、
当前审计 hash 与 `preserve_previous_user_confirmation`。它不会伪造新的用户 receipt。

指标或不确定性、cohort、split、样本单位、方法、run、图表语义或论断边界变化均属科学
变化。页面会展示 semantic delta，并保持 C3/人工确认；未知变化一律阻断。

## 修复顺序

证据失败按以下顺序处理：

1. 修复证据生产者或源绑定；
2. 修复 validator/adapter 合同缺口；
3. 只修复受影响的正文歧义；
4. 仅在必要时修复图表元数据或图表语义；
5. 只有科学内容真实变化时才重跑数据或方法。

这样可以避免用文字修改掩盖证据身份错误，也避免把重画图表当成默认解决办法。
