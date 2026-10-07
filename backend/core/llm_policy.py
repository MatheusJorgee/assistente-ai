"""
Politica de custo do LLM: que modelo e quanto raciocinio cada FUNCAO merece.

Antes, toda chamada sem `thinking_budget` explicito herdava o global (-1 = dinamico).
Medido em 2026-09-20: um aviso proativo de 33 tokens de fala gastava 980 tokens
pensando (cobrados como saida, US$2,50/M) — 30x a fala — e o classificador de
enderecamento gastava 242 pra dar o mesmo veredicto que com raciocinio zero.

A funcao que chama o generate() e descoberta pela pilha (nenhum call site precisa mudar);
`purpose=` explicito no generate() sempre vence. Funcao desconhecida = comportamento antigo.
"""

import sys
from dataclasses import dataclass
from typing import Optional

TIER_LITE = "lite"        # classificadores e resumos: modelo mais barato
TIER_PADRAO = "padrao"    # modelo configurado (GEMINI_MODEL)
TIER_FORTE = "forte"      # so onde compensa: objetivos multi-passo (modo agente)


@dataclass(frozen=True)
class Politica:
    tier: str = TIER_PADRAO
    # None = nao interfere (vale o que o chamador passou ou o THINKING_BUDGET global)
    thinking: Optional[int] = None
    max_tokens_min: int = 0


# chave = "modulo.funcao" (ou so "funcao"); modulo = ultimo segmento do nome do modulo.
_POLITICAS = {
    # Falas curtas de persona (1-2 frases): raciocinio so gasta token.
    "quinta_feira_brain.gerar_aviso_contextual": Politica(thinking=0),
    "quinta_feira_brain.decidir_observacao": Politica(thinking=0),
    "quinta_feira_brain.puxar_assunto": Politica(thinking=0),
    "quinta_feira_brain.gerar_aviso": Politica(thinking=0),
    "quinta_feira_brain._comentar_acao": Politica(thinking=0),
    "quinta_feira_brain.gerar_narracao_noticias": Politica(thinking=0),
    "quinta_feira_brain.montar_briefing": Politica(thinking=0),
    "quinta_feira_brain.contar_o_dia": Politica(thinking=0),
    "briefing_service.gerar_briefing": Politica(thinking=0),
    "draft_tool.execute": Politica(thinking=0),
    # Classificador chamado a cada fala captada no modo ambiente: alta frequencia, JSON curto.
    "quinta_feira_brain.classificar_enderecamento": Politica(tier=TIER_LITE, thinking=0),
    # Destilar uma regra curta de uma correcao: so acontece quando ele corrige, tarefa simples.
    "quinta_feira_brain._aprender_licao": Politica(tier=TIER_LITE, thinking=0),
    # Compressao de historico (resumo).
    "sliding_window_context.compress": Politica(tier=TIER_LITE, thinking=0),
    # Extracao estruturada: um pouco de raciocinio ajuda, mas com TETO (o dinamico e ilimitado).
    "reflection_service.refletir": Politica(thinking=1024, max_tokens_min=4096),
    "memory_consolidation.consolidar": Politica(thinking=1024),
    # Revisão semanal das próprias falhas: 1 chamada/semana, modelo leve, sem raciocínio.
    "self_review.revisar": Politica(tier=TIER_LITE, thinking=0),
    # Avaliação de regressão: só quando o Matheus pede, 1 chamada por caso (máx. 10), sem raciocínio.
    "regressao.rodar_avaliacao": Politica(thinking=0),
    # Ler a tela com imagem: 1 chamada por "analisar", só quando o modelo/você pede; sem raciocínio.
    "vision_tool._analisar": Politica(thinking=0),
    # Trabalho de bastidor (madrugada): até 2 chamadas por noite, modelo leve, sem raciocínio.
    "bastidor.preparar_uma": Politica(tier=TIER_LITE, thinking=0),
    "curiosity_service._escolher_pesquisas": Politica(thinking=0),
    "curiosity_service._destilar": Politica(thinking=1024),
    "document_tool.execute": Politica(thinking=512),
}

_PADRAO = Politica()
_MODULOS_IGNORADOS = {"llm_policy", "gemini_provider", "llm_provider", "token_ledger"}


def politica_para(proposito: str) -> Politica:
    """Politica do proposito ('modulo.funcao'). Desconhecido -> sem interferir."""
    if not proposito:
        return _PADRAO
    if proposito in _POLITICAS:
        return _POLITICAS[proposito]
    funcao = proposito.rsplit(".", 1)[-1]
    return _POLITICAS.get(funcao, _PADRAO)


def inferir_proposito(profundidade_inicial: int = 2) -> str:
    """'modulo.funcao' de quem chamou o generate(), pulando frames do proprio provider."""
    try:
        frame = sys._getframe(profundidade_inicial)
        while frame is not None:
            modulo = str(frame.f_globals.get("__name__", "")).rsplit(".", 1)[-1]
            if modulo not in _MODULOS_IGNORADOS:
                return f"{modulo}.{frame.f_code.co_name}"
            frame = frame.f_back
    except Exception:
        pass
    return "desconhecido"
