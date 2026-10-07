"""
MostrarVisorTool — abre conteúdo visual no "visor" da própria Quinta-Feira.

A IA chama esta ferramenta enquanto fala para exibir, dentro da página dela
(sem abrir link externo), um card de notícia, um gráfico (cripto/ações) ou
uma imagem. A diretiva é capturada pelo Brain e anexada ao brain_response,
de modo que o visor abre no mesmo instante em que a resposta chega ao frontend.

Esta tool serve principalmente para EXPOR O SCHEMA à LLM; a normalização e o
disparo são tratados no Brain (_execute_tool_call), que intercepta a chamada.
"""

from __future__ import annotations

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)


class MostrarVisorTool(MotorTool):
    """Exibe conteúdo visual (notícia, gráfico, imagem) no visor da Quinta-Feira."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="mostrar_no_visor",
                description=(
                    "Abre conteúdo visual DENTRO da página da Quinta-Feira (não abre link externo) "
                    "enquanto você fala. Use proativamente: ao comentar uma notícia, mostre o card "
                    "dela; ao falar de cripto/ações (ex: bitcoin), mostre o gráfico; para ilustrar, "
                    "uma imagem. Chame esta ferramenta ANTES ou JUNTO de responder sobre o assunto."
                ),
                category="ui",
                parameters=[
                    ToolParameter(
                        name="tipo",
                        type="string",
                        description="'noticia' (card), 'grafico' (cripto/ações) ou 'imagem'.",
                        required=True,
                        choices=["noticia", "grafico", "imagem"],
                    ),
                    ToolParameter(
                        name="titulo",
                        type="string",
                        description="Título/manchete (notícia) ou legenda do conteúdo.",
                        required=False,
                    ),
                    ToolParameter(
                        name="resumo",
                        type="string",
                        description="Resumo curto da notícia (1-2 frases).",
                        required=False,
                    ),
                    ToolParameter(
                        name="imagem",
                        type="string",
                        description="URL da imagem (card de notícia) ou da imagem a exibir.",
                        required=False,
                    ),
                    ToolParameter(
                        name="fonte",
                        type="string",
                        description="Fonte/veículo da notícia (ex: 'G1').",
                        required=False,
                    ),
                    ToolParameter(
                        name="url",
                        type="string",
                        description="URL da matéria original (para o botão 'abrir no navegador').",
                        required=False,
                    ),
                    ToolParameter(
                        name="ativo",
                        type="string",
                        description="Para tipo=grafico: ativo a exibir (ex: 'bitcoin', 'BTC', 'ETH', 'AAPL').",
                        required=False,
                    ),
                ],
                security_level=SecurityLevel.LOW,
                tags=["ui", "visor", "frontend"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        return bool(str(kwargs.get("tipo") or "").strip())

    async def execute(self, **kwargs) -> str:
        # O Brain intercepta esta tool e trata a normalização/disparo.
        # Este corpo é fallback caso seja executada diretamente.
        logger.info(f"[VISOR] mostrar_no_visor chamada: tipo={kwargs.get('tipo')!r}")
        return "Visor atualizado."
