' ============================================================
' QUINTA-FEIRA v2.1 - AUTO-START COMPLETO
' VBScript para iniciar Backend + Chrome (Modo App)
' ============================================================
' 
' Função: 
'   1. Iniciar Backend silenciosamente na porta 8080
'   2. Aguardar 3 segundos
'   3. Abrir Chrome em modo APP mostrando http://localhost:3000
'
' Instalação: Win+R → shell:startup → Colar este ficheiro
' ============================================================

Option Explicit
Dim objShell, objFSO, strProjectRoot, strBackendPath, strChromePath
Dim strBackendCmd, objWshProcessEnv

' Criar objetos
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' ============ DEFINIR CAMINHOS ============
strProjectRoot = objFSO.GetParentFolderName(WScript.ScriptFullName)
strBackendPath = strProjectRoot & "\backend"

' Tentar encontrar Chrome em caminhos comuns
Dim aChromeLocations, i, strChromePath
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
' Verificar se backend/start_hub.py existe
If Not objFSO.FileExists(strBackendPath & "\start_hub.py") Then
    msgbox "ERRO: Ficheiro backend/start_hub.py não encontrado!" & vbCrLf & _
           "Caminho esperado: " & strBackendPath & "\start_hub.py", , "Quinta-Feira - ERRO"
    WScript.Quit(1)
End If

' ============ EXECUTAR BACKEND (INVISÍVEL) ============
' Comando: pythonw backend/start_hub.py --port 8080
' (pythonw executa sem janela de console)
strBackendCmd = "pythonw """ & strBackendPath & "\start_hub.py"" --port 8080"

' Executar invisível (0 = Hidden, False = não esperar)
objShell.Run strBackendCmd, 0, False

' ============ AGUARDAR 3 SEGUNDOS ============
' Dar tempo ao Uvicorn ligar e estar pronto
WScript.Sleep(3000)

' ============ ABRIR CHROME EM MODO APP ============
' Comando: chrome.exe --app=http://localhost:3000
' Isto abre Chrome sem barra de endereços, abas, ou outras UI
' Comporta-se como uma aplicação nativa

Dim strChromeCmd
strChromeCmd = """" & strChromePath & """ --app=http://localhost:3000 --profile-directory=Default"

' Executar Chrome (1 = Normal window, False = não esperar)
objShell.Run strChromeCmd, 1, False

' ============ FIM ============
' Script termina aqui
' Backend continua rodando em background
' Chrome fica aberto no modo app

' Notas para Utilizador:
' - Para trocar localhost por URL de nuvem (Vercel):
'   Mudar: http://localhost:3000
'   Para: https://seu-app.vercel.app
' - Backend continua rodando mesmo depois de fechar Chrome
' - Para parar: taskkill /F /IM python.exe (terminal)
