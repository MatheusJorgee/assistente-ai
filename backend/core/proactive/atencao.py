"""
Gerente de atenção: quando NÃO falar.

O que fazia a Quinta parecer um alarme e não uma pessoa: a mesma condição anunciada de novo a cada
10-90 min, cooldowns que zeravam ao reiniciar, e nenhum teto de quantos avisos por hora. Uma pessoa
que avisa uma vez ("seu disco está cheio") e depois cala, ou espaça cada vez mais, ou só volta a falar
se a coisa PIOROU.

Regras (tudo local, sem LLM, e persistido em disco: reiniciar não zera a paciência dela):
  - Por assunto (chave): depois de avisar, o intervalo para repetir CRESCE (x3, teto de 24 h) enquanto a
    condição continua; quando a condição some (`resolvido`), o assunto zera e pode ser avisado de novo.
  - Piorou de verdade (`piorou=True`)? Pode repetir antes, mas nunca em menos de 10 min.
  - Global (só avisos espontâneos comuns): no mínimo 10 min entre dois avisos, no máximo 4 por hora e
    10 por dia. Críticos (bateria crítica, temperatura, madrugada) só obedecem o espaçamento por assunto.
  - Isentos de tudo: lembretes e ações que ELE agendou, saudação/despedida do dia.
  - Guarda também os últimos textos ditos, para o avaliador de repetição sobreviver ao reinício.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ISENTOS = {"lembrete", "agendado", "saudacao", "despedida"}
CRITICOS = {"bateria_critica", "temperatura", "madrugada"}
# Observações espontâneas variam a cada vez: só o teto global vale (sem backoff por assunto)
SO_GLOBAL = {"observacao"}

BASE_S = 3 * 3600.0          # 1º reaviso do mesmo assunto: 3 h depois
BASE_CRITICO_S = 20 * 60.0   # críticos: 20 min
FATOR = 3.0                  # cada repetição espaça x3
FATOR_CRITICO = 2.0
TETO_S = 24 * 3600.0
TETO_CRITICO_S = 3 * 3600.0
MIN_PIOROU_S = 10 * 60.0

GAP_GLOBAL_S = 10 * 60.0
MAX_POR_HORA = 4
MAX_POR_DIA = 10
RECENTES_MAX = 12

_DIR = Path(__file__).resolve().parents[2] / ".runtime"


class Atencao:
    def __init__(self, arquivo: Optional[Path] = None, reacao: Any = None) -> None:
        self._reacao = reacao   # Reacao (reacao.py): ajusta o intervalo pelo engajamento; None = neutro
        self._arq = Path(arquivo) if arquivo else _DIR / "atencao.json"
        self._lock = threading.Lock()
        self._assuntos: Dict[str, Dict[str, Any]] = {}   # chave -> {ultimo_ts, vezes}
        self._falas: List[float] = []                    # instantes das falas espontâneas comuns
        self.recentes: List[str] = []
        self._carregar()

    # ------------------------------------------------------------------ persistência

    def _carregar(self) -> None:
        try:
            d = json.loads(self._arq.read_text(encoding="utf-8"))
            self._assuntos = dict(d.get("assuntos", {}))
            self._falas = [float(x) for x in d.get("falas", [])]
            self.recentes = [str(x) for x in d.get("recentes", [])][-RECENTES_MAX:]
        except Exception:
            pass

    def _salvar(self) -> None:
        try:
            self._arq.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._arq.with_suffix(".tmp")
            tmp.write_text(json.dumps({"assuntos": self._assuntos, "falas": self._falas[-50:],
                                       "recentes": self.recentes[-RECENTES_MAX:]}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._arq)
        except OSError:
            pass

    # ------------------------------------------------------------------ decisão

    def _intervalo(self, chave: str, vezes: int) -> float:
        critico = chave in CRITICOS
        base, fator, teto = (BASE_CRITICO_S, FATOR_CRITICO, TETO_CRITICO_S) if critico else (BASE_S, FATOR, TETO_S)
        intervalo = min(teto, base * (fator ** max(0, vezes - 1)))
        if self._reacao is not None and not critico:
            intervalo = min(teto, intervalo * self._reacao.fator(chave))   # ignorado x4, respondido x0,75
        return intervalo

    def avaliar(self, chave: str, agora: Optional[float] = None, *, piorou: bool = False) -> Tuple[bool, str]:
        """Vale falar disso agora? Devolve (sim/não, motivo). Não altera nada."""
        agora = time.time() if agora is None else agora
        if chave in ISENTOS:
            return True, "isento"
        with self._lock:
            a = None if chave in SO_GLOBAL else self._assuntos.get(chave)
            if a:
                espera = MIN_PIOROU_S if piorou else self._intervalo(chave, int(a.get("vezes", 1)))
                falta = float(a["ultimo_ts"]) + espera - agora
                if falta > 0:
                    return False, f"já avisei disso; só de novo em {int(falta // 60)} min" + ("" if piorou else " (a menos que piore)")
            if chave not in CRITICOS:
                recentes = [t for t in self._falas if agora - t < 86400]
                if recentes and agora - max(recentes) < GAP_GLOBAL_S:
                    return False, "falei há pouco (espaçamento entre avisos)"
                if sum(1 for t in recentes if agora - t < 3600) >= MAX_POR_HORA:
                    return False, "muitos avisos nesta hora"
                if len(recentes) >= MAX_POR_DIA:
                    return False, "muitos avisos hoje"
        return True, "ok"

    def registrar(self, chave: str, texto: str = "", agora: Optional[float] = None) -> None:
        """Chame DEPOIS de falar."""
        agora = time.time() if agora is None else agora
        with self._lock:
            if texto:
                self.recentes.append(texto[:300])
                self.recentes = self.recentes[-RECENTES_MAX:]
            if chave not in ISENTOS:
                if chave not in SO_GLOBAL:
                    a = self._assuntos.setdefault(chave, {"vezes": 0, "ultimo_ts": agora})
                    a["vezes"] = int(a.get("vezes", 0)) + 1
                    a["ultimo_ts"] = agora
                if chave not in CRITICOS:
                    self._falas = [t for t in self._falas if agora - t < 86400] + [agora]
            self._salvar()

    def resolvido(self, chave: str) -> None:
        """A condição sumiu (RAM normalizou, internet voltou, ele fez uma pausa): o assunto zera."""
        with self._lock:
            if chave in self._assuntos:
                del self._assuntos[chave]
                self._salvar()

    def assuntos_ativos(self) -> Dict[str, int]:
        with self._lock:
            return {k: int(v.get("vezes", 0)) for k, v in self._assuntos.items()}


_instancia: Optional[Atencao] = None


def get_atencao() -> Atencao:
    global _instancia
    if _instancia is None:
        try:
            from .reacao import get_reacao
            _instancia = Atencao(reacao=get_reacao())
        except Exception:
            _instancia = Atencao()
    return _instancia
