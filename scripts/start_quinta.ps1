# ============================================================================
# start_quinta.ps1 - Launcher da Quinta-Feira
# ----------------------------------------------------------------------------
# Sobe backend (uvicorn) + frontend (next) ocultos, aguarda o health check,
# abre a janela (navegador) e dispara o briefing matinal falado.
#
# Rodado normalmente via start_quinta_hidden.vbs (sem janelas visíveis).
# Logs em backend\.runtime\ para diagnóstico se algo falhar no boot.
# ============================================================================

$ErrorActionPreference = "SilentlyContinue"

# Raiz do projeto = pasta-pai deste script (scripts/ -> raiz)
$root     = Split-Path $PSScriptRoot -Parent
$backend  = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python   = Join-Path $backend ".venv\Scripts\python.exe"

# Pasta de logs
$logDir = Join-Path $backend ".runtime"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$launcherLog = Join-Path $logDir "quinta_launcher.log"
$backendLog  = Join-Path $logDir "quinta_backend.log"
$frontendLog = Join-Path $logDir "quinta_frontend.log"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $launcherLog -Value "$ts  $msg"
}

Log "===== Launcher iniciado ====="

# 1. Backend (uvicorn) em janela oculta, com stdout/stderr em arquivo
Log "Iniciando backend..."
Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $backend -WindowStyle Hidden `
    -RedirectStandardOutput $backendLog -RedirectStandardError "$backendLog.err"

# 2. Frontend (next dev) em janela oculta, com saída em arquivo
Log "Iniciando frontend..."
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev > `"$frontendLog`" 2>&1" `
    -WorkingDirectory $frontend -WindowStyle Hidden

# 3. Aguardar backend ficar saudável (até ~90s)
#    IMPORTANTE: usar 127.0.0.1 (IPv4) e NÃO "localhost". No Windows localhost
#    resolve para ::1 (IPv6) primeiro, mas o backend escuta em 0.0.0.0 (IPv4),
#    fazendo o health check expirar no timeout antes de cair para IPv4.
$healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
        if ($h.status -eq "healthy") { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if ($healthy) { Log "Backend saudavel apos ~$i s" } else { Log "AVISO: backend nao respondeu em 90s" }

# 4. Abrir a janela (navegador no frontend)
#    Preferimos o Chrome: o Brave (Shields) bloqueia iframes/imagens de terceiros
#    (TradingView, og:images), quebrando o visor. Fallback: navegador padrão.
$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
    Log "Abrindo no Chrome: $chrome"
    Start-Process -FilePath $chrome -ArgumentList "--new-window", "http://localhost:3000"
} else {
    Log "Chrome nao encontrado; abrindo no navegador padrao"
    Start-Process "http://localhost:3000"
}

# 5. A narração do briefing/notícias agora é feita PELO NAVEGADOR (frontend),
#    em sincronia com os cards do visor (a notícia falada == a exibida).
#    Por isso NÃO disparamos mais o briefing falado no backend (evita voz dupla).
Log "Briefing/noticias serao narrados pelo navegador (em sincronia com o visor)."
Log "===== Launcher concluido ====="
