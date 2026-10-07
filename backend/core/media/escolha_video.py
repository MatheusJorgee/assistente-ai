"""
Escolha do vídeo certo para um pedido de música (regras puras, sem rede e sem LLM).

Problemas que isto resolve:
  - o resolvedor pegava o PRIMEIRO resultado do YouTube sem olhar o que era: "novo álbum do Tyler"
    virava uma entrevista/notícia sobre o Tyler;
  - "novo/último álbum" é um pedido sobre algo que ela NÃO sabe (qual é o álbum mais recente): buscar o
    texto cru é chute. Esses pedidos vão para o modelo pesquisar o nome real antes de tocar.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional

_RECENCIA = re.compile(r"\b(novo|nova|novos|novas|ultimo|ultima|recente|recentes|lancamento|lancou|mais novo|mais nova)\b")
_OBRA = re.compile(r"\b(album|disco|cd|single|ep|musica nova|som novo)\b")
_ALBUM = re.compile(r"\b(album|disco|cd)\b")
_LIXO = re.compile(
    r"\b(interview\w*|entrevista\w*|react\w*|reag\w*|reacao|review\w*|analis\w*|resenha\w*|explained|explicad\w*|explicacao|talks|reveals|"
    r"news|noticia|noticias|documentary|documentario|trailer|tutorial|how to|behind the scenes|bastidores|"
    r"podcast|shorts|meme|type beat|instrumental|karaoke|cover|remix|slowed|sped up|8d|nightcore|"
    r"432hz|528hz|playlist|mashup|compilation|lofi|lo fi|mixtape|unboxing|vlog|rating|ranking|tier list|breakdown|snippet|teaser|preview|leak|leaked)\b"
)
_BONUS_TITULO = re.compile(r"\b(official audio|audio oficial|official music video|full album|album completo|official video|lyrics|letra)\b")


def _norm(t: Any) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def pedido_vago(pesquisa: str) -> bool:
    """'o novo álbum do fulano', 'último single da fulana': depende de saber o que é o mais recente."""
    n = _norm(pesquisa)
    return bool(_RECENCIA.search(n) and _OBRA.search(n))


def eh_album(pesquisa: str) -> bool:
    return bool(_ALBUM.search(_norm(pesquisa)))


_RUIDO_QUERY = re.compile(
    r"\b(toca|toque|tocar|play|coloca|colocar|bota|botar|ponha|poe|quero|escutar|ouvir|para|pra|mim|me|por favor|favor|"
    r"o|a|os|as|um|uma|do|da|de|dos|das|no|na|album|disco|novo|nova|ultimo|ultima|musica|som|banda|artista|cantor|cantora|"
    r"completo|inteiro|aquele|aquela|full|official|audio|lyrics|letra|letras)\b"
)


def tokens_do_artista(pesquisa: str) -> List[str]:
    """Palavras que sobram do pedido depois de tirar o ruído de comando: normalmente o artista/título."""
    n = _RUIDO_QUERY.sub(" ", _norm(pesquisa))
    return [t for t in n.split() if len(t) >= 3]


def _segundos(dur: Any) -> Optional[int]:
    if isinstance(dur, (int, float)) and not isinstance(dur, bool):
        return int(dur) if dur > 0 else None
    partes = str(dur or "").strip().split(":")
    if not partes or not all(p.isdigit() for p in partes) or len(partes) > 3:
        return None
    total = 0
    for p in partes:
        total = total * 60 + int(p)
    return total


def _canal(v: Dict[str, Any]) -> str:
    c = v.get("channel")
    return str(c.get("name", "") if isinstance(c, dict) else c or "")


def pontuar(video: Dict[str, Any], pesquisa: str) -> float:
    """Quanto o vídeo parece ser O QUE FOI PEDIDO (música/álbum do artista), e não algo SOBRE o artista."""
    titulo, canal = _norm(video.get("title")), _norm(_canal(video))
    toks = tokens_do_artista(pesquisa)
    nota = 0.0
    if toks:
        achou = sum(1 for t in toks if t in titulo or t in canal)
        nota += 3.0 * achou / len(toks)
    if _LIXO.search(titulo):
        nota -= 4.0
    if re.search(r"mix", titulo):
        nota -= 1.5  # "Full Album Mix" costuma ser reupload editado
    if _BONUS_TITULO.search(titulo):
        nota += 1.0
    if canal.endswith(" topic") or "vevo" in canal:
        nota += 1.5
    if toks and any(t in canal for t in toks):
        nota += 1.0  # o canal é do próprio artista
    dur = _segundos(video.get("duration"))
    if dur is None:
        nota -= 1.0  # sem duração = live/ao vivo ou short: não serve para tocar
    elif eh_album(pesquisa):
        nota += 1.5 if 15 * 60 <= dur <= 100 * 60 else -2.0
    else:
        nota += 1.0 if 90 <= dur <= 10 * 60 else -2.0 if dur > 20 * 60 else 0.0
    return nota


def escolher(videos: List[Dict[str, Any]], pesquisa: str, minimo: float = 2.0) -> Optional[Dict[str, Any]]:
    """O melhor resultado, ou None se NENHUM parece o que foi pedido (melhor não tocar do que tocar errado)."""
    if not videos:
        return None
    melhor = max(videos, key=lambda v: pontuar(v, pesquisa))
    return melhor if pontuar(melhor, pesquisa) >= minimo else None
