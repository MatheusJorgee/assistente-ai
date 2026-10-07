"""
Skills de texto (v1) com fila de aprovação (B6/B7).

Uma skill é `skills_agent/<nome>/SKILL.md`: frontmatter (name, description, created_by: agent) +
instruções em texto. SEM scripts (não há sandbox). Fluxo:

  propor()  -> NUNCA escreve em skills_agent/: cria um PENDENTE (com hash) em .runtime/skills_pendentes/
  aprovar() -> só o Matheus (a tool do LLM não chama isto): reescaneia, confere o hash e grava
               atômico, guardando a versão anterior em .versions/ (dá para reverter)
  rejeitar()/quarentena, reverter(), arquivar() (= "apagar" sem excluir)

Guardas: nome por regex; teto de 40 KB e de 50 pendentes; scanner (só achado CRÍTICO bloqueia);
turno contaminado não propõe; circuit-breaker de 3 falhas iguais seguidas. Zero chamadas de LLM.
"""

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TAMANHO_MAX = 40 * 1024
PENDENTES_MAX = 50
DESCRICAO_MAX = 200
FALHAS_MAX = 3
NOME_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
_BASE = Path(__file__).resolve().parents[2]

# Achados CRÍTICOS (bloqueiam). Skill é texto que o modelo LERÁ como instrução: o risco é ela
# mandar o modelo burlar regras, vazar segredos ou agir sem perguntar.
_CRITICOS = [
    ("tenta anular as regras do sistema", re.compile(
        r"ignore\s+(todas?\s+)?(as\s+)?(regras|instru[cç][õo]es|diretrizes)|desconsidere\s+(as\s+)?(regras|instru)"
        r"|ignore\s+previous|disregard\s+.*instructions", re.I)),
    ("manda pular a aprovação", re.compile(
        r"sem\s+(pedir|perguntar|precisar\s+d[ea])\s+(aprova[cç][ãa]o|permiss[ãa]o|confirma[cç][ãa]o)"
        r"|n[ãa]o\s+(pe[cç]a|pergunte)\s+(aprova|permiss|confirma)|bypass\s+approval|skip\s+approval", re.I)),
    ("manda ler ou enviar segredos", re.compile(
        r"(api[_ -]?key|token|senha|password|\.env|credenciais?)\W.{0,40}(envie|enviar|mande|mandar|cole|exiba|mostre|send|post|upload)"
        r"|(envie|enviar|mande|cole|send|post)\W.{0,40}(api[_ -]?key|token|senha|password|\.env|credenciais?)", re.I)),
    ("manda baixar e executar", re.compile(
        r"(baix|download|curl|wget|iwr|invoke-webrequest).{0,60}(execut|rode|run|iex|invoke-expression)|\|\s*(iex|sh|bash)\b", re.I)),
    ("esconde ações do usuário", re.compile(
        r"n[ãa]o\s+(conte|diga|avise|mencione)\s+ao\s+(matheus|usu[áa]rio)|esconda\s+do\s+(matheus|usu[áa]rio)"
        r"|without\s+telling\s+the\s+user", re.I)),
    ("mexe nas próprias skills/regras", re.compile(
        r"(apague|delete|remova|desative|desabilite)\s+(todas?\s+)?(as\s+)?(skills?|regras|guardas?|aprova[cç][õo]es)", re.I)),
]
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def escanear(texto: str) -> List[str]:
    """Rótulos dos achados críticos ([] = passou)."""
    return [rotulo for rotulo, rx in _CRITICOS if rx.search(texto or "")]


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def montar(nome: str, descricao: str, corpo: str) -> str:
    return f"---\nname: {nome}\ndescription: {descricao}\ncreated_by: agent\n---\n{corpo.strip()}\n"


def ler_frontmatter(texto: str) -> Tuple[Dict[str, str], str]:
    m = _FRONT.match(texto or "")
    if not m:
        return {}, texto or ""
    meta: Dict[str, str] = {}
    for linha in m.group(1).splitlines():
        if ":" in linha:
            k, v = linha.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


class SkillStore:
    def __init__(self, skills_dir: Optional[Path] = None, pendentes_dir: Optional[Path] = None) -> None:
        self.dir = Path(skills_dir or _BASE / "skills_agent")
        self.pend = Path(pendentes_dir or _BASE / ".runtime" / "skills_pendentes")
        self._lock = threading.Lock()
        self._motivo_seguido = ""   # circuit-breaker: o MESMO motivo de recusa, seguidas vezes
        self._n_seguidas = 0

    # ------------------------------------------------------------------ propor

    def _recusar(self, motivo: str) -> Tuple[bool, str]:
        if motivo == self._motivo_seguido:
            self._n_seguidas += 1
        else:
            self._motivo_seguido, self._n_seguidas = motivo, 1
        return False, motivo

    def propor(self, nome: str, descricao: str, corpo: str, *, contaminado: bool = False) -> Tuple[bool, str]:
        """Cria um PENDENTE. Devolve (ok, mensagem para o modelo). Nunca escreve em skills_agent/."""
        if self._n_seguidas >= FALHAS_MAX:
            return False, "Muitas propostas recusadas pelo mesmo motivo: pare de propor e pergunte ao Matheus."
        nome = (nome or "").strip().lower()
        descricao = " ".join((descricao or "").split())[:DESCRICAO_MAX]
        corpo = (corpo or "").strip()
        if contaminado:
            return self._recusar("Turno contaminado por conteúdo externo: não posso propor skills agora.")
        if not NOME_RE.match(nome):
            return self._recusar("Nome inválido: use minúsculas, números e hífen (3 a 40 caracteres).")
        if not descricao or not corpo:
            return self._recusar("Faltou a descrição ou o corpo da skill.")
        texto = montar(nome, descricao, corpo)
        if len(texto.encode("utf-8")) > TAMANHO_MAX:
            return self._recusar("Skill grande demais (máximo de 40 KB).")
        achados = escanear(texto)
        if achados:
            return self._recusar("Bloqueada pelo scanner: " + "; ".join(achados))
        existente = self.dir / nome / "SKILL.md"
        if existente.exists():
            meta, _ = ler_frontmatter(existente.read_text(encoding="utf-8"))
            if meta.get("created_by") != "agent":
                return self._recusar("Já existe uma skill sua com esse nome; eu só edito as que eu criei.")
        with self._lock:
            self.pend.mkdir(parents=True, exist_ok=True)
            if len(list(self.pend.glob("*.json"))) >= PENDENTES_MAX:
                return self._recusar("Há propostas demais esperando aprovação.")
            pid = uuid.uuid4().hex[:10]
            (self.pend / f"{pid}.json").write_text(json.dumps({
                "id": pid, "nome": nome, "descricao": descricao, "texto": texto, "sha": _sha(texto),
                "ts": time.time(), "status": "pendente", "edita": existente.exists(),
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        self._motivo_seguido, self._n_seguidas = "", 0
        return True, f"Proposta '{nome}' guardada; ela só passa a valer quando o Matheus aprovar na tela."

    # ------------------------------------------------------------------ decisões do Matheus

    def pendentes(self) -> List[Dict[str, Any]]:
        if not self.pend.exists():
            return []
        out = []
        for arq in sorted(self.pend.glob("*.json")):
            try:
                d = json.loads(arq.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if d.get("status") == "pendente":
                atual = self.dir / d["nome"] / "SKILL.md"
                d["texto_atual"] = atual.read_text(encoding="utf-8") if atual.exists() else ""
                out.append(d)
        return out

    def _carregar(self, pid: str) -> Optional[Tuple[Path, Dict[str, Any]]]:
        if not re.fullmatch(r"[0-9a-f]{10}", pid or ""):
            return None
        arq = self.pend / f"{pid}.json"
        if not arq.exists():
            return None
        return arq, json.loads(arq.read_text(encoding="utf-8"))

    def aprovar(self, pid: str) -> Tuple[bool, str]:
        achado = self._carregar(pid)
        if not achado:
            return False, "Proposta não encontrada."
        arq, d = achado
        if d.get("status") != "pendente":
            return False, "Esta proposta já foi decidida."
        texto = d["texto"]
        if _sha(texto) != d["sha"]:
            return False, "A proposta foi alterada depois de criada; recusada."
        crit = escanear(texto)  # reescaneia ao aplicar
        if crit:
            return False, "Bloqueada pelo scanner: " + "; ".join(crit)
        alvo = self.dir / d["nome"]
        atual = alvo / "SKILL.md"
        if atual.exists():
            meta, _ = ler_frontmatter(atual.read_text(encoding="utf-8"))
            if meta.get("created_by") != "agent":
                return False, "Existe uma skill sua com esse nome; não sobrescrevo."
            versoes = alvo / ".versions"
            versoes.mkdir(parents=True, exist_ok=True)
            shutil.copy2(atual, versoes / f"{int(time.time() * 1000)}.md")
        alvo.mkdir(parents=True, exist_ok=True)
        tmp = alvo / f".SKILL.{uuid.uuid4().hex[:6]}.tmp"
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, atual)  # gravação atômica
        d["status"] = "aprovada"
        arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return True, f"Skill '{d['nome']}' aprovada."

    def rejeitar(self, pid: str, quarentena: bool = False) -> bool:
        achado = self._carregar(pid)
        if not achado:
            return False
        arq, d = achado
        if d.get("status") != "pendente":
            return False
        d["status"] = "quarentena" if quarentena else "rejeitada"
        arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    # ------------------------------------------------------------------ uso e manutenção

    def listar(self) -> List[Dict[str, str]]:
        out = []
        if self.dir.exists():
            for pasta in sorted(p for p in self.dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
                arq = pasta / "SKILL.md"
                if arq.exists():
                    meta, _ = ler_frontmatter(arq.read_text(encoding="utf-8"))
                    out.append({"nome": pasta.name, "descricao": meta.get("description", ""), "por": meta.get("created_by", "")})
        return out

    def ler(self, nome: str) -> Optional[str]:
        nome = (nome or "").strip().lower()
        if not NOME_RE.match(nome):
            return None
        arq = self.dir / nome / "SKILL.md"
        if not arq.exists():
            return None
        return ler_frontmatter(arq.read_text(encoding="utf-8"))[1].strip()

    def reverter(self, nome: str) -> bool:
        if not NOME_RE.match(nome or ""):
            return False
        versoes = self.dir / nome / ".versions"
        ultimas = sorted(versoes.glob("*.md")) if versoes.exists() else []
        if not ultimas:
            return False
        shutil.copy2(ultimas[-1], self.dir / nome / "SKILL.md")
        ultimas[-1].unlink()
        return True

    def arquivar(self, nome: str) -> bool:
        """'Apagar' = arquivar (mover para .arquivo/); nunca exclui."""
        if not NOME_RE.match(nome or ""):
            return False
        origem = self.dir / nome
        if not origem.exists():
            return False
        destino = self.dir / ".arquivo" / f"{nome}-{int(time.time())}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origem), str(destino))
        return True

    def indice_para_prompt(self, limite: int = 8) -> str:
        """Uma linha por skill (nome: descrição): o modelo sabe que existem e lê o corpo sob demanda."""
        itens = self.listar()[:limite]
        if not itens:
            return ""
        linhas = "\n".join(f"- {s['nome']}: {s['descricao']}" for s in itens)
        return ("[SKILLS QUE O MATHEUS APROVOU — leia o corpo com a ferramenta `skills` (acao=ler) "
                f"quando o pedido combinar]\n{linhas}\n[/SKILLS]")


_instancia: Optional[SkillStore] = None


def get_skill_store() -> SkillStore:
    global _instancia
    if _instancia is None:
        _instancia = SkillStore()
    return _instancia
