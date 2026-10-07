"""
MemoryConsolidation — faxina periódica da memória semântica.

Com o tempo ela acumula fatos repetidos ("interesse em finanças" aparece 2x) e
versões concorrentes do mesmo fato. Esta rotina relê todos os fatos e usa o LLM
pra decidir o que FUNDIR (mantém um, reescreve com o melhor de cada, apaga os
duplicados) — mantendo o recall enxuto e afiado em vez de ir inchando.

Conservadora: só funde o que é claramente o MESMO fato; na dúvida, mantém os dois.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

logger = get_logger(__name__)


class MemoryConsolidation:
    def __init__(self, *, brain: Any, memory_manager: Any) -> None:
        self._brain = brain
        self._memory = memory_manager
        self.last_run_ts: float = 0.0
        self.last_merged: int = 0

    async def consolidar(self) -> Dict[str, Any]:
        import time
        # Lê TODOS os fatos direto do banco (retrieve_memory capa em 100, e as
        # duplicatas antigas — justamente as que mais importam — ficariam de fora).
        try:
            try:
                from ..database import get_database
            except ImportError:
                from ..database import get_database
            db = await get_database()
            fatos = await db.query_all(
                "SELECT id, category, key, value FROM semantic_memories ORDER BY id ASC", ()
            )
        except Exception:
            mem = await self._memory.retrieve_memory(memory_type="semantic", limit=100)
            fatos = mem.get("semantic", [])
        if len(fatos) < 6:
            self.last_run_ts = time.time()
            return {"ok": True, "antes": len(fatos), "fundidos": 0, "motivo": "pouco pra consolidar"}
        # Se a lista for enorme, processa em blocos pra não estourar o prompt
        fatos = fatos[:140]

        # B10/custo: nada mudou desde a última faxina => nem chama o LLM
        from ..memory.origem import (
            _DIR, assinatura_fatos, gravar_assinatura, ler_assinatura, remocao_segura, salvar_preimagem,
        )
        arq_assinatura = _DIR.parent / "consolidacao_assinatura.txt"
        assinatura = assinatura_fatos(fatos)
        if ler_assinatura(arq_assinatura) == assinatura:
            self.last_run_ts = time.time()
            return {"ok": True, "antes": len(fatos), "fundidos": 0, "motivo": "nada mudou desde a última faxina"}

        listagem = "\n".join(
            f"[{f['id']}] ({f.get('category','')}) {str(f.get('value','')).strip()}"
            for f in fatos
        )
        system = (
            "Você é a Quinta-Feira fazendo faxina da própria memória. Abaixo, fatos que você "
            "guardou sobre o Matheus, cada um com um id. Encontre os que são o MESMO fato (duplicados "
            "ou versões concorrentes) e diga como consolidar: para cada grupo de duplicados, escolha UM "
            "id pra manter (com o valor final, fundindo o melhor de cada) e liste os outros ids pra "
            "remover. Seja CONSERVADORA: só funda o que é claramente a mesma informação; fatos "
            "diferentes ficam intocados (não precisa citá-los). Não invente fatos novos.\n"
            'Responda APENAS JSON: {"merges": [{"manter_id": N, "valor_final": "...", "remover_ids": [N, N]}]}'
        )
        try:
            from core.llm_provider import Message
        except ImportError:
            from ..llm_provider import Message
        try:
            resp = await self._brain.llm_provider.generate(
                messages=[Message(role="system", content=system),
                          Message(role="user", content=listagem)],
                # Folga generosa: thinking dinâmico do Gemini 2.5 consome o teto e
                # trunca o JSON (gotcha do projeto). Lista longa precisa de espaço.
                tools=None, temperature=0.2, max_tokens=6144,
            )
            data = self._parse_json_tolerante(resp.text or "")
        except Exception as exc:
            logger.warning(f"[CONSOLIDA] LLM falhou: {exc}")
            self.last_run_ts = time.time()
            return {"ok": False, "erro": str(exc)[:80]}

        ids_validos = {int(f["id"]) for f in fatos}
        # B10: o LLM pode errar (ou ser induzido): uma faxina que apagaria demais é descartada,
        # e antes de mexer guarda-se uma cópia (pré-imagem) para restaurar.
        a_remover = {int(i) for m in data.get("merges", []) for i in (m.get("remover_ids") or []) if str(i).lstrip("-").isdigit()}
        if not remocao_segura(len(fatos), len(a_remover)):
            logger.warning(f"[CONSOLIDA] abortada: apagaria {len(a_remover)} de {len(fatos)} fatos (suspeito)")
            self.last_run_ts = time.time()
            return {"ok": False, "erro": "faxina suspeita (apagaria fatos demais); nada foi alterado"}
        if data.get("merges"):
            salvar_preimagem(fatos)
        fundidos = 0
        for merge in data.get("merges", []):
            try:
                manter = int(merge.get("manter_id"))
                if manter not in ids_validos:
                    continue
                valor = str(merge.get("valor_final", "")).strip()
                remover = [int(i) for i in merge.get("remover_ids", []) if int(i) in ids_validos and int(i) != manter]
                if not remover:
                    continue
                if valor:
                    await self._memory.update_semantic_value(manter, valor, fonte=None)  # a faxina não se passa por você
                for rid in remover:
                    if await self._memory.delete_semantic(rid):
                        fundidos += 1
            except Exception as exc:
                logger.debug(f"[CONSOLIDA] merge falhou: {exc}")

        self.last_run_ts = time.time()
        self.last_merged = fundidos
        gravar_assinatura(arq_assinatura, assinatura if not fundidos else "")  # mudou: reavalia na próxima
        logger.info(f"[CONSOLIDA] {fundidos} fato(s) duplicado(s) removido(s) de {len(fatos)}")
        return {"ok": True, "antes": len(fatos), "fundidos": fundidos, "depois": len(fatos) - fundidos}

    @staticmethod
    def _parse_json_tolerante(txt: str) -> Dict[str, Any]:
        """Parse robusto: tenta o JSON inteiro; se truncou, extrai os objetos de
        merge completos um a um (resiste a resposta cortada pelo limite de tokens)."""
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        # Fallback: cata cada objeto {"manter_id":...,"remover_ids":[...]} válido
        merges = []
        for obj in re.findall(r"\{[^{}]*\"manter_id\"[^{}]*\}", txt, re.DOTALL):
            try:
                merges.append(json.loads(obj))
            except Exception:
                continue
        return {"merges": merges}
