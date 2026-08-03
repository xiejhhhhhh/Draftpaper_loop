# Draftpaper-loop Install Profiles

Draftpaper-loop keeps the workflow control plane separate from optional scientific runtimes. Install only the profile required by the current task, then use `draftpaper doctor --json` to inspect the active interpreter.

| Profile | Command | Capability boundary |
|---|---|---|
| Minimal | `python -m pip install draftpaper-cli` | Workflow control, bibliography, PDF inspection, packaged schemas/plugins and vendored paper-fetch fallback |
| Plotting | `python -m pip install "draftpaper-cli[plotting]"` | NumPy/pandas scientific plugin runtime, Matplotlib/SciencePlots figures, SciPy, seaborn and scikit-learn |
| Full text | `python -m pip install "draftpaper-cli[fulltext]"` | Enhanced PDF parsing, article extraction and metadata normalization; the vendored paper-fetch fallback remains available without this extra |
| MinerU Agent | `python -m pip install "draftpaper-cli[mineru-agent]"` | Compatibility profile only; the official Agent connector is already in core and this profile installs no local model or GPU runtime |
| MCP | `python -m pip install "draftpaper-cli[mcp]"` | Local stdio MCP server and typed MCP transport |
| Research workstation | `python -m pip install "draftpaper-cli[plotting,fulltext,mcp]"` | Combined local research environment |

For an editable checkout, replace `draftpaper-cli` with `-e .`, for example:

```powershell
python -m pip install -e ".[plotting,fulltext,mcp]"
draftpaper doctor --json
```

The Doctor report contains `environment.install_profiles`. Each profile reports required and missing import modules, capabilities, an exact recovery command and any runtime fallback. Missing optional profiles do not invalidate the minimal control plane. They must, however, be installed before a stage claims to execute the associated capability.

Release CI validates the independent minimal, plotting, fulltext and MCP environments. `mineru-agent` is a no-op connector profile and does not add a local MinerU model. Wheel metadata is also checked with `tools/verify_install_matrix.py` so heavy plotting or GPU packages cannot drift back into the default dependency set. Self-hosted MinerU is an external user-managed endpoint, not an installation profile.
