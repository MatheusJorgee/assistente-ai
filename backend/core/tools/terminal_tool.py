"""
Terminal Tool - Executar comandos PowerShell/Bash com seguranÃ§a.
"""

import asyncio
import sys
from typing import Optional

try:
    from core.tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from core.tools.security import get_security_validator
    from core import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .security import get_security_validator
    from core import get_logger

logger = get_logger(__name__)


class TerminalTool(MotorTool):
    """Ferramenta para executar comandos no terminal."""
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="executar_terminal",
                description="Executa comando no terminal (PowerShell/Bash)",
                category="terminal",
                parameters=[
                    ToolParameter(
                        name="comando",
                        type="string",
                        description="Comando PowerShell/Bash a executar",
                        required=True
                    ),
                    ToolParameter(
                        name="timeout",
                        type="int",
                        description="Timeout em segundos (default 30)",
                        required=False,
                        default=30
                    ),
                ],
                examples=[
                    "Get-Process",
                    "dir c:\\users",
                    "ls -la /tmp",
                    "echo 'OlÃ¡, Mundo!'"
                ],
                security_level=SecurityLevel.CRITICAL,
                tags=["automation", "ejecute", "shell"]
            )
        )
        self.security = get_security_validator()
    
    def validate_input(self, **kwargs) -> bool:
        """Valida se comando foi fornecido."""
        return "comando" in kwargs and isinstance(kwargs["comando"], str)
    
    async def execute(self, **kwargs) -> str:
        """Executa comando com validaÃ§Ã£o de seguranÃ§a."""
        comando = kwargs["comando"].strip()
        timeout = kwargs.get("timeout", 30)
        
        if not comando:
            raise ValueError("Comando nÃ£o pode estar vazio")
        
        # 1. ValidaÃ§Ã£o de seguranÃ§a
        security_check = self.security.validate(comando)
        
        if not security_check.allowed and security_check.action.value == "deny":
            return f"[POLICY_BLOCKED] Comando bloqueado por seguranÃ§a: {security_check.reason}"
        
        # 2. Selecionar shell baseado no SO
        if sys.platform == "win32":
            shell = "powershell"
            shell_args = ["-NoProfile", "-Command"]
        else:
            shell = "/bin/bash"
            shell_args = ["-c"]
        
        # 3. Executar com timeout
        try:
            if sys.platform == "win32":
                # PowerShell no Windows
                process = await asyncio.create_subprocess_exec(
                    shell,
                    *shell_args,
                    comando,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                # Bash no Linux/macOS
                process = await asyncio.create_subprocess_shell(
                    comando,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            # Aguardar conclusÃ£o
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')
            
            if error_output:
                return f"STDOUT:\n{output}\n\nSTDERR:\n{error_output}"
            
            return output if output else "(sem saÃ­da)"
        
        except asyncio.TimeoutError:
            raise RuntimeError(f"Timeout apÃ³s {timeout}s: {comando}")
        except Exception as e:
            raise RuntimeError(f"Erro ao executar: {str(e)}")

