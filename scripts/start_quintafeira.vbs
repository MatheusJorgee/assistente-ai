' start_quintafeira.vbs - Iniciar Quinta-Feira em background silenciosamente
' Este script executa o backend sem abrir janela visível

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Obter caminho do diretório do projeto
scriptDir = objFSO.GetParentFolderName(objFSO.GetParentFolderName(WScript.ScriptFullName))
backendDir = scriptDir & "\backend"

' Nome do arquivo de log
logFile = backendDir & "\quintafeira.log"

' Comando para executar (uvicorn)
cmdLine = backendDir & "\.venv\Scripts\python.exe " & backendDir & "\main.py"

' Executar em background, minimizado, sem janela
objShell.Run cmdLine, 0, False

' Log de início
Set logWriter = objFSO.OpenTextFile(logFile, 8, True)
logWriter.WriteLine "[" & Now & "] Quinta-Feira iniciado em background"
logWriter.Close

WScript.Echo "Quinta-Feira iniciado em background. Para parar, use stop_quintafeira.vbs"
