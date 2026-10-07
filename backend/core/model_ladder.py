"""
Escada de modelos com "esgotado até T" (A6).

Quando a cota de um modelo acaba (HTTP 429 / RESOURCE_EXHAUSTED), tentar de novo o mesmo modelo a
cada mensagem só gasta tempo: a Quinta ficaria muda esperando o erro voltar. Aqui o modelo esgotado
sai da fila por alguns minutos e a chamada cai direto para o próximo da escada
(escolhido -> padrão -> lite). Se TODOS estão em cooldown, tenta o que volta primeiro (melhor
tentar do que ficar muda).

Estado só em memória (some ao reiniciar, que é o certo: a cota pode ter voltado).
"""

import re
import threading
import time
from typing import Dict, Iterable, List, Optional

COOLDOWN_PADRAO_S = 300.0
COOLDOWN_MAX_S = 3600.0

_lock = threading.Lock()
_ate: Dict[str, float] = {}  # modelo -> instante (monotonic) em que volta a valer

_RE_RETRY = re.compile(r"retry(?:Delay|_delay)?\D{0,12}?(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def eh_cota(exc: BaseException) -> bool:
    """O erro é de cota/limite de taxa (e não de nome de modelo errado, rede etc.)?"""
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if codigo == 429:
        return True
    texto = f"{type(exc).__name__} {exc}".upper()
    return "RESOURCE_EXHAUSTED" in texto or " 429" in texto or "QUOTA" in texto


def _espera_sugerida(exc: BaseException) -> Optional[float]:
    m = _RE_RETRY.search(str(exc))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def marcar_esgotado(modelo: str, segundos: Optional[float] = None, *, agora: Optional[float] = None) -> float:
    """Tira o modelo da fila. Devolve por quantos segundos."""
    dur = max(30.0, min(COOLDOWN_MAX_S, segundos if segundos else COOLDOWN_PADRAO_S))
    t = time.monotonic() if agora is None else agora
    with _lock:
        _ate[modelo] = t + dur
    return dur


def marcar_por_erro(modelo: str, exc: BaseException) -> Optional[float]:
    """Se o erro é de cota, marca o modelo (respeitando o 'retry in Ns' do erro, com teto)."""
    if not eh_cota(exc):
        return None
    return marcar_esgotado(modelo, _espera_sugerida(exc))


def restante(modelo: str, *, agora: Optional[float] = None) -> float:
    t = time.monotonic() if agora is None else agora
    with _lock:
        return max(0.0, _ate.get(modelo, 0.0) - t)


def escada(preferido: str, alternativas: Iterable[str], *, agora: Optional[float] = None) -> List[str]:
    """Ordem de tentativa: [preferido, *alternativas] sem repetição e sem os esgotados.
    Se todos estão esgotados, devolve todos, do que volta primeiro para o que volta por último."""
    todos: List[str] = []
    for m in [preferido, *alternativas]:
        if m and m not in todos:
            todos.append(m)
    livres = [m for m in todos if restante(m, agora=agora) <= 0]
    if livres:
        return livres
    return sorted(todos, key=lambda m: restante(m, agora=agora))


def limpar() -> None:
    with _lock:
        _ate.clear()
