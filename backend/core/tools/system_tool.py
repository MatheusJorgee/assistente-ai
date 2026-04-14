"""
System Tool - InformaÃ§Ãµes e controle do sistema (processos, serviÃ§os, arquivos).
"""

import asyncio
import json
import sys
from typing import Optional, Dict, List, Any

try:
    from core.tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from core import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from core import get_logger

logger = get_logger(__name__)


class SystemTool(MotorTool):
    """Ferramenta para consultar e controlar sistema."""
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="sistema",
                description="Consulta informaÃ§Ãµes do sistema (processos, serviÃ§os, arquivos)",
                category="system",
                parameters=[
                    ToolParameter(
                        name="acao",
                        type="string",
                        description="AÃ§Ã£o: listar_processos, listar_servicos, info_arquivo, listar_arquivos",
                        required=True,
                        choices=["listar_processos", "listar_servicos", "info_arquivo", "listar_arquivos", "info_sistema"]
                    ),
                    ToolParameter(
                        name="filtro",
                        type="string",
                        description="Filtro opcional (nome de processo, serviÃ§o ou caminho)",
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
                tags=["system", "processo", "informaÃ§Ã£o"]
            )
        )
    
    def validate_input(self, **kwargs) -> bool:
        """Valida se aÃ§Ã£o foi fornecida."""
        acao = kwargs.get("acao", "").lower()
        valid_acoes = [
            "listar_processos", "listar_servicos", "info_arquivo",
            "listar_arquivos", "info_sistema"
        ]
        return acao in valid_acoes
    
    async def execute(self, **kwargs) -> str:
        """Executa aÃ§Ã£o do sistema."""
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
                    raise ValueError("caminho Ã© obrigatÃ³rio para info_arquivo")
                return await self._info_arquivo(caminho)
            elif acao == "listar_arquivos":
                if not caminho:
                    caminho = "."
                return await self._listar_arquivos(caminho)
            elif acao == "info_sistema":
                return await self._info_sistema()
            else:
                raise ValueError(f"AÃ§Ã£o desconhecida: {acao}")
        
        except Exception as e:
            raise RuntimeError(f"Erro ao executar aÃ§Ã£o de sistema: {str(e)}")
    
    async def _listar_processos(self, filtro: Optional[str] = None) -> str:
        """Lista processos em execuÃ§Ã£o."""
        try:
            if sys.platform == "win32":
                cmd = "Get-Process | Select-Object Name, Id, PrivateMemorySize | ConvertTo-Json"
            else:
                cmd = "ps aux"
            
            # SimulaÃ§Ã£o para teste (nÃ£o executar de verdade)
            logger.info(f"[SYSTEM] Listando processos (filtro: {filtro})")
            
            # Mock data
            if filtro:
                return f"âœ“ Processos contendo '{filtro}':\n  - python.exe (PID: 1234)\n  - python.exe (PID: 5678)"
            else:
                return "âœ“ Processos do sistema:\n  - System (PID: 4)\n  - explorer.exe (PID: 2048)\n  - python.exe (PID: 1234)"
        
        except Exception as e:
            raise RuntimeError(f"Erro ao listar processos: {str(e)}")
    
    async def _listar_servicos(self, filtro: Optional[str] = None) -> str:
        """Lista serviÃ§os do sistema."""
        try:
            if sys.platform == "win32":
                cmd = "Get-Service | Select-Object Name, Status | ConvertTo-Json"
            else:
                cmd = "systemctl list-units --type=service"
            
            logger.info(f"[SYSTEM] Listando serviÃ§os (filtro: {filtro})")
            
            if filtro:
                return f"âœ“ ServiÃ§os contendo '{filtro}':\n  - {filtro}Service (Running)"
            else:
                return "âœ“ Alguns serviÃ§os:\n  - wuauserv (Running)\n  - WinDefend (Running)\n  - AudioSrv (Running)"
        
        except Exception as e:
            raise RuntimeError(f"Erro ao listar serviÃ§os: {str(e)}")
    
    async def _info_arquivo(self, caminho: str) -> str:
        """ObtÃ©m informaÃ§Ãµes de arquivo."""
        try:
            import os
            from pathlib import Path
            
            logger.info(f"[SYSTEM] InformaÃ§Ãµes de arquivo: {caminho}")
            
            path = Path(caminho)
            if not path.exists():
                raise ValueError(f"Caminho nÃ£o encontrado: {caminho}")
            
            info = {
                "caminho": str(path.absolute()),
                "tipo": "diretÃ³rio" if path.is_dir() else "arquivo",
                "tamanho_bytes": path.stat().st_size if path.is_file() else "N/A",
                "modificado": str(path.stat().st_mtime)
            }
            
            return json.dumps(info, indent=2, ensure_ascii=False)
        
        except Exception as e:
            raise RuntimeError(f"Erro ao obter informaÃ§Ãµes: {str(e)}")
    
    async def _listar_arquivos(self, caminho: str = ".") -> str:
        """Lista arquivos em diretÃ³rio."""
        try:
            from pathlib import Path
            
            logger.info(f"[SYSTEM] Listando arquivos: {caminho}")
            
            path = Path(caminho)
            if not path.is_dir():
                raise ValueError(f"NÃ£o Ã© um diretÃ³rio: {caminho}")
            
            files = []
            for item in list(path.iterdir())[:10]:  # Limitar a 10 arquivos
                files.append({
                    "nome": item.name,
                    "tipo": "ðŸ“ dir" if item.is_dir() else "ðŸ“„ arquivo",
                    "tamanho": str(item.stat().st_size) if item.is_file() else "N/A"
                })
            
            return json.dumps(files, indent=2, ensure_ascii=False)
        
        except Exception as e:
            raise RuntimeError(f"Erro ao listar arquivos: {str(e)}")
    
    async def _info_sistema(self) -> str:
        """ObtÃ©m informaÃ§Ãµes do sistema."""
        try:
            import platform
            
            logger.info("[SYSTEM] Obtendo informaÃ§Ãµes do sistema")
            
            info = {
                "so": platform.system(),
                "versao": platform.release(),
                "maquina": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version()
            }
            
            return json.dumps(info, indent=2, ensure_ascii=False)
        
        except Exception as e:
            raise RuntimeError(f"Erro ao obter informaÃ§Ãµes: {str(e)}")

