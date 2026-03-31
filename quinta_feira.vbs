Set WshShell = CreateObject("WScript.Shell")

' 1. Ligar o Cérebro (Backend Python) nas sombras
WshShell.Run "cmd.exe /c cd /d ""C:\Users\mathe\Documents\assistente-ai\backend"" && ..\.venv\Scripts\activate && python start_hub.py --port 8080", 0, False

' 2. Ligar o Monitor (Frontend Next.js) nas sombras
WshShell.Run "cmd.exe /c cd /d ""C:\Users\mathe\Documents\assistente-ai\frontend"" && npm run dev", 0, False

' 3. Esperar 8 segundos para os dois motores aquecerem
WScript.Sleep 8000

' 4. Abrir a Interface no Chrome (Modo App) apontando para a sua própria máquina
WshShell.Run "chrome.exe --app=http://localhost:3000", 1, False