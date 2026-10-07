# ============================================================================
# quinta_control.ps1 - Painel de controle da Quinta-Feira
# ----------------------------------------------------------------------------
# Liga, desliga, reinicia e mostra o status do assistente.
# Uso: clique no atalho "Quinta-Feira" (menu interativo) OU:
#   powershell -File quinta_control.ps1 -Acao ligar|desligar|reiniciar|status
# ============================================================================

param(
    [ValidateSet("ligar", "desligar", "reiniciar", "status", "menu")]
    [string]$Acao = "menu"
)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path $PSScriptRoot -Parent
$vbs  = Join-Path $PSScriptRoot "start_quinta_hidden.vbs"

function Get-PortPids([int]$porta) {
    $conns = Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue
    if ($conns) { return ($conns.OwningProcess | Select-Object -Unique) }
    return @()
}

function Kill-Pid([int]$id) {
    # CIM Terminate funciona onde Stop-Process/taskkill falham (processos detached)
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($p) { Invoke-CimMethod -InputObject $p -MethodName Terminate | Out-Null }
}

function Stop-Quinta {
    Write-Host "  Desligando Quinta-Feira..." -ForegroundColor Yellow
    # Backend (8000) e frontend (3000)
    foreach ($porta in 8000, 3000) {
        foreach ($id in (Get-PortPids $porta)) { Kill-Pid $id }
    }
    # Stragglers: python/node/cmd do projeto
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like "*uvicorn main:app*" -or
                $_.CommandLine -like "*npm run dev*" -or
                ($_.CommandLine -like "*assistente-ai*" -and ($_.Name -in @("python.exe","node.exe")))
            )
        } | ForEach-Object { Kill-Pid $_.ProcessId }
    Start-Sleep -Seconds 2
    Write-Host "  Desligado." -ForegroundColor Green
}

function Start-Quinta {
    Write-Host "  Ligando Quinta-Feira (backend + frontend + briefing)..." -ForegroundColor Cyan
    Start-Process "wscript.exe" -ArgumentList """$vbs"""
    Write-Host "  Iniciando em segundo plano. A janela abrira e o briefing sera falado em instantes." -ForegroundColor Green
}

function Show-Status {
    $b = Get-PortPids 8000
    $f = Get-PortPids 3000
    $online = $false
    try { $h = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 3; $online = ($h.status -eq "healthy") } catch {}
    Write-Host ""
    Write-Host "  STATUS DA QUINTA-FEIRA" -ForegroundColor Cyan
    Write-Host "  ----------------------"
    Write-Host "  Backend (8000):  $(if($b){"NO AR (PID $($b -join ','))"}else{'desligado'})"
    Write-Host "  Frontend (3000): $(if($f){"NO AR (PID $($f -join ','))"}else{'desligado'})"
    Write-Host "  Health check:    $(if($online){'healthy'}else{'sem resposta'})"
    Write-Host ""
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host ""
        Write-Host "  ============================" -ForegroundColor Cyan
        Write-Host "      QUINTA-FEIRA - CONTROLE" -ForegroundColor Cyan
        Write-Host "  ============================" -ForegroundColor Cyan
        Show-Status
        Write-Host "   [1] Ligar"
        Write-Host "   [2] Desligar"
        Write-Host "   [3] Reiniciar"
        Write-Host "   [4] Atualizar status"
        Write-Host "   [0] Sair"
        Write-Host ""
        $op = Read-Host "  Escolha"
        switch ($op) {
            "1" { Start-Quinta; Read-Host "  (enter para voltar)" }
            "2" { Stop-Quinta;  Read-Host "  (enter para voltar)" }
            "3" { Stop-Quinta; Start-Quinta; Read-Host "  (enter para voltar)" }
            "4" { }
            "0" { return }
            default { }
        }
    }
}

switch ($Acao) {
    "ligar"     { Start-Quinta }
    "desligar"  { Stop-Quinta }
    "reiniciar" { Stop-Quinta; Start-Quinta }
    "status"    { Show-Status }
    "menu"      { Show-Menu }
}
