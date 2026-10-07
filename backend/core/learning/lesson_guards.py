"""
Lições -> guardas (B13).

Uma lição em texto ("não me avise do clima") depende de o modelo lembrar de obedecer. Quando ela
volta a ser reforçada N vezes, vale virar REGRA em código. Aqui: recorrência >= N gera uma PROPOSTA de
guarda (heurística local, sem LLM); o Matheus aceita ou rejeita. Rejeitada nunca é reproposta.
Aceita vira regra que o monitor proativo aplica (bloquear um tipo de aviso).

Persistência: .runtime/lesson_guards.json. Tipos de aviso: clima, rede, observacao, disco.
"""

import hashlib
import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

RECORRENCIA_MIN = 3
TIPOS_BLOQUEAVEIS = {"clima": "clima", "rede": "rede", "internet": "rede", "disco": "disco",
                     "observac": "observacao", "comentario": "observacao"}
_GATILHOS = ("nao me avise", "nao avise", "para de avisar", "pare de avisar", "sem avisos", "nao fale sozinha",
             "nao comente", "para de comentar", "pare de comentar", "nao interrompa", "nao me interrompa", "avisos de")
_DIR = Path(__file__).resolve().parents[2] / ".runtime"


def _norm(t: str) -> str:
    sem = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in sem if unicodedata.category(c) != "Mn"))


def _id(texto: str) -> str:
    return hashlib.sha1(_norm(texto).encode("utf-8")).hexdigest()[:10]


def propor_regra(licao: str) -> Optional[Dict[str, str]]:
    """Regra de código que a lição sugere, ou None (lição que é só estilo: fica como texto)."""
    n = _norm(licao)
    if not any(g in n for g in _GATILHOS):
        return None
    for chave, tipo in TIPOS_BLOQUEAVEIS.items():
        if chave in n:
            return {"acao": "bloquear_aviso", "tipo": tipo}
    return {"acao": "bloquear_aviso", "tipo": "observacao"}  # "pare de comentar/avisar" genérico


class GuardStore:
    def __init__(self, pasta: Optional[Path] = None) -> None:
        self._arq = Path(pasta or _DIR) / "lesson_guards.json"
        self._lock = threading.Lock()

    def _ler(self) -> Dict[str, Any]:
        try:
            d = json.loads(self._arq.read_text(encoding="utf-8"))
            return {"propostas": list(d.get("propostas", []))}
        except Exception:
            return {"propostas": []}

    def _gravar(self, d: Dict[str, Any]) -> None:
        self._arq.parent.mkdir(parents=True, exist_ok=True)
        self._arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    def atualizar_propostas(self, licoes: List[Dict[str, Any]]) -> int:
        """Cria propostas para lições reforçadas >= N vezes. Devolve quantas novas."""
        novas = 0
        with self._lock:
            d = self._ler()
            existentes = {p["id"] for p in d["propostas"]}  # inclui rejeitadas: nunca repropõe
            for l in licoes:
                texto = str(l.get("texto", ""))
                if int(l.get("reforcos", 0)) + 1 < RECORRENCIA_MIN:  # 1ª vez + reforços
                    continue
                pid = _id(texto)
                regra = propor_regra(texto)
                if pid in existentes or not regra:
                    continue
                d["propostas"].append({"id": pid, "licao": texto[:140], "regra": regra, "status": "pendente"})
                novas += 1
            if novas:
                self._gravar(d)
        return novas

    def listar(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            ps = self._ler()["propostas"]
        return [p for p in ps if status is None or p["status"] == status]

    def decidir(self, pid: str, aceitar: bool) -> bool:
        with self._lock:
            d = self._ler()
            for p in d["propostas"]:
                if p["id"] == pid and p["status"] == "pendente":
                    p["status"] = "aceita" if aceitar else "rejeitada"
                    self._gravar(d)
                    return True
        return False

    def tipos_bloqueados(self) -> set:
        return {p["regra"]["tipo"] for p in self.listar("aceita") if p["regra"].get("acao") == "bloquear_aviso"}


_instancia: Optional[GuardStore] = None


def get_guard_store() -> GuardStore:
    global _instancia
    if _instancia is None:
        _instancia = GuardStore()
    return _instancia
