"""
Teste de integração com o Gemini de VERDADE (opt-in). NUNCA roda no smoke_test.

O smoke bloqueia a API de propósito (para não gastar crédito), então nada testa a conversa real. Este
script roda poucas conversas fixas contra o modelo real e confere o comportamento: escolheu a ferramenta
certa? respondeu curto? quantas chamadas gastou?

  python diagnostics/integracao_real.py              # só mostra o plano e o custo máximo (não chama nada)
  python diagnostics/integracao_real.py --confirmo   # roda de verdade

Salvaguardas:
  - sem --confirmo, nenhuma chamada;
  - teto de chamadas ao modelo (padrão 14, `--max-chamadas`): passou do teto, PARA;
  - o YouTube é simulado (não abre navegador nem toca música); estado (lacunas, atenção...) vai para uma
    pasta temporária, sem sujar o seu;
  - ferramentas de leitura do PC (disco) rodam de verdade; nada crítico é executado.
"""

import argparse
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CENARIOS = [
    {"nome": "conversa simples", "mensagem": "oi, tudo bem?", "espera_ferramentas": [], "max_chamadas": 2, "max_palavras": 60},
    {"nome": "espaço em disco (ferramenta real, só leitura)", "mensagem": "o que está ocupando mais espaço no meu disco C?",
     "espera_ferramentas": ["sistema"], "max_chamadas": 4, "max_palavras": 200},
    {"nome": "onde fica (holograma)", "mensagem": "onde fica a Bahia?", "espera_ferramentas": ["mostrar_holograma"], "max_chamadas": 4, "max_palavras": 120},
    {"nome": "pedido de música (automação simulada)", "mensagem": "toca Numb do Linkin Park", "espera_ferramentas": ["tocar_youtube_invisivel"],
     "max_chamadas": 2, "max_palavras": 40},
    {"nome": "não inventar (pergunta que exige ferramenta)", "mensagem": "quais processos estão usando mais memória agora?",
     "espera_ferramentas": ["sistema"], "max_chamadas": 4, "max_palavras": 200},
]


class AutomacaoFalsa:
    async def tocar_youtube_invisivel(self, pesquisa, **k):
        return f"(simulado) tocando {pesquisa}"


def _preparar_estado_isolado() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quinta_integracao_"))
    import core.learning.gaps as gp
    import core.proactive.atencao as at
    import core.learning.regressao as rg
    import core.learning.self_review as sr
    gp._instancia = gp.LedgerLacunas(tmp / "lacunas.jsonl")
    at._instancia = at.Atencao(tmp / "atencao.json")
    rg._instancia = rg.Casos(tmp / "casos.jsonl")
    sr._instancia = sr.Melhorias(tmp / "melhorias.json")


async def _rodar(max_chamadas_total: int) -> int:
    from brain.quinta_feira_brain import QuintaFeiraBrain
    from core import runtime_progress as rp
    from core.gemini_provider import GeminiAdapter
    from core.tools import inicializar_ferramentas

    chamadas = {"n": 0}

    class Estouro(Exception):
        pass

    for nome in ("_chamar_com_fallback", "generate_stream"):
        original = getattr(GeminiAdapter, nome)

        if nome == "generate_stream":
            def embrulha(orig):
                async def f(self, *a, **k):
                    chamadas["n"] += 1
                    if chamadas["n"] > max_chamadas_total:
                        raise Estouro(f"teto de {max_chamadas_total} chamadas atingido")
                    async for item in orig(self, *a, **k):
                        yield item
                return f
        else:
            def embrulha(orig):
                async def f(self, *a, **k):
                    chamadas["n"] += 1
                    if chamadas["n"] > max_chamadas_total:
                        raise Estouro(f"teto de {max_chamadas_total} chamadas atingido")
                    return await orig(self, *a, **k)
                return f
        setattr(GeminiAdapter, nome, embrulha(original))

    _preparar_estado_isolado()
    brain = QuintaFeiraBrain(llm_provider=GeminiAdapter(), tool_registry=inicializar_ferramentas())
    await brain.initialize()
    brain._automation = AutomacaoFalsa()
    vis = brain.tool_registry._tools.get("capturar_tela")
    if vis:
        vis.set_brain(brain)

    falhas: List[str] = []
    resultados: List[Dict[str, Any]] = []
    for c in CENARIOS:
        usadas: List[str] = []

        async def ouvir(tipo: str, dados: Dict[str, Any]) -> None:
            if tipo == "tool_call_start":
                usadas.append(str(dados.get("tool")))

        antes, t0 = chamadas["n"], time.time()
        try:
            with rp.com_progresso(ouvir):
                resp = await asyncio.wait_for(brain.ask(c["mensagem"]), timeout=120)
            texto = (resp.text or "").strip()
            erro = ""
        except Exception as exc:
            texto, erro = "", f"{type(exc).__name__}: {exc}"
        gastas = chamadas["n"] - antes
        problemas = []
        if erro:
            problemas.append(f"exceção: {erro[:100]}")
        for f in c["espera_ferramentas"]:
            if f not in usadas:
                problemas.append(f"não usou a ferramenta esperada '{f}' (usou: {usadas or 'nenhuma'})")
        if not c["espera_ferramentas"] and usadas:
            problemas.append(f"usou ferramenta sem precisar: {usadas}")
        if gastas > c["max_chamadas"]:
            problemas.append(f"gastou {gastas} chamadas (teto do cenário: {c['max_chamadas']})")
        if len(texto.split()) > c["max_palavras"]:
            problemas.append(f"resposta longa demais ({len(texto.split())} palavras)")
        if not texto and not erro:
            problemas.append("resposta vazia")
        resultados.append({"cenario": c["nome"], "ok": not problemas, "chamadas": gastas, "s": round(time.time() - t0, 1),
                           "ferramentas": usadas, "resposta": texto[:160], "problemas": problemas})
        falhas += [f"{c['nome']}: {p}" for p in problemas]

    print("\n=== RESULTADO ===")
    for r in resultados:
        print(f"[{'OK ' if r['ok'] else 'FALHOU'}] {r['cenario']} | {r['chamadas']} chamada(s) | {r['s']}s | ferramentas: {r['ferramentas'] or '-'}")
        print(f"        resposta: {r['resposta']!r}")
        for p in r["problemas"]:
            print(f"        ! {p}")
    print(f"\nTotal: {chamadas['n']} chamada(s) ao modelo (teto {max_chamadas_total}).")
    return 1 if falhas else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirmo", action="store_true", help="roda de verdade (gasta crédito do Gemini)")
    ap.add_argument("--max-chamadas", type=int, default=16)
    a = ap.parse_args()
    previsto = sum(c["max_chamadas"] for c in CENARIOS)
    print(f"{len(CENARIOS)} cenários; no máximo {previsto} chamadas previstas (teto global {a.max_chamadas}).")
    for c in CENARIOS:
        print(f"  - {c['nome']}: '{c['mensagem']}' (até {c['max_chamadas']} chamadas)")
    if not a.confirmo:
        print("\nNada foi chamado. Rode com --confirmo para executar de verdade.")
        return 0
    os.environ.setdefault("PYTHONUTF8", "1")
    return asyncio.run(_rodar(a.max_chamadas))


if __name__ == "__main__":
    raise SystemExit(main())
