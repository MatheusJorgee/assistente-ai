"""
Terminal Security Validator - ValidaÃ§Ã£o de comandos antes de executar.

SeguranÃ§a em mÃºltiplas camadas:
1. Bloqueio de padrÃµes perigosos (regex)
2. Whitelist de comandos permitidos
3. Logging de tentativas suspeitas
"""

import re
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


class SecurityAction(Enum):
    """Action apÃ³s anÃ¡lise de seguranÃ§a."""
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


@dataclass
class SecurityCheckResult:
    """Resultado de uma verificaÃ§Ã£o de seguranÃ§a."""
    allowed: bool
    action: SecurityAction
    reason: str
    risk_level: str  # "low", "medium", "high", "critical"


class TerminalSecurityValidator:
    """
    Validador de seguranÃ§a para comandos terminais.
    
    EstratÃ©gia: Lista negra de padrÃµes perigosos + Lista branca de permitidos.
    """
    
    # PadrÃµes CRÃTICOS - absolutamente bloqueados
    CRITICAL_PATTERNS = [
        # DestruiÃ§Ã£o de dados
        r"(?i)^del\s+/s\s+/f",          # del /s /f C:\
        r"(?i)^rm\s+-rf\s+/",           # rm -rf /
        r"(?i)format\s+\w:",            # format C:
        
        # Shutdown/Reboot
        r"(?i)^shutdown",
        r"(?i)^restart",
        r"(?i)\|.*shutdown",
        r"(?i)\|.*restart",
        
        # EscalaÃ§Ã£o de privilÃ©gio
        r"(?i)runas",
        r"(?i)psexec",
        r"(?i)sudo\s+",
        
        # AlteraÃ§Ã£o de registros perigosos
        r"(?i)reg\s+add.*\bdisable",
        r"(?i)reg\s+add.*\bfirewall",
        
        # Scripts remotos perigosos
        r"(?i)powershell\s+.*\s+iex",   # Invoke-Expression
        r"(?i)powershell\s+.*-enc",     # Encoded scripts
        
        # Remover logs/auditoria
        r"(?i)clear\s+eventlog",
        r"(?i)wevtutil\s+clear",
    ]
    
    # PadrÃµes MÃ‰DIOS - requerem confirmaÃ§Ã£o
    MEDIUM_PATTERNS = [
        # OperaÃ§Ãµes em lote
        r"(?i)del\s+/s",
        r"(?i)rmdir\s+/s",
        
        # AlteraÃ§Ã£o de permissÃµes
        r"(?i)icacls",
        r"(?i)chmod\s+777",
        
        # InstalaÃ§Ã£o de serviÃ§os
        r"(?i)sc\s+create",
        r"(?i)sc\s+start",
        
        # ModificaÃ§Ã£o de firewall
        r"(?i)netsh\s+advfirewall",
        
        # Network operations perigosas
        r"(?i)route\s+add",
    ]
    
    # Whitelist de comandos SEMPRE permitidos
    WHITELIST = [
        r"(?i)^cd\s+",
        r"(?i)^dir\s*$",
        r"(?i)^ls\s*$",
        r"(?i)^pwd\s*$",
        r"(?i)^echo\s+",
        r"(?i)^whoami\s*$",
        r"(?i)^date\s*$",
        r"(?i)^time\s*$",
        r"(?i)^Get-ChildItem",
        r"(?i)^Get-Process",
        r"(?i)^Get-Service",
        r"(?i)^Get-Content",
        r"(?i)^Select-String",
        r"(?i)^where-object",
    ]
    
    def __init__(self, mode: str = "strict"):
        """
        Inicializa validador.
        
        Args:
            mode: "strict" (produÃ§Ã£o) ou "trusted-local" (dev)
        """
        self.mode = mode
        self._violation_count = {}
    
    def validate(self, command: str) -> SecurityCheckResult:
        """
        Valida um comando antes de executar.
        
        Retorna SecurityCheckResult com decisÃ£o e motivo.
        """
        command = command.strip()
        
        if not command:
            return SecurityCheckResult(
                allowed=False,
                action=SecurityAction.DENY,
                reason="Comando vazio",
                risk_level="low"
            )
        
        # 1. Verificar whitelist (permissÃ£o rÃ¡pida)
        for pattern in self.WHITELIST:
            if re.match(pattern, command):
                logger.debug(f"[SECURITY] âœ“ Whitelist: {command[:50]}")
                return SecurityCheckResult(
                    allowed=True,
                    action=SecurityAction.ALLOW,
                    reason="Comando na whitelist",
                    risk_level="low"
                )
        
        # 2. Verificar padrÃµes CRÃTICOS
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, command):
                risk_reason = f"PadrÃ£o crÃ­tico detectado: {pattern}"
                logger.warning(f"[SECURITY] âŒ CRÃTICO: {command[:50]} | {risk_reason}")
                self._increment_violation(command)
                
                return SecurityCheckResult(
                    allowed=False,
                    action=SecurityAction.DENY,
                    reason=risk_reason,
                    risk_level="critical"
                )
        
        # 3. Verificar padrÃµes MÃ‰DIOS
        for pattern in self.MEDIUM_PATTERNS:
            if re.search(pattern, command):
                if self.mode == "strict":
                    reason = f"PadrÃ£o mÃ©dio detectado (strict mode): {pattern}"
                    logger.warning(f"[SECURITY] âš ï¸  MÃ‰DIO (bloqueado): {command[:50]}")
                    self._increment_violation(command)
                    
                    return SecurityCheckResult(
                        allowed=False,
                        action=SecurityAction.DENY,
                        reason=reason,
                        risk_level="medium"
                    )
                else:
                    reason = f"PadrÃ£o mÃ©dio detectado (requer confirmaÃ§Ã£o): {pattern}"
                    logger.warning(f"[SECURITY] âš ï¸  MÃ‰DIO (prompt): {command[:50]}")
                    
                    return SecurityCheckResult(
                        allowed=True,  # Ã‰ permitido, mas com prompt
                        action=SecurityAction.PROMPT,
                        reason=reason,
                        risk_level="medium"
                    )
        
        # 4. Se passou em todas as verificaÃ§Ãµes
        logger.debug(f"[SECURITY] âœ“ Comando ok: {command[:50]}")
        return SecurityCheckResult(
            allowed=True,
            action=SecurityAction.ALLOW,
            reason="Comando passou em todas as verificaÃ§Ãµes",
            risk_level="low"
        )
    
    def _increment_violation(self, command: str) -> None:
        """Incrementa contador de violaÃ§Ãµes para rate-limiting."""
        prefix = command.split()[0] if command else "unknown"
        self._violation_count[prefix] = self._violation_count.get(prefix, 0) + 1
    
    def get_violation_stats(self) -> Dict[str, int]:
        """Retorna estatÃ­sticas de violaÃ§Ãµes detectadas."""
        return self._violation_count.copy()
    
    def reset_violations(self) -> None:
        """Reseta contador de violaÃ§Ãµes."""
        self._violation_count.clear()


# Singleton global
_validator = None

def get_security_validator(mode: str = "strict") -> TerminalSecurityValidator:
    """Factory para obter validador de seguranÃ§a."""
    global _validator
    if _validator is None:
        _validator = TerminalSecurityValidator(mode=mode)
    return _validator

