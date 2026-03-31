
    def controlar_energia(self, acao: str, delay: int = 10, **kwargs) -> str:
        """Controla energia do sistema: shutdown, restart, sleep. Absorve parâmetros extra do Gemini.
        
        Args:
            acao (str): 'shutdown' (desligar), 'restart' (reiniciar), 'sleep' (suspender)
            delay (int): Segundos para aguardar antes de executar (padrão: 10)
            
        Returns:
            str: Mensagem de resultado
        """
        acao_lower = acao.lower().strip()
        
        # Normalizar comandos
        if acao_lower in ['desligar', 'shutdown', 'shudown', 'deslizar']:
            acao_normalizada = 'shutdown'
            msg_user = f"Computador será desligado em {delay} segundos."
        elif acao_lower in ['reiniciar', 'restart', 'reboot', 're-iniciar']:
            acao_normalizada = 'restart'
            msg_user = f"Computador será reiniciado em {delay} segundos."
        elif acao_lower in ['dormir', 'sleep', 'suspender', 'hibernar', 'dormer']:
            acao_normalizada = 'sleep'
            msg_user = "Computador entrando em modo de suspensão."
        else:
            return f"Ação desconhecida: '{acao}'. Use: desligar (shutdown), reiniciar (restart), ou dormir (sleep)."
        
        try:
            sistema = os.name
            
            if sistema == 'nt':  # Windows
                if acao_normalizada == 'shutdown':
                    os.system(f'shutdown /s /t {delay}')
                elif acao_normalizada == 'restart':
                    os.system(f'shutdown /r /t {delay}')
                else:  # sleep
                    os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
            
            else:  # Linux/Mac
                if acao_normalizada == 'shutdown':
                    os.system(f'shutdown -h +{delay // 60}')
                elif acao_normalizada == 'restart':
                    os.system(f'shutdown -r +{delay // 60}')
                else:  # sleep
                    os.system('systemctl suspend')
            
            print(f">>> [ENERGIA] {msg_user}")
            return msg_user
            
        except Exception as e:
            return f"Erro ao executar controle de energia: {str(e)}"
