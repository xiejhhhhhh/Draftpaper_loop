# DraftPaper CLI

`AI 科研工作流` `本地优先` `Python CLI` `LaTeX 初稿` `文献证据链` `全文抓取` `Codex Skill Wrapper`

联系方式：xiejinhui22@mails.ucas.ac.cn

中文 | [English](README.md)

DraftPaper CLI 是一个本地优先的科研论文流程化写作引擎。它把研究 idea、本地数据、已验证的方法代码、结果图表和可追溯文献证据组织成分阶段的 LaTeX 论文初稿。

该提交包对应公开仓库入口。项目以 source-available 形式开放给非商业科研、教学、评估和个人使用。商业使用、付费服务、SaaS 部署、企业部署、转售，或集成到商业产品中，需要获得项目开发者的书面授权。

仓库地址：https://github.com/xiejhhhhhh/Draftpaper_CLI

## 快速开始

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "你的研究idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

运行测试：

```powershell
python -m unittest discover -s tests
```

## 许可证和商业使用

DraftPaper CLI 以 source-available 形式开放给非商业科研、评估、教学和个人论文工作流使用。商业使用需要单独获得书面授权。

如需商业授权，请联系 xiejinhui22@mails.ucas.ac.cn。

第三方组件保留各自许可证。
