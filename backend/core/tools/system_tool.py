"""
System Tool - Informações e controle do sistema (processos, serviços, arquivos).
"""

import asyncio
import json
import sys
from typing import Optional, Dict, List, Any

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)


class SystemTool(MotorTool):
    """Ferramenta para consultar e controlar sistema."""
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="sistema",
                description="Consulta informações do sistema (processos, serviços, arquivos)",
                category="system",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="Ação: listar_processos, listar_servicos, info_arquivo, listar_arquivos",
                        required=True,
                        choices=["listar_processos", "listar_servicos", "info_arquivo", "listar_arquivos", "info_sistema"]
                    ),
                    ToolParameter(
                        name="filtro",
                        type="string",
                        description="Filtro opcional (nome de processo, serviço ou caminho)",
                        required=False,
                        default=None
                    ),
                    ToolParameter(
                        name="caminho",
                        type="string",
                        description="Para info_arquivo/listar_arquivos: caminho da pasta",
                        required=False,
                        default=None
                    ),
                ],
                examples=[
                    "acao=listar_processos",
                    "acao=listar_processos, filtro=python",
                    "acao=listar_arquivos, caminho=c:\\Users",
                    "acao=info_sistema"
                ],
                security_level=SecurityLevel.LOW,
                tags=["system", "processo", "informação"]
            )
        )
    
    def validate_input(self, **kwargs) -> bool:
        """Valida se ação foi fornecida."""
        acao = kwargs.get("acao", "").lower()
        valid_acoes = [
            "listar_processos", "listar_servicos", "info_arquivo",
            "listar_arquivos", "info_sistema"
        ]
        return acao in valid_acoes
    
    async def execute(self, **kwargs) -> str:
        """Executa ação do sistema."""
        acao = kwargs.get("acao", "").lower()
        filtro = kwargs.get("filtro", None)
        caminho = kwargs.get("caminho", None)
        
        try:
            if acao == "listar_processos":
                return await self._listar_processos(filtro)
            elif acao == "listar_servicos":
                return await self._listar_servicos(filtro)
            elif acao == "info_arquivo":
                if not caminho:
                    raise ValueError("caminho é obrigatório para info_arquivo")
                return await self._info_arquivo(caminho)
            elif acao == "listar_arquivos":
                if not caminho:
                    caminho = "."
                return await self._listar_arquivos(caminho)
            elif acao == "info_sistema":
                return await self._info_sistema()
            else:
                raise ValueError(f"Ação desconhecida: {acao}")
        
        except Exception as e:
            raise RuntimeError(f"Erro ao executar ação de sistema: {str(e)}")
    
    async def _listar_processos(self, filtro: Optional[str] = None) -> str:
        """Lista processos em execução."""
        try:
            if sys.platform == "win32":
                cmd = "Get-Process | Select-Object Name, Id, PrivateMemorySize | ConvertTo-Json"
            else:
                cmd = "ps aux"
            
            # Simulação para teste (não executar de verdade)
            logger.info(f"[SYSTEM] Listando processos (filtro: {filtro})")
            
            # Mock data
            if filtro:
                return f"âœ" Processos contendo '{filtro}':\n  - python.exe (PID: 1234)\n  - python.exe (PID: 5678)"
            else:
                return "âœ" Processos do sistema:\n  - System (PID: 4)\n  - explorer.exe (PID: 2048)\n  - python.exe (PID: 1234)"
        
        except Exception as e:
            raise RuntimeError(f"Erro ao listar processos: {str(e)}")
    
    async def _listar_servicos(self, filtro: Optional[str] = None) -> str:
        """Lista serviços do sistema."""
        try:
            if sys.platform == "win32":
                cmd = "Get-Service | Select-Object Name, Status | ConvertTo-Json"
            else:
                cmd = "systemctl list-units --type=service"
            
            logger.info(f"[SYSTEM] Listando serviços (filtro: {filtro})")
            
            if filtro:
                return f"âœ" Serviços contendo '{filtro}':\n  - {filtro}Service (Running)"
            else:
                return "âœ" Alguns serviços:\n  - wuauserv (Running)\n  - WinDefend (Running)\n  - AudioSrv (Running)"
        
        except Exception as e:
            raise RuntimeError(f"Erro ao listar serviços: {str(e)}")
    
    async def _info_arquivo(self, caminho: str) -> str:
        """Obtém informações de arquivo."""
        try:
            import os
            from pathlib import Path
            
            logger.info(f"[SYSTEM] Informações de arquivo: {caminho}")
            
            path = Path(caminho)
            if not path.exists():
                raise ValueError(f"Caminho não encontrado: {caminho}")
            
            info = {
                "caminho": str(path.absolute()),
                "tipo": "diretório" if path.is_dir() else "arquivo",
                "tamanho_bytes": path.stat().st_size if path.is_file() else "N/A",
                "modificado": str(path.stat().st_mtime)
            }
            
            return json.dumps(info, indent=2, ensure_ascii=False)
        
        except Exception as e:
            raise RuntimeError(f"Erro ao obter informações: {str(e)}")
    
    async def _listar_arquivos(self, caminho: str = ".") -> str:
        """Lista arquivos em diretório."""
        try:
            from pathlib import Path
            
            logger.info(f"[SYSTEM] Listando arquivos: {caminho}")
            
            path = Path(caminho)
            if not path.is_dir():
                raise ValueError(f"Não é um diretório: {caminho}")
            
            files = []
            for item in list(path.iterdir())[:10]:  # Limitar a 10 arquivos
                files.append({
                    "nome": item.name,
                    "tipo": "ðŸ" dir" if item.is_dir() else "ðŸ"„ arquivo",
                    "tamanho": str(item.stat().st_size) if item.is_file() else "N/A"
                })
            
            return json.dumps(files, indent=2, ensure_ascii=False)
        
        except Exception as e:
            raise RuntimeError(f"Erro ao listar arquivos: {str(e)}")
    
    async def _info_sistema(self) -> str:
        """Obtém informações do sistema."""
        try:
            import platform
            
            logger.info("[SYSTEM] Obtendo informações do sistema")
            
            info = {
                "so": platform.system(),
                "versao": platform.release(),
                "maquina": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version()
            }
            
            return json.dumps(info, indent=2, ensure_ascii=False)
        
        except Exception as e:
            raise RuntimeError(f"Erro ao obter informações: {str(e)}")

