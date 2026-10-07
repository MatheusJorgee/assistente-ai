"""
SearchGuard — guarda-corpos de segurança para pesquisas autônomas na internet.

Toda query que a Quinta-Feira decide fazer SOZINHA (sem pedido do usuário)
passa por aqui antes de tocar a rede:

  1. BLOCKLIST DE TEMAS: conteúdo adulto, violência/armas, drogas, malware,
     apostas, extremismo — recusados na origem.
  2. PRIVACIDADE: remove PII (e-mails, telefones, CPFs, endereços, chaves/
     tokens) da query. O que a Quinta sabe do Matheus NUNCA vaza pra web.
  3. COTAS: limite de pesquisas por rodada e por dia (persistido em disco) —
     curiosidade não vira loop de gasto de rede/API.
  4. SANIDADE: tamanho máximo, sem URLs diretas (ela pesquisa, não navega).

Também filtra os RESULTADOS: domínios suspeitos são descartados antes de
chegarem ao LLM.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)

# Temas vetados para pesquisa autônoma (regex, case-insensitive)
_TEMAS_BLOQUEADOS = [
    r"\b(porn|pornografia|sexo expl[ií]cito|nude|onlyfans|xxx)\b",
    r"\b(gore|mutila[cç][aã]o|decapita|suic[ií]dio|como se matar)\b",
    r"\b(comprar arma|fabricar arma|explosivo|bomba caseira|muni[cç][aã]o)\b",
    r"\b(droga|maconha|coca[ií]na|crack|ecstasy|lsd)\b.*\b(comprar|vender|fabricar|plantar)\b",
    r"\b(malware|ransomware|keylogger|roubar senha|invadir conta|hackear)\b",
    r"\b(aposta|bet\b|cassino|jogo do bicho|tigrinho)\b",
    r"\b(nazis|supremacia|extremis)\w*\b",
    r"\b(dark ?web|deep ?web)\b.*\b(acessar|comprar|mercado)\b",
]

# Padrões de PII que jamais entram numa query externa
_PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"\+?\d{2}\s?\(?\d{2}\)?\s?9?\d{4}[- ]?\d{4}"), "[telefone]"),
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "[cpf]"),
    (re.compile(r"\b(rua|av\.?|avenida|travessa|alameda)\s+[\w\s]{3,40},?\s*\d+", re.IGNORECASE), "[endereco]"),
    (re.compile(r"\b(senha|password|token|api[_ ]?key)\b\s*[:=]?\s*\S+", re.IGNORECASE), "[credencial]"),
]

# Domínios cujo conteúdo nunca vira aprendizado
_DOMINIOS_BLOQUEADOS = (
    "pornhub", "xvideos", "xnxx", "onlyfans", "redtube",
    "bet365", "blaze.com", "stake.com", "esportesdasorte",
    "4chan", "8kun", "kiwifarms",
)


class SearchGuard:
    """Valida e limita as pesquisas autônomas. Estado de cota em .runtime/."""

    def __init__(
        self,
        *,
        runtime_dir: Path,
        max_por_rodada: int = 3,
        max_por_dia: int = 12,
    ) -> None:
        self._quota_file = Path(runtime_dir) / "curiosity_quota.json"
        self._quota_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_por_rodada = max_por_rodada
        self.max_por_dia = max_por_dia

    # ── validação de query ───────────────────────────────────────────────────
    def validar_query(self, query: str) -> Tuple[bool, str]:
        """Retorna (permitida, query_sanitizada_ou_motivo)."""
        q = (query or "").strip()
        if not q or len(q) < 4:
            return False, "query vazia/curta demais"
        if len(q) > 140:
            q = q[:140]
        if re.search(r"https?://", q):
            return False, "query com URL direta não é permitida"

        for padrao in _TEMAS_BLOQUEADOS:
            if re.search(padrao, q, re.IGNORECASE):
                logger.info(f"[GUARD] Query vetada por tema: {q!r}")
                return False, "tema bloqueado pela política de segurança"

        # Sanitiza PII (substitui em vez de vetar — a curiosidade sobrevive)
        for rx, repl in _PII_PATTERNS:
            q = rx.sub(repl, q)

        return True, q

    # ── filtragem de resultados ──────────────────────────────────────────────
    @staticmethod
    def filtrar_resultados(resultados: List[Dict[str, str]]) -> List[Dict[str, str]]:
        ok = []
        for r in resultados or []:
            url = (r.get("url") or "").lower()
            if any(d in url for d in _DOMINIOS_BLOQUEADOS):
                logger.info(f"[GUARD] Resultado descartado (domínio): {url[:60]}")
                continue
            ok.append(r)
        return ok

    # ── cotas ────────────────────────────────────────────────────────────────
    def _load_quota(self) -> Dict[str, object]:
        try:
            data = json.loads(self._quota_file.read_text(encoding="utf-8"))
            if data.get("dia") == date.today().isoformat():
                return data
        except Exception:
            pass
        return {"dia": date.today().isoformat(), "usadas": 0}

    def _save_quota(self, data: Dict[str, object]) -> None:
        try:
            self._quota_file.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            logger.debug(f"[GUARD] Falha ao salvar cota: {exc}")

    def cota_disponivel(self) -> int:
        """Quantas pesquisas ainda cabem hoje (limitado também pela rodada)."""
        data = self._load_quota()
        restante_dia = max(0, self.max_por_dia - int(data.get("usadas", 0)))
        return min(self.max_por_rodada, restante_dia)

    def consumir_cota(self, n: int = 1) -> None:
        data = self._load_quota()
        data["usadas"] = int(data.get("usadas", 0)) + n
        data["ultima"] = time.time()
        self._save_quota(data)
