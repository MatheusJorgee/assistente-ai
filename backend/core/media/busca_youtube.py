"""
Busca no YouTube via yt-dlp (só metadados, nada é baixado).

Substitui a `youtube-search-python`, que quebrou com o httpx 0.28 (`post() got an unexpected keyword
argument 'proxies'`): o erro era engolido em silêncio, o resolvedor sempre devolvia "nada" e ela caía em
"clicar no primeiro resultado" — por isso tocava vídeo aleatório.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def buscar(query: str, n: int = 10) -> List[Dict[str, Any]]:
    """Até `n` resultados: [{id, title, channel, duration(seg)}]. Levanta a exceção real se falhar."""
    import yt_dlp

    opcoes = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 10}
    with yt_dlp.YoutubeDL(opcoes) as y:
        info = y.extract_info(f"ytsearch{int(n)}:{query}", download=False)
    saida: List[Dict[str, Any]] = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        saida.append({
            "id": e["id"],
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or "",
            "duration": e.get("duration"),
        })
    return saida
