#!/usr/bin/env pwsh
# Script para reset de memória - Remove o histórico de erros da Quinta-Feira
# Utilidade para resolver "Alucinação Induzida por Histórico"

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "====== RESET DE MEMORIA - QUINTA-FEIRA ======" -ForegroundColor Cyan
Write-Host "Removendo historico de erros guardado na base de dados..." -ForegroundColor Yellow
Write-Host ""

# Chamar o script Python
python reset_memoria.py
$exitCode = $LASTEXITCODE

Write-Host ""

if ($exitCode -eq 0) {
    Write-Host "✓ Reset de memoria concluido com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Próximos passos:" -ForegroundColor Cyan
    Write-Host "  1. Reinicie o backend: python backend/main.py"
    Write-Host "  2. A assistente agora terá memoria limpa e chamara ferramentas normalmente"
    Write-Host ""
} else {
    Write-Host "✗ Erro ao executar reset de memoria" -ForegroundColor Red
}

Read-Host "Pressione Enter para sair"
