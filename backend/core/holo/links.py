"""
Links de BUSCA para hospedagem e voos. Só abrem a pesquisa no site com o destino (e as datas)
já preenchidos: sem scraping, sem afiliado, sem preço. Hosts fixos; tudo passa por urlencode.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode


def _datas(inicio: Optional[date], dias: Optional[int]) -> Optional[tuple]:
    if inicio is None or not dias or dias < 1:
        return None
    return inicio.isoformat(), (inicio + timedelta(days=dias)).isoformat()


def links_hospedagem(destino: str, inicio: Optional[date] = None, dias: Optional[int] = None) -> List[Dict[str, str]]:
    """Botões de busca de hospedagem/voos para o destino (com datas quando houver)."""
    destino = (destino or "").strip()
    if not destino:
        return []
    datas = _datas(inicio, dias)

    booking = {"ss": destino}
    if datas:
        booking.update({"checkin": datas[0], "checkout": datas[1]})
    airbnb = quote(destino, safe="")
    airbnb_url = f"https://www.airbnb.com.br/s/{airbnb}/homes"
    if datas:
        airbnb_url += "?" + urlencode({"checkin": datas[0], "checkout": datas[1]})

    return [
        {"rotulo": "Buscar no Booking", "url": "https://www.booking.com/searchresults.html?" + urlencode(booking)},
        {"rotulo": "Buscar no Google Hotéis", "url": "https://www.google.com/travel/search?" + urlencode({"q": f"hotéis em {destino}"})},
        {"rotulo": "Buscar no Airbnb", "url": airbnb_url},
        {"rotulo": "Buscar voos", "url": "https://www.google.com/travel/flights?" + urlencode({"q": f"Voos para {destino}"})},
    ]
