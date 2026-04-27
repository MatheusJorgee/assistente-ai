"""
Logger.py: Setup Centralizado de Logging
==========================================

Padrão: Singleton + Factory

Responsabilidade:
- Configurar logging unificado para todo o backend
- Silenciar bibliotecas ruidosas (google.genai, urllib3, etc)
- Apenas INFO+ para código próprio, WARNING+ para libs externas
- Formato consistente com timestamps e níveis

Uso:
    from .logger import get_logger
    logger = get_logger(__name__)
    logger.info("Mensagem")
"""

import logging
import sys
from typing import Optional


class LoggerFactory:
    """Factory para criar loggers com configuração consistente."""
    
    _configured = False
    
    @classmethod
    def configure_root_logger(
        cls,
        log_level: str = "INFO",
        log_format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ) -> None:
        """
        Configura root logger uma única vez (Singleton).
        
        Args:
            log_level: DEBUG, INFO, WARNING, ERROR, CRITICAL
            log_format: Formato das mensagens
        """
        if cls._configured:
            return
        
        # Configurar root logger
        root = logging.getLogger()
        root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        # Handler para stdout
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)  # Handler aceita tudo, root filtra
        
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)
        
        root.addHandler(handler)
        
        # ===== SILENCIAR LIBS RUIDOSAS =====
        # Estas libs emitem WARNING+ mesmo quando não é erro
        silent_libs = [
            'httpx',
            'google.genai',
            'urllib3',
            'googleapis',
            'google.auth',
            'asyncio',
        ]
        
        for lib in silent_libs:
            logging.getLogger(lib).setLevel(logging.WARNING)
        
        cls._configured = True
        root.info("[LOGGER] Logging configurado com sucesso")
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Obtém logger para um módulo específico.
        
        Args:
            name: Tipicamente __name__ do módulo
            
        Returns:
            Instância de logging.Logger
        """
        # Garantir que root foi configurado
        if not cls._configured:
            cls.configure_root_logger()
        
        return logging.getLogger(name)


# ===== INTERFACE PÚBLICA =====

def configure_logging(
    log_level: str = "INFO",
    log_format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
) -> None:
    """
    Configura logging do backend.
    
    Chame UMA VEZ ao iniciar o aplicativo (ex: em main.py ou FastAPI startup).
    
    Args:
        log_level: DEBUG, INFO, WARNING, ERROR, CRITICAL
        log_format: Formato das mensagens
    
    Exemplo:
        from .logger import configure_logging
        configure_logging(log_level="INFO")
    """
    LoggerFactory.configure_root_logger(log_level, log_format)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Obtém logger para uso em módulo.
    
    Args:
        name: Tipicamente __name__ (se None, usa "quintafeira.unnamed")
    
    Returns:
        logging.Logger configurado
    
    Exemplo:
        from .logger import get_logger
        logger = get_logger(__name__)
        logger.info("Iniciando...")
    """
    if name is None:
        name = "quintafeira.unnamed"
    
    return LoggerFactory.get_logger(name)

