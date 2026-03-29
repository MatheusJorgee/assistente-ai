' ============================================
' QUINTA-FEIRA SILENCIOSA v2.1
' Script invisível para iniciar backend na porta 8080
' ============================================

Dim objShell, strPath, strCmd, objFSO

' Criar objetos
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Obter caminho do script (raiz do projeto)
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Construir comando: pythonw com backend/start_hub.py --port 8080
' pythonw = python sem janela de console
strCmd = "pythonw """ & strPath & "\backend\start_hub.py"" --port 8080"

' Executar INVISÍVEL (0 = Hidden, False = Não esperar)
objShell.Run strCmd, 0, False

' Limpeza
Set objShell = Nothing
Set objFSO = Nothing

' Script termina aqui (sem output)
