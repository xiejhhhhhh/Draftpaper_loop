# Draftpaper-loop Environment Deployment

This guide defines the complete local environment for producing and compiling a paper. A Python install profile is only one layer of the environment; it does not install a TeX distribution, Visual C++ runtime, or system Git.

## Supported targets

| Target | Use | Core checks |
|---|---|---|
| `control` | CLI, project state, and configuration | Python package and control-plane imports |
| `research` | Literature, data, methods, and evidence work | `control` plus plotting and full-text imports |
| `publication` | Complete paper production | `research` plus XeLaTeX, pdfLaTeX, BibTeX, `kpsewhich`, and system Git for a source checkout |
| `agent` | Agent/MCP operation | The selected target plus the MCP bridge and workflow Skill |

The control and research targets do not claim that a PDF can be compiled. Use the `publication` target before starting a final manuscript run.

## Windows standard route

The supported default route is a current-user MiKTeX 25.12 installation, system Git for Windows, and the Microsoft Visual C++ x64 runtime. It does not require administrator rights for MiKTeX and does not install MinerU, CUDA, Node.js, Java, or academic-library dependencies.

### 1. Create the Python environment

From a source checkout:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[plotting,fulltext,mcp]"
```

Python 3.10, 3.11, and 3.12 are supported. The `fulltext` extra installs the PyMuPDF route for enhanced local PDF extraction. MinerU remains an optional external endpoint or Agent connector; it is not part of the core installation.

### 2. Check and install system prerequisites

Run the read-only check first:

```powershell
.\tools\bootstrap_windows_environment.ps1 -Mode Check
```

The explicit core installer may request WinGet installation of only the following components:

```powershell
.\tools\bootstrap_windows_environment.ps1 -Mode InstallCore
```

It checks or installs:

- Microsoft Visual C++ 2015+ x64 runtime, required by native Python wheels such as PyMuPDF;
- Git for Windows in a normal system or current-user installation, not the Codex private runtime;
- MiKTeX 25.12 in private/current-user scope.

Open a new PowerShell after installation and run `-Mode Check` again. The script is intentionally not a general workstation bootstrapper: optional `gh`, Node.js, Java, MinerU, CUDA, and discipline-specific libraries must be installed separately when a project requires them.

### 3. Configure MiKTeX

MiKTeX Basic is a just-enough-TeX installation. Allow automatic installation of missing packages and refresh its file-name database:

```powershell
initexmf --set-config-value=[MPM]AutoInstall=yes
initexmf --update-fndb
```

The first real compile may download missing TeX packages. This is an explicit network boundary: a Basic MiKTeX installation with automatic package installation is not a fully offline reproduction environment. For an offline environment, pre-warm the required packages on a connected machine or use a separately managed TeX Live/MiKTeX package mirror.

### 4. Run deterministic diagnostics

`doctor` is read-only and does not install packages or modify a project:

```powershell
.\.venv\Scripts\python -m draftpaper_cli doctor --target publication --json
```

The report distinguishes a missing import, a native DLL import failure, a missing TeX executable, a wrong executable source, and a missing TeX resource. A private Codex Git executable does not satisfy the source-checkout publication requirement.

### 5. Run the complete isolated verifier

The explicit verifier writes only to the requested output directory. It runs a real `pypdf` PDF read, both XeLaTeX and pdfLaTeX plus BibTeX, and `kpsewhich plainnat.bst`:

```powershell
.\.venv\Scripts\python -m draftpaper_cli verify-environment `
  --target publication `
  --compile-latex `
  --output .tmp\environment-verification
```

The output contains:

- `environment_verification.json`, the machine-readable receipt;
- `environment_verification.zh-CN.html` and `environment_verification.en.html`, readable reports;
- isolated XeLaTeX and pdfLaTeX PDFs and compile logs under `artifacts/`.

The command fails when a core component is absent, when a PDF is empty/unreadable, when a TeX run has a fatal error, or when the final pass still contains unresolved citations. Initial TeX warnings are not treated as final evidence; the final engine pass is checked after BibTeX and the repeat runs.

### 6. Compile through Draftpaper

The standalone fixture verifies the toolchain. A separate Draftpaper smoke test must use a temporary project and the formal LaTeX assemble/compile entry point. Do not run an environment smoke test in a real paper directory. Keep its output outside Git and compare the protected project-state hash before and after the compile.

## Cross-platform alternatives

On Ubuntu or Debian, install a TeX distribution through the operating-system package manager, for example `texlive-xetex`, `texlive-latex-extra`, and `texlive-bibtex-extra`, then install Draftpaper and run the same `verify-environment` command. TeX Live is supported on Linux and macOS; MiKTeX 25.12 private scope is the Windows default, not a requirement for other platforms.

The `publication` contract uses an independently discoverable system Git for a source checkout. A wheel installation can use the `control` or `research` target without Git, but local LaTeX compilation still requires the four TeX tools.

## Troubleshooting

| Finding | Meaning | Recovery |
|---|---|---|
| `missing` Python module | The selected profile is not installed | Install the profile named by Doctor |
| `import_failed` with a DLL message | A native extension cannot load | Repair Visual C++ x64 and reinstall the affected wheel |
| `xelatex`/`pdflatex`/`bibtex` missing | The publication toolchain is incomplete | Install MiKTeX or TeX Live and reopen the shell |
| `kpsewhich plainnat.bst` empty | The bibliography resource is not discoverable | Refresh the file-name database and install the bibliography package |
| Git is from a Codex runtime | The source checkout is not using an independent system Git | Install Git for Windows and check `where.exe git` |
| first compile asks for packages | MiKTeX is using its normal on-demand behavior | Allow the package install, or pre-warm packages for offline work |
| MinerU unavailable | Optional enhanced PDF route is not configured | Continue with pypdf/PyMuPDF or configure a user-managed MinerU endpoint |

## What is not committed

Do not commit `.venv`, MiKTeX or Git binaries, downloaded TeX packages, local verification receipts, project data, API keys, tokens, user-directory paths, or real paper outputs. The repository contains the environment contract, schemas, tests, documentation, and deployment script only.
