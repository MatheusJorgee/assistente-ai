' ============================================================
' QUINTA-FEIRA v2.1 - AUTO-START COMPLETO
' VBScript para iniciar Backend + Chrome (Modo App)
' ============================================================

Option Explicit
Dim objShell, objFSO, strProjectRoot, strBackendPath, strChromePath
Dim strBackendCmd, aChromeLocations, i, strChromeCmd

' Criar objetos
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' ============ DEFINIR CAMINHOS ============
strProjectRoot = objFSO.GetParentFolderName(WScript.ScriptFullName)
strBackendPath = strProjectRoot & "\backend"

' Tentar encontrar Chrome em caminhos comuns
aChromeLocations = Array( _
    "C:\Program Files\Google\Chrome\Application\chrome.exe", _
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", _
    "C:\Program Files\Chromium\Application\chrome.exe" _
)

' Procurar Chrome
strChromePath = ""
For i = 0 To UBound(aChromeLocations)
    If objFSO.FileExists(aChromeLocations(i)) Then
        strChromePath = aChromeLocations(i)
        Exit For
    End If
Next

' Se Chrome não encontrado, usar via PATH (fallback)
If strChromePath = "" Then
    strChromePath = "chrome.exe"
End If

' ============ VALIDAÇÕES ============
If Not objFSO.FileExists(strBackendPath & "\start_hub.py") Then
    msgbox "ERRO: Ficheiro backend/start_hub.py não encontrado!" & vbCrLf & _
           "Caminho esperado: " & strBackendPath & "\start_hub.py", , "Quinta-Feira - ERRO"
    WScript.Quit(1)
End If

' ============ EXECUTAR BACKEND (INVISÍVEL) ============
strBackendCmd = "pythonw """ & strBackendPath & "\start_hub.py"" --port 8080"
objShell.Run strBackendCmd, 0, False

' ============ AGUARDAR 3 SEGUNDOS ============
WScript.Sleep(3000)

' ============ ABRIR CHROME EM MODO APP ============
strChromeCmd = """" & strChromePath & """ --app=https://quinta-feira-l9v469mdf-matheusjorgees-projects.vercel.app --profile-directory=Default"
objShell.Run strChromeCmd, 1, False