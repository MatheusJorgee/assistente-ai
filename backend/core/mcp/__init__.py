"""Cliente MCP (Model Context Protocol) mínimo: ferramentas de terceiros com política de aprovação."""

from .manager import PREFIXO, carregar, e_leitura, e_mcp, ler_config, parar_todos

__all__ = ["PREFIXO", "carregar", "e_leitura", "e_mcp", "ler_config", "parar_todos"]
