[CmdletBinding()]
param(
    [ValidateSet("Check", "InstallCore")]
    [string]$Mode = "Check"
)

$ErrorActionPreference = "Stop"

$packages = @(
    [pscustomobject]@{
        Id = "Python.Python.3.11"
        Label = "Independent Python 3.11 runtime"
        ProbeNames = @("python", "py")
        InstallerOverride = "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0"
    },
    [pscustomobject]@{
        Id = "Microsoft.VCRedist.2015+.x64"
        Label = "Visual C++ x64 runtime"
        ProbeNames = @()
    },
    [pscustomobject]@{
        Id = "Git.Git"
        Label = "System Git for Windows"
        ProbeNames = @("git", "git.exe")
    },
    [pscustomobject]@{
        Id = "MiKTeX.MiKTeX"
        Label = "MiKTeX 25.12 private installation"
        ProbeNames = @("xelatex", "pdflatex", "bibtex", "kpsewhich")
    }
)

function Find-CommandPath {
    param([string[]]$Names)

    $knownPaths = @(
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python312\python.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python311\python.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python310\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python312\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python311\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python310\python.exe"),
        (Join-Path ${env:ProgramFiles} "Git\cmd\git.exe"),
        (Join-Path ${env:ProgramFiles} "Git\bin\git.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Git\cmd\git.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\MiKTeX\miktex\bin\x64\xelatex.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\MiKTeX\miktex\bin\x64\bibtex.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\MiKTeX\miktex\bin\x64\kpsewhich.exe")
    )
    foreach ($knownPath in $knownPaths) {
        $knownName = [System.IO.Path]::GetFileNameWithoutExtension($knownPath)
        if (($knownName -in $Names -or ($knownName + ".exe") -in $Names) -and (Test-Path -LiteralPath $knownPath)) {
            return $knownPath
        }
    }
    foreach ($name in $Names) {
        $command = Get-Command -Name $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) {
            return $command.Source
        }
    }
    return $null
}

function Test-VcRuntime {
    $locations = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($location in $locations) {
        $records = Get-ItemProperty -Path $location -ErrorAction SilentlyContinue
        foreach ($record in $records) {
            if ([string]$record.DisplayName -match "Visual C\+\+.*\(x64\)") {
                return $record
            }
        }
    }
    return $null
}

function Test-PythonRuntime {
    $candidates = @(
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python312\python.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python311\python.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Python\Python310\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python312\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python311\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python310\python.exe")
    )
    $uvPythonRoot = Join-Path ${env:APPDATA} "uv\python"
    if (Test-Path -LiteralPath $uvPythonRoot) {
        $candidates += Get-ChildItem -LiteralPath $uvPythonRoot -Directory -Filter "cpython-3.11-*" -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "python.exe" }
    }
    $pythonCommand = Get-Command -Name "python" -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $pythonCommand) {
        $candidates += $pythonCommand.Source
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        if ($candidate -match "[\\/](?:\.cache[\\/]codex-runtimes|hermes-agent[\\/]venv|\.venv)[\\/]") {
            continue
        }
        try {
            $version = (& $candidate -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null | Select-Object -First 1)
        }
        catch {
            continue
        }
        if ([string]$version -match "^3\.11(?:\.|$)") {
            return [pscustomobject]@{
                path = [string]$candidate
                version = [string]$version
            }
        }
    }
    return $null
}

function Get-ComponentReport {
    param($Package)

    if ($Package.Id -eq "Python.Python.3.11") {
        $python = Test-PythonRuntime
        if ($null -ne $python) {
            return [pscustomobject]@{
                id = $Package.Id
                label = $Package.Label
                status = "available"
                path = $python.path
                version = $python.version
                scope = "user_or_machine"
            }
        }
        return [pscustomobject]@{
            id = $Package.Id
            label = $Package.Label
            status = "missing_or_unsupported"
            path = $null
            version = $null
            scope = $null
        }
    }

    if ($Package.Id -eq "Microsoft.VCRedist.2015+.x64") {
        $vc = Test-VcRuntime
        if ($null -ne $vc) {
            return [pscustomobject]@{
                id = $Package.Id
                label = $Package.Label
                status = "available"
                path = $null
                version = [string]$vc.DisplayVersion
                scope = "machine"
            }
        }
        return [pscustomobject]@{
            id = $Package.Id
            label = $Package.Label
            status = "missing"
            path = $null
            version = $null
            scope = $null
        }
    }

    $paths = @()
    foreach ($probe in $Package.ProbeNames) {
        $path = Find-CommandPath -Names @($probe)
        if ($null -ne $path) {
            $paths += $path
        }
    }
    $standalonePath = $paths | Where-Object { $_ -notmatch "\.cache[\\/]codex-runtimes[\\/]" } | Select-Object -First 1
    $privateRuntime = $paths | Where-Object { $_ -match "\.cache[\\/]codex-runtimes[\\/]" } | Select-Object -First 1
    $miktexPath = $paths | Where-Object { $_ -match "MiKTeX" } | Select-Object -First 1
    $status = "missing"
    $pathValue = $null
    $scope = $null
    if ($Package.Id -eq "Git.Git" -and $null -ne $standalonePath) {
        $status = "available"
        $pathValue = [string]$standalonePath
    }
    elseif ($Package.Id -eq "Git.Git" -and $null -ne $privateRuntime) {
        $status = "non_standalone_tool"
        $pathValue = [string]$privateRuntime
    }
    elseif ($Package.Id -eq "MiKTeX.MiKTeX" -and $null -ne $miktexPath) {
        $pathValue = [string]$miktexPath
        $localPrefix = [string]$env:LOCALAPPDATA
        $scope = if ($localPrefix -and $miktexPath.StartsWith($localPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            "user"
        }
        else {
            "machine_or_unknown"
        }
        $status = if ($scope -eq "user") { "available" } else { "wrong_scope" }
    }
    elseif ($paths.Count -gt 0) {
        $status = "available"
        $pathValue = [string]$paths[0]
    }
    return [pscustomobject]@{
        id = $Package.Id
        label = $Package.Label
        status = $status
        path = $pathValue
        version = $null
        scope = $scope
    }
}

function Install-Package {
    param($Package)

    if ($Package.Id -eq "Python.Python.3.11") {
        $uv = Get-Command -Name "uv" -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $uv) {
            & $uv.Source python install 3.11 *> $null
            if ($LASTEXITCODE -eq 0) {
                return
            }
        }
    }

    if ($Package.Id -in @("MiKTeX.MiKTeX", "Python.Python.3.11")) {
        $arguments = @(
            "install", "--id", $Package.Id, "--exact", "--scope", "user",
            "--source", "winget", "--silent",
            "--accept-package-agreements", "--accept-source-agreements",
            "--disable-interactivity"
        )
    }
    else {
        $arguments = @(
            "install", "--id", $Package.Id, "--exact",
            "--source", "winget", "--silent",
            "--accept-package-agreements", "--accept-source-agreements",
            "--disable-interactivity"
        )
    }
    if ($Package.PSObject.Properties.Name -contains "InstallerOverride" -and $Package.InstallerOverride) {
        $arguments += @("--override", $Package.InstallerOverride)
    }
    & winget @arguments *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed for $($Package.Id) with exit code $LASTEXITCODE."
    }
}

$before = @($packages | ForEach-Object { Get-ComponentReport -Package $_ })
$actions = @()
if ($Mode -eq "InstallCore") {
    if ($null -eq (Get-Command -Name "winget" -CommandType Application -ErrorAction SilentlyContinue)) {
        throw "winget is required for InstallCore mode."
    }
    foreach ($package in $packages) {
        $current = $before | Where-Object { $_.id -eq $package.Id } | Select-Object -First 1
        if ($current.status -notin @("available")) {
            Install-Package -Package $package
            $actions += [pscustomobject]@{ id = $package.Id; action = "install_requested"; status = "completed" }
        }
        else {
            $actions += [pscustomobject]@{ id = $package.Id; action = "none"; status = "already_available" }
        }
    }
}

$after = @($packages | ForEach-Object { Get-ComponentReport -Package $_ })
$payload = [pscustomobject]@{
    schema_version = "dpl.windows_environment_bootstrap.v1"
    mode = $Mode
    mutated = ($Mode -eq "InstallCore")
    private_miktex_required = $true
    components = $after
    actions = $actions
    next_step = if ($Mode -eq "Check") {
        "Run InstallCore only after reviewing this report; then open a new shell, run Check again, and create the project virtual environment."
    }
    else {
        "Open a new shell, run Check, configure MiKTeX automatic package installation, and run Draftpaper verification."
    }
}
$payload | ConvertTo-Json -Depth 8 -Compress
