# SETUP COMPLETO - Instalar + Atalho Desktop
# Script: setup_completo.ps1
# Função: Fazer tudo de uma vez (Startup + Desktop)

param(
    [switch]$SkipStartup,
    [switch]$SkipDesktop
)

$projectRoot = "C:\Users\mathe\Documents\assistente-ai"

# ---- VERIFICAR ADMIN ----
$isAdmin = [bool]([System.Security.Principal.WindowsIdentity]::GetCurrent().groups -match "S-1-5-32-544")
if (-not $isAdmin) {
    Write-Host "❌ Requer admin! (Win+X, depois A)" -ForegroundColor Red
    exit 1
}

Write-Host "`n╔════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  QUINTA-FEIRA SETUP COMPLETO v2.1    ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════╝`n" -ForegroundColor Cyan

# ====== PARTE 1: STARTUP ======
if (-not $SkipStartup) {
    Write-Host "[1/2] INSTALLANDO NO WINDOWS STARTUP" -ForegroundColor Yellow
    Write-Host "════════════════════════════════════════" -ForegroundColor Yellow
    
    $vbsSource = "$projectRoot\quinta_feira_silenciosa.vbs"
    $startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    $vbsTarget = "$startupPath\quinta_feira_silenciosa.vbs"
    
    # Verificações
    if (-not (Test-Path $vbsSource)) {
        Write-Host "❌ VBS não encontrado" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $startupPath)) {
        New-Item -ItemType Directory -Path $startupPath -Force | Out-Null
    }
    if (-not (Test-Path "$projectRoot\.venv\Scripts\pythonw.exe")) {
        Write-Host "❌ pythonw.exe não encontrado em .venv" -ForegroundColor Red
        exit 1
    }
    
    # Copiar
    Copy-Item $vbsSource $vbsTarget -Force
    Write-Host "✓ VBS instalado em Startup" -ForegroundColor Green
    Write-Host "  Auto-start: ATIVADO (proxima reboot)" -ForegroundColor White
}

# ====== PARTE 2: DESKTOP SHORTCUT ======
if (-not $SkipDesktop) {
    Write-Host "`n[2/2] CRIANDO ATALHO NA DESKTOP" -ForegroundColor Yellow
    Write-Host "════════════════════════════════════════" -ForegroundColor Yellow
    
    $vbsFile = "$projectRoot\quinta_feira_silenciosa.vbs"
    $desktopPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop")
    $shortcutPath = "$desktopPath\Quinta-Feira.lnk"
    
    # Verificações
    if (-not (Test-Path $vbsFile)) {
        Write-Host "❌ VBS não encontrado" -ForegroundColor Red
        exit 1
    }
    
    # Criar atalho
    $shortcutObject = New-Object -ComObject WScript.Shell
    $shortcut = $shortcutObject.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbsFile`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "Quinta-Feira Backend - Auto-start invisível na porta 8080"
    $shortcut.IconLocation = "C:\Windows\System32\cmd.exe,0"
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    
    Write-Host "✓ Atalho criado na Desktop" -ForegroundColor Green
    Write-Host "  Nome: Quinta-Feira.lnk" -ForegroundColor White
    Write-Host "  Ícone: Command Prompt (azul)" -ForegroundColor White
}

# ====== RESUMO FINAL ======
Write-Host "`n╔════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  ✅ SETUP COMPLETO!                   ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════╝`n" -ForegroundColor Green

Write-Host "📋 RESUMO DO QUE FOI FEITO:" -ForegroundColor Cyan
Write-Host ""
if (-not $SkipStartup) {
    Write-Host "  ✓ VBS instalado em Windows Startup" -ForegroundColor Green
    Write-Host "    → Auto-start na próxima reboot" -ForegroundColor White
}
if (-not $SkipDesktop) {
    Write-Host "  ✓ Atalho 'Quinta-Feira.lnk' criado na Desktop" -ForegroundColor Green
    Write-Host "    → Duplo clique para iniciar manualmente" -ForegroundColor White
}

Write-Host "`n🎯 PRÓXIMOS PASSOS:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Na Desktop, duplo clique em 'Quinta-Feira.lnk'" -ForegroundColor White
Write-Host "     → Backend inicia silenciosamente" -ForegroundColor White
Write-Host "     → Sem janela de console visível" -ForegroundColor White
Write-Host ""
Write-Host "  2. Abrir browser: http://localhost:3000" -ForegroundColor White
Write-Host "     → Frontend conecta em ws://localhost:8080" -ForegroundColor White
Write-Host ""
Write-Host "  3. Testar: npm run dev (em novo terminal)" -ForegroundColor White
Write-Host "     → F12 → Console → Procurar 'Port=8080'" -ForegroundColor White
Write-Host ""
Write-Host "  4. Reiniciar PC para ativar auto-start" -ForegroundColor White
Write-Host "     → Backend inicia automaticamente" -ForegroundColor White
Write-Host "     → Sem fazer nada!" -ForegroundColor White

Write-Host "`n🔗 LOCAL DOS ARQUIVOS:" -ForegroundColor Cyan
Write-Host ""
if (-not $SkipStartup) {
    Write-Host "  Startup: $env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\quinta_feira_silenciosa.vbs" -ForegroundColor Gray
}
if (-not $SkipDesktop) {
    Write-Host "  Desktop: $([System.IO.Path]::Combine($env:USERPROFILE, 'Desktop'))\Quinta-Feira.lnk" -ForegroundColor Gray
}

Write-Host ""
Read-Host "Pressiona Enter para finalizar..."
