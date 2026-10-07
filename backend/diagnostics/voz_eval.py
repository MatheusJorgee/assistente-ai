"""
Eval de voz (B11): mede a latência do /tts do backend para frases padrão (curta, média, longa).
Não chama nenhuma API paga (edge-tts é gratuito), mas precisa do backend rodando.

Uso:  python diagnostics/voz_eval.py [http://127.0.0.1:8000] [repeticoes]
"""

import json
import statistics
import sys
import time
import urllib.request

FRASES = {
    "curta": "Um instante.",
    "media": "Encontrei três museus perto de você, e o primeiro abre às nove da manhã.",
    "longa": ("Lisboa tem sol na maior parte da semana, com máximas perto de vinte e cinco graus. "
              "Vale reservar um dia para Belém e outro para Alfama, sempre com um casaco leve na mochila."),
}


def pedir(base: str, texto: str) -> tuple:
    corpo = json.dumps({"text": texto}).encode("utf-8")
    req = urllib.request.Request(f"{base}/tts", data=corpo, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        dados = r.read()
    return (time.perf_counter() - t0) * 1000, len(dados)


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    print(f"/tts em {base} ({n} repetições por frase)")
    for nome, texto in FRASES.items():
        tempos, tam = [], 0
        for _ in range(n):
            ms, tam = pedir(base, texto)
            tempos.append(ms)
        print(f"  {nome:<6} {len(texto):>3} chars | p50 {statistics.median(tempos):6.0f} ms | max {max(tempos):6.0f} ms | {tam/1024:5.1f} KB")
    try:
        with urllib.request.urlopen(f"{base}/traces", timeout=10) as r:
            print("traces:", json.dumps(json.loads(r.read())["etapas"], ensure_ascii=False))
    except Exception as exc:
        print("traces indisponíveis:", exc)


if __name__ == "__main__":
    main()
