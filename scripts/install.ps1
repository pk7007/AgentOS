<#
.SYNOPSIS
  Install the agentos command for the current user. Dry run unless -Apply is given.

.DESCRIPTION
  Creates <AgentosHome>\venv, installs this repository into it (editable, so the bundled
  definitions stay in place), writes <AgentosHome>\bin\agentos.cmd, adds that folder to the
  *user* PATH (unless -NoPath), then runs `agentos init` and `agentos doctor`.
  It prints the Codex plugin commands but never runs them, and never edits ~/.codex/config.toml.
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$AgentosHome = $(if ($env:AGENTOS_HOME) { $env:AGENTOS_HOME } else { Join-Path $env:USERPROFILE ".agentos" }),
    [string]$Python = "python",
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$AgentosHome = [IO.Path]::GetFullPath($AgentosHome)
$Venv = Join-Path $AgentosHome "venv"
$Bin = Join-Path $AgentosHome "bin"
$Shim = Join-Path $Bin "agentos.cmd"
$Plugin = Join-Path $Repo "plugins\codex"

function Step([string]$Text) { if ($Apply) { Write-Host "==> $Text" } else { Write-Host "[plan] $Text" } }
function Fail([string]$Text) { Write-Host "error: $Text"; exit 1 }
function Check([string]$What) { if ($LASTEXITCODE -ne 0) { Fail "$What failed (exit $LASTEXITCODE)" } }

if (-not $Apply) { Write-Host "DRY RUN - nothing will change. Re-run with -Apply to install." }
Write-Host "repo:         $Repo"
Write-Host "agentos home: $AgentosHome"

Step "check $Python is Python 3.11 or newer"
if ($Apply) {
    $ver = (& $Python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1)
    if (-not $ver) { Fail "cannot run '$Python'. Install Python 3.11+ or pass -Python <path>." }
    if ([version]"$ver" -lt [version]"3.11") { Fail "Python $ver found; agentos needs Python 3.11 or newer." }
    Write-Host "    Python $ver"
}

Step "create virtual environment $Venv"
if ($Apply -and -not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    & $Python -m venv $Venv
    Check "venv creation"
}

Step "pip install -e $Repo into the virtual environment"
if ($Apply) {
    & (Join-Path $Venv "Scripts\python.exe") -m pip install --disable-pip-version-check -q -e $Repo
    Check "pip install"
}

Step "write $Shim"
if ($Apply) {
    New-Item -ItemType Directory -Force $Bin | Out-Null
    $lines = @(
        "@echo off",
        "setlocal",
        "if not defined AGENTOS_HOME set ""AGENTOS_HOME=$AgentosHome""",
        """%~dp0..\venv\Scripts\agentos.exe"" %*",
        "exit /b %ERRORLEVEL%"
    )
    [IO.File]::WriteAllText($Shim, ($lines -join "`r`n") + "`r`n", (New-Object Text.ASCIIEncoding))
}

if ($NoPath) {
    Write-Host "skip PATH change (-NoPath)"
} else {
    Step "add $Bin to the user PATH if missing"
    if ($Apply) {
        $old = [Environment]::GetEnvironmentVariable("Path", "User")
        $parts = @(($old -split ";") | Where-Object { $_ })
        if ($parts -contains $Bin) {
            Write-Host "    already on PATH"
        } else {
            $new = (@($parts) + $Bin) -join ";"
            [Environment]::SetEnvironmentVariable("Path", $new, "User")
            Write-Host "    old user PATH: $old"
            Write-Host "    new user PATH: $new"
            Write-Host "    open a new terminal to pick it up"
        }
    }
}

Step "agentos init and agentos doctor"
if ($Apply) {
    $env:AGENTOS_HOME = $AgentosHome
    & $Shim init
    Check "agentos init"
    & $Shim doctor
    Check "agentos doctor"
}

Write-Host ""
Write-Host "Codex plugin (run these yourself; agentos does not change your Codex config):"
Write-Host "    codex plugin marketplace add $Plugin"
Write-Host "    codex plugin add agentos@agentos"
Write-Host "Optional agent registrations to copy by hand: $Plugin\config-snippet.toml"
if (-not $Apply) { Write-Host ""; Write-Host "DRY RUN complete. Nothing was changed." }
exit 0
