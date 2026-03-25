import subprocess

class AndroidBridge:
    def _executar_adb_shell(self, comando: str):
        # GARANTE QUE O TEU CAMINHO ESTÁ CORRETO AQUI
        ADB_PATH = r"C:\Users\mathe\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe" 
        
        print(f"\n>>> [LOG TÁTICO ADB] Comando: {comando}")
        
        try:
            cmd_partes = comando.split()
            if not cmd_partes:
                return "Falha no Android: comando vazio."

            if cmd_partes[0].lower() == "adb":
                cmd_partes = cmd_partes[1:]

            if not cmd_partes:
                return "Falha no Android: comando ADB inválido."

            # Somente subcomandos necessários para reduzir superfície de ataque.
            subcomandos_permitidos = {"shell", "devices", "start-server", "kill-server"}
            if cmd_partes[0].lower() not in subcomandos_permitidos:
                return "Falha no Android: subcomando ADB não permitido."

            comando_limpo = " ".join(cmd_partes).lower()
            bloqueados = [" rm ", "reboot", "wipe", "format", "mkfs", ";", "&&", "||", "|", "`"]
            if any(token in f" {comando_limpo} " for token in bloqueados):
                return "Falha no Android: comando bloqueado por política de segurança."
            
            execucao = [ADB_PATH] + cmd_partes
            resultado = subprocess.run(execucao, capture_output=True, text=True, timeout=15)
            
            # Se o Android responder algo, vamos ver no terminal preto do PC
            if resultado.stdout: print(f">>> [RESPOSTA ANDROID]: {resultado.stdout}")
            if resultado.stderr: print(f">>> [ERRO ANDROID]: {resultado.stderr}")

            if resultado.returncode == 0:
                return f"Comando enviado. Resposta do sistema: {resultado.stdout}"
            else:
                return f"Falha no Android: {resultado.stderr}"
                
        except Exception as e:
            print(f">>> [FALHA NO MOTOR]: {str(e)}")
            return f"Erro físico: {str(e)}"