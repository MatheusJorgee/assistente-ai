# Create Desktop Shortcut for Quinta-Feira Silent Startup
# Script: criar_atalho_desktop.ps1
# Função: Criar atalho na Desktop para quinta_feira_silenciosa.vbs

# ---- CAMINHOS ----
$projectRoot = "C:\Users\mathe\Documents\assistente-ai"
$vbsFile = "$projectRoot\quinta_feira_silenciosa.vbs"
$desktopPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop")
$shortcutPath = "$desktopPath\Quinta-Feira.lnk"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "📌 Criar Atalho na Desktop" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# ---- VERIFICAÇÃO ----
Write-Host "`n[1/3] Verificando VBS..." -ForegroundColor White
if (-not (Test-Path $vbsFile)) {
    Write-Host "❌ VBS não encontrado: $vbsFile" -ForegroundColor Red
    exit 1
}
Write-Host "✓ VBS encontrado" -ForegroundColor Green

Write-Host "`n[2/3] Verificando Desktop..." -ForegroundColor White
if (-not (Test-Path $desktopPath)) {
    Write-Host "❌ Desktop não encontrada" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Desktop: $desktopPath" -ForegroundColor Green

# ---- CRIAR ATALHO ----
Write-Host "`n[3/3] Criando atalho..." -ForegroundColor White
try {
    # Criar objeto COM para atalho do Windows
    $shortcutObject = New-Object -ComObject WScript.Shell
    $shortcut = $shortcutObject.CreateShortcut($shortcutPath)
    
    # Definir propriedades do atalho
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbsFile`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "Quinta-Feira Backend - Auto-start invisível na porta 8080"
    $shortcut.IconLocation = "C:\Windows\System32\cmd.exe,0"  # Ícone de CMD (azul)
    $shortcut.WindowStyle = 7  # 7 = Minimizado
    
    # Salvar atalho
    $shortcut.Save()
    
    Write-Host "✓ Atalho criado com sucesso!" -ForegroundColor Green
}
catch {
    Write-Host "❌ Erro ao criar atalho: $_" -ForegroundColor Red
    exit 1
}

# ---- SUCESSO ----
Write-Host "`n======================================" -ForegroundColor Green
Write-Host "✅ ATALHO NA DESKTOP CRIADO!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

Write-Host "`n📍 Localização: $shortcutPath" -ForegroundColor Cyan
Write-Host "`n🎯 Duplo clique no atalho para:" -ForegroundColor Cyan
Write-Host "   1. Iniciar backend na porta 8080" -ForegroundColor White
Write-Host "   2. Sem janela de console visível" -ForegroundColor White
Write-Host "   3. Silenciosamente em background" -ForegroundColor White

Write-Host "`n✨ Dica: Copiar atalho e colar no Startup para auto-start" -ForegroundColor Yellow
Write-Host "   Startup: C:\\Users\\mathe\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup" -ForegroundColor Yellow

Write-Host "`n" -ForegroundColor White
Read-Host "Pressiona Enter para sair..."
