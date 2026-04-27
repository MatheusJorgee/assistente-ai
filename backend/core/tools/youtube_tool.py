"""
YouTubeTool -- Reproducao de musicas/videos no YouTube.

Padrao fire-and-forget:
  - Daemon thread propria com ProactorEventLoop isolado (Windows-safe).
  - execute() retorna IMEDIATAMENTE; o LLM nao espera nem gasta tokens.
  - Browser headless fica aberto ate 1h ou ate o processo encerrar.
  - Erros de automacao sao silenciosos (nao afetam o LLM).
  - Evento media_playback_requested e sempre enviado ao frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import threading
from typing import Any, Dict, Optional

try:
    from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
except ImportError:
    from base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter

logger = logging.getLogger(__name__)

_YT_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{6,})"
)


def _extract_video_id(text: str) -> str:
    if not text:
        return ""
    m = _YT_URL_RE.search(text)
    return m.group(1) if m else ""


def _play_media_in_background(query: str) -> None:
    """
    Executa a automacao Playwright num loop ProactorEventLoop dedicado.

    NUNCA deve ser awaited. Iniciada via:
        threading.Thread(target=_play_media_in_background, args=(query,), daemon=True).start()

    Fluxo:
      1. Cria ProactorEventLoop proprio (suporta subprocessos no Windows).
      2. Instancia OSAutomation e chama tocar_youtube_invisivel_async(query).
      3. Mantem o loop vivo por 1h para o audio continuar tocando.
      4. Qualquer falha e silenciosa -- nao afeta o LLM.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Importa OSAutomation dentro da thread para evitar conflito de loops
        try:
            import os as _os
            _backend_dir = _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__)))
            if _backend_dir not in sys.path:
                sys.path.insert(0, _backend_dir)
            from automation import OSAutomation
        except Exception:
            return  # Playwright/automacao indisponivel -- encerra silenciosamente

        automation = OSAutomation()
        # Inicia reproducao
        loop.run_until_complete(automation.tocar_youtube_invisivel_async(query))
        # Keepalive: mantém o browser aberto por 1 hora
        loop.run_until_complete(asyncio.sleep(3600))
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "[THREAD YOUTUBE] Erro fatal em background: %s", e, exc_info=True
        )
    finally:
        loop.close()


class YouTubeTool(MotorTool):
    """
    Ferramenta para tocar musicas e videos no YouTube.

    Parametros:
      pesquisa   -- termo de busca (ex: "Coldplay - Yellow")
      video_url  -- URL direta (opcional)
      video_id   -- ID do video (opcional)
      raciocinio -- contexto para log (opcional)
    """

    def __init__(self, youtube_controller=None) -> None:
        self._controller = youtube_controller  # injetado em testes
        super().__init__(
            metadata=ToolMetadata(
                name="youtube_play",
                description=(
                    "Toca musica ou video no YouTube via motor invisivel no host. "
                    "Aceita: pesquisa por nome/artista, URL direta ou ID do video. "
                    "Use para qualquer pedido de reproducao de musica ou video."
                ),
                category="media",
                parameters=[
                    ToolParameter(
                        name="pesquisa",
                        type="string",
                        description=(
                            "Termo de busca no YouTube (ex: 'Coldplay Yellow', "
                            "'lofi hip hop', 'Eminem Lose Yourself')."
                        ),
                        required=False,
                    ),
                    ToolParameter(
                        name="video_url",
                        type="string",
                        description="URL completa do YouTube (ex: https://youtu.be/abc123).",
                        required=False,
                    ),
                    ToolParameter(
                        name="video_id",
                        type="string",
                        description="ID do video YouTube (ex: dQw4w9WgXcQ).",
                        required=False,
                    ),
                    ToolParameter(
                        name="raciocinio",
                        type="string",
                        description="Contexto/motivo (opcional).",
                        required=False,
                    ),
                ],
                examples=[
                    "pesquisa=Coldplay Yellow",
                    "pesquisa=lofi hip hop relaxing",
                    "video_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                ],
                security_level=SecurityLevel.LOW,
                tags=["youtube", "media", "music", "video"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return bool(
            str(kwargs.get("pesquisa", "")).strip()
            or str(kwargs.get("video_url", "")).strip()
            or str(kwargs.get("video_id", "")).strip()
        )

    async def execute(self, **kwargs: Any) -> str:
        pesquisa = str(kwargs.get("pesquisa", "")).strip()
        video_url = str(kwargs.get("video_url", "")).strip()
        video_id = str(kwargs.get("video_id", "")).strip()

        if not video_id and video_url:
            video_id = _extract_video_id(video_url)
        if not video_id and pesquisa:
            maybe = _extract_video_id(pesquisa)
            if maybe:
                video_id = maybe

        if not (pesquisa or video_id or video_url):
            raise ValueError(
                "Nenhum parametro: pesquisa, video_url ou video_id obrigatorio."
            )

        query = pesquisa or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else video_url
        )

        # ── Fire-and-forget: daemon thread com ProactorLoop proprio ────
        threading.Thread(
            target=_play_media_in_background,
            args=(query,),
            daemon=True,
            name="yt-playback",
        ).start()

        # ── Evento visual para o frontend (sempre enviado) ──────────────
        media_payload: Dict[str, Any] = {
            "provider": "youtube",
            "video_id": video_id or None,
            "video_url": video_url or (
                f"https://www.youtube.com/watch?v={video_id}" if video_id else None
            ),
            "search_query": pesquisa or None,
            "title": pesquisa or None,
            "autoplay": True,
        }
        try:
            self.publish_runtime("media_playback_requested", media_payload)
        except Exception:
            pass

        label = pesquisa or (
            f"youtube.com/watch?v={video_id}" if video_id else video_url
        )
        return json.dumps(
            {"ok": True, "label": label, "status": "reproducao iniciada em segundo plano"},
            ensure_ascii=False,
        )
