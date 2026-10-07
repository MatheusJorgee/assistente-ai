"""
Cópia de segurança do que a Quinta APRENDEU (memória, lembretes, pessoas, lições, skills...).

Um disco ruim, uma faxina mal feita ou um erro seu apagaria meses de aprendizado. Uma cópia por dia,
com manifesto (hash de cada arquivo), 14 dias de histórico e restauração verificada.

O que entra: bancos SQLite (copiados pela API de backup do SQLite, sem travar quem está usando), os
arquivos de estado (.json/.jsonl), os diários, skills e plugins aprovados.
O que NÃO entra, de propósito: `.env`, `.vault`, `mcp.json` (pode ter chaves), logs, caches (holo/tts),
quarentena, sandbox e auditoria.

Restaurar NÃO sobrescreve arquivo aberto: o pedido fica marcado e é aplicado no PRÓXIMO boot, antes de
qualquer banco ser aberto, depois de conferir os hashes e de guardar uma cópia "pre_restauracao" do
estado atual (restaurar também é desfazível). Local, sem LLM.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

MANTER_DIAS = 14
NOME_PENDENTE = "restaurar_no_boot.json"
_BASE = Path(__file__).resolve().parents[2]

# (subpasta relativa, padrões) — só o que é APRENDIZADO/ESTADO do usuário
_ORIGENS = [
    (".runtime", ("*.db", "*.json", "*.jsonl")),
    ("data", ("*.db", "diario_*.txt")),
    ("skills_agent", ("**/SKILL.md",)),
    ("plugins_agent", ("*.py", "manifest.json")),
]
_EXCLUIR_NOMES = {"mcp.json", "eval_ultimo.json"}          # mcp.json pode ter chaves
_EXCLUIR_PARTES = {".vault", "sandbox", "audit", "holo_cache", "tts_cache", "quarentena", "traces", ".versions", ".versoes", ".arquivo", "backups"}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def selecionar(base: Path) -> List[Path]:
    """Caminhos relativos a `base` que entram no backup."""
    achados: List[Path] = []
    for sub, padroes in _ORIGENS:
        raiz = Path(base) / sub
        if not raiz.exists():
            continue
        for padrao in padroes:
            for arq in raiz.glob(padrao):
                if not arq.is_file() or arq.name in _EXCLUIR_NOMES or _EXCLUIR_PARTES & set(arq.relative_to(base).parts):
                    continue
                if arq.suffix == ".log" or arq.name.endswith(".err"):
                    continue
                rel = arq.relative_to(base)
                if rel not in achados:
                    achados.append(rel)
    return sorted(achados)


def _copiar(origem: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origem.suffix == ".db":
        src = sqlite3.connect(f"file:{origem.as_posix()}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(str(destino))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    else:
        shutil.copy2(origem, destino)


def fazer_backup(base: Optional[Path] = None, destino_raiz: Optional[Path] = None, *,
                 hoje: Optional[date] = None, forcar: bool = False) -> Optional[Path]:
    """Cria backups/AAAA-MM-DD. Devolve a pasta, ou None se já existe o de hoje (e não é `forcar`)."""
    base = Path(base or _BASE)
    raiz = Path(destino_raiz or base / "backups")
    dia = (hoje or date.today()).isoformat()
    final = raiz / dia
    if final.exists() and not forcar:
        return None
    raiz.mkdir(parents=True, exist_ok=True)
    tmp = raiz / f".{dia}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    arquivos: Dict[str, Dict[str, Any]] = {}
    for rel in selecionar(base):
        try:
            _copiar(base / rel, tmp / rel)
            copiado = tmp / rel
            arquivos[rel.as_posix()] = {"sha": _sha(copiado), "bytes": copiado.stat().st_size}
        except (OSError, sqlite3.Error):
            continue   # um arquivo ruim não pode impedir o resto do backup
    (tmp / "manifesto.json").write_text(json.dumps({"dia": dia, "criado": time.time(), "arquivos": arquivos},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    if final.exists():
        shutil.rmtree(final)
    os.replace(tmp, final)
    podar(raiz)
    return final


def podar(raiz: Path, manter: int = MANTER_DIAS) -> int:
    dias = sorted(p for p in Path(raiz).iterdir() if p.is_dir() and _e_dia(p.name)) if Path(raiz).exists() else []
    apagados = 0
    for velho in dias[:-manter] if manter > 0 else dias:
        shutil.rmtree(velho, ignore_errors=True)
        apagados += 1
    return apagados


def _e_dia(nome: str) -> bool:
    try:
        date.fromisoformat(nome)
        return True
    except ValueError:
        return False


def verificar(pasta: Path) -> List[str]:
    """Problemas do backup (vazio = íntegro): arquivo ausente ou com hash diferente do manifesto."""
    try:
        man = json.loads((Path(pasta) / "manifesto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["manifesto ausente ou ilegível"]
    problemas = []
    for rel, info in man.get("arquivos", {}).items():
        arq = Path(pasta) / rel
        if not arq.exists():
            problemas.append(f"{rel}: ausente")
        elif _sha(arq) != info.get("sha"):
            problemas.append(f"{rel}: alterado ou corrompido")
    return problemas


def listar(raiz: Optional[Path] = None) -> List[Dict[str, Any]]:
    raiz = Path(raiz or _BASE / "backups")
    saida = []
    if raiz.exists():
        for p in sorted((x for x in raiz.iterdir() if x.is_dir() and _e_dia(x.name)), reverse=True):
            try:
                man = json.loads((p / "manifesto.json").read_text(encoding="utf-8"))
                saida.append({"dia": p.name, "arquivos": len(man.get("arquivos", {})),
                              "bytes": sum(i.get("bytes", 0) for i in man.get("arquivos", {}).values())})
            except (OSError, ValueError):
                saida.append({"dia": p.name, "arquivos": 0, "bytes": 0, "erro": "manifesto ilegível"})
    return saida


# ------------------------------------------------------------------ restauração (no próximo boot)

def agendar_restauracao(dia: str, base: Optional[Path] = None, destino_raiz: Optional[Path] = None) -> str:
    """Marca a restauração para o próximo boot. Devolve '' se ok, ou o motivo da recusa."""
    base = Path(base or _BASE)
    raiz = Path(destino_raiz or base / "backups")
    if not _e_dia(dia) or not (raiz / dia).is_dir():
        return "esse dia não tem backup"
    problemas = verificar(raiz / dia)
    if problemas:
        return "o backup está danificado: " + "; ".join(problemas[:3])
    (raiz / NOME_PENDENTE).write_text(json.dumps({"dia": dia, "pedido": time.time()}), encoding="utf-8")
    return ""


def aplicar_restauracao_pendente(base: Optional[Path] = None, destino_raiz: Optional[Path] = None) -> Optional[str]:
    """Chamado no INÍCIO do boot. Devolve o dia restaurado, ou None se não havia pedido/deu problema."""
    base = Path(base or _BASE)
    raiz = Path(destino_raiz or base / "backups")
    marca = raiz / NOME_PENDENTE
    if not marca.exists():
        return None
    try:
        dia = json.loads(marca.read_text(encoding="utf-8"))["dia"]
        pasta = raiz / dia
        marca.unlink()          # nunca repete: se algo falhar, não entra em laço a cada boot
        if not _e_dia(dia) or verificar(pasta):
            return None
        man = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
        _guardar_estado_atual(base, raiz)
        for rel in man["arquivos"]:
            destino = base / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            if destino.suffix == ".db":   # sobras do modo WAL do banco antigo corromperiam o restaurado
                for extra in (destino.with_name(destino.name + "-wal"), destino.with_name(destino.name + "-shm")):
                    extra.unlink(missing_ok=True)
            shutil.copy2(pasta / rel, destino)
        return dia
    except (OSError, ValueError, KeyError):
        return None


def _guardar_estado_atual(base: Path, raiz: Path) -> None:
    """Cópia 'pre_restauracao' do estado de agora (restaurar também é desfazível)."""
    pre = raiz / f"pre_restauracao_{int(time.time())}"
    for rel in selecionar(base):
        try:
            _copiar(base / rel, pre / rel)
        except (OSError, sqlite3.Error):
            continue
