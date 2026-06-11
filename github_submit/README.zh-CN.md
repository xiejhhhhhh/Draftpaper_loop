# Draftpaper-loop

`AI 科研循环` `Loop Engineering` `本地优先` `Python CLI` `LaTeX 初稿` `文献证据链` `全文抓取` `Codex Skill Wrapper`

中文 | [English](README.md)

Draftpaper-loop 是一个本地优先的科研论文 loop engine。CLI 是稳定的工具调用面，真正的产品概念是一个可反复运行的循环：观察项目状态、判断下一步安全阶段、运行命令、验证输出、保存 artifact 和 hash、诊断失败，并只重跑必要的上游环节。

仓库地址：https://github.com/xiejhhhhhh/Draftpaper-loop

## 快速开始

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

运行测试：

```powershell
python -m unittest discover -s tests
```

## 最近更新

### v0.6.0 (2026-06-11) -- renamed and reframed as Draftpaper-loop

- 将项目从 CLI-first 论文初稿工具重新定位为 loop-engineered 科研论文系统。
- 保留 `draftpaper` 作为稳定命令行接口。
- 将联系方式、商业使用条款和个人主页移动到 README 末尾，放在版本更新之后。

## 许可证、商业使用和联系方式

Draftpaper-loop 以 source-available 形式开放给非商业科研、评估、教学和个人论文工作流使用。商业使用需要单独获得书面授权。

如需商业授权，请联系 xiejinhui22@mails.ucas.ac.cn。

个人主页：https://xiejhhhhhh.github.io/Jinhui_profile/

第三方组件保留各自许可证。
