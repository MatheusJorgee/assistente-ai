"""
HologramaTool: abre um HOLOGRAMA na tela do Matheus.

  - tipo=mapa    "onde fica a Bahia?"  -> globo com o lugar destacado + resumo.
  - tipo=viagem  "vou pra Lisboa 4 dias" -> globo + painéis de hospedagem, atrações, cronograma,
                 clima e dicas do guia.
  - tipo=fechar  fecha o holograma.

TUDO vem de fontes abertas e REAIS (OpenStreetMap, Wikivoyage, Wikipedia, Open-Meteo). Não existe
API gratuita com preço/disponibilidade de hotel: a hospedagem sai como locais mapeados + botões que
abrem a busca no Booking/Google/Airbnb. Nada é inventado.

O painel vai para a tela pelo evento `holo_show` (só existe quando há chat WebSocket aberto); ao LLM
volta só um resumo curto — e a saída inteira é conteúdo EXTERNO (envelope + contaminação do turno).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from .base import MotorTool, SecurityLevel, ToolMetadata, ToolParameter
from .. import get_logger
from ..config import get_config
from ..holo import clima, geo, guia, poi, trip
from ..holo.links import links_hospedagem
from ..holo.schema import AVISO_HOSPEDAGEM, sanitizar_texto, validar_payload
from ..runtime_progress import emitir, tem_ouvinte

logger = get_logger(__name__)

DESTINO_GRANDE_KM = 50.0  # acima disso (país/estado), hospedagem e cronograma não fazem sentido
_INDISPONIVEL = object()

# Estilo da viagem -> que seções do guia vêm primeiro nas dicas
_PRIORIDADE_POR_ESTILO = {
    "gastronomia": ("comer", "beber"), "cultural": ("ver",), "aventura": ("fazer",),
    "familia": ("fazer",), "economico": ("circular",), "conforto": (),
}


def _parse_data(valor: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(valor).strip()) if valor else None
    except ValueError:
        return None


class HologramaTool(MotorTool):
    """Abre um holograma (mapa ou viagem) na tela, com dados reais e gratuitos."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="mostrar_holograma",
                description=(
                    "Abre um HOLOGRAMA na tela do Matheus. Use quando ele perguntar ONDE FICA um lugar "
                    "(país, estado, cidade, ponto turístico): tipo='mapa'. Use quando ele mencionar uma "
                    "VIAGEM, destino, passeio ou pedir hospedagem, o que fazer ou roteiro: tipo='viagem' "
                    "(passe 'dias' e 'data_inicio' se ele disser). tipo='fechar' fecha o holograma. Os dados "
                    "são reais e gratuitos (OpenStreetMap, Wikivoyage, Open-Meteo). NÃO existe preço nem "
                    "disponibilidade ao vivo e você NUNCA deve inventar preço, horário ou endereço. NÃO use "
                    "para notícia ou gráfico de ativo (use mostrar_no_visor) nem para pesquisar fatos "
                    "(use pesquisar_informacao_online)."
                ),
                category="ui",
                parameters=[
                    ToolParameter(name="tipo", type="string", description="mapa | viagem | fechar",
                                  required=True, choices=["mapa", "viagem", "fechar"]),
                    ToolParameter(name="lugar", type="string",
                                  description="Nome do lugar ou destino (ex.: 'Bahia, Brasil', 'Lisboa')",
                                  required=False),
                    ToolParameter(name="dias", type="int", description="Dias de viagem (1 a 14; padrão 3)",
                                  required=False, default=3),
                    ToolParameter(name="data_inicio", type="string",
                                  description="Data de início da viagem, AAAA-MM-DD (só se ele disser)",
                                  required=False),
                    ToolParameter(name="estilo", type="string",
                                  description="Estilo da viagem, se ele disser",
                                  required=False,
                                  choices=["economico", "conforto", "cultural", "gastronomia", "aventura", "familia"]),
                ],
                examples=["onde fica a Bahia?", "vou viajar pra Lisboa 4 dias", "fecha o holograma"],
                security_level=SecurityLevel.LOW,
                tags=["holograma", "mapa", "viagem"],
            )
        )

    def validate_input(self, **kwargs: Any) -> bool:
        return str(kwargs.get("tipo") or "mapa").lower() in ("mapa", "viagem", "fechar")

    # ------------------------------------------------------------------ execução

    async def execute(self, **kwargs: Any) -> str:
        cfg = get_config()
        if not getattr(cfg, "HOLO_ENABLED", True):
            return "[ERRO] Hologramas desativados (HOLO_ENABLED=false)."

        tipo = str(kwargs.get("tipo") or "mapa").lower()
        if tipo == "fechar":
            await emitir("holo_hide")
            return "Holograma fechado."

        lugar = sanitizar_texto(kwargs.get("lugar"), 120)
        if not lugar:
            return "[ERRO] Diga qual lugar mostrar (ex.: 'Bahia, Brasil')."
        try:
            dias = max(1, min(14, int(kwargs.get("dias") or 3)))
        except (TypeError, ValueError):
            dias = 3
        inicio = _parse_data(kwargs.get("data_inicio"))
        estilo = str(kwargs.get("estilo") or "").lower()
        prazo = float(getattr(cfg, "HOLO_DEADLINE_S", 14.0))

        try:
            lug = await asyncio.wait_for(geo.geocodificar(lugar), timeout=prazo)
        except asyncio.TimeoutError:
            lug = None
        if lug is None:
            return (f"[ERRO] Não achei '{lugar}' no mapa agora. Peça ao Matheus para especificar "
                    "(cidade, estado, país) ou tente de novo em instantes.")

        if tipo == "viagem":
            dados = await self._coletar_viagem(lug, dias, inicio, prazo)
        else:
            dados = await self._coletar_mapa(lug, prazo)

        bruto = self._montar(lug, tipo, dias, inicio, estilo, dados)
        payload = validar_payload(bruto)
        if payload is None:
            return "[ERRO] Não consegui montar o holograma deste lugar."

        com_tela = tem_ouvinte()
        if com_tela:
            await emitir("holo_show", **payload)
        return self._resumo_para_llm(lug, tipo, dias, payload, dados, com_tela)

    # ------------------------------------------------------------------ coleta

    @staticmethod
    async def _reunir(tarefas: Dict[str, "asyncio.Future[Any]"], prazo: float) -> Dict[str, Any]:
        """Roda tudo em paralelo com um prazo global. O que não terminou (ou falhou) fica
        INDISPONÍVEL; o que terminou é usado: um painel lento não derruba os outros."""
        if not tarefas:
            return {}
        await asyncio.wait(list(tarefas.values()), timeout=prazo)
        saida: Dict[str, Any] = {}
        for nome, t in tarefas.items():
            if not t.done():
                t.cancel()
                saida[nome] = _INDISPONIVEL
            elif t.cancelled() or t.exception() is not None:
                saida[nome] = _INDISPONIVEL
            else:
                saida[nome] = t.result()
        return saida

    async def _coletar_mapa(self, lug: geo.Lugar, prazo: float) -> Dict[str, Any]:
        tarefas = {"resumo": asyncio.ensure_future(guia.buscar_resumo(lug.nome, lug.wikipedia))}
        return await self._reunir(tarefas, prazo)

    async def _coletar_viagem(self, lug: geo.Lugar, dias: int, inicio: Optional[date], prazo: float) -> Dict[str, Any]:
        grande = geo.bbox_diagonal_km(lug.bbox) > DESTINO_GRANDE_KM
        titulo_guia = lug.wikipedia.split(":", 1)[1] if lug.wikipedia and ":" in lug.wikipedia else lug.nome
        tarefas: Dict[str, "asyncio.Future[Any]"] = {
            "resumo": asyncio.ensure_future(guia.buscar_resumo(lug.nome, lug.wikipedia)),
            "guia": asyncio.ensure_future(guia.buscar_guia(titulo_guia)),
        }
        if not grande:
            tarefas["poi"] = asyncio.ensure_future(poi.buscar_poi(lug.lat, lug.lon, lug.bbox))
        if inicio is not None:
            tarefas["clima"] = asyncio.ensure_future(clima.buscar_clima(lug.lat, lug.lon, inicio, dias))
        dados = await self._reunir(tarefas, prazo)
        par = dados.pop("poi", _INDISPONIVEL)
        # Overpass falhou (ou estourou o prazo) => os dois painéis ficam indisponíveis
        dados["atracoes"], dados["hospedagens"] = (
            (_INDISPONIVEL, _INDISPONIVEL) if par is _INDISPONIVEL or par[0] is None else par)
        dados["grande"] = grande
        return dados

    # ------------------------------------------------------------------ montagem

    def _montar(self, lug: geo.Lugar, tipo: str, dias: int, inicio: Optional[date], estilo: str,
                dados: Dict[str, Any]) -> Dict[str, Any]:
        def ok(nome: str) -> Any:
            v = dados.get(nome, _INDISPONIVEL)
            return None if v is _INDISPONIVEL else v

        paineis: List[Dict[str, Any]] = []
        fontes: List[Dict[str, str]] = [{"nome": "OpenStreetMap (ODbL)", "url": "https://www.openstreetmap.org/copyright"}]

        resumo = ok("resumo")
        texto = resumo[0] if resumo else ""
        if tipo == "viagem" and dados.get("grande"):
            texto = (texto[:480] + " " if texto else "") + (
                "Este destino é grande demais para hospedagem e cronograma: diga uma cidade específica.")
        if texto:
            paineis.append({"tipo": "resumo", "texto": texto, "status": "ok"})
        if resumo:
            fontes.append({"nome": "Wikipedia (CC BY-SA)", "url": resumo[1]})

        if tipo == "viagem":
            atracoes = ok("atracoes")
            hospedagens = ok("hospedagens")
            if atracoes:
                paineis.append({"tipo": "atracoes", "itens": atracoes, "status": "ok"})
                cron = trip.agrupar_por_dia(atracoes, dias)
                if cron:
                    paineis.append({"tipo": "cronograma", "dias": cron, "metodo": "proximidade", "status": "ok"})
            # Hospedagem: sempre tem os botões de busca (é o painel mais resiliente).
            paineis.append({
                "tipo": "hospedagem", "itens": hospedagens or [], "aviso": AVISO_HOSPEDAGEM,
                "links": links_hospedagem(lug.nome, inicio, dias if inicio else None),
                "status": "ok" if hospedagens else "parcial",
            })
            c = ok("clima")
            if c:
                paineis.append({"tipo": "clima", **c})
                fontes.append({"nome": "Open-Meteo (CC BY 4.0)", "url": "https://open-meteo.com"})
            g = ok("guia")
            if g:
                secoes, url_guia, _ = g
                prioridade = list(_PRIORIDADE_POR_ESTILO.get(estilo, ()))
                if not atracoes:
                    prioridade.append("ver")  # sem locais mapeados, o guia é a fonte do "o que ver"
                dicas = guia.montar_dicas(secoes, prioridade)
                if dicas:
                    paineis.append({"tipo": "dicas", "secoes": dicas, "status": "ok"})
                fontes.append({"nome": "Wikivoyage (CC BY-SA)", "url": url_guia})

        titulo = lug.nome if tipo == "mapa" else f"Viagem: {lug.nome} · {dias} {'dia' if dias == 1 else 'dias'}"
        return {
            "id": uuid.uuid4().hex[:12], "tipo": tipo, "titulo": titulo,
            "geo": {"lat": lug.lat, "lon": lug.lon, "bbox": lug.bbox, "kind": lug.kind, "polygon": lug.polygon},
            "paineis": paineis, "fontes": fontes,
        }

    # ------------------------------------------------------------------ texto para o LLM

    def _resumo_para_llm(self, lug: geo.Lugar, tipo: str, dias: int, payload: Dict[str, Any],
                         dados: Dict[str, Any], com_tela: bool) -> str:
        por_tipo = {p["tipo"]: p for p in payload["paineis"]}
        partes: List[str] = []
        if tipo == "mapa":
            partes.append(f"Holograma aberto: {lug.nome_completo} (lat {lug.lat:.2f}, lon {lug.lon:.2f}).")
            r = por_tipo.get("resumo")
            if r:
                partes.append(r["texto"][:260])
        else:
            partes.append(f"Holograma de viagem aberto para {lug.nome_completo}.")
            if "atracoes" in por_tipo:
                nomes = ", ".join(i["nome"] for i in por_tipo["atracoes"]["itens"][:5])
                partes.append(f"Atrações reais no mapa: {nomes}.")
            hosp = por_tipo.get("hospedagem")
            if hosp:
                partes.append(f"{len(hosp['itens'])} hospedagens mapeadas no OpenStreetMap, SEM preço ao vivo "
                              "(botões de busca no Booking, Google Hotéis e Airbnb).")
            if "cronograma" in por_tipo:
                partes.append(f"Cronograma de {len(por_tipo['cronograma']['dias'])} dia(s) por proximidade, "
                              "sem horário de funcionamento.")
            if "clima" in por_tipo:
                partes.append(por_tipo["clima"]["rotulo"] + ".")
            faltou = [n for n, v in dados.items() if v is _INDISPONIVEL]
            if faltou:
                partes.append("Indisponível agora: " + ", ".join(faltou) + ".")
            if dados.get("grande"):
                partes.append("Destino grande: peça uma cidade para hospedagem e cronograma.")
            partes.append("Comente em 2 ou 3 frases; NÃO invente preços, horários nem endereços.")
        if not com_tela:
            partes.append("(Sem tela conectada: descreva por voz/texto.)")
        return sanitizar_texto(" ".join(partes), 600)
