# ============================================================================
# register_quinta_startup.ps1 - Registra a Quinta-Feira para iniciar com o PC
# ----------------------------------------------------------------------------
# Cria um atalho na pasta Inicializar (Startup) do Windows apontando para o
# wrapper invisível (start_quinta_hidden.vbs). Roda no logon, sem precisar de
# admin, e sem nenhuma janela de terminal visível.
#
# Execute UMA vez. Para remover depois, rode: unregister_quinta_startup.ps1
# ============================================================================

$vbs = Join-Path $PSScriptRoot "start_quinta_hidden.vbs"
if (-not (Test-Path $vbs)) {
    Write-Host "ERRO: nao encontrei $vbs" -ForegroundColor Red
    exit 1
}

$startupDir = [System.Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startupDir "QuintaFeira.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = """$vbs"""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7   # minimizado/oculto
$shortcut.Description = "Inicia a Quinta-Feira (backend + frontend + briefing) no logon"
$shortcut.Save()

if (Test-Path $lnkPath) {
    Write-Host ""
    Write-Host "  Quinta-Feira registrada para iniciar com o PC!" -ForegroundColor Green
    Write-Host "  Atalho: $lnkPath"
    Write-Host ""
    Write-Host "  Testar agora sem reiniciar:"
    Write-Host "    wscript `"$vbs`""
    Write-Host ""
    Write-Host "  Remover depois:"
    Write-Host "    Remove-Item `"$lnkPath`""
} else {
    Write-Host "ERRO: falha ao criar o atalho." -ForegroundColor Red
    exit 1
}
