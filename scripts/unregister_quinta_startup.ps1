# ============================================================================
# unregister_quinta_startup.ps1 - Remove a Quinta-Feira da inicializacao
# ============================================================================

$startupDir = [System.Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startupDir "QuintaFeira.lnk"

if (Test-Path $lnkPath) {
    Remove-Item $lnkPath -Force
    Write-Host "Atalho de inicializacao removido: $lnkPath" -ForegroundColor Green
} else {
    Write-Host "Nenhum atalho de inicializacao encontrado."
}
