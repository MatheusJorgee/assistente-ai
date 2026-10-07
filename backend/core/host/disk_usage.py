"""
Medição REAL de uso de disco (somente leitura, sem LLM, sem aprovação).

Responde "o que está ocupando espaço no meu PC?" com números de verdade: pastas maiores e arquivos
maiores, com orçamento de tempo (o disco todo pode levar minutos: devolve o que mediu até o prazo e
diz o que ficou de fora). Não segue links simbólicos nem junções (evita loop e dupla contagem;
no Windows isso inclui os placeholders do OneDrive), e ignora o que o sistema nega ler.
"""

import heapq
import os
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def formatar_bytes(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unidade == "TB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


def _e_link(entrada: "os.DirEntry") -> bool:
    try:
        if entrada.is_symlink():
            return True
        return bool(getattr(entrada.stat(follow_symlinks=False), "st_file_attributes", 0) & REPARSE)
    except OSError:
        return True


def tamanho_da_pasta(raiz: Path, prazo: float) -> Tuple[int, bool]:
    """(bytes, completo). `completo` False = o prazo estourou antes de terminar."""
    total = 0
    pilha = [str(raiz)]
    while pilha:
        if time.monotonic() > prazo:
            return total, False
        try:
            with os.scandir(pilha.pop()) as it:
                for e in it:
                    try:
                        if _e_link(e):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            pilha.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total, True


def medir_pastas(raiz: Path, top: int = 15, limite_s: float = 40.0) -> Dict[str, object]:
    """Tamanho de cada subpasta imediata de `raiz` (e dos arquivos soltos nela), maiores primeiro."""
    raiz = Path(raiz)
    prazo = time.monotonic() + max(1.0, limite_s)
    filhos: List[Path] = []
    soltos = 0
    try:
        with os.scandir(raiz) as it:
            for e in it:
                try:
                    if _e_link(e):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        filhos.append(Path(e.path))
                    elif e.is_file(follow_symlinks=False):
                        soltos += e.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError as exc:
        return {"erro": f"não consegui ler {raiz}: {exc.__class__.__name__}", "itens": [], "completo": False}

    resultados: List[Tuple[int, str, bool]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(tamanho_da_pasta, p, prazo): p for p in filhos}
        for fut, p in futuros.items():
            try:
                tam, ok = fut.result(timeout=max(0.5, prazo - time.monotonic() + 5))
            except Exception:
                tam, ok = 0, False
            resultados.append((tam, p.name, ok))
    itens = [{"nome": n, "bytes": t, "parcial": not ok} for t, n, ok in sorted(resultados, reverse=True)[: max(1, top)]]
    if soltos:
        itens.append({"nome": "(arquivos soltos nesta pasta)", "bytes": soltos, "parcial": False})
        itens.sort(key=lambda i: i["bytes"], reverse=True)
    return {"raiz": str(raiz), "itens": itens[: max(1, top)],
            "completo": all(ok for _, _, ok in resultados),
            "nao_medidas": [n for _, n, ok in resultados if not ok][:10]}


def maiores_arquivos(raiz: Path, top: int = 15, min_bytes: int = 100 * 1024 * 1024,
                     limite_s: float = 40.0) -> Dict[str, object]:
    """Os `top` maiores arquivos sob `raiz` (>= min_bytes), com o prazo de tempo."""
    prazo = time.monotonic() + max(1.0, limite_s)
    heap: List[Tuple[int, str]] = []
    pilha = [str(raiz)]
    completo = True
    while pilha:
        if time.monotonic() > prazo:
            completo = False
            break
        try:
            with os.scandir(pilha.pop()) as it:
                for e in it:
                    try:
                        if _e_link(e):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            pilha.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            tam = e.stat(follow_symlinks=False).st_size
                            if tam >= min_bytes:
                                if len(heap) < top:
                                    heapq.heappush(heap, (tam, e.path))
                                elif tam > heap[0][0]:
                                    heapq.heapreplace(heap, (tam, e.path))
                    except OSError:
                        continue
        except OSError:
            continue
    itens = [{"caminho": c, "bytes": t} for t, c in sorted(heap, reverse=True)]
    return {"raiz": str(raiz), "itens": itens, "completo": completo}


def resumo_discos() -> List[Dict[str, object]]:
    """Espaço total/usado/livre de cada unidade (psutil)."""
    try:
        import psutil
    except ImportError:
        return []
    saida = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in (part.opts or "") or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        saida.append({"unidade": part.mountpoint, "total": u.total, "usado": u.used, "livre": u.free})
    return saida
