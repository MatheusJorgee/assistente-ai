"""
Contrato do evento `holo_show` (v1) e sua validação. FONTE ÚNICA: o frontend revalida o mesmo
contrato em lib/holo.ts (parseHoloPayload) e descarta o que for inválido em vez de quebrar.

Payload:
  { v:1, id, tipo:"mapa"|"viagem", titulo(<=80),
    geo:{lat,lon,bbox?,kind:"ponto"|"area",polygon?(<=800 pts, 3 casas)},
    paineis:[<=7, um por tipo], fontes:[<=6] }

Tudo aqui trata o texto como DADO de terceiros (OSM/Wikivoyage/Wikipedia): é higienizado, nunca
vira HTML, e URLs só passam se forem http(s) e de host esperado.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

VERSAO = 1

# Tetos (contrato)
MAX_TITULO = 80
MAX_RESUMO = 600
MAX_ITENS = 12
MAX_LINKS = 5
MAX_DIAS_CRONOGRAMA = 14
MAX_DIAS_CLIMA = 16
MAX_SECOES_DICAS = 5
MAX_ITENS_DICA = 6
MAX_CHARS_DICA = 200
MAX_DESCRICAO = 160
MAX_NOME = 80
MAX_PAINEIS = 7
MAX_FONTES = 6
MAX_PONTOS_POLIGONO = 800
MAX_BYTES_PAYLOAD = 64 * 1024

TIPOS_PAINEL = ("resumo", "hospedagem", "atracoes", "cronograma", "clima", "dicas")

AVISO_HOSPEDAGEM = (
    "Sem preço nem disponibilidade ao vivo: os locais vêm do OpenStreetMap e os botões abrem a "
    "busca no site escolhido."
)
AVISO_CRONOGRAMA = (
    "Sugestão automática por proximidade entre locais reais. Não considera horário de "
    "funcionamento nem trajeto: confira antes de ir."
)

# Hosts que os links de painéis podem apontar (o backend só os gera de hosts fixos, e o
# frontend confere de novo).
HOSTS_LINK = (
    "booking.com", "google.com", "airbnb.com.br", "airbnb.com", "openstreetmap.org",
    "wikipedia.org", "wikivoyage.org", "open-meteo.com",
)

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ESPACOS = re.compile(r"\s+")


def sanitizar_texto(valor: Any, limite: int) -> str:
    """Texto de terceiros -> texto puro, uma linha, sem controle nem '<' '>' (nunca vira HTML)."""
    s = str(valor if valor is not None else "")
    s = _CONTROLE.sub(" ", s).replace("<", " ").replace(">", " ")
    s = _ESPACOS.sub(" ", s).strip()
    if len(s) > limite:
        s = s[: max(0, limite - 1)].rstrip() + "…"
    return s


def _host_permitido(host: str, hosts: Iterable[str]) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in hosts)


def url_segura(url: Any, hosts: Optional[Iterable[str]] = HOSTS_LINK) -> Optional[str]:
    """Devolve a URL se for http(s), sem credenciais, curta e de host esperado; senão None."""
    if not isinstance(url, str) or not url or len(url) > 500:
        return None
    try:
        p = urlparse(url.strip())
    except Exception:
        return None
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return None
    if hosts is not None and not _host_permitido(p.hostname, hosts):
        return None
    return url.strip()


def _num(v: Any, lo: float, hi: float) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo <= f <= hi else None


def _lat(v: Any) -> Optional[float]:
    return _num(v, -90.0, 90.0)


def _lon(v: Any) -> Optional[float]:
    return _num(v, -180.0, 180.0)


def _link(item: Any) -> Optional[Dict[str, str]]:
    if not isinstance(item, dict):
        return None
    url = url_segura(item.get("url"))
    rotulo = sanitizar_texto(item.get("rotulo"), 60)
    return {"rotulo": rotulo, "url": url} if url and rotulo else None


def _fonte(item: Any) -> Optional[Dict[str, str]]:
    if not isinstance(item, dict):
        return None
    url = url_segura(item.get("url"))
    nome = sanitizar_texto(item.get("nome"), 60)
    return {"nome": nome, "url": url} if url and nome else None


def _status(v: Any) -> str:
    return v if v in ("ok", "parcial", "indisponivel") else "ok"


def _painel_resumo(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    texto = sanitizar_texto(p.get("texto"), MAX_RESUMO)
    return {"tipo": "resumo", "texto": texto, "status": _status(p.get("status"))} if texto else None


def _painel_hospedagem(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    itens = []
    for it in (p.get("itens") or [])[:MAX_ITENS]:
        if not isinstance(it, dict):
            continue
        nome = sanitizar_texto(it.get("nome"), MAX_NOME)
        link = url_segura(it.get("link_mapa"))
        if not nome or not link:
            continue
        item: Dict[str, Any] = {"nome": nome, "link_mapa": link}
        cat = sanitizar_texto(it.get("categoria"), 40)
        if cat:
            item["categoria"] = cat
        lat, lon = _lat(it.get("lat")), _lon(it.get("lon"))
        if lat is not None and lon is not None:
            item["lat"], item["lon"] = round(lat, 5), round(lon, 5)
        itens.append(item)
    links = [x for x in (_link(i) for i in (p.get("links") or [])[:MAX_LINKS]) if x]
    if not itens and not links:
        return None
    # Aviso FIXO: o backend não deixa o painel sair sem dizer que não há preço ao vivo.
    return {"tipo": "hospedagem", "itens": itens, "links": links, "aviso": AVISO_HOSPEDAGEM,
            "status": _status(p.get("status"))}


def _painel_atracoes(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    itens = []
    for it in (p.get("itens") or [])[:MAX_ITENS]:
        if not isinstance(it, dict):
            continue
        nome = sanitizar_texto(it.get("nome"), MAX_NOME)
        lat, lon = _lat(it.get("lat")), _lon(it.get("lon"))
        link = url_segura(it.get("link_mapa"))
        iid = sanitizar_texto(it.get("id"), 12)
        if not (nome and lat is not None and lon is not None and link and iid):
            continue
        item: Dict[str, Any] = {"id": iid, "nome": nome, "lat": round(lat, 5), "lon": round(lon, 5), "link_mapa": link}
        desc = sanitizar_texto(it.get("descricao"), MAX_DESCRICAO)
        if desc:
            item["descricao"] = desc
        cat = sanitizar_texto(it.get("categoria"), 40)
        if cat:
            item["categoria"] = cat
        wiki = url_segura(it.get("wikipedia"))
        if wiki:
            item["wikipedia"] = wiki
        itens.append(item)
    return {"tipo": "atracoes", "itens": itens, "status": _status(p.get("status"))} if itens else None


def _painel_cronograma(p: Dict[str, Any], ids_validos: Iterable[str]) -> Optional[Dict[str, Any]]:
    validos = set(ids_validos)
    dias = []
    for d in (p.get("dias") or [])[:MAX_DIAS_CRONOGRAMA]:
        if not isinstance(d, dict):
            continue
        blocos = []
        for b in (d.get("blocos") or [])[:3]:
            if not isinstance(b, dict) or b.get("periodo") not in ("manha", "tarde", "noite"):
                continue
            # O cronograma só referencia IDs de atrações REAIS do payload: nunca nomes soltos.
            ids = [i for i in (b.get("poi_ids") or []) if isinstance(i, str) and i in validos][:4]
            if ids:
                blocos.append({"periodo": b["periodo"], "poi_ids": ids})
        if blocos:
            try:
                n = int(d.get("n"))
            except (TypeError, ValueError):
                n = len(dias) + 1
            dias.append({"n": n, "titulo": sanitizar_texto(d.get("titulo"), 60), "blocos": blocos})
    if not dias:
        return None
    metodo = p.get("metodo") if p.get("metodo") in ("proximidade", "llm") else "proximidade"
    return {"tipo": "cronograma", "dias": dias, "metodo": metodo, "aviso": AVISO_CRONOGRAMA,
            "status": _status(p.get("status"))}


def _painel_clima(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    dias = []
    for d in (p.get("dias") or [])[:MAX_DIAS_CLIMA]:
        if not isinstance(d, dict):
            continue
        data = sanitizar_texto(d.get("data"), 10)
        tmin, tmax = _num(d.get("tmin"), -90, 70), _num(d.get("tmax"), -90, 70)
        if not data or tmin is None or tmax is None:
            continue
        chuva = _num(d.get("chuva_mm"), 0, 2000)
        dias.append({"data": data, "tmin": round(tmin, 1), "tmax": round(tmax, 1),
                     "chuva_mm": round(chuva, 1) if chuva is not None else 0.0})
    if not dias:
        return None
    origem = p.get("origem") if p.get("origem") in ("previsao", "ano_anterior") else "previsao"
    return {"tipo": "clima", "rotulo": sanitizar_texto(p.get("rotulo"), 100), "dias": dias,
            "origem": origem, "status": _status(p.get("status"))}


def _painel_dicas(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    secoes = []
    for s in (p.get("secoes") or [])[:MAX_SECOES_DICAS]:
        if not isinstance(s, dict):
            continue
        titulo = sanitizar_texto(s.get("titulo"), 40)
        itens = [x for x in (sanitizar_texto(i, MAX_CHARS_DICA) for i in (s.get("itens") or [])[:MAX_ITENS_DICA]) if x]
        if titulo and itens:
            secoes.append({"titulo": titulo, "itens": itens})
    return {"tipo": "dicas", "secoes": secoes, "status": _status(p.get("status"))} if secoes else None


def _geo(g: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(g, dict):
        return None
    lat, lon = _lat(g.get("lat")), _lon(g.get("lon"))
    if lat is None or lon is None:
        return None
    out: Dict[str, Any] = {"lat": round(lat, 5), "lon": round(lon, 5),
                           "kind": "area" if g.get("kind") == "area" else "ponto"}
    bbox = g.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        s, n, w, e = _lat(bbox[0]), _lat(bbox[1]), _lon(bbox[2]), _lon(bbox[3])
        if None not in (s, n, w, e):
            out["bbox"] = [round(s, 4), round(n, 4), round(w, 4), round(e, 4)]
    poligono = _poligono(g.get("polygon"))
    if poligono and out["kind"] == "area":
        out["polygon"] = poligono
    return out


def _poligono(mp: Any) -> Optional[List[List[List[List[float]]]]]:
    """MultiPolygon [poly][anel][pt][lon,lat], no máximo MAX_PONTOS_POLIGONO pontos, 3 casas."""
    if not isinstance(mp, list):
        return None
    saida, total = [], 0
    for poly in mp:
        aneis = []
        for anel in (poly if isinstance(poly, list) else []):
            pts = []
            for pt in (anel if isinstance(anel, list) else []):
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    lo, la = _lon(pt[0]), _lat(pt[1])
                    if lo is not None and la is not None:
                        pts.append([round(lo, 3), round(la, 3)])
            if len(pts) >= 4:
                if total + len(pts) > MAX_PONTOS_POLIGONO:
                    return saida or None  # estourou o teto: para no que já coube
                total += len(pts)
                aneis.append(pts)
        if aneis:
            saida.append(aneis)
    return saida or None


def _tamanho(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def validar_payload(bruto: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Payload bruto -> payload válido dentro dos tetos, ou None se não tem o mínimo (geo)."""
    if not isinstance(bruto, dict):
        return None
    geo = _geo(bruto.get("geo"))
    if geo is None:
        return None
    tipo = bruto.get("tipo") if bruto.get("tipo") in ("mapa", "viagem") else "mapa"

    paineis_brutos = [p for p in (bruto.get("paineis") or []) if isinstance(p, dict)]
    atracoes = next((_painel_atracoes(p) for p in paineis_brutos if p.get("tipo") == "atracoes"), None)
    ids_atracoes = [i["id"] for i in (atracoes or {}).get("itens", [])]

    construtores = {
        "resumo": _painel_resumo, "hospedagem": _painel_hospedagem, "atracoes": lambda p: atracoes,
        "cronograma": lambda p: _painel_cronograma(p, ids_atracoes), "clima": _painel_clima,
        "dicas": _painel_dicas,
    }
    paineis, vistos = [], set()
    for p in paineis_brutos:
        t = p.get("tipo")
        if t not in construtores or t in vistos:
            continue
        pronto = construtores[t](p)
        if pronto:
            paineis.append(pronto)
            vistos.add(t)
        if len(paineis) >= MAX_PAINEIS:
            break

    payload = {
        "v": VERSAO,
        "id": sanitizar_texto(bruto.get("id"), 40) or "holo",
        "tipo": tipo,
        "titulo": sanitizar_texto(bruto.get("titulo"), MAX_TITULO) or "Holograma",
        "geo": geo,
        "paineis": paineis,
        "fontes": [f for f in (_fonte(x) for x in (bruto.get("fontes") or [])[:MAX_FONTES]) if f],
    }

    # Teto de bytes: primeiro corta o polígono, depois os itens, do fim para o começo.
    if _tamanho(payload) > MAX_BYTES_PAYLOAD and "polygon" in payload["geo"]:
        payload["geo"].pop("polygon", None)
    for p in reversed(payload["paineis"]):
        while _tamanho(payload) > MAX_BYTES_PAYLOAD and p.get("itens"):
            p["itens"].pop()
    return payload
