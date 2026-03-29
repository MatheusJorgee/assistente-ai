# ===========================================
# SETUP AUTOMÁTICO - Script Invisível
# Quinta-Feira v2.1 Port 8080 Auto-Startup
# ===========================================

# Script: instalar_silencioso.ps1
# Função: Copiar VBS para Startup do Windows
# Como usar: .\instalar_silencioso.ps1 (como Admin)

# ---- VERIFICAR SE ESTÁ COMO ADMIN ----
$isAdmin = [bool]([System.Security.Principal.WindowsIdentity]::GetCurrent().groups -match "S-1-5-32-544")

if (-not $isAdmin) {
    Write-Host "❌ Este script requer permissões de Administrador!" -ForegroundColor Red
    Write-Host "Solução: Abrir PowerShell como Admin (Win+X, depois A)" -ForegroundColor Yellow
    Read-Host "Pressiona Enter para sair..."
    exit 1
}

# ---- CAMINHOS ----
$projectRoot = "C:\Users\mathe\Documents\assistente-ai"
$vbsSource = "$projectRoot\quinta_feira_silenciosa.vbs"
$startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$vbsTarget = "$startupPath\quinta_feira_silenciosa.vbs"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "⚙️  INSTALAÇÃO: Script Silencioso" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---- VERIFICAÇÃO 1: VBS EXISTE? ----
Write-Host "`n[1/5] Verificando se VBS existe..." -ForegroundColor White
if (-not (Test-Path $vbsSource)) {
    Write-Host "❌ Arquivo não encontrado: $vbsSource" -ForegroundColor Red
    exit 1
}
Write-Host "✓ VBS encontrado em: $vbsSource" -ForegroundColor Green

# ---- VERIFICAÇÃO 2: Pasta Startup existe? ----
Write-Host "[2/5] Verificando pasta Startup..." -ForegroundColor White
if (-not (Test-Path $startupPath)) {
    Write-Host "⚠️  Pasta Startup não existe. Criando..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $startupPath -Force | Out-Null
}
Write-Host "✓ Pasta Startup: $startupPath" -ForegroundColor Green

# ---- VERIFICAÇÃO 3: backend/start_hub.py existe? ----
Write-Host "[3/5] Verificando backend/start_hub.py..." -ForegroundColor White
if (-not (Test-Path "$projectRoot\backend\start_hub.py")) {
    Write-Host "❌ Arquivo não encontrado: $projectRoot\backend\start_hub.py" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Backend encontrado" -ForegroundColor Green

# ---- VERIFICAÇÃO 4: .venv\Scripts\pythonw.exe existe? ----
Write-Host "[4/5] Verificando pythonw.exe no .venv..." -ForegroundColor White
$pythonw = "$projectRoot\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Host "❌ pythonw não encontrado em .venv" -ForegroundColor Red
    Write-Host "   Caminho esperado: $pythonw" -ForegroundColor Yellow
    Write-Host "   Solução: Verificar se .venv foi criado (python -m venv .venv)" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ pythonw.exe encontrado" -ForegroundColor Green

# ---- INSTALAÇÃO: COPIAR VBS ----
Write-Host "[5/5] Copiando script para Startup..." -ForegroundColor White
try {
    Copy-Item $vbsSource $vbsTarget -Force
    Write-Host "✓ Script copiado com sucesso!" -ForegroundColor Green
}
catch {
    Write-Host "❌ Erro ao copiar: $_" -ForegroundColor Red
    exit 1
}

# ---- SUCESSO ----
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "✅ INSTALAÇÃO COMPLETA!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Write-Host "`n📋 Resumo:" -ForegroundColor Cyan
Write-Host "  • VBS instalado: $vbsTarget" -ForegroundColor White
Write-Host "  • Porta: 8080" -ForegroundColor White
Write-Host "  • Auto-start: ✓ Ativado" -ForegroundColor White

Write-Host "`n🧪 Testar antes de reiniciar:" -ForegroundColor Cyan
Write-Host "  & '$vbsSource'" -ForegroundColor Yellow
Write-Host "  # Esperar 3s e verificar: netstat -ano | findstr :8080" -ForegroundColor Yellow

Write-Host "`n🚀 Próximas ações:" -ForegroundColor Cyan
Write-Host "  1. Testar manualmente (comando acima)" -ForegroundColor White
Write-Host "  2. Confirmar porta 8080 aberta (netstat)" -ForegroundColor White
Write-Host "  3. Reiniciar PC para ativar auto-start" -ForegroundColor White
Write-Host "  4. Verificar se backend iniciou sozinho" -ForegroundColor White

Write-Host "`n" -ForegroundColor White
Read-Host "Pressiona Enter para sair..."
