$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repoRoot "scripts\start_quinta_feira.ps1"

if (-not (Test-Path $launcher)) {
    Write-Error "Launcher não encontrado em: $launcher"
}

# Reinicia serviços para garantir carregamento da versão mais recente do código.
& $launcher -OpenBrowser -ForceRestart
