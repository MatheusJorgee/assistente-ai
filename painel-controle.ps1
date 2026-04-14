# Painel de Controle - Quinta Feira
$projectRoot = "C:\Users\mathe\Documents\assistente-ai"
$vbsIniciar = Join-Path $projectRoot "QuintaFeira-Iniciar.vbs"
$vbsParar = Join-Path $projectRoot "QuintaFeira-Parar.vbs"

$running = $true

while ($running) {
    Clear-Host
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  PAINEL DE CONTROLE - QUINTA FEIRA" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
    
    Write-Host "1. [INICIAR] Backend + Frontend + Browser" -ForegroundColor Green
    Write-Host "2. [PARAR] Todos os servicos" -ForegroundColor Yellow
    Write-Host "3. [STATUS] Health Check" -ForegroundColor Blue
    Write-Host "4. [REINICIAR] Servicos" -ForegroundColor Cyan
    Write-Host "5. [ABRIR] Navegador" -ForegroundColor Magenta
    Write-Host "6. [SAIR]" -ForegroundColor Red
    Write-Host "`n----------------------------------------" -ForegroundColor Gray
    
    $choice = Read-Host "Escolha uma opcao (1-6)"
    
    switch ($choice) {
        "1" {
            Write-Host "`n[*] Iniciando Quinta Feira..." -ForegroundColor Green
            & $vbsIniciar
            Start-Sleep -Seconds 3
        }
        
        "2" {
            Write-Host "`n[*] Parando todos os servicos..." -ForegroundColor Yellow
            & $vbsParar
            Start-Sleep -Seconds 2
        }
        
        "3" {
            Write-Host "`n[*] Testando conexao com backend..." -ForegroundColor Blue
            try {
                $response = curl http://localhost:8000/health -ErrorAction Stop
                Write-Host "[OK] Backend respondendo: $response" -ForegroundColor Green
            } catch {
                Write-Host "[ERRO] Backend nao esta respondendo!" -ForegroundColor Red
            }
            
            try {
                $response2 = curl http://localhost:3000 -ErrorAction Stop
                Write-Host "[OK] Frontend respondendo" -ForegroundColor Green
            } catch {
                Write-Host "[ERRO] Frontend nao esta respondendo!" -ForegroundColor Red
            }
            Write-Host "`nPressione Enter..." -ForegroundColor Gray
            Read-Host
        }
        
        "4" {
            Write-Host "`n[*] Reiniciando..." -ForegroundColor Cyan
            & $vbsParar
            Start-Sleep -Seconds 3
            & $vbsIniciar
            Start-Sleep -Seconds 3
        }
        
        "5" {
            Write-Host "`n[*] Abrindo navegador..." -ForegroundColor Magenta
            Start-Process "http://localhost:3000"
            Start-Sleep -Seconds 2
        }
        
        "6" {
            Write-Host "`nAte logo!" -ForegroundColor Cyan
            $running = $false
        }
        
        default {
            Write-Host "`n[ERRO] Opcao invalida!" -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
}
