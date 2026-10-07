"""
Pontos de interesse e hospedagens REAIS do OpenStreetMap, via Overpass.

O que vem daqui existe no mapa: nome, tipo e coordenadas. NÃO há preço, avaliação nem
disponibilidade (o OSM não tem). Para não entregar uma lista de becos e lojas, os itens são
ordenados por "notoriedade" (tem Wikipedia/Wikidata/site/estrelas). Overpass é lento e instável:
timeout curto, segundo servidor como reserva, e `None` (falhou) é diferente de `[]` (nada achado).
"""

import re
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from . import http
from .geo import bbox_diagonal_km

_SERVIDORES = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_TTL_POI = 7 * 86400.0
LIMITE = 12

_CAT_ATRACAO = {
    "attraction": "Atração", "museum": "Museu", "gallery": "Galeria", "viewpoint": "Mirante",
    "zoo": "Zoológico", "theme_park": "Parque temático", "aquarium": "Aquário",
    "monument": "Monumento", "castle": "Castelo", "memorial": "Memorial", "ruins": "Ruínas",
    "archaeological_site": "Sítio arqueológico", "fort": "Forte", "park": "Parque", "garden": "Jardim",
}
_CAT_HOSPEDAGEM = {
    "hotel": "Hotel", "hostel": "Hostel", "guest_house": "Pousada/casa de hóspedes",
    "apartment": "Apartamento", "motel": "Motel",
}
_LANG = re.compile(r"^[a-z]{2,3}$")


def raio_para(bbox: Optional[Sequence[float]]) -> int:
    """Raio de busca (m) a partir do tamanho do lugar: entre 3 e 15 km."""
    metade = bbox_diagonal_km(bbox) * 1000 / 2
    return int(max(3000, min(15000, metade or 5000)))


def _consulta_atracoes(lat: float, lon: float, raio: int) -> str:
    a = f"(around:{raio},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:10];("
        f'nwr["tourism"~"^(attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium)$"]["name"]{a};'
        f'nwr["historic"~"^(monument|castle|memorial|ruins|archaeological_site|fort)$"]["name"]{a};'
        f'nwr["leisure"~"^(park|garden)$"]["name"]["wikipedia"]{a};'
        ");out center tags 120;"
    )


def _consulta_hospedagens(lat: float, lon: float, raio: int) -> str:
    a = f"(around:{raio},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:10];("
        f'nwr["tourism"~"^(hotel|hostel|guest_house|apartment|motel)$"]["name"]{a};'
        ");out center tags 120;"
    )


def _pontuar(tags: Dict[str, Any]) -> int:
    """Notoriedade: Wikipedia/Wikidata pesam mais; site e estrelas ajudam."""
    pontos = 0
    if tags.get("wikipedia"):
        pontos += 5
    if tags.get("wikidata"):
        pontos += 4
    if tags.get("website") or tags.get("contact:website"):
        pontos += 2
    try:
        pontos += min(5, int(float(tags.get("stars", 0))))
    except (TypeError, ValueError):
        pass
    if tags.get("tourism") == "attraction":
        pontos += 1
    if tags.get("tourism") == "museum" or tags.get("historic") in ("castle", "fort", "archaeological_site"):
        pontos += 3
    if tags.get("heritage") or tags.get("heritage:operator"):
        pontos += 2
    if tags.get("historic") == "memorial" and not tags.get("wikipedia"):
        pontos -= 2  # estátuas/placas de rua: existem aos montes e raramente são o "o que ver"
    return pontos


def _coordenadas(el: Dict[str, Any]) -> Optional[tuple]:
    try:
        if "lat" in el and "lon" in el:
            return float(el["lat"]), float(el["lon"])
        c = el.get("center") or {}
        return float(c["lat"]), float(c["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def link_mapa(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}#map=17/{lat:.5f}/{lon:.5f}"


def _url_wikipedia(tag: Any) -> Optional[str]:
    """Tag do OSM 'pt:Título' -> URL da Wikipedia (só idioma de 2-3 letras)."""
    if not isinstance(tag, str) or ":" not in tag:
        return None
    lang, titulo = tag.split(":", 1)
    lang = lang.strip().lower()
    if not _LANG.match(lang) or not titulo.strip():
        return None
    return f"https://{lang}.wikipedia.org/wiki/{quote(titulo.strip().replace(' ', '_'))}"


def _categoria(tags: Dict[str, Any], tabela: Dict[str, str], chaves: Sequence[str]) -> str:
    for chave in chaves:
        valor = tags.get(chave)
        if valor in tabela:
            return tabela[valor]
    return ""


def normalizar_elementos(
    elementos: Any, *, hospedagem: bool, limite: int = LIMITE, prefixo: str = "a",
) -> List[Dict[str, Any]]:
    """Elementos do Overpass -> itens do painel, dedupe por nome, ordenados por notoriedade."""
    if not isinstance(elementos, list):
        return []
    candidatos = []
    for el in elementos:
        if not isinstance(el, dict):
            continue
        tags = el.get("tags") if isinstance(el.get("tags"), dict) else {}
        nome = str(tags.get("name:pt") or tags.get("name") or "").strip()
        coord = _coordenadas(el)
        if not nome or coord is None:
            continue
        candidatos.append((_pontuar(tags), nome, coord, tags))

    # Mais notórios primeiro; empate por nome (determinístico).
    candidatos.sort(key=lambda c: (-c[0], c[1].lower()))
    itens, vistos = [], set()
    for _, nome, (lat, lon), tags in candidatos:
        chave = nome.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        item: Dict[str, Any] = {"id": f"{prefixo}{len(itens) + 1}", "nome": nome,
                                "lat": round(lat, 5), "lon": round(lon, 5), "link_mapa": link_mapa(lat, lon)}
        if hospedagem:
            cat = _categoria(tags, _CAT_HOSPEDAGEM, ("tourism",))
            try:
                estrelas = int(float(tags.get("stars", 0)))
            except (TypeError, ValueError):
                estrelas = 0
            if cat and 1 <= estrelas <= 5:
                cat = f"{cat} {estrelas}★"
        else:
            cat = _categoria(tags, _CAT_ATRACAO, ("tourism", "historic", "leisure"))
            desc = tags.get("description:pt") or tags.get("description")
            if desc:
                item["descricao"] = str(desc)
            wiki = _url_wikipedia(tags.get("wikipedia"))
            if wiki:
                item["wikipedia"] = wiki
        if cat:
            item["categoria"] = cat
        itens.append(item)
        if len(itens) >= limite:
            break
    return itens


async def _overpass(consulta: str) -> Optional[List[Dict[str, Any]]]:
    """Roda a consulta no 1º servidor; se falhar, no 2º. None = todos falharam."""
    for url in _SERVIDORES:
        dados = await http.aget_json(url, metodo="POST", dados={"data": consulta}, ttl=_TTL_POI)
        if isinstance(dados, dict) and isinstance(dados.get("elements"), list):
            return dados["elements"]
    return None


def _consulta_tudo(lat: float, lon: float, raio: int) -> str:
    """Atrações + hospedagens numa consulta só: metade da carga no Overpass (que limita por IP)."""
    a = f"(around:{raio},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:12];("
        f'nwr["tourism"~"^(attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium)$"]["name"]{a};'
        f'nwr["historic"~"^(monument|castle|memorial|ruins|archaeological_site|fort)$"]["name"]{a};'
        f'nwr["leisure"~"^(park|garden)$"]["name"]["wikipedia"]{a};'
        f'nwr["tourism"~"^(hotel|hostel|guest_house|apartment|motel)$"]["name"]{a};'
        ");out center tags 400;"
    )


async def buscar_poi(lat: float, lon: float, bbox: Optional[Sequence[float]]):
    """(atrações, hospedagens); ambos None se o Overpass falhou em todos os espelhos."""
    els = await _overpass(_consulta_tudo(lat, lon, raio_para(bbox)))
    if els is None:
        return None, None
    hosp_els = [e for e in els if str((e.get("tags") or {}).get("tourism", "")) in _CAT_HOSPEDAGEM]
    atr_els = [e for e in els if e not in hosp_els]
    return (normalizar_elementos(atr_els, hospedagem=False, prefixo="a"),
            normalizar_elementos(hosp_els, hospedagem=True, prefixo="h"))


async def buscar_atracoes(lat: float, lon: float, bbox: Optional[Sequence[float]]) -> Optional[List[Dict[str, Any]]]:
    els = await _overpass(_consulta_atracoes(lat, lon, raio_para(bbox)))
    return None if els is None else normalizar_elementos(els, hospedagem=False, prefixo="a")


async def buscar_hospedagens(lat: float, lon: float, bbox: Optional[Sequence[float]]) -> Optional[List[Dict[str, Any]]]:
    els = await _overpass(_consulta_hospedagens(lat, lon, raio_para(bbox)))
    return None if els is None else normalizar_elementos(els, hospedagem=True, prefixo="h")
