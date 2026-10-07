"""
Painel único: quanto ela gastou, onde falhou, o que piorou, o que espera decisão sua.

Já existiam `/custo`, `/traces`, `/lacunas`, `/evals`, `/backups`... em rotas separadas. Aqui tudo numa
resposta só (`GET /painel`) e numa aba da tela. Cada seção é coletada de forma independente: uma que
falha vira `{"erro": ...}` e não derruba as outras. Só lê o que já está no disco: ZERO chamadas de modelo.
"""

import os
import time
from datetime import date
from typing import Any, Callable, Dict, List, Optional


def _custo() -> Dict[str, Any]:
    from .token_ledger import resumo
    r = resumo(horas=24.0)
    return {"chamadas": r["chamadas"], "usd": r["usd_total"], "projecao_mes_usd": r["usd_projecao_mes"],
            "taxa_cache": r["taxa_cache"], "top": [{"funcao": x["funcao"], "chamadas": x["chamadas"], "usd": x["usd"]} for x in r["por_funcao"][:5]]}


def _latencia() -> Dict[str, Any]:
    from .traces import resumo
    return resumo()


def _lacunas() -> Dict[str, Any]:
    from ..learning.gaps import get_ledger
    led = get_ledger()
    return {"total_7d": led.total(7), "grupos": led.agrupar(7, 5)}


def _regressao() -> Dict[str, Any]:
    from ..learning.regressao import resumo_gratis
    r = resumo_gratis()
    return {"casos": r["casos"], "avaliaveis": r["avaliaveis"], "regras_fora_do_prompt": len(r["regras_fora_do_prompt"])}


def _atencao() -> Dict[str, Any]:
    from ..proactive.atencao import get_atencao
    a = get_atencao()
    hoje = time.time() - 86400
    from ..proactive.reacao import get_reacao
    return {"assuntos_ativos": a.assuntos_ativos(), "falas_24h": len([t for t in a._falas if t >= hoje]), "reacao": get_reacao().resumo()}


def _backups() -> Dict[str, Any]:
    from ..host import backup
    lista = backup.listar()
    return {"total": len(lista), "ultimo": lista[0]["dia"] if lista else None, "hoje": bool(lista and lista[0]["dia"] == date.today().isoformat())}


def _pendentes() -> Dict[str, Any]:
    from ..learning.lesson_guards import get_guard_store
    from ..learning.self_review import get_melhorias
    from ..plugins import get_plugin_store
    from ..skills import get_skill_store
    return {"skills": len(get_skill_store().pendentes()), "ferramentas": len(get_plugin_store().pendentes()),
            "melhorias": len(get_melhorias().listar("pendente")), "regras": len(get_guard_store().listar("pendente"))}


def _seguranca() -> Dict[str, Any]:
    from ..api.session_token import modo_configurado
    try:
        from ..policy.approvals import get_broker
        modo = get_broker().modo
    except Exception:
        modo = "desconhecido"
    return {"token_modo": modo_configurado(), "aprovacao_modo": modo, "mcp_ativo": os.getenv("MCP_ENABLED", "true").lower() not in ("0", "false", "no")}


COLETORES: Dict[str, Callable[[], Dict[str, Any]]] = {
    "custo": _custo, "latencia": _latencia, "lacunas": _lacunas, "regressao": _regressao,
    "atencao": _atencao, "backups": _backups, "pendentes": _pendentes, "seguranca": _seguranca,
}


def alertas_de(d: Dict[str, Any]) -> List[str]:
    """O que merece a sua atenção, em frases curtas (só olha os números já coletados)."""
    a: List[str] = []
    ok = lambda k: isinstance(d.get(k), dict) and "erro" not in d[k]  # noqa: E731
    if ok("backups") and not d["backups"]["hoje"]:
        a.append("Ainda não há backup de hoje da memória.")
    if ok("seguranca") and d["seguranca"]["token_modo"] != "exigir":
        a.append(f"O token de sessão está em modo '{d['seguranca']['token_modo']}': o backend ainda aceita quem não o envia.")
    if ok("pendentes"):
        n = sum(d["pendentes"].values())
        if n:
            a.append(f"{n} item(ns) esperando a sua decisão na aba Aprovações.")
    if ok("regressao") and d["regressao"]["regras_fora_do_prompt"]:
        a.append(f"{d['regressao']['regras_fora_do_prompt']} regra(s) que você ensinou não chegam ao prompt.")
    if ok("lacunas") and d["lacunas"]["total_7d"] >= 5:
        a.append(f"{d['lacunas']['total_7d']} falhas registradas nos últimos 7 dias.")
    if ok("custo") and d["custo"]["chamadas"] and d["custo"]["taxa_cache"] < 0.05 and d["custo"]["chamadas"] > 30:
        a.append("Quase nada do prompt está vindo do cache (taxa < 5%): pode estar gastando mais que o necessário.")
    erros = [k for k, v in d.items() if isinstance(v, dict) and "erro" in v]
    if erros:
        a.append("Não consegui ler: " + ", ".join(erros) + ".")
    return a


def montar(coletores: Optional[Dict[str, Callable[[], Dict[str, Any]]]] = None) -> Dict[str, Any]:
    dados: Dict[str, Any] = {}
    for nome, fn in (coletores or COLETORES).items():
        try:
            dados[nome] = fn()
        except Exception as exc:
            dados[nome] = {"erro": f"{type(exc).__name__}: {str(exc)[:80]}"}
    dados["alertas"] = alertas_de(dados)
    dados["gerado_em"] = time.time()
    return dados
