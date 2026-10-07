"""
Clima da viagem (Open-Meteo, gratuito e sem chave).

  - Datas nos próximos 16 dias  -> PREVISÃO.
  - Datas mais distantes        -> os MESMOS dias do ano anterior (dado real, mas NÃO é previsão):
                                    o painel diz isso com todas as letras.
  - Sem data de início          -> sem painel de clima (não se inventa um período).
"""

from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from . import http

_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
_DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum"
_HORIZONTE_PREVISAO = 15  # dias à frente em que a previsão é confiável e disponível
_ATRASO_ARQUIVO = 7       # o arquivo histórico só cobre datas com alguns dias de atraso


def _mesmo_dia_no_ano(d: date, ano: int) -> date:
    try:
        return d.replace(year=ano)
    except ValueError:  # 29/02 em ano não bissexto
        return d.replace(year=ano, day=28)


def janela(hoje: date, inicio: date, dias: int) -> Tuple[str, date, date]:
    """('previsao'|'ano_anterior', primeiro dia, último dia) a consultar."""
    dias = max(1, dias)
    fim = inicio + timedelta(days=dias - 1)
    if fim >= hoje and inicio <= hoje + timedelta(days=_HORIZONTE_PREVISAO):
        return "previsao", max(inicio, hoje), min(fim, hoje + timedelta(days=_HORIZONTE_PREVISAO))
    ano = inicio.year - 1
    ini_a, fim_a = _mesmo_dia_no_ano(inicio, ano), _mesmo_dia_no_ano(fim, ano)
    while fim_a > hoje - timedelta(days=_ATRASO_ARQUIVO):  # tem que estar no passado
        ano -= 1
        ini_a, fim_a = _mesmo_dia_no_ano(inicio, ano), _mesmo_dia_no_ano(fim, ano)
    return "ano_anterior", ini_a, fim_a


def _dias_de(dados: Any) -> list:
    try:
        d = dados["daily"]
        saida = []
        for data, tmax, tmin, chuva in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"],
                                           d["precipitation_sum"]):
            if tmax is None or tmin is None:
                continue
            saida.append({"data": data, "tmin": tmin, "tmax": tmax, "chuva_mm": chuva or 0.0})
        return saida
    except (KeyError, TypeError):
        return []


async def buscar_clima(
    lat: float, lon: float, inicio: Optional[date], dias: int, hoje: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """Painel de clima (dict pronto para o schema) ou None (sem data, ou a fonte falhou)."""
    if inicio is None:
        return None
    hoje = hoje or date.today()
    origem, ini, fim = janela(hoje, inicio, dias)
    dados = await http.aget_json(
        _FORECAST if origem == "previsao" else _ARCHIVE,
        params={"latitude": round(lat, 3), "longitude": round(lon, 3), "daily": _DAILY,
                "timezone": "auto", "start_date": ini.isoformat(), "end_date": fim.isoformat()},
        ttl=3 * 3600.0 if origem == "previsao" else 30 * 86400.0,
    )
    lista = _dias_de(dados)
    if not lista:
        return None
    rotulo = (
        "Previsão para os dias da viagem"
        if origem == "previsao"
        else "Referência: os mesmos dias do ano anterior (não é previsão)"
    )
    return {"rotulo": rotulo, "dias": lista, "origem": origem, "status": "ok"}
