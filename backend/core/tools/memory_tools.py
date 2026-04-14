"""
Tool de memÃ³ria de longo prazo (episÃ³dica e semÃ¢ntica).
"""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    from core.memory import MemoryManager
    from core.tools.base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
except ImportError:
    from core.memory import MemoryManager
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter


class MemoryTool(MotorTool):
    def __init__(self, memory_manager: MemoryManager):
        self._memory = memory_manager
        super().__init__(
            metadata=ToolMetadata(
                name="memory_manager",
                description=(
                    "Salva, recupera e busca memÃ³rias de longo prazo para evitar amnÃ©sia "
                    "entre reinicializaÃ§Ãµes do backend."
                ),
                category="memory",
                parameters=[
                    ToolParameter(
                        name="action",
                        type="string",
                        description="AÃ§Ã£o: save_memory, retrieve_memory ou search_memory.",
                        required=True,
                        choices=["save_memory", "retrieve_memory", "search_memory"],
                    ),
                    ToolParameter(
                        name="memory_type",
                        type="string",
                        description="Tipo de memÃ³ria: episodic, semantic ou all.",
                        required=False,
                        default="all",
                        choices=["episodic", "semantic", "all"],
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="ConteÃºdo da memÃ³ria para salvar.",
                        required=False,
                    ),
                    ToolParameter(
                        name="query",
                        type="string",
                        description="Consulta textual para busca de memÃ³ria.",
                        required=False,
                    ),
                    ToolParameter(
                        name="key",
                        type="string",
                        description="Chave semÃ¢ntica opcional para facts persistentes.",
                        required=False,
                    ),
                    ToolParameter(
                        name="category",
                        type="string",
                        description="Categoria semÃ¢ntica (ex: user, host, workflow).",
                        required=False,
                        default="user",
                    ),
                    ToolParameter(
                        name="event_type",
                        type="string",
                        description="Tipo de evento episÃ³dico.",
                        required=False,
                        default="generic",
                    ),
                    ToolParameter(
                        name="importance",
                        type="float",
                        description="ImportÃ¢ncia episÃ³dica entre 0.0 e 1.0.",
                        required=False,
                        default=0.5,
                    ),
                    ToolParameter(
                        name="confidence",
                        type="float",
                        description="ConfianÃ§a semÃ¢ntica entre 0.0 e 1.0.",
                        required=False,
                        default=0.85,
                    ),
                    ToolParameter(
                        name="source",
                        type="string",
                        description="Fonte da memÃ³ria (ex: tool, user, autonomous_worker).",
                        required=False,
                        default="tool",
                    ),
                    ToolParameter(
                        name="session_id",
                        type="string",
                        description="SessÃ£o opcional para memÃ³ria episÃ³dica.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="tags",
                        type="list",
                        description="Lista de tags para memÃ³ria episÃ³dica.",
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
        if action not in {"save_memory", "retrieve_memory", "search_memory"}:
            return False

        if action == "save_memory":
            content = kwargs.get("content")
            return isinstance(content, str) and bool(content.strip())

        if action == "search_memory":
            query = kwargs.get("query")
            return isinstance(query, str) and bool(query.strip())

        return True

    async def execute(self, **kwargs) -> str:
        action = str(kwargs.get("action", "")).lower().strip()
        memory_type = str(kwargs.get("memory_type", "all")).lower().strip()

        if action == "save_memory":
            result = await self._memory.save_memory(
                memory_type=memory_type if memory_type in {"episodic", "semantic"} else "episodic",
                content=str(kwargs.get("content", "")).strip(),
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

        return json.dumps({"ok": False, "error": "action invÃ¡lida"}, ensure_ascii=False)

