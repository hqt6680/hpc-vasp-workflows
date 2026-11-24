[CmdletBinding()]
param(
    [ValidateSet('Install', 'Start', 'Stop', 'Status', 'Uninstall')]
    [string]$Action = 'Status',

    [switch]$ResumeAtLogon
)

$ErrorActionPreference = 'Stop'
$taskPath = '\'
$projectRoot = Split-Path -Parent $PSScriptRoot
$watcherPath = Join-Path $PSScriptRoot 'pbs_watch.py'
$description = "VASP PBS watcher for $projectRoot"
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent()

if ($ResumeAtLogon -and $Action -ne 'Install') {
    throw '-ResumeAtLogon applies to Install.'
}

if (-not (Test-Path -LiteralPath $watcherPath -PathType Leaf)) {
    throw "Watcher script is missing: $watcherPath"
}
$python = Get-Command python.exe -CommandType Application | Select-Object -First 1
$taskName = & $python.Source -X utf8 $watcherPath task-name
if ($LASTEXITCODE -ne 0 -or $taskName -cnotmatch '^CodexVaspPbsWatch(?:-[0-9a-f]{16})?$') {
    throw 'Could not determine the Windows task name from the PBS watcher configuration.'
}

$task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
if ($task -and $task.Description -ne $description) {
    throw "The task name $taskName is already in use for another workspace."
}

if ($Action -eq 'Install') {
    $receipt = Join-Path $projectRoot '.vasp-local/restore.json'
    if ($task -and (Test-Path -LiteralPath $receipt -PathType Leaf)) {
        $record = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.watch.task_preexisting) {
            Write-Output "Using the existing task $taskName with its original settings."
            return
        }
    }
    if ($task -and $task.State -eq 'Running') {
        throw 'Stop the local watcher before reinstalling its task.'
    }

    $pythonwPath = Join-Path (Split-Path -Parent $python.Source) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
        throw "The current Python installation does not provide pythonw.exe: $pythonwPath"
    }

    $definition = @{
        Action = New-ScheduledTaskAction -Execute $pythonwPath -WorkingDirectory $projectRoot `
            -Argument ('-X utf8 "{0}" watch --interval 120' -f $watcherPath)
        Principal = New-ScheduledTaskPrincipal -UserId $account.User.Value -LogonType Interactive -RunLevel Limited
        Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Description = $description
    }
    if ($ResumeAtLogon) {
        $definition.Trigger = New-ScheduledTaskTrigger -AtLogOn -User $account.Name
    }

    Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -InputObject (New-ScheduledTask @definition) `
        -Force | Out-Null
    Write-Output "Installed $taskName."
    return
}

if (-not $task) {
    if ($Action -eq 'Status' -or $Action -eq 'Uninstall') {
        Write-Output "$taskName is not installed."
        return
    }
    throw "Install $taskName first."
}

switch ($Action) {
    'Start' { Start-ScheduledTask -InputObject $task }
    'Stop' { Stop-ScheduledTask -InputObject $task }
    'Status' {
        $info = Get-ScheduledTaskInfo -InputObject $task
        [pscustomobject]@{
            TaskName = $taskName
            State = $task.State
            ResumeAtLogon = [bool]$task.Triggers
            LastRunTime = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
        }
    }
    'Uninstall' {
        if ($task.State -eq 'Running') {
            Stop-ScheduledTask -InputObject $task
        }
        Unregister-ScheduledTask -InputObject $task -Confirm:$false
    }
}
