' stop_quintafeira.vbs - Parar Quinta-Feira
' Este script encerra o processo do backend de forma limpa

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Matar processo Python que está rodando main.py
objShell.Run "taskkill /IM python.exe /F /T", 0, True

' Esperar um pouco para confirmar encerramento
WScript.Sleep 1000

' Log de parada
backendDir = objFSO.GetParentFolderName(objFSO.GetParentFolderName(WScript.ScriptFullName)) & "\backend"
Set logWriter = objFSO.OpenTextFile(backendDir & "\quintafeira.log", 8, True)
logWriter.WriteLine "[" & Now & "] Quinta-Feira parado"
logWriter.Close

WScript.Echo "Quinta-Feira foi parado com sucesso"
