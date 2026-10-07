"""
Casos de regressão feitos das SUAS correções.

Toda vez que você corrige a Quinta, o caso vira um teste: a pergunta original, a resposta que estava
errada, a correção e a regra destilada. Assim uma melhoria (mudar prompt, modelo, política) prova que
melhorou e que não voltou a errar o que você já corrigiu.

Duas camadas, para não gastar crédito à toa:
  1. GRÁTIS e sempre disponível:
       - checagens determinísticas derivadas da regra ("não use lista", "responda curto", "sem emoji"...),
         validadas contra a própria resposta ruim (se ela não FALHA na checagem, a checagem é inútil e o
         caso é marcado como sem checagem válida);
       - teste de regras ativas: toda lição chega mesmo ao prompt? (só as mais reforçadas cabem.)
  2. PAGA e só quando VOCÊ pede, com orçamento: `rodar_avaliacao` refaz a pergunta de cada caso (uma
     chamada por caso, no máximo N) com o prompt de verdade e aplica as checagens. Nunca roda sozinha.

Privacidade: fica em .runtime/casos.jsonl (local), com segredos mascarados e textos cortados; você pode
apagar um caso.
"""

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .gaps import _SEGREDO, mascarar

_DIR = Path(__file__).resolve().parents[2] / ".runtime"
MAX_CASOS = 200
MAX_AVALIACAO = 10
_lock = threading.Lock()
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")
_LISTA = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.M)


def _mascarar_linhas(texto: str, limite: int) -> str:
    """Como `mascarar`, mas PRESERVA as quebras de linha (a checagem 'sem lista' depende delas)."""
    limpo = _SEGREDO.sub("[oculto]", texto or "")
    linhas = [re.sub(r"[ \t]+", " ", ln).strip() for ln in limpo.splitlines()]
    return "\n".join(ln for ln in linhas if ln)[:limite]


def _norm(t: str) -> str:
    import unicodedata
    sem = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in sem if unicodedata.category(c) != "Mn")


def _frases(texto: str) -> int:
    return len([f for f in re.split(r"(?<=[.!?])\s+|\n+", texto.strip()) if f.strip()])


# ------------------------------------------------------------------ checagens (texto -> passou?)
CHECAGENS: Dict[str, Callable[[str], bool]] = {
    "sem_lista": lambda t: not _LISTA.search(t),
    "curta": lambda t: _frases(t) <= 3 and len(t) <= 400,
    "sem_emoji": lambda t: not _EMOJI.search(t),
    "sem_markdown": lambda t: not re.search(r"(\*\*|__|^#{1,6}\s|`)", t, re.M),
    "sem_desculpas": lambda t: not re.search(r"desculp|perd[aã]o|sinto muito", _norm(t)),
}


def escolher_checagens(licao: str) -> List[str]:
    """Checagens aplicáveis a uma regra, por palavras-chave (a regra vem no imperativo: 'Não use...')."""
    n = _norm(licao)
    neg = bool(re.search(r"\bnao\b|\bsem\b|\bevite\b|\bpare\b|\bnunca\b", n))
    achadas = []
    if neg and re.search(r"lista|topico|bullet|enumer", n):
        achadas.append("sem_lista")
    if re.search(r"curt|breve|objetiv|uma frase|poucas palavras|resum|direto|conciso", n) and not neg:
        achadas.append("curta")
    if neg and "emoji" in n:
        achadas.append("sem_emoji")
    if neg and re.search(r"markdown|asterisc|negrito|formatac", n):
        achadas.append("sem_markdown")
    if re.search(r"desculp|perdao|sinto muito", n) and neg:
        achadas.append("sem_desculpas")
    return achadas


def aplicar(checagens: List[str], texto: str) -> List[str]:
    """Nomes das checagens que FALHARAM."""
    return [c for c in checagens if c in CHECAGENS and not CHECAGENS[c](texto or "")]


# ------------------------------------------------------------------ casos
class Casos:
    def __init__(self, arquivo: Optional[Path] = None) -> None:
        self._arq = Path(arquivo) if arquivo else _DIR / "casos.jsonl"

    def _ler(self) -> List[Dict[str, Any]]:
        try:
            saida = []
            for bruto in self._arq.read_text(encoding="utf-8").splitlines():
                try:
                    saida.append(json.loads(bruto))
                except ValueError:
                    continue
            return saida
        except OSError:
            return []

    def _gravar(self, casos: List[Dict[str, Any]]) -> None:
        self._arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._arq.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")
        tmp.replace(self._arq)

    def registrar(self, pergunta: str, resposta_ruim: str, correcao: str, licao: str) -> Optional[str]:
        """Cria (ou reforça) um caso. Devolve o id, ou None se não há o mínimo (pergunta e regra)."""
        pergunta, licao = mascarar(pergunta, 300), mascarar(licao, 160)
        if len(pergunta) < 3 or len(licao) < 8:
            return None
        ruim = _mascarar_linhas(resposta_ruim, 500)
        checagens = escolher_checagens(licao)
        # a checagem só vale se a resposta que você corrigiu FALHA nela (senão não detecta o erro)
        validas = [c for c in checagens if c in aplicar([c], ruim)] if ruim else []
        with _lock:
            casos = self._ler()
            for c in casos:
                if c["licao"] == licao:
                    c["reforcos"] = int(c.get("reforcos", 0)) + 1
                    self._gravar(casos)
                    return c["id"]
            caso = {"id": uuid.uuid4().hex[:10], "ts": time.time(), "pergunta": pergunta, "resposta_ruim": ruim,
                    "correcao": mascarar(correcao, 200), "licao": licao, "checagens": validas, "reforcos": 0}
            casos.append(caso)
            self._gravar(casos[-MAX_CASOS:])
            return caso["id"]

    def listar(self) -> List[Dict[str, Any]]:
        with _lock:
            return self._ler()

    def remover(self, cid: str) -> bool:
        with _lock:
            casos = self._ler()
            novos = [c for c in casos if c["id"] != cid]
            if len(novos) == len(casos):
                return False
            self._gravar(novos)
            return True


_instancia: Optional[Casos] = None


def get_casos() -> Casos:
    global _instancia
    if _instancia is None:
        _instancia = Casos()
    return _instancia


def registrar_caso(pergunta: str, resposta_ruim: str, correcao: str, licao: str) -> Optional[str]:
    return get_casos().registrar(pergunta, resposta_ruim, correcao, licao)


# ------------------------------------------------------------------ camada GRÁTIS: regras ativas
def regras_fora_do_prompt(licoes: List[Dict[str, Any]], max_no_prompt: int) -> List[str]:
    """Lições que NÃO chegam ao prompt (só as mais reforçadas cabem). É o tipo de regressão
    silenciosa: você a ensinou, ela não a vê."""
    ordenadas = sorted(licoes, key=lambda d: (int(d.get("reforcos", 0)), float(d.get("ts", 0))), reverse=True)
    return [str(d.get("texto", "")) for d in ordenadas[max_no_prompt:]]


def resumo_gratis(casos: Optional[Casos] = None) -> Dict[str, Any]:
    """Estado dos casos sem gastar nada."""
    lista = (casos or get_casos()).listar()
    try:
        from .lessons_store import _MAX_NO_PROMPT, get_lessons_store
        fora = regras_fora_do_prompt(get_lessons_store().listar(), _MAX_NO_PROMPT)
    except Exception:
        fora = []
    avaliaveis = [c for c in lista if c.get("checagens")]
    return {"casos": len(lista), "avaliaveis": len(avaliaveis), "sem_checagem": len(lista) - len(avaliaveis),
            "regras_fora_do_prompt": fora, "custo_estimado_chamadas": min(len(avaliaveis), MAX_AVALIACAO)}


# ------------------------------------------------------------------ camada PAGA (só sob demanda)
_ARQ_ULTIMO = _DIR / "eval_ultimo.json"


async def rodar_avaliacao(brain: Any, casos: Optional[Casos] = None, *, confirmar: bool = False,
                          maximo: int = MAX_AVALIACAO, arquivo_ultimo: Optional[Path] = None) -> Dict[str, Any]:
    """Refaz a pergunta de cada caso avaliável (UMA chamada por caso, no máximo `maximo`) com o
    prompt real e aplica as checagens. Sem `confirmar`, não faz nada (só diz o custo)."""
    casos_lista = [c for c in (casos or get_casos()).listar() if c.get("checagens")]
    alvo = casos_lista[-max(1, min(maximo, MAX_AVALIACAO)):]
    if not confirmar:
        return {"executado": False, "chamadas_previstas": len(alvo),
                "aviso": "Cada caso custa uma chamada ao modelo. Envie confirmar=true para rodar."}
    if not alvo:
        return {"executado": True, "chamadas": 0, "resultados": [], "motivo": "nenhum caso com checagem válida"}

    from ..llm_provider import Message
    sistema = str(getattr(brain, "system_prompt", "") or "")
    try:
        sistema += "\n\n" + (brain._licoes_prompt() or "")
    except Exception:
        pass
    resultados = []
    for c in alvo:
        try:
            resp = await brain.llm_provider.generate(
                messages=[Message(role="system", content=sistema), Message(role="user", content=c["pergunta"])],
                tools=None, temperature=0.2, max_tokens=512,
            )
            texto = (resp.text or "").strip()
        except Exception as exc:
            resultados.append({"id": c["id"], "ok": None, "erro": type(exc).__name__})
            continue
        falhas = aplicar(c["checagens"], texto)
        resultados.append({"id": c["id"], "ok": not falhas, "falhas": falhas, "licao": c["licao"]})

    arq = arquivo_ultimo or _ARQ_ULTIMO
    anterior: Dict[str, Any] = {}
    try:
        anterior = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        pass
    ok = sum(1 for r in resultados if r["ok"])
    resumo = {"executado": True, "chamadas": len(resultados), "passaram": ok, "total": len(resultados),
              "resultados": resultados, "ts": time.time()}
    prev = {r["id"]: r["ok"] for r in anterior.get("resultados", [])}
    resumo["regrediu"] = [r["id"] for r in resultados if r["ok"] is False and prev.get(r["id"]) is True]
    resumo["melhorou"] = [r["id"] for r in resultados if r["ok"] is True and prev.get(r["id"]) is False]
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(resumo, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return resumo
