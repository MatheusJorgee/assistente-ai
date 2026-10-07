"""
Ferramentas propostas pela Quinta: fila, testes isolados e aprovação (quarentena).

Fluxo:
  propor()      -> só cria um PENDENTE (código + testes + relatório do scanner). Nada é executado.
  rodar_testes()-> SÓ quando você pede: roda os testes num subprocesso separado (ambiente mínimo, pasta
                   temporária, prazo). Windows não tem limite de recursos por processo: o prazo mata o
                   processo, mas um teste malicioso poderia fazer estrago antes; por isso o scanner barra
                   o óbvio e você lê o código antes de rodar.
  aprovar()     -> exige: scanner sem críticos, testes que PASSARAM para este mesmo hash e nome coerente.
                   Grava em plugins_agent/ e no manifesto (hash pinado). Só carrega no PRÓXIMO boot.
  arquivar()    -> tira do manifesto (o arquivo vai para .arquivo/, nunca é apagado).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .scan import escanear

TAMANHO_MAX = 60 * 1024
PENDENTES_MAX = 20
PRAZO_TESTES_S = 20.0
NOME_RE = re.compile(r"^[a-z][a-z0-9_]{2,30}$")
_BASE = Path(__file__).resolve().parents[2]

_HARNESS = r'''
import asyncio, importlib.util, json, sys, traceback
sys.path.insert(0, sys.argv[1])
def carregar(caminho, nome):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
resultado = {"ok": False, "passaram": 0, "falhas": []}
try:
    plugin = carregar(sys.argv[2], "plugin_sob_teste")
    ns = {"plugin": plugin, "asyncio": asyncio}
    exec(compile(open(sys.argv[3], encoding="utf-8").read(), "testes", "exec"), ns)
    testes = [(k, v) for k, v in ns.items() if k.startswith("test_") and callable(v)]
    if not testes:
        resultado["falhas"].append("nenhuma função test_* nos testes")
    for nome, fn in testes:
        try:
            r = fn()
            if asyncio.iscoroutine(r):
                asyncio.run(r)
            resultado["passaram"] += 1
        except BaseException as exc:
            resultado["falhas"].append(f"{nome}: {type(exc).__name__}: {str(exc)[:200]}")
    resultado["ok"] = bool(testes) and not resultado["falhas"]
except BaseException as exc:
    resultado["falhas"].append(f"não carregou: {type(exc).__name__}: {str(exc)[:200]}")
print("@@RESULTADO@@" + json.dumps(resultado))
'''


def _sha(*partes: str) -> str:
    h = hashlib.sha256()
    for p in partes:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class PluginStore:
    def __init__(self, plugins_dir: Optional[Path] = None, pendentes_dir: Optional[Path] = None) -> None:
        self.dir = Path(plugins_dir or _BASE / "plugins_agent")
        self.pend = Path(pendentes_dir or _BASE / ".runtime" / "plugins_pendentes")
        self.manifesto = self.dir / "manifest.json"

    # ------------------------------------------------------------------ propor

    def propor(self, nome: str, descricao: str, codigo: str, testes: str, *, contaminado: bool = False) -> Tuple[bool, str]:
        nome = (nome or "").strip().lower()
        descricao = " ".join((descricao or "").split())[:200]
        if contaminado:
            return False, "Turno contaminado por conteúdo externo: não posso propor ferramentas agora."
        if not NOME_RE.match(nome):
            return False, "Nome inválido: minúsculas, números e _ (3 a 31 caracteres)."
        if not descricao or not codigo.strip() or not testes.strip():
            return False, "Faltou descrição, código ou testes (sem testes não há proposta)."
        if len(codigo.encode("utf-8")) + len(testes.encode("utf-8")) > TAMANHO_MAX:
            return False, "Código grande demais (máximo de 60 KB somando os testes)."
        rel_codigo, rel_testes = escanear(codigo), escanear(testes, teste=True)
        if rel_codigo["criticos"] or rel_testes["criticos"]:
            return False, "Bloqueada pelo scanner: " + "; ".join((rel_codigo["criticos"] + rel_testes["criticos"])[:5])
        self.pend.mkdir(parents=True, exist_ok=True)
        if len(list(self.pend.glob("*.json"))) >= PENDENTES_MAX:
            return False, "Há propostas demais esperando aprovação."
        pid = uuid.uuid4().hex[:10]
        (self.pend / f"{pid}.json").write_text(json.dumps({
            "id": pid, "nome": nome, "descricao": descricao, "codigo": codigo, "testes": testes,
            "sha": _sha(nome, codigo, testes), "avisos": rel_codigo["avisos"], "status": "pendente",
            "testes_ok_sha": "", "resultado_testes": None, "ts": time.time(),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        return True, f"Proposta '{nome}' guardada em quarentena; só vale depois que o Matheus rodar os testes e aprovar."

    # ------------------------------------------------------------------ fila

    def _arq(self, pid: str) -> Optional[Path]:
        if not re.fullmatch(r"[0-9a-f]{10}", pid or ""):
            return None
        a = self.pend / f"{pid}.json"
        return a if a.exists() else None

    def pendentes(self) -> List[Dict[str, Any]]:
        if not self.pend.exists():
            return []
        out = []
        for a in sorted(self.pend.glob("*.json")):
            try:
                d = json.loads(a.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if d.get("status") == "pendente":
                out.append(d)
        return out

    # ------------------------------------------------------------------ testes isolados

    def rodar_testes(self, pid: str, prazo_s: float = PRAZO_TESTES_S) -> Dict[str, Any]:
        a = self._arq(pid)
        if not a:
            return {"ok": False, "falhas": ["proposta não encontrada"]}
        d = json.loads(a.read_text(encoding="utf-8"))
        if _sha(d["nome"], d["codigo"], d["testes"]) != d["sha"]:
            return {"ok": False, "falhas": ["a proposta foi alterada depois de criada"]}
        if escanear(d["codigo"])["criticos"] or escanear(d["testes"], teste=True)["criticos"]:
            return {"ok": False, "falhas": ["o scanner bloqueou o código"]}
        from ..host.safe_env import build_env
        with tempfile.TemporaryDirectory() as tmp:
            pl, ts, hn = Path(tmp) / "plugin.py", Path(tmp) / "testes.py", Path(tmp) / "harness.py"
            pl.write_text(d["codigo"], encoding="utf-8")
            ts.write_text(d["testes"], encoding="utf-8")
            hn.write_text(_HARNESS, encoding="utf-8")
            try:
                p = subprocess.run([sys.executable, str(hn), str(_BASE), str(pl), str(ts)], cwd=tmp, env=build_env(),
                                   capture_output=True, text=True, timeout=prazo_s, encoding="utf-8", errors="replace")
                m = re.search(r"@@RESULTADO@@(\{.*\})", p.stdout)
                res = json.loads(m.group(1)) if m else {"ok": False, "passaram": 0, "falhas": [f"sem resultado (código {p.returncode})"]}
            except subprocess.TimeoutExpired:
                res = {"ok": False, "passaram": 0, "falhas": [f"passou de {int(prazo_s)}s e foi encerrado"]}
        d["resultado_testes"] = res
        d["testes_ok_sha"] = d["sha"] if res.get("ok") else ""
        a.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return res

    # ------------------------------------------------------------------ decisão

    def aprovar(self, pid: str, somente_leitura: bool = False) -> Tuple[bool, str]:
        a = self._arq(pid)
        if not a:
            return False, "Proposta não encontrada."
        d = json.loads(a.read_text(encoding="utf-8"))
        if d.get("status") != "pendente":
            return False, "Esta proposta já foi decidida."
        if _sha(d["nome"], d["codigo"], d["testes"]) != d["sha"]:
            return False, "A proposta foi alterada depois de criada; recusada."
        rel = escanear(d["codigo"])
        if rel["criticos"]:
            return False, "Bloqueada pelo scanner: " + "; ".join(rel["criticos"][:5])
        if d.get("testes_ok_sha") != d["sha"]:
            return False, "Rode os testes primeiro: só aprovo o que passou nos testes com este mesmo código."
        self.dir.mkdir(parents=True, exist_ok=True)
        destino = self.dir / f"{d['nome']}.py"
        if destino.exists():
            versoes = self.dir / ".versoes"
            versoes.mkdir(exist_ok=True)
            shutil.copy2(destino, versoes / f"{d['nome']}-{int(time.time())}.py")
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(d["codigo"], encoding="utf-8")
        os.replace(tmp, destino)
        man = self._ler_manifesto()
        man[d["nome"]] = {"sha": hashlib.sha256(d["codigo"].encode("utf-8")).hexdigest(), "aprovado_em": time.time(),
                          "leitura": bool(somente_leitura), "avisos": d.get("avisos", [])}
        self._gravar_manifesto(man)
        d["status"] = "aprovada"
        a.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return True, f"Ferramenta '{d['nome']}' aprovada. Ela passa a valer quando a Quinta for reiniciada."

    def rejeitar(self, pid: str) -> bool:
        a = self._arq(pid)
        if not a:
            return False
        d = json.loads(a.read_text(encoding="utf-8"))
        if d.get("status") != "pendente":
            return False
        d["status"] = "rejeitada"
        a.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    def arquivar(self, nome: str) -> bool:
        man = self._ler_manifesto()
        if nome not in man or not NOME_RE.match(nome):
            return False
        del man[nome]
        self._gravar_manifesto(man)
        arq = self.dir / f"{nome}.py"
        if arq.exists():
            (self.dir / ".arquivo").mkdir(exist_ok=True)
            shutil.move(str(arq), str(self.dir / ".arquivo" / f"{nome}-{int(time.time())}.py"))
        return True

    # ------------------------------------------------------------------ manifesto

    def _ler_manifesto(self) -> Dict[str, Any]:
        try:
            d = json.loads(self.manifesto.read_text(encoding="utf-8"))
            return dict(d) if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gravar_manifesto(self, man: Dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.manifesto.with_suffix(".tmp")
        tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.manifesto)

    def aprovadas(self) -> Dict[str, Any]:
        return self._ler_manifesto()


_instancia: Optional[PluginStore] = None


def get_plugin_store() -> PluginStore:
    global _instancia
    if _instancia is None:
        _instancia = PluginStore()
    return _instancia
