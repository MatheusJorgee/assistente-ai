"""
StyleProfile — a Quinta-Feira aprendendo COMO falar com o Matheus.

A reflexão não extrai só fatos sobre ele; também olha as PRÓPRIAS falas dela
e as reações dele (respondeu animado? ignorou? foi seco? riu?) e destila
diretrizes de estilo ("ele prefere resposta curta quando está jogando",
"piada sobre X não colou — aposentar"). Essas diretrizes são injetadas em
todo prompt — é personalidade que amadurece com a convivência, em vez de
ficar congelada no system prompt.

Persistência: backend/.runtime/style_profile.json (máx. 8 diretrizes,
as mais novas substituem as mais antigas; duplicatas são ignoradas).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

_MAX_DIRETRIZES = 8


class StyleProfile:
    def __init__(self, runtime_dir: Optional[Path] = None) -> None:
        base = runtime_dir or (Path(__file__).resolve().parents[2] / ".runtime")
        self._file = Path(base) / "style_profile.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict[str, object]]:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return list(data.get("diretrizes", []))
        except Exception:
            return []

    def _save(self, diretrizes: List[Dict[str, object]]) -> None:
        try:
            self._file.write_text(
                json.dumps({"diretrizes": diretrizes}, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug(f"[ESTILO] Falha ao salvar: {exc}")

    def add_many(self, textos: List[str]) -> int:
        """Adiciona diretrizes novas (dedupe leve); mantém as 8 mais recentes."""
        diretrizes = self._load()
        existentes = {str(d.get("texto", "")).strip().lower() for d in diretrizes}
        novas = 0
        for t in textos:
            t = (t or "").strip()
            if not t or len(t) < 8 or t.lower() in existentes:
                continue
            diretrizes.append({"texto": t[:180], "ts": time.time()})
            existentes.add(t.lower())
            novas += 1
        if novas:
            diretrizes = sorted(diretrizes, key=lambda d: d.get("ts", 0))[-_MAX_DIRETRIZES:]
            self._save(diretrizes)
            logger.info(f"[ESTILO] {novas} diretriz(es) nova(s) de estilo aprendida(s)")
        return novas

    def to_prompt(self) -> str:
        diretrizes = self._load()
        if not diretrizes:
            return ""
        linhas = "\n".join(f"- {d.get('texto', '')}" for d in diretrizes[-_MAX_DIRETRIZES:])
        return (
            "[ESTILO APRENDIDO — ajustes de comportamento que VOCÊ mesma concluiu "
            "observando as reações do Matheus na convivência. Siga-os; eles vencem "
            "instruções genéricas de personalidade]\n"
            f"{linhas}\n[/ESTILO APRENDIDO]"
        )


_instance: Optional[StyleProfile] = None


def get_style_profile() -> StyleProfile:
    global _instance
    if _instance is None:
        _instance = StyleProfile()
    return _instance
