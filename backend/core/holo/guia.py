"""
Guia turístico (Wikivoyage) e resumo do lugar (Wikipedia). Ambos sob licença CC BY-SA: cada
painel leva a fonte e o link da página.

O texto é de TERCEIROS: só passa como dado (higienizado, cortado, nunca HTML). O que o LLM recebe
é curto, e a saída da tool inteira é tratada como conteúdo externo (envelope + contaminação).
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

from . import http
from .schema import MAX_CHARS_DICA, MAX_ITENS_DICA, sanitizar_texto

_TTL_GUIA = 14 * 86400.0
_TITULO_SECAO = re.compile(r"^\s*(=+)\s*(.+?)\s*\1\s*$")

# Nome da seção (pt/en) -> chave canônica
_ALIASES = {
    "ver": "ver", "see": "ver",
    "fazer": "fazer", "do": "fazer",
    "comer": "comer", "eat": "comer",
    "beber": "beber", "drink": "beber", "sair à noite": "beber", "sair a noite": "beber",
    "dormir": "dormir", "sleep": "dormir",
    "chegar": "chegar", "get in": "chegar",
    "circular": "circular", "get around": "circular",
    "segurança": "seguranca", "seguranca": "seguranca", "stay safe": "seguranca",
    "clima": "clima", "climate": "clima",
    "comprar": "comprar", "buy": "comprar",
}

_TITULO_DICA = {
    "chegar": "Chegar", "circular": "Circular", "comer": "Comer", "beber": "Beber e sair",
    "seguranca": "Segurança", "fazer": "O que fazer", "ver": "O que ver", "clima": "Clima",
}
# Ordem em que as seções viram painel de dicas
ORDEM_DICAS = ("chegar", "circular", "comer", "seguranca", "fazer")


def extrair_secoes(texto: Any) -> Dict[str, List[str]]:
    """Texto do Wikivoyage ('== Ver ==' + linhas) -> {chave canônica: [linhas]}.

    Subseções sem nome conhecido (ex.: 'De avião' dentro de 'Chegar') continuam na seção
    canônica pai; uma seção de nível 2 desconhecida encerra o contexto."""
    if not isinstance(texto, str):
        return {}
    secoes: Dict[str, List[str]] = {}
    atual: Optional[str] = None
    for linha in texto.splitlines():
        m = _TITULO_SECAO.match(linha)
        if m:
            nivel, titulo = len(m.group(1)), m.group(2).strip().lower()
            canonica = _ALIASES.get(titulo)
            if canonica:
                atual = canonica
            elif nivel <= 2:
                atual = None
            continue
        if atual is None:
            continue
        limpa = sanitizar_texto(linha.lstrip("•*-– \t"), MAX_CHARS_DICA)
        if len(limpa) >= 12:  # descarta migalhas ("•", nomes soltos de 1-2 palavras)
            secoes.setdefault(atual, []).append(limpa)
    return {k: v[:MAX_ITENS_DICA] for k, v in secoes.items() if v}


def montar_dicas(secoes: Dict[str, List[str]], prioridade: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Seções canônicas -> seções do painel `dicas` (até 5). `prioridade` (ex.: o estilo da viagem)
    vem primeiro; depois a ordem útil para quem viaja."""
    chaves = [k for k in dict.fromkeys((*prioridade, *ORDEM_DICAS)) if k in secoes]
    saida = []
    for k in chaves[:5]:
        saida.append({"titulo": _TITULO_DICA.get(k, k.capitalize()), "itens": secoes[k][:MAX_ITENS_DICA]})
    return saida


async def buscar_guia(
    titulo: str, idiomas: Sequence[str] = ("pt", "en"),
) -> Optional[Tuple[Dict[str, List[str]], str, str]]:
    """(seções, url da página, idioma) do Wikivoyage, ou None. Tenta pt e depois en."""
    titulo = (titulo or "").strip()
    if not titulo:
        return None
    for lang in idiomas:
        dados = await http.aget_json(
            f"https://{lang}.wikivoyage.org/w/api.php",
            params={
                "action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki",
                "titles": titulo, "redirects": 1, "format": "json", "formatversion": 2,
            },
            ttl=_TTL_GUIA,
        )
        try:
            pagina = dados["query"]["pages"][0]
            if pagina.get("missing"):
                continue
            secoes = extrair_secoes(pagina.get("extract", ""))
        except (KeyError, IndexError, TypeError):
            continue
        if secoes:
            url = f"https://{lang}.wikivoyage.org/wiki/{quote(str(pagina.get('title', titulo)).replace(' ', '_'))}"
            return secoes, url, lang
    return None


def _titulo_e_idioma(nome: str, wiki_tag: Optional[str]) -> Tuple[str, Optional[str]]:
    """Tag do OSM 'pt:Título' tem prioridade; senão, o nome do lugar."""
    if wiki_tag and ":" in wiki_tag:
        lang, tit = wiki_tag.split(":", 1)
        if re.fullmatch(r"[a-z]{2,3}", lang.strip().lower()) and tit.strip():
            return tit.strip(), lang.strip().lower()
    return nome, None


async def buscar_resumo(nome: str, wiki_tag: Optional[str] = None) -> Optional[Tuple[str, str, str]]:
    """(texto, url, idioma) do resumo da Wikipedia, ou None. Ignora páginas de desambiguação."""
    titulo, lang_tag = _titulo_e_idioma(nome, wiki_tag)
    idiomas = ([lang_tag] if lang_tag else []) + [l for l in ("pt", "en") if l != lang_tag]
    for lang in idiomas:
        dados = await http.aget_json(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(titulo.replace(' ', '_'))}",
            ttl=_TTL_GUIA,
        )
        if not isinstance(dados, dict) or dados.get("type") == "disambiguation":
            continue
        texto = sanitizar_texto(dados.get("extract"), 600)
        url = (((dados.get("content_urls") or {}).get("desktop") or {}).get("page")) or ""
        if texto and url:
            return texto, url, lang
    return None
