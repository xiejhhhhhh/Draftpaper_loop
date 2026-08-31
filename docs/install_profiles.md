# Draftpaper-loop Install Profiles

Draftpaper-loop keeps the workflow control plane separate from optional scientific runtimes. Install only the profile required by the current task, then use `draftpaper doctor --json` to inspect the active interpreter.

| Profile | Command | Capability boundary |
|---|---|---|
| Minimal | `python -m pip install draftpaper-cli` | Workflow control, bibliography, PDF inspection, packaged schemas/plugins and vendored paper-fetch fallback |
| Plotting | `python -m pip install "draftpaper-cli[plotting]"` | NumPy/pandas scientific plugin runtime, Matplotlib/SciencePlots figures, SciPy, seaborn, scikit-learn and rendered-figure OCR quality checks |
| Full text | `python -m pip install "draftpaper-cli[fulltext]"` | Enhanced PDF parsing, article extraction and metadata normalization; the vendored paper-fetch fallback remains available without this extra |
| MinerU Agent | `python -m pip install "draftpaper-cli[mineru-agent]"` | Compatibility profile only; the official Agent connector is already in core and this profile installs no local model or GPU runtime |
| MCP | `python -m pip install "draftpaper-cli[mcp]"` | Local stdio MCP server and typed MCP transport |
| Browser | `python -m pip install "draftpaper-cli[browser]"` | Optional publisher-browser fallback; Python 3.11/3.12 and browser assets installed separately |
| Research workstation | `python -m pip install "draftpaper-cli[plotting,fulltext]"` | Combined local research environment; add `mcp` separately for Agent operation |

For an editable checkout, replace `draftpaper-cli` with `-e .`, for example:

```powershell
python -m pip install -c requirements/runtime-constraints.txt -e ".[plotting,fulltext]"
draftpaper doctor --json
```

For Agent/MCP operation, install the additional bridge explicitly:

```powershell
python -m pip install -c requirements/runtime-constraints.txt -e ".[mcp]"
```

The Doctor report contains `environment.install_profiles`. Each profile reports required and missing import modules, capabilities, an exact recovery command and any runtime fallback. Missing optional profiles do not invalidate the minimal control plane. They must, however, be installed before a stage claims to execute the associated capability.

Python profiles do not constitute the complete publication environment. A local final-paper build additionally requires a working TeX distribution with `xelatex`, `pdflatex`, `bibtex`, and `kpsewhich`; a source checkout also requires an independently discoverable system Git. `minimal`/`plotting` support Python 3.10-3.12; `fulltext`/`research`/`publication`/`agent`/`browser` support Python 3.11-3.12. On Windows, follow the [complete environment deployment guide](environment_deployment.md) for the MiKTeX 25.12 private-install route, Visual C++ x64 runtime, read-only diagnostics, and isolated compilation verification.

Release CI validates the independent minimal, plotting, fulltext, MCP and browser environments; fulltext also imports the vendored paper-fetch CLI. `mineru-agent` is a no-op connector profile and does not add a local MinerU model. Wheel metadata is also checked with `tools/verify_install_matrix.py` so heavy plotting or GPU packages cannot drift back into the default dependency set. Self-hosted MinerU is an external user-managed endpoint, not an installation profile.
