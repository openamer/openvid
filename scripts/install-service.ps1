<#
.SYNOPSIS
  Installs OPENVID as a persistent background service on Windows.
.DESCRIPTION
  Uses Task Scheduler (no admin needed) to run openvid-server at logon and
  restart it if it dies. Writes logs to <repo>\service.log.
.PARAMETER Remove
  Uninstall the scheduled task.
#>
param([switch]$Remove)

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Repo   # scripts/ -> repo root
$Python = Join-Path $env:LOCALAPPDATA "openamer-laptop\venv\Scripts\python.exe"
$TaskName = "OPENVID-Server"

if ($Remove) {
    schtasks /Delete /TN $TaskName /F 2>$null
    Write-Host "OPENVID service removed."
    exit 0
}

# load key from openamer .env into task env (token stored encrypted per-user)
$envFile = Join-Path $env:LOCALAPPDATA "openamer-laptop\.env"
$keyLine = (Get-Content $envFile | Select-String "^OPENROUTER_API_KEY=").Line
$key = $keyLine -replace "^OPENROUTER_API_KEY=", "" -replace '"', ""

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument "-m openvid.server --port 8765" `
    -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

# persist env vars for the task (user-level, survives reboot)
[Environment]::SetEnvironmentVariable("OPENVID_LLM_KEY", $key, "User")
[Environment]::SetEnvironmentVariable("OPENVID_LLM_MODEL", "z-ai/glm-5.3-flash", "User")
[Environment]::SetEnvironmentVariable("OPENVID_FILES_ROOT", "$Repo,C:\Users\$env:USERNAME\openamer-repo", "User")

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5
$health = try { (Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 5).Content } catch { "starting..." }
Write-Host "OPENVID service installed + started."
Write-Host "Health: $health"
