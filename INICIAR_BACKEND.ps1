#!/usr/bin/env pwsh
# Script para iniciar o backend Quinta-Feira v2.1
# Uso: .\INICIAR_BACKEND.ps1

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "====== QUINTA-FEIRA v2.1 BACKEND ======" -ForegroundColor Cyan
Write-Host "Iniciando servidor em http://localhost:8000" -ForegroundColor Yellow
Write-Host ""

# Verificar se Python esta instalado
$pythonCheck = python --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Python nao foi encontrado. Instale Python primeiro." -ForegroundColor Red
    exit 1
}

Write-Host "Python detectado: $pythonCheck" -ForegroundColor Green

# Verificar se requirements foi instalado
$requirementsCheck = python -c "import fastapi; import uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Dependencias nao instaladas." -ForegroundColor Red
    Write-Host "Execute: pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host "Dependencias OK" -ForegroundColor Green
Write-Host ""

# Iniciar backend
python backend/main.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERRO: Falha ao executar backend" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}
