# Claude Code Integration

Draftpaper-loop treats every coding agent as a calling layer over the same
authoritative CLI workflow. This guide covers the Claude Code surface; the
Codex surface is documented in the main README. Nothing about the scientific
workflow changes between agents — the CLI owns stage order, evidence gates,
and human checkpoints.

## What ships in the repository

| Asset | Purpose |
| --- | --- |
| `CLAUDE.md` | Project memory loaded automatically when Claude Code opens the repository: workflow authority, required control loop, protected human checkpoints, do-not-edit list. |
| `.claude/skills/draftpaper-workflow/` | Project-scoped skill, byte-identical to the canonical resource packaged in the wheel (`draftpaper_cli/resources/draftpaper_workflow/`). |
| `.claude/commands/` | Slash commands: `/dp-status`, `/dp-continue`, `/dp-doctor`, `/dp-review`. Each one runs the `status` → `verify-next-action` control loop before acting. |
| `.claude/agents/paper-reviewer.md` | Optional read-only subagent for the two independent manuscript reviews. |
| `.claude/settings.json` | Permission guardrails: allows `python -m draftpaper_cli.cli …` invocations, denies direct edits to `project.json`, stage manifests, passports, and append-only ledgers. |
| `.mcp.json` | Project-scoped MCP configuration for the local stdio server (`python -m draftpaper_cli.mcp.server`). |

## Quick start

```bash
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git
cd Draftpaper_loop
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\activate
python -m pip install -e .[plotting]
claude
```

Claude Code picks up `CLAUDE.md`, the project skill, the slash commands, and
`.mcp.json` automatically. Then ask in natural language, for example:

> Create a paper project about X in field Y, search literature, write the
> research plan, and tell me which stage is blocked.

## User-level skill install

To use the skill outside this repository checkout, install the canonical copy
from the wheel into your Claude Code home:

```bash
draftpaper install-skill --agent claude          # ~/.claude/skills/draftpaper-workflow
draftpaper skill-doctor  --agent claude          # sha256 check against the canonical resource
```

`--agent codex` (the default) keeps the original behavior and installs into
`$CODEX_HOME/skills` (default `~/.codex/skills`). `CLAUDE_CONFIG_DIR`
overrides the Claude Code home. `--destination` still overrides the target
directory for either agent, and `--force` repairs a drifted install.

## MCP server

The repository root `.mcp.json` is already in Claude Code's project MCP
format (`"type": "stdio"`). To regenerate it, or to write the configuration
somewhere else:

```bash
python -m pip install -e .[mcp]
draftpaper mcp-doctor
draftpaper mcp-install --output .mcp.json
```

The server is a thin projection over CommandSpec metadata: roughly ten
bounded tools, no arbitrary shell, no raw writes, and no protected human
checkpoint can be executed through it. Science or network execution requires
the short-lived capability token described in the skill.

## Keeping the copies honest

The canonical skill lives in the wheel resource; the two repository copies
(`.claude/skills/…`, `codex_skills/…`) are generated from it.
`tests/test_claude_code_compat.py` fails whenever a copy drifts from the
canonical bytes, and `skill-doctor --agent claude|codex` performs the same
check against installed user-level copies.
