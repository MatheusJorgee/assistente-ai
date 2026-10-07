"""
Portão de origem e pré-imagem da memória (B10). Tudo local, sem LLM.

- `sem_conteudo_externo`: a reflexão NÃO aprende com texto de terceiros (mensagem de WhatsApp,
  página, documento) que apareceu na conversa: uma injeção ali viraria "fato sobre o Matheus".
  Também tira tokens do prompt da reflexão.
- `salvar_preimagem`: antes de a consolidação reescrever/apagar fatos, guarda uma cópia para poder
  restaurar (só as últimas N).
- `assinatura_fatos`: se nada mudou desde a última consolidação, nem chama o LLM.
"""

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_BLOCO = re.compile(r"\[CONTEÚDO EXTERNO NÃO CONFIÁVEL.*?\[/CONTEÚDO EXTERNO\]", re.S)
_DIR = Path(__file__).resolve().parents[2] / "data" / "memoria_preimagem"
MANTER = 7
FRACAO_MAX_REMOVIDA = 0.30  # uma faxina que apagaria mais que isso é suspeita: aborta


def sem_conteudo_externo(texto: str) -> Tuple[str, int]:
    """(texto sem os blocos de conteúdo externo, quantos blocos foram removidos)."""
    limpo, n = _BLOCO.subn("[conteúdo externo omitido]", texto or "")
    return limpo, n


def assinatura_fatos(fatos: Iterable[Dict[str, Any]]) -> str:
    linhas = sorted(f"{f.get('id')}|{f.get('category', '')}|{str(f.get('value', '')).strip()}" for f in fatos)
    return hashlib.sha256("\n".join(linhas).encode("utf-8")).hexdigest()


def salvar_preimagem(fatos: List[Dict[str, Any]], pasta: Optional[Path] = None, manter: int = MANTER) -> Path:
    pasta = pasta or _DIR
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"fatos_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.json"
    arq.write_text(json.dumps(fatos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    antigos = sorted(pasta.glob("fatos_*.json"))
    for velho in antigos[:-manter]:
        velho.unlink(missing_ok=True)
    return arq


def ler_assinatura(arq: Path) -> str:
    try:
        return arq.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def gravar_assinatura(arq: Path, assinatura: str) -> None:
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(assinatura, encoding="utf-8")
    except OSError:
        pass


def remocao_segura(total_fatos: int, ids_a_remover: int) -> bool:
    """A faxina não pode apagar mais que a fração máxima (mínimo de 3 permitidos)."""
    return ids_a_remover <= max(3, int(total_fatos * FRACAO_MAX_REMOVIDA))
