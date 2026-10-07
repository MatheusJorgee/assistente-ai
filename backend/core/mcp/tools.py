"""Ferramenta que representa UMA ferramenta de um servidor MCP."""

from typing import Any, Dict, List

from ..tools.base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
from .client import ErroMCP, ServidorMCP
from .guard import caminho_sensivel, mascarar_segredos

_TIPOS = {"string": "string", "integer": "int", "number": "number", "boolean": "bool", "array": "list", "object": "string"}


def _higienizar(texto: Any, n: int) -> str:
    return " ".join(str(texto or "").split())[:n]


def parametros_do_schema(schema: Any) -> List[ToolParameter]:
    """inputSchema (JSON Schema) -> ToolParameter. Só o nível de cima; descrições cortadas."""
    if not isinstance(schema, dict):
        return []
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    obrigatorios = set(schema.get("required") or []) if isinstance(schema.get("required"), list) else set()
    saida: List[ToolParameter] = []
    for nome, p in list(props.items())[:20]:
        if not isinstance(p, dict) or not isinstance(nome, str):
            continue
        saida.append(ToolParameter(
            name=nome[:40], type=_TIPOS.get(str(p.get("type")), "string"),
            description=_higienizar(p.get("description"), 120), required=nome in obrigatorios,
            choices=list(p["enum"])[:20] if isinstance(p.get("enum"), list) else None,
        ))
    return saida


class MCPTool(MotorTool):
    def __init__(self, nome_registrado: str, servidor: ServidorMCP, definicao: Dict[str, Any], somente_leitura: bool) -> None:
        self._servidor = servidor
        self._original = definicao["name"]
        descricao = _higienizar(definicao.get("description"), 300)
        super().__init__(ToolMetadata(
            name=nome_registrado,
            # o texto do servidor é de terceiros: vai com o rótulo e cortado
            description=f"[MCP: {servidor.nome}] {descricao}",
            category="mcp",
            parameters=parametros_do_schema(definicao.get("inputSchema")),
            examples=[],
            security_level=SecurityLevel.LOW if somente_leitura else SecurityLevel.CRITICAL,
            tags=["mcp", servidor.nome],
        ))

    def validate_input(self, **kwargs: Any) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        argumentos = {k: v for k, v in kwargs.items() if v is not None}
        # Caminho de segredo (.env, .vault, chaves, perfis...): recusa aqui, sem chamar o servidor.
        sensivel = caminho_sensivel(argumentos)
        if sensivel:
            # Recusa DE PROPÓSITO (segurança): prefixo próprio, para NÃO contar como falha na revisão semanal
            return f"[BLOQUEADO] Caminho sensível ({sensivel}): não leio segredos por essa via."
        try:
            return mascarar_segredos(await self._servidor.chamar(self._original, argumentos))
        except ErroMCP as exc:
            return f"[ERRO] MCP {self._servidor.nome}/{self._original}: {exc}"
