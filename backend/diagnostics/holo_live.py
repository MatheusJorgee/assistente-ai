"""
Teste MANUAL dos hologramas com a REDE de verdade (não roda no smoke_test).

Uso:  python diagnostics/holo_live.py "Bahia" mapa
      python diagnostics/holo_live.py "Lisboa" viagem 4 2026-10-05

Mostra o texto que o LLM recebe, o payload que a tela recebe (resumido) e a latência. Grava o
payload em backend/data/holo_cache/ultimo_payload.json para conferir/usar como fixture.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import runtime_progress as rp  # noqa: E402
from core.tools.holograma_tool import HologramaTool  # noqa: E402


async def main() -> None:
    lugar = sys.argv[1] if len(sys.argv) > 1 else "Bahia"
    tipo = sys.argv[2] if len(sys.argv) > 2 else "mapa"
    dias = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    data = sys.argv[4] if len(sys.argv) > 4 else None
    eventos = []

    async def cb(t, d):
        eventos.append((t, d))

    t0 = time.perf_counter()
    with rp.com_progresso(cb):
        texto = await HologramaTool().execute(tipo=tipo, lugar=lugar, dias=dias, data_inicio=data)
    dt = time.perf_counter() - t0
    print(f"[{dt:.1f}s] TEXTO AO LLM ({len(texto)} chars):\n{texto}\n")
    for t, d in eventos:
        if t != "holo_show":
            continue
        tam = len(json.dumps(d, ensure_ascii=False))
        poli = d["geo"].get("polygon")
        pts = sum(len(a) for p in poli for a in p) if poli else 0
        print(f"holo_show: {d['titulo']} | {tam/1024:.1f} KB | polígono {pts} pts | geo {d['geo']['lat']},{d['geo']['lon']}")
        for p in d["paineis"]:
            n = len(p.get("itens") or p.get("dias") or p.get("secoes") or [])
            print(f"  - {p['tipo']:<10} status={p.get('status')} itens={n}")
            for it in (p.get("itens") or [])[:4]:
                print(f"      · {it['nome']}")
        print("  fontes:", ", ".join(f["nome"] for f in d["fontes"]))
        saida = Path(__file__).resolve().parents[1] / "data" / "holo_cache" / "ultimo_payload.json"
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
