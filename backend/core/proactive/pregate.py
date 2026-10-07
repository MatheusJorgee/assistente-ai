"""
Pré-gate SEM LLM do pulso de presença (A4).

Antes, a cada ~50 min o pulso chamava o Gemini só para ele responder "NADA" na maioria das vezes:
créditos gastos para decidir ficar quieta. Aqui uma regra em Python decide se VALE a chamada:

  - tem uma descoberta nova para contar           -> acorda
  - o contexto mudou desde a última consulta      -> acorda (app em foco, jogo, chamada, apps abertos,
                                                    bateria baixa/carregando, CPU/RAM em pico)
  - faz muito tempo que não consulta (heartbeat)  -> acorda
  - em chamada ou tela cheia                      -> nunca acorda (ela não falaria mesmo)
  - senão                                         -> dorme (zero token)
"""

from typing import Any, Dict, Optional, Tuple

HEARTBEAT_S = 3 * 3600.0


def assinatura(snap: Dict[str, Any]) -> Tuple[Any, ...]:
    bateria = snap.get("bateria_pct")
    faixa_bat = None if bateria is None else ("baixa" if bateria <= 20 else "ok")
    return (
        snap.get("app_em_foco") or "",
        snap.get("jogo_rodando") or "",
        bool(snap.get("em_chamada")),
        tuple(snap.get("apps_abertos") or ()),
        faixa_bat,
        bool(snap.get("na_tomada")),
        (snap.get("cpu_pct") or 0) >= 90,
        (snap.get("ram_pct") or 0) >= 90,
    )


def deve_acordar(
    snap: Dict[str, Any],
    anterior: Optional[Tuple[Any, ...]],
    *,
    descoberta: Optional[str],
    agora: float,
    ultima_consulta: float,
) -> Tuple[bool, str]:
    """(acordar?, motivo). `ultima_consulta` = instante da última chamada ao LLM (0 = nunca)."""
    if snap.get("em_chamada") or snap.get("fullscreen"):
        return False, "em chamada ou tela cheia"
    if descoberta:
        return True, "descoberta nova"
    if anterior is None:
        return True, "primeira consulta"
    if assinatura(snap) != anterior:
        return True, "contexto mudou"
    if agora - ultima_consulta >= HEARTBEAT_S:
        return True, "heartbeat"
    return False, "nada mudou"


# ── A5: avaliador de aviso, fail-closed e sem custo de token ─────────────────
import re as _re
from typing import Iterable

_PALAVRA = _re.compile(r"\w{3,}", _re.UNICODE)
_VAZIOS = {"nada", "n/a", "none", "null", "silêncio", "silencio", "..."}


def _tokens(texto: str) -> set:
    return {t.lower() for t in _PALAVRA.findall(texto or "")}


def aviso_vale(texto: str, recentes: Iterable[str], *, limite_similar: float = 0.6) -> Tuple[bool, str]:
    """Última barreira antes de falar algo espontâneo. Na dúvida, NÃO avisa (fail-closed):
    vazio/"NADA", curto demais, longo demais (vira palestra) ou quase igual a algo já dito."""
    t = (texto or "").strip()
    if not t or t.lower().strip(" .!") in _VAZIOS:
        return False, "vazio"
    if len(t) < 8:
        return False, "curto demais"
    if len(t) > 400:
        return False, "longo demais para um aviso"
    novos = _tokens(t)
    for antigo in recentes:
        velhos = _tokens(antigo)
        if novos and velhos:
            sim = len(novos & velhos) / len(novos | velhos)
            if sim >= limite_similar:
                return False, "repete o que já foi dito"
    return True, "ok"
