"""
Geocodificação (Nominatim/OpenStreetMap) + simplificação de polígonos.

O Nominatim devolve o CONTORNO real do lugar (país, estado, cidade). Mas o contorno vem detalhado
demais (milhares de pontos) e o `polygon_threshold` dele não garante o tamanho; por isso a
simplificação é NOSSA (Douglas-Peucker, 3 casas decimais, teto de pontos) e o polígono já sai
pronto para o globo.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import http
from .schema import MAX_PONTOS_POLIGONO

_URL = "https://nominatim.openstreetmap.org/search"
_TTL_GEO = 30 * 86400.0  # lugares quase não mudam

Ponto = List[float]      # [lon, lat]
Anel = List[Ponto]
Poligono = List[Anel]    # [exterior, buraco, buraco...]
MultiPoligono = List[Poligono]


@dataclass
class Lugar:
    nome: str                                  # nome curto (ex.: "Bahia")
    nome_completo: str                         # display_name do OSM (ex.: "Bahia, Nordeste, Brasil")
    lat: float
    lon: float
    bbox: Optional[Tuple[float, float, float, float]]  # (sul, norte, oeste, leste)
    kind: str                                  # "area" (tem contorno) | "ponto"
    polygon: Optional[MultiPoligono]
    wikipedia: Optional[str]                   # "pt:Bahia" (tag do OSM), se houver
    pais: str = ""


# ----------------------------------------------------------------------------- geometria pura

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bbox_diagonal_km(bbox: Optional[Sequence[float]]) -> float:
    """Diagonal do retângulo (sul, norte, oeste, leste) em km; 0 se não houver bbox."""
    if not bbox or len(bbox) != 4:
        return 0.0
    s, n, w, e = bbox
    return _haversine_km(s, w, n, e)


def _dist_ponto_segmento(p: Ponto, a: Ponto, b: Ponto) -> float:
    ax, ay, bx, by, px, py = a[0], a[1], b[0], b[1], p[0], p[1]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker(pts: Sequence[Ponto], eps: float) -> List[Ponto]:
    """Simplifica uma polilinha mantendo os extremos (versão iterativa: contornos têm milhares de pontos)."""
    n = len(pts)
    if n < 3 or eps <= 0:
        return [list(p) for p in pts]
    manter = [False] * n
    manter[0] = manter[-1] = True
    pilha = [(0, n - 1)]
    while pilha:
        ini, fim = pilha.pop()
        maior, idx = 0.0, -1
        for i in range(ini + 1, fim):
            d = _dist_ponto_segmento(pts[i], pts[ini], pts[fim])
            if d > maior:
                maior, idx = d, i
        if idx != -1 and maior > eps:
            manter[idx] = True
            pilha.append((ini, idx))
            pilha.append((idx, fim))
    return [list(p) for p, m in zip(pts, manter) if m]


def _area_anel(anel: Anel) -> float:
    """Área (em graus², só para ordenar/descartar) pela fórmula do cadarço."""
    s = 0.0
    for i in range(len(anel) - 1):
        s += anel[i][0] * anel[i + 1][1] - anel[i + 1][0] * anel[i][1]
    return abs(s) / 2


def _fechar(anel: Anel) -> Anel:
    return anel if anel and anel[0] == anel[-1] else anel + [anel[0]]


def _arredondar(anel: Anel) -> Anel:
    return [[round(p[0], 3), round(p[1], 3)] for p in anel]


def normalizar_geojson(geo: Any) -> Optional[MultiPoligono]:
    """GeoJSON (Polygon/MultiPolygon) -> MultiPolygon [poly][anel][pt][lon,lat]; outros tipos -> None."""
    if not isinstance(geo, dict):
        return None
    tipo, coords = geo.get("type"), geo.get("coordinates")
    if tipo == "Polygon" and isinstance(coords, list):
        return [coords]
    if tipo == "MultiPolygon" and isinstance(coords, list):
        return coords
    return None


def simplificar_multipoligono(mp: MultiPoligono, max_pontos: int = MAX_PONTOS_POLIGONO) -> MultiPoligono:
    """Reduz o contorno a no máximo `max_pontos` pontos (aumenta a tolerância até caber; se preciso,
    descarta as ilhas menores) e arredonda a 3 casas."""
    poligonos: List[Poligono] = []
    for poly in mp:
        aneis = [_fechar([list(map(float, p[:2])) for p in anel]) for anel in poly if isinstance(anel, list) and len(anel) >= 4]
        if aneis:
            poligonos.append(aneis)
    poligonos.sort(key=lambda poly: _area_anel(poly[0]), reverse=True)  # maiores primeiro

    eps = 0.002  # ~200 m
    for _ in range(14):
        candidato: MultiPoligono = []
        for i, poly in enumerate(poligonos):
            exterior = douglas_peucker(poly[0], eps)
            if len(exterior) < 4:
                continue
            if i > 0 and _area_anel(exterior) < eps * eps * 4:
                continue  # ilhota que sumiu na simplificação (o maior polígono nunca some)
            aneis = [_arredondar(_fechar(exterior))]
            for buraco in poly[1:]:
                b = douglas_peucker(buraco, eps)
                if len(b) >= 4 and _area_anel(b) >= eps * eps * 4:
                    aneis.append(_arredondar(_fechar(b)))
            candidato.append(aneis)
        if candidato and sum(len(a) for poly in candidato for a in poly) <= max_pontos:
            return candidato
        eps *= 1.6

    # Ainda passou do teto: fica só com o que cabe, das maiores para as menores.
    saida: MultiPoligono = []
    total = 0
    for poly in candidato or []:
        n = sum(len(a) for a in poly)
        if total + n > max_pontos:
            continue
        saida.append(poly)
        total += n
    return saida


# ----------------------------------------------------------------------------- Nominatim

def escolher_resultado(resultados: Any) -> Optional[Dict[str, Any]]:
    """O Nominatim já ordena por importância: pega o primeiro com coordenadas válidas."""
    if not isinstance(resultados, list):
        return None
    for r in resultados:
        try:
            float(r["lat"]), float(r["lon"])
            return r
        except (KeyError, TypeError, ValueError):
            continue
    return None


def lugar_de_resultado(r: Dict[str, Any]) -> Lugar:
    completo = str(r.get("display_name") or r.get("name") or "").strip()
    nome = str(r.get("name") or completo.split(",")[0]).strip() or completo
    bbox = None
    try:
        s, n, w, e = (float(x) for x in r["boundingbox"])
        bbox = (s, n, w, e)
    except (KeyError, TypeError, ValueError):
        pass
    mp = normalizar_geojson(r.get("geojson"))
    polygon = simplificar_multipoligono(mp) if mp else None
    extra = r.get("extratags") if isinstance(r.get("extratags"), dict) else {}
    wiki = extra.get("wikipedia") if isinstance(extra.get("wikipedia"), str) else None
    pais = ""
    if isinstance(r.get("address"), dict):
        pais = str(r["address"].get("country_code", "")).lower()
    return Lugar(
        nome=nome, nome_completo=completo, lat=float(r["lat"]), lon=float(r["lon"]), bbox=bbox,
        kind="area" if polygon else "ponto", polygon=polygon or None, wikipedia=wiki, pais=pais,
    )


async def geocodificar(lugar: str) -> Optional[Lugar]:
    """Lugar pelo nome (país, estado, cidade, ponto turístico), com contorno quando existir."""
    consulta = (lugar or "").strip()
    if not consulta:
        return None
    dados = await http.aget_json(
        _URL,
        params={
            "q": consulta, "format": "jsonv2", "polygon_geojson": 1, "polygon_threshold": 0.01,
            "addressdetails": 1, "extratags": 1, "limit": 3, "accept-language": "pt-BR",
        },
        ttl=_TTL_GEO,
    )
    r = escolher_resultado(dados)
    return lugar_de_resultado(r) if r else None
