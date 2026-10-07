"""
Reação às falas espontâneas: ela aprende quais avisos você quer ouvir.

Depois de falar algo por conta própria, a Quinta observa o desfecho:
  - `respondida`: você escreveu/falou com ela em até 2 minutos;
  - `ignorada`: passou o tempo e você não reagiu.
Cada TIPO de aviso (clima, pausa, observação, pendência...) mantém uma média móvel de engajamento. Tipo
que você quase sempre ignora passa a ser dito com intervalos maiores (até x4); tipo que você responde
volta um pouco mais cedo (x0,75). Nunca cala de vez (o backoff e o teto global continuam valendo) e os
avisos críticos, lembretes e o que você agendou ficam de fora: isso não é "preferência", é o combinado.

Persistido; local; zero chamadas de modelo; visível no painel.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

JANELA_RESPOSTA_S = 120.0
JANELA_IGNORADA_S = 600.0
ALFA = 0.25
MIN_AMOSTRAS = 3
FATOR_MIN, FATOR_MAX = 0.75, 4.0
_DIR = Path(__file__).resolve().parents[2] / ".runtime"


class Reacao:
    def __init__(self, arquivo: Optional[Path] = None) -> None:
        self._arq = Path(arquivo) if arquivo else _DIR / "reacao.json"
        self._lock = threading.Lock()
        self._tipos: Dict[str, Dict[str, float]] = {}
        self._pendentes: List[Dict[str, Any]] = []
        self._carregar()

    def _carregar(self) -> None:
        try:
            d = json.loads(self._arq.read_text(encoding="utf-8"))
            self._tipos = {k: {"ewma": float(v["ewma"]), "n": float(v["n"])} for k, v in d.get("tipos", {}).items()}
            self._pendentes = list(d.get("pendentes", []))
        except Exception:
            pass

    def _salvar(self) -> None:
        try:
            self._arq.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._arq.with_suffix(".tmp")
            tmp.write_text(json.dumps({"tipos": self._tipos, "pendentes": self._pendentes[-20:]}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._arq)
        except OSError:
            pass

    def _aprender(self, tipo: str, engajou: float) -> None:
        t = self._tipos.setdefault(tipo, {"ewma": 0.5, "n": 0.0})
        t["ewma"] = (1 - ALFA) * t["ewma"] + ALFA * engajou
        t["n"] += 1

    def _resolver_expirados(self, agora: float) -> None:
        restantes = []
        for p in self._pendentes:
            if agora - p["ts"] >= JANELA_IGNORADA_S:
                self._aprender(p["tipo"], 0.0)          # ninguém reagiu a tempo: ignorada
            else:
                restantes.append(p)
        self._pendentes = restantes

    def registrar_fala(self, tipo: str, agora: Optional[float] = None) -> None:
        agora = time.time() if agora is None else agora
        with self._lock:
            self._resolver_expirados(agora)
            self._pendentes.append({"tipo": tipo, "ts": agora})
            self._salvar()

    def usuario_falou(self, agora: Optional[float] = None) -> int:
        """O Matheus escreveu/falou: as falas espontâneas recentes contam como respondidas."""
        agora = time.time() if agora is None else agora
        n = 0
        with self._lock:
            self._resolver_expirados(agora)
            restantes = []
            for p in self._pendentes:
                if agora - p["ts"] <= JANELA_RESPOSTA_S:
                    self._aprender(p["tipo"], 1.0)
                    n += 1
                else:
                    restantes.append(p)   # entre 2 e 10 min: ainda pode virar ignorada, não é resposta
            self._pendentes = restantes
            if n:
                self._salvar()
        return n

    def fator(self, tipo: str, agora: Optional[float] = None) -> float:
        """Multiplicador do intervalo de repetição do tipo (1.0 = neutro)."""
        with self._lock:
            self._resolver_expirados(time.time() if agora is None else agora)
            t = self._tipos.get(tipo)
        if not t or t["n"] < MIN_AMOSTRAS:
            return 1.0
        e = t["ewma"]
        if e < 0.15:
            f = 4.0
        elif e < 0.35:
            f = 2.0
        elif e > 0.7:
            f = 0.75
        else:
            f = 1.0
        return max(FATOR_MIN, min(FATOR_MAX, f))

    def resumo(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {k: {"engajamento": round(v["ewma"], 2), "amostras": int(v["n"])} for k, v in self._tipos.items()}


_instancia: Optional[Reacao] = None


def get_reacao() -> Reacao:
    global _instancia
    if _instancia is None:
        _instancia = Reacao()
    return _instancia
