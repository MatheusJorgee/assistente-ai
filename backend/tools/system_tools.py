"""
Ferramenta de Controle de Energia: Desligar, Reiniciar, Dormir
"""

import asyncio
import os
import subprocess
from typing import Dict, Any

try:
    from backend.core.tool_registry import Tool, ToolMetadata
except ModuleNotFoundError:
    from core.tool_registry import Tool, ToolMetadata


class SystemPowerControlTool(Tool):
    """
    Ferramenta para controlar energia do sistema: desligar (shutdown),
    reiniciar (restart) ou suspender (sleep).
    """
    
    def __init__(self, power_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="system_power_control",
                description="Controla energia do sistema: shutdown (desligar), restart (reiniciar), sleep (suspender)",
                version="1.0.0",
                tags=["system", "power", "control"]
            )
        )
        self.power_controller = power_controller
    
    def validate_input(self, **kwargs) -> bool:
        """Valida se tem o comando de energia."""
        acao = kwargs.get('acao', '').strip().lower()
        return acao in ['shutdown', 'restart', 'sleep', 'desligar', 'reiniciar', 'dormir', 'suspender']
    
    async def execute(self, **kwargs) -> str:
        """
        Executa comando de controle de energia.
        
        Args:
            acao (str): 'shutdown' (desligar), 'restart' (reiniciar), 'sleep' (suspender)
            delay (int): Segundos para aguardar antes de executar (opcional, padrão: 10)
            
        Returns:
            str: Resultado da ação
        """
        if not self.power_controller:
            # Fallback: usar função nativa se não houver controller externo
            return await self._executar_nativo(**kwargs)
        
        try:
            result = await asyncio.to_thread(
                self.power_controller,
                kwargs.get('acao', 'shutdown'),
                kwargs.get('delay', 10)
            )
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'system_power_control',
                    'command': kwargs.get('acao'),
                    'delay': kwargs.get('delay', 10),
                    'result': 'SUCESSO'
                })
            
            return result
            
        except Exception as e:
            return f"[ERRO Power Control] {str(e)}"
    
    async def _executar_nativo(self, **kwargs) -> str:
        """Executa comando de energia usando comandos nativos do SO."""
        acao = kwargs.get('acao', 'shutdown').strip().lower()
        delay = kwargs.get('delay', 10)
        
        # Normalizar ação
        if acao in ['desligar', 'shutdown']:
            acao_normalizada = 'shutdown'
        elif acao in ['reiniciar', 'restart']:
            acao_normalizada = 'restart'
        elif acao in ['dormir', 'suspender', 'sleep']:
            acao_normalizada = 'sleep'
        else:
            return f"Ação desconhecida: {acao}. Use: shutdown, restart, ou sleep."
        
        try:
            # Detectar SO
            sistema = os.name
            
            if sistema == 'nt':  # Windows
                if acao_normalizada == 'shutdown':
                    cmd = f'shutdown /s /t {delay}'
                    msg = f"Computador será desligado em {delay} segundos."
                elif acao_normalizada == 'restart':
                    cmd = f'shutdown /r /t {delay}'
                    msg = f"Computador será reiniciado em {delay} segundos."
                else:  # sleep
                    cmd = 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0'
                    msg = "Computador entrando em modo de suspensão."
            
            else:  # Linux/Mac
                if acao_normalizada == 'shutdown':
                    cmd = f'shutdown -h +{delay // 60}'
                    msg = f"Computador será desligado em {delay} segundos."
                elif acao_normalizada == 'restart':
                    cmd = f'shutdown -r +{delay // 60}'
                    msg = f"Computador será reiniciado em {delay} segundos."
                else:  # sleep
                    cmd = 'systemctl suspend'
                    msg = "Computador entrando em modo de suspensão."
            
            # Executar comando
            await asyncio.to_thread(
                subprocess.run,
                cmd,
                shell=True,
                capture_output=True,
                timeout=5
            )
            
            print(f">>> [POWER] {msg}")
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'power_control',
                    'command': acao_normalizada,
                    'system': sistema,
                    'result': 'SUCESSO'
                })
            
            return msg
            
        except Exception as e:
            return f"Erro ao executar comando de energia: {str(e)}"
