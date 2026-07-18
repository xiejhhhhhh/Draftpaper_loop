# 最终论文信息补全与精确修订

Draftpaper-loop 使用一个可审阅事务集中处理最终作者信息和定点正文修改。Completion workspace 不会替代 canonical section source，也不会成为第二套 Scientific Evidence Registry。

## 操作流程

```powershell
draftpaper prepare-manuscript-completion --project <project>
draftpaper preview-manuscript-completion --project <project> --input manuscript_completion.yaml
draftpaper apply-manuscript-completion --project <project> --packet-id <id> --packet-hash <sha256>
draftpaper manuscript-completion-status --project <project>
draftpaper rollback-manuscript-completion --project <project> --transaction-id <id>
```

`prepare-manuscript-completion` 会生成符合目标期刊要求的模板，并区分必填、推荐、缺失、占位符和不适用字段。用户只需要填写一个 `manuscript_completion.yaml`，即可一次补充作者、单位、ORCID、基金、致谢、数据与代码可用性、链接、人工确认的新文献和多处正文修订。

## 稳定段落定位

每项修订至少提供一个稳定校验条件：

```yaml
section_revisions:
  - revision_key: methods-robustness-note
    target:
      section: methods
      paragraph_id: methods:p004:1a2b3c4d5e
      expected_sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
      expected_text: 当前段落原文。
      line_start_hint: 118
      line_end_hint: 126
    operation: insert_after
    mode: exact_text
    content: 作者确认后的补充内容。
```

行号只用于方便用户查看。真正的写入依据是 `paragraph_id`、`expected_sha256`、规范化原文和可选 occurrence。任何 stale、歧义、重叠或冲突目标都会让整个 packet 被拒绝，不会只写入一部分。

## 预览与接受

Preview 会生成统一的 metadata/section/BibTeX diff、定位报告、stale 影响报告、候选 LaTeX 和候选 PDF，但不会修改 canonical manuscript。`compile_required`、尚未生成的 Codex patch，或者数据、方法、run、科学证据变更均为非通过状态。

Apply 必须使用 preview 给出的准确 packet hash。系统会再次核对 project revision、source-map hash、promoted evidence snapshot 和所有目标的 before hash，然后原子写入。作者确认的 exact text 会形成 user lock，后续 writer 不能静默覆盖；重复 apply 保持幂等。

Rollback 只有在全部 after hash 仍与事务 receipt 一致时才允许执行，不会覆盖 completion 之后新增的人工修改。

## 最终发布顺序

Completion 完成后，需要重新组装并编译 `latex/main.pdf`，再运行最终 citation audit、integrity/quality gate 和两位独立盲评者。`review-final-manuscript` 会把 active completion manifest、canonical manuscript、reference registry、evidence snapshot、citation audit、审稿报告、质量报告和 PDF 绑定为同一个 release hash。

