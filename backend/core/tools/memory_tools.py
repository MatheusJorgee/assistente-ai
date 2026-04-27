"""
Tool de memória de longo prazo (episódica e semântica).
"""

from __future__ import annotations

import json
import os
import datetime
from typing import Any, Optional

try:
    from .. import get_logger
    from ..memory import MemoryManager
    from ..tools.base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
except ImportError:
    from .. import get_logger
    from ..memory import MemoryManager
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter

_logger = get_logger(__name__)


class MemoryTool(MotorTool):
    def __init__(self, memory_manager: MemoryManager):
        self._memory = memory_manager
        super().__init__(
            metadata=ToolMetadata(
                name="memory_manager",
                description=(
                    "Salva, recupera e busca memórias de longo prazo para evitar amnésia "
                    "entre reinicializações do backend."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="action",
                        type="string",
                        description="Ação: save_memory, retrieve_memory ou search_memory.",
                        required=True,
                        choices=["save_memory", "retrieve_memory", "search_memory"],
                    ),
                    ToolParameter(
                        name="memory_type",
                        type="string",
                        description="Tipo de memória: episodic, semantic ou all.",
                        required=False,
                        default="all",
                        choices=["episodic", "semantic", "all"],
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="Conteúdo da memória para salvar.",
                        required=False,
                    ),
                    ToolParameter(
                        name="fato",
                        type="string",
                        description=(
                            "Fato direto a ser gravado no arquivo de memória "
                            "(ex: 'Usuário tem alergia a camarão'). Use junto com tipo_memoria."
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="tipo_memoria",
                        type="string",
                        description=(
                            "'permanente' para fatos duráveis (alergias, nomes, preferências). "
                            "'diaria' para fatos temporários (humor, refeições, dores do dia)."
                        ),
                        required=False,
                        choices=["permanente", "diaria"],
                    ),
                    ToolParameter(
                        name="entidade",
                        type="string",
                        description="Nome da pessoa relacionada. Use 'usuario' para o próprio usuário.",
                        required=False,
                        default="usuario",
                    ),
                    ToolParameter(
                        name="query",
                        type="string",
                        description="Consulta textual para busca de memória.",
                        required=False,
                    ),
                    ToolParameter(
                        name="key",
                        type="string",
                        description="Chave semântica opcional para facts persistentes.",
                        required=False,
                    ),
                    ToolParameter(
                        name="category",
                        type="string",
                        description="Categoria semântica (ex: user, host, workflow).",
                        required=False,
                        default="user",
                    ),
                    ToolParameter(
                        name="event_type",
                        type="string",
                        description="Tipo de evento episódico.",
                        required=False,
                        default="generic",
                    ),
                    ToolParameter(
                        name="importance",
                        type="float",
                        description="Importância episódica entre 0.0 e 1.0.",
                        required=False,
                        default=0.5,
                    ),
                    ToolParameter(
                        name="confidence",
                        type="float",
                        description="Confiança semântica entre 0.0 e 1.0.",
                        required=False,
                        default=0.85,
                    ),
                    ToolParameter(
                        name="source",
                        type="string",
                        description="Fonte da memória (ex: tool, user, autonomous_worker).",
                        required=False,
                        default="tool",
                    ),
                    ToolParameter(
                        name="session_id",
                        type="string",
                        description="Sessão opcional para memória episódica.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="tags",
                        type="list",
                        description="Lista de tags para memória episódica.",
                        required=False,
                        default=[],
                    ),
                    ToolParameter(
                        name="limit",
                        type="int",
                        description="Limite de registros em retrieve/search.",
                        required=False,
                        default=10,
                    ),
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["memory", "long-term", "episodic", "semantic"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        action = str(kwargs.get("action", "")).lower().strip()
        fato = kwargs.get("fato") or kwargs.get("content")

        # Se há fato/content, aceita sem exigir action
        if isinstance(fato, str) and fato.strip():
            return True

        if action not in {"save_memory", "retrieve_memory", "search_memory"}:
            return False

        if action == "save_memory":
            content = kwargs.get("content") or kwargs.get("fato")
            return isinstance(content, str) and bool(content.strip())

        if action == "search_memory":
            query = kwargs.get("query")
            return isinstance(query, str) and bool(query.strip())

        return True

    async def execute(self, **kwargs) -> str:
        _logger.info(f"[DEBUG] MemoryTool EXECUTADA! Args: {kwargs}")
        action = str(kwargs.get("action", "")).lower().strip()
        memory_type = str(kwargs.get("memory_type", "all")).lower().strip()

        # FORÇAR save_memory quando há conteúdo, mesmo sem action explícita
        fato_detectado = str(kwargs.get("fato") or kwargs.get("content") or "").strip()
        if fato_detectado and action not in {"retrieve_memory", "search_memory"}:
            action = "save_memory"

        if action == "save_memory":
            fato = fato_detectado
            tipo = str(kwargs.get("tipo_memoria") or "").strip().lower()
            if not tipo:
                tipo = "permanente" if memory_type == "semantic" else "diaria"
            entidade = str(kwargs.get("entidade") or kwargs.get("category") or "usuario").strip()

            _logger.info(f"[DEBUG] CHAMANDO memorizar_informacao(fato={fato!r}, tipo={tipo!r}, entidade={entidade!r})")
            resultado_arquivo = memorizar_informacao(fato=fato, tipo_memoria=tipo, entidade=entidade)
            _logger.info(f"[DEBUG] RESULTADO DA ESCRITA: {resultado_arquivo}")

            result = await self._memory.save_memory(
                memory_type=memory_type if memory_type in {"episodic", "semantic"} else "episodic",
                content=fato or str(kwargs.get("content", "")).strip(),
                session_id=str(kwargs.get("session_id", "")),
                event_type=str(kwargs.get("event_type", "generic")),
                importance=float(kwargs.get("importance", 0.5)),
                tags=[str(t) for t in kwargs.get("tags", [])] if isinstance(kwargs.get("tags", []), list) else [],
                key=(str(kwargs["key"]) if "key" in kwargs and kwargs.get("key") is not None else None),
                category=str(kwargs.get("category", "user")),
                confidence=float(kwargs.get("confidence", 0.85)),
                source=str(kwargs.get("source", "tool")),
                payload=kwargs.get("payload") if isinstance(kwargs.get("payload"), dict) else None,
            )
            result["file_result"] = resultado_arquivo
            return json.dumps(result, ensure_ascii=False)

        if action == "retrieve_memory":
            result = await self._memory.retrieve_memory(
                memory_type=memory_type,
                limit=int(kwargs.get("limit", 10)),
            )
            return json.dumps(result, ensure_ascii=False)

        if action == "search_memory":
            result = await self._memory.search_memory(
                query=str(kwargs.get("query", "")).strip(),
                memory_type=memory_type,
                limit=int(kwargs.get("limit", 10)),
            )
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"ok": False, "error": "action inválida"}, ensure_ascii=False)


VAULT_PATH = "./.vault/Memorias"
DIARY_PATH = "./data"


def memorizar_informacao(fato: str, tipo_memoria: str, entidade: str = "usuario") -> str:
    """
    Salva uma informação na memória da Quinta-Feira.

    Args:
        fato: O que deve ser lembrado. Exemplos:
              'Usuário tem alergia a camarão'
              'Usuário está com dor de cabeça hoje'
        tipo_memoria: 'permanente' para fatos duráveis (alergias, nomes, preferências).
                      'diaria' para fatos temporários (humor, refeições, dores do dia).
        entidade: Nome da pessoa relacionada. Use 'usuario' se for sobre o próprio usuário.
    """
    print("\n" + "=" * 50)
    print(f"[DEBUG] TOOL memorizar_informacao EXECUTADA")
    print(f"Salvando -> Fato: {fato} | Tipo: {tipo_memoria}")
    print("=" * 50 + "\n")

    tipo_memoria = tipo_memoria.strip().lower()

    if tipo_memoria not in ("permanente", "diaria"):
        tipo_memoria = "diaria"

    try:
        if tipo_memoria == "permanente":
            os.makedirs(VAULT_PATH, exist_ok=True)
            entidade_slug = entidade.strip().lower().replace(" ", "_")
            caminho = os.path.join(VAULT_PATH, f"{entidade_slug}.md")
            secao = "## Núcleo Duro"

            if not os.path.exists(caminho):
                agora = datetime.datetime.now().isoformat()
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(
                        f"---\ndata: {agora}\ntags: [{entidade_slug}]\n---\n\n"
                        f"# {entidade}\n\n{secao}\n- {fato}\n"
                    )
            else:
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = f.read()

                if secao in conteudo:
                    conteudo = conteudo.replace(secao, f"{secao}\n- {fato}", 1)
                else:
                    conteudo += f"\n{secao}\n- {fato}\n"

                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(conteudo)

            return f"Memória permanente salva: {entidade_slug}.md"

        else:
            os.makedirs(DIARY_PATH, exist_ok=True)
            hoje = datetime.date.today().isoformat()
            agora = datetime.datetime.now().strftime("%H:%M")
            caminho = os.path.join(DIARY_PATH, f"diario_{hoje}.txt")

            with open(caminho, "a", encoding="utf-8") as f:
                f.write(f"- [{agora}] {fato}\n")

            return "Memória diária salva."

    except OSError as e:
        return f"ERRO ao salvar memória: {str(e)}"


class MemorizarInformacaoTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="memorizar_informacao",
                description=(
                    "Salva uma informação na memória da Quinta-Feira. "
                    "Use 'permanente' para fatos duráveis (alergias, nomes, preferências). "
                    "Use 'diaria' para fatos temporários (humor, refeições, dores do dia)."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="fato",
                        type="string",
                        description="O que deve ser lembrado (ex: 'Usuário tem alergia a camarão').",
                        required=True,
                    ),
                    ToolParameter(
                        name="tipo_memoria",
                        type="string",
                        description="'permanente' para fatos duráveis, 'diaria' para eventos do dia.",
                        required=True,
                        choices=["permanente", "diaria"],
                    ),
                    ToolParameter(
                        name="entidade",
                        type="string",
                        description="Nome da pessoa relacionada. Use 'usuario' se for sobre o próprio usuário.",
                        required=False,
                        default="usuario",
                    ),
                ],
                security_level=SecurityLevel.LOW,
                tags=["memory", "short-term", "long-term", "nuclear"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        fato = kwargs.get("fato") or kwargs.get("content") or kwargs.get("query")
        return isinstance(fato, str) and bool(fato.strip())

    async def execute(self, **kwargs) -> str:
        _logger.info(f"[DEBUG] MemorizarInformacaoTool EXECUTADA! Args: {kwargs}")
        fato = str(kwargs.get("fato") or kwargs.get("content") or kwargs.get("query") or "").strip()
        tipo = str(kwargs.get("tipo_memoria") or kwargs.get("tipo") or "").strip().lower()
        if not tipo:
            memory_type = str(kwargs.get("memory_type") or "").strip().lower()
            tipo = "permanente" if memory_type == "semantic" else "diaria"
        entidade = str(kwargs.get("entidade") or kwargs.get("category") or "usuario").strip()

        if not fato:
            msg = f"ERRO: fato vazio. kwargs recebidos: {kwargs}"
            _logger.error(f"{msg}")
            return msg

        _logger.info(f"[DEBUG] CHAMANDO memorizar_informacao(fato={fato!r}, tipo={tipo!r}, entidade={entidade!r})")
        resultado = memorizar_informacao(fato=fato, tipo_memoria=tipo, entidade=entidade)
        _logger.info(f"[DEBUG] RESULTADO DA ESCRITA: {resultado}")
        return resultado


# ─── Active Recall ────────────────────────────────────────────────────────────

def pesquisar_memoria(termo_busca: str) -> str:
    """
    Busca ativamente no banco de memorias permanentes (Vault) por uma palavra-chave, apelido ou contexto.
    Use OBRIGATORIAMENTE esta ferramenta ANTES de usar o WhatsApp se o usuario usar um apelido
    ou se voce nao tiver certeza absoluta do nome real do contato.
    """
    pasta = "./.vault/Memorias"
    resultados = []

    if os.path.exists(pasta):
        for filename in sorted(os.listdir(pasta)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(pasta, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    conteudo = f.read()
                if termo_busca.lower() in conteudo.lower() or termo_busca.lower() in filename.lower():
                    nome_limpo = filename.replace(".md", "").upper()
                    resultados.append(f"--- Fatos sobre {nome_limpo} ---\n{conteudo}")
            except (OSError, UnicodeDecodeError):
                continue

    if resultados:
        return "\n\n".join(resultados)
    return f"Nenhum registro encontrado na memoria para '{termo_busca}'. Peca esclarecimentos ao usuario."


class PesquisarMemoriaTool(MotorTool):
    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="pesquisar_memoria",
                description=(
                    "Busca ativamente no Vault de memorias permanentes por palavra-chave, apelido ou contexto. "
                    "Use OBRIGATORIAMENTE antes de usar o WhatsApp quando o usuario fornecer um apelido "
                    "(ex: 'yngridola', 'amor', 'mãe') ou quando nao souber o nome real do contato. "
                    "Retorna todos os fatos encontrados sobre a entidade pesquisada."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="termo_busca",
                        type="string",
                        description="Palavra-chave, apelido ou nome a buscar na memoria permanente.",
                        required=True,
                    ),
                ],
                security_level=SecurityLevel.LOW,
                tags=["memory", "search", "active-recall", "vault"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        termo = kwargs.get("termo_busca")
        return isinstance(termo, str) and bool(termo.strip())

    async def execute(self, **kwargs) -> str:
        return pesquisar_memoria(str(kwargs.get("termo_busca", "")).strip())
