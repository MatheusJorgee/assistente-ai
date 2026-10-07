"""
Ledger de tokens e custo do Gemini.

Todo generate() registra aqui quanto gastou de entrada, cache, saida e raciocinio,
rotulado pela FUNCAO que fez a chamada (aviso proativo, chat, reflexao...). Sem isso
nao da pra saber onde o dinheiro vai — e o raciocinio ("thinking") e cobrado como saida.

Persistencia: backend/.runtime/token_ledger.jsonl (uma linha por chamada).
Nunca quebra uma requisicao: qualquer falha de escrita e engolida.
"""

import json
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# US$ por 1M de tokens (texto): (entrada, saida, leitura de cache).
# Fonte: ai.google.dev/gemini-api/docs/pricing em 2026-09-20. E ESTIMATIVA — serve pra
# comparar funcoes e achar vazamento, nao pra fechar fatura. Atualize quando o preco mudar.
PRECOS: Dict[str, Tuple[float, float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
    "gemini-2.5-flash": (0.30, 2.50, 0.03),
    "gemini-2.5-pro": (1.25, 10.00, 0.125),
    "gemini-3.1-flash-lite": (0.25, 1.50, 0.025),
    "gemini-3.5-flash-lite": (0.30, 2.50, 0.03),
    "gemini-3.5-flash": (1.50, 9.00, 0.15),
    "gemini-3.6-flash": (0.75, 3.75, 0.075),
    "gemini-3.7-flash": (0.75, 3.75, 0.075),
    "gemini-3.8-flash": (0.75, 3.75, 0.075),
    "gemini-3.1-pro": (2.00, 12.00, 0.20),
}
_PRECO_PADRAO = PRECOS["gemini-2.5-flash"]

_ARQUIVO = Path(__file__).resolve().parents[2] / ".runtime" / "token_ledger.jsonl"
_MAX_BYTES = 4 * 1024 * 1024
_MANTER_LINHAS = 20000

_lock = threading.Lock()
_escritas = 0


def _preco(modelo: str) -> Tuple[float, float, float]:
    """Casa pelo prefixo mais longo (ex.: 'gemini-2.5-flash-lite' antes de '...-flash')."""
    nome = (modelo or "").replace("models/", "")
    for chave in sorted(PRECOS, key=len, reverse=True):
        if nome.startswith(chave):
            return PRECOS[chave]
    return _PRECO_PADRAO


def custo_usd(modelo: str, prompt: int, cached: int, saida: int, pensou: int) -> float:
    """Custo estimado de UMA chamada. Raciocinio e cobrado como saida."""
    p_in, p_out, p_cache = _preco(modelo)
    novos = max(prompt - cached, 0)
    return (novos * p_in + cached * p_cache + (saida + pensou) * p_out) / 1_000_000


def _campo(usage: Any, nome: str) -> int:
    try:
        return int(getattr(usage, nome, 0) or 0)
    except Exception:
        return 0


def registrar(
    proposito: str,
    modelo: str,
    usage: Any,
    latencia_s: float,
    n_tools: int = 0,
    arquivo: Optional[Path] = None,
) -> None:
    """Grava uma chamada. Silencioso em caso de erro."""
    global _escritas
    try:
        prompt = _campo(usage, "prompt_token_count")
        cached = _campo(usage, "cached_content_token_count")
        saida = _campo(usage, "candidates_token_count")
        pensou = _campo(usage, "thoughts_token_count")
        linha = {
            "ts": round(time.time(), 1),
            "proposito": proposito or "desconhecido",
            "modelo": (modelo or "").replace("models/", ""),
            "entrada": prompt,
            "cache": cached,
            "saida": saida,
            "pensou": pensou,
            "seg": round(latencia_s, 2),
            "tools": n_tools,
            "usd": round(custo_usd(modelo, prompt, cached, saida, pensou), 7),
        }
        alvo = arquivo or _ARQUIVO
        with _lock:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with alvo.open("a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
            _escritas += 1
            if _escritas % 500 == 0:
                _podar(alvo)
    except Exception:
        pass


def _podar(alvo: Path) -> None:
    """Mantem o arquivo pequeno: se passou de 4MB, guarda so as ultimas linhas."""
    try:
        if alvo.stat().st_size <= _MAX_BYTES:
            return
        linhas = alvo.read_text(encoding="utf-8").splitlines()[-_MANTER_LINHAS:]
        alvo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    except Exception:
        pass


def resumo(horas: float = 24.0, arquivo: Optional[Path] = None) -> Dict[str, Any]:
    """Agrega o gasto da janela por funcao, do mais caro pro mais barato."""
    alvo = arquivo or _ARQUIVO
    corte = time.time() - horas * 3600
    por_funcao: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"chamadas": 0, "entrada": 0, "cache": 0, "saida": 0, "pensou": 0, "usd": 0.0, "modelos": set()}
    )
    try:
        with alvo.open("r", encoding="utf-8") as f:
            for bruto in f:
                try:
                    r = json.loads(bruto)
                except Exception:
                    continue
                if r.get("ts", 0) < corte:
                    continue
                d = por_funcao[r.get("proposito", "desconhecido")]
                d["chamadas"] += 1
                for k in ("entrada", "cache", "saida", "pensou"):
                    d[k] += int(r.get(k, 0) or 0)
                d["usd"] += float(r.get("usd", 0) or 0)
                d["modelos"].add(r.get("modelo", ""))
    except FileNotFoundError:
        pass
    except Exception:
        pass

    linhas = []
    for nome, d in por_funcao.items():
        linhas.append(
            {
                "funcao": nome,
                "chamadas": d["chamadas"],
                "entrada": d["entrada"],
                "cache": d["cache"],
                "saida": d["saida"],
                "pensou": d["pensou"],
                "usd": round(d["usd"], 5),
                "modelos": sorted(m for m in d["modelos"] if m),
            }
        )
    linhas.sort(key=lambda x: x["usd"], reverse=True)
    total = round(sum(x["usd"] for x in linhas), 5)
    chamadas = sum(x["chamadas"] for x in linhas)
    entrada = sum(x["entrada"] for x in linhas)
    cache = sum(x["cache"] for x in linhas)
    return {
        "janela_horas": horas,
        "chamadas": chamadas,
        "usd_total": total,
        "usd_projecao_mes": round(total / horas * 24 * 30, 2) if horas > 0 and chamadas else 0.0,
        "taxa_cache": round(cache / entrada, 3) if entrada else 0.0,
        "por_funcao": linhas,
        "nota": "Estimativa com precos oficiais de 2026-09-20; raciocinio cobrado como saida.",
    }
