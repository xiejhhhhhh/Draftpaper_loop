# DraftPaper CLI

`AI Research Workflow` `Local-first` `Python CLI` `LaTeX Drafting` `Literature Evidence` `Paper Fetch` `Codex Skill Wrapper`

Contact: xiejinhui22@mails.ucas.ac.cn

[中文](README.zh-CN.md) | English

DraftPaper CLI is a local-first staged workflow engine for research paper projects. It turns a research idea, local data, verified method code, result artifacts, and traceable literature evidence into a staged LaTeX manuscript draft.

This submission package mirrors the public repository entrypoint. The project is source-available for non-commercial research, education, evaluation, and personal use. Commercial use, paid services, SaaS deployment, enterprise deployment, resale, or integration into commercial products requires written authorization from the developer.

Repository: https://github.com/xiejhhhhhh/Draftpaper_CLI

## Quick Start

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli search-literature --project C:\DraftPaper_CLI\projects\your_project --query "topic keywords"
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## License and Commercial Use

DraftPaper CLI is source-available for non-commercial research, evaluation, education, and personal paper-writing workflows. Commercial use requires separate written authorization.

For commercial authorization, contact xiejinhui22@mails.ucas.ac.cn.

Third-party components keep their own licenses.
