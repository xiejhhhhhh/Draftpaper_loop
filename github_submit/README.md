# Draftpaper-loop

`AI Research Loop` `Loop Engineering` `Local-first` `Python CLI` `LaTeX Drafting` `Literature Evidence` `Paper Fetch` `Codex Skill Wrapper`

[中文](README.zh-CN.md) | English

Draftpaper-loop is a local-first research paper loop engine. The CLI is the stable tool surface, while the product concept is a repeatable loop: observe project state, decide the next safe stage, run a command, verify outputs, persist artifacts and hashes, diagnose failures, and rerun only the necessary upstream work.

Repository: https://github.com/xiejhhhhhh/Draftpaper-loop

## Quick Start

```powershell
python -m pip install -e .
python -m draftpaper_cli.cli create-project --root C:\DraftPaper_CLI\projects --idea "Your research idea" --field "machine learning astronomy" --target-journal APJS
python -m draftpaper_cli.cli status --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli run-pipeline --project C:\DraftPaper_CLI\projects\your_project
python -m draftpaper_cli.cli validate-project --project C:\DraftPaper_CLI\projects\your_project
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Recent Updates

### v0.6.0 (2026-06-11) -- renamed and reframed as Draftpaper-loop

- Reframed the project from a CLI-first paper drafting tool to a loop-engineered research manuscript system.
- Kept `draftpaper` as the stable command-line interface.
- Moved contact, commercial-use terms, and homepage information to the end of the README after the update log.

## License, Commercial Use, And Contact

Draftpaper-loop is source-available for non-commercial research, evaluation, education, and personal paper-writing workflows. Commercial use requires separate written authorization.

For commercial authorization, contact xiejinhui22@mails.ucas.ac.cn.

Personal homepage: https://xiejhhhhhh.github.io/Jinhui_profile/

Third-party components keep their own licenses.
