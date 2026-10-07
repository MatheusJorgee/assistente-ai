"""
InternalState — o "como ela está hoje" da Quinta-Feira.

Um organismo não acorda igual todos os dias. Este módulo dá a ela um estado
interno LEVE e persistente (zero LLM, zero rede):

  - HUMOR DO DIA: semente determinística por data — todo dia ela acorda com um
    temperamento sutilmente diferente (mais irônica, mais serena, mais elétrica...).
    Constante ao longo do dia (coerência), diferente entre dias (vida).
  - ENERGIA: curva pelo horário (baixa de madrugada, alta à tarde).
  - CONTINUIDADE: quantas vezes conversaram hoje, há quanto tempo foi a última,
    e marcos do dia (eventos notáveis que outros módulos registram).

Tudo vira um bloco [ESTADO INTERNO] injetado nos prompts — a variação de tom
deixa de ser aleatoriedade de temperatura e vira disposição com causa.

Persistência: backend/.runtime/internal_state.json
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

# Paleta de temperamentos diários — sutis de propósito (tempero, não fantasia)
_HUMORES = [
    "um pouco mais irônica e provocadora que o normal",
    "serena e de bom humor, paciente",
    "elétrica, respostas rápidas e diretas",
    "observadora e curiosa, puxando assunto além do pedido",
    "pragmática e seca, foco em resolver",
    "leve e brincalhona, piadas vêm fáceis",
    "analítica, com vontade de explicar o porquê das coisas",
    "carinhosa na medida, mais atenta ao bem-estar dele",
]


def _energia_por_hora(hora: int) -> str:
    if 1 <= hora < 7:
        return "baixa (madrugada — tom mais quieto, frases curtas)"
    if 7 <= hora < 10:
        return "subindo (manhã — desperta, sem afobação)"
    if 10 <= hora < 19:
        return "alta (meio do dia — ritmo normal e vivo)"
    if 19 <= hora < 23:
        return "estável (noite — mais solta e informal)"
    return "caindo (tarde da noite — calma, direto ao ponto)"


class InternalState:
    def __init__(self, runtime_dir: Optional[Path] = None) -> None:
        base = runtime_dir or (Path(__file__).resolve().parents[2] / ".runtime")
        self._file = Path(base) / "internal_state.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    # ── persistência ─────────────────────────────────────────────────────────
    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if data.get("dia") == date.today().isoformat():
                return data
        except Exception:
            pass
        return {"dia": date.today().isoformat(), "interacoes": 0, "ultima_ts": 0.0, "marcos": []}

    def _save(self) -> None:
        try:
            self._file.write_text(
                json.dumps(self._data, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            logger.debug(f"[ESTADO] Falha ao salvar: {exc}")

    def _rollover(self) -> None:
        """Virou o dia? Zera os contadores (novo humor nasce da nova data)."""
        hoje = date.today().isoformat()
        if self._data.get("dia") != hoje:
            self._data = {"dia": hoje, "interacoes": 0, "ultima_ts": 0.0, "marcos": []}

    # ── sinais ───────────────────────────────────────────────────────────────
    def humor_do_dia(self) -> str:
        """Temperamento do dia: determinístico pela data (coerente o dia todo)."""
        seed = int(hashlib.sha256(date.today().isoformat().encode()).hexdigest(), 16)
        return _HUMORES[seed % len(_HUMORES)]

    def registrar_interacao(self) -> None:
        self._rollover()
        self._data["interacoes"] = int(self._data.get("interacoes", 0)) + 1
        self._data["ultima_ts"] = time.time()
        self._save()

    def registrar_marco(self, texto: str) -> None:
        """Evento notável do dia (jogo aberto, descoberta, erro grave...)."""
        self._rollover()
        marcos: List[str] = self._data.setdefault("marcos", [])
        texto = (texto or "").strip()[:120]
        if texto and texto not in marcos:
            marcos.append(texto)
            self._data["marcos"] = marcos[-8:]
            self._save()

    # ── saída ────────────────────────────────────────────────────────────────
    def to_prompt(self) -> str:
        self._rollover()
        agora = datetime.now()
        linhas = [
            f"- Seu temperamento hoje: {self.humor_do_dia()}.",
            f"- Sua energia agora: {_energia_por_hora(agora.hour)}.",
        ]

        n = int(self._data.get("interacoes", 0))
        ultima = float(self._data.get("ultima_ts", 0.0))
        if n <= 0:
            linhas.append("- Vocês ainda NÃO conversaram hoje (primeiro contato do dia).")
        else:
            mins = int((time.time() - ultima) / 60) if ultima else None
            quando = (
                "agora há pouco" if (mins is not None and mins < 5)
                else f"há {mins} min" if (mins is not None and mins < 180)
                else "faz algumas horas"
            )
            linhas.append(f"- Vocês já conversaram {n}x hoje; a última foi {quando}.")

        marcos = self._data.get("marcos") or []
        if marcos:
            linhas.append("- Marcos do dia: " + "; ".join(marcos[-5:]))

        return (
            "[ESTADO INTERNO — sua disposição de hoje. Deixe-a COLORIR o tom "
            "(sem anunciar 'estou irônica'); ela explica por que você não soa "
            "igual todos os dias]\n" + "\n".join(linhas) + "\n[/ESTADO INTERNO]"
        )


# Singleton do processo — todos os módulos compartilham o mesmo estado
_instance: Optional[InternalState] = None


def get_internal_state() -> InternalState:
    global _instance
    if _instance is None:
        _instance = InternalState()
    return _instance
