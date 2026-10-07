' ============================================================================
' start_quinta_hidden.vbs - Wrapper invisivel
' ----------------------------------------------------------------------------
' Executa start_quinta.ps1 com janela 100% oculta (sem flash de terminal).
' E o alvo usado pela tarefa agendada no logon do Windows.
' ============================================================================

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Pasta onde este .vbs esta
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = scriptDir & "\start_quinta.ps1"

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"

' 0 = janela oculta ; False = nao esperar terminar
shell.Run cmd, 0, False
