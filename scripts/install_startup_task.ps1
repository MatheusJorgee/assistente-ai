$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repoRoot "scripts\start_quinta_feira.ps1"
$taskName = "QuintaFeiraAutoStart"
$startupFolder = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$startupCmd = Join-Path $startupFolder "QuintaFeiraAutoStart.cmd"

if (-not (Test-Path $launcher)) {
    Write-Error "Launcher não encontrado em: $launcher"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Inicia Quinta-Feira automaticamente no login" -Force | Out-Null
    Write-Host ">>> Tarefa '$taskName' registrada com sucesso."
    Write-Host ">>> Para remover depois: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
}
catch {
    $cmdContent = "@echo off`r`npowershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{0}""`r`n" -f $launcher
    Set-Content -Path $startupCmd -Value $cmdContent -Encoding ASCII
    Write-Host ">>> Sem permissão para Task Scheduler. Fallback aplicado na pasta Startup do usuário: $startupCmd"
    Write-Host ">>> Para remover depois: Remove-Item -Force `"$startupCmd`""
}
