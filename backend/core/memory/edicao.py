"""
Edição da memória pela tela (B12) e "ontem você falou de…" do briefing. Tudo local, sem LLM.
"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional

VALOR_MAX = 500


def validar_valor(valor: Any) -> Optional[str]:
    """Texto limpo do novo valor de um fato, ou None se inválido (vazio, não-texto, gigante)."""
    if not isinstance(valor, str):
        return None
    limpo = " ".join(valor.split())
    if not limpo or len(limpo) > VALOR_MAX:
        return None
    return limpo


def _data(ts: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def linha_ontem(episodicas: Iterable[Dict[str, Any]], hoje: date) -> str:
    """Resumo do diário mais recente ANTES de hoje (a linha "ontem você falou de…"), ou ''.
    Só olha diários com até 3 dias: coisa velha não é "ontem"."""
    melhor: Optional[Dict[str, Any]] = None
    melhor_data: Optional[date] = None
    for m in episodicas:
        if m.get("event_type") != "diario":
            continue
        d = _data(m.get("created_at"))
        if d is None or d >= hoje or (hoje - d).days > 3:
            continue
        if melhor_data is None or d > melhor_data:
            melhor, melhor_data = m, d
    if not melhor:
        return ""
    resumo = " ".join(str(melhor.get("summary", "")).split())[:400]
    return f"DO SEU DIÁRIO (dia anterior): {resumo}" if resumo else ""
