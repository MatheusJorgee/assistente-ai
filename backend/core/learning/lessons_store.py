"""
LessonsStore — a Quinta-Feira aprendendo com as CORRECOES do Matheus.

Quando ele corrige algo ("nao era assim", "na verdade..."), o brain destila uma regra de
COMPORTAMENTO curta e generalizavel ("nao responda com lista quando ele pergunta rapido")
e guarda aqui. As licoes entram em toda resposta, entao o erro nao se repete na proxima
sessao. Fato pontual ("o nome dela e Yngrid") continua indo pra memoria semantica.

Regras de seguranca:
- so nasce de fala DIRETA dele (o brain nao aprende de mensagens automaticas/de terceiros);
- texto sanitizado (uma linha, teto de tamanho);
- correcao repetida REFORCA a licao existente em vez de duplicar;
- ele pode ver (GET /licoes) e apagar (DELETE /licoes/{i}).

Persistencia: backend/.runtime/lessons.json (max 12 licoes; as menos reforcadas e mais
antigas saem primeiro).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_MAX_LICOES = 12
_MAX_NO_PROMPT = 8
_MAX_CHARS = 140
_STOP = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "um",
    "uma", "que", "pra", "para", "com", "por", "se", "nao", "não", "ele", "quando",
}


def _tokens(texto: str) -> set:
    return {w for w in re.findall(r"[a-zà-ú0-9]+", (texto or "").lower()) if w not in _STOP and len(w) > 2}


def _sanitizar(texto: str) -> str:
    t = re.sub(r"\s+", " ", (texto or "")).strip().strip("\"'`-• ")
    return t[:_MAX_CHARS]


class LessonsStore:
    def __init__(self, runtime_dir: Optional[Path] = None) -> None:
        base = runtime_dir or (Path(__file__).resolve().parents[2] / ".runtime")
        self._file = Path(base) / "lessons.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict[str, object]]:
        try:
            return list(json.loads(self._file.read_text(encoding="utf-8")).get("licoes", []))
        except Exception:
            return []

    def _save(self, licoes: List[Dict[str, object]]) -> None:
        try:
            self._file.write_text(
                json.dumps({"licoes": licoes}, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception as exc:
            logger.debug(f"[LICOES] Falha ao salvar: {exc}")

    def registrar(self, texto: str) -> str:
        """Guarda uma licao. Retorna 'nova', 'reforcada' ou 'ignorada'."""
        texto = _sanitizar(texto)
        if len(texto) < 12 or texto.upper().startswith("NENHUMA"):
            return "ignorada"
        licoes = self._load()
        novo = _tokens(texto)
        for l in licoes:
            existente = _tokens(str(l.get("texto", "")))
            if novo and existente and len(novo & existente) / len(novo | existente) >= 0.5:
                l["reforcos"] = int(l.get("reforcos", 0)) + 1
                l["ts"] = time.time()
                self._save(licoes)
                logger.info(f"[LICOES] Licao reforcada: {l.get('texto')}")
                return "reforcada"
        licoes.append({"texto": texto, "ts": time.time(), "reforcos": 0})
        if len(licoes) > _MAX_LICOES:
            licoes.sort(key=lambda d: (int(d.get("reforcos", 0)), float(d.get("ts", 0))), reverse=True)
            licoes = licoes[:_MAX_LICOES]
        self._save(licoes)
        logger.info(f"[LICOES] Licao nova: {texto}")
        return "nova"

    def listar(self) -> List[Dict[str, object]]:
        return self._load()

    def remover(self, indice: int) -> bool:
        licoes = self._load()
        if 0 <= indice < len(licoes):
            licoes.pop(indice)
            self._save(licoes)
            return True
        return False

    def to_prompt(self) -> str:
        licoes = self._load()
        if not licoes:
            return ""
        licoes.sort(key=lambda d: (int(d.get("reforcos", 0)), float(d.get("ts", 0))), reverse=True)
        linhas = "\n".join(f"- {d.get('texto', '')}" for d in licoes[:_MAX_NO_PROMPT])
        return (
            "[LIÇÕES QUE O MATHEUS ME ENSINOU — correções dele que valem SEMPRE; "
            "nunca repita esses erros]\n"
            f"{linhas}\n[/LIÇÕES]"
        )


_instance: Optional[LessonsStore] = None


def get_lessons_store() -> LessonsStore:
    global _instance
    if _instance is None:
        _instance = LessonsStore()
    return _instance
