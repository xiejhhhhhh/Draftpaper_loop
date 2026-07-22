# Windows Global Install and Fresh-Session Verification

This guide installs the source checkout in editable mode so that `draftpaper` is available on `PATH` in new Windows terminals. It also installs the bundled Codex workflow skill so a newly opened Codex task can discover the matching workflow contract.

## What this setup guarantees

- `draftpaper` resolves outside the repository in a fresh shell.
- The imported package points to the intended checkout.
- The plotting profile used by real paper projects is available.
- The installed Codex workflow skill matches the package version and hash.
- A project can be created, validated, and inspected through the global command.

An editable install continues to depend on the source checkout. Keep the repository at a stable path; if it is moved, rerun the install command from the new location.

## 1. Check prerequisites

Draftpaper-loop requires Python 3.10 or newer and Git. In PowerShell:

```powershell
python --version
python -c "import sys; print(sys.executable)"
git --version
```

## 2. Clone to a stable location and install

The following example uses `D:\Draftpaper_loop`:

```powershell
git clone https://github.com/xiejhhhhhh/Draftpaper_loop.git D:\Draftpaper_loop
Set-Location D:\Draftpaper_loop
python -m pip install -U pip
python -m pip install -e ".[plotting]"
```

If the repository already exists, update it without rewriting local history:

```powershell
Set-Location D:\Draftpaper_loop
git pull --ff-only origin main
python -m pip install -e ".[plotting]"
```

The install creates the `draftpaper` launcher in the current Python interpreter's Scripts directory. Verify both the distribution and launcher:

```powershell
python -m pip show draftpaper-cli
where.exe draftpaper
```

## 3. Install the Codex workflow skill

Install the skill shipped with the same package version:

```powershell
draftpaper install-skill --destination "$HOME\.codex\skills\draftpaper-workflow" --force
draftpaper doctor --json
```

In the Doctor JSON, `environment.workflow_skill.status` should be `passed`. Open a new Codex task after installation so skill discovery starts from the updated directory.

`doctor` may still report missing optional profiles such as `fulltext`. That does not invalidate the minimal control plane or the installed plotting profile. Install an optional profile only when its capabilities are needed, for example:

```powershell
Set-Location D:\Draftpaper_loop
python -m pip install -e ".[plotting,fulltext]"
```

## 4. Verify from outside the repository

Launch a clean process in `%TEMP%`, resolve the executable, and run Doctor:

```powershell
cmd.exe /d /c "cd /d %TEMP% && where draftpaper && draftpaper doctor --json"
```

The command proves that success does not depend on the repository being the working directory or on a PowerShell profile.

## 5. Create and validate a smoke-test project

Keep generated paper projects and research data outside the source repository. When `--root` points outside the configured project root, acknowledge that boundary with `--allow-external-project-root`. Parse `project_path` from the command output because current releases append a stable short project ID to the directory name.

```powershell
$ProjectsRoot = "D:\Draftpaper_projects"

$Created = draftpaper create-project `
  --root $ProjectsRoot `
  --allow-external-project-root `
  --idea "Global install smoke test" `
  --field "workflow validation" `
  --target-journal MNRAS | ConvertFrom-Json

$Project = $Created.project_path
draftpaper validate-project --project $Project
draftpaper status --project $Project
```

Acceptance criteria:

- `create-project` returns `status: created` and a concrete `project_path`.
- `validate-project` returns `status: passed`, `error_count: 0`, and `warning_count: 0`.
- `status` returns `pipeline_state: ready` and a structured `next_action`.

Continue by following the reported next action rather than hard-coding a stage sequence:

```powershell
draftpaper run-pipeline --project $Project
draftpaper status --project $Project
```

## 6. Run the repository tests

Contributors should install the development profile and run the complete suite from the checkout:

```powershell
Set-Location D:\Draftpaper_loop
python -m pip install -e ".[dev,plotting]"
python -m pytest -q
```

The full suite includes subprocess, LaTeX/PDF, wheel, contract, and scientific workflow regressions, so it can take substantially longer than a small unit-test suite on Windows.

## Troubleshooting

### `draftpaper` is not recognized

Find the launcher directory:

```powershell
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

Add the printed directory to the current user's `PATH` through Windows Environment Variables, open a new terminal, and rerun `where.exe draftpaper`. Do not change the system Python or copy the launcher manually.

### The imported package points to another checkout

Run:

```powershell
draftpaper doctor --json
```

Inspect `environment.runtime_source`. If the path is stale, reinstall from the intended checkout with `python -m pip install -e ".[plotting]"`.

### The repository was moved

An editable install stores a link to the checkout. Reinstall from its new location and refresh the skill:

```powershell
Set-Location <new-repository-path>
python -m pip install -e ".[plotting]"
draftpaper install-skill --destination "$HOME\.codex\skills\draftpaper-workflow" --force
draftpaper doctor --json
```

### Remove the command

```powershell
python -m pip uninstall draftpaper-cli
```

The source checkout and generated paper projects are not deleted by uninstalling the Python distribution.
