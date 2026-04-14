# start_quintafeira.ps1 - Gerenciador de inicialização para Quinta-Feira
# Executa o backend FastAPI com validações e logging

param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start"
)

# Configuração
$projectRoot = Split-Path -Parent -Path $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$venvPath = Join-Path $backendDir ".venv"
$mainScript = Join-Path $backendDir "main.py"
$logFile = Join-Path $backendDir "quintafeira.log"
$pidFile = Join-Path $backendDir "quintafeira.pid"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

# Cores para output
$colors = @{
    Success = "Green"
    Error = "Red"
    Warning = "Yellow"
    Info = "Cyan"
}

function Write-Log {
    param([string]$Message, [string]$Type = "Info")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Type] $Message"
    Add-Content -Path $logFile -Value $logMessage
    Write-Host $logMessage -ForegroundColor $colors[$Type]
}

function Validate-Environment {
    # Verificar se venv existe
    if (-not (Test-Path $venvPath)) {
        Write-Log "ERRO: Ambiente virtual não encontrado em $venvPath" "Error"
        Write-Log "Execute: cd $backendDir; python -m venv .venv" "Error"
        return $false
    }
    
    # Verificar se Python existe
    if (-not (Test-Path $pythonExe)) {
        Write-Log "ERRO: Python executável não encontrado em $pythonExe" "Error"
        return $false
    }
    
    # Verificar se main.py existe
    if (-not (Test-Path $mainScript)) {
        Write-Log "ERRO: main.py não encontrado em $mainScript" "Error"
        return $false
    }
    
    return $true
}

function Start-QuintafeirService {
    Write-Log "Iniciando Quinta-Feira..." "Info"
    
    if (-not (Validate-Environment)) {
        Write-Log "Validação de ambiente falhou" "Error"
        return $false
    }
    
    # Verificar se já está rodando
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile
        if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
            Write-Log "Quinta-Feira já está rodando (PID: $oldPid)" "Warning"
            return $true
        }
    }
    
    # Iniciar o processo
    try {
        $process = Start-Process -FilePath $pythonExe `
                                -ArgumentList $mainScript `
                                -WorkingDirectory $backendDir `
                                -PassThru `
                                -NoNewWindow
        
        # Salvar PID
        $process.Id | Out-File -FilePath $pidFile -Force
        
        Write-Log "Quinta-Feira iniciado com sucesso (PID: $($process.Id))" "Success"
        
        # Aguardar um pouco e verificar se está rodando
        Start-Sleep -Seconds 2
        
        if ($process.HasExited) {
            Write-Log "Processo terminou inesperadamente!" "Error"
            return $false
        }
        
        Write-Log "Backend respondendo em: http://localhost:8000" "Success"
        Write-Log "Frontend disponível em: http://localhost:3000" "Success"
        
        return $true
    }
    catch {
        Write-Log "Erro ao iniciar Quinta-Feira: $_" "Error"
        return $false
    }
}

function Stop-QuintafeirService {
    Write-Log "Parando Quinta-Feira..." "Info"
    
    if (-not (Test-Path $pidFile)) {
        Write-Log "Arquivo PID não encontrado. Tentando matar todos os python.exe..." "Warning"
        Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
        Write-Log "Processos Python encerrados" "Success"
        return
    }
    
    $pid = Get-Content $pidFile
    
    try {
        if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {
            Stop-Process -Id $pid -Force
            Write-Log "Processo $pid encerrado com sucesso" "Success"
        }
        else {
            Write-Log "Processo $pid não encontrado" "Warning"
        }
    }
    catch {
        Write-Log "Erro ao parar processo: $_" "Error"
    }
    
    # Remover arquivo PID
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force
    }
}

function Get-QuintafeirStatus {
    Write-Host "================== STATUS QUINTA-FEIRA ==================" -ForegroundColor Cyan
    
    if (-not (Test-Path $pidFile)) {
        Write-Host "Status: NÃO RODANDO" -ForegroundColor Red
        return
    }
    
    $pid = Get-Content $pidFile
    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
    
    if ($process) {
        Write-Host "Status: ✅ RODANDO" -ForegroundColor Green
        Write-Host "PID: $pid" -ForegroundColor Green
        Write-Host "Processo: $($process.ProcessName)" -ForegroundColor Green
        Write-Host "Memória: $([Math]::Round($process.WorkingSet / 1MB, 2)) MB" -ForegroundColor Green
        Write-Host "CPU: $($process.CPU) segundos" -ForegroundColor Green
        Write-Host ""
        Write-Host "Endpoints:"
        Write-Host "  - Backend API: http://localhost:8000" -ForegroundColor Cyan
        Write-Host "  - Frontend: http://localhost:3000" -ForegroundColor Cyan
        Write-Host "  - API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
    }
    else {
        Write-Host "Status: NÃO RODANDO (arquivo PID antigo)" -ForegroundColor Yellow
        Remove-Item $pidFile -Force
    }
    
    Write-Host "==========================================================" -ForegroundColor Cyan
}

# Executar ação
switch ($Action.ToLower()) {
    "start" {
        Start-QuintafeirService
    }
    "stop" {
        Stop-QuintafeirService
    }
    "restart" {
        Stop-QuintafeirService
        Start-Sleep -Seconds 2
        Start-QuintafeirService
    }
    "status" {
        Get-QuintafeirStatus
    }
    default {
        Write-Host "Uso: .\start_quintafeira.ps1 -Action [start|stop|restart|status]" -ForegroundColor Yellow
    }
}

Write-Log "Ação completada: $Action" "Info"
