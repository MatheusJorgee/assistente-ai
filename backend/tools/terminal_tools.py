"""
Ferramentas de Automação para Terminal/PowerShell
Implementa segurança aprimorada com Regex avan\u00e7ado.
"""

import re
import subprocess
import os
import asyncio
from typing import Dict, Any

from backend.core.tool_registry import Tool, ToolMetadata


class TerminalSecurityValidator:
    """
    Validador de segurança para comandos de terminal.
    Usa Regex para identificar padrões destrutivos e perigosos.
    """
    
    def __init__(self, security_profile: str = "trusted-local"):
        self.security_profile = security_profile
        
        # Padrões CRÍTICOS: Comandos destrutivos, persistentes, admin escalation
        self.critical_patterns = [
            # Formatação/Apagamento de disco
            (r"\bformat\b[^a-z]*(?:/fs|/v)?\s+[A-Z]:", "DESTRUIÇÃO DE DISCO"),
            (r"\bdiskpart\b", "Acesso ao gerenciador de disco"),
            (r"\bmkfs\b", "Formatação Linux"),
            (r"\b(?:rmdir|rm)\b\s+/s|--recursive|/r", "Apagamento recursivo"),
            
            # Limpeza de registros/evidências
            (r"\bvssadmin\b.*delete.*shadow", "Apagamento de shadow copies"),
            (r"\bwmic\b.*logicaldisk.*delete", "Apagamento via WMI"),
            (r"\bclear\b.*event\b.*log|eventclear", "Limpeza de event logs"),
            (r"\bGet-EventLog\b.*Remove|Clear-EventLog", "Limpeza PowerShell EventLog"),
            
            # Regedit destrutivo
            (r"\breg\b\s+delete\b", "Dele\u00e7\u00e3o de registro"),
            (r"\bREG\s+DELETE", "DELETE registry"),
            
            # Boot/Recuperação System
            (r"\bbcdedit\b\s+/delete", "Manipula\u00e7\u00e3o BCD"),
            (r"\bbootcfg\b\s+/delete", "Manipula\u00e7\u00e3o boot config"),
            
            # Shutdown/Reboot destrutivo
            (r"\bshutdown\b\s+/(s|p|h)\b", "Shutdown/Hibernation"),
            (r"\reboot\b"," Reboot imediato"),
            
            # Privilegios/UAC Bypass
            (r"\bnet\b\s+user\b.*admin", "Cria\u00e7\u00e3o de user admin"),
            (r"\busermod\b.*-aG\s+sudo", "Escalation de privil\u00e9gio linux"),
            (r"\bsudo\b.*chmod\b.*777", "Permiss\u00f5es abertas root"),
            
            # Code Execution Obfuscation (tentativa de bypass)
            (r"\bpowershell\b.*-enc(?:odedcommand)?", "PowerShell encoded command"),
            (r"\bcmd\b\s+/c.*(?:del|format|diskpart)", "CMD com comando destrutivo"),
            (r"\b(?:invoke-expression|IEX)\b", "Execução dinâmica de código"),
            (r"[\x00-\x1F](?:cmd|powershell)", "Null-byte injection"),
            
            # Ransomware/Cryptolocker indicators
            (r"\b(?:cipher|cipher\.exe)\b\s+/w", "Cipher wipe (Cryptolocker pattern)"),
            (r"\bwbadmin\b\s+delete\b", "Delet backup Windows"),
        ]
        
        # Padrões MÉDIOS: Requerem confirmação ou logging extra
        self.medium_patterns = [
            (r"\bdel\b\s+(?:/f|/s|/q)", "Apagamento com flags possibilidade recursiva"),
            (r"\brm\b\s+(?:-r|-rf|-f)", "Remove recursivo"),
            (r"\binstall\b.*service", "Instala sistema servi\u00e7o"),
            (r"\bnet\b\s+share", "Compartilha de arquivo"),
        ]
        
        # Padrões BAIXO: Apenas logging
        self.low_patterns = [
            (r"\bwhoami\b", "Verificação de usuário"),
            (r"\bwhere\b", "Busca de executável"),
        ]
    
    def classify_command(self, comando: str) -> Dict[str, Any]:
        """
        Classifica um comando por nível de risco.
        
        Returns:
            {
                'risk': 'CRÍTICO' | 'MÉDIO' | 'BAIXO' | 'SEGURO',
                'pattern': str (padrão que correspondeu),
                'reason': str (explicação humana),
                'allowed': bool (deve executar?),
                'needs_confirmation': bool
            }
        """
        cmd_lower = (comando or "").strip().lower()
        
        # Verificar padrões críticos
        for pattern, reason in self.critical_patterns:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return {
                    'risk': 'CRÍTICO',
                    'pattern': pattern,
                    'reason': reason,
                    'allowed': False,
                    'needs_confirmation': False
                }
        
        # Verificar padrões médios
        for pattern, reason in self.medium_patterns:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return {
                    'risk': 'MÉDIO',
                    'pattern': pattern,
                    'reason': reason,
                    'allowed': self.security_profile != 'strict',
                    'needs_confirmation': True
                }
        
        # Verificar padrões baixos (apenas para logging)
        for pattern, reason in self.low_patterns:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return {
                    'risk': 'BAIXO',
                    'pattern': pattern,
                    'reason': reason,
                    'allowed': True,
                    'needs_confirmation': False
                }
        
        # Comando não identificado como perigoso
        return {
            'risk': 'SEGURO',
            'pattern': None,
            'reason': 'Comando padr\u00e3o sem padrões perigosos detectados',
            'allowed': True,
            'needs_confirmation': False
        }


class ExecutarTerminalTool(Tool):
    """
    Ferramenta para executar comandos no terminal (PowerShell/CMD).
    
    Exemplos:
        execute(comando="Get-Process", justificacao="Listar processos")
        execute(comando="ipconfig", justificacao="Verificar IP")
    """
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="terminal",
                description="Executa comandos no PowerShell/CMD do Windows com validação de segurança",
                version="2.0.0",
                tags=["system", "automation", "security"]
            )
        )
        self.security_validator = TerminalSecurityValidator(
            security_profile=os.getenv("QUINTA_SECURITY_PROFILE", "trusted-local")
        )
        self.max_output_lines = 200
    
    def validate_input(self, **kwargs) -> bool:
        """Valida se comando e justificacao estão presentes."""
        return 'comando' in kwargs and 'justificacao' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Executa comando com validação de segurança.
        
        Args:
            comando (str): Comando a executar
            justificacao (str): Motivo/contexto para execução
            
        Returns:
            str: Output do comando ou erro
        """
        comando = kwargs.get('comando', '').strip()
        justificacao = kwargs.get('justificacao', '').strip()
        
        # 1. Validar comando
        validacao = self.security_validator.classify_command(comando)
        
        if not validacao['allowed']:
            msg = f"[BLOQUEADO] {validacao['reason']} (Risco: {validacao['risk']})"
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'command': comando,
                    'risk_level': validacao['risk'],
                    'result': 'BLOQUEADO',
                    'reason': msg
                })
            return msg
        
        if validacao['needs_confirmation']:
            msg = f"[ATENÇÃO] Requer confirma\u00e7\u00e3o: {validacao['reason']} (Risco: {validacao['risk']})"
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'command': comando,
                    'risk_level': validacao['risk'],
                    'result': 'PENDENTE_CONFIRMAÇÃO',
                    'reason': msg
                })
            return msg
        
        # 2. Executar comando
        try:
            resultado = await asyncio.to_thread(
                self._executar_sync,
                comando
            )
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'command': comando,
                    'risk_level': validacao['risk'],
                    'result': 'SUCESSO',
                    'output_lines': resultado.count('\n')
                })
            
            return resultado
            
        except Exception as e:
            error_msg = f"[ERRO] Execução falhou: {str(e)}"
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'command': comando,
                    'risk_level': 'ERRO',
                    'result': 'FALHA',
                    'error': str(e)
                })
            return error_msg
    
    def _executar_sync(self, comando: str) -> str:
        """Executa comando de forma síncrona (para asyncio.to_thread)."""
        try:
            resultado = subprocess.run(
                comando,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ}
            )
            
            # Limitar output para evitar overflow
            output = resultado.stdout or resultado.stderr
            linhas = output.split('\n')
            if len(linhas) > self.max_output_lines:
                truncado = '\n'.join(linhas[:self.max_output_lines])
                truncado += f"\n\n[...truncado {len(linhas) - self.max_output_lines} linhas...]"
                return truncado
            
            return output if output else "[Executado - sem output]"
            
        except subprocess.TimeoutExpired:
            return "[ERRO] Comando demorou mais de 30 segundos (timeout)"
        except Exception as e:
            return f"[ERRO] {str(e)}"


class AprenderemExecutarTool(Tool):
    """
    Ferramenta para aprender novos comandos via Oráculo e executá-los.
    Consulta o modelo de IA para gerar comandos seguros para objetivos desconhecidos.
    """
    
    def __init__(self, oraculo_engine=None, database=None):
        super().__init__(
            metadata=ToolMetadata(
                name="aprender_executar",
                description="Consulta Oráculo para aprender comando desconhecido, valida e executa",
                version="2.0.0",
                tags=["learning", "automation", "system"]
            )
        )
        self.oraculo = oraculo_engine
        self.db = database
        self.terminal_tool = ExecutarTerminalTool()
    
    def validate_input(self, **kwargs) -> bool:
        """Valida objetivo e ambiente."""
        return 'objetivo' in kwargs and 'ambiente' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Aprende do Oráculo, guarda em cache e executa.
        
        Args:
            objetivo (str): O que você quer fazer
            ambiente (str): "Windows PowerShell" ou similar
            
        Returns:
            str: Resultado da execução
        """
        if not self.oraculo or not self.db:
            return "[ERRO] Oráculo ou Database não injetados"
        
        objetivo = kwargs.get('objetivo', '').strip()
        ambiente = kwargs.get('ambiente', 'Windows PowerShell').strip()
        
        if self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'consulting_oracle',
                'objective': objetivo
            })
        
        # Consultar Oráculo
        conhecimento = await asyncio.to_thread(
            self.oraculo.consultar_comando_tecnico,
            objetivo,
            ambiente
        )
        
        comando = conhecimento.get("comando_exato", "")
        risco = conhecimento.get("risco", "ALTO")
        
        if not comando:
            return f"[ERRO] Oráculo não conseguiu gerar comando para: {objetivo}"
        
        if risco == "ALTO":
            msg = f"[AVISO] Oráculo gerou comando com risco ALTO. Requer permissão explícita antes de executar."
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'high_risk_detected',
                    'command': comando
                })
            return msg
        
        # Guardar na cache
        try:
            self.db.salvar_habilidade(objetivo, ambiente, comando)
        except:
            pass  # Falha silenciosa se DB não estiver pronto
        
        # Executar usando a terminal tool
        return await self.terminal_tool.safe_execute(
            comando=comando,
            justificacao=f"Execução autônoma pós-aprendizado: {objetivo}"
        )
