param(
    [switch]$OpenBrowser,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

function Open-QuintaFeiraUi {
    param([string]$Url)

    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe"
    )

    $chromeExe = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chromeExe) {
        Start-Process -FilePath $chromeExe -ArgumentList "--new-window", $Url -WindowStyle Normal
        return
    }

    # Fallback: navegador padrão
    Start-Process $Url
}

function Test-PortInUse {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $conn
    } catch {
        return $false
    }
}

function Stop-ProcessOnPort {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $conn -and $conn.OwningProcess -gt 0) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
    } catch {
        # Sem ação: se não conseguir parar, próxima checagem de porta decide o fluxo.
    }
}

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python do ambiente virtual não encontrado em: $pythonExe"
}

if ($ForceRestart) {
    Write-Host ">>> Reinício forçado solicitado. Encerrando serviços nas portas 8000 e 3000..."
    Stop-ProcessOnPort -Port 8000
    Stop-ProcessOnPort -Port 3000
}

if (-not (Test-PortInUse -Port 8000)) {
    Write-Host ">>> Iniciando backend na porta 8000..."
    Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $backendDir -WindowStyle Hidden
} else {
    Write-Host ">>> Backend já está ativo na porta 8000."
}

if (-not (Test-PortInUse -Port 3000)) {
    Write-Host ">>> Iniciando frontend na porta 3000..."
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory $frontendDir -WindowStyle Hidden
} else {
    Write-Host ">>> Frontend já está ativo na porta 3000."
}

if ($OpenBrowser) {
    Start-Sleep -Seconds 2
    Open-QuintaFeiraUi -Url "http://127.0.0.1:3000"
}
