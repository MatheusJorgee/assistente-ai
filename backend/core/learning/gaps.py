"""
Registro de LACUNAS: onde a Quinta falha.

Ela só melhora onde sabe medir. Cada vez que algo dá errado (ferramenta falhou, ação negada por
falta de permissão, ferramenta que não existe, "não sei/não consigo", uma correção sua), grava-se uma
linha curta em .runtime/lacunas.jsonl: tipo, ferramenta, ação e uma CAUSA normalizada (sem números,
caminhos nem trechos entre aspas, para agrupar falhas iguais). Nada do que você disse é guardado, e
tokens/chaves/e-mails são mascarados. Tudo local, sem LLM.

`agrupar()` conta as falhas repetidas: é a matéria-prima da revisão semanal (self_review.py).
"""

import json
import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

TIPOS = ("erro_ferramenta", "negado", "ferramenta_inexistente", "nao_sei", "correcao")
_DIR = Path(__file__).resolve().parents[2] / ".runtime"
MAX_LINHAS = 2000
_lock = threading.Lock()

_SEGREDO = re.compile(
    r"(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{16,}|xox[bap]-[A-Za-z0-9\-]{10,}|ghp_[A-Za-z0-9]{20,}|\b\d{6,}:[A-Za-z0-9_\-]{20,}"
    r"|[\w.+-]+@[\w-]+\.[\w.-]+|(?i:(?:key|token|secret|senha|password)\s*[=:]\s*\S+))")
_VARIAVEL = re.compile(r"[A-Za-z]:\\[^\s'\"]+|(?<!\w)/[\w./-]{3,}|\d+|'[^']*'|\"[^\"]*\"")
_ESP = re.compile(r"\s+")

# frases em que ela admite um limite (para registrar "nao_sei")
_LIMITE = re.compile(
    r"(n[ãa]o (tenho|posso|consigo|sei como)|sem permiss[ãa]o|fora do (meu )?alcance|n[ãa]o (est[áa]|fui) autorizad)", re.I)


def mascarar(texto: str, limite: int = 160) -> str:
    return _ESP.sub(" ", _SEGREDO.sub("[oculto]", texto or "")).strip()[:limite]


def assinatura(causa: str) -> str:
    """Causa normalizada: falhas iguais com números/caminhos diferentes caem no mesmo grupo."""
    return _ESP.sub(" ", _VARIAVEL.sub("#", mascarar(causa, 200))).strip().lower()[:110]


def frase_de_limite(texto: str) -> str:
    """A frase da resposta em que ela admite não poder/saber (ou '' se não houver)."""
    for frase in re.split(r"(?<=[.!?])\s+|\n+", texto or ""):
        if _LIMITE.search(frase):
            return frase.strip()
    return ""


class LedgerLacunas:
    def __init__(self, arquivo: Optional[Path] = None) -> None:
        self._arq = Path(arquivo) if arquivo else _DIR / "lacunas.jsonl"

    def registrar(self, tipo: str, ferramenta: str = "", acao: str = "", causa: str = "",
                  agora: Optional[float] = None) -> bool:
        """Grava uma lacuna. Devolve False se ignorada (tipo inválido ou repetida há segundos)."""
        if tipo not in TIPOS:
            return False
        agora = time.time() if agora is None else agora
        reg = {"ts": agora, "tipo": tipo, "ferramenta": (ferramenta or "")[:40], "acao": (acao or "")[:30],
               "causa": assinatura(causa)}
        try:
            with _lock:
                ultimas = self._ler_linhas()[-15:]
                if any(r.get("tipo") == tipo and r.get("ferramenta") == reg["ferramenta"] and r.get("acao") == reg["acao"]
                       and r.get("causa") == reg["causa"] and agora - float(r.get("ts", 0)) < 30 for r in ultimas):
                    return False
                self._arq.parent.mkdir(parents=True, exist_ok=True)
                with self._arq.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                self._podar()
            return True
        except OSError:
            return False

    def _ler_linhas(self) -> List[Dict[str, Any]]:
        try:
            saida = []
            for bruto in self._arq.read_text(encoding="utf-8").splitlines():
                try:
                    saida.append(json.loads(bruto))
                except ValueError:
                    continue
            return saida
        except OSError:
            return []

    def _podar(self) -> None:
        linhas = self._ler_linhas()
        if len(linhas) > MAX_LINHAS + 500:
            self._arq.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in linhas[-MAX_LINHAS:]) + "\n", encoding="utf-8")

    def recentes(self, dias: float = 7.0, agora: Optional[float] = None) -> List[Dict[str, Any]]:
        agora = time.time() if agora is None else agora
        with _lock:
            return [r for r in self._ler_linhas() if agora - float(r.get("ts", 0)) <= dias * 86400]

    def agrupar(self, dias: float = 7.0, top: int = 10, agora: Optional[float] = None) -> List[Dict[str, Any]]:
        """Falhas repetidas, das mais frequentes para as menos: [{tipo, ferramenta, acao, causa, n}]."""
        c: Counter = Counter()
        for r in self.recentes(dias, agora):
            c[(r["tipo"], r.get("ferramenta", ""), r.get("acao", ""), r.get("causa", ""))] += 1
        return [{"tipo": t, "ferramenta": f, "acao": a, "causa": ca, "n": n}
                for (t, f, a, ca), n in c.most_common(max(1, top))]

    def total(self, dias: float = 7.0, agora: Optional[float] = None) -> int:
        return len(self.recentes(dias, agora))


_instancia: Optional[LedgerLacunas] = None


def get_ledger() -> LedgerLacunas:
    global _instancia
    if _instancia is None:
        _instancia = LedgerLacunas()
    return _instancia
