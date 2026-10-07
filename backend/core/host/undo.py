"""
Desfazer (B1) para as operações de arquivo da Quinta: escrever, sobrescrever e apagar.

Regras:
  - Só empilha se SOUBER o estado anterior (sobrescrita guarda uma cópia; arquivo novo guarda que
    não existia; arquivo grande demais para copiar não entra na pilha e o resultado diz isso).
  - Apagar NÃO exclui: move para a quarentena (`data/quarentena/<id>/`). Só o expurgo (30 dias)
    apaga de verdade.
  - Pilha de 10. Ao desfazer confere se o arquivo continua como a Quinta deixou (sha256); se você
    mexeu depois, NÃO desfaz (não pisa no seu trabalho).
  - Zero chamadas de LLM: tudo local.
"""

import hashlib
import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

PILHA_MAX = 10
TAMANHO_MAX_COPIA = 5 * 1024 * 1024   # arquivo maior não é copiado: não empilha
RETENCAO_DIAS = 30
_DIR_PADRAO = Path(__file__).resolve().parents[2] / "data" / "quarentena"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


class UndoManager:
    def __init__(self, base: Optional[Path] = None) -> None:
        self._base = Path(base) if base else _DIR_PADRAO
        self._pilha: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ registro

    def _nova_pasta(self) -> Path:
        pasta = self._base / uuid.uuid4().hex[:12]
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _empilhar(self, entrada: Dict[str, Any]) -> None:
        with self._lock:
            self._pilha.append(entrada)
            while len(self._pilha) > PILHA_MAX:
                self._pilha.pop(0)  # a mais antiga sai da pilha (a cópia fica até o expurgo)
        self._salvar_indice()

    def antes_de_escrever(self, path: Path) -> Optional[Dict[str, Any]]:
        """Chame ANTES de escrever. Devolve o 'recibo' a ser fechado com `depois_de_escrever`,
        ou None se não dá para desfazer (ex.: arquivo grande demais)."""
        if path.exists():
            if not path.is_file() or path.stat().st_size > TAMANHO_MAX_COPIA:
                return None
            pasta = self._nova_pasta()
            shutil.copy2(path, pasta / "original")
            return {"tipo": "sobrescrita", "path": str(path), "backup": str(pasta / "original")}
        return {"tipo": "criado", "path": str(path)}

    def depois_de_escrever(self, recibo: Optional[Dict[str, Any]]) -> bool:
        if not recibo:
            return False
        p = Path(recibo["path"])
        try:
            recibo = dict(recibo, sha_depois=_sha(p), ts=time.time())
        except OSError:
            return False
        self._empilhar(recibo)
        return True

    def apagar_para_quarentena(self, path: Path) -> bool:
        """Move o arquivo/pasta para a quarentena e empilha. Levanta OSError se não conseguir."""
        pasta = self._nova_pasta()
        destino = pasta / "apagado"
        shutil.move(str(path), str(destino))
        self._empilhar({"tipo": "apagado", "path": str(path), "backup": str(destino), "ts": time.time()})
        return True

    # ------------------------------------------------------------------ desfazer

    def topo(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._pilha[-1]) if self._pilha else None

    def tamanho(self) -> int:
        with self._lock:
            return len(self._pilha)

    def desfazer(self) -> str:
        """Desfaz a última operação. Devolve uma frase para o usuário."""
        with self._lock:
            if not self._pilha:
                return "Não há nada para desfazer."
            entrada = self._pilha[-1]
        p = Path(entrada["path"])
        tipo = entrada["tipo"]
        try:
            if tipo == "criado":
                if p.exists() and _sha(p) != entrada.get("sha_depois"):
                    return f"Não desfiz: {p.name} mudou depois que eu o criei."
                if p.exists():
                    self._para_quarentena_sem_pilha(p)
                msg = f"Desfeito: {p.name} (arquivo que eu tinha criado) foi removido."
            elif tipo == "sobrescrita":
                if not p.exists() or _sha(p) != entrada.get("sha_depois"):
                    return f"Não desfiz: {p.name} mudou depois da minha escrita."
                shutil.copy2(entrada["backup"], p)
                msg = f"Desfeito: {p.name} voltou ao conteúdo de antes."
            elif tipo == "apagado":
                if p.exists():
                    return f"Não desfiz: já existe outro arquivo em {p}."
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(entrada["backup"], str(p))
                msg = f"Desfeito: {p.name} foi restaurado."
            else:
                return "Não sei desfazer essa operação."
        except OSError as exc:
            return f"Não consegui desfazer ({type(exc).__name__}). Nada foi alterado além do já feito."
        with self._lock:
            if self._pilha and self._pilha[-1] is entrada:
                self._pilha.pop()
        self._salvar_indice()
        return msg

    def _para_quarentena_sem_pilha(self, p: Path) -> None:
        pasta = self._nova_pasta()
        shutil.move(str(p), str(pasta / "removido_no_desfazer"))

    # ------------------------------------------------------------------ manutenção

    def expurgar(self, dias: int = RETENCAO_DIAS, *, agora: Optional[float] = None) -> int:
        """Apaga de verdade o que está na quarentena há mais de `dias`. Devolve quantas pastas."""
        if not self._base.exists():
            return 0
        limite = (agora if agora is not None else time.time()) - dias * 86400
        with self._lock:
            em_uso = {Path(e["backup"]).parent.name for e in self._pilha if e.get("backup")}
        n = 0
        for pasta in self._base.iterdir():
            if pasta.is_dir() and pasta.name not in em_uso and pasta.stat().st_mtime < limite:
                shutil.rmtree(pasta, ignore_errors=True)
                n += 1
        return n

    def _salvar_indice(self) -> None:
        """Índice só para inspeção manual (a pilha vive em memória: reiniciar zera o desfazer,
        mas os arquivos continuam na quarentena)."""
        try:
            self._base.mkdir(parents=True, exist_ok=True)
            with self._lock:
                dados = list(self._pilha)
            (self._base / "indice.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


_instancia: Optional[UndoManager] = None


def get_undo() -> UndoManager:
    global _instancia
    if _instancia is None:
        _instancia = UndoManager()
    return _instancia
