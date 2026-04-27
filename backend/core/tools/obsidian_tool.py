"""
Tool de gravaÃ§Ã£o de MemÃ³ria Nuclear no Obsidian Vault.
"""

from __future__ import annotations

import os
import datetime

try:
    from ..tools.base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from ..memory.memory_manager import anotar_memoria_diaria
except ImportError:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
    from ..memory.memory_manager import anotar_memoria_diaria


VAULT_MEMORIAS_PATH = "./.vault/Memorias"


def salvar_memoria_obsidian(nome_entidade: str, categoria: str, fato: str) -> str:
    """
    Grava um fato permanente no Obsidian (MemÃ³ria Nuclear).
    Use isto QUANDO o usuÃ¡rio pedir para anotar uma preferÃªncia, alergia, vÃ­nculo ou dado imutÃ¡vel.

    Args:
        nome_entidade: O nome do arquivo (ex: 'paulo', 'preferencias_comida'). Use minÃºsculas e underscores.
        categoria: A categoria para o metadado (ex: 'pessoa', 'comida', 'sistema').
        fato: O fato direto e conciso a ser gravado (ex: 'Tem alergia a amendoim').
    """
    os.makedirs(VAULT_MEMORIAS_PATH, exist_ok=True)
    caminho_arquivo = os.path.join(VAULT_MEMORIAS_PATH, f"{nome_entidade}.md")

    agora = datetime.datetime.now().isoformat()

    if not os.path.exists(caminho_arquivo):
        conteudo_inicial = f"""---
data: {agora}
categoria: {categoria}
tags: [memoria_nuclear, {categoria}, {nome_entidade}]
---

# {nome_entidade.replace('_', ' ').title()}

## 🛡️ NÃºcleo Duro (Core Facts)
- {fato}

"""
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write(conteudo_inicial)
        return f"Novo arquivo criado e memÃ³ria salva em {caminho_arquivo}"

    else:
        with open(caminho_arquivo, "a", encoding="utf-8") as f:
            f.write(f"- {fato}\n")
        return f"MemÃ³ria adicionada ao arquivo existente {caminho_arquivo}"


class ObsidianMemoryTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="salvar_memoria_obsidian",
                description=(
                    "Grava um fato permanente no Obsidian (MemÃ³ria Nuclear). "
                    "Use QUANDO o usuÃ¡rio pedir para anotar uma preferÃªncia, alergia, "
                    "vÃ­nculo ou dado imutÃ¡vel."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="nome_entidade",
                        type="string",
                        description=(
                            "Nome do arquivo (ex: 'paulo', 'preferencias_comida'). "
                            "Use minÃºsculas e underscores."
                        ),
                        required=True,
                    ),
                    ToolParameter(
                        name="categoria",
                        type="string",
                        description="Categoria do metadado (ex: 'pessoa', 'comida', 'sistema').",
                        required=True,
                    ),
                    ToolParameter(
                        name="fato",
                        type="string",
                        description="Fato direto e conciso a ser gravado.",
                        required=True,
                    ),
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["memory", "obsidian", "nuclear", "long-term"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        for campo in ("nome_entidade", "categoria", "fato"):
            valor = kwargs.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                return False
        return True

    async def execute(self, **kwargs) -> str:
        return salvar_memoria_obsidian(
            nome_entidade=str(kwargs.get("nome_entidade", "")).strip(),
            categoria=str(kwargs.get("categoria", "")).strip(),
            fato=str(kwargs.get("fato", "")).strip(),
        )


class AnotarMemoriaDiariaTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="anotar_memoria",
                description=(
                    "Usa esta ferramenta para anotar fatos do dia-a-dia do usuÃ¡rio, "
                    "como dores, humor, refeiÃ§Ãµes, eventos temporÃ¡rios ou qualquer "
                    "acontecimento volÃ¡til do dia. Grava no arquivo de memÃ³ria "
                    "de curto prazo (contexto efÃªmero) do dia atual."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="fato",
                        type="string",
                        description=(
                            "Fato direto e conciso do dia a ser anotado "
                            "(ex: 'UsuÃ¡rio relatou dor de cabeÃ§a Ã s 14h')."
                        ),
                        required=True,
                    ),
                ],
                security_level=SecurityLevel.LOW,
                tags=["memory", "short-term", "diaria", "volatile"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        fato = kwargs.get("fato")
        return isinstance(fato, str) and bool(fato.strip())

    async def execute(self, **kwargs) -> str:
        return anotar_memoria_diaria(str(kwargs.get("fato", "")).strip())
