<#
.SYNOPSIS
  Remove the agentos command for the current user. Dry run unless -Apply is given.

.DESCRIPTION
  Removes <AgentosHome>\venv, <AgentosHome>\bin and the PATH entry (unless -NoPath).
  Keeps state, backups and handovers. With -PurgeState those are removed too, after a final
  database backup is written to <AgentosHome>\agentos-final-<time>.db (which is kept).
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$AgentosHome = $(if ($env:AGENTOS_HOME) { $env:AGENTOS_HOME } else { Join-Path $env:USERPROFILE ".agentos" }),
    [switch]$PurgeState,
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"
$AgentosHome = [IO.Path]::GetFullPath($AgentosHome)
$Venv = Join-Path $AgentosHome "venv"
$Bin = Join-Path $AgentosHome "bin"
$Exe = Join-Path $Venv "Scripts\agentos.exe"
$Db = Join-Path $AgentosHome "state\agentos.db"

function Step([string]$Text) { if ($Apply) { Write-Host "==> $Text" } else { Write-Host "[plan] $Text" } }
function Fail([string]$Text) { Write-Host "error: $Text"; exit 1 }

if (-not $Apply) { Write-Host "DRY RUN - nothing will change. Re-run with -Apply to uninstall." }
Write-Host "agentos home: $AgentosHome"

if ($PurgeState) {
    Step "write a final database backup to $AgentosHome, then remove state, backups, handovers and logs"
    if ($Apply -and (Test-Path $Db)) {
        if (-not (Test-Path $Exe)) { Fail "cannot back up: $Exe is missing. Copy $Db yourself, then re-run." }
        $env:AGENTOS_HOME = $AgentosHome
        $out = & $Exe backup --dest $AgentosHome --json
        if ($LASTEXITCODE -ne 0) { Fail "final backup failed (exit $LASTEXITCODE); nothing was removed." }
        $final = ($out | Out-String | ConvertFrom-Json).path
        $kept = Join-Path $AgentosHome ("agentos-final-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".db")
        Move-Item -LiteralPath $final -Destination $kept
        Write-Host "    final backup kept: $kept"
    }
} else {
    Write-Host "keep state, backups and handovers (use -PurgeState to remove them)"
}

Step "remove $Venv"
if ($Apply -and (Test-Path $Venv)) { Remove-Item -LiteralPath $Venv -Recurse -Force }
Step "remove $Bin"
if ($Apply -and (Test-Path $Bin)) { Remove-Item -LiteralPath $Bin -Recurse -Force }

if ($PurgeState -and $Apply) {
    foreach ($d in "state", "backups", "handovers", "logs") {
        $p = Join-Path $AgentosHome $d
        if (Test-Path $p) { Remove-Item -LiteralPath $p -Recurse -Force }
    }
}

if ($NoPath) {
    Write-Host "skip PATH change (-NoPath)"
} else {
    Step "remove $Bin from the user PATH"
    if ($Apply) {
        $old = [Environment]::GetEnvironmentVariable("Path", "User")
        $parts = @(($old -split ";") | Where-Object { $_ })
        if ($parts -contains $Bin) {
            $new = (@($parts) | Where-Object { $_ -ne $Bin }) -join ";"
            [Environment]::SetEnvironmentVariable("Path", $new, "User")
            Write-Host "    old user PATH: $old"
            Write-Host "    new user PATH: $new"
        } else {
            Write-Host "    not on PATH"
        }
    }
}

Write-Host "The Codex plugin, if you added it, stays until you run: codex plugin remove agentos@agentos"
if (-not $Apply) { Write-Host ""; Write-Host "DRY RUN complete. Nothing was changed." }
exit 0
